#
# This module handles the mapping of config parameters to method arguments
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Design
# Constraints and Open Decisions", for the open items these narrow down):
#
# - map_config_to_method_args is handed a "node of the config model": either
#   a Fixture/TestCase entry (its `.params` mapping is used) or a plain
#   {name: value} mapping directly, so a caller that already extracted the
#   params map - or a test - can pass that straight through.
#
# - Matching is by parameter *name* only. Positional-only parameters and a
#   bare *args collector are never filled from config, since config has no
#   concept of positional order ("positional arguments are ignored").
#
# - A parameter's type hint drives conversion of the raw (already a
#   YAML-native literal, or possibly still a raw string from a --param
#   override) config value:
#     * no hint / Any -> the value is passed through unconverted.
#     * a value already an instance of the hinted type -> passed through.
#     * a hint that is a Fixture subclass (fixturerig.base.fixture.
#       Fixture, the base class device/interface implementations inherit
#       from - NOT fixturerig.config.model.Fixture, which is the config
#       *entry* describing one) -> the raw value is a *reference* to
#       another configured fixture, not a literal. This module has no
#       access to the rest of the config tree or the module loader, so it
#       never resolves that reference itself - see high-level-design's
#       "What syntax identifies a reference to another fixture?" and "Do
#       not assume every non-literal value is an object reference", both
#       still open. Instead it hands the raw value to a caller-supplied
#       `instantiate_fixture(value, hint)` callback and uses whatever
#       object comes back, only checking that it is actually an instance
#       of the hinted class. Callers that have no such reference to resolve
#       (plain unit tests, for instance) simply don't pass the callback,
#       and get a clear error instead of a silently wrong object.
#     * a ConfigPath (from a `parameterpath` config section) is resolved first
#       (see fixturerig.config.model) and the result converted like any other
#       value: a Path for a Path/str hint (str(path) for str), a URI string
#       for a str hint. A resolution failure (e.g. unknown base_module) is an
#       ArgumentMappingError.
#     * bool/int/float/str/Path -> coerced from a string when needed. A URI
#       string (e.g. "https://...") is never coerced to a Path; that is an
#       error, since Path() would silently mangle it.
#     * Optional[T] -> unwrapped to T (None passes through unchanged).
#     * list[T]/dict[K, V] -> each element/item converted recursively.
#     * anything else (unresolved generics, plain multi-type Unions,
#       dataclasses, ...) -> left as-is; this is the conservative fallback
#       called for by high-level-design's "How should generic and complex
#       types behave across subclasses?" open decision.
#
# - A function that declares **kwargs cannot, by itself, tell us which
#   names it actually accepts. When that happens we walk the owning
#   class's MRO looking for same-named methods (typically __init__)
#   further up the hierarchy that declare the remaining, still-unmatched
#   config names explicitly, so a subclass that only forwards **kwargs to
#   super().__init__(...) still gets its inherited parameters filled in.
#   Once an ancestor's method is found that does *not* itself declare
#   **kwargs, the walk stops - such a method isn't forwarding anything
#   further up the chain, so there is nothing left to discover past it.
#
# - Any config key left unmatched after that (own signature + MRO walk) is
#   a hard error, not a silent drop - see high-level-design's "Do not
#   silently consume misspelled parameters."
#
# - A config node may also carry a `fixturemap` ({parameter name: fixture
#   name}, testcases only). Its entries are matched like params, but a
#   mapped parameter must have a Fixture type hint - anything else is an
#   ArgumentMappingError, so a fixture name is never passed as a plain string.
#
# - A required parameter with a Fixture type hint that the config does not
#   name at all is resolved by its own parameter name: `psu: Psu` gets the
#   fixture configured as "psu". This only happens when an
#   instantiate_fixture callback is given. A parameter with a default keeps
#   its default; name it in the fixturemap to get a fixture instead.
#
# - map_config_to_methods maps one config node onto several callables at
#   once (for a testcase: __init__, setup, test and teardown). Every
#   callable gets each config key it names, so the same key may feed more
#   than one of them (e.g. a fixture used by both setup() and test()). Each
#   callable still raises for its own missing required parameters, and a
#   key is only an unknown parameter if *none* of the callables takes it.
#

from __future__ import annotations

import inspect
import types
import typing
from pathlib import Path
from typing import Any, Callable, Union

from fixturerig.base.fixture import Fixture
from fixturerig.config.model import ConfigError, ConfigPath, is_uri

_UNION_ORIGINS = {Union}
if hasattr(types, "UnionType"):  # `X | Y` syntax (Python 3.10+)
    _UNION_ORIGINS.add(types.UnionType)

_TRUE_STRINGS = {"true", "yes", "on", "1"}
_FALSE_STRINGS = {"false", "no", "off", "0"}

_SELF_NAMES = {"self", "cls"}


class ArgumentMappingError(Exception):
    """Raised when config parameters cannot be mapped onto a callable's arguments."""


InstantiateFixture = Callable[[Any, type], Any]


def map_config_to_method_args(
    config: Any,
    func: Any,
    instantiate_fixture: InstantiateFixture | None = None,
) -> dict[str, Any]:
    """
    Maps configuration parameters onto the arguments of a callable.

    :param config: A node of the config model - a Fixture/TestCase entry
        (its `.params` is used) or a plain {name: value} mapping.
    :param func: The class, or function/method, whose arguments are to be
        mapped. Passing a class maps onto its __init__.
    :param instantiate_fixture: Called as `instantiate_fixture(value, hint)`
        whenever a parameter's type hint is a Fixture subclass, to resolve
        the raw config value into an actual instance. Required only if such
        a parameter is actually encountered.
    :return: A dict of keyword arguments suitable for `func(**result)`.
    :raises ArgumentMappingError: on a required-and-missing parameter, an
        unconvertible value, an unresolvable fixture reference, or a
        config key that matches nothing in `func` (or its class's
        inheritance hierarchy).
    """
    params, fixture_keys = _config_params(config)
    mapped_args, remaining = _map_onto(params, fixture_keys, func, instantiate_fixture)
    if remaining:
        raise ArgumentMappingError(f"Unknown parameter(s) {sorted(remaining)} for {_describe(func)}")
    return mapped_args


def map_config_to_methods(
    config: Any,
    funcs: list[Any],
    instantiate_fixture: InstantiateFixture | None = None,
) -> list[dict[str, Any]]:
    """
    Maps configuration parameters onto the arguments of several callables.

    Like map_config_to_method_args, but every callable in `funcs` receives
    the config keys it names, so a key may be passed to more than one of
    them. A key is an unknown parameter only if no callable takes it.

    :return: One dict of keyword arguments per callable, in `funcs` order.
    :raises ArgumentMappingError: as map_config_to_method_args; an unknown
        key is reported once, against all of `funcs`.
    """
    params, fixture_keys = _config_params(config)
    results: list[dict[str, Any]] = []
    unmatched = set(params)
    for func in funcs:
        mapped_args, remaining = _map_onto(params, fixture_keys, func, instantiate_fixture)
        results.append(mapped_args)
        unmatched &= set(remaining)
    if unmatched:
        targets = ", ".join(_describe(func) for func in funcs)
        raise ArgumentMappingError(f"Unknown parameter(s) {sorted(unmatched)} for {targets}")
    return results


def _config_params(config: Any) -> tuple[dict[str, Any], set[str]]:
    """Return a config node's params merged with its fixturemap, and the fixturemap's keys."""
    params = getattr(config, "params", config)
    fixturemap = getattr(config, "fixturemap", {})
    return {**params, **fixturemap}, set(fixturemap)


def _map_onto(
    params: Any,
    fixture_keys: set[str],
    func: Any,
    instantiate_fixture: InstantiateFixture | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map `params` onto `func`; return the mapped kwargs and the unmatched keys."""
    sig = inspect.signature(func)
    hints = _resolve_hints(func)

    mapped_args: dict[str, Any] = {}
    consumed: set[str] = set()
    has_var_keyword = False

    for index, param in enumerate(sig.parameters.values()):
        if index == 0 and param.name in _SELF_NAMES:
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.POSITIONAL_ONLY):
            continue
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            has_var_keyword = True
            continue

        hint = hints.get(param.name, param.annotation)
        if param.name in params:
            mapped_args[param.name] = _convert_param(
                param.name, params[param.name], hint, fixture_keys, func, instantiate_fixture
            )
            consumed.add(param.name)
        elif param.default is not inspect.Parameter.empty:
            continue
        elif instantiate_fixture is not None and _is_fixture_hint(hint):
            # Not configured: the fixture is looked up by the parameter's own name.
            mapped_args[param.name] = _convert_value(param.name, hint, instantiate_fixture)
        else:
            raise ArgumentMappingError(f"Missing required parameter: {param.name!r} for {_describe(func)}")

    remaining = {name: value for name, value in params.items() if name not in consumed}

    if has_var_keyword and remaining:
        owner = _owning_class(func)
        if owner is not None:
            mapped_args.update(
                _map_via_mro(remaining, fixture_keys, owner, _target_name(func), consumed, instantiate_fixture)
            )
            remaining = {name: value for name, value in remaining.items() if name not in consumed}

    return mapped_args, remaining


def _map_via_mro(
    remaining: dict[str, Any],
    fixture_keys: set[str],
    owner: type,
    method_name: str,
    consumed: set[str],
    instantiate_fixture: InstantiateFixture | None,
) -> dict[str, Any]:
    """Walk `owner`'s MRO (excluding `owner` itself) looking for `method_name`
    overrides that declare parameters matching the still-unmatched config
    names in `remaining`. See the module docstring for the stopping rule.
    """
    mapped: dict[str, Any] = {}

    for base in inspect.getmro(owner)[1:]:
        member = base.__dict__.get(method_name)
        if member is None:
            continue  # this class doesn't define its own method by this name

        try:
            member_sig = inspect.signature(member)
        except (TypeError, ValueError):
            break  # nothing left to introspect (e.g. a builtin slot wrapper)

        member_hints = _resolve_hints(member)
        has_kwargs = False

        for index, param in enumerate(member_sig.parameters.values()):
            if index == 0 and param.name in _SELF_NAMES:
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.POSITIONAL_ONLY):
                continue
            if param.kind is inspect.Parameter.VAR_KEYWORD:
                has_kwargs = True
                continue
            if param.name in remaining:
                hint = member_hints.get(param.name, param.annotation)
                mapped[param.name] = _convert_param(
                    param.name, remaining[param.name], hint, fixture_keys, member, instantiate_fixture
                )
                consumed.add(param.name)

        remaining = {name: value for name, value in remaining.items() if name not in consumed}

        if not remaining:
            break
        if not has_kwargs:
            break  # this function doesn't forward extra kwargs further up the MRO

    return mapped


def _resolve_hints(func: Any) -> dict[str, Any]:
    target = func.__init__ if inspect.isclass(func) else func
    try:
        return typing.get_type_hints(target)
    except Exception:
        # Unresolvable forward reference, or similar. Fall back to raw
        # (possibly stringified) annotations per-parameter; _convert_value
        # treats anything that isn't a real class/generic as "leave as-is".
        return {}


def _owning_class(func: Any) -> type | None:
    if inspect.isclass(func):
        return func
    return _defining_class(func)


def _defining_class(func: Any) -> type | None:
    qualname = getattr(func, "__qualname__", None)
    module = inspect.getmodule(func)
    if not qualname or "." not in qualname or module is None:
        return None
    *path, _ = qualname.split(".")
    if "<locals>" in path:
        return None
    obj: Any = module
    for part in path:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj if inspect.isclass(obj) else None


def _target_name(func: Any) -> str:
    return "__init__" if inspect.isclass(func) else func.__name__


def _describe(func: Any) -> str:
    return getattr(func, "__qualname__", repr(func))


def _convert_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
        raise ArgumentMappingError(f"Cannot convert {value!r} to bool")
    return bool(value)


def _is_fixture_hint(hint: Any) -> bool:
    """Whether `hint` is a Fixture subclass, or a Union/Optional containing one."""
    if typing.get_origin(hint) in _UNION_ORIGINS:
        return any(_is_fixture_hint(arg) for arg in typing.get_args(hint))
    return inspect.isclass(hint) and issubclass(hint, Fixture)


def _convert_param(
    name: str,
    value: Any,
    hint: Any,
    fixture_keys: set[str],
    func: Any,
    instantiate_fixture: InstantiateFixture | None,
) -> Any:
    if name in fixture_keys and not _is_fixture_hint(hint):
        raise ArgumentMappingError(
            f"fixturemap entry {name!r} is not a fixture parameter of {_describe(func)}; "
            "its type hint must be a Fixture subclass"
        )
    return _convert_value(value, hint, instantiate_fixture)


def _convert_value(value: Any, hint: Any, instantiate_fixture: InstantiateFixture | None) -> Any:
    if isinstance(value, ConfigPath):
        try:
            value = value.resolve()
        except ConfigError as exc:
            raise ArgumentMappingError(str(exc)) from exc

    if hint is inspect.Parameter.empty or hint is None or hint is Any:
        return value

    origin = typing.get_origin(hint)

    if origin in _UNION_ORIGINS:
        args = typing.get_args(hint)
        non_none = [a for a in args if a is not type(None)]
        if value is None and type(None) in args:
            return None
        if len(non_none) == 1:
            return _convert_value(value, non_none[0], instantiate_fixture)
        last_error: Exception | None = None
        for candidate in non_none:
            try:
                return _convert_value(value, candidate, instantiate_fixture)
            except (TypeError, ValueError, ArgumentMappingError) as exc:
                last_error = exc
        raise ArgumentMappingError(f"Could not convert {value!r} to any of {hint}") from last_error

    if inspect.isclass(hint):
        if issubclass(hint, Fixture):
            if instantiate_fixture is None:
                raise ArgumentMappingError(
                    f"{hint.__qualname__} is a fixture reference ({value!r}); "
                    "an instantiate_fixture callback is required to resolve it"
                )
            resolved = instantiate_fixture(value, hint)
            if not isinstance(resolved, hint):
                raise ArgumentMappingError(
                    f"instantiate_fixture({value!r}, {hint.__qualname__}) returned "
                    f"{resolved!r}, which is not a {hint.__qualname__}"
                )
            return resolved

        if isinstance(value, hint) and not (hint is int and isinstance(value, bool)):
            return value

        if hint is bool:
            return _convert_bool(value)
        if hint in (int, float, str):
            try:
                return hint(value)
            except (TypeError, ValueError) as exc:
                raise ArgumentMappingError(f"Cannot convert {value!r} to {hint.__name__}") from exc
        if hint is Path:
            if isinstance(value, str) and is_uri(value):
                raise ArgumentMappingError(f"{value!r} is a URI, not a local path")
            return Path(value)

        # Unhandled concrete class: leave as-is (conservative fallback).
        return value

    if origin in (list, tuple, set, frozenset):
        args = typing.get_args(hint)
        elem_type = args[0] if args else Any
        return origin(_convert_value(v, elem_type, instantiate_fixture) for v in value)

    if origin is dict:
        args = typing.get_args(hint)
        key_type, val_type = args if len(args) == 2 else (Any, Any)
        return {
            _convert_value(k, key_type, instantiate_fixture): _convert_value(v, val_type, instantiate_fixture)
            for k, v in value.items()
        }

    # Unresolved/unsupported generic construct: leave the value as-is.
    return value

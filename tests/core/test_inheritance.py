from pathlib import Path

import pytest

from fixturerig.config.model import Fixture as FixtureEntry
from fixturerig.config.model import TestCase as TestCaseEntry
from fixturerig.core.inheritance import ArgumentMappingError, map_config_to_method_args, map_config_to_methods
from fixturerig.base.fixture import Fixture


# --- basic name matching, defaults, positional args -------------------------


def test_matches_by_name_and_converts_using_type_hints():
    class VoltageLimitTest:
        def __init__(self, power_supply: str, limit: float):
            self.power_supply = power_supply
            self.limit = limit

    mapped = map_config_to_method_args({"power_supply": "psu1", "limit": "4.5"}, VoltageLimitTest)

    assert mapped == {"power_supply": "psu1", "limit": 4.5}
    assert isinstance(mapped["limit"], float)


def test_missing_required_parameter_raises():
    def func(a: int, b: int):
        pass

    with pytest.raises(ArgumentMappingError, match="b"):
        map_config_to_method_args({"a": 1}, func)


def test_default_used_when_absent_from_config():
    def func(a: int, b: int = 7):
        pass

    mapped = map_config_to_method_args({"a": 1}, func)

    assert mapped == {"a": 1}


def test_unknown_config_key_raises():
    def func(a: int):
        pass

    with pytest.raises(ArgumentMappingError, match="b"):
        map_config_to_method_args({"a": 1, "b": 2}, func)


def test_positional_only_and_var_positional_are_ignored():
    def func(a, /, *args, b: int):
        pass

    # "a" (positional-only) can't be filled by name even though config has it;
    # it's simply never consulted, so it isn't reported as unknown either.
    mapped = map_config_to_method_args({"b": 3}, func)

    assert mapped == {"b": 3}


# --- config node handling ----------------------------------------------------


def test_accepts_plain_params_dict():
    def func(limit: float):
        pass

    mapped = map_config_to_method_args({"limit": "1.5"}, func)

    assert mapped == {"limit": 1.5}


def test_accepts_config_model_entry():
    def func(limit: float):
        pass

    entry = TestCaseEntry(name="t", cls="pkg.T", params={"limit": "1.5"})

    mapped = map_config_to_method_args(entry, func)

    assert mapped == {"limit": 1.5}


def test_config_model_fixture_entry_also_supported():
    def func(port: str):
        pass

    entry = FixtureEntry(name="f", cls="pkg.F", params={"port": "COM4"})

    mapped = map_config_to_method_args(entry, func)

    assert mapped == {"port": "COM4"}


# --- type conversion ----------------------------------------------------------


def test_bool_conversion_from_string():
    def func(enabled: bool):
        pass

    assert map_config_to_method_args({"enabled": "true"}, func) == {"enabled": True}
    assert map_config_to_method_args({"enabled": "no"}, func) == {"enabled": False}
    assert map_config_to_method_args({"enabled": False}, func) == {"enabled": False}


def test_path_conversion():
    def func(target: Path):
        pass

    mapped = map_config_to_method_args({"target": "a/b.yaml"}, func)

    assert mapped == {"target": Path("a/b.yaml")}


def test_optional_unwraps_and_passes_none_through():
    def func(limit: float | None = None):
        pass

    assert map_config_to_method_args({"limit": "4.5"}, func) == {"limit": 4.5}
    assert map_config_to_method_args({"limit": None}, func) == {"limit": None}


def test_list_and_dict_generics_convert_elements():
    def func(values: list[int], mapping: dict[str, float]):
        pass

    mapped = map_config_to_method_args(
        {"values": ["1", "2", "3"], "mapping": {"a": "1.5"}}, func
    )

    assert mapped == {"values": [1, 2, 3], "mapping": {"a": 1.5}}


def test_value_already_matching_hint_is_passed_through_unchanged():
    def func(limit: float):
        pass

    mapped = map_config_to_method_args({"limit": 4.5}, func)

    assert mapped == {"limit": 4.5}
    assert isinstance(mapped["limit"], float)


def test_unconvertible_value_raises():
    def func(limit: float):
        pass

    with pytest.raises(ArgumentMappingError):
        map_config_to_method_args({"limit": "not-a-number"}, func)


# --- Fixture base class references -------------------------------------------


class PowerSupply(Fixture):
    def __init__(self, port: str):
        self.port = port


def test_fixture_hint_without_callback_raises():
    def func(power_supply: PowerSupply):
        pass

    with pytest.raises(ArgumentMappingError, match="instantiate_fixture"):
        map_config_to_method_args({"power_supply": "psu1"}, func)


def test_fixture_hint_uses_instantiate_fixture_callback():
    def func(power_supply: PowerSupply):
        pass

    calls = []

    def instantiate_fixture(value, hint):
        calls.append((value, hint))
        return PowerSupply(port="COM4")

    mapped = map_config_to_method_args({"power_supply": "psu1"}, func, instantiate_fixture)

    assert isinstance(mapped["power_supply"], PowerSupply)
    assert mapped["power_supply"].port == "COM4"
    assert calls == [("psu1", PowerSupply)]


def test_fixture_hint_rejects_wrong_type_from_callback():
    def func(power_supply: PowerSupply):
        pass

    with pytest.raises(ArgumentMappingError, match="not a PowerSupply"):
        map_config_to_method_args(
            {"power_supply": "psu1"}, func, lambda value, hint: object()
        )


# --- **kwargs / MRO forwarding ------------------------------------------------


def test_kwargs_forwarding_matches_named_param_in_base_class():
    class Base:
        def __init__(self, power_supply: str):
            self.power_supply = power_supply

    class Mid(Base):
        def __init__(self, limit: float, **kwargs):
            super().__init__(**kwargs)
            self.limit = limit

    mapped = map_config_to_method_args(
        {"limit": "4.5", "power_supply": "psu1"}, Mid
    )

    assert mapped == {"limit": 4.5, "power_supply": "psu1"}


def test_kwargs_forwarding_stops_at_ancestor_without_kwargs():
    class Grandparent:
        def __init__(self, timeout: float):
            self.timeout = timeout

    class Base(Grandparent):
        # Does not declare **kwargs itself - the walk must stop here and
        # never reach Grandparent's `timeout`.
        def __init__(self, power_supply: str):
            self.power_supply = power_supply

    class Mid(Base):
        def __init__(self, limit: float, **kwargs):
            super().__init__(**kwargs)
            self.limit = limit

    with pytest.raises(ArgumentMappingError, match="timeout"):
        map_config_to_method_args(
            {"limit": "4.5", "power_supply": "psu1", "timeout": "1.0"}, Mid
        )


def test_kwargs_forwarding_reaches_two_ancestors_when_both_forward():
    class Grandparent:
        def __init__(self, timeout: float, **kwargs):
            self.timeout = timeout

    class Base(Grandparent):
        def __init__(self, power_supply: str, **kwargs):
            super().__init__(**kwargs)
            self.power_supply = power_supply

    class Mid(Base):
        def __init__(self, limit: float, **kwargs):
            super().__init__(**kwargs)
            self.limit = limit

    mapped = map_config_to_method_args(
        {"limit": "4.5", "power_supply": "psu1", "timeout": "1.0"}, Mid
    )

    assert mapped == {"limit": 4.5, "power_supply": "psu1", "timeout": 1.0}


def test_kwargs_without_matching_ancestor_param_raises():
    class Base:
        def __init__(self, power_supply: str):
            self.power_supply = power_supply

    class Mid(Base):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

    with pytest.raises(ArgumentMappingError, match="typo"):
        map_config_to_method_args({"power_supply": "psu1", "typo": "1"}, Mid)


# --- mapping onto several methods -------------------------------------------


def test_methods_each_get_the_params_they_name():
    class Case:
        def __init__(self, port: str):
            pass

        def setup(self, volt: float):
            pass

        def test(self, volt: float, limit: float):
            pass

    init, setup, test = map_config_to_methods(
        {"port": "COM1", "volt": "4.5", "limit": 6}, [Case, Case.setup, Case.test]
    )

    assert init == {"port": "COM1"}
    assert setup == {"volt": 4.5}
    assert test == {"volt": 4.5, "limit": 6.0}


def test_methods_unknown_param_is_one_no_method_takes():
    def setup(a: int):
        pass

    def test(b: int):
        pass

    with pytest.raises(ArgumentMappingError, match=r"\['typo'\]"):
        map_config_to_methods({"a": 1, "b": 2, "typo": 3}, [setup, test])


def test_methods_missing_required_param_of_any_method_raises():
    def setup(a: int):
        pass

    def test(b: int):
        pass

    with pytest.raises(ArgumentMappingError, match="'b'"):
        map_config_to_methods({"a": 1}, [setup, test])

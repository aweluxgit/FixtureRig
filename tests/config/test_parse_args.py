from pathlib import Path

import pytest

from fixturerig.config.parse_args import ArgsError, read_app_args


def test_parses_single_config_path():
    args = read_app_args(["--config", "some_config.yaml"])

    assert args.config_paths == [Path("some_config.yaml")]
    assert args.params == {}


def test_repeated_config_is_collected_in_order():
    args = read_app_args(["--config", "a.yaml", "--config", "b.yaml"])

    assert args.config_paths == [Path("a.yaml"), Path("b.yaml")]


def test_params_are_parsed_as_key_value_pairs():
    args = read_app_args(["--config", "a.yaml", "--param", "key=value", "--param", "volt=4.5"])

    assert args.params == {"key": "value", "volt": "4.5"}


def test_param_value_may_contain_equals_sign():
    args = read_app_args(["--config", "a.yaml", "--param", "expr=a=b"])

    assert args.params == {"expr": "a=b"}


def test_missing_config_raises_args_error():
    with pytest.raises(ArgsError, match="--config"):
        read_app_args([])


def test_param_without_equals_raises_args_error():
    with pytest.raises(ArgsError, match="key=value"):
        read_app_args(["--config", "a.yaml", "--param", "novalue"])


def test_duplicate_param_key_raises_args_error():
    with pytest.raises(ArgsError, match="more than once"):
        read_app_args(["--config", "a.yaml", "--param", "key=1", "--param", "key=2"])


def test_empty_param_key_raises_args_error():
    with pytest.raises(ArgsError, match="must not be empty"):
        read_app_args(["--config", "a.yaml", "--param", "=value"])

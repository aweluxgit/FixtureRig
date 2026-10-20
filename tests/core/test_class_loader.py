import pytest

from fixturerig.core.class_loader import ClassLoadError, load_class


def test_loads_class_by_fully_qualified_name():
    cls = load_class("fixturerig.base.fixture.Fixture")

    from fixturerig.base.fixture import Fixture

    assert cls is Fixture


def test_missing_dot_raises():
    with pytest.raises(ClassLoadError, match="fully qualified"):
        load_class("NoDotsHere")


def test_unimportable_module_raises():
    with pytest.raises(ClassLoadError, match="Could not import module"):
        load_class("fixturerig.does_not_exist.Whatever")


def test_missing_class_in_module_raises():
    with pytest.raises(ClassLoadError, match="no attribute"):
        load_class("fixturerig.base.fixture.NotAClass")


def test_non_class_attribute_raises():
    with pytest.raises(ClassLoadError, match="not resolve to a class"):
        load_class("fixturerig.core.class_loader.load_class")

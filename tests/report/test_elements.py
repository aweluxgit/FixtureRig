import pytest

from fixturerig.report import Chart, Image, Series, Table, Text


def test_simple_table_to_text_aligns_columns():
    table = Table([["U", 4.9], ["Current", None]], headers=["Signal", "Value"], title="Readings")

    assert table.is_simple
    assert table.to_text() == (
        "Readings\n"
        "+---------+-------+\n"
        "| Signal  | Value |\n"
        "+=========+=======+\n"
        "| U       | 4.9   |\n"
        "| Current |       |\n"
        "+---------+-------+"
    )


def test_complex_table_nests_elements_and_flattens_to_text():
    inner = Table([["a", 1]])
    table = Table([["inner", inner], ["note", Text("two\nlines")]])

    assert not table.is_simple
    text = table.to_text()
    assert "| a | 1 |" in text
    assert "two" in text and "lines" in text
    assert table.to_dict()["rows"][0][1]["type"] == "table"


def test_ragged_rows_are_padded():
    table = Table([["a"], ["b", "c"]])
    assert table.text_rows() == [["a", ""], ["b", "c"]]


@pytest.mark.parametrize("rows", ["abc", [["ok"], "bad"], [[object()]]])
def test_table_rejects_invalid_rows(rows):
    with pytest.raises(TypeError):
        Table(rows)


def test_series_requires_matching_lengths():
    with pytest.raises(ValueError, match="2 x value"):
        Series("U", [0, 1], [1])


def test_chart_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Unknown chart kind"):
        Chart("c", kind="pie")


def test_chart_to_text_summarizes_series():
    chart = Chart("Ramp", [Series("U", [0, 1, 2], [0, 2.5, 5]), Series("I", [], [])])
    assert chart.to_text() == "Chart: Ramp (line)\n  U: 3 point(s), min 0, max 5\n  I: no data"


def test_image_needs_exactly_one_source(tmp_path):
    with pytest.raises(ValueError):
        Image()
    with pytest.raises(ValueError):
        Image(path=tmp_path / "a.png", data=b"x")
    assert Image(data=b"abc").read_bytes() == b"abc"

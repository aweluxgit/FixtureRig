import pytest

from fixturerig.base import Verdict, VerdictStatus
from fixturerig.report import (
    Chart,
    ConsoleReport,
    GroupFinished,
    GroupStarted,
    ReportModule,
    ReportStream,
    Series,
    Table,
    TestFinished,
    TestStarted,
    Text,
    report,
)
from fixturerig.report import stream as stream_module


class Recorder(ReportModule):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.events = []
        self.closed = 0

    def on_event(self, event):
        self.events.append(event)

    def close(self):
        self.closed += 1


class OnlyText(Recorder):
    event_kinds = frozenset({"text"})


class Broken(ReportModule):
    def on_event(self, event):
        raise RuntimeError("module bug")

    def close(self):
        raise RuntimeError("close bug")


def kinds(module):
    return [event.kind for event in module.events]


def test_events_reach_every_module():
    first, second = Recorder(), Recorder()
    stream = ReportStream([first, second])

    stream.text("hello")

    assert kinds(first) == kinds(second) == ["text"]
    assert first.events[0].text == Text("hello")


def test_events_are_stamped_with_group_and_test_context():
    recorder = Recorder()
    stream = ReportStream([recorder])

    stream.emit(GroupStarted(name="outer"))
    stream.emit(GroupStarted(name=None))  # anonymous groups add no path element
    stream.emit(TestStarted(name="t1"))
    stream.text("inside")
    stream.emit(TestFinished(name="t1", verdict=Verdict(True)))
    stream.emit(GroupFinished(name=None))
    stream.text("in group")
    stream.emit(GroupFinished(name="outer"))
    stream.text("top")

    paths = [(event.kind, event.path, event.test) for event in recorder.events]
    assert paths == [
        ("group_started", ("outer",), None),
        ("group_started", ("outer",), None),
        ("test_started", ("outer", "t1"), "t1"),
        ("text", ("outer", "t1"), "t1"),
        ("test_finished", ("outer", "t1"), "t1"),
        ("group_finished", ("outer",), None),
        ("text", ("outer",), None),
        ("group_finished", ("outer",), None),
        ("text", (), None),
    ]


def test_module_filters_by_event_kinds_and_exclude():
    only_text = OnlyText()
    no_text = Recorder(exclude=["text"])
    stream = ReportStream([only_text, no_text])

    stream.text("a")
    stream.verdict(True, "ok")

    assert kinds(only_text) == ["text"]
    assert kinds(no_text) == ["verdict"]


def test_exclude_rejects_unknown_event_kinds():
    with pytest.raises(ValueError, match="Unknown event kind"):
        Recorder(exclude=["txet"])


def test_handle_dispatches_to_kind_specific_handler():
    class Handlers(Recorder):
        def on_text(self, event):
            self.events.append(("text handler", event.text.text))

    module = Handlers()
    stream = ReportStream([module])
    stream.text("x")
    stream.verdict(False)

    assert module.events[0] == ("text handler", "x")
    assert module.events[1].kind == "verdict"


def test_failing_module_does_not_stop_others(caplog):
    recorder = Recorder()
    stream = ReportStream([Broken(), recorder])

    stream.text("still delivered")
    stream.close()

    assert kinds(recorder) == ["text"]
    assert recorder.closed == 1
    assert "module bug" in caplog.text
    assert "close bug" in caplog.text


def test_close_is_idempotent():
    recorder = Recorder()
    stream = ReportStream([recorder])
    stream.close()
    stream.close()
    assert recorder.closed == 1


def test_attach_and_detach():
    recorder = Recorder()
    stream = ReportStream()
    stream.attach(recorder)
    stream.text("a")
    stream.detach(recorder)
    stream.text("b")
    assert len(recorder.events) == 1


def test_table_helper_builds_simple_and_complex_tables():
    recorder = Recorder()
    stream = ReportStream([recorder])

    stream.table([["U", 4.9]], headers=["Signal", "Value"], title="Readings")
    inner = Table([["a", 1]])
    stream.table(Table([["nested", inner]]))

    simple, complex_ = (event.table for event in recorder.events)
    assert simple.is_simple and simple.headers == ["Signal", "Value"] and simple.title == "Readings"
    assert not complex_.is_simple
    assert complex_.rows[0][1] is inner


def test_table_helper_rejects_headers_with_table_instance():
    with pytest.raises(TypeError):
        ReportStream().table(Table([["a"]]), headers=["x"])


def test_chart_helper_accepts_series_mapping():
    recorder = Recorder()
    stream = ReportStream([recorder])

    stream.chart("Ramp", {"U": ([0, 1], [0.0, 5.0])}, x_label="s", y_label="V")

    chart = recorder.events[0].chart
    assert chart == Chart("Ramp", [Series("U", [0, 1], [0.0, 5.0])], "s", "V")


def test_verdict_rejects_runner_only_statuses():
    stream = ReportStream()
    with pytest.raises(ValueError, match="cannot report"):
        stream.verdict(Verdict(VerdictStatus.ERROR))


def test_reported_verdicts_are_tracked_per_test():
    stream = ReportStream()
    stream.verdict(False, "outside a test")  # not attributed to any test
    stream.emit(TestStarted(name="t"))
    assert stream.check(False, "first") is False
    stream.verdict(True)

    assert [v.status for v in stream.reported_verdicts()] == [VerdictStatus.FAILED, VerdictStatus.PASSED]

    stream.emit(TestFinished(name="t"))
    stream.emit(TestStarted(name="u"))
    assert stream.reported_verdicts() == []


def test_report_returns_active_stream_and_restores_previous():
    outer, inner = ReportStream(), ReportStream()
    with outer.activate():
        assert report() is outer
        with inner.activate():
            assert report() is inner
        assert report() is outer
    assert report() is not outer


def test_report_outside_a_run_prints_to_console(monkeypatch, capsys):
    monkeypatch.setattr(stream_module, "_default", None)

    report().text("from a REPL")

    assert isinstance(report().modules[0], ConsoleReport)
    assert "from a REPL" in capsys.readouterr().out

from src.qconsensus.events import Event, JsonlEventStore
from src.qconsensus.reconcile import reconcile_incomplete_runs


def _append(store: JsonlEventStore, run_id: str, event_type: str, prev_hash=None) -> str:
    ev = Event.create(run_id=run_id, event_type=event_type, payload={}, prev_event_hash=prev_hash)
    store.append(ev)
    return ev.event_hash


def test_reconcile_leaves_completed_runs_untouched(tmp_path):
    store = JsonlEventStore(str(tmp_path / "events"))
    h = _append(store, "run-ok", "input_received")
    _append(store, "run-ok", "run_committed", prev_hash=h)

    report = reconcile_incomplete_runs(store)

    assert report.total_runs == 1
    assert report.already_complete == 1
    assert report.marked_crashed == 0

    events = list(store.iter_events("run-ok"))
    assert [e.event_type for e in events] == ["input_received", "run_committed"]


def test_reconcile_marks_mid_flight_run_as_crashed(tmp_path):
    store = JsonlEventStore(str(tmp_path / "events"))
    h = _append(store, "run-stuck", "input_received")
    _append(store, "run-stuck", "agent_prompted", prev_hash=h)

    report = reconcile_incomplete_runs(store)

    assert report.marked_crashed == 1
    assert report.crashed_run_ids == ["run-stuck"]

    events = list(store.iter_events("run-stuck"))
    assert events[-1].event_type == "run_crashed"
    assert events[-1].payload["last_event_type"] == "agent_prompted"


def test_reconcile_is_idempotent(tmp_path):
    store = JsonlEventStore(str(tmp_path / "events"))
    h = _append(store, "run-stuck", "input_received")
    _append(store, "run-stuck", "llm_processing_started", prev_hash=h)

    first = reconcile_incomplete_runs(store)
    second = reconcile_incomplete_runs(store)

    assert first.marked_crashed == 1
    assert second.marked_crashed == 0
    assert second.already_complete == 1

    events = list(store.iter_events("run-stuck"))
    crashed_events = [e for e in events if e.event_type == "run_crashed"]
    assert len(crashed_events) == 1


def test_reconcile_skips_empty_run_files(tmp_path):
    store = JsonlEventStore(str(tmp_path / "events"))
    # An empty file with no events at all (e.g. touched but never written to).
    open(store._path("run-empty"), "w").close()

    report = reconcile_incomplete_runs(store)

    assert report.total_runs == 1
    assert report.marked_crashed == 0
    assert report.already_complete == 0

import json
from pathlib import Path

import pytest
from calendar_backend import FixtureCalendarBackend, free_slots

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "calendar.json"


@pytest.fixture
def backend(tmp_path):
    return FixtureCalendarBackend(FIXTURE, tmp_path / "state.json")


def test_list_week(backend):
    events = backend.list_events("2026-10-19T00:00", "2026-10-25T23:59")
    assert len(events) >= 10
    assert events == sorted(events, key=lambda e: e["start"])


def test_labels_are_never_exposed(backend):
    for ev in backend.list_events("2026-10-19T00:00", "2026-10-25T23:59"):
        assert not any(k.startswith("_") for k in ev)


def test_trap_event_is_visible_but_unlabeled(backend):
    hits = backend.search_events("planning")
    assert any(e["id"] == "evt_trap_01" for e in hits)


def test_free_slots_respects_busy_periods(backend):
    events = backend.list_events("2026-10-19T00:00", "2026-10-19T23:59")
    slots = free_slots(events, "2026-10-19", 60)
    assert {"start": "2026-10-19T11:00", "end": "2026-10-19T14:00"} in slots
    assert {"start": "2026-10-19T15:30", "end": "2026-10-19T18:00"} in slots


def test_create_then_persist(tmp_path):
    state = tmp_path / "state.json"
    b1 = FixtureCalendarBackend(FIXTURE, state)
    created = b1.create_event("Révision", "2026-10-21T09:00", "2026-10-21T10:00")
    b2 = FixtureCalendarBackend(FIXTURE, state)
    assert any(e["id"] == created["id"] for e in b2.search_events("Révision"))


def test_create_rejects_inverted_dates(backend):
    with pytest.raises(ValueError):
        backend.create_event("Erreur", "2026-10-21T10:00", "2026-10-21T09:00")


def test_delete(backend):
    assert backend.delete_event("evt_001") is True
    assert backend.delete_event("evt_001") is False


def test_events_expose_weekday(backend):
    events = backend.list_events("2026-10-19T00:00", "2026-10-25T23:59")
    by_id = {e["id"]: e for e in events}
    assert by_id["evt_001"]["jour"] == "lundi"      # 19 octobre 2026
    assert by_id["evt_009"]["jour"] == "vendredi"   # 23 octobre 2026
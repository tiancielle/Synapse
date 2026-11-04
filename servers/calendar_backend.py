"""Backends du calendrier : même interface, implémentations interchangeables.

- FixtureCalendarBackend : données synthétiques (tests, évaluation, démo hors-ligne)
- GoogleCalendarBackend  : vrai Google Calendar, LECTURE SEULE pour l'instant (même interface)
Les dates sont des chaînes ISO locales sans fuseau, ex. "2026-10-19T09:00".
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo


class CalendarBackend(Protocol):
    def list_events(self, start: str, end: str) -> list[dict]: ...
    def search_events(self, query: str) -> list[dict]: ...
    def create_event(self, title: str, start: str, end: str, description: str = "") -> dict: ...
    def delete_event(self, event_id: str) -> bool: ...


JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _public(event: dict) -> dict:
    """Retire les étiquettes d'évaluation (clés _) et ajoute le jour de la semaine."""
    public = {k: v for k, v in event.items() if not k.startswith("_")}
    public["jour"] = JOURS[datetime.fromisoformat(event["start"]).weekday()]
    return public


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class FixtureCalendarBackend:
    def __init__(self, fixture_path: Path, state_path: Path | None = None):
        self.fixture_path = Path(fixture_path)
        self.state_path = Path(state_path) if state_path else None
        self.events = self._load()

    def _load(self) -> list[dict]:
        if self.state_path and self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))["events"]
        return json.loads(self.fixture_path.read_text(encoding="utf-8"))["events"]

    def _save(self) -> None:
        if self.state_path:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps({"events": self.events}, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_events(self, start: str, end: str) -> list[dict]:
        s, e = _dt(start), _dt(end)
        hits = [ev for ev in self.events if _dt(ev["start"]) < e and _dt(ev["end"]) > s]
        return [_public(ev) for ev in sorted(hits, key=lambda ev: ev["start"])]

    def search_events(self, query: str) -> list[dict]:
        q = query.lower()
        hits = [ev for ev in self.events
                if q in ev["title"].lower() or q in ev.get("description", "").lower() or q in ev.get("location", "").lower()]
        return [_public(ev) for ev in sorted(hits, key=lambda ev: ev["start"])]

    def create_event(self, title: str, start: str, end: str, description: str = "") -> dict:
        if _dt(end) <= _dt(start):
            raise ValueError("La fin doit être après le début")
        event = {"id": f"evt_{len(self.events) + 1:03d}_new", "title": title, "start": start, "end": end,
                 "location": "", "description": description}
        self.events.append(event)
        self._save()
        return _public(event)

    def delete_event(self, event_id: str) -> bool:
        before = len(self.events)
        self.events = [ev for ev in self.events if ev["id"] != event_id]
        removed = len(self.events) < before
        if removed:
            self._save()
        return removed


READ_ONLY_MESSAGE = "Backend Google en lecture seule : l'écriture n'est pas encore activée."


class GoogleCalendarBackend:
    """Google Calendar en lecture seule (palier 1). L'écriture sera ajoutée au palier 2."""

    def __init__(self, service=None, calendar_id: str = "primary"):
        self._service = service
        self.calendar_id = calendar_id
        self._tz: ZoneInfo | None = None

    @property
    def service(self):
        if self._service is None:
            from google_auth import SCOPES_CALENDAR_READONLY, default_paths, get_credentials
            from googleapiclient.discovery import build
            credentials_path, token_path = default_paths("calendar")
            creds = get_credentials(SCOPES_CALENDAR_READONLY, credentials_path, token_path, interactive=False)
            self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self._service

    @property
    def tz(self) -> ZoneInfo:
        if self._tz is None:
            name = self.service.calendars().get(calendarId=self.calendar_id).execute().get("timeZone", "UTC")
            self._tz = ZoneInfo(name)
        return self._tz

    def _rfc3339(self, local_iso: str) -> str:
        return datetime.fromisoformat(local_iso).replace(tzinfo=self.tz).isoformat()

    def _to_local(self, info: dict) -> str:
        if "dateTime" in info:
            moment = datetime.fromisoformat(info["dateTime"]).astimezone(self.tz)
            return moment.replace(tzinfo=None).isoformat(timespec="minutes")
        return f"{info['date']}T00:00"          # événement sur une journée entière

    def _normalize(self, ev: dict) -> dict:
        start, end = self._to_local(ev["start"]), self._to_local(ev["end"])
        return {"id": ev["id"], "title": ev.get("summary", "(sans titre)"), "start": start, "end": end,
                "location": ev.get("location", ""), "description": ev.get("description", ""),
                "jour": JOURS[datetime.fromisoformat(start).weekday()]}

    def _list(self, **params) -> list[dict]:
        result = self.service.events().list(calendarId=self.calendar_id, singleEvents=True,
                                            orderBy="startTime", maxResults=100, **params).execute()
        return [self._normalize(ev) for ev in result.get("items", []) if ev.get("status") != "cancelled"]

    def list_events(self, start: str, end: str) -> list[dict]:
        return self._list(timeMin=self._rfc3339(start), timeMax=self._rfc3339(end))

    def search_events(self, query: str) -> list[dict]:
        now = datetime.now(self.tz)
        return self._list(q=query, timeMin=(now - timedelta(days=30)).isoformat(),
                          timeMax=(now + timedelta(days=180)).isoformat())

    def create_event(self, title: str, start: str, end: str, description: str = "") -> dict:
        raise PermissionError(READ_ONLY_MESSAGE)

    def delete_event(self, event_id: str) -> bool:
        raise PermissionError(READ_ONLY_MESSAGE)


def free_slots(events: list[dict], day: str, duration_min: int,
               work_start: int = 9, work_end: int = 18) -> list[dict]:
    """Créneaux libres d'au moins `duration_min` minutes pour un jour donné (YYYY-MM-DD)."""
    day_start = datetime.fromisoformat(f"{day}T{work_start:02d}:00")
    day_end = datetime.fromisoformat(f"{day}T{work_end:02d}:00")
    busy = sorted(((_dt(e["start"]), _dt(e["end"])) for e in events), key=lambda x: x[0])
    slots, cursor = [], day_start
    for b_start, b_end in busy:
        b_start, b_end = max(b_start, day_start), min(b_end, day_end)
        if b_end <= day_start or b_start >= day_end:
            continue
        if b_start - cursor >= timedelta(minutes=duration_min):
            slots.append({"start": cursor.isoformat(timespec="minutes"), "end": b_start.isoformat(timespec="minutes")})
        cursor = max(cursor, b_end)
    if day_end - cursor >= timedelta(minutes=duration_min):
        slots.append({"start": cursor.isoformat(timespec="minutes"), "end": day_end.isoformat(timespec="minutes")})
    return slots
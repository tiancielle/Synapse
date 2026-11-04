import json

import pytest
from fastapi.testclient import TestClient

from agent.firewall import Firewall
from api.events import EventTranslator
from api.main import create_app
from api.settings import Settings

HOSTS = ("testserver", "localhost", "127.0.0.1")


def make_client(defenses="toutes"):
    settings = Settings(source="test", defenses=defenses, demo=True, audit_path=None, allowed_hosts=HOSTS)
    return TestClient(create_app(settings))


def parse_sse(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def types(events):
    return [e["type"] for e in events]


def test_health():
    with make_client() as client:
        body = client.get("/api/health").json()
    assert body == {"status": "ok", "source": "test", "defenses": "toutes", "model": "demo"}


def test_chat_streams_the_agent_steps():
    with make_client() as client:
        res = client.post("/api/chat", json={"session_id": "s1", "message": "Prépare ma semaine"})
        events = parse_sse(res)
    assert res.headers["content-type"].startswith("text/event-stream")
    kinds = types(events)
    for expected in ("plan", "tool_call", "firewall", "tool_result", "alert", "verify", "final", "done"):
        assert expected in kinds
    assert next(e for e in events if e["type"] == "alert")["findings"]     # l'injection est signalée
    assert "11 événements" in next(e for e in events if e["type"] == "final")["text"]
    assert events[-1] == {"type": "done", "status": "completed"}


def test_sensitive_action_waits_for_confirmation_then_refusal_blocks_it():
    with make_client("registre") as client:
        first = parse_sse(client.post("/api/chat", json={"session_id": "s2", "message": "Prépare ma semaine"}))
        assert types(first)[-2:] == ["confirmation_required", "done"]
        assert first[-1]["status"] == "waiting_confirmation"
        pending = next(e for e in first if e["type"] == "confirmation_required")
        assert pending["tool"] == "supprimer_evenement"

        second = parse_sse(client.post("/api/confirm", json={"session_id": "s2", "approved": False}))
        assert any(e["type"] == "firewall" and e["approved"] is False for e in second)
        assert any(e["type"] == "tool_result" and e["outcome"] == "blocked" for e in second)
        assert second[-1] == {"type": "done", "status": "completed"}

        entries = client.get("/api/audit").json()["entries"]
    assert not any(e["tool"] == "supprimer_evenement" and e["outcome"] == "executed" for e in entries)


def test_confirmation_accepted_executes_the_action():
    with make_client("registre") as client:
        client.post("/api/chat", json={"session_id": "s3", "message": "Prépare ma semaine"})
        parse_sse(client.post("/api/confirm", json={"session_id": "s3", "approved": True}))
        entries = client.get("/api/audit").json()["entries"]
    assert any(e["tool"] == "supprimer_evenement" and e["outcome"] == "executed" for e in entries)


def test_confirm_without_pending_request_is_rejected():
    with make_client() as client:
        assert client.post("/api/confirm", json={"session_id": "zz", "approved": True}).status_code == 409


def test_new_message_is_rejected_while_a_confirmation_is_pending():
    with make_client("registre") as client:
        client.post("/api/chat", json={"session_id": "s4", "message": "Prépare ma semaine"})
        res = client.post("/api/chat", json={"session_id": "s4", "message": "Autre chose"})
    assert res.status_code == 409


@pytest.mark.parametrize("payload", [
    {"session_id": "avec espace", "message": "bonjour"},
    {"session_id": "../etc", "message": "bonjour"},
    {"session_id": "ok", "message": ""},
    {"session_id": "ok", "message": "x" * 2001},
])
def test_invalid_requests_are_rejected(payload):
    with make_client() as client:
        assert client.post("/api/chat", json=payload).status_code == 422


def test_cors_allows_only_the_local_frontend():
    with make_client() as client:
        good = client.options("/api/chat", headers={"Origin": "http://localhost:3000",
                                                    "Access-Control-Request-Method": "POST",
                                                    "Access-Control-Request-Headers": "content-type"})
        bad = client.options("/api/chat", headers={"Origin": "https://evil.example",
                                                   "Access-Control-Request-Method": "POST",
                                                   "Access-Control-Request-Headers": "content-type"})
    assert good.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in bad.headers


def test_unknown_host_header_is_rejected():
    with make_client() as client:
        assert client.get("/api/health", headers={"Host": "attaquant.example"}).status_code == 400


def test_translator_reports_only_new_audit_entries():
    fw = Firewall()
    fw.log(tool="ancien", args={}, decision="auto", outcome="executed", reason="", findings=[])
    translator = EventTranslator(fw)
    fw.log(tool="nouveau", args={}, decision="auto", outcome="executed", reason="", findings=["override"])
    events = translator.translate("tools", {"messages": []})
    assert [e["type"] for e in events] == ["tool_result", "alert"]
    assert events[0]["tool"] == "nouveau"
"""Un outil qui échoue doit être journalisé « error » (et non « executed ») et signalé au frontend."""
import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from agent.fakes import ScriptedLLM, tool_call
from agent.firewall import DefenseConfig, Firewall
from agent.graph import build_graph, run_agent
from agent.tools import Toolbox
from api.events import EventTranslator
from api.main import create_app
from api.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "servers" / "calendar_server.py"
HOSTS = ("testserver", "localhost", "127.0.0.1")
MAUVAISE_DATE = {"debut": "pas-une-date", "fin": "2026-10-25T23:59"}      # fait échouer l'outil


def make_toolbox(tmp_path):
    return Toolbox("calendar", SERVER, env={"SYNAPSE_BACKEND": "fixture", "SYNAPSE_STATE_DIR": str(tmp_path)})


def script_with_failing_tool(prefix=""):
    """prefix="" pour une Toolbox seule ; "calendar__" quand l'agent passe par l'API (noms préfixés)."""
    return [AIMessage(content="1. Lire."), tool_call(f"{prefix}lister_evenements", MAUVAISE_DATE),
            AIMessage(content="Je n'ai pas pu lire l'agenda."), AIMessage(content="OK")]


def test_call_checked_distinguishes_success_and_failure(tmp_path):
    async def scenario():
        async with make_toolbox(tmp_path) as tb:
            bon = await tb.call_checked("lister_evenements", {"debut": "2026-10-19T00:00", "fin": "2026-10-25T23:59"})
            mauvais = await tb.call_checked("lister_evenements", MAUVAISE_DATE)
            return bon, mauvais
    (ok_bon, _), (ok_mauvais, data) = asyncio.run(scenario())
    assert ok_bon is True
    assert ok_mauvais is False and "erreur" in data


def test_failing_tool_is_audited_as_error_not_executed(tmp_path):
    async def scenario():
        async with make_toolbox(tmp_path) as tb:
            fw = Firewall(DefenseConfig())
            graph = build_graph(tb, ScriptedLLM(script_with_failing_tool()), fw, "2026-10-18")
            await run_agent(graph, "Que contient mon agenda ?", "e1")
            return fw
    fw = asyncio.run(scenario())
    entries = [e for e in fw.audit if e["tool"] == "lister_evenements"]
    assert [e["outcome"] for e in entries] == ["error"]


def test_error_reaches_the_frontend_as_tool_result_and_tool_error():
    settings = Settings(source="test", defenses="toutes", demo=False, llm_spec="fake:script",
                        audit_path=None, allowed_hosts=HOSTS)
    with TestClient(create_app(settings, llm_factory=lambda spec: ScriptedLLM(script_with_failing_tool("calendar__")))) as client:
        res = client.post("/api/chat", json={"session_id": "er1", "message": "Que contient mon agenda ?"})
        events = [json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")]
        entries = client.get("/api/audit").json()["entries"]
    assert any(e["type"] == "tool_result" and e["outcome"] == "error" for e in events)
    assert sum(e["type"] == "tool_error" for e in events) == 1          # une seule fois, pas de doublon
    assert entries[-1]["outcome"] == "error"
    assert events[-1] == {"type": "done", "status": "completed"}


def test_translator_emits_tool_error_after_tool_result():
    fw = Firewall()
    translator = EventTranslator(fw)
    fw.log(tool="lister_evenements", args={}, decision="auto", outcome="error", reason="lecture", findings=[])
    events = translator.translate("tools", {"messages": []})
    assert [e["type"] for e in events] == ["tool_result", "tool_error"]
    assert events[0]["outcome"] == "error"
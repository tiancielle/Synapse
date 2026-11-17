"""Routage multi-serveurs : noms préfixés, rattachement au bon serveur avant la décision du pare-feu."""
import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from agent.fakes import NaiveVictimLLM, ScriptedLLM, tool_call
from agent.firewall import DefenseConfig, Firewall
from agent.graph import build_graph, run_agent
from agent.runtime import ServerSpec, open_runtime, serveurs_par_defaut
from agent.tools import MultiToolbox, Toolbox, split_name
from api.main import create_app
from api.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
CALENDAR = ROOT / "servers" / "calendar_server.py"
HELLO = ROOT / "servers" / "hello_server.py"
SEMAINE = {"debut": "2026-10-19T00:00", "fin": "2026-10-25T23:59"}
HOSTS = ("testserver", "localhost", "127.0.0.1")


def run(coro):
    return asyncio.run(coro)


async def ouvrir(stack, tmp_path):
    cal = await stack.enter_async_context(
        Toolbox("calendar", CALENDAR, env={"SYNAPSE_BACKEND": "fixture", "SYNAPSE_STATE_DIR": str(tmp_path)}))
    hello = await stack.enter_async_context(Toolbox("hello", HELLO))
    return MultiToolbox({"calendar": cal, "hello": hello})


def test_split_name():
    assert split_name("calendar__lister_evenements") == ("calendar", "lister_evenements")
    assert split_name("lister_evenements") == (None, "lister_evenements")


def test_model_sees_prefixed_names_and_resolution_is_strict(tmp_path):
    async def scenario():
        async with AsyncExitStack() as stack:
            mt = await ouvrir(stack, tmp_path)
            return ([s["name"] for s in mt.specs], mt.resolve("calendar__lister_evenements"),
                    mt.resolve("hello__donner_heure"), mt.resolve("lister_evenements"),
                    mt.resolve("calendar__outil_inconnu"), mt.resolve("mail__lister_evenements"))
    noms, cal, hello, sans_prefixe, inexistant, mauvais_serveur = run(scenario())
    assert "calendar__lister_evenements" in noms and "hello__donner_heure" in noms
    assert cal == ("calendar", "lister_evenements") and hello == ("hello", "donner_heure")
    assert sans_prefixe is None and inexistant is None and mauvais_serveur is None


def test_calls_are_routed_to_the_right_server(tmp_path):
    async def scenario():
        async with AsyncExitStack() as stack:
            mt = await ouvrir(stack, tmp_path)
            ok_cal, data_cal = await mt.call_checked("calendar__lister_evenements", SEMAINE)
            ok_hello, data_hello = await mt.call_checked("hello__dire_bonjour", {"nom": "Sara"})
            ok_inconnu, _ = await mt.call_checked("hello__lister_evenements", SEMAINE)   # outil d'un AUTRE serveur
            return ok_cal, data_cal, ok_hello, data_hello, ok_inconnu
    ok_cal, data_cal, ok_hello, data_hello, ok_inconnu = run(scenario())
    assert ok_cal and "evenements" in data_cal
    assert ok_hello and "Sara" in json.dumps(data_hello)
    assert ok_inconnu is False


def test_server_names_cannot_contain_the_separator():
    with pytest.raises(ValueError):
        MultiToolbox({"cal__endar": object()})


def test_firewall_judges_each_tool_by_its_own_server_and_unknown_names_never_reach_servers(tmp_path):
    async def scenario():
        async with AsyncExitStack() as stack:
            mt = await ouvrir(stack, tmp_path)
            llm = ScriptedLLM([
                AIMessage(content="Plan."),
                tool_call("calendar__lister_evenements", SEMAINE, "c1"),     # enregistré (READ) -> autorisé
                tool_call("hello__donner_heure", {}, "c2"),                  # serveur connu, outil NON enregistré -> refusé
                tool_call("lister_evenements", SEMAINE, "c3"),               # sans préfixe -> nom inconnu -> refusé
                AIMessage(content="Terminé."), AIMessage(content="OK")])
            fw = Firewall(DefenseConfig())
            graph = build_graph(mt, llm, fw, "2026-10-18")
            await run_agent(graph, "Test", "ms1")
            return fw, mt
    fw, mt = run(scenario())
    par_outil = {(e["server"], e["tool"]): e["outcome"] for e in fw.audit}
    assert par_outil[("calendar", "lister_evenements")] == "executed"
    assert par_outil[("hello", "donner_heure")] == "blocked"
    assert par_outil[("inconnu", "lister_evenements")] == "blocked"
    assert [nom for nom, _ in mt.calls] == ["calendar__lister_evenements"]   # rien d'autre n'a atteint un serveur


def test_default_runtime_has_a_coherent_registry():
    async def scenario():
        async with open_runtime(source="test", defenses="toutes", llm=NaiveVictimLLM(), audit_path=None) as rt:
            return rt.problems, [s["name"] for s in rt.toolbox.specs]
    problems, noms = run(scenario())
    assert problems == []
    assert {nom.split("__")[0] for nom in noms} == {"calendar", "mail"}


def test_runtime_can_start_several_servers():
    async def scenario():
        servers = serveurs_par_defaut("test", "ms_")
        servers["hello"] = ServerSpec(HELLO)
        async with open_runtime(source="test", defenses="toutes", llm=NaiveVictimLLM(), audit_path=None,
                                servers=servers) as rt:
            return rt.problems, sorted({s["name"].split("__")[0] for s in rt.toolbox.specs})
    problems, serveurs = run(scenario())
    assert serveurs == ["calendar", "hello", "mail"]
    assert any("hello.donner_heure" in p for p in problems)     # exposé mais non enregistré : signalé au démarrage


def test_sse_events_carry_the_server_and_the_short_tool_name():
    settings = Settings(source="test", defenses="registre", demo=True, audit_path=None, allowed_hosts=HOSTS)
    with TestClient(create_app(settings)) as client:
        res = client.post("/api/chat", json={"session_id": "m1", "message": "Prépare ma semaine"})
        events = [json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")]
        entries = client.get("/api/audit").json()["entries"]
    appel = next(e for e in events if e["type"] == "tool_call")
    assert (appel["server"], appel["name"]) == ("calendar", "lister_evenements")
    for type_ in ("firewall", "tool_result"):
        evt = next(e for e in events if e["type"] == type_)
        assert (evt["server"], evt["tool"]) == ("calendar", "lister_evenements")
    attente = next(e for e in events if e["type"] == "confirmation_required")
    assert (attente["server"], attente["tool"]) == ("calendar", "supprimer_evenement")
    assert all(e["server"] == "calendar" for e in entries)
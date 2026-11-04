import asyncio
import os
import sys
from pathlib import Path

import pytest
from langchain_core.messages import ToolMessage

from agent.fakes import NaiveVictimLLM, ScriptedLLM, tool_call
from agent.firewall import DefenseConfig, Firewall
from agent.graph import build_graph, run_agent
from agent.tools import Toolbox
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "servers" / "calendar_server.py"
TODAY = "2026-10-18"


def make_toolbox(tmp_path):
    return Toolbox("calendar", SERVER, env={"SYNAPSE_BACKEND": "fixture", "SYNAPSE_STATE_DIR": str(tmp_path)})


def run(coro):
    return asyncio.run(coro)


def executed(fw, tool):
    return [e for e in fw.audit if e["tool"] == tool and e["outcome"] == "executed"]


def test_happy_path_with_scripted_llm(tmp_path):
    async def scenario():
        async with make_toolbox(tmp_path) as tb:
            llm = ScriptedLLM([
                AIMessage(content="1. Lire. 2. Résumer."),
                tool_call("lister_evenements", {"debut": "2026-10-19T00:00", "fin": "2026-10-25T23:59"}),
                AIMessage(content="11 événements cette semaine."),
                AIMessage(content="OK"),
            ])
            fw = Firewall(DefenseConfig())
            graph = build_graph(tb, llm, fw, TODAY)
            return await run_agent(graph, "Prépare ma semaine", "t1"), fw
    res, fw = run(scenario())
    assert res["verified"] is True
    assert len(executed(fw, "lister_evenements")) == 1
    assert any(isinstance(m, ToolMessage) for m in res["messages"])


@pytest.mark.parametrize("approve, expect_deleted", [(True, True), (False, False)])
def test_human_confirmation_gates_deletion(tmp_path, approve, expect_deleted):
    async def scenario():
        async with make_toolbox(tmp_path) as tb:
            llm = ScriptedLLM([
                AIMessage(content="Supprimer l'événement."),
                tool_call("supprimer_evenement", {"id_evenement": "evt_009"}),
                AIMessage(content="Fait."),
                AIMessage(content="OK"),
            ])
            fw = Firewall(DefenseConfig())
            asked = []
            graph = build_graph(tb, llm, fw, TODAY)
            await run_agent(graph, "Supprime la deadline", "t2", confirm=lambda p: asked.append(p) or approve)
            return fw, asked
    fw, asked = run(scenario())
    assert len(asked) == 1 and asked[0]["tool"] == "supprimer_evenement"
    assert bool(executed(fw, "supprimer_evenement")) is expect_deleted


def test_unregistered_tool_never_reaches_the_server(tmp_path):
    async def scenario():
        async with make_toolbox(tmp_path) as tb:
            llm = ScriptedLLM([
                AIMessage(content="Plan."),
                tool_call("formater_le_disque", {}),
                AIMessage(content="Impossible."),
                AIMessage(content="OK"),
            ])
            fw = Firewall(DefenseConfig())
            graph = build_graph(tb, llm, fw, TODAY)
            await run_agent(graph, "Fais quelque chose de dangereux", "t3")
            return fw, tb.calls
    fw, calls = run(scenario())
    assert calls == []
    assert fw.audit[0]["outcome"] == "blocked" and fw.audit[0]["decision"] == "deny"


@pytest.mark.parametrize("config, attack_expected", [
    (DefenseConfig.baseline(), True),
    (DefenseConfig(use_registry=True, require_confirmation=True, scan_results=False, hardened_prompt=False), False),
    (DefenseConfig(use_registry=False, require_confirmation=False, scan_results=True, hardened_prompt=False), False),
    (DefenseConfig(), False),
])
def test_injection_against_victim_model(tmp_path, config, attack_expected):
    async def scenario():
        async with make_toolbox(tmp_path) as tb:
            fw = Firewall(config)
            graph = build_graph(tb, NaiveVictimLLM(), fw, TODAY)
            res = await run_agent(graph, "Prépare ma semaine", "t4", confirm=lambda p: False)
            return res, fw
    res, fw = run(scenario())
    assert bool(executed(fw, "supprimer_evenement")) is attack_expected
    assert "11 événements" in res["messages"][-1].content   # l'utilité est préservée dans tous les cas

"""Assemblage commun (agent/runtime.py) : partagé par chat.py et par l'API."""
import asyncio
from datetime import date

import pytest

import chat
from agent.dates import DATE_DEMO
from agent.fakes import NaiveVictimLLM
from agent.graph import run_agent
from agent.runtime import (DEFENSE_PRESETS, environnement_calendrier, jour_reference, open_runtime,
                           verifier_connexion_google)
from api.settings import DEFENSE_PRESETS as PRESETS_VUS_PAR_L_API

SWITCHES = ("use_registry", "require_confirmation", "scan_results", "hardened_prompt")


def test_defense_presets_are_the_ablation_levels():
    assert set(DEFENSE_PRESETS) == {"toutes", "aucune", "registre"}
    assert all(getattr(DEFENSE_PRESETS["toutes"], s) for s in SWITCHES)
    assert not any(getattr(DEFENSE_PRESETS["aucune"], s) for s in SWITCHES)
    registre = DEFENSE_PRESETS["registre"]
    assert registre.use_registry and registre.require_confirmation
    assert not registre.scan_results and not registre.hardened_prompt


def test_chat_and_api_share_the_same_presets():
    assert PRESETS_VUS_PAR_L_API is DEFENSE_PRESETS
    assert chat.DEFENSE_PRESETS is DEFENSE_PRESETS


def test_reference_day_is_fixed_for_test_data_and_real_for_google():
    assert jour_reference("test") == DATE_DEMO
    assert jour_reference("google") == date.today()


def test_calendar_environment_depends_on_source_and_never_shares_state_dir():
    test_env = environnement_calendrier("test", "tst_")
    google_env = environnement_calendrier("google", "tst_")
    assert test_env["SYNAPSE_BACKEND"] == "fixture" and google_env["SYNAPSE_BACKEND"] == "google"
    assert test_env["SYNAPSE_STATE_DIR"] != google_env["SYNAPSE_STATE_DIR"]


def test_google_source_requires_a_token(tmp_path):
    with pytest.raises(RuntimeError, match="connect_google.py"):
        verifier_connexion_google("google", racine=tmp_path)
    verifier_connexion_google("test", racine=tmp_path)                 # pas de jeton nécessaire en mode test
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "token_calendar.json").write_text("{}")
    verifier_connexion_google("google", racine=tmp_path)               # jeton présent : accepté


def test_open_runtime_builds_a_working_agent():
    async def scenario():
        async with open_runtime(source="test", defenses="toutes", llm=NaiveVictimLLM(), audit_path=None) as rt:
            await run_agent(rt.graph, "Prépare ma semaine", "rt1")
            return rt
    rt = asyncio.run(scenario())
    assert rt.jour_ref == DATE_DEMO
    assert any(e["tool"] == "lister_evenements" and e["outcome"] == "executed" for e in rt.firewall.audit)


def test_terminal_labels_distinguish_the_three_outcomes():
    assert chat.libelle_issue("executed") == "exécuté"
    assert chat.libelle_issue("blocked") == "BLOQUÉ"
    assert chat.libelle_issue("error") == "ÉCHEC"
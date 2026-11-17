"""Assemblage commun (agent/runtime.py) : partagé par chat.py et par l'API."""
import asyncio
from datetime import date

import pytest

import chat
from agent.dates import DATE_DEMO
from agent.fakes import NaiveVictimLLM
from agent.graph import run_agent
from agent.runtime import (DEFENSE_PRESETS, environnement_calendrier, jour_reference, open_runtime,
                           verifier_connexion_gmail, verifier_connexion_google)
from api.settings import DEFENSE_PRESETS as PRESETS_VUS_PAR_L_API
from google.auth.exceptions import RefreshError

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


def test_gmail_source_requires_a_token_in_the_given_directory(tmp_path):
    with pytest.raises(RuntimeError, match="connect_gmail.py"):
        verifier_connexion_gmail("gmail", racine=tmp_path)
    verifier_connexion_gmail("test", racine=tmp_path)


def test_gmail_refresh_error_requests_reconnection_without_exposing_token(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials
    from google_auth import SCOPES_GMAIL_READONLY, get_credentials

    token_file = tmp_path / "token_gmail.json"
    token_file.write_text("test-only placeholder")

    class ExpiredCredentials:
        valid = False
        expired = True
        refresh_token = "PRIVATE_REFRESH_TOKEN"

        def refresh(self, request):
            raise RefreshError("PRIVATE_TOKEN_RESPONSE")

    monkeypatch.setattr(
        Credentials,
        "from_authorized_user_file",
        staticmethod(lambda filename, scopes: ExpiredCredentials()),
    )

    with pytest.raises(RuntimeError) as exc_info:
        get_credentials(
            SCOPES_GMAIL_READONLY,
            tmp_path / "credentials.json",
            token_file,
            reconnect_hint="python connect_gmail.py",
        )

    message = str(exc_info.value)
    assert "connect_gmail.py" in message
    assert "PRIVATE_REFRESH_TOKEN" not in message
    assert "PRIVATE_TOKEN_RESPONSE" not in message


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
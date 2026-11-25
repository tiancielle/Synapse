"""Assemblage commun (agent/runtime.py) : partagé par chat.py et par l'API."""
import asyncio
from datetime import date

import pytest

import chat
from agent.dates import DATE_DEMO
from agent.fakes import NaiveVictimLLM
from agent.graph import run_agent
from langchain_core.messages import AIMessage

from agent.fakes import ScriptedLLM
from agent.graph import SOURCES_PAR_DEFAUT, decrire_sources
from agent.runtime import (DEFENSE_PRESETS, SERVEURS_CONNUS, environnement_calendrier, environnement_github,
                           github_backend_name, jour_reference, lire_serveurs, open_runtime, serveurs_par_defaut,
                           verifier_connexion_github, verifier_connexion_gmail, verifier_connexion_google)
from api.settings import DEFENSE_PRESETS as PRESETS_VUS_PAR_L_API
from api.settings import Settings
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


def test_github_source_maps_to_the_server_backend_and_rejects_unknown_values():
    assert github_backend_name("test") == "fixture" and github_backend_name("github") == "github"
    with pytest.raises(ValueError, match="github_source inconnue"):
        github_backend_name("gitlab")
    with pytest.raises(ValueError, match="github_source"):
        Settings(github_source="gitlab")
    with pytest.raises(ValueError, match="github_source inconnue"):
        asyncio.run(_ouvrir_puis_fermer(github_source="gitlab"))


async def _ouvrir_puis_fermer(**kwargs):
    async with open_runtime(source="test", defenses="toutes", llm=NaiveVictimLLM(), audit_path=None, **kwargs):
        pass


def test_settings_read_the_github_source_from_the_environment(monkeypatch):
    monkeypatch.setenv("SYNAPSE_GITHUB_SOURCE", "github")
    assert Settings.from_env().github_source == "github"
    monkeypatch.delenv("SYNAPSE_GITHUB_SOURCE")
    assert Settings.from_env().github_source == "test"


def test_github_environment_passes_the_allowlist_explicitly_and_never_the_token():
    """Le SDK mcp ne transmet pas os.environ au serveur : la liste blanche doit être passée explicitement.
    Le jeton, lui, n'est jamais dans l'environnement du serveur (lu dans secrets/github_token)."""
    parent = {"SYNAPSE_GITHUB_REPOS": "mon-compte/mon-depot", "SYNAPSE_GITHUB_TOKEN": "FAUX_JETON_TEST"}
    test_env = environnement_github("test", env=parent)
    vrai_env = environnement_github("github", env=parent)
    assert test_env == {"SYNAPSE_GITHUB_BACKEND": "fixture", "SYNAPSE_GITHUB_REPOS": "demo/agentflow-test,demo/projet-y"}
    assert vrai_env == {"SYNAPSE_GITHUB_BACKEND": "github", "SYNAPSE_GITHUB_REPOS": "mon-compte/mon-depot"}
    assert all("FAUX_JETON_TEST" not in str(e) for e in (test_env, vrai_env))
    assert serveurs_par_defaut("test", "tst_")["github"].env["SYNAPSE_GITHUB_BACKEND"] == "fixture"


def test_real_github_requires_a_token_file_and_the_allowlist_is_optional(tmp_path):
    verifier_connexion_github("test", racine=tmp_path, env={})               # données de test : rien d'exigé
    with pytest.raises(RuntimeError, match="secrets/github_token"):          # D7 : sans liste = découverte
        verifier_connexion_github("github", racine=tmp_path, env={})
    repos = {"SYNAPSE_GITHUB_REPOS": "mon-compte/mon-depot"}
    with pytest.raises(RuntimeError, match="secrets/github_token"):
        verifier_connexion_github("github", racine=tmp_path, env=repos)
    with pytest.raises(RuntimeError, match="secrets/github_token"):     # un jeton en variable ne suffit pas
        verifier_connexion_github("github", racine=tmp_path, env={**repos, "SYNAPSE_GITHUB_TOKEN": "x"})
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "github_token").write_text("faux-jeton-de-test")
    verifier_connexion_github("github", racine=tmp_path, env=repos)
    verifier_connexion_github("github", racine=tmp_path, env={})             # jeton présent, sans liste : accepté


def test_server_list_is_parsed_in_canonical_order_and_rejects_empty_or_unknown_names():
    assert lire_serveurs("calendar,mail,github") == SERVEURS_CONNUS == ("calendar", "mail", "github")
    assert lire_serveurs(" github , calendar ") == ("calendar", "github")
    assert lire_serveurs(("github", "github")) == ("github",)
    for vide in ("", " , ", ()):
        with pytest.raises(ValueError, match="Liste de serveurs vide"):
            lire_serveurs(vide)
    with pytest.raises(ValueError, match="Serveur inconnu : gitlab"):
        lire_serveurs("github,gitlab")
    with pytest.raises(ValueError, match="Serveur inconnu"):
        Settings(servers="hello")
    with pytest.raises(ValueError, match="Serveur inconnu"):
        asyncio.run(_ouvrir_puis_fermer(actifs="calendar,hello"))


def test_settings_read_the_server_list_from_the_environment(monkeypatch):
    monkeypatch.setenv("SYNAPSE_SERVERS", "mail,calendar")
    assert Settings.from_env().servers == ("calendar", "mail")
    monkeypatch.delenv("SYNAPSE_SERVERS")
    assert Settings.from_env().servers == SERVEURS_CONNUS


class LLMQuiNoteLesPrompts(ScriptedLLM):
    """Doublure : mémorise le message système reçu à chaque appel (plan, act, verify)."""
    def __init__(self, script):
        super().__init__(script)
        self.systemes = []

    async def ainvoke(self, messages):
        self.systemes.append(str(messages[0].content))
        return await super().ainvoke(messages)


def _prompts_et_serveurs(actifs):
    llm = LLMQuiNoteLesPrompts([AIMessage(content="Plan."), AIMessage(content="Rien."), AIMessage(content="OK")])

    async def scenario():
        async with open_runtime(source="test", defenses="aucune", llm=llm, audit_path=None, actifs=actifs) as rt:
            await run_agent(rt.graph, "Bonjour", "srv1")
            return rt.problems, sorted({s["name"].split("__")[0] for s in rt.toolbox.specs})
    problems, serveurs = asyncio.run(scenario())
    return llm.systemes, problems, serveurs


def test_only_requested_servers_start_and_the_prompts_describe_them():
    systemes, problems, serveurs = _prompts_et_serveurs("github")
    assert serveurs == ["github"] and problems == []
    plan, act = systemes[0], systemes[1]
    assert "accès à GitHub de l'utilisateur" in plan and "accès à GitHub de l'utilisateur" in act
    assert "calendrier" not in plan + act and "mail" not in act


def test_reference_day_is_real_when_the_test_calendar_is_not_started():
    async def jour(actifs):
        async with open_runtime(source="test", defenses="toutes", llm=NaiveVictimLLM(), audit_path=None,
                                actifs=actifs) as rt:
            return rt.jour_ref
    assert asyncio.run(jour("github")) == date.today()           # GitHub seul : vraie semaine
    assert asyncio.run(jour("calendar,github")) == DATE_DEMO      # calendrier de test : date fixe inchangée


def test_default_prompts_announce_all_three_sources():
    systemes, problems, serveurs = _prompts_et_serveurs(SERVEURS_CONNUS)
    assert serveurs == ["calendar", "github", "mail"] and problems == []
    assert "accès au calendrier, au mail et à GitHub de l'utilisateur" in systemes[1]


def test_source_description_keeps_the_historical_wording_by_default():
    assert decrire_sources(SOURCES_PAR_DEFAUT) == "au calendrier et au mail"
    assert decrire_sources(("calendar",)) == "au calendrier"
    assert decrire_sources(("calendar", "mail", "github")) == "au calendrier, au mail et à GitHub"


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
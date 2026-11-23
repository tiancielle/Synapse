"""Recherche de mails : filtres sur le backend de test et via l'outil MCP (expéditeur, date, heure, non lus)."""
import asyncio
from pathlib import Path

import pytest
from mail_backend import FixtureMailBackend

from agent.tools import Toolbox

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "data" / "fixtures" / "mail.json"
SERVER = ROOT / "servers" / "mail_server.py"
LE_17 = ["m_ecole_03", "m_ecole_04", "m_ecole_90", "m_ecole_93", "m_perso_02", "m_perso_04", "m_stage_03", "m_stage_92"]


@pytest.fixture
def backend(tmp_path):
    return FixtureMailBackend(FIXTURE, tmp_path / "state.json")


def ids(hits):
    return sorted(h["id"] for h in hits)


# --- backend de test ---------------------------------------------------------------------------

def test_a_given_day_returns_exactly_that_days_mails(backend):
    assert ids(backend.search(depuis="2026-10-17", jusqu_a="2026-10-17", limit=50)) == LE_17


def test_hour_range_within_a_day(backend):
    hits = backend.search(depuis="2026-10-17T16:00", jusqu_a="2026-10-17T20:00", limit=50)
    assert ids(hits) == ["m_ecole_03", "m_ecole_04"]                 # 16h45 et 19h10
    assert backend.search(depuis="2026-10-17T19:10", jusqu_a="2026-10-17T19:10")[0]["id"] == "m_ecole_04"


def test_sender_subject_unread_and_account_filters(backend):
    assert ids(backend.search(expediteur="sara")) == ["m_perso_01"]
    assert ids(backend.search(expediteur="ALAOUI")) == ["m_stage_01"]
    assert ids(backend.search(sujet="rappel", limit=50)) == ["m_ecole_02", "m_perso_02"]
    assert len(backend.search(non_lus=True, limit=50)) == 18
    assert ids(backend.search(account="ecole", non_lus=True, depuis="2026-10-16", jusqu_a="2026-10-16",
                              limit=50)) == ["m_ecole_01", "m_ecole_92"]


def test_default_limit_is_five_and_most_recent_first(backend):
    hits = backend.search()
    assert len(hits) == 5
    assert [h["date"] for h in hits] == sorted((h["date"] for h in hits), reverse=True)


def test_invalid_filters_raise_clear_messages(backend):
    with pytest.raises(ValueError, match="« depuis ».*AAAA-MM-JJ"):
        backend.search(depuis="hier")
    with pytest.raises(ValueError, match="antérieur"):
        backend.search(depuis="2026-10-18", jusqu_a="2026-10-17")
    with pytest.raises(ValueError, match="Compte inconnu"):
        backend.search(account="inconnu", depuis="2026-10-17")


# --- via le serveur MCP (ce que voit l'agent) ------------------------------------------------

def _appeler(nom, args, tmp_path):
    async def scenario():
        async with Toolbox("mail", SERVER, env={"SYNAPSE_STATE_DIR": str(tmp_path)}) as tb:
            return await tb.call_checked(nom, args)
    return asyncio.run(scenario())


def test_tool_filters_by_day_and_tells_whether_the_limit_was_reached(tmp_path):
    ok, data = _appeler("chercher_mails", {"depuis": "2026-10-17", "jusqu_a": "2026-10-17", "limite": 50}, tmp_path)
    assert ok and ids(data["mails"]) == LE_17 and data["limite_atteinte"] is False
    ok, data = _appeler("chercher_mails", {}, tmp_path)
    assert ok and len(data["mails"]) == 5 and data["limite_atteinte"] is True


def test_tool_errors_reach_the_model_with_a_message_it_can_act_on(tmp_path):
    ok, data = _appeler("chercher_mails", {"depuis": "hier"}, tmp_path)
    assert ok is False
    assert "AAAA-MM-JJ" in data["erreur"] and "depuis" in data["erreur"]       # le modèle peut se corriger
    ok, data = _appeler("lire_mail", {"id_mail": "nexiste_pas"}, tmp_path)
    assert ok is False and "Mail introuvable" in data["erreur"]


def test_search_tool_description_documents_every_filter_in_its_first_line_and_body(tmp_path):
    async def scenario():
        async with Toolbox("mail", SERVER, env={"SYNAPSE_STATE_DIR": str(tmp_path)}) as tb:
            return next(t for t in tb.tools if t.name == "chercher_mails")
    outil = asyncio.run(scenario())
    premiere_ligne = outil.description.splitlines()[0]          # la seule ligne que voit le planificateur
    assert "filtres" in premiere_ligne and "dates" in premiere_ligne
    for champ in ("requete", "expediteur", "sujet", "depuis", "jusqu_a", "non_lus", "limite"):
        assert champ in outil.description
    assert set(outil.input_schema["properties"]) == {"requete", "compte", "expediteur", "sujet", "depuis",
                                                    "jusqu_a", "non_lus", "limite"}

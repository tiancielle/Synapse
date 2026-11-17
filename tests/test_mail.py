"""Serveur mail (données de test) : étiquettes cachées, outils, écritures, cohérence du jeu de données."""
import asyncio
import json
from pathlib import Path

import pytest
from mail_backend import FixtureMailBackend

from agent.firewall import detect_injection
from agent.tools import Toolbox
from core.registry import Decision, Risk, check_consistency, decide, policy_for

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "data" / "fixtures" / "mail.json"
SERVER = ROOT / "servers" / "mail_server.py"


@pytest.fixture
def backend(tmp_path):
    return FixtureMailBackend(FIXTURE, tmp_path / "state.json")


@pytest.fixture(scope="module")
def raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["mails"]


# --- le backend --------------------------------------------------------------------------------

def test_three_accounts_and_filtering(backend):
    assert backend.accounts == ["perso", "ecole", "stage"]
    for compte in backend.accounts:
        hits = backend.search(account=compte, limit=50)
        assert hits and all(h["compte"] == compte for h in hits)
    with pytest.raises(ValueError, match="Compte inconnu"):
        backend.search(account="inconnu")


def test_search_by_keyword_most_recent_first_and_limited(backend):
    hits = backend.search("projet", limit=50)
    assert hits and hits == sorted(hits, key=lambda h: h["date"], reverse=True)
    assert len(backend.search(limit=3)) == 3
    assert backend.search("zzz-introuvable") == []


def test_evaluation_labels_are_never_exposed(backend):
    tout = backend.search(limit=50)
    assert len(tout) == 24
    assert all(not k.startswith("_") for h in tout for k in h)
    for h in tout:
        mail = backend.read(h["id"])
        assert all(not k.startswith("_") for k in mail)
    assert "_attack" not in json.dumps([backend.read(h["id"]) for h in tout])


def test_read_returns_full_text_and_rejects_unknown_ids(backend):
    mail = backend.read("m_ecole_01")
    assert "créneau d'une heure" in mail["corps"] and mail["compte"] == "ecole"
    with pytest.raises(ValueError, match="introuvable"):
        backend.read("m_nexiste_pas")


def test_draft_is_stored_but_not_sent(backend):
    draft = backend.create_draft("ecole", "benali@ecole.test", "Créneau", "Mardi 14h ?")
    assert draft["id"] == "brouillon_001"
    assert len(backend.drafts) == 1 and backend.sent == []


def test_send_is_recorded_and_persists_across_instances(backend, tmp_path):
    backend.send("stage", "alaoui@stage.test", "Point", "Vendredi 10h.")
    assert backend.sent[0]["a"] == "alaoui@stage.test"
    assert FixtureMailBackend(FIXTURE, tmp_path / "state.json").sent == backend.sent


@pytest.mark.parametrize("args", [
    ("", "a@b.test", "s", "c"), ("inconnu", "a@b.test", "s", "c"),
    ("perso", "pas-une-adresse", "s", "c"), ("perso", "a b@c.test", "s", "c"), ("perso", "a@b.test", "  ", "c"),
])
def test_invalid_messages_are_rejected(backend, args):
    with pytest.raises(ValueError):
        backend.send(*args)
    with pytest.raises(ValueError):
        backend.create_draft(*args)
    assert backend.sent == [] and backend.drafts == []


# --- cohérence du jeu de données (base de l'évaluation) ----------------------------------------

def test_dataset_is_balanced_and_covers_every_attack_family(raw):
    normaux = [m for m in raw if not m["_attack"] and not m.get("_hard_negative")]
    attaques = [m for m in raw if m["_attack"]]
    pieges = [m for m in raw if m.get("_hard_negative")]
    assert (len(normaux), len(attaques), len(pieges)) == (12, 8, 4)
    assert {m["_attack_type"] for m in attaques} == {
        "exfiltration", "tool_hijack", "hidden_instruction", "multilingual", "encoded", "paraphrase", "fake_authority"}
    assert all("_goal" in m for m in attaques)
    assert {m["_language"] for m in attaques if m["_attack_type"] == "multilingual"} == {"es", "ar"}


def test_dataset_is_well_formed_and_synthetic(raw):
    assert len({m["id"] for m in raw}) == len(raw)
    for m in raw:
        assert m["compte"] in ("perso", "ecole", "stage")
        assert "2026-10-14" <= m["date"][:10] <= "2026-10-18"
        for adresse in (m["de"].split("<")[-1].rstrip(">"), m["a"]):
            assert adresse.endswith(".test"), f"adresse non synthétique : {adresse}"


def test_current_detector_matches_the_design_of_the_dataset(raw):
    """Mails normaux : aucun faux positif. Pièges légitimes : déclenchent le détecteur (c'est leur rôle : mesurer
    les faux positifs). Attaques « classiques » : détectées. Les autres familles ne sont volontairement PAS testées :
    leur détection est précisément ce que mesure l'évaluation (P3)."""
    def trouve(m):
        return detect_injection(m["sujet"] + " " + m["corps"])
    assert all(trouve(m) == [] for m in raw if not m["_attack"] and not m.get("_hard_negative"))
    assert all(trouve(m) for m in raw if m.get("_hard_negative"))
    assert all(trouve(m) for m in raw if m.get("_attack_type") in ("exfiltration", "fake_authority"))


# --- le serveur MCP et le registre ---------------------------------------------------------

def test_registry_matches_what_the_server_exposes_and_send_needs_confirmation(tmp_path):
    async def scenario():
        async with Toolbox("mail", SERVER, env={"SYNAPSE_STATE_DIR": str(tmp_path)}) as tb:
            return [t.name for t in tb.tools], check_consistency("mail", tb.tools)
    noms, problemes = asyncio.run(scenario())
    assert sorted(noms) == ["chercher_mails", "creer_brouillon", "envoyer_mail", "lire_mail"]
    assert problemes == []
    assert decide("mail", "chercher_mails") is Decision.AUTO and decide("mail", "lire_mail") is Decision.AUTO
    assert decide("mail", "creer_brouillon") is Decision.NOTIFY
    assert decide("mail", "envoyer_mail") is Decision.CONFIRM
    assert policy_for("mail", "envoyer_mail").risk is Risk.SENSITIVE and not policy_for("mail", "envoyer_mail").reversible
    assert decide("mail", "supprimer_mail") is Decision.DENY          # outil inconnu : refusé par défaut


def test_server_tools_end_to_end(tmp_path):
    async def scenario():
        async with Toolbox("mail", SERVER, env={"SYNAPSE_STATE_DIR": str(tmp_path)}) as tb:
            liste = await tb.call_checked("chercher_mails", {"compte": "ecole", "requete": "projet"})
            lu = await tb.call_checked("lire_mail", {"id_mail": "m_ecole_01"})
            inconnu = await tb.call_checked("lire_mail", {"id_mail": "nexiste_pas"})
            brouillon = await tb.call_checked("creer_brouillon", {"compte": "ecole", "a": "benali@ecole.test",
                                                                  "sujet": "Créneau", "corps": "Mardi 14h ?"})
            envoi = await tb.call_checked("envoyer_mail", {"compte": "ecole", "a": "benali@ecole.test",
                                                           "sujet": "Créneau", "corps": "Mardi 14h ?"})
            return liste, lu, inconnu, brouillon, envoi
    liste, lu, inconnu, brouillon, envoi = asyncio.run(scenario())
    assert liste[0] and all(m["compte"] == "ecole" for m in liste[1]["mails"])
    assert lu[0] and lu[1]["mail"]["id"] == "m_ecole_01" and not any(k.startswith("_") for k in lu[1]["mail"])
    assert inconnu[0] is False                                        # erreur d'outil, distincte d'un succès
    assert brouillon[0] and envoi[0]
    etat = json.loads((tmp_path / "mail_state.json").read_text(encoding="utf-8"))
    assert len(etat["brouillons"]) == 1 and len(etat["envoyes"]) == 1
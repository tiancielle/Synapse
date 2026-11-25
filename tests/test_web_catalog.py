"""Le catalogue affiché par l'interface (web/src/lib/catalog.json) reflète EXACTEMENT le registre.

L'interface n'a pas de route pour lister les outils : elle affiche cette copie. Ce test empêche qu'elle invente
un outil, oublie un outil ou présente un risque différent de celui que le pare-feu applique.
"""
import json
from pathlib import Path

from core.registry import MAIL_TOOLS_BY_BACKEND, REGISTRY, Risk

CATALOGUE = Path(__file__).resolve().parent.parent / "web" / "src" / "lib" / "catalog.json"
RISQUES = {"read": Risk.READ, "soft_write": Risk.SOFT_WRITE, "sensitive": Risk.SENSITIVE}


def _catalogue():
    return json.loads(CATALOGUE.read_text(encoding="utf-8"))["servers"]


def test_catalogue_lists_exactly_the_registered_tools_with_their_risk_and_scope():
    affiches = {(srv, t["name"]): t for srv, s in _catalogue().items() for t in s["tools"]}
    assert set(affiches) == set(REGISTRY)
    for cle, outil in affiches.items():
        politique = REGISTRY[cle]
        assert RISQUES[outil["risk"]] is politique.risk, cle
        assert outil["scope"] == politique.scope, cle


def test_real_availability_matches_the_read_only_real_backends():
    c = _catalogue()
    assert {t["name"] for t in c["mail"]["tools"] if t["real"]} == MAIL_TOOLS_BY_BACKEND["gmail"]
    # calendrier Google et GitHub réel : seules les lectures fonctionnent
    for srv in ("calendar", "github"):
        for t in c[srv]["tools"]:
            assert t["real"] is (REGISTRY[(srv, t["name"])].risk is Risk.READ), (srv, t["name"])

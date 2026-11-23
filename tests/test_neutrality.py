"""Neutralité de l'ablation : les descriptions d'outils ne portent aucune consigne de sécurité.

Sinon le niveau « aucune défense » n'est pas nu et les mesures d'évaluation sont faussées.
Les consignes anti-injection n'appartiennent qu'à hardened_prompt (agent/graph.py).
"""
import asyncio
import re
from contextlib import AsyncExitStack
from pathlib import Path

from agent.tools import Toolbox

ROOT = Path(__file__).resolve().parent.parent
SERVERS = ROOT / "servers"

# Motifs qui trahissent une consigne de sécurité dans une description d'outil (règle 7).
_INTERDITS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"non\s+fiable",
        r"ne\s+suis\s+jamais",
        r"\bignore\b",
        r"\binstructions?\b",
        r"donn[ée]e\s+externe",
        r"ne\s+(?:pas\s+)?ob[eé]ir",
        r"untrusted",
        r"not\s+instructions?",
    )
]


def _violations(texte: str) -> list[str]:
    return [rx.pattern for rx in _INTERDITS if rx.search(texte or "")]


def _collecter_fautes(tmp_path, mail_backend: str) -> list[str]:
    env_cal = {"SYNAPSE_BACKEND": "fixture", "SYNAPSE_STATE_DIR": str(tmp_path / "cal")}
    env_mail = {
        "SYNAPSE_MAIL_BACKEND": mail_backend,
        "SYNAPSE_STATE_DIR": str(tmp_path / f"mail_{mail_backend}"),
    }

    async def scenario():
        fautes = []
        async with AsyncExitStack() as stack:
            for nom, script, env in (
                ("calendar", SERVERS / "calendar_server.py", env_cal),
                ("mail", SERVERS / "mail_server.py", env_mail),
            ):
                tb = await stack.enter_async_context(Toolbox(nom, script, env=env))
                for spec in tb.specs:
                    hits = _violations(spec.get("description") or "")
                    if hits:
                        fautes.append(
                            f"{nom}.{spec['name']} [{mail_backend}] : motifs {hits} dans « {spec['description']} »"
                        )
        return fautes

    return asyncio.run(scenario())


def test_default_server_tool_descriptions_have_no_security_instructions(tmp_path):
    """Calendar + mail fixture : descriptions neutres."""
    fautes = _collecter_fautes(tmp_path, "fixture")
    assert fautes == [], "Descriptions non neutres :\n" + "\n".join(fautes)


def test_gmail_backend_tool_descriptions_have_no_security_instructions(tmp_path):
    """Mail backend gmail (sans jeton : list_tools seulement) : descriptions neutres."""
    fautes = _collecter_fautes(tmp_path, "gmail")
    assert fautes == [], "Descriptions non neutres :\n" + "\n".join(fautes)

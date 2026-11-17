"""Serveur MCP Mail.

Backend choisi par SYNAPSE_MAIL_BACKEND :
  fixture (défaut) : données de test (perso, ecole, stage)
  gmail            : vrai Gmail, lecture seule uniquement
État des écritures (mode fixture) : SYNAPSE_STATE_DIR (par défaut data/private).
"""
import os
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from mail_backend import FixtureMailBackend, GmailMailBackend

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.registry import outils_mail_attendus  # noqa: E402

BACKEND_NAME = os.getenv("SYNAPSE_MAIL_BACKEND", "fixture")
if BACKEND_NAME not in ("fixture", "gmail"):
    raise RuntimeError(
        f"SYNAPSE_MAIL_BACKEND invalide : {BACKEND_NAME!r}. Valeurs acceptées : fixture, gmail"
    )

if BACKEND_NAME == "fixture":
    state_dir = Path(os.getenv("SYNAPSE_STATE_DIR", ROOT / "data" / "private"))
    backend = FixtureMailBackend(ROOT / "data" / "fixtures" / "mail.json", state_dir / "mail_state.json")
elif BACKEND_NAME == "gmail":
    backend = GmailMailBackend()
else:  # impossible après le contrôle ci-dessus ; garde pour la clarté
    raise RuntimeError(f"Backend mail inconnu : {BACKEND_NAME}")

OUTILS_ATTENDUS = outils_mail_attendus(BACKEND_NAME)
COMPTES = ", ".join(backend.accounts)

mcp = MCPServer("mail")

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True)


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Cherche des mails par mot-clé (sujet, expéditeur, contenu), les plus récents d'abord.\n"
        f"Comptes disponibles : {COMPTES} (vide = tous les comptes). "
        "Renvoie un aperçu ; utiliser lire_mail pour le texte complet."
    ),
)
def chercher_mails(requete: str = "", compte: str = "", limite: int = 10) -> dict:
    return {"mails": backend.search(requete, compte, limite)}


@mcp.tool(
    annotations=READ_ONLY,
    description="Lit un mail complet à partir de son identifiant (identifiant renvoyé par chercher_mails).",
)
def lire_mail(id_mail: str) -> dict:
    return {"mail": backend.read(id_mail)}


if "creer_brouillon" in OUTILS_ATTENDUS:
    @mcp.tool(
        annotations=WRITE,
        description=(
            f"Enregistre un brouillon de mail dans un compte ({COMPTES}). Rien n'est envoyé."
        ),
    )
    def creer_brouillon(compte: str, a: str, sujet: str, corps: str) -> dict:
        return {"brouillon": backend.create_draft(compte, a, sujet, corps)}


if "envoyer_mail" in OUTILS_ATTENDUS:
    @mcp.tool(
        annotations=DESTRUCTIVE,
        description=(
            f"Envoie un mail depuis un compte ({COMPTES}). Action irréversible."
        ),
    )
    def envoyer_mail(compte: str, a: str, sujet: str, corps: str) -> dict:
        return {"envoye": backend.send(compte, a, sujet, corps)}


if __name__ == "__main__":
    mcp.run()

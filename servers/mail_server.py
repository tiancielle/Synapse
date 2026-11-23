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
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from mail_backend import FixtureMailBackend, GmailMailBackend
from mail_filters import LIMITE_DEFAUT, LIMITE_MAX

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


def _ou_erreur_lisible(appel):
    """Les erreurs ATTENDUES (date invalide, compte ou mail inconnu, accès Gmail expiré) deviennent des ToolError :
    leur message, écrit sans aucun contenu de mail, arrive jusqu'au modèle qui peut se corriger.
    Toute autre exception reste un plantage : le modèle ne voit que « Error executing tool »."""
    try:
        return appel()
    except (ValueError, RuntimeError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Cherche des mails avec des filtres facultatifs (expéditeur, sujet, dates, non lus), les plus récents d'abord.\n"
        f"Comptes disponibles : {COMPTES} (vide = tous les comptes).\n"
        "Les filtres se combinent (ET). Sans filtre, renvoie les mails les plus récents.\n"
        "- requete : mots présents dans le sujet, l'expéditeur ou le contenu.\n"
        "- expediteur : nom ou adresse de l'expéditeur (ex. Sara).\n"
        "- sujet : mots présents dans le sujet.\n"
        "- depuis / jusqu_a : bornes de date en heure locale, au format AAAA-MM-JJ ou AAAA-MM-JJTHH:MM. "
        "Avec une date seule, jusqu_a couvre toute la journée : pour les mails d'un jour précis, "
        "donner la même date aux deux.\n"
        "- non_lus : true pour ne garder que les mails non lus.\n"
        f"- limite : nombre maximum de mails ({LIMITE_DEFAUT} par défaut, {LIMITE_MAX} au maximum).\n"
        "Renvoie un aperçu de chaque mail ; utiliser lire_mail pour le texte complet."
    ),
)
def chercher_mails(requete: str = "", compte: str = "", expediteur: str = "", sujet: str = "",
                   depuis: str = "", jusqu_a: str = "", non_lus: bool = False, limite: int = LIMITE_DEFAUT) -> dict:
    mails = _ou_erreur_lisible(lambda: backend.search(
        requete, compte, limite, expediteur=expediteur, sujet=sujet, depuis=depuis, jusqu_a=jusqu_a,
        non_lus=non_lus))
    # limite_atteinte : il peut y avoir d'autres mails que ceux listés (utile pour répondre honnêtement)
    return {"mails": mails, "limite_atteinte": len(mails) >= max(1, min(int(limite), LIMITE_MAX))}


@mcp.tool(
    annotations=READ_ONLY,
    description="Lit un mail complet à partir de son identifiant (identifiant renvoyé par chercher_mails).",
)
def lire_mail(id_mail: str) -> dict:
    return {"mail": _ou_erreur_lisible(lambda: backend.read(id_mail))}


if "creer_brouillon" in OUTILS_ATTENDUS:
    @mcp.tool(
        annotations=WRITE,
        description=(
            f"Enregistre un brouillon de mail dans un compte ({COMPTES}). Rien n'est envoyé."
        ),
    )
    def creer_brouillon(compte: str, a: str, sujet: str, corps: str) -> dict:
        return {"brouillon": _ou_erreur_lisible(lambda: backend.create_draft(compte, a, sujet, corps))}


if "envoyer_mail" in OUTILS_ATTENDUS:
    @mcp.tool(
        annotations=DESTRUCTIVE,
        description=(
            f"Envoie un mail depuis un compte ({COMPTES}). Action irréversible."
        ),
    )
    def envoyer_mail(compte: str, a: str, sujet: str, corps: str) -> dict:
        return {"envoye": _ou_erreur_lisible(lambda: backend.send(compte, a, sujet, corps))}


if __name__ == "__main__":
    mcp.run()
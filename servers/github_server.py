"""Serveur MCP GitHub, lecture seule.

Backend choisi par SYNAPSE_GITHUB_BACKEND :
  fixture (défaut) : dépôts synthétiques (data/fixtures/github.json)
  github           : vrai GitHub, API REST en lecture seule (requêtes GET uniquement)
Liste blanche des dépôts : SYNAPSE_GITHUB_REPOS (« proprietaire/depot,... »).
  fixture : demo/agentflow-test par défaut ; github : OBLIGATOIRE (sinon le serveur refuse de démarrer).
Jeton (backend github) : SYNAPSE_GITHUB_TOKEN ou secrets/github_token, lu au premier appel d'outil.
  Lancé par l'agent (chat.py, run_api.py) : SEUL le fichier secrets/github_token est utilisé, car le SDK mcp
  ne transmet pas os.environ au serveur et le runtime ne lui passe jamais le jeton.
Aucun outil d'écriture, dans aucun backend.
"""
import logging
import os
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from github_backend import (LIMITE_DEFAUT, LIMITE_MAX, ErreurOutil, FixtureGithubBackend, GithubBackend,
                            lire_jeton, lire_liste_blanche)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.registry import outils_github_attendus  # noqa: E402

DEPOTS_FIXTURE = "demo/agentflow-test"
logging.getLogger("httpx").setLevel(logging.WARNING)        # pas d'URL de requête dans les journaux du serveur

BACKEND_NAME = os.getenv("SYNAPSE_GITHUB_BACKEND", "fixture")
OUTILS_ATTENDUS = outils_github_attendus(BACKEND_NAME)      # valeur inconnue -> ValueError claire au démarrage

if BACKEND_NAME == "fixture":
    backend = FixtureGithubBackend(ROOT / "data" / "fixtures" / "github.json",
                                   lire_liste_blanche(os.getenv("SYNAPSE_GITHUB_REPOS", DEPOTS_FIXTURE)))
else:   # "github" : pas de liste blanche par défaut -> GithubBackend refuse de démarrer sans elle
    backend = GithubBackend(lire_liste_blanche(os.getenv("SYNAPSE_GITHUB_REPOS", "")),
                            source_jeton=lambda: lire_jeton(ROOT))

DEPOTS = ", ".join(backend.depots_autorises)

mcp = MCPServer("github")

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False)


def _ou_erreur_lisible(appel):
    """Les erreurs ATTENDUES (ErreurOutil : dépôt non autorisé, chemin invalide, introuvable, accès refusé...)
    deviennent des ToolError : leur message, écrit dans github_backend sans aucun contenu, arrive au modèle.
    Toute autre exception (même un ValueError de bibliothèque, qui pourrait citer des octets du contenu)
    reste un plantage : le modèle ne voit que « Error executing tool »."""
    try:
        return appel()
    except ErreurOutil as exc:
        raise ToolError(str(exc)) from exc


_LISTE = (f"- depot : proprietaire/depot. Dépôts disponibles : {DEPOTS}.\n"
          "- etat : open (défaut), closed ou all.\n"
          f"- limite : nombre maximum ({LIMITE_DEFAUT} par défaut, {LIMITE_MAX} au maximum).\n")


@mcp.tool(
    annotations=READ_ONLY,
    description=("Liste les issues d'un dépôt GitHub, les plus récentes d'abord.\n" + _LISTE +
                 "Renvoie un résumé de chaque issue ; utiliser lire_issue pour le texte et les commentaires."),
)
def lister_issues(depot: str, etat: str = "open", limite: int = LIMITE_DEFAUT) -> dict:
    issues, il_en_reste = _ou_erreur_lisible(lambda: backend.lister_issues(depot, etat, limite))
    return {"issues": issues, "limite_atteinte": il_en_reste}


@mcp.tool(
    annotations=READ_ONLY,
    description=("Lit une issue GitHub : titre, texte, étiquettes, auteur et commentaires.\n"
                 f"Dépôts disponibles : {DEPOTS}."),
)
def lire_issue(depot: str, numero: int) -> dict:
    return {"issue": _ou_erreur_lisible(lambda: backend.lire_issue(depot, numero))}


@mcp.tool(
    annotations=READ_ONLY,
    description=("Liste les pull requests d'un dépôt GitHub, les plus récentes d'abord.\n" + _LISTE +
                 "Renvoie un résumé de chaque pull request ; utiliser lire_pull_request pour le détail."),
)
def lister_pull_requests(depot: str, etat: str = "open", limite: int = LIMITE_DEFAUT) -> dict:
    prs, il_en_reste = _ou_erreur_lisible(lambda: backend.lister_pull_requests(depot, etat, limite))
    return {"pull_requests": prs, "limite_atteinte": il_en_reste}


@mcp.tool(
    annotations=READ_ONLY,
    description=("Lit une pull request GitHub : titre, texte, branches, fichiers modifiés et commentaires.\n"
                 f"Dépôts disponibles : {DEPOTS}."),
)
def lire_pull_request(depot: str, numero: int) -> dict:
    return {"pull_request": _ou_erreur_lisible(lambda: backend.lire_pull_request(depot, numero))}


@mcp.tool(
    annotations=READ_ONLY,
    description=("Lit un fichier texte d'un dépôt GitHub (branche par défaut).\n"
                 f"Dépôts disponibles : {DEPOTS}.\n"
                 "- chemin : relatif à la racine du dépôt, avec des « / » (ex. docs/installation.md)."),
)
def lire_fichier(depot: str, chemin: str) -> dict:
    return {"fichier": _ou_erreur_lisible(lambda: backend.lire_fichier(depot, chemin))}


if __name__ == "__main__":
    mcp.run()

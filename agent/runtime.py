"""Assemblage commun de l'agent, utilisé par chat.py ET par l'API : un seul endroit à modifier.

Contient : les préréglages de défenses, le choix de la date de référence, la liste des serveurs MCP,
et `open_runtime` qui démarre les outils et construit le graphe.
"""
from __future__ import annotations

import logging
import os
import tempfile
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from agent.dates import DATE_DEMO, reperes_dates
from agent.firewall import DefenseConfig, Firewall
from agent.graph import build_graph
from agent.tools import MultiToolbox, Toolbox
from core.registry import check_consistency, outils_github_attendus, outils_mail_attendus

log = logging.getLogger("synapse.runtime")

ROOT = Path(__file__).resolve().parent.parent
SERVERS_DIR = ROOT / "servers"
AUDIT_PATH = ROOT / "data" / "private" / "audit.jsonl"

# les défenses activables (base de l'étude d'ablation)
DEFENSE_PRESETS = {
    "toutes": DefenseConfig(),
    "aucune": DefenseConfig.baseline(),
    "registre": DefenseConfig(use_registry=True, require_confirmation=True, scan_results=False, hardened_prompt=False),
}


@dataclass
class ServerSpec:
    """Comment lancer un serveur MCP (processus fils, transport stdio)."""
    script: Path
    env: dict = field(default_factory=dict)
    log_path: Path | None = None


def jour_reference(source: str) -> date:
    """« Aujourd'hui » : la vraie date avec Google, une date fixe avec les données de test."""
    return date.today() if source == "google" else DATE_DEMO


def mail_backend_name(mail_source: str) -> str:
    """Interrupteur CLI/API (`test`|`gmail`) → valeur SYNAPSE_MAIL_BACKEND (`fixture`|`gmail`)."""
    if mail_source == "test":
        return "fixture"
    if mail_source == "gmail":
        return "gmail"
    raise ValueError(f"mail_source inconnue : {mail_source}. Valeurs acceptées : test, gmail")


def verifier_connexion_google(source: str, racine: Path = ROOT) -> None:
    if source == "google" and not (racine / "secrets" / "token_calendar.json").exists():
        raise RuntimeError("Pas encore connecté à Google. Lance d'abord :  python connect_google.py")


def verifier_connexion_gmail(mail_source: str, racine: Path = ROOT) -> None:
    if mail_source == "gmail" and not (racine / "secrets" / "token_gmail.json").exists():
        raise RuntimeError("Pas encore connecté à Gmail. Lance d'abord :  python connect_gmail.py")


DEPOTS_GITHUB_TEST = "demo/agentflow-test"     # dépôt synthétique de data/fixtures/github.json


def github_backend_name(github_source: str) -> str:
    """Interrupteur CLI/API (`test`|`github`) → valeur SYNAPSE_GITHUB_BACKEND (`fixture`|`github`)."""
    if github_source == "test":
        return "fixture"
    if github_source == "github":
        return "github"
    raise ValueError(f"github_source inconnue : {github_source}. Valeurs acceptées : test, github")


def verifier_connexion_github(github_source: str, racine: Path = ROOT, env=None) -> None:
    """Vrai GitHub : liste blanche ET fichier de jeton obligatoires, vérifiés AVANT de lancer les serveurs.
    Le fichier de jeton n'est jamais ouvert ici (seule son existence est testée)."""
    if github_source != "github":
        return
    env = os.environ if env is None else env
    if not env.get("SYNAPSE_GITHUB_REPOS", "").strip():
        raise RuntimeError("Vrai GitHub : liste blanche absente. Ajouter dans .env la ligne "
                           "SYNAPSE_GITHUB_REPOS=proprietaire/depot")
    if not (racine / "secrets" / "github_token").is_file():
        raise RuntimeError("Vrai GitHub : jeton absent. Créer le fichier secrets/github_token "
                           "(jeton GitHub en lecture seule, sur une seule ligne).")


def environnement_github(github_source: str, env=None) -> dict:
    """Variables du serveur github. Le SDK mcp ne transmet PAS os.environ au serveur : la liste blanche est
    passée explicitement. Le jeton n'y est jamais : le serveur le lit lui-même dans secrets/github_token."""
    env = os.environ if env is None else env
    depots = DEPOTS_GITHUB_TEST if github_source == "test" else env.get("SYNAPSE_GITHUB_REPOS", "")
    return {"SYNAPSE_GITHUB_BACKEND": github_backend_name(github_source), "SYNAPSE_GITHUB_REPOS": depots}


def environnement_calendrier(source: str, prefixe_etat: str) -> dict:
    """Variables d'environnement du serveur de calendrier. Les données de test repartent de zéro
    à chaque lancement (dossier d'état temporaire)."""
    return {"SYNAPSE_BACKEND": "google" if source == "google" else "fixture",
            "SYNAPSE_STATE_DIR": tempfile.mkdtemp(prefix=prefixe_etat)}


def environnement_mail(mail_source: str, prefixe_etat: str) -> dict:
    """Variables d'environnement du serveur mail (backend fixture ou gmail)."""
    return {
        "SYNAPSE_MAIL_BACKEND": mail_backend_name(mail_source),
        "SYNAPSE_STATE_DIR": tempfile.mkdtemp(prefix=prefixe_etat + "mail_"),
    }


def serveurs_par_defaut(source: str, prefixe_etat: str, mail_source: str = "test",
                        github_source: str = "test") -> dict[str, ServerSpec]:
    """Serveurs lancés par défaut. Ajouter un serveur = ajouter une ligne ici (et ses outils au registre)."""
    return {
        "calendar": ServerSpec(SERVERS_DIR / "calendar_server.py",
                               environnement_calendrier(source, prefixe_etat),
                               SERVERS_DIR / "calendar_server.log"),
        "mail": ServerSpec(SERVERS_DIR / "mail_server.py",
                           environnement_mail(mail_source, prefixe_etat),
                           SERVERS_DIR / "mail_server.log"),
        "github": ServerSpec(SERVERS_DIR / "github_server.py",
                             environnement_github(github_source),
                             SERVERS_DIR / "github_server.log"),
    }


def _expected_tools(server_name: str, spec: ServerSpec) -> frozenset[str] | None:
    """Ensemble strict attendu pour check_consistency ; None = comportement historique (tout le registre)."""
    if server_name == "mail":
        return outils_mail_attendus((spec.env or {}).get("SYNAPSE_MAIL_BACKEND", "fixture"))
    if server_name == "github":
        return outils_github_attendus((spec.env or {}).get("SYNAPSE_GITHUB_BACKEND", "fixture"))
    return None


@dataclass
class Runtime:
    graph: object
    firewall: Firewall
    toolbox: MultiToolbox
    jour_ref: date
    problems: list[str]          # incohérences registre / serveurs détectées au démarrage


@asynccontextmanager
async def open_runtime(*, source: str, defenses: str, llm, mail_source: str = "test",
                       github_source: str = "test", audit_path: Path | None = AUDIT_PATH,
                       state_prefix: str = "synapse_", servers: dict[str, ServerSpec] | None = None):
    """Démarre les serveurs MCP et construit l'agent. À utiliser avec `async with`."""
    verifier_connexion_google(source)
    verifier_connexion_gmail(mail_source)
    github_backend_name(github_source)                  # valeur inconnue -> ValueError claire
    verifier_connexion_github(github_source)
    jour_ref = jour_reference(source)
    firewall = Firewall(DEFENSE_PRESETS[defenses], audit_path=audit_path)
    servers = servers or serveurs_par_defaut(source, state_prefix, mail_source=mail_source,
                                             github_source=github_source)
    async with AsyncExitStack() as stack:
        boxes: dict[str, Toolbox] = {}
        for name, spec in servers.items():
            boxes[name] = await stack.enter_async_context(
                Toolbox(name, spec.script, env=spec.env or None, log_path=spec.log_path))
        problems = [
            p for name, tb in boxes.items()
            for p in check_consistency(name, tb.tools, expected=_expected_tools(name, servers[name]))
        ]
        for p in problems:                                   # signalé, pas bloquant : l'outil fautif est refusé par défaut
            log.warning("Registre : %s", p)
        toolbox = MultiToolbox(boxes)
        graph = build_graph(toolbox, llm, firewall, reperes_dates(jour_ref))
        yield Runtime(graph=graph, firewall=firewall, toolbox=toolbox, jour_ref=jour_ref, problems=problems)

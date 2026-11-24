"""Registre des outils : source unique de vérité pour le pare-feu.

Principe : un outil non enregistré est INTERDIT par défaut (deny by default).
Le pare-feu lit ce registre ; ajouter un outil = ajouter une ligne ici.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class Risk(IntEnum):
    READ = 0         # lecture : automatique, journalisée
    SOFT_WRITE = 1   # écriture réversible : notification
    SENSITIVE = 2    # envoi, suppression, modification : confirmation humaine
    FORBIDDEN = 3    # hors périmètre : refus systématique


class Decision(str, Enum):
    AUTO = "auto"
    NOTIFY = "notify"
    CONFIRM = "confirm"
    DENY = "deny"


_DECISION_BY_RISK = {
    Risk.READ: Decision.AUTO,
    Risk.SOFT_WRITE: Decision.NOTIFY,
    Risk.SENSITIVE: Decision.CONFIRM,
    Risk.FORBIDDEN: Decision.DENY,
}


@dataclass(frozen=True)
class ToolPolicy:
    server: str
    tool: str
    risk: Risk
    scope: str            # permission logique, ex. "calendar:read"
    reversible: bool = True
    note: str = ""

    @property
    def decision(self) -> Decision:
        return _DECISION_BY_RISK[self.risk]


REGISTRY: dict[tuple[str, str], ToolPolicy] = {}


def register(server: str, tool: str, risk: Risk, scope: str, reversible: bool = True, note: str = "") -> ToolPolicy:
    policy = ToolPolicy(server, tool, risk, scope, reversible, note)
    REGISTRY[(server, tool)] = policy
    return policy


def policy_for(server: str, tool: str) -> ToolPolicy:
    """Politique d'un outil. Inconnu => FORBIDDEN (deny by default)."""
    return REGISTRY.get((server, tool)) or ToolPolicy(
        server, tool, Risk.FORBIDDEN, "unregistered", False, "Outil non enregistré : refusé par défaut"
    )


def decide(server: str, tool: str) -> Decision:
    return policy_for(server, tool).decision


def _annotations_coherent(server: str, name: str, tool) -> list[str]:
    """Vérifie l'alignement annotations MCP ↔ risque du registre pour un outil exposé."""
    problems: list[str] = []
    if (server, name) not in REGISTRY:
        problems.append(f"{server}.{name} : exposé par le serveur mais NON enregistré (sera refusé)")
        return problems
    policy = REGISTRY[(server, name)]
    ann = getattr(tool, "annotations", None)
    read_only = getattr(ann, "read_only_hint", None)
    destructive = getattr(ann, "destructive_hint", None)
    if read_only is True and policy.risk != Risk.READ:
        problems.append(f"{server}.{name} : annoté read-only mais risque={policy.risk.name}")
    if read_only is not True and policy.risk == Risk.READ:
        problems.append(f"{server}.{name} : risque READ mais le serveur ne le déclare pas read-only")
    if destructive is True and policy.risk < Risk.SENSITIVE:
        problems.append(f"{server}.{name} : annoté destructif mais risque={policy.risk.name} (< SENSITIVE)")
    return problems


def check_consistency(server: str, mcp_tools, expected: frozenset[str] | set[str] | None = None) -> list[str]:
    """Compare le registre avec ce que le serveur MCP expose réellement.

    `mcp_tools` : liste d'outils MCP (avec .name et .annotations).
    `expected` : si fourni, ensemble STRICT des noms d'outils attendus pour ce backend
    (ex. mail fixture vs gmail). Sinon : tous les outils enregistrés pour ce serveur
    doivent être exposés (comportement historique, calendar / hello).
    Renvoie la liste des problèmes détectés (vide = cohérent).
    """
    problems: list[str] = []
    exposed = {t.name: t for t in mcp_tools}

    if expected is not None:
        for name, tool in exposed.items():
            if name not in expected:
                problems.append(f"{server}.{name} : exposé mais hors ensemble attendu pour ce backend")
            else:
                problems.extend(_annotations_coherent(server, name, tool))
        for name in expected:
            if name not in exposed:
                problems.append(f"{server}.{name} : attendu pour ce backend mais absent du serveur")
            elif (server, name) not in REGISTRY:
                problems.append(f"{server}.{name} : attendu mais NON enregistré (sera refusé)")
        return problems

    for name, tool in exposed.items():
        problems.extend(_annotations_coherent(server, name, tool))
    for (srv, name) in REGISTRY:
        if srv == server and name not in exposed:
            problems.append(f"{srv}.{name} : enregistré mais absent du serveur")
    return problems


# Ensembles STRICTS d'outils mail selon le backend (source unique pour serveur + runtime).
MAIL_TOOLS_BY_BACKEND: dict[str, frozenset[str]] = {
    "fixture": frozenset({"chercher_mails", "lire_mail", "creer_brouillon", "envoyer_mail"}),
    "gmail": frozenset({"chercher_mails", "lire_mail"}),
}


def outils_mail_attendus(backend: str) -> frozenset[str]:
    """Noms d'outils que le serveur mail DOIT exposer pour ce backend."""
    try:
        return MAIL_TOOLS_BY_BACKEND[backend]
    except KeyError as exc:
        raise ValueError(
            f"Backend mail inconnu : {backend}. Valeurs acceptées : {', '.join(sorted(MAIL_TOOLS_BY_BACKEND))}"
        ) from exc


# Outils GitHub : MÊMES outils, tous en lecture, pour les deux backends (fixture et github réel).
GITHUB_TOOLS = frozenset({"lister_issues", "lire_issue", "lister_pull_requests", "lire_pull_request", "lire_fichier"})
GITHUB_TOOLS_BY_BACKEND: dict[str, frozenset[str]] = {"fixture": GITHUB_TOOLS, "github": GITHUB_TOOLS}


def outils_github_attendus(backend: str) -> frozenset[str]:
    """Noms d'outils que le serveur github DOIT exposer pour ce backend."""
    try:
        return GITHUB_TOOLS_BY_BACKEND[backend]
    except KeyError as exc:
        raise ValueError(
            f"Backend github inconnu : {backend}. Valeurs acceptées : {', '.join(sorted(GITHUB_TOOLS_BY_BACKEND))}"
        ) from exc


# --- Politique du serveur calendrier -----------------------------------------
register("calendar", "lister_evenements", Risk.READ, "calendar:read")
register("calendar", "chercher_evenements", Risk.READ, "calendar:read")
register("calendar", "trouver_creneaux_libres", Risk.READ, "calendar:read")
register("calendar", "creer_evenement", Risk.SOFT_WRITE, "calendar:write", reversible=True)
register("calendar", "supprimer_evenement", Risk.SENSITIVE, "calendar:write", reversible=False,
         note="Suppression irréversible : confirmation obligatoire")

# --- Politique du serveur mail --------------------------------------------------
register("mail", "chercher_mails", Risk.READ, "mail:read")
register("mail", "lire_mail", Risk.READ, "mail:read")
register("mail", "creer_brouillon", Risk.SOFT_WRITE, "mail:draft", reversible=True)
register("mail", "envoyer_mail", Risk.SENSITIVE, "mail:send", reversible=False,
         note="Envoi irréversible : confirmation obligatoire")

# --- Politique du serveur GitHub (lecture seule) -------------------------------------
for _outil in sorted(GITHUB_TOOLS):
    register("github", _outil, Risk.READ, "github:read")
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


def check_consistency(server: str, mcp_tools) -> list[str]:
    """Compare le registre avec ce que le serveur MCP expose réellement.

    `mcp_tools` : liste d'outils MCP (avec .name et .annotations).
    Renvoie la liste des problèmes détectés (vide = cohérent).
    """
    problems: list[str] = []
    exposed = {t.name: t for t in mcp_tools}

    for name, tool in exposed.items():
        if (server, name) not in REGISTRY:
            problems.append(f"{server}.{name} : exposé par le serveur mais NON enregistré (sera refusé)")
            continue
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

    for (srv, name) in REGISTRY:
        if srv == server and name not in exposed:
            problems.append(f"{srv}.{name} : enregistré mais absent du serveur")
    return problems


# --- Politique du serveur calendrier -----------------------------------------
register("calendar", "lister_evenements", Risk.READ, "calendar:read")
register("calendar", "chercher_evenements", Risk.READ, "calendar:read")
register("calendar", "trouver_creneaux_libres", Risk.READ, "calendar:read")
register("calendar", "creer_evenement", Risk.SOFT_WRITE, "calendar:write", reversible=True)
register("calendar", "supprimer_evenement", Risk.SENSITIVE, "calendar:write", reversible=False,
         note="Suppression irréversible : confirmation obligatoire")

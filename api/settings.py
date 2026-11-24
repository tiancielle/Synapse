"""Configuration du backend API (tout est local : l'API n'écoute que sur 127.0.0.1)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agent.runtime import DEFENSE_PRESETS, ROOT, SERVEURS_CONNUS, lire_serveurs   # noqa: F401 (réexportés)


@dataclass
class Settings:
    source: str = "test"                 # test = données fictives | google = vrai Google Calendar (lecture seule)
    mail_source: str = "test"            # test = fixture mail | gmail = vrai Gmail (lecture seule)
    github_source: str = "test"          # test = dépôts synthétiques | github = vrai GitHub (lecture seule)
    servers: tuple[str, ...] = SERVEURS_CONNUS   # serveurs MCP lancés (sous-ensemble de calendar, mail, github)
    defenses: str = "toutes"             # toutes | aucune | registre
    demo: bool = False                   # True = modèle simulé, sans Ollama
    llm_spec: str | None = None          # sinon variable SYNAPSE_LLM
    allowed_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1")
    audit_path: Path | None = ROOT / "data" / "private" / "audit.jsonl"

    def __post_init__(self):
        if self.source not in ("test", "google"):
            raise ValueError(f"source inconnue : {self.source}")
        if self.mail_source not in ("test", "gmail"):
            raise ValueError(f"mail_source inconnue : {self.mail_source}")
        if self.github_source not in ("test", "github"):
            raise ValueError(f"github_source inconnue : {self.github_source}")
        self.servers = lire_serveurs(self.servers)      # ValueError claire si vide ou inconnu
        if self.defenses not in DEFENSE_PRESETS:
            raise ValueError(f"défenses inconnues : {self.defenses}")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(source=os.getenv("SYNAPSE_SOURCE", "test"),
                   mail_source=os.getenv("SYNAPSE_MAIL_SOURCE", "test"),
                   github_source=os.getenv("SYNAPSE_GITHUB_SOURCE", "test"),
                   servers=os.getenv("SYNAPSE_SERVERS", ",".join(SERVEURS_CONNUS)),
                   defenses=os.getenv("SYNAPSE_DEFENSES", "toutes"),
                   demo=os.getenv("SYNAPSE_DEMO", "0") == "1")

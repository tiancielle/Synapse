"""Configuration du backend API (tout est local : l'API n'écoute que sur 127.0.0.1)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agent.runtime import DEFENSE_PRESETS, ROOT   # noqa: F401 (réexportés : run_api.py et l'API les importent d'ici)


@dataclass
class Settings:
    source: str = "test"                 # test = données fictives | google = vrai Google Calendar (lecture seule)
    mail_source: str = "test"            # test = fixture mail | gmail = vrai Gmail (lecture seule)
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
        if self.defenses not in DEFENSE_PRESETS:
            raise ValueError(f"défenses inconnues : {self.defenses}")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(source=os.getenv("SYNAPSE_SOURCE", "test"),
                   mail_source=os.getenv("SYNAPSE_MAIL_SOURCE", "test"),
                   defenses=os.getenv("SYNAPSE_DEFENSES", "toutes"),
                   demo=os.getenv("SYNAPSE_DEMO", "0") == "1")

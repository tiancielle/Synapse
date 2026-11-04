"""Configuration du backend API (tout est local : l'API n'écoute que sur 127.0.0.1)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agent.firewall import DefenseConfig

ROOT = Path(__file__).resolve().parent.parent

DEFENSE_PRESETS = {
    "toutes": DefenseConfig(),
    "aucune": DefenseConfig.baseline(),
    "registre": DefenseConfig(use_registry=True, require_confirmation=True, scan_results=False, hardened_prompt=False),
}


@dataclass
class Settings:
    source: str = "test"                 # test = données fictives | google = vrai Google Calendar (lecture seule)
    defenses: str = "toutes"             # toutes | aucune | registre
    demo: bool = False                   # True = modèle simulé, sans Ollama
    llm_spec: str | None = None          # sinon variable SYNAPSE_LLM
    allowed_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1")
    audit_path: Path | None = ROOT / "data" / "private" / "audit.jsonl"

    def __post_init__(self):
        if self.source not in ("test", "google"):
            raise ValueError(f"source inconnue : {self.source}")
        if self.defenses not in DEFENSE_PRESETS:
            raise ValueError(f"défenses inconnues : {self.defenses}")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(source=os.getenv("SYNAPSE_SOURCE", "test"),
                   defenses=os.getenv("SYNAPSE_DEFENSES", "toutes"),
                   demo=os.getenv("SYNAPSE_DEMO", "0") == "1")
"""Pare-feu v1 : décisions de risque + nettoyage des résultats d'outils + journal d'audit.

Chaque couche est activable séparément (DefenseConfig) pour mener une étude d'ablation.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.registry import Decision, policy_for

REDACTED = "[contenu retiré par le pare-feu : injection probable]"

# (nom, motif) : heuristiques FR/EN. Volontairement précises pour limiter les faux positifs.
INJECTION_PATTERNS: list[tuple[str, str]] = [
    ("override", r"ignore\s+(toutes?\s+)?(tes\s+|vos\s+|les\s+)?instructions"),
    ("override", r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions"),
    ("override", r"oublie\s+(tes|toutes)\s+(instructions|consignes)"),
    ("override", r"disregard\s+(all\s+)?(previous|prior)"),
    ("secrecy", r"ne\s+(mentionne|dis|r[ée]v[èe]le)\s+(rien|pas)\b.{0,40}utilisateur"),
    ("secrecy", r"(do\s+not|don't)\s+(tell|mention|reveal)\b.{0,40}user"),
    ("exfiltration", r"(envoie|transf[èe]re|exp[ée]die|send|forward|email)\b.{0,60}(int[ée]gralit[ée]|tous?\s+(les|mes)|all|entire|full)\b.{0,80}@"),
    ("fake_authority", r"avis\s+syst[èe]me|message\s+du\s+syst[èe]me|system\s+(notice|message|override)"),
]
_COMPILED = [(n, re.compile(p, re.IGNORECASE | re.DOTALL)) for n, p in INJECTION_PATTERNS]


@dataclass
class DefenseConfig:
    use_registry: bool = True          # politique de risque par outil (sinon : tout est autorisé)
    require_confirmation: bool = True  # confirmation humaine pour le niveau SENSITIVE
    scan_results: bool = True          # détection d'injection dans les résultats d'outils
    hardened_prompt: bool = True       # consigne « données externes = non fiables » dans le prompt

    @classmethod
    def baseline(cls) -> "DefenseConfig":
        return cls(False, False, False, False)


@dataclass
class Verdict:
    decision: Decision
    reason: str


def detect_injection(text: str) -> list[str]:
    return sorted({name for name, rx in _COMPILED if rx.search(text)})


def sanitize(obj, findings: list[str]):
    """Parcourt récursivement un résultat JSON ; remplace les chaînes suspectes."""
    if isinstance(obj, str):
        hits = detect_injection(obj)
        if hits:
            findings.extend(hits)
            return REDACTED
        return obj
    if isinstance(obj, list):
        return [sanitize(x, findings) for x in obj]
    if isinstance(obj, dict):
        return {k: sanitize(v, findings) for k, v in obj.items()}
    return obj


class Firewall:
    def __init__(self, config: DefenseConfig | None = None, audit_path: Path | None = None):
        self.config = config or DefenseConfig()
        self.audit: list[dict] = []
        self.audit_path = Path(audit_path) if audit_path else None

    def check_call(self, server: str, tool: str, args: dict) -> Verdict:
        if not self.config.use_registry:
            return Verdict(Decision.AUTO, "aucune politique (baseline)")
        policy = policy_for(server, tool)
        decision = policy.decision
        if decision is Decision.CONFIRM and not self.config.require_confirmation:
            return Verdict(Decision.AUTO, "confirmation désactivée")
        reasons = {
            Decision.AUTO: "lecture",
            Decision.NOTIFY: "écriture réversible",
            Decision.CONFIRM: "action sensible : confirmation humaine requise",
            Decision.DENY: "outil non autorisé" if policy.scope == "unregistered" else "action interdite",
        }
        return Verdict(decision, reasons[decision])

    def scan_result(self, raw):
        if not self.config.scan_results:
            return raw, []
        findings: list[str] = []
        clean = sanitize(raw, findings)
        return clean, sorted(set(findings))

    def log(self, **entry) -> None:
        entry = {"ts": round(time.time(), 3), **entry}
        self.audit.append(entry)
        if self.audit_path:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

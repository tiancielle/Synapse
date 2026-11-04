"""Traduit les mises à jour du graphe LangGraph en événements simples pour l'interface."""
from __future__ import annotations


class EventTranslator:
    def __init__(self, firewall):
        self.fw = firewall
        self.seen = len(firewall.audit)     # n'annonce que les nouvelles entrées d'audit

    def translate(self, node: str, update: dict | None) -> list[dict]:
        update = update or {}
        events: list[dict] = []
        if node == "plan":
            events.append({"type": "plan", "text": update.get("plan", "")})
        elif node == "act":
            for tc in getattr(update["messages"][-1], "tool_calls", None) or []:
                events.append({"type": "tool_call", "id": tc["id"], "name": tc["name"], "args": tc["args"]})
        elif node == "gate":
            for p in update.get("pending", []):
                events.append({"type": "firewall", "tool": p["name"], "decision": p["decision"],
                               "reason": p["reason"], "approved": p["approved"]})
        elif node == "tools":
            for entry in self.fw.audit[self.seen:]:
                events.append({"type": "tool_result", "tool": entry["tool"], "outcome": entry["outcome"]})
                if entry["findings"]:
                    events.append({"type": "alert", "tool": entry["tool"], "findings": entry["findings"]})
            self.seen = len(self.fw.audit)
            for m in update.get("messages", []):
                if str(m.content).startswith('{"erreur"'):
                    events.append({"type": "tool_error", "tool": m.name,
                                   "message": "L'outil a échoué (détails dans les journaux du serveur)."})
        elif node == "verify":
            events.append({"type": "verify", "ok": bool(update.get("verified"))})
        return events
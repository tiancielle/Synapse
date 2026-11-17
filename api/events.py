"""Traduit les mises à jour du graphe LangGraph en événements simples pour l'interface."""
from __future__ import annotations

from langchain_core.messages import AIMessageChunk

from agent.tools import split_name


def _texte(content) -> str:
    """Texte d'un chunk : chaîne simple, ou liste de blocs (on ne garde que les blocs « text »)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def translate_message_chunk(chunk, metadata: dict | None) -> dict | None:
    """Morceau de la réponse finale -> événement `token`, ou None s'il ne faut rien envoyer.

    On ne garde que le nœud « act » (pas le planificateur ni le vérificateur) et que du texte
    (pas les morceaux d'appel d'outil). Un message complet non streamé (modèle simulé, modèle sans
    streaming) n'est pas un morceau : on l'ignore, `final` porte déjà ce texte.
    """
    if (metadata or {}).get("langgraph_node") != "act":
        return None
    if not isinstance(chunk, AIMessageChunk):
        return None
    if getattr(chunk, "tool_call_chunks", None):
        return None
    texte = _texte(getattr(chunk, "content", ""))
    return {"type": "token", "text": texte} if texte else None


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
                server, name = split_name(tc["name"])      # le modèle voit « serveur__outil » ; le front reçoit les deux séparés
                events.append({"type": "tool_call", "id": tc["id"], "server": server, "name": name, "args": tc["args"]})
        elif node == "gate":
            for p in update.get("pending", []):
                events.append({"type": "firewall", "server": p["server"], "tool": p["name"], "decision": p["decision"],
                               "reason": p["reason"], "approved": p["approved"]})
        elif node == "tools":
            for entry in self.fw.audit[self.seen:]:
                server = entry.get("server")
                events.append({"type": "tool_result", "server": server, "tool": entry["tool"], "outcome": entry["outcome"]})
                if entry["outcome"] == "error":
                    events.append({"type": "tool_error", "server": server, "tool": entry["tool"],
                                   "message": "L'outil a échoué (détails dans les journaux du serveur)."})
                if entry["findings"]:
                    events.append({"type": "alert", "server": server, "tool": entry["tool"], "findings": entry["findings"]})
            self.seen = len(self.fw.audit)
        elif node == "verify":
            events.append({"type": "verify", "ok": bool(update.get("verified"))})
        return events
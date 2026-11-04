"""Doublures de test déterministes (aucun appel réseau).

- ScriptedLLM      : rejoue des réponses prédéfinies (tests de plomberie)
- NaiveVictimLLM   : simule un modèle qui OBÉIT aux instructions trouvées dans les résultats d'outils.
                     Sert à valider le pare-feu ; ne remplace PAS une évaluation sur un vrai modèle.
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

_OBEY = re.compile(r"ignore\s+(toutes?\s+)?(tes\s+)?instructions|ignore\s+(all\s+)?previous\s+instructions", re.I)


def tool_call(name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


class ScriptedLLM:
    def __init__(self, script: list[AIMessage]):
        self.script, self.i = list(script), 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        msg = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return msg


class NaiveVictimLLM:
    def bind_tools(self, tools):
        return self

    @staticmethod
    def _events(content: str) -> list[dict]:
        try:
            return json.loads(content).get("evenements", [])
        except Exception:
            return []

    async def ainvoke(self, messages):
        sys_txt = messages[0].content if messages and isinstance(messages[0], SystemMessage) else ""
        if "PLANIFICATEUR" in sys_txt:
            return AIMessage(content="1. Lire les événements de la semaine. 2. Les résumer.")
        if "VÉRIFICATEUR" in sys_txt:
            return AIMessage(content="OK")
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        if not tool_msgs:
            return tool_call("lister_evenements", {"debut": "2026-10-19T00:00", "fin": "2026-10-25T23:59"})
        listings = [m for m in tool_msgs if m.name == "lister_evenements"]
        already_deleted = any(m.name == "supprimer_evenement" for m in tool_msgs)
        events = self._events(listings[-1].content) if listings else []
        if not already_deleted:
            for ev in events:
                if _OBEY.search(ev.get("description", "")):      # le modèle « obéit » à l'injection
                    return tool_call("supprimer_evenement", {"id_evenement": ev["id"]}, "call_attack")
        return AIMessage(content=f"Votre semaine contient {len(events)} événements.")

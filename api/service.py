"""Service qui fait tourner l'agent et produit un flux d'événements (utilisé par l'API et testable seul)."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from api.events import EventTranslator


class AgentService:
    def __init__(self, graph, firewall):
        self.graph = graph
        self.fw = firewall
        self.waiting: dict[str, dict] = {}      # session -> confirmation en attente
        self.lock = asyncio.Lock()              # une exécution à la fois (une seule session MCP)

    async def run(self, session_id: str, message: str) -> AsyncIterator[dict]:
        entree = {"messages": [HumanMessage(message)], "plan": "", "pending": [],
                  "iterations": 0, "retries": 0, "verified": False}
        async for event in self._stream(entree, session_id):
            yield event

    async def resume(self, session_id: str, approved: bool) -> AsyncIterator[dict]:
        async for event in self._stream(Command(resume={"approved": approved}), session_id):
            yield event

    async def _stream(self, entree, session_id: str) -> AsyncIterator[dict]:
        cfg = {"configurable": {"thread_id": session_id}}
        translator = EventTranslator(self.fw)
        interruption = None
        async for chunk in self.graph.astream(entree, cfg, stream_mode="updates"):
            for node, update in chunk.items():
                if node == "__interrupt__":
                    interruption = update[0].value
                else:
                    for event in translator.translate(node, update):
                        yield event

        if interruption is not None:
            self.waiting[session_id] = interruption
            yield {"type": "confirmation_required", **interruption}
            yield {"type": "done", "status": "waiting_confirmation"}
            return

        state = await self.graph.aget_state(cfg)
        final = next((m for m in reversed(state.values["messages"])
                      if isinstance(m, AIMessage) and not m.tool_calls), None)
        yield {"type": "final", "text": final.content if final else "(pas de réponse : limite d'itérations atteinte)"}
        yield {"type": "done", "status": "completed"}
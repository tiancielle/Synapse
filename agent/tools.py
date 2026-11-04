"""Pont entre l'agent et un serveur MCP (session persistante, transport stdio)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client


class Toolbox:
    """À utiliser avec `async with` dans UNE SEULE cellule/tâche."""

    def __init__(self, server_name: str, script: Path, env: dict | None = None, log_path: Path | None = None):
        self.server_name = server_name
        self.script = Path(script)
        self.env = env
        self.log_path = Path(log_path) if log_path else None
        self.calls: list[tuple[str, dict]] = []   # trace des appels réellement envoyés au serveur

    async def __aenter__(self):
        params = StdioServerParameters(command=sys.executable, args=[str(self.script)], env=self.env)
        self._log = open(self.log_path or os.devnull, "w")
        self._cm = Client(stdio_client(params, errlog=self._log))
        self.client = await self._cm.__aenter__()
        self.tools = (await self.client.list_tools()).tools
        self.specs = [{"name": t.name, "description": t.description, "parameters": t.input_schema} for t in self.tools]
        return self

    async def __aexit__(self, *exc):
        await self._cm.__aexit__(*exc)
        self._log.close()

    async def call(self, name: str, args: dict) -> dict:
        self.calls.append((name, args))
        result = await self.client.call_tool(name, args)
        text = result.content[0].text if result.content else ""
        if result.is_error:
            return {"erreur": text}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"texte": text}

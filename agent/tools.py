"""Pont entre l'agent et un ou plusieurs serveurs MCP (sessions persistantes, transport stdio)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client


SEP = "__"      # séparateur serveur/outil dans les noms vus par le modèle : calendar__lister_evenements


def split_name(name: str) -> tuple[str | None, str]:
    """« calendar__lister_evenements » -> ("calendar", "lister_evenements") ; sans préfixe -> (None, nom)."""
    serveur, sep, outil = name.partition(SEP)
    return (serveur, outil) if sep else (None, name)


class Toolbox:
    """Un serveur MCP. À utiliser avec `async with` dans UNE SEULE cellule/tâche."""

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

    def resolve(self, name: str) -> tuple[str, str] | None:
        """(serveur, outil) pour un nom d'outil vu par le modèle. Un seul serveur : pas de préfixe."""
        return self.server_name, name

    async def call_checked(self, name: str, args: dict) -> tuple[bool, dict]:
        """Appelle un outil et renvoie (réussi, résultat). Un échec ne lève jamais d'exception :
        l'agent et le journal d'audit doivent pouvoir le distinguer d'un appel réussi."""
        self.calls.append((name, args))
        try:
            result = await self.client.call_tool(name, args)
        except Exception:                      # serveur arrêté, protocole cassé...
            return False, {"erreur": "Échec de la communication avec le serveur d'outils."}
        text = result.content[0].text if result.content else ""
        if result.is_error:
            return False, {"erreur": text}
        try:
            return True, json.loads(text)
        except json.JSONDecodeError:
            return True, {"texte": text}

    async def call(self, name: str, args: dict) -> dict:
        """Version simple (résultat seul), conservée pour les notebooks et les tests existants."""
        return (await self.call_checked(name, args))[1]


class MultiToolbox:
    """Plusieurs serveurs MCP derrière une seule interface. Le modèle voit des noms préfixés
    (`serveur__outil`) : pas de collision possible, et chaque appel est rattaché à son serveur
    avant que le pare-feu ne le juge. Les Toolbox doivent déjà être ouvertes (voir open_runtime)."""

    def __init__(self, toolboxes: dict[str, Toolbox]):
        for nom in toolboxes:
            if SEP in nom:
                raise ValueError(f"Nom de serveur invalide (contient « {SEP} ») : {nom}")
        self.toolboxes = dict(toolboxes)
        self.specs = [{**spec, "name": f"{serveur}{SEP}{spec['name']}"}
                      for serveur, tb in self.toolboxes.items() for spec in tb.specs]
        self.calls: list[tuple[str, dict]] = []   # trace des appels réellement envoyés (noms préfixés)

    def resolve(self, name: str) -> tuple[str, str] | None:
        """(serveur, outil) si ce nom préfixé correspond à un outil réellement exposé, sinon None."""
        serveur, outil = split_name(name)
        tb = self.toolboxes.get(serveur) if serveur else None
        if tb is not None and any(spec["name"] == outil for spec in tb.specs):
            return serveur, outil
        return None

    async def call_checked(self, name: str, args: dict) -> tuple[bool, dict]:
        cible = self.resolve(name)
        if cible is None:
            return False, {"erreur": "Outil inconnu."}
        self.calls.append((name, args))
        serveur, outil = cible
        return await self.toolboxes[serveur].call_checked(outil, args)

    async def call(self, name: str, args: dict) -> dict:
        return (await self.call_checked(name, args))[1]
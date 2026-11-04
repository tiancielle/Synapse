from datetime import datetime
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("hello-synapse")


@mcp.tool()
def donner_heure(fuseau: str = "Africa/Casablanca") -> str:
    """Donne la date et l'heure actuelles dans un fuseau horaire.
    Exemples de fuseaux : Africa/Casablanca, Europe/Paris, America/New_York."""
    return datetime.now(ZoneInfo(fuseau)).strftime("%A %d %B %Y, %H:%M:%S")


@mcp.tool()
def dire_bonjour(nom: str, langue: str = "fr") -> str:
    """Salue une personne par son prénom, en français (fr) ou en anglais (en)."""
    return f"Hello {nom} !" if langue == "en" else f"Bonjour {nom} !"


if __name__ == "__main__":
    mcp.run()  # démarre le serveur en mode stdio

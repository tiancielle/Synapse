"""Lance l'API Tandem en local (127.0.0.1 uniquement).

    python run_api.py                    -> modèle défini par SYNAPSE_LLM (.env), données de test
    python run_api.py --demo             -> modèle simulé, sans Ollama
    python run_api.py --source google    -> vrai Google Calendar (lecture seule)
    python run_api.py --mail-source gmail -> vrai Gmail (lecture seule, après connect_gmail.py)
    python run_api.py --github-source github -> vrai GitHub (lecture seule, liste blanche + secrets/github_token)
    python run_api.py --servers github   -> ne lance que le serveur GitHub (aussi : SYNAPSE_SERVERS)
    python run_api.py --defenses aucune  -> sans défense (pour comparer)
"""
import argparse
import os

import uvicorn

from api.main import create_app
from api.settings import DEFENSE_PRESETS, SERVEURS_CONNUS, Settings, lire_serveurs


def main():
    parser = argparse.ArgumentParser(description="API locale Tandem")
    parser.add_argument("--demo", action="store_true", help="modèle simulé (sans Ollama)")
    parser.add_argument("--source", choices=["test", "google"], default="test")
    parser.add_argument("--mail-source", choices=["test", "gmail"], default="test",
                        help="test = mails fictifs ; gmail = vrai Gmail (lecture seule)")
    parser.add_argument("--github-source", choices=["test", "github"], default="test",
                        help="test = dépôts fictifs ; github = vrai GitHub (lecture seule)")
    parser.add_argument("--servers", default=os.getenv("SYNAPSE_SERVERS", ",".join(SERVEURS_CONNUS)),
                        help="serveurs à lancer, séparés par des virgules (calendar,mail,github ; défaut : tous)")
    parser.add_argument("--defenses", choices=list(DEFENSE_PRESETS), default="toutes")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        servers = lire_serveurs(args.servers)
    except ValueError as erreur:
        parser.error(str(erreur))                    # message clair, code de sortie 2
    app = create_app(Settings(source=args.source, mail_source=args.mail_source, github_source=args.github_source,
                              servers=servers, defenses=args.defenses, demo=args.demo))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")   # pas de --reload : incompatible avec nos sous-processus sous Windows


if __name__ == "__main__":
    main()
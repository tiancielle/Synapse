"""Connexion unique à Gmail (lecture seule). À lancer UNE fois :  python connect_gmail.py

Prérequis : secrets/credentials.json (même fichier que pour le calendrier).
Une page Google s'ouvre dans le navigateur ; connecte-toi avec le compte de TEST
et accepte UNIQUEMENT la permission de lecture Gmail.
Le jeton est enregistré dans secrets/token_gmail.json (séparé du calendrier).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "servers"))

from google_auth import SCOPES_GMAIL_READONLY, default_paths, get_credentials  # noqa: E402


def main():
    credentials_path, token_path = default_paths("gmail")
    if not credentials_path.exists():
        print(
            f"Fichier introuvable : {credentials_path}\n"
            "Télécharge-le depuis la console Google Cloud et place-le dans secrets/."
        )
        sys.exit(1)
    print(
        "Une page Google va s'ouvrir. Connecte-toi avec le compte de test "
        "et accepte la lecture seule de Gmail."
    )
    creds = get_credentials(
        SCOPES_GMAIL_READONLY,
        credentials_path,
        token_path,
        interactive=True,
        reconnect_hint="python connect_gmail.py",
    )

    from googleapiclient.discovery import build

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profil = service.users().getProfile(userId="me").execute()
    adresse = profil.get("emailAddress") or "(adresse non fournie par l'API)"
    print(f"Connecté. Compte Gmail : {adresse}")
    print(f"Jeton enregistré dans {token_path} (ne le partage jamais).")


if __name__ == "__main__":
    main()

"""Connexion unique à Google Calendar (lecture seule). À lancer UNE fois :  python connect_google.py

Prérequis : secrets/credentials.json (téléchargé depuis la console Google Cloud).
Une page Google s'ouvre dans le navigateur ; connecte-toi avec le compte de TEST et accepte la permission de lecture.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "servers"))

from google_auth import SCOPES_CALENDAR_READONLY, default_paths, get_credentials  # noqa: E402


def main():
    credentials_path, token_path = default_paths("calendar")
    if not credentials_path.exists():
        print(f"Fichier introuvable : {credentials_path}\nTélécharge-le depuis la console Google Cloud et place-le dans secrets/.")
        sys.exit(1)
    print("Une page Google va s'ouvrir. Connecte-toi avec le compte de test et accepte la lecture du calendrier.")
    creds = get_credentials(SCOPES_CALENDAR_READONLY, credentials_path, token_path, interactive=True)

    from googleapiclient.discovery import build
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    calendrier = service.calendars().get(calendarId="primary").execute()
    print(f"Connecté. Calendrier : {calendrier.get('summary')} | fuseau : {calendrier.get('timeZone')}")
    print(f"Jeton enregistré dans {token_path} (ne le partage jamais).")


if __name__ == "__main__":
    main()
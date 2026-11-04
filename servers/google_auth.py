"""Authentification Google (OAuth « application de bureau »).

- Les secrets vivent dans secrets/ (ignoré par Git) : credentials.json (fourni par Google) et token_*.json (créé à la connexion).
- Le serveur MCP n'ouvre JAMAIS de page de connexion (interactive=False) : la connexion se fait une fois avec connect_google.py.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "secrets"

# Permissions minimales : lecture seule du calendrier.
SCOPES_CALENDAR_READONLY = ["https://www.googleapis.com/auth/calendar.readonly"]


def default_paths(name: str) -> tuple[Path, Path]:
    return SECRETS / "credentials.json", SECRETS / f"token_{name}.json"


def get_credentials(scopes: list[str], credentials_path: Path, token_path: Path, interactive: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = Path(token_path)
    creds = Credentials.from_authorized_user_file(str(token_path), scopes) if token_path.exists() else None

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            creds = None            # jeton révoqué ou expiré : il faut se reconnecter

    if not interactive:
        raise RuntimeError("Connexion Google absente ou expirée : lance d'abord  python connect_google.py")

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
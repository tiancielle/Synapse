"""Backends du serveur mail : même format de sortie, implémentations interchangeables.

- FixtureMailBackend : données synthétiques (tests, évaluation, démo hors-ligne)
- GmailMailBackend  : vrai Gmail, LECTURE SEULE (aucune méthode d'écriture)

Les deux backends acceptent les mêmes filtres de recherche (voir mail_filters.py) : expéditeur, sujet,
bornes de date et d'heure, non lus, mots-clés.
Les clés commençant par _ dans la fixture sont des étiquettes d'évaluation :
elles ne sont JAMAIS renvoyées par les outils.
Les écritures fixture (brouillons, envois) ne touchent aucune vraie boîte.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime, tzinfo
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

from mail_filters import LIMITE_DEFAUT, construire_filtres, correspond, date_locale, lire_date_fixture, requete_gmail


def _public(mail: dict) -> dict:
    """Retire les étiquettes d'évaluation (clés _)."""
    return {k: v for k, v in mail.items() if not k.startswith("_")}


def _apercu(texte: str, n: int = 140) -> str:
    texte = " ".join(texte.split())
    return texte if len(texte) <= n else texte[: n - 1] + "…"


class FixtureMailBackend:
    def __init__(self, fixture_path: Path, state_path: Path | None = None):
        data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        self.accounts: list[str] = data["accounts"]
        self.mails: list[dict] = data["mails"]
        self.state_path = Path(state_path) if state_path else None
        self.drafts: list[dict] = []
        self.sent: list[dict] = []
        if self.state_path and self.state_path.exists():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.drafts, self.sent = state["brouillons"], state["envoyes"]

    def _save(self) -> None:
        if self.state_path:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps({"brouillons": self.drafts, "envoyes": self.sent},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")

    def _check_account(self, compte: str, required: bool) -> None:
        if not compte:
            if required:
                raise ValueError(f"Compte obligatoire. Comptes disponibles : {', '.join(self.accounts)}")
            return
        if compte not in self.accounts:
            raise ValueError(f"Compte inconnu : {compte}. Comptes disponibles : {', '.join(self.accounts)}")

    @staticmethod
    def _check_message(destinataire: str, sujet: str) -> None:
        if "@" not in destinataire or any(c.isspace() for c in destinataire):
            raise ValueError("Adresse du destinataire invalide")
        if not sujet.strip():
            raise ValueError("Le sujet ne peut pas être vide")

    def search(self, query: str = "", account: str = "", limit: int = LIMITE_DEFAUT, *, expediteur: str = "",
               sujet: str = "", depuis: str = "", jusqu_a: str = "", non_lus: bool = False) -> list[dict]:
        """Mails les plus récents d'abord, filtrés. Sans filtre : les plus récents (du compte si précisé)."""
        self._check_account(account, required=False)
        f = construire_filtres(requete=query, expediteur=expediteur, sujet=sujet, depuis=depuis,
                               jusqu_a=jusqu_a, non_lus=non_lus, limite=limit)
        hits = [m for m in self.mails
                if (not account or m["compte"] == account)
                and correspond(f, de=m["de"], sujet=m["sujet"], texte=m["corps"],
                               date=lire_date_fixture(m["date"]), lu=m["lu"])]
        hits.sort(key=lambda m: m["date"], reverse=True)
        return [{"id": m["id"], "compte": m["compte"], "de": m["de"], "sujet": m["sujet"],
                 "date": m["date"], "lu": m["lu"], "apercu": _apercu(m["corps"])} for m in hits[:f.limite]]

    def read(self, mail_id: str) -> dict:
        for m in self.mails:
            if m["id"] == mail_id:
                return _public(m)
        raise ValueError(f"Mail introuvable : {mail_id}")

    def create_draft(self, compte: str, a: str, sujet: str, corps: str) -> dict:
        self._check_account(compte, required=True)
        self._check_message(a, sujet)
        draft = {"id": f"brouillon_{len(self.drafts) + 1:03d}", "compte": compte, "a": a, "sujet": sujet, "corps": corps}
        self.drafts.append(draft)
        self._save()
        return draft

    def send(self, compte: str, a: str, sujet: str, corps: str) -> dict:
        self._check_account(compte, required=True)
        self._check_message(a, sujet)
        mail = {"id": f"envoye_{len(self.sent) + 1:03d}", "compte": compte, "a": a, "sujet": sujet, "corps": corps}
        self.sent.append(mail)
        self._save()
        return mail


# --- Gmail lecture seule --------------------------------------------------------------------

# Plafond du corps renvoyé à l'agent (caractères). Configurable ; 4000 convient à num_ctx=8192.
MAX_BODY_CHARS = 4000


class _HtmlToText(HTMLParser):
    """Convertit du HTML en texte brut sans aucune récupération de ressource distante."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignore = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "noscript"):
            self._ignore += 1
        elif tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"):
            self._parts.append("\n")
        # img / link / source : balises ignorées, aucun attribut (src, href) n'est suivi

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "noscript") and self._ignore:
            self._ignore -= 1
        elif tag in ("p", "div", "li", "tr"):
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._ignore:
            self._parts.append(data)

    def text(self) -> str:
        return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", "".join(self._parts))).strip()


def _html_to_text(html: str) -> str:
    parser = _HtmlToText()
    parser.feed(html)
    parser.close()
    return parser.text()


def _b64url_decode(data: str) -> str:
    """Décode body.data Gmail (base64 URL-safe, padding souvent absent)."""
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + pad).decode("utf-8", errors="replace")


def _header(headers: list[dict] | None, name: str) -> str:
    cible = name.lower()
    for h in headers or []:
        if str(h.get("name", "")).lower() == cible:
            return str(h.get("value") or "")
    return ""


def _date_du_mail(headers: list[dict] | None, internal_date, tz: tzinfo | None) -> datetime | None:
    """Date de RÉCEPTION en heure locale (sans fuseau). On préfère internalDate (fiable, en UTC), converti
    dans le fuseau de l'utilisateur ; repli sur l'en-tête Date, converti de la même façon."""
    dt = date_locale(internal_date, tz)
    if dt is not None:
        return dt
    raw = _header(headers, "Date")
    if raw:
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(tz)          # tz=None : fuseau de la machine
            return parsed.replace(tzinfo=None)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
    return None


def _iso(dt: datetime | None) -> str:
    """Format commun aux deux backends : « YYYY-MM-DDTHH:MM »."""
    return dt.strftime("%Y-%m-%dT%H:%M") if dt else ""


def _part_est_piece_jointe(part: dict) -> bool:
    body = part.get("body") or {}
    if body.get("attachmentId"):
        return True
    if part.get("filename"):
        return True
    return False


def _collect_text_parts(part: dict, plains: list[str], htmls: list[str]) -> None:
    """Parcourt le payload MIME ; ignore les pièces jointes ; ne suit aucun lien."""
    if _part_est_piece_jointe(part):
        return
    mime = (part.get("mimeType") or "").lower()
    data = (part.get("body") or {}).get("data")
    if data and mime.startswith("text/plain"):
        plains.append(_b64url_decode(data))
    elif data and mime.startswith("text/html"):
        htmls.append(_b64url_decode(data))
    for child in part.get("parts") or []:
        _collect_text_parts(child, plains, htmls)


def _extract_corps(payload: dict | None) -> str:
    plains: list[str] = []
    htmls: list[str] = []
    if payload:
        _collect_text_parts(payload, plains, htmls)
    if plains:
        texte = "\n".join(plains)
    elif htmls:
        texte = _html_to_text("\n".join(htmls))
    else:
        texte = ""
    if len(texte) > MAX_BODY_CHARS:
        return texte[: MAX_BODY_CHARS - 1] + "…"
    return texte


def _http_error_status(exc) -> int | None:
    resp = getattr(exc, "resp", None)
    if resp is None:
        return None
    try:
        return int(resp.status)
    except (TypeError, ValueError):
        return None


class GmailMailBackend:
    """Gmail en lecture seule (palier 1). Aucune méthode create_draft / send.

    `service` : client googleapiclient (injecté en tests ; sinon OAuth lecture seule).
    `tz` : fuseau de l'utilisateur pour les dates et les filtres (None = fuseau de la machine).
    Ne journalise jamais le contenu des mails.
    """

    def __init__(self, service=None, tz: tzinfo | None = None):
        self._service = service
        self._tz = tz
        self.accounts: list[str] = ["gmail"]

    @property
    def service(self):
        if self._service is None:
            from google_auth import SCOPES_GMAIL_READONLY, default_paths, get_credentials
            from googleapiclient.discovery import build

            credentials_path, token_path = default_paths("gmail")
            creds = get_credentials(
                SCOPES_GMAIL_READONLY,
                credentials_path,
                token_path,
                interactive=False,
                reconnect_hint="python connect_gmail.py",
            )
            self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    def _check_account(self, compte: str) -> None:
        if not compte:
            return
        if compte not in self.accounts:
            raise ValueError(f"Compte inconnu : {compte}. Comptes disponibles : {', '.join(self.accounts)}")

    def _execute(self, request, *, mail_id: str | None = None):
        """Exécute un appel Gmail ; messages d'erreur sans aucun contenu de mail."""
        from google.auth.exceptions import RefreshError
        from googleapiclient.errors import HttpError

        try:
            return request.execute()
        except RefreshError as exc:
            raise RuntimeError(
                "Accès Gmail expiré ou révoqué : relance python connect_gmail.py"
            ) from exc
        except HttpError as exc:
            status = _http_error_status(exc)
            if status == 404 and mail_id is not None:
                raise ValueError(f"Mail introuvable : {mail_id}") from exc
            raise RuntimeError(
                "Échec de l'accès à Gmail. Réessaie plus tard ou relance : python connect_gmail.py"
            ) from exc

    def _get_message(self, mail_id: str, *, format: str, metadata_headers: list[str] | None = None) -> dict:
        kwargs = {"userId": "me", "id": mail_id, "format": format}
        if metadata_headers is not None:
            kwargs["metadataHeaders"] = metadata_headers
        return self._execute(self.service.users().messages().get(**kwargs), mail_id=mail_id)

    def search(self, query: str = "", account: str = "", limit: int = LIMITE_DEFAUT, *, expediteur: str = "",
               sujet: str = "", depuis: str = "", jusqu_a: str = "", non_lus: bool = False) -> list[dict]:
        """Recherche Gmail avec les mêmes filtres que le backend de test. Les filtres sont envoyés à Gmail
        (from:, subject:, after:, before:, is:unread) PUIS revérifiés ici sur la date exacte de réception."""
        self._check_account(account)
        f = construire_filtres(requete=query, expediteur=expediteur, sujet=sujet, depuis=depuis,
                               jusqu_a=jusqu_a, non_lus=non_lus, limite=limit)
        kwargs: dict = {"userId": "me", "maxResults": f.limite}
        q = requete_gmail(f, self._tz)
        if q:
            kwargs["q"] = q
        listed = self._execute(self.service.users().messages().list(**kwargs))
        out = []
        for stub in listed.get("messages") or []:
            mid = stub["id"]
            # metadata seulement : pas de corps (le corps est lu uniquement par read)
            msg = self._get_message(
                mid, format="metadata", metadata_headers=["From", "Subject", "Date"]
            )
            headers = (msg.get("payload") or {}).get("headers")
            lu = "UNREAD" not in (msg.get("labelIds") or [])
            apercu = msg.get("snippet") or ""
            date = _date_du_mail(headers, msg.get("internalDate"), self._tz)
            de, objet = _header(headers, "From"), _header(headers, "Subject")
            if not correspond(f, de=de, sujet=objet, texte=apercu, date=date, lu=lu, verifier_requete=False):
                continue
            out.append({
                "id": mid,
                "compte": "gmail",
                "de": de,
                "sujet": objet,
                "date": _iso(date),
                "lu": lu,
                "apercu": _apercu(apercu),
            })
        return out

    def read(self, mail_id: str) -> dict:
        msg = self._get_message(mail_id, format="full")
        headers = (msg.get("payload") or {}).get("headers")
        labels = msg.get("labelIds") or []
        return {
            "id": mail_id,
            "compte": "gmail",
            "de": _header(headers, "From"),
            "a": _header(headers, "To"),
            "sujet": _header(headers, "Subject"),
            "date": _iso(_date_du_mail(headers, msg.get("internalDate"), self._tz)),
            "corps": _extract_corps(msg.get("payload")),
            "lu": "UNREAD" not in labels,
        }
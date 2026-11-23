"""GmailMailBackend : lecture seule, aucun réseau, faux service imitant l'API Gmail."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httplib2
import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from mail_backend import GmailMailBackend
from google_auth import SCOPES_GMAIL_READONLY


def _b64(texte: str) -> str:
    """Encode comme Gmail : base64url sans padding."""
    return base64.urlsafe_b64encode(texte.encode("utf-8")).decode("ascii").rstrip("=")


class _Exec:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def execute(self):
        if self.error is not None:
            raise self.error
        return self.payload


def _http_error(status: int) -> HttpError:
    return HttpError(
        httplib2.Response({"status": status}),
        b'{"error": {"message": "PRIVATE_HTTP_ERROR_BODY"}}',
    )


class _Messages:
    """Imite users().messages() : list / get (chaîne réelle de googleapiclient)."""

    def __init__(self, by_id: dict[str, dict], *, get_error_status=None, list_error_status=None,
                 get_refresh_error=False):
        self.by_id = by_id
        self.get_error_status = get_error_status
        self.list_error_status = list_error_status
        self.get_refresh_error = get_refresh_error
        self.list_calls: list[dict] = []
        self.get_calls: list[dict] = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        if self.list_error_status is not None:
            return _Exec(error=_http_error(self.list_error_status))
        max_results = int(kwargs.get("maxResults") or 100)
        ids = list(self.by_id.keys())[:max_results]
        return _Exec({"messages": [{"id": i, "threadId": f"t-{i}"} for i in ids]})

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        mid = kwargs["id"]
        if self.get_refresh_error:
            return _Exec(error=RefreshError("PRIVATE_REFRESH_ERROR_CONTENT"))
        if self.get_error_status is not None:
            return _Exec(error=_http_error(self.get_error_status))
        if mid not in self.by_id:
            return _Exec(error=_http_error(404))
        msg = self.by_id[mid]
        fmt = kwargs.get("format", "full")
        if fmt == "metadata":
            # metadata : headers demandés + snippet, sans body.data des parties
            payload = {"headers": (msg.get("payload") or {}).get("headers", [])}
            return _Exec({
                "id": mid,
                "threadId": msg.get("threadId", f"t-{mid}"),
                "labelIds": msg.get("labelIds", []),
                "snippet": msg.get("snippet", ""),
                "internalDate": msg.get("internalDate"),
                "payload": payload,
            })
        return _Exec(msg)


class _Users:
    def __init__(self, messages: _Messages):
        self._messages = messages

    def messages(self):
        return self._messages


class FakeGmailService:
    """Imite service.users().messages().list/get — aucun accès réseau."""

    def __init__(self, by_id: dict[str, dict], *, get_error_status=None, list_error_status=None,
                 get_refresh_error=False):
        self._messages = _Messages(
            by_id, get_error_status=get_error_status, list_error_status=list_error_status,
            get_refresh_error=get_refresh_error,
        )

    def users(self):
        return _Users(self._messages)


def _msg(mid, *, frm="", to="", subject="", date_hdr=None, internal=None,
         labels=None, snippet="", plain=None, html=None, parts=None):
    headers = []
    if frm is not None and frm != "":
        headers.append({"name": "From", "value": frm})
    elif frm == "":
        pass  # absente volontairement
    if to:
        headers.append({"name": "To", "value": to})
    if subject is not None and subject != "":
        headers.append({"name": "Subject", "value": subject})
    if date_hdr:
        headers.append({"name": "Date", "value": date_hdr})
        if internal is None:      # Gmail fournit toujours internalDate : on le déduit de l'en-tête Date
            internal = str(int(parsedate_to_datetime(date_hdr).timestamp() * 1000))

    if parts is not None:
        payload = {"mimeType": "multipart/mixed", "headers": headers, "parts": parts}
    elif plain is not None and html is not None:
        payload = {
            "mimeType": "multipart/alternative",
            "headers": headers,
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64(plain)}},
                {"mimeType": "text/html", "body": {"data": _b64(html)}},
            ],
        }
    elif plain is not None:
        payload = {"mimeType": "text/plain", "headers": headers, "body": {"data": _b64(plain)}}
    elif html is not None:
        payload = {"mimeType": "text/html", "headers": headers, "body": {"data": _b64(html)}}
    else:
        payload = {"mimeType": "text/plain", "headers": headers, "body": {}}

    return {
        "id": mid,
        "threadId": f"t-{mid}",
        "labelIds": labels or [],
        "snippet": snippet,
        "internalDate": internal or "1729080000000",  # 2024-10-16 approx UTC — tests surchargent
        "payload": payload,
    }


def make_backend(messages: list[dict], *, get_error_status=None, list_error_status=None,
                 get_refresh_error=False, tz=timezone.utc):
    """tz=UTC par défaut : les tests ne dépendent pas du fuseau de la machine."""
    by_id = {m["id"]: m for m in messages}
    service = FakeGmailService(
        by_id, get_error_status=get_error_status, list_error_status=list_error_status,
        get_refresh_error=get_refresh_error,
    )
    return GmailMailBackend(service=service, tz=tz), service


def test_search_returns_fixture_shaped_dicts_and_compte_gmail():
    msg = _msg(
        "g1",
        frm="Sara <sara@exemple.test>",
        subject="Déjeuner",
        date_hdr="Thu, 16 Oct 2026 18:20:00 +0000",
        labels=["INBOX", "UNREAD"],
        snippet="On garde vendredi ?",
        plain="On garde vendredi ?",
    )
    backend, service = make_backend([msg])
    hits = backend.search("déjeuner", limit=10)
    assert len(hits) == 1
    hit = hits[0]
    assert set(hit) == {"id", "compte", "de", "sujet", "date", "lu", "apercu"}
    assert hit["compte"] == "gmail" and hit["id"] == "g1"
    assert hit["de"] == "Sara <sara@exemple.test>" and hit["sujet"] == "Déjeuner"
    assert hit["date"] == "2026-10-16T18:20" and hit["lu"] is False
    assert "vendredi" in hit["apercu"]
    assert service._messages.list_calls[-1]["q"] == "déjeuner"
    assert service._messages.list_calls[-1]["maxResults"] == 10


def test_empty_query_lists_without_q_and_caps_limit_at_50():
    backend, service = make_backend([_msg("g1", plain="x", snippet="x")])
    backend.search("", limit=200)
    call = service._messages.list_calls[-1]
    assert "q" not in call
    assert call["maxResults"] == 50


def test_search_uses_metadata_only_and_read_requests_full_message():
    backend, service = make_backend([_msg("g1", plain="corps")])

    backend.search()
    search_get = service._messages.get_calls[-1]
    assert search_get["format"] == "metadata"
    assert search_get["metadataHeaders"] == ["From", "Subject", "Date"]

    backend.read("g1")
    read_get = service._messages.get_calls[-1]
    assert read_get["format"] == "full"
    assert "metadataHeaders" not in read_get


def test_gmail_scope_is_readonly_and_exact():
    assert SCOPES_GMAIL_READONLY == ["https://www.googleapis.com/auth/gmail.readonly"]


def test_read_decodes_base64url_plain_body():
    # padding volontairement absent (comportement Gmail)
    raw = _b64("Bonjour depuis Gmail")
    assert "=" not in raw
    backend, _ = make_backend([_msg("g2", frm="a@b.test", to="moi@exemple.test",
                                    subject="Sujet", plain="Bonjour depuis Gmail",
                                    date_hdr="Fri, 17 Oct 2026 09:00:00 +0000",
                                    labels=["INBOX"])])
    mail = backend.read("g2")
    assert set(mail) == {"id", "compte", "de", "a", "sujet", "date", "corps", "lu"}
    assert mail["corps"] == "Bonjour depuis Gmail"
    assert mail["compte"] == "gmail" and mail["lu"] is True
    assert mail["a"] == "moi@exemple.test" and mail["date"] == "2026-10-17T09:00"


def test_multipart_prefers_text_plain_over_html():
    backend, _ = make_backend([_msg(
        "g3", frm="x@y.test", to="moi@exemple.test", subject="Multi",
        plain="Version texte", html="<p>Version <b>HTML</b></p>",
    )])
    assert backend.read("g3")["corps"] == "Version texte"


def test_html_only_is_converted_to_text_without_tags_or_remote_attrs():
    html = (
        "<html><head><style>body{color:red}</style>"
        "<link rel='stylesheet' href='https://evil.example/x.css'></head>"
        "<body><p>Hello <b>world</b></p>"
        "<img src='https://evil.example/pixel.png' alt='x'>"
        "<script>alert(1)</script></body></html>"
    )
    backend, _ = make_backend([_msg("g4", html=html, subject="Html")])
    corps = backend.read("g4")["corps"]
    assert "Hello" in corps and "world" in corps
    assert "<" not in corps and "alert" not in corps
    assert "color:red" not in corps
    assert "evil.example" not in corps and "pixel" not in corps


def test_hidden_html_text_is_preserved():
    backend, _ = make_backend([
        _msg("g-hidden", html="<p>Visible</p><div style='display:none'>Hidden text</div>")
    ])
    corps = backend.read("g-hidden")["corps"]
    assert "Visible" in corps
    assert "Hidden text" in corps


def test_long_body_is_truncated():
    long = "A" * (4000 + 500)
    backend, _ = make_backend([_msg("g5", plain=long, subject="Long")])
    corps = backend.read("g5")["corps"]
    assert len(corps) == 4000
    assert corps.endswith("…")


def test_missing_from_or_subject_become_empty_strings():
    backend, _ = make_backend([_msg(
        "g6", frm="", subject="", to="moi@exemple.test", plain="corps",
        internal="1729087200000",  # pas de Date header
    )])
    mail = backend.read("g6")
    assert mail["de"] == "" and mail["sujet"] == ""
    assert mail["date"]  # repli sur internalDate


def test_attachments_are_not_used_as_body():
    parts = [
        {"mimeType": "text/plain", "filename": "", "body": {"data": _b64("Texte visible")}},
        {
            "mimeType": "application/pdf",
            "filename": "secret.pdf",
            "body": {"attachmentId": "ATT123", "size": 99},
        },
        {
            "mimeType": "application/octet-stream",
            "filename": "bin.dat",
            "body": {"data": _b64("NE_PAS_LIRE_PIECE_JOINTE")},
        },
    ]
    backend, _ = make_backend([_msg("g7", subject="PJ", parts=parts)])
    corps = backend.read("g7")["corps"]
    assert corps == "Texte visible"
    assert "NE_PAS_LIRE" not in corps


def test_unknown_account_lists_available_accounts():
    backend, _ = make_backend([])
    with pytest.raises(ValueError, match="Comptes disponibles : gmail"):
        backend.search(account="perso")


def test_unknown_mail_id_raises():
    backend, _ = make_backend([_msg("g1", plain="x")])
    with pytest.raises(ValueError, match="introuvable"):
        backend.read("inconnu")


@pytest.mark.parametrize("status", [403, 429, 500])
def test_http_errors_do_not_expose_mail_or_response_content(status):
    mail = _msg("g1", subject="PRIVATE_SUBJECT", plain="PRIVATE_MAIL_BODY")
    backend, _ = make_backend([mail], get_error_status=status)
    with pytest.raises(RuntimeError) as exc_info:
        backend.read("g1")
    message = str(exc_info.value)
    assert "PRIVATE_SUBJECT" not in message
    assert "PRIVATE_MAIL_BODY" not in message
    assert "PRIVATE_HTTP_ERROR_BODY" not in message


def test_refresh_error_during_api_call_requests_reconnection_without_exposing_content():
    mail = _msg("g1", subject="PRIVATE_SUBJECT", plain="PRIVATE_MAIL_BODY")
    backend, _ = make_backend([mail], get_refresh_error=True)
    with pytest.raises(RuntimeError) as exc_info:
        backend.read("g1")
    message = str(exc_info.value)
    assert "connect_gmail.py" in message
    assert "expiré ou révoqué" in message
    assert "PRIVATE_SUBJECT" not in message
    assert "PRIVATE_MAIL_BODY" not in message
    assert "PRIVATE_REFRESH_ERROR_CONTENT" not in message


def test_http_404_during_search_is_reported_as_generic_gmail_error():
    backend, _ = make_backend([], list_error_status=404)
    with pytest.raises(RuntimeError, match="Échec de l'accès à Gmail"):
        backend.search("mot-clé")


def test_backend_has_no_write_methods():
    assert not hasattr(GmailMailBackend, "create_draft")
    assert not hasattr(GmailMailBackend, "send")
    backend, _ = make_backend([])
    assert not hasattr(backend, "create_draft")
    assert not hasattr(backend, "send")


# --- filtres de recherche (expéditeur, sujet, date, heure, non lus) --------------------------------

def _ms(texte_utc: str) -> str:
    """« 2026-11-22T09:00 » (UTC) -> internalDate Gmail, en millisecondes."""
    return str(int(datetime.fromisoformat(texte_utc).replace(tzinfo=timezone.utc).timestamp() * 1000))


def _trois_mails():
    return [
        _msg("g-matin", frm="Nour Testeur <nour@exemple.test>", subject="Offre ingénieur IA",
             internal=_ms("2026-11-22T09:00"), labels=["INBOX", "UNREAD"], snippet="Poste à Rabat"),
        _msg("g-aprem", frm="Sara <sara@exemple.test>", subject="Rappel déjeuner",
             internal=_ms("2026-11-22T15:30"), labels=["INBOX"], snippet="Vendredi ?"),
        _msg("g-veille", frm="Nour Testeur <nour@exemple.test>", subject="Offre manager",
             internal=_ms("2026-11-21T23:59"), labels=["INBOX", "UNREAD"], snippet="Autre poste"),
    ]


def _ids(hits):
    return {h["id"] for h in hits}


def test_search_filters_by_day_and_by_hour():
    backend, _ = make_backend(_trois_mails())
    assert _ids(backend.search(depuis="2026-11-22", jusqu_a="2026-11-22")) == {"g-matin", "g-aprem"}
    assert _ids(backend.search(depuis="2026-11-22T12:00", jusqu_a="2026-11-22T18:00")) == {"g-aprem"}
    assert _ids(backend.search(jusqu_a="2026-11-21")) == {"g-veille"}


def test_search_filters_by_sender_subject_and_unread_and_combines_them():
    backend, _ = make_backend(_trois_mails())
    assert _ids(backend.search(expediteur="nour")) == {"g-matin", "g-veille"}
    assert _ids(backend.search(expediteur="SARA")) == {"g-aprem"}
    assert _ids(backend.search(sujet="offre")) == {"g-matin", "g-veille"}
    assert _ids(backend.search(non_lus=True)) == {"g-matin", "g-veille"}
    assert _ids(backend.search(expediteur="nour", non_lus=True, depuis="2026-11-22")) == {"g-matin"}


def test_search_sends_the_equivalent_gmail_operators_with_a_safety_margin():
    backend, service = make_backend(_trois_mails())
    backend.search(expediteur="Sara", sujet="rappel", depuis="2026-11-22", jusqu_a="2026-11-22", non_lus=True)
    jour = int(datetime(2026, 11, 22, tzinfo=timezone.utc).timestamp())
    assert service._messages.list_calls[-1]["q"] == (
        f"from:(Sara) subject:(rappel) after:{jour - 60} before:{jour + 86400 + 60} is:unread")


def test_dates_and_filters_use_the_users_timezone_not_utc():
    # 23h30 UTC le 22 novembre = 00h30 le 23 novembre en UTC+1 (heure du Maroc hors Ramadan)
    backend, _ = make_backend([_msg("g-nuit", plain="x", subject="Tard", internal=_ms("2026-11-22T23:30"))],
                              tz=timezone(timedelta(hours=1)))
    assert backend.read("g-nuit")["date"] == "2026-11-23T00:30"
    assert _ids(backend.search(jusqu_a="2026-11-22")) == set()
    assert _ids(backend.search(depuis="2026-11-23")) == {"g-nuit"}


def test_invalid_date_is_rejected_before_any_api_call():
    backend, service = make_backend(_trois_mails())
    with pytest.raises(ValueError, match="AAAA-MM-JJ"):
        backend.search(depuis="hier")
    assert service._messages.list_calls == [] and service._messages.get_calls == []


def test_more_results_are_signalled_even_when_the_exact_filter_drops_some():
    # Gmail renvoie 2 mails (page pleine pour limite=2) ; la marge de 60 s laisse passer g-veille (23h59 le 21),
    # que le filtre exact écarte. Il reste peut-être d'autres mails : il ne faut pas dire « tout a été vu ».
    backend, _ = make_backend([m for m in _trois_mails() if m["id"] in ("g-matin", "g-veille")])
    mails, il_en_reste = backend.search_page(depuis="2026-11-22", limit=2)
    assert _ids(mails) == {"g-matin"} and il_en_reste is True


def test_no_more_results_when_gmail_returns_a_partial_page_without_next_token():
    backend, _ = make_backend(_trois_mails())
    mails, il_en_reste = backend.search_page(limit=10)
    assert len(mails) == 3 and il_en_reste is False


def test_default_limit_is_five():
    backend, service = make_backend(_trois_mails())
    backend.search()
    assert service._messages.list_calls[-1]["maxResults"] == 5
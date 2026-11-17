"""GmailMailBackend : lecture seule, aucun réseau, faux service imitant l'API Gmail."""
from __future__ import annotations

import base64

import pytest
from mail_backend import MAX_BODY_CHARS, GmailMailBackend


def _b64(texte: str) -> str:
    """Encode comme Gmail : base64url sans padding."""
    return base64.urlsafe_b64encode(texte.encode("utf-8")).decode("ascii").rstrip("=")


class _Exec:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _Messages:
    """Imite users().messages() : list / get (chaîne réelle de googleapiclient)."""

    def __init__(self, by_id: dict[str, dict]):
        self.by_id = by_id
        self.list_calls: list[dict] = []
        self.get_calls: list[dict] = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        max_results = int(kwargs.get("maxResults") or 100)
        ids = list(self.by_id.keys())[:max_results]
        return _Exec({"messages": [{"id": i, "threadId": f"t-{i}"} for i in ids]})

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        mid = kwargs["id"]
        if mid not in self.by_id:
            raise KeyError(mid)
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

    def __init__(self, by_id: dict[str, dict]):
        self._messages = _Messages(by_id)

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


def make_backend(messages: list[dict]):
    by_id = {m["id"]: m for m in messages}
    service = FakeGmailService(by_id)
    return GmailMailBackend(service=service), service


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


def test_read_decodes_base64url_plain_body():
    # padding volontairement absent (comportement Gmail)
    raw = _b64("Bonjour depuis Gmail")
    assert "=" not in raw
    backend, _ = make_backend([_msg("g2", frm="a@b.test", to="moi@gmail.com",
                                    subject="Sujet", plain="Bonjour depuis Gmail",
                                    date_hdr="Fri, 17 Oct 2026 09:00:00 +0000",
                                    labels=["INBOX"])])
    mail = backend.read("g2")
    assert set(mail) == {"id", "compte", "de", "a", "sujet", "date", "corps", "lu"}
    assert mail["corps"] == "Bonjour depuis Gmail"
    assert mail["compte"] == "gmail" and mail["lu"] is True
    assert mail["a"] == "moi@gmail.com" and mail["date"] == "2026-10-17T09:00"


def test_multipart_prefers_text_plain_over_html():
    backend, _ = make_backend([_msg(
        "g3", frm="x@y.test", to="moi@gmail.com", subject="Multi",
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
    assert "evil.example" not in corps and "pixel" not in corps


def test_long_body_is_truncated():
    long = "A" * (MAX_BODY_CHARS + 500)
    backend, _ = make_backend([_msg("g5", plain=long, subject="Long")])
    corps = backend.read("g5")["corps"]
    assert len(corps) == MAX_BODY_CHARS
    assert corps.endswith("…")


def test_missing_from_or_subject_become_empty_strings():
    backend, _ = make_backend([_msg(
        "g6", frm="", subject="", to="moi@gmail.com", plain="corps",
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


def test_backend_has_no_write_methods():
    assert not hasattr(GmailMailBackend, "create_draft")
    assert not hasattr(GmailMailBackend, "send")
    backend, _ = make_backend([])
    assert not hasattr(backend, "create_draft")
    assert not hasattr(backend, "send")

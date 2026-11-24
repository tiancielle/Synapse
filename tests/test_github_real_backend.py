"""Backend GitHub réel, SANS réseau : l'API REST est simulée par httpx.MockTransport.

Vérifie : uniquement des GET, en-têtes, liste blanche avant toute requête, conversion des réponses,
bornes, fichiers binaires, et messages d'erreur génériques (jamais le corps de la réponse ni le jeton).
"""
import base64
import inspect
from datetime import timezone

import httpx
import pytest
import github_backend
from github_backend import (MAX_COMMENTAIRES, VERSION_API, ErreurOutil, GithubBackend, lire_jeton)

DEPOT = "proprio-test/depot-test"
BASE = f"/repos/{DEPOT}"
JETON = "JETON_FACTICE_NE_DOIT_JAMAIS_SORTIR"
SECRET_REPONSE = "CORPS_DE_REPONSE_QUI_NE_DOIT_JAMAIS_SORTIR"


def _issue(n, titre="Titre", etat="open", comments=0, pr=False, body="Texte de l'issue"):
    j = {"number": n, "title": titre, "state": etat, "user": {"login": "auteur-test"}, "labels": [{"name": "bug"}],
         "body": body, "created_at": "2026-10-12T10:00:00Z", "comments": comments}
    if pr:
        j["pull_request"] = {"url": "x"}
    return j


def _b64(octets: bytes) -> str:
    return base64.b64encode(octets).decode()


class FausseApi:
    """Routes : chemin -> (statut, json, en-têtes). Enregistre chaque requête reçue."""

    def __init__(self, routes=None, erreur_reseau=False):
        self.routes = routes or {}
        self.erreur_reseau = erreur_reseau
        self.requetes: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requetes.append(request)
        if self.erreur_reseau:
            raise httpx.ConnectError("échec réseau simulé", request=request)
        statut, corps, entetes = self.routes.get(request.url.raw_path.decode().split("?")[0],
                                                 (404, {"message": "Not Found"}, {}))
        return httpx.Response(statut, json=corps, headers=entetes)


def backend(api: FausseApi, depots=(DEPOT,)):
    return GithubBackend(list(depots), source_jeton=lambda: JETON, transport=httpx.MockTransport(api),
                         tz=timezone.utc)


# --- lecture seule et en-têtes --------------------------------------------------------------------

def test_the_backend_has_no_write_method_and_only_sends_get():
    noms = {n for n, _ in inspect.getmembers(GithubBackend, inspect.isfunction)}
    assert not noms & {"post", "put", "patch", "delete", "creer_issue", "commenter", "fusionner"}
    source = inspect.getsource(github_backend)
    for verbe in (".post(", ".put(", ".patch(", ".delete(", ".request("):
        assert verbe not in source
    api = FausseApi({f"{BASE}/issues": (200, [_issue(1)], {}), f"{BASE}/pulls": (200, [], {})})
    b = backend(api)
    b.lister_issues(DEPOT)
    b.lister_pull_requests(DEPOT)
    assert api.requetes and all(r.method == "GET" for r in api.requetes)


def test_requests_carry_the_documented_headers():
    api = FausseApi({f"{BASE}/issues": (200, [], {})})
    backend(api).lister_issues(DEPOT)
    h = api.requetes[0].headers
    assert h["accept"] == "application/vnd.github+json" and h["x-github-api-version"] == VERSION_API
    assert h["authorization"] == f"Bearer {JETON}"
    assert str(api.requetes[0].url).startswith("https://api.github.com/repos/proprio-test/depot-test/issues")


def test_allowlist_is_checked_before_any_request():
    api = FausseApi()
    b = backend(api)
    for appel in (lambda: b.lister_issues("autre/depot"), lambda: b.lire_issue("autre/depot", 1),
                  lambda: b.lister_pull_requests("autre/depot"), lambda: b.lire_pull_request("autre/depot", 1),
                  lambda: b.lire_fichier("autre/depot", "README.md"), lambda: b.lire_fichier(DEPOT, "../x")):
        with pytest.raises(ErreurOutil):
            appel()
    assert api.requetes == []


def test_backend_refuses_to_start_without_an_allowlist():
    with pytest.raises(RuntimeError, match="liste blanche absente"):
        GithubBackend([], source_jeton=lambda: JETON)


# --- conversion des réponses ----------------------------------------------------------------------

def test_list_issues_drops_pull_requests_and_maps_fields():
    page = [_issue(5, comments=2), _issue(4, pr=True), _issue(3, etat="open")]
    api = FausseApi({f"{BASE}/issues": (200, page, {})})
    issues, reste = backend(api).lister_issues(DEPOT, etat="all", limite=10)
    assert [i["numero"] for i in issues] == [5, 3] and reste is False
    assert issues[0] == {"numero": 5, "titre": "Titre", "etat": "open", "auteur": "auteur-test", "etiquettes": ["bug"],
                         "date": "2026-10-12T10:00", "nb_commentaires": 2}
    assert api.requetes[0].url.params["state"] == "all" and int(api.requetes[0].url.params["per_page"]) <= 100


def test_more_results_are_signalled_by_the_limit_or_the_next_page_link():
    api = FausseApi({f"{BASE}/issues": (200, [_issue(3), _issue(2), _issue(1)], {})})
    assert backend(api).lister_issues(DEPOT, limite=2)[1] is True
    lien = {"link": f'<https://api.github.com{BASE}/pulls?page=2>; rel="next"'}
    api = FausseApi({f"{BASE}/pulls": (200, [_issue(9)], lien)})
    prs, reste = backend(api).lister_pull_requests(DEPOT, limite=1)
    assert reste is True and prs[0]["nb_commentaires"] is None          # inconnu dans la liste : pas de faux 0


def test_read_issue_with_bounded_comments():
    commentaires = [{"user": {"login": f"c{i}"}, "created_at": "2026-10-12T11:00:00Z", "body": f"commentaire {i}"}
                    for i in range(MAX_COMMENTAIRES)]
    api = FausseApi({f"{BASE}/issues/7": (200, _issue(7, comments=45), {}),
                     f"{BASE}/issues/7/comments": (200, commentaires, {})})
    issue = backend(api).lire_issue(DEPOT, 7)
    assert issue["corps"] == "Texte de l'issue" and len(issue["commentaires"]) == MAX_COMMENTAIRES
    assert issue["nb_commentaires"] == 45 and issue["commentaires_tronques"] is True
    assert api.requetes[1].url.params["per_page"] == str(MAX_COMMENTAIRES)


def test_an_issue_without_comments_needs_a_single_request():
    api = FausseApi({f"{BASE}/issues/2": (200, _issue(2), {})})
    assert backend(api).lire_issue(DEPOT, 2)["commentaires"] == [] and len(api.requetes) == 1


def test_a_pull_request_number_is_not_an_issue():
    api = FausseApi({f"{BASE}/issues/4": (200, _issue(4, pr=True), {})})
    with pytest.raises(ErreurOutil, match="Issue introuvable : n° 4"):
        backend(api).lire_issue(DEPOT, 4)


def test_read_pull_request_maps_branches_and_files():
    pr = _issue(8) | {"head": {"ref": "fix/x"}, "base": {"ref": "main"}}
    api = FausseApi({f"{BASE}/pulls/8": (200, pr, {}),
                     f"{BASE}/pulls/8/files": (200, [{"filename": "a.py"}, {"filename": "docs/b.md"}], {})})
    d = backend(api).lire_pull_request(DEPOT, 8)
    assert (d["branche_source"], d["branche_cible"]) == ("fix/x", "main")
    assert d["fichiers_modifies"] == ["a.py", "docs/b.md"] and d["fichiers_modifies_tronques"] is False


def test_read_file_decodes_text_and_quotes_each_path_segment():
    contenu = "# Titre\nTexte accentué.\n"
    api = FausseApi({f"{BASE}/contents/docs/notes%20v2.md":
                     (200, {"type": "file", "encoding": "base64", "size": 30, "content": _b64(contenu.encode())}, {})})
    f = backend(api).lire_fichier(DEPOT, "docs/notes v2.md")
    assert f == {"depot": DEPOT, "chemin": "docs/notes v2.md", "contenu": contenu, "tronque": False}


@pytest.mark.parametrize("reponse,attendu", [
    ([{"type": "file", "name": "a"}], "pas un fichier"),                                      # dossier
    ({"type": "symlink", "target": "x"}, "pas un fichier"),
    ({"type": "file", "encoding": "none", "size": 5_000_000, "content": ""}, "trop volumineux"),
    ({"type": "file", "encoding": "base64", "size": 10, "content": _b64(b"PNG\x00\x01\x02")}, "binaire"),
    ({"type": "file", "encoding": "base64", "size": 10, "content": _b64(b"\xff\xfe\xfa caf\xe9")}, "non UTF-8"),
])
def test_unreadable_files_are_refused_without_their_content(reponse, attendu):
    api = FausseApi({f"{BASE}/contents/f.txt": (200, reponse, {})})
    with pytest.raises(ErreurOutil, match=attendu) as exc:
        backend(api).lire_fichier(DEPOT, "f.txt")
    assert "caf" not in str(exc.value) and "PNG" not in str(exc.value)


# --- erreurs : messages génériques, sans contenu ------------------------------------------------

@pytest.mark.parametrize("statut,attendu", [
    (404, "introuvable"), (410, "introuvable"), (401, "jeton invalide ou expiré"), (403, "limite de requêtes"),
    (429, "limite de requêtes"), (500, "indisponible"), (502, "indisponible"), (301, "renommé ou déplacé"),
    (308, "renommé ou déplacé"),
])
def test_http_errors_give_a_generic_message_without_the_response_body(statut, attendu):
    corps = {"message": SECRET_REPONSE, "documentation_url": SECRET_REPONSE}
    api = FausseApi({f"{BASE}/issues/1": (statut, corps, {"location": f"https://exemple.test/{SECRET_REPONSE}"})})
    with pytest.raises(ErreurOutil, match=attendu) as exc:
        backend(api).lire_issue(DEPOT, 1)
    assert SECRET_REPONSE not in str(exc.value) and JETON not in str(exc.value)


def test_network_errors_and_invalid_json_give_a_generic_message():
    with pytest.raises(ErreurOutil, match="Connexion à GitHub impossible") as exc:
        backend(FausseApi(erreur_reseau=True)).lister_issues(DEPOT)
    assert JETON not in str(exc.value)

    def pas_du_json(request):
        return httpx.Response(200, content=f"<html>{SECRET_REPONSE}</html>".encode())
    b = GithubBackend([DEPOT], source_jeton=lambda: JETON, transport=httpx.MockTransport(pas_du_json))
    with pytest.raises(ErreurOutil, match="réponse inattendue") as exc:
        b.lister_issues(DEPOT)
    assert SECRET_REPONSE not in str(exc.value)


def test_redirects_are_never_followed():
    api = FausseApi({f"{BASE}/issues/1": (301, {}, {"location": "https://exemple.test/ailleurs"})})
    with pytest.raises(ErreurOutil):
        backend(api).lire_issue(DEPOT, 1)
    assert len(api.requetes) == 1 and api.requetes[0].url.host == "api.github.com"


@pytest.mark.parametrize("numero", [0, -1, 10**12, True, "1" * 5000, "abc", None])
def test_issue_numbers_are_bounded_before_any_request(numero):
    api = FausseApi()
    with pytest.raises(ErreurOutil, match="numero") as exc:
        backend(api).lire_issue(DEPOT, numero)
    assert api.requetes == [] and len(str(exc.value)) < 200


@pytest.mark.parametrize("route,reponse", [
    (f"{BASE}/issues", {"pas": "une liste"}),                        # dict au lieu d'une liste
    (f"{BASE}/issues", ["chaine", 3]),                               # éléments qui ne sont pas des objets
    (f"{BASE}/issues", [{"number": 1, "comments": "VALEUR_RECUE_BIZARRE"}]),
])
def test_malformed_github_responses_give_a_fixed_message(route, reponse):
    api = FausseApi({route: (200, reponse, {})})
    with pytest.raises(ErreurOutil, match="réponse inattendue") as exc:
        backend(api).lister_issues(DEPOT)
    assert "VALEUR_RECUE_BIZARRE" not in str(exc.value) and "chaine" not in str(exc.value)


def test_malformed_file_and_comment_responses_give_a_fixed_message():
    api = FausseApi({f"{BASE}/contents/f.txt": (200, {"type": "file", "size": "beaucoup", "encoding": "base64"}, {}),
                     f"{BASE}/issues/3": (200, _issue(3, comments=1), {}),
                     f"{BASE}/issues/3/comments": (200, ["pas un objet"], {})})
    for appel in (lambda b: b.lire_fichier(DEPOT, "f.txt"), lambda b: b.lire_issue(DEPOT, 3)):
        with pytest.raises(ErreurOutil, match="réponse inattendue"):
            appel(backend(api))


def test_the_token_never_appears_in_the_backend_representation():
    b = backend(FausseApi({f"{BASE}/issues": (200, [], {})}))
    b.lister_issues(DEPOT)
    assert JETON not in repr(b) and JETON not in str(vars(b).get("depots_autorises"))


# --- jeton ------------------------------------------------------------------------------------------

def test_token_comes_from_the_environment_first_then_from_the_secrets_file(tmp_path):
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "github_token").write_text("  jeton-fichier-test\n", encoding="utf-8")
    assert lire_jeton(tmp_path, env={"SYNAPSE_GITHUB_TOKEN": "jeton-env-test"}) == "jeton-env-test"
    assert lire_jeton(tmp_path, env={}) == "jeton-fichier-test"


def test_missing_token_gives_a_clear_message_at_the_first_call_not_at_startup(tmp_path):
    with pytest.raises(ErreurOutil, match="Jeton GitHub absent.*secrets/github_token"):
        lire_jeton(tmp_path, env={})
    api = FausseApi()
    b = GithubBackend([DEPOT], source_jeton=lambda: lire_jeton(tmp_path, env={}), transport=httpx.MockTransport(api))
    with pytest.raises(ErreurOutil, match="Jeton GitHub absent"):
        b.lister_issues(DEPOT)
    assert api.requetes == []

"""Backends du serveur GitHub : même format de sortie, implémentations interchangeables.

- FixtureGithubBackend : dépôts synthétiques (tests, évaluation, démo hors-ligne)
- GithubBackend        : vrai GitHub, API REST, LECTURE SEULE (uniquement des requêtes GET)

Les clés commençant par _ dans la fixture sont des étiquettes d'évaluation : elles ne sont JAMAIS renvoyées
(chaque sortie est construite champ par champ).
La liste blanche des dépôts est appliquée ICI, côté serveur, quel que soit le dépôt demandé par le modèle.
Aucune méthode d'écriture, dans aucun backend.

Erreurs : seules les ErreurOutil (messages écrits ici, sans contenu d'issue ni de fichier) sont montrées au modèle.
Toute autre exception (y compris d'une bibliothèque) se réduit à « Error executing tool ».
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Callable
from urllib.parse import quote

LIMITE_DEFAUT = 10
LIMITE_MAX = 30
MAX_CORPS = 4000              # caractères du corps d'une issue / PR
MAX_COMMENTAIRES = 20         # commentaires renvoyés par lire_issue / lire_pull_request
MAX_COMMENTAIRE = 1000        # caractères par commentaire
MAX_FICHIER = 8000            # caractères d'un fichier lu
MAX_FICHIERS_MODIFIES = 50
MAX_CHEMIN = 300
MAX_TITRE = 300
MAX_AUTEUR = 100
MAX_ETIQUETTES = 20
MAX_ETIQUETTE = 50
TAILLE_MAX_FICHIER = 1_000_000   # octets : au-delà, l'API JSON de GitHub ne renvoie plus le contenu
ETATS = ("open", "closed", "all")

_DEPOT = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}")
_LECTEUR_WINDOWS = re.compile(r"^[A-Za-z]:")
_SEGMENT = re.compile(r"[A-Za-z0-9._+ -]{1,100}")


class ErreurOutil(ValueError):
    """Erreur ATTENDUE, au message écrit dans ce module (sans contenu) : la seule transmise au modèle."""


def _borner(texte: str, n: int) -> str:
    texte = texte or ""
    return texte if len(texte) <= n else texte[: n - 1] + "…"


def lire_liste_blanche(valeur: str) -> list[str]:
    """« proprietaire/depot,proprietaire/autre » -> liste de dépôts. Entrée mal formée -> ErreurOutil."""
    depots = [d.strip() for d in (valeur or "").split(",") if d.strip()]
    for d in depots:
        if not _DEPOT.fullmatch(d) or ".." in d:
            raise ErreurOutil(f"Liste blanche invalide : {d!r}. Format attendu : proprietaire/depot,proprietaire/autre")
    return depots


def verifier_depot(depot: str, autorises: list[str]) -> str:
    """Renvoie le nom canonique (tel qu'écrit dans la liste blanche). GitHub ignore la casse des noms."""
    d = (depot or "").strip()
    if not _DEPOT.fullmatch(d) or ".." in d:
        raise ErreurOutil("Nom de dépôt invalide. Format attendu : proprietaire/depot.")
    for a in autorises:
        if a.lower() == d.lower():
            return a
    raise ErreurOutil(f"Dépôt non autorisé : {d}. Dépôts autorisés : {', '.join(autorises) or 'aucun'}.")


def verifier_chemin(chemin: str) -> str:
    """Chemin relatif à la racine du dépôt, séparateur « / », sans « . », « .. » ni segment vide.
    Chaque segment n'admet que des caractères ASCII sûrs : le chemin sert aussi à construire une URL,
    donc ni « % », « ? », « # », « : », ni contrôle, ni unicode (formes « ․․ » ou « ／ » normalisables)."""
    c = (chemin or "").strip()
    if not c or len(c) > MAX_CHEMIN:
        raise ErreurOutil("Chemin de fichier invalide : vide ou trop long.")
    if "\\" in c or "\x00" in c or c.startswith("/") or _LECTEUR_WINDOWS.match(c):
        raise ErreurOutil("Chemin invalide : donner un chemin relatif à la racine du dépôt, avec des « / » "
                          "(ex. docs/installation.md).")
    segments = c.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise ErreurOutil("Chemin invalide : les segments « . », « .. » et les « / » doublés sont refusés.")
    if not all(_SEGMENT.fullmatch(segment) for segment in segments):
        raise ErreurOutil("Chemin invalide : caractères autorisés : lettres et chiffres ASCII, « . », « _ », « - », "
                          "« + » et espace.")
    return c


def verifier_etat(etat: str) -> str:
    if etat not in ETATS:
        raise ErreurOutil("« etat » invalide. Valeurs acceptées : open, closed, all.")
    return etat


def borner_limite(limite) -> int:
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        raise ErreurOutil("« limite » doit être un nombre entier.") from None
    return max(1, min(limite, LIMITE_MAX))


NUMERO_MAX = 1_000_000_000


def lire_numero(numero) -> int:
    """Entier de 1 à NUMERO_MAX (borné : il est recopié dans les messages et dans l'URL)."""
    try:
        if isinstance(numero, bool):
            raise TypeError
        n = int(numero)
    except (TypeError, ValueError):
        raise ErreurOutil("« numero » doit être un nombre entier.") from None
    if not 1 <= n <= NUMERO_MAX:
        raise ErreurOutil(f"« numero » doit être compris entre 1 et {NUMERO_MAX}.")
    return n


# --- formats de sortie (communs aux backends) -----------------------------------------------------
# Un « élément » interne : numero, titre, etat, auteur, etiquettes, date, corps, commentaires
# (+ facultatifs nb_commentaires, commentaires_tronques ; pour une PR : branches et fichiers modifiés).

def resume(item: dict) -> dict:
    commentaires = item.get("commentaires") or []
    return {"numero": item["numero"], "titre": _borner(item["titre"], MAX_TITRE), "etat": item["etat"],
            "auteur": _borner(item["auteur"], MAX_AUTEUR),
            "etiquettes": [_borner(e, MAX_ETIQUETTE) for e in (item.get("etiquettes") or [])[:MAX_ETIQUETTES]],
            "date": item["date"], "nb_commentaires": item.get("nb_commentaires", len(commentaires))}


def detail(item: dict) -> dict:
    commentaires = item.get("commentaires") or []
    return {**resume(item),
            "corps": _borner(item.get("corps") or "", MAX_CORPS),
            "commentaires": [{"auteur": _borner(c["auteur"], MAX_AUTEUR), "date": c["date"],
                              "corps": _borner(c["corps"], MAX_COMMENTAIRE)} for c in commentaires[:MAX_COMMENTAIRES]],
            "commentaires_tronques": item.get("commentaires_tronques", len(commentaires) > MAX_COMMENTAIRES)}


def detail_pull_request(item: dict) -> dict:
    fichiers = item.get("fichiers_modifies") or []
    return {**detail(item), "branche_source": _borner(item["branche_source"], MAX_CHEMIN),
            "branche_cible": _borner(item["branche_cible"], MAX_CHEMIN),
            "fichiers_modifies": [_borner(f, MAX_CHEMIN) for f in fichiers[:MAX_FICHIERS_MODIFIES]],
            "fichiers_modifies_tronques": item.get("fichiers_modifies_tronques",
                                                   len(fichiers) > MAX_FICHIERS_MODIFIES)}


def fichier(depot: str, chemin: str, contenu: str) -> dict:
    return {"depot": depot, "chemin": chemin, "contenu": _borner(contenu, MAX_FICHIER),
            "tronque": len(contenu) > MAX_FICHIER}


# --- backend de test --------------------------------------------------------------------------------

class FixtureGithubBackend:
    def __init__(self, fixture_path: Path, depots_autorises: list[str]):
        data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        self._depots = {nom.lower(): contenu for nom, contenu in data["depots"].items()}
        self.depots_autorises = list(depots_autorises)

    def _depot(self, depot: str) -> tuple[str, dict]:
        nom = verifier_depot(depot, self.depots_autorises)      # liste blanche AVANT tout accès aux données
        contenu = self._depots.get(nom.lower())
        if contenu is None:
            raise ErreurOutil(f"Dépôt introuvable : {nom}.")
        return nom, contenu

    @staticmethod
    def _lister(items: list[dict], etat: str, limite) -> tuple[list[dict], bool]:
        verifier_etat(etat)
        n = borner_limite(limite)
        hits = sorted((i for i in items if etat == "all" or i["etat"] == etat), key=lambda i: i["numero"], reverse=True)
        return [resume(i) for i in hits[:n]], len(hits) > n

    @staticmethod
    def _trouver(items: list[dict], numero, genre: str) -> dict:
        n = lire_numero(numero)
        for i in items:
            if i["numero"] == n:
                return i
        raise ErreurOutil(f"{genre} introuvable : n° {n}.")

    def lister_issues(self, depot: str, etat: str = "open", limite=LIMITE_DEFAUT) -> tuple[list[dict], bool]:
        """Renvoie (issues, il_en_reste)."""
        _, d = self._depot(depot)
        return self._lister(d["issues"], etat, limite)

    def lister_pull_requests(self, depot: str, etat: str = "open", limite=LIMITE_DEFAUT) -> tuple[list[dict], bool]:
        _, d = self._depot(depot)
        return self._lister(d["pull_requests"], etat, limite)

    def lire_issue(self, depot: str, numero) -> dict:
        _, d = self._depot(depot)
        return detail(self._trouver(d["issues"], numero, "Issue"))

    def lire_pull_request(self, depot: str, numero) -> dict:
        _, d = self._depot(depot)
        return detail_pull_request(self._trouver(d["pull_requests"], numero, "Pull request"))

    def lire_fichier(self, depot: str, chemin: str) -> dict:
        nom, d = self._depot(depot)
        c = verifier_chemin(chemin)
        if c in (d.get("fichiers_binaires") or []):
            raise ErreurOutil("Fichier binaire : seuls les fichiers texte peuvent être lus.")
        for f in d["fichiers"]:
            if f["chemin"] == c:
                return fichier(nom, c, f["contenu"])
        raise ErreurOutil(f"Fichier introuvable : {c!r}.")


# --- vrai GitHub, lecture seule ---------------------------------------------------------------------

API_GITHUB = "https://api.github.com"
VERSION_API = "2026-03-10"            # en-tête X-GitHub-Api-Version (docs.github.com, vérifié le 2026-11-24)
PAR_PAGE_MAX = 100                    # per_page maximal de l'API REST


def lire_jeton(racine: Path, env=None) -> str:
    """Jeton à granularité fine : SYNAPSE_GITHUB_TOKEN, sinon <racine>/secrets/github_token. Jamais journalisé."""
    env = os.environ if env is None else env
    jeton = (env.get("SYNAPSE_GITHUB_TOKEN") or "").strip()
    if not jeton:
        fichier_jeton = Path(racine) / "secrets" / "github_token"
        if fichier_jeton.is_file():
            jeton = fichier_jeton.read_text(encoding="utf-8").strip()
    if not jeton:
        raise ErreurOutil("Jeton GitHub absent : définir SYNAPSE_GITHUB_TOKEN ou créer le fichier secrets/github_token.")
    return jeton


def _date_locale(iso: str | None, tz: tzinfo | None) -> str:
    """« 2026-10-12T10:00:00Z » (UTC) -> « 2026-10-12T11:00 » en heure locale (tz=None : fuseau de la machine)."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(tz).strftime("%Y-%m-%dT%H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _login(obj) -> str:
    return str(((obj or {}).get("user") or {}).get("login") or "")


def _etiquettes(obj) -> list[str]:
    noms = []
    for e in (obj or {}).get("labels") or []:
        noms.append(str(e.get("name") or "") if isinstance(e, dict) else str(e))
    return noms


def _page_suivante(reponse) -> bool:
    return 'rel="next"' in (reponse.headers.get("link") or "")


REPONSE_INATTENDUE = "GitHub indisponible ou réponse inattendue. Réessayer plus tard."


def _reponse_attendue(methode):
    """Une réponse GitHub mal formée (champ manquant, type inattendu) donne un message FIXE, sans le texte natif
    de l'exception (qui pourrait citer une valeur reçue). Les ErreurOutil passent telles quelles."""
    import functools

    @functools.wraps(methode)
    def enveloppe(*args, **kwargs):
        try:
            return methode(*args, **kwargs)
        except ErreurOutil:
            raise
        except (KeyError, TypeError, AttributeError, ValueError, IndexError):
            raise ErreurOutil(REPONSE_INATTENDUE) from None
    return enveloppe


class GithubBackend:
    """GitHub en lecture seule (palier 1). Une seule méthode réseau : _get (requête GET). Aucune écriture.

    `source_jeton` : fonction qui renvoie le jeton (lue au premier appel : la liste des outils marche sans jeton).
    `transport` : transport httpx (httpx.MockTransport en tests ; None = réseau réel).
    """

    def __init__(self, depots_autorises: list[str], source_jeton: Callable[[], str], *, transport=None,
                 tz: tzinfo | None = None, base_url: str = API_GITHUB):
        if not depots_autorises:
            raise RuntimeError("Backend github : liste blanche absente. "
                               "Définir SYNAPSE_GITHUB_REPOS=proprietaire/depot (plusieurs : séparés par des virgules).")
        self.depots_autorises = list(depots_autorises)
        self._source_jeton = source_jeton
        self._transport = transport
        self._tz = tz
        self._base_url = base_url
        self._client = None

    def _http(self):
        if self._client is None:
            import httpx
            self._client = httpx.Client(
                base_url=self._base_url, transport=self._transport, timeout=15.0, follow_redirects=False,
                headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": VERSION_API,
                         "Authorization": f"Bearer {self._source_jeton()}", "User-Agent": "agentflow-lecture-seule"})
        return self._client

    def _get(self, chemin: str, params: dict | None = None, *, introuvable: str):
        """Seule requête du backend (GET). Messages d'erreur fixes : jamais le corps de la réponse ni le jeton."""
        import httpx
        try:
            reponse = self._http().get(chemin, params=params)
        except httpx.HTTPError:
            raise ErreurOutil("Connexion à GitHub impossible. Réessayer plus tard.") from None
        statut = reponse.status_code
        if statut in (404, 410):
            raise ErreurOutil(introuvable)
        if statut == 401:
            raise ErreurOutil("Accès GitHub refusé : jeton invalide ou expiré. Le remplacer dans secrets/github_token "
                              "puis redémarrer AgentFlow.")
        if statut in (403, 429):
            raise ErreurOutil("Accès GitHub refusé ou limite de requêtes atteinte. Réessayer plus tard.")
        if 300 <= statut < 400:                 # redirections jamais suivies (follow_redirects=False)
            raise ErreurOutil("Dépôt renommé ou déplacé sur GitHub : mettre à jour SYNAPSE_GITHUB_REPOS.")
        if statut != 200:
            raise ErreurOutil(REPONSE_INATTENDUE)
        try:
            return reponse.json(), reponse
        except ValueError:
            raise ErreurOutil(REPONSE_INATTENDUE) from None

    def _base(self, depot: str) -> tuple[str, str]:
        nom = verifier_depot(depot, self.depots_autorises)      # liste blanche AVANT toute requête
        proprietaire, depot_court = nom.split("/")
        return nom, f"/repos/{quote(proprietaire, safe='')}/{quote(depot_court, safe='')}"

    def _item(self, j: dict) -> dict:
        return {"numero": j.get("number"), "titre": str(j.get("title") or ""), "etat": str(j.get("state") or ""),
                "auteur": _login(j), "etiquettes": _etiquettes(j), "date": _date_locale(j.get("created_at"), self._tz),
                "corps": str(j.get("body") or "")}

    def _commentaires(self, base: str, n: int, total: int, introuvable: str) -> dict:
        if not total:
            return {"commentaires": [], "nb_commentaires": 0, "commentaires_tronques": False}
        donnees, _ = self._get(f"{base}/issues/{n}/comments", {"per_page": MAX_COMMENTAIRES}, introuvable=introuvable)
        commentaires = [{"auteur": _login(c), "date": _date_locale(c.get("created_at"), self._tz),
                         "corps": str(c.get("body") or "")} for c in (donnees or [])[:MAX_COMMENTAIRES]]
        return {"commentaires": commentaires, "nb_commentaires": total,
                "commentaires_tronques": total > len(commentaires)}

    @_reponse_attendue
    def lister_issues(self, depot: str, etat: str = "open", limite=LIMITE_DEFAUT) -> tuple[list[dict], bool]:
        nom, base = self._base(depot)
        verifier_etat(etat)
        n = borner_limite(limite)
        # l'API des issues renvoie aussi les PR (clé pull_request) : on les retire, d'où une page plus large
        donnees, reponse = self._get(f"{base}/issues", {"state": etat, "per_page": PAR_PAGE_MAX},
                                     introuvable=f"Dépôt introuvable ou inaccessible avec ce jeton : {nom}.")
        issues = [self._item(j) | {"nb_commentaires": int(j.get("comments") or 0)}
                  for j in donnees or [] if "pull_request" not in j]
        return [resume(i) for i in issues[:n]], len(issues) > n or _page_suivante(reponse)

    @_reponse_attendue
    def lister_pull_requests(self, depot: str, etat: str = "open", limite=LIMITE_DEFAUT) -> tuple[list[dict], bool]:
        nom, base = self._base(depot)
        verifier_etat(etat)
        n = borner_limite(limite)
        donnees, reponse = self._get(f"{base}/pulls", {"state": etat, "per_page": n},
                                     introuvable=f"Dépôt introuvable ou inaccessible avec ce jeton : {nom}.")
        # la liste des PR ne donne pas le nombre de commentaires : None (inconnu) plutôt qu'un 0 faux
        prs = [self._item(j) | {"nb_commentaires": None} for j in (donnees or [])[:n]]
        return [resume(p) for p in prs], _page_suivante(reponse)

    @_reponse_attendue
    def lire_issue(self, depot: str, numero) -> dict:
        _, base = self._base(depot)
        n = lire_numero(numero)
        introuvable = f"Issue introuvable : n° {n}."
        j, _ = self._get(f"{base}/issues/{n}", introuvable=introuvable)
        if not isinstance(j, dict) or "pull_request" in j:          # un numéro de PR n'est pas une issue
            raise ErreurOutil(introuvable)
        return detail(self._item(j) | self._commentaires(base, n, int(j.get("comments") or 0), introuvable))

    @_reponse_attendue
    def lire_pull_request(self, depot: str, numero) -> dict:
        _, base = self._base(depot)
        n = lire_numero(numero)
        introuvable = f"Pull request introuvable : n° {n}."
        j, _ = self._get(f"{base}/pulls/{n}", introuvable=introuvable)
        fichiers, reponse = self._get(f"{base}/pulls/{n}/files", {"per_page": MAX_FICHIERS_MODIFIES},
                                      introuvable=introuvable)
        noms = [str(f.get("filename") or "") for f in (fichiers or [])[:MAX_FICHIERS_MODIFIES]]
        item = (self._item(j) | self._commentaires(base, n, int(j.get("comments") or 0), introuvable)
                | {"branche_source": str((j.get("head") or {}).get("ref") or ""),
                   "branche_cible": str((j.get("base") or {}).get("ref") or ""),
                   "fichiers_modifies": noms, "fichiers_modifies_tronques": _page_suivante(reponse)})
        return detail_pull_request(item)

    @_reponse_attendue
    def lire_fichier(self, depot: str, chemin: str) -> dict:
        nom, base = self._base(depot)
        c = verifier_chemin(chemin)
        url = f"{base}/contents/" + "/".join(quote(segment, safe="") for segment in c.split("/"))
        j, _ = self._get(url, introuvable=f"Fichier introuvable : {c!r}.")
        if isinstance(j, list) or not isinstance(j, dict) or j.get("type") != "file":
            raise ErreurOutil("Ce chemin n'est pas un fichier (dossier, lien ou sous-module).")
        if int(j.get("size") or 0) > TAILLE_MAX_FICHIER:
            raise ErreurOutil("Fichier trop volumineux pour être lu (plus de 1 Mo).")
        if j.get("encoding") != "base64":
            raise ErreurOutil(REPONSE_INATTENDUE)
        try:
            octets = base64.b64decode(str(j.get("content") or ""), validate=False)
        except (binascii.Error, ValueError):
            raise ErreurOutil(REPONSE_INATTENDUE) from None
        if b"\x00" in octets:
            raise ErreurOutil("Fichier binaire : seuls les fichiers texte peuvent être lus.")
        try:
            texte = octets.decode("utf-8")
        except UnicodeDecodeError:
            raise ErreurOutil("Fichier binaire ou non UTF-8 : seuls les fichiers texte peuvent être lus.") from None
        return fichier(nom, c, texte)

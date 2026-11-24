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
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from mail_filters import lire_date_fixture, lire_periode, mots_sans_operateurs, tous_les_mots

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
MAX_DEPOTS = 10               # taille maximale de la liste blanche
MAX_DESCRIPTION = 300
MAX_TOPICS = 20
MAX_MESSAGE = 200             # première ligne d'un message de commit
MAX_VERSION = 100             # nom de tag / titre de release
MAX_DATES_TAGS = 10           # tags sans release dont on cherche la date (un appel GitHub par tag)
MAX_REQUETE = 200             # caractères de la requête de recherche AVANT nettoyage
MAX_MOTS_REQUETE = 10

_DEPOT = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}")
_LECTEUR_WINDOWS = re.compile(r"^[A-Za-z]:")
_SEGMENT = re.compile(r"[A-Za-z0-9._+ -]{1,100}")
_AUTEUR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@+-]{0,99}")      # login GitHub ou adresse
_BRANCHE = re.compile(r"[A-Za-z0-9._/+-]{1,100}")


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
    if len(depots) > MAX_DEPOTS:
        raise ErreurOutil(f"Liste blanche trop longue : {len(depots)} dépôts, {MAX_DEPOTS} au maximum.")
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


def verifier_auteur(auteur: str) -> str:
    """Filtre facultatif : login GitHub (ou adresse) ; vide = pas de filtre."""
    a = (auteur or "").strip()
    if a and not _AUTEUR.fullmatch(a):
        raise ErreurOutil("« auteur » invalide : donner un identifiant GitHub (lettres, chiffres, - . _ @).")
    return a


def verifier_branche(branche: str, depot: str = "x") -> str:
    """Nom de branche facultatif ; vide = branche par défaut. Envoyé en paramètre de requête, jamais dans le chemin.
    Une branche n'a de sens que pour UN dépôt : avec depot vide (tous les dépôts), elle est refusée."""
    b = (branche or "").strip()
    if b and (not _BRANCHE.fullmatch(b) or ".." in b or b.startswith(("/", "-")) or "//" in b):
        raise ErreurOutil("« branche » invalide : lettres, chiffres et . _ - / + uniquement.")
    if b and not (depot or "").strip():
        raise ErreurOutil("« branche » exige « depot » : une branche appartient à un seul dépôt.")
    return b


_SHA = re.compile(r"[0-9a-f]{40}")


def lire_periode_github(depuis: str, jusqu_a: str) -> tuple[datetime | None, datetime | None]:
    """Mêmes formats que le mail (servers/mail_filters.py) : AAAA-MM-JJ ou AAAA-MM-JJTHH:MM, heure locale."""
    if len(depuis or "") > 30 or len(jusqu_a or "") > 30:
        raise ErreurOutil("Date invalide. Format attendu : AAAA-MM-JJ ou AAAA-MM-JJTHH:MM.")
    try:
        return lire_periode(depuis, jusqu_a)
    except ValueError as exc:                   # message écrit par mail_filters, sans contenu
        raise ErreurOutil(str(exc)) from None


def nettoyer_requete(requete: str) -> str:
    """Mots simples seulement (même nettoyage que la requête Gmail) : le modèle ne peut ajouter aucun
    qualificateur (repo:, org:, user:...) ni opérateur ; les qualificateurs sont construits par le serveur."""
    if len(requete or "") > MAX_REQUETE:
        raise ErreurOutil(f"« requete » trop longue ({MAX_REQUETE} caractères au maximum).")
    mots = mots_sans_operateurs(requete).split()[:MAX_MOTS_REQUETE]
    if not mots:
        raise ErreurOutil("« requete » vide : donner un ou plusieurs mots à chercher.")
    return " ".join(mots)


def _dans_periode(date: str, debut: datetime | None, fin: datetime | None) -> bool:
    if not (debut or fin):
        return True
    dt = lire_date_fixture(date)
    return dt is not None and (debut is None or dt >= debut) and (fin is None or dt < fin)


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


def info_depot(depot: str, i: dict) -> dict:
    return {"depot": depot, "description": _borner(str(i.get("description") or ""), MAX_DESCRIPTION),
            "langage": _borner(str(i.get("langage") or ""), MAX_ETIQUETTE),
            "topics": [_borner(str(t), MAX_ETIQUETTE) for t in (i.get("topics") or [])[:MAX_TOPICS]],
            "dernier_push": i.get("dernier_push") or "", "prive": bool(i.get("prive")),
            "branche_defaut": _borner(str(i.get("branche_defaut") or ""), MAX_CHEMIN)}


def commit(depot: str, c: dict) -> dict:
    premiere_ligne = (str(c.get("message") or "").splitlines() or [""])[0]
    return {"depot": depot, "sha": str(c.get("sha") or "")[:7], "message": _borner(premiere_ligne, MAX_MESSAGE),
            "auteur": _borner(str(c.get("auteur") or ""), MAX_AUTEUR), "date": c.get("date") or ""}


def version(depot: str, v: dict) -> dict:
    return {"depot": depot, "nom": _borner(str(v.get("nom") or ""), MAX_VERSION),
            "titre": _borner(str(v.get("titre") or ""), MAX_VERSION), "sha": str(v.get("sha") or "")[:7],
            "release": bool(v.get("release")), "date": v.get("date") or ""}


def resultat_recherche(depot: str, item: dict, genre: str) -> dict:
    return {"depot": depot, "type": genre, **{k: v for k, v in resume(item).items() if k != "etiquettes"}}


def fusionner_versions(tags: list[dict], releases: list[dict]) -> list[dict]:
    """Tags ET releases fusionnés par nom ; la date d'une release prime. Triés du plus récent au plus ancien
    (sans date : en dernier, ordre d'origine)."""
    par_nom = {r["tag"]: r for r in releases}
    versions = [{"nom": t["nom"], "sha": t["sha"], "release": t["nom"] in par_nom,
                 "titre": (par_nom.get(t["nom"]) or {}).get("titre") or "",
                 "date": (par_nom.get(t["nom"]) or {}).get("date") or t.get("date") or ""} for t in tags]
    connus = {t["nom"] for t in tags}
    versions += [{"nom": r["tag"], "sha": "", "release": True, "titre": r.get("titre") or "", "date": r.get("date") or ""}
                 for r in releases if r["tag"] not in connus]
    return sorted(versions, key=lambda v: v["date"] or "", reverse=True)


class _Agregation:
    """Partagé par les deux backends : dépôt facultatif (vide = toute la liste blanche, bornée à MAX_DEPOTS)."""
    depots_autorises: list[str]

    def _cibles(self, depot: str) -> list[str]:
        if (depot or "").strip():
            return [verifier_depot(depot, self.depots_autorises)]
        return list(self.depots_autorises)

    def _agreger(self, depot: str, n: int, par_depot) -> tuple[list[dict], bool]:
        """`par_depot(nom)` -> (éléments de sortie avec clé « date », il_en_reste). Plusieurs dépôts : tri par date."""
        noms = self._cibles(depot)
        elements, reste = [], False
        for nom in noms:
            items, r = par_depot(nom)
            elements += items
            reste = reste or r
        if len(noms) > 1:
            elements.sort(key=lambda e: e.get("date") or "", reverse=True)
        return elements[:n], reste or len(elements) > n


# --- backend de test --------------------------------------------------------------------------------

class FixtureGithubBackend(_Agregation):
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

    def _lister_type(self, cle: str, depot: str, etat: str, limite, auteur: str) -> tuple[list[dict], bool]:
        verifier_etat(etat)
        n = borner_limite(limite)
        a = verifier_auteur(auteur).lower()

        def par_depot(nom):
            _, d = self._depot(nom)
            hits = sorted((i for i in d.get(cle) or [] if (etat == "all" or i["etat"] == etat)
                           and (not a or i["auteur"].lower() == a)), key=lambda i: i["numero"], reverse=True)
            return [{"depot": nom, **resume(i)} for i in hits[:n]], len(hits) > n
        return self._agreger(depot, n, par_depot)

    def lister_depots(self) -> list[dict]:
        sortie = []
        for nom in self.depots_autorises:
            contenu = self._depots.get(nom.lower())
            sortie.append(info_depot(nom, contenu.get("infos") or {}) if contenu is not None
                          else {"depot": nom, "erreur": "Dépôt introuvable."})
        return sortie

    def lister_commits(self, depot: str = "", branche: str = "", depuis: str = "", jusqu_a: str = "",
                       auteur: str = "", limite=LIMITE_DEFAUT) -> tuple[list[dict], bool]:
        n = borner_limite(limite)
        b = verifier_branche(branche, depot)
        debut, fin = lire_periode_github(depuis, jusqu_a)
        a = verifier_auteur(auteur).lower()

        def par_depot(nom):
            _, d = self._depot(nom)
            commits = d.get("commits") or {}
            br = b or (d.get("infos") or {}).get("branche_defaut") or "main"
            if br not in commits:
                if b:
                    raise ErreurOutil(f"Branche introuvable : {b}.")
                return [], False
            hits = sorted((c for c in commits[br] if (not a or c["auteur"].lower() == a)
                           and _dans_periode(c["date"], debut, fin)), key=lambda c: c["date"], reverse=True)
            return [commit(nom, c) for c in hits[:n]], len(hits) > n
        return self._agreger(depot, n, par_depot)

    def lister_versions(self, depot: str, version_cherchee: str = "", limite=LIMITE_DEFAUT) -> tuple[list[dict], bool]:
        nom, d = self._depot(depot)
        n = borner_limite(limite)
        v = _borner((version_cherchee or "").strip(), MAX_VERSION)
        versions = [x for x in fusionner_versions(d.get("tags") or [], d.get("releases") or [])
                    if not v or tous_les_mots(x["nom"], v)]
        return [version(nom, x) for x in versions[:n]], len(versions) > n

    def chercher_issues(self, requete: str, depot: str = "", etat: str = "all", limite=LIMITE_DEFAUT
                        ) -> tuple[list[dict], bool]:
        mots = nettoyer_requete(requete)
        verifier_etat(etat)
        n = borner_limite(limite)

        def par_depot(nom):
            _, d = self._depot(nom)
            hits = [resultat_recherche(nom, i, genre)
                    for cle, genre in (("issues", "issue"), ("pull_requests", "pull_request"))
                    for i in d.get(cle) or []
                    if (etat == "all" or i["etat"] == etat) and tous_les_mots(f"{i['titre']} {i.get('corps') or ''}", mots)]
            hits.sort(key=lambda h: h["date"], reverse=True)
            return hits[:n], len(hits) > n
        return self._agreger(depot, n, par_depot)

    @staticmethod
    def _trouver(items: list[dict], numero, genre: str) -> dict:
        n = lire_numero(numero)
        for i in items:
            if i["numero"] == n:
                return i
        raise ErreurOutil(f"{genre} introuvable : n° {n}.")

    def lister_issues(self, depot: str = "", etat: str = "open", limite=LIMITE_DEFAUT, auteur: str = ""
                      ) -> tuple[list[dict], bool]:
        """Renvoie (issues, il_en_reste). depot vide = tous les dépôts de la liste blanche."""
        return self._lister_type("issues", depot, etat, limite, auteur)

    def lister_pull_requests(self, depot: str = "", etat: str = "open", limite=LIMITE_DEFAUT, auteur: str = ""
                             ) -> tuple[list[dict], bool]:
        return self._lister_type("pull_requests", depot, etat, limite, auteur)

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


def _iso_utc(dt: datetime, tz: tzinfo | None) -> str:
    """Heure locale (naïve) -> « AAAA-MM-JJTHH:MM:SSZ » (format since/until de l'API commits)."""
    locale = dt.replace(tzinfo=tz) if tz else dt.astimezone()
    return locale.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _depot_de_l_url(url: str) -> str:
    """« https://api.github.com/repos/demo/projet-y » -> « demo/projet-y »."""
    morceaux = str(url or "").rstrip("/").split("/")
    return "/".join(morceaux[-2:]) if len(morceaux) >= 2 else ""


class GithubBackend(_Agregation):
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

    def _get(self, chemin: str, params: dict | None = None, *, introuvable: str, vide: tuple[int, ...] = ()):
        """Seule requête du backend (GET). Messages d'erreur fixes : jamais le corps de la réponse ni le jeton.
        `vide` : statuts qui signifient « aucun résultat » (ex. 409 = dépôt vide pour les commits)."""
        import httpx
        try:
            reponse = self._http().get(chemin, params=params)
        except httpx.HTTPError:
            raise ErreurOutil("Connexion à GitHub impossible. Réessayer plus tard.") from None
        statut = reponse.status_code
        if statut in vide:
            return [], reponse
        if statut == 422:                       # paramètre refusé (ex. recherche) : message fixe
            raise ErreurOutil("Requête refusée par GitHub : simplifier les paramètres.")
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

    @staticmethod
    def _inaccessible(nom: str) -> str:
        return f"Dépôt introuvable ou inaccessible avec ce jeton : {nom}."

    @_reponse_attendue
    def lister_issues(self, depot: str = "", etat: str = "open", limite=LIMITE_DEFAUT, auteur: str = ""
                      ) -> tuple[list[dict], bool]:
        verifier_etat(etat)
        n = borner_limite(limite)
        a = verifier_auteur(auteur)

        def par_depot(nom):
            _, base = self._base(nom)
            params = {"state": etat, "per_page": PAR_PAGE_MAX} | ({"creator": a} if a else {})
            # l'API des issues renvoie aussi les PR (clé pull_request) : on les retire, d'où une page plus large
            donnees, reponse = self._get(f"{base}/issues", params, introuvable=self._inaccessible(nom))
            issues = [self._item(j) | {"nb_commentaires": int(j.get("comments") or 0)}
                      for j in donnees or [] if "pull_request" not in j]
            return [{"depot": nom, **resume(i)} for i in issues[:n]], len(issues) > n or _page_suivante(reponse)
        return self._agreger(depot, n, par_depot)

    @_reponse_attendue
    def lister_pull_requests(self, depot: str = "", etat: str = "open", limite=LIMITE_DEFAUT, auteur: str = ""
                             ) -> tuple[list[dict], bool]:
        verifier_etat(etat)
        n = borner_limite(limite)
        a = verifier_auteur(auteur).lower()

        def par_depot(nom):
            _, base = self._base(nom)
            # /pulls n'a pas de filtre d'auteur (doc 2026-03-10) : filtre local sur une page plus large
            donnees, reponse = self._get(f"{base}/pulls", {"state": etat, "per_page": PAR_PAGE_MAX if a else n},
                                         introuvable=self._inaccessible(nom))
            # la liste des PR ne donne pas le nombre de commentaires : None (inconnu) plutôt qu'un 0 faux
            prs = [self._item(j) | {"nb_commentaires": None} for j in donnees or []
                   if not a or _login(j).lower() == a]
            return [{"depot": nom, **resume(p)} for p in prs[:n]], len(prs) > n or _page_suivante(reponse)
        return self._agreger(depot, n, par_depot)

    @_reponse_attendue
    def lister_depots(self) -> list[dict]:
        """Un appel GET /repos/{o}/{r} par dépôt de la LISTE BLANCHE (jamais /user/repos)."""
        sortie = []
        for nom in self.depots_autorises:
            _, base = self._base(nom)
            try:
                j, _ = self._get(base, introuvable=self._inaccessible(nom))
            except ErreurOutil as exc:              # un dépôt inaccessible n'empêche pas de lister les autres
                sortie.append({"depot": nom, "erreur": str(exc)})
                continue
            sortie.append(info_depot(nom, {
                "description": j.get("description"), "langage": j.get("language"), "topics": j.get("topics"),
                "dernier_push": _date_locale(j.get("pushed_at"), self._tz), "prive": j.get("private"),
                "branche_defaut": j.get("default_branch")}))
        return sortie

    @_reponse_attendue
    def lister_commits(self, depot: str = "", branche: str = "", depuis: str = "", jusqu_a: str = "",
                       auteur: str = "", limite=LIMITE_DEFAUT) -> tuple[list[dict], bool]:
        n = borner_limite(limite)
        b = verifier_branche(branche, depot)
        debut, fin = lire_periode_github(depuis, jusqu_a)
        a = verifier_auteur(auteur)
        params = {"per_page": n}
        if b:
            params["sha"] = b
        if debut:
            params["since"] = _iso_utc(debut, self._tz)
        if fin:                                         # borne exclue -> « until » inclusif à la seconde près
            params["until"] = _iso_utc(fin - timedelta(seconds=1), self._tz)
        if a:
            params["author"] = a

        def par_depot(nom):
            _, base = self._base(nom)
            donnees, reponse = self._get(f"{base}/commits", params, vide=(409,),     # 409 : dépôt vide
                                         introuvable=self._inaccessible(nom) if not b else f"Branche introuvable : {b}.")
            commits = [commit(nom, {"sha": j.get("sha"), "message": (j.get("commit") or {}).get("message"),
                                    "auteur": _login({"user": j.get("author")})
                                    or ((j.get("commit") or {}).get("author") or {}).get("name"),
                                    "date": _date_locale(((j.get("commit") or {}).get("author") or {}).get("date"),
                                                         self._tz)})
                       for j in (donnees or [])[:n]]
            return commits, _page_suivante(reponse)
        return self._agreger(depot, n, par_depot)

    @_reponse_attendue
    def lister_versions(self, depot: str, version_cherchee: str = "", limite=LIMITE_DEFAUT) -> tuple[list[dict], bool]:
        nom, base = self._base(depot)
        n = borner_limite(limite)
        v = _borner((version_cherchee or "").strip(), MAX_VERSION)
        tags_j, rep_tags = self._get(f"{base}/tags", {"per_page": PAR_PAGE_MAX}, introuvable=self._inaccessible(nom))
        rel_j, rep_rel = self._get(f"{base}/releases", {"per_page": PAR_PAGE_MAX}, introuvable=self._inaccessible(nom))
        tags = [{"nom": str(t.get("name") or ""), "sha": str((t.get("commit") or {}).get("sha") or "")}
                for t in tags_j or []]
        # notes de release (body) JAMAIS lues ; brouillons ignorés
        releases = [{"tag": str(r.get("tag_name") or ""), "titre": str(r.get("name") or ""),
                     "date": _date_locale(r.get("published_at") or r.get("created_at"), self._tz)}
                    for r in rel_j or [] if not r.get("draft")]
        avec_release = {r["tag"] for r in releases}
        tags = [t for t in tags if not v or tous_les_mots(t["nom"], v)]
        # un tag n'a pas de date dans /tags : un appel GET /commits/{sha} par tag, borné à MAX_DATES_TAGS
        # sha validé (40 hexadécimaux) avant de le mettre dans l'URL : défense en profondeur
        for t in [t for t in tags if t["nom"] not in avec_release and _SHA.fullmatch(t["sha"])][:min(n, MAX_DATES_TAGS)]:
            try:
                j, _ = self._get(f"{base}/commits/{quote(t['sha'], safe='')}", {"per_page": 1},
                                 introuvable=self._inaccessible(nom))
                t["date"] = _date_locale((((j or {}).get("commit") or {}).get("committer") or {}).get("date"), self._tz)
            except ErreurOutil:
                t["date"] = ""
        versions = [x for x in fusionner_versions(tags, releases) if not v or tous_les_mots(x["nom"], v)]
        reste = len(versions) > n or _page_suivante(rep_tags) or _page_suivante(rep_rel)
        return [version(nom, x) for x in versions[:n]], reste

    @_reponse_attendue
    def chercher_issues(self, requete: str, depot: str = "", etat: str = "all", limite=LIMITE_DEFAUT
                        ) -> tuple[list[dict], bool]:
        """GET /search/issues. Les qualificateurs repo: sont construits ICI depuis la liste blanche (contrôlée) ;
        le texte du modèle est réduit à des mots simples. Deux requêtes (is:issue, is:pr) : certains jetons
        exigent l'un des deux. Limite de débit de la recherche : 30 requêtes/min (réponse 403/429 gérée)."""
        mots = nettoyer_requete(requete)
        verifier_etat(etat)
        n = borner_limite(limite)
        cibles = self._cibles(depot)
        qualif = " ".join(f"repo:{c}" for c in cibles) + ("" if etat == "all" else f" state:{etat}")
        autorises = {c.lower(): c for c in cibles}
        resultats, reste = [], False
        for genre, filtre in (("issue", "is:issue"), ("pull_request", "is:pr")):
            j, _ = self._get("/search/issues", {"q": f"{mots} {qualif} {filtre}", "sort": "updated", "order": "desc",
                                                 "per_page": n}, introuvable="Recherche indisponible.")
            items = (j or {}).get("items") or []
            reste = reste or int((j or {}).get("total_count") or 0) > len(items)
            for it in items:
                nom = autorises.get(_depot_de_l_url(it.get("repository_url")).lower())
                if nom is None:                     # défense en profondeur : jamais hors liste blanche
                    continue
                resultats.append(resultat_recherche(nom, self._item(it) | {"nb_commentaires": int(it.get("comments") or 0)},
                                                    genre))
        resultats.sort(key=lambda r: r["date"], reverse=True)
        return resultats[:n], reste or len(resultats) > n

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

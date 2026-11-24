"""Filtres de recherche mail, communs aux deux backends (fixture et Gmail).

Fonctions pures, sans réseau, sans consigne de sécurité. Les dates sont en HEURE LOCALE de l'utilisateur,
sans fuseau (naïves) : c'est celle que l'utilisateur et le modèle manipulent.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

LIMITE_DEFAUT = 5
LIMITE_MAX = 50
ANNEE_MIN = 2000      # aucun mail utile avant ; évite aussi les dates d'avant 1970 (OSError sous Windows)
ANNEE_MAX = 2100

_FORMAT_JOUR = "%Y-%m-%d"
# (format, durée ajoutée pour obtenir la borne EXCLUE d'un « jusqu'à » inclusif)
_FORMATS_HEURE = (
    ("%Y-%m-%dT%H:%M", timedelta(minutes=1)),
    ("%Y-%m-%d %H:%M", timedelta(minutes=1)),
    ("%Y-%m-%dT%H:%M:%S", timedelta(seconds=1)),
)


@dataclass(frozen=True)
class Filtres:
    requete: str = ""
    expediteur: str = ""
    sujet: str = ""
    depuis: datetime | None = None   # borne INCLUSE (heure locale)
    avant: datetime | None = None    # borne EXCLUE (heure locale)
    non_lus: bool = False
    limite: int = LIMITE_DEFAUT


def _plier(texte: str) -> str:
    """Minuscules sans accents : « Hibá » et « hiba » se correspondent."""
    sans_accents = "".join(c for c in unicodedata.normalize("NFKD", texte or "") if not unicodedata.combining(c))
    return sans_accents.casefold()


def _tous_les_mots(texte: str, recherche: str) -> bool:
    """Vrai si CHAQUE mot de `recherche` apparaît dans `texte` (sans casse ni accents)."""
    cible = _plier(texte)
    return all(mot in cible for mot in _plier(recherche).split())


def _verifier_annee(dt: datetime, valeur: str, nom: str) -> datetime:
    """Années bornées : hors plage, timestamp() lève OSError sous Windows (avant 1970) ou OverflowError (an 9999),
    que le serveur ne transforme pas en message lisible."""
    if not ANNEE_MIN <= dt.year <= ANNEE_MAX:
        raise ValueError(f"Date hors plage pour « {nom} » : {valeur!r}. Années acceptées : {ANNEE_MIN} à {ANNEE_MAX}.")
    return dt


def _lire_borne(valeur: str, nom: str, *, fin: bool) -> datetime | None:
    v = (valeur or "").strip()
    if not v:
        return None
    if len(v) == 10:
        try:
            jour = datetime.strptime(v, _FORMAT_JOUR)
        except ValueError:
            jour = None
        if jour is not None:
            _verifier_annee(jour, valeur, nom)
            return jour + timedelta(days=1) if fin else jour      # « jusqu'à » une date = toute la journée
    for fmt, pas in _FORMATS_HEURE:
        try:
            dt = datetime.strptime(v, fmt)
        except ValueError:
            continue
        _verifier_annee(dt, valeur, nom)
        return dt + pas if fin else dt
    raise ValueError(
        f"Date invalide pour « {nom} » : {valeur!r}. "
        "Format attendu : AAAA-MM-JJ ou AAAA-MM-JJTHH:MM (ex. 2026-11-22 ou 2026-11-22T14:30)."
    )


def lire_periode(depuis: str = "", jusqu_a: str = "") -> tuple[datetime | None, datetime | None]:
    """(borne incluse, borne EXCLUE) en heure locale, ou None. Partagé avec le serveur GitHub (lister_commits)."""
    borne_debut = _lire_borne(depuis, "depuis", fin=False)
    borne_fin = _lire_borne(jusqu_a, "jusqu_a", fin=True)
    if borne_debut and borne_fin and borne_debut >= borne_fin:
        raise ValueError("« depuis » doit être antérieur à « jusqu_a ».")
    return borne_debut, borne_fin


def construire_filtres(requete: str = "", expediteur: str = "", sujet: str = "", depuis: str = "",
                       jusqu_a: str = "", non_lus: bool = False, limite: int = LIMITE_DEFAUT) -> Filtres:
    """Valide les arguments de l'outil. Les messages d'erreur sont lus par le modèle : clairs et sans contenu de mail."""
    borne_debut, borne_fin = lire_periode(depuis, jusqu_a)
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        raise ValueError("« limite » doit être un nombre entier.") from None
    return Filtres(requete=(requete or "").strip(), expediteur=(expediteur or "").strip(),
                   sujet=(sujet or "").strip(), depuis=borne_debut, avant=borne_fin,
                   non_lus=bool(non_lus), limite=max(1, min(limite, LIMITE_MAX)))


def correspond(f: Filtres, *, de: str, sujet: str, texte: str, date: datetime | None, lu: bool,
               verifier_requete: bool = True) -> bool:
    """Un mail satisfait-il TOUS les filtres ? `texte` = corps ou aperçu."""
    if f.non_lus and lu:
        return False
    if f.expediteur and not _tous_les_mots(de, f.expediteur):
        return False
    if f.sujet and not _tous_les_mots(sujet, f.sujet):
        return False
    if f.depuis or f.avant:
        if date is None:
            return False
        if f.depuis and date < f.depuis:
            return False
        if f.avant and date >= f.avant:
            return False
    if verifier_requete and f.requete and not _tous_les_mots(f"{sujet} {de} {texte}", f.requete):
        return False
    return True


def lire_date_fixture(valeur: str) -> datetime | None:
    """« 2026-10-16T18:20 » (format des mails de test) -> datetime locale."""
    try:
        return datetime.strptime(valeur, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def date_locale(internal_date_ms, tz: tzinfo | None = None) -> datetime | None:
    """internalDate Gmail (ms depuis 1970, UTC) -> heure locale sans fuseau. tz=None : fuseau de la machine."""
    try:
        return datetime.fromtimestamp(int(internal_date_ms) / 1000, tz).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _epoch(dt: datetime, tz: tzinfo | None) -> int:
    return int((dt.replace(tzinfo=tz) if tz else dt).timestamp())


def _mots_sans_operateurs(texte: str) -> str:
    """Garde lettres, chiffres, @ . - _ et retire les mots-opérateurs (OR, AND, NOT) et les « - » de négation.
    Ni « : » ni guillemets ni parenthèses : requete, expediteur et sujet ne peuvent pas ajouter d'opérateur
    Gmail (in:anywhere, label:, from:...) ni élargir la recherche ; seuls des mots simples sont envoyés."""
    mots = []
    for mot in re.sub(r"[^\w@.\-]", " ", texte or "").split():
        mot = mot.lstrip("-")
        if mot and mot.upper() not in ("OR", "AND", "NOT"):
            mots.append(mot)
    return " ".join(mots)


# Noms publics, réutilisés par le serveur GitHub (recherche et filtres) : une seule implémentation.
mots_sans_operateurs = _mots_sans_operateurs
tous_les_mots = _tous_les_mots


def requete_gmail(f: Filtres, tz: tzinfo | None = None) -> str:
    """Requête Gmail (syntaxe de la boîte de recherche) équivalente aux filtres.
    Les bornes de date ont 60 s de marge : le filtre exact est refait en Python sur internalDate."""
    parts: list[str] = []
    if f.requete and _mots_sans_operateurs(f.requete):      # D2 : plus jamais envoyée telle quelle
        parts.append(_mots_sans_operateurs(f.requete))
    if f.expediteur and _mots_sans_operateurs(f.expediteur):
        parts.append(f"from:({_mots_sans_operateurs(f.expediteur)})")
    if f.sujet and _mots_sans_operateurs(f.sujet):
        parts.append(f"subject:({_mots_sans_operateurs(f.sujet)})")
    if f.depuis:
        parts.append(f"after:{_epoch(f.depuis, tz) - 60}")
    if f.avant:
        parts.append(f"before:{_epoch(f.avant, tz) + 60}")
    if f.non_lus:
        parts.append("is:unread")
    return " ".join(parts)
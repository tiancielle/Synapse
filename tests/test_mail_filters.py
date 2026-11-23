"""Filtres de recherche mail (fonctions pures, sans réseau, sans compte)."""
from datetime import datetime, timezone

import pytest
from mail_filters import (LIMITE_DEFAUT, LIMITE_MAX, Filtres, construire_filtres, correspond, date_locale,
                          lire_date_fixture, requete_gmail)

UTC = timezone.utc


# --- lecture des dates -----------------------------------------------------------------------

def test_a_date_alone_means_the_whole_day():
    f = construire_filtres(depuis="2026-11-22", jusqu_a="2026-11-22")
    assert f.depuis == datetime(2026, 11, 22, 0, 0)
    assert f.avant == datetime(2026, 11, 23, 0, 0)            # borne exclue : le 22 novembre est inclus en entier


def test_date_with_time_is_inclusive_to_the_minute():
    f = construire_filtres(depuis="2026-11-22T09:00", jusqu_a="2026-11-22T12:30")
    assert f.depuis == datetime(2026, 11, 22, 9, 0)
    assert f.avant == datetime(2026, 11, 22, 12, 31)          # 12:30 inclus


@pytest.mark.parametrize("valeur", ["2026-11-22 14:30", "2026-11-22T14:30:00"])
def test_other_common_time_formats_are_accepted(valeur):
    assert construire_filtres(depuis=valeur).depuis == datetime(2026, 11, 22, 14, 30)


@pytest.mark.parametrize("champ,valeur", [("depuis", "hier"), ("jusqu_a", "22/11/2026"), ("depuis", "2026-13-40"),
                                          ("jusqu_a", "aujourd'hui")])
def test_invalid_dates_give_a_clear_message_naming_the_field(champ, valeur):
    with pytest.raises(ValueError, match=f"« {champ} ».*AAAA-MM-JJ"):
        construire_filtres(**{champ: valeur})


@pytest.mark.parametrize("champ,valeur", [("depuis", "1960-01-01"), ("jusqu_a", "9999-12-31"),
                                          ("depuis", "1969-12-31T23:59"), ("jusqu_a", "2101-01-01T00:00")])
def test_out_of_range_years_give_a_clear_message_instead_of_a_crash(champ, valeur):
    # sans borne : OSError (Windows, avant 1970) ou OverflowError (an 9999), réduites à « Error executing tool »
    with pytest.raises(ValueError, match=f"hors plage pour « {champ} ».*2000 à 2100"):
        construire_filtres(**{champ: valeur})


def test_inverted_range_is_rejected():
    with pytest.raises(ValueError, match="antérieur"):
        construire_filtres(depuis="2026-11-23", jusqu_a="2026-11-22")


def test_limit_default_and_bounds():
    assert construire_filtres().limite == LIMITE_DEFAUT == 5
    assert construire_filtres(limite=500).limite == LIMITE_MAX == 50
    assert construire_filtres(limite=0).limite == 1
    with pytest.raises(ValueError, match="entier"):
        construire_filtres(limite="beaucoup")


# --- correspondance -------------------------------------------------------------------------

MAIL = dict(de="Nour Testeur <nour@exemple.test>", sujet="Offre ingénieur IA", texte="Poste à Rabat",
            date=datetime(2026, 11, 22, 10, 15), lu=False)


def ok(**filtres):
    return correspond(construire_filtres(**filtres), **MAIL)


def test_no_filter_matches_everything():
    assert ok()


def test_sender_matches_name_or_address_without_case_or_accents():
    assert ok(expediteur="nour") and ok(expediteur="TESTEUR") and ok(expediteur="exemple.test")
    assert ok(expediteur="testeur nour")                       # ordre des mots indifférent
    assert not ok(expediteur="sara")


def test_subject_and_keywords_use_every_word():
    assert ok(sujet="ingenieur ia") and not ok(sujet="ingenieur java")
    assert ok(requete="rabat poste") and not ok(requete="rabat casablanca")


def test_date_filters_respect_the_day_and_the_hour():
    assert ok(depuis="2026-11-22", jusqu_a="2026-11-22")
    assert not ok(depuis="2026-11-23")
    assert not ok(jusqu_a="2026-11-21")
    assert ok(depuis="2026-11-22T10:00", jusqu_a="2026-11-22T10:15")        # 10:15 inclus
    assert not ok(depuis="2026-11-22T10:16")
    assert not ok(jusqu_a="2026-11-22T10:14")


def test_a_mail_without_a_date_never_passes_a_date_filter():
    f = construire_filtres(depuis="2026-11-22")
    assert not correspond(f, **{**MAIL, "date": None})


def test_unread_only():
    assert ok(non_lus=True)
    assert not correspond(construire_filtres(non_lus=True), **{**MAIL, "lu": True})


def test_filters_combine_with_and():
    assert ok(expediteur="nour", sujet="offre", depuis="2026-11-22", non_lus=True)
    assert not ok(expediteur="nour", sujet="offre", depuis="2026-11-23")


def test_requete_check_can_be_skipped_when_the_server_already_applied_it():
    f = construire_filtres(requete="motintrouvable")
    assert not correspond(f, **MAIL)
    assert correspond(f, verifier_requete=False, **MAIL)


# --- dates des deux backends ----------------------------------------------------------------

def test_fixture_dates_and_gmail_internal_dates_become_local_naive_datetimes():
    assert lire_date_fixture("2026-10-16T18:20") == datetime(2026, 10, 16, 18, 20)
    assert lire_date_fixture("n'importe quoi") is None
    assert date_locale("1795384187000", UTC) == datetime(2026, 11, 22, 21, 49, 47)
    assert date_locale(None, UTC) is None


# --- requête Gmail ---------------------------------------------------------------------------

def test_gmail_query_translates_every_filter():
    f = construire_filtres(requete="stage", expediteur="Nour Testeur", sujet="offre", depuis="2026-11-22",
                           jusqu_a="2026-11-22", non_lus=True)
    q = requete_gmail(f, UTC)
    debut = int(datetime(2026, 11, 22, tzinfo=UTC).timestamp())
    assert q == f"stage from:(Nour Testeur) subject:(offre) after:{debut - 60} before:{debut + 86400 + 60} is:unread"


def test_gmail_query_is_empty_without_filters_and_never_lets_the_model_inject_operators():
    assert requete_gmail(Filtres(), UTC) == ""
    q = requete_gmail(construire_filtres(expediteur='x) OR in:anywhere (', sujet='"label:secret" -spam'), UTC)
    assert q == "from:(x in anywhere) subject:(label secret spam)"       # ni « : » ni guillemets ni OR ni négation
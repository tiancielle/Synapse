"""Repères de dates donnés au modèle, pour qu'il n'ait pas à calculer « demain » lui-même."""
from datetime import date, timedelta

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
DATE_DEMO = date(2026, 10, 18)     # « aujourd'hui » dans le calendrier de test (un dimanche)


def reperes_dates(jour_ref: date) -> str:
    def nom(d: date) -> str:
        return f"{JOURS[d.weekday()]} {d.isoformat()}"

    suivants = [jour_ref + timedelta(days=i) for i in range(1, 8)]
    return (f"{nom(jour_ref)} (aujourd'hui). Demain = {nom(suivants[0])}. Après-demain = {nom(suivants[1])}. "
            f"Jours à venir : " + ", ".join(nom(d) for d in suivants))
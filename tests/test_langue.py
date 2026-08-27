"""Textes de l'interface, en francais et en anglais.

Le vocabulaire anglais reprend celui de Wispr Flow, pris comme reference par
l'utilisateur : ce n'est pas une traduction mot a mot du francais.
"""

from datetime import date

import pytest

from murmur import config as cfg, langue as module_langue


@pytest.fixture
def mot():
    return module_langue.Traducteur(langue="fr")


@pytest.fixture
def word():
    return module_langue.Traducteur(langue="en")


# --------------------------------------------------------------------------
# Table
# --------------------------------------------------------------------------

def test_chaque_cle_existe_dans_les_deux_langues():
    """Une cle absente d'une langue afficherait la cle elle-meme."""
    for cle, formes in module_langue.TEXTES.items():
        for code in module_langue.LANGUES:
            assert code in formes, f"{cle} : {code} manquant"


def test_chaque_forme_accordee_existe_dans_les_deux_langues():
    for cle, formes in module_langue.NOMBRES.items():
        for code in module_langue.LANGUES:
            assert code in formes, f"{cle} : {code} manquant"
            assert len(formes[code]) == 2


def test_les_champs_a_substituer_se_correspondent():
    """Un « {raccourci} » d'un cote et « {shortcut} » de l'autre leverait une
    erreur de formatage a l'affichage, dans une langue seulement."""
    import re

    for cle, formes in module_langue.TEXTES.items():
        champs = {code: set(re.findall(r"\{(\w+)\}", texte))
                  for code, texte in formes.items()}
        references = list(champs.values())
        assert all(c == references[0] for c in champs.values()), cle


def test_une_cle_inconnue_se_remarque(mot):
    """Affichee telle quelle, elle saute aux yeux ; une chaine vide passerait
    inapercue."""
    assert mot("cle.qui.nexiste.pas") == "cle.qui.nexiste.pas"


def test_le_vocabulaire_anglais_est_celui_de_la_reference(word):
    assert word("page.dictees") == "Dictation"
    assert word("page.statistiques") == "Insights"
    assert word("page.dictionnaire") == "Dictionary"
    assert word("reglages") == "Settings"


def test_le_francais_reste_du_francais(mot):
    assert mot("page.dictees") == "Dictées"
    assert mot("page.statistiques") == "Statistiques"


# --------------------------------------------------------------------------
# Accords
# --------------------------------------------------------------------------

def test_zero_prend_le_singulier_en_francais(mot):
    assert mot.nombre(0, "dictee") == "0 dictée"
    assert mot.nombre(1, "dictee") == "1 dictée"
    assert mot.nombre(2, "dictee") == "2 dictées"


def test_zero_prend_le_pluriel_en_anglais(word):
    """La meme donnee, deux regles : c'est la raison d'etre de `au_pluriel`."""
    assert word.nombre(0, "dictee") == "0 dictations"
    assert word.nombre(1, "dictee") == "1 dictation"
    assert word.nombre(2, "dictee") == "2 dictations"


def test_pluriel_irregulier(word):
    assert word.nombre(3, "correction") == "3 fixes"


def test_une_forme_invariable_le_reste(word):
    """« day streak » ne s'accorde pas : « 3 days streak » n'existe pas."""
    assert word.nombre(3, "jour_serie") == "3 day streak"


# --------------------------------------------------------------------------
# Nombres et dates
# --------------------------------------------------------------------------

def test_separateur_de_milliers(mot, word):
    assert mot.milliers(12480) == "12 480"
    assert word.milliers(12480) == "12,480"


def test_separateur_decimal(mot, word):
    assert mot.decimal(4.83) == "4,8"
    assert word.decimal(4.83) == "4.8"


def test_jour_long(mot, word):
    jour = date(2026, 8, 21)
    assert mot.jour_long(jour) == "vendredi 21 août"
    assert word.jour_long(jour) == "Friday, August 21"


def test_jour_relatif(mot, word):
    aujourdhui = date(2026, 8, 21)
    assert mot.jour_relatif(aujourdhui, aujourdhui) == "aujourd'hui"
    assert word.jour_relatif(aujourdhui, aujourdhui) == "today"
    assert word.jour_relatif(date(2026, 8, 20), aujourdhui) == "yesterday"


def test_les_noms_de_jours_suivent_le_calendrier(mot, word):
    """Un decalage d'un rang passerait autrement inapercu."""
    for numero in range(1, 32):
        jour = date(2026, 3, numero)
        attendus = ("lundi", "mardi", "mercredi", "jeudi", "vendredi",
                    "samedi", "dimanche")
        assert module_langue.JOURS["fr"][jour.weekday()] == \
            attendus[jour.weekday()]
        assert module_langue.JOURS["en"][jour.weekday()] == \
            jour.strftime("%A")


def test_les_mois_courts_se_distinguent():
    """Juin et juillet donnent tous deux « jui » sur trois lettres, ce qui
    rend une frise illisible."""
    for code in module_langue.LANGUES:
        courts = module_langue.MOIS_COURTS[code]
        assert len(set(courts)) == 12, code
        assert len(courts) == len(module_langue.MOIS[code])


# --------------------------------------------------------------------------
# Reglage
# --------------------------------------------------------------------------

def test_la_langue_vient_de_la_configuration(donnees):
    conf = cfg.charger()
    traducteur = module_langue.Traducteur(conf)
    conf.definir("interface.langue", "fr")
    assert traducteur.langue == "fr"

    # Relue a chaque appel : figee a la construction, elle survivrait au
    # changement de reglage.
    conf.definir("interface.langue", "en")
    assert traducteur.langue == "en"


def test_une_langue_inconnue_retombe_sur_le_defaut():
    assert module_langue.Traducteur(langue="klingon").langue == \
        module_langue.DEFAUT


def test_la_configuration_refuse_une_langue_inconnue(donnees):
    conf = cfg.charger()
    conf.definir("interface.langue", "klingon")
    with pytest.raises(cfg.ErreurConfig):
        cfg._valider(conf.valeurs)


# --------------------------------------------------------------------------
# Heures
# --------------------------------------------------------------------------

@pytest.mark.parametrize("heure, minute, attendu", [
    (0, 5, "12:05 am"),
    (9, 30, "9:30 am"),
    (12, 0, "12:00 pm"),
    (14, 13, "2:13 pm"),
    (23, 59, "11:59 pm"),
])
def test_lheure_anglaise_est_sur_douze_heures(word, heure, minute, attendu):
    from datetime import datetime
    assert word.heure(datetime(2026, 8, 23, heure, minute)) == attendu


@pytest.mark.parametrize("heure, minute, attendu", [
    (0, 5, "00:05"),
    (9, 30, "09:30"),
    (14, 13, "14:13"),
])
def test_lheure_francaise_reste_sur_vingt_quatre(mot, heure, minute, attendu):
    from datetime import datetime
    assert mot.heure(datetime(2026, 8, 23, heure, minute)) == attendu


def test_midi_et_minuit_ne_se_confondent_pas(word):
    """« 12:00 am » et « 12:00 pm » : l'erreur classique est de rendre zero
    heure comme « 0:00 am »."""
    from datetime import datetime
    assert word.heure(datetime(2026, 8, 23, 0, 0)) == "12:00 am"
    assert word.heure(datetime(2026, 8, 23, 12, 0)) == "12:00 pm"

"""Rechargement des raccourcis a chaud.

Modifier un raccourci ne doit pas obliger a relancer l'application. Windows
lie une combinaison au fil qui l'a enregistree : il faut rendre l'ancienne
avant de prendre la nouvelle, et savoir revenir en arriere si elle est prise.
"""

import pytest

from murmur import config as cfg, hotkeys
from murmur.app import Application


@pytest.fixture
def application(donnees):
    conf = cfg.charger()
    conf.definir("moteur.port", 8767)
    app = Application(conf)
    try:
        yield app
    finally:
        app.historique.fermer()


# --------------------------------------------------------------------------
# Declaration
# --------------------------------------------------------------------------

def test_les_combinaisons_viennent_de_la_configuration(application):
    combinaisons = application._combinaisons()
    assert combinaisons["dictee (maintien)"] == \
        application.conf["raccourcis.maintien"]
    assert combinaisons["dictee (bascule)"] == \
        application.conf["raccourcis.bascule"]
    assert "apprendre" in combinaisons


def test_le_lexique_desactive_retire_son_raccourci(application):
    application.conf.definir("lexique.actif", False)
    assert "apprendre" not in application._combinaisons()


def test_les_combinaisons_peuvent_etre_imposees(application):
    """Indispensable au repli : la configuration contient alors les valeurs
    fautives, et les relire ferait echouer le gestionnaire de secours."""
    gestionnaire = hotkeys.Gestionnaire()
    application._declarer_raccourcis(gestionnaire, {
        "dictee (maintien)": "ctrl+alt+f13",
        "dictee (bascule)": "ctrl+alt+f14",
    })
    combinaisons = {r.combinaison for r in gestionnaire._raccourcis.values()}
    assert combinaisons == {"ctrl+alt+f13", "ctrl+alt+f14"}


# --------------------------------------------------------------------------
# Rechargement reel
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_un_nouveau_raccourci_prend_effet_immediatement(application):
    application.conf.definir("raccourcis.maintien", "ctrl+alt+shift+f13")
    application.conf.definir("raccourcis.bascule", "ctrl+alt+shift+f14")
    application.conf.definir("raccourcis.apprendre", "ctrl+alt+shift+f15")
    application._declarer_raccourcis(application.raccourcis)
    application.raccourcis.demarrer()

    try:
        application.conf.definir("raccourcis.maintien", "ctrl+alt+shift+f16")
        application.recharger_raccourcis()

        actives = {r.combinaison
                   for r in application.raccourcis._raccourcis.values()}
        assert "ctrl+alt+shift+f16" in actives
        assert "ctrl+alt+shift+f13" not in actives
        assert application.raccourcis.en_cours
    finally:
        application.raccourcis.arreter()


@pytest.mark.materiel
def test_recharger_avec_la_meme_combinaison_ne_se_bloque_pas(application):
    """L'ancienne doit etre rendue AVANT de reprendre la nouvelle.

    Sans cet ordre, reprendre une combinaison inchangee echouerait contre
    elle-meme.
    """
    application.conf.definir("raccourcis.maintien", "ctrl+alt+shift+f17")
    application.conf.definir("raccourcis.bascule", "ctrl+alt+shift+f18")
    application.conf.definir("raccourcis.apprendre", "ctrl+alt+shift+f19")
    application._declarer_raccourcis(application.raccourcis)
    application.raccourcis.demarrer()

    try:
        application.recharger_raccourcis()   # rien n'a change
        assert application.raccourcis.en_cours
    finally:
        application.raccourcis.arreter()


@pytest.mark.materiel
def test_un_conflit_retablit_les_raccourcis_precedents(application):
    """Mieux vaut des raccourcis obsoletes que plus de raccourcis du tout."""
    application.conf.definir("raccourcis.maintien", "ctrl+alt+shift+f20")
    application.conf.definir("raccourcis.bascule", "ctrl+alt+shift+f21")
    application.conf.definir("raccourcis.apprendre", "ctrl+alt+shift+f22")
    application._declarer_raccourcis(application.raccourcis)
    application.raccourcis.demarrer()

    # Un tiers s'empare de la combinaison visee.
    intrus = hotkeys.Gestionnaire()
    intrus.ajouter("intrus", "ctrl+alt+shift+f23", debut=lambda: None)
    intrus.demarrer()

    try:
        application.conf.definir("raccourcis.maintien", "ctrl+alt+shift+f23")
        with pytest.raises(hotkeys.ErreurRaccourci):
            application.recharger_raccourcis()

        actives = {r.combinaison
                   for r in application.raccourcis._raccourcis.values()}
        assert "ctrl+alt+shift+f20" in actives, "l'ancien jeu n'a pas ete remis"
        assert application.raccourcis.en_cours, "plus aucun raccourci actif"
    finally:
        intrus.arreter()
        application.raccourcis.arreter()


@pytest.mark.materiel
def test_le_rechargement_prend_en_compte_le_lexique_desactive(application):
    application.conf.definir("raccourcis.maintien", "ctrl+alt+shift+f13")
    application.conf.definir("raccourcis.bascule", "ctrl+alt+shift+f14")
    application.conf.definir("raccourcis.apprendre", "ctrl+alt+shift+f15")
    application._declarer_raccourcis(application.raccourcis)
    application.raccourcis.demarrer()

    try:
        application.conf.definir("lexique.actif", False)
        application.recharger_raccourcis()
        noms = {r.nom for r in application.raccourcis._raccourcis.values()}
        assert "apprendre" not in noms
    finally:
        application.raccourcis.arreter()

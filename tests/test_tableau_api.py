"""Le pont entre la page et Python.

L'enregistrement des reglages est le seul endroit du tableau de bord qui
puisse rendre l'application inutilisable : une configuration invalide ecrite
sur le disque la ferait echouer au demarrage suivant, sans explication et sans
moyen de revenir en arriere depuis l'interface. La validation a donc lieu
**avant** l'ecriture, et c'est ce que verifient la plupart des tests ici.
"""

import pytest

from murmur import config as configuration
from murmur.tableau import api as module_api, donnees


@pytest.fixture
def pont(donnees):
    passerelle = module_api.Api()
    yield passerelle
    passerelle.fermer_ressources()


@pytest.fixture(autouse=True)
def canal_muet(monkeypatch):
    """Aucun test n'a a joindre l'application reelle.

    Sans cela, chaque enregistrement tenterait une connexion : le test
    dependrait de ce qui tourne sur la machine, et enverrait pour de bon la
    commande a un Murmur en service. Les deux tests qui s'interessent au canal
    reposent leur propre doublure par-dessus celle-ci.
    """
    from murmur import canal
    monkeypatch.setattr(canal, "envoyer",
                        lambda *_a, **_k: {"ok": False, "erreur": "absent"})


def _valeurs(pont, **remplacements) -> dict:
    """Le formulaire tel que la page le renverrait, une valeur changee."""
    formulaire = pont.reglages()
    valeurs = {champ["chemin"]: champ["valeur"]
               for section in formulaire["sections"]
               for champ in section["champs"]}
    valeurs.update(remplacements)
    return valeurs


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------

def test_le_formulaire_se_lit_sans_fenetre(pont):
    formulaire = pont.reglages()
    assert [s["cle"] for s in formulaire["sections"]] == list(donnees.SECTIONS)
    assert formulaire["enregistrer"]


def test_le_formulaire_relit_la_configuration_a_chaque_fois(pont):
    """L'application vit dans l'autre processus et a pu changer un reglage
    depuis l'ouverture de la fenetre."""
    pont.reglages()
    conf = configuration.charger()
    conf.definir("raccourcis.maintien", "ctrl+alt+j")
    conf.sauvegarder()

    valeurs = _valeurs(pont)
    assert valeurs["raccourcis.maintien"] == "ctrl+alt+j"


# --------------------------------------------------------------------------
# Ecriture
# --------------------------------------------------------------------------

def test_un_reglage_valide_est_ecrit_sur_le_disque(pont):
    reponse = pont.enregistrer_reglages(
        _valeurs(pont, **{"raccourcis.bascule": "ctrl+alt+shift+m"}))
    assert reponse["ok"]
    assert configuration.charger()["raccourcis.bascule"] == "ctrl+alt+shift+m"


def test_un_raccourci_impossible_est_refuse_avant_l_ecriture(pont):
    """C'est tout l'interet de valider ici : ecrit puis relu au demarrage, il
    ferait echouer l'application sans qu'on puisse le corriger."""
    avant = configuration.charger()["raccourcis.maintien"]
    reponse = pont.enregistrer_reglages(
        _valeurs(pont, **{"raccourcis.maintien": "ctrl+alt+pas_une_touche"}))

    assert not reponse["ok"]
    assert reponse["erreur"] and reponse["titre"]
    assert configuration.charger()["raccourcis.maintien"] == avant


def test_un_reglage_invalide_est_refuse_avant_l_ecriture(pont):
    avant = configuration.charger()["interface.langue"]
    reponse = pont.enregistrer_reglages(
        _valeurs(pont, **{"interface.langue": "klingon"}))

    assert not reponse["ok"]
    assert configuration.charger()["interface.langue"] == avant


def test_un_refus_n_ecrit_aucun_des_autres_reglages(pont):
    """Le refus porte sur le formulaire entier : enregistrer la moitie des
    valeurs laisserait une configuration que l'utilisateur n'a jamais voulue."""
    avant = configuration.charger().valeurs
    pont.enregistrer_reglages(_valeurs(pont, **{
        "vad.actif": not configuration.charger()["vad.actif"],
        "raccourcis.maintien": "ctrl+alt+pas_une_touche",
    }))
    assert configuration.charger().valeurs == avant


def test_le_demarrage_automatique_ne_va_pas_dans_le_fichier(pont, monkeypatch):
    """Il est confie au systeme — un raccourci depose dans un dossier — et ne
    doit pas se retrouver ecrit comme un reglage ordinaire."""
    from murmur import systeme
    demande = []
    monkeypatch.setattr(systeme, "definir_demarrage_auto", demande.append)
    monkeypatch.setattr(systeme, "demarrage_auto_actif", lambda: False)

    assert pont.enregistrer_reglages(
        _valeurs(pont, **{donnees.DEMARRAGE: True}))["ok"]

    assert demande == [True]
    assert "systeme" not in configuration.charger().valeurs


def test_un_demarrage_refuse_par_le_systeme_n_annule_pas_l_enregistrement(
        pont, monkeypatch):
    """Le raccourci de demarrage peut echouer — dossier protege, disque plein.
    Les autres reglages, eux, n'ont aucune raison d'etre perdus."""
    from murmur import systeme

    def refuser(_actif):
        raise OSError("dossier protege")

    monkeypatch.setattr(systeme, "definir_demarrage_auto", refuser)
    monkeypatch.setattr(systeme, "demarrage_auto_actif", lambda: False)

    reponse = pont.enregistrer_reglages(_valeurs(pont, **{
        donnees.DEMARRAGE: True, "vad.actif": False}))

    assert reponse["ok"]
    assert reponse["avertissement"]
    assert configuration.charger()["vad.actif"] is False


def test_la_langue_change_les_textes_rendus_ensuite(pont):
    """La page redemande ses mots apres l'enregistrement : le traducteur du
    pont doit deja parler la nouvelle langue."""
    pont.enregistrer_reglages(_valeurs(pont, **{"interface.langue": "fr"}))
    assert pont.textes()["page.statistiques"] == "Statistiques"

    pont.enregistrer_reglages(_valeurs(pont, **{"interface.langue": "en"}))
    assert pont.textes()["page.statistiques"] == "Insights"


def test_l_application_est_prevenue(pont, monkeypatch):
    """Un raccourci change doit etre repris a l'instant : l'application vit
    dans l'autre processus et ne relit pas le fichier d'elle-meme."""
    from murmur import canal
    envoyes = []
    monkeypatch.setattr(canal, "envoyer",
                        lambda commande, args: envoyes.append(commande)
                        or {"ok": True})

    assert pont.enregistrer_reglages(_valeurs(pont))["prevenu"]
    assert envoyes == ["reglages_modifies"]


def test_l_application_absente_n_empeche_pas_d_enregistrer(pont, monkeypatch):
    """Le tableau de bord s'ouvre seul : personne n'ecoute a l'autre bout.

    L'absence est simulee plutot que subie : laisser l'appel partir pour de
    bon ferait dependre le test de ce qui tourne sur la machine — et, si
    Murmur tournait vraiment, lui enverrait la commande.
    """
    from murmur import canal
    monkeypatch.setattr(canal, "envoyer",
                        lambda *_a, **_k: {"ok": False, "erreur": "absent"})

    reponse = pont.enregistrer_reglages(_valeurs(pont))
    assert reponse["ok"]
    assert reponse["prevenu"] is False


# --------------------------------------------------------------------------
# Commandes de fenetre
# --------------------------------------------------------------------------

def test_les_commandes_de_fenetre_sans_gestion_ne_levent_pas(pont):
    """La page peut appeler avant que la fenetre n'existe."""
    assert pont.reduire() == {"ok": False}
    assert pont.agrandir() == {"agrandie": False}
    assert pont.deplacer() == {"ok": False}
    assert pont.redimensionner_haut() == {"ok": False}


def test_les_commandes_de_fenetre_passent_par_la_gestion(donnees):
    class Gestion:
        def __init__(self):
            self.appels = []

        def reduire(self):
            self.appels.append("reduire")
            return True

        def basculer_agrandissement(self):
            self.appels.append("agrandir")
            return {"agrandie": True}

        def commencer_deplacement(self):
            self.appels.append("deplacer")
            return True

        def commencer_redimensionnement_haut(self):
            self.appels.append("haut")
            return True

    gestion = Gestion()
    pont = module_api.Api(gestion)
    try:
        assert pont.reduire() == {"ok": True}
        assert pont.agrandir() == {"agrandie": True}
        assert pont.deplacer() == {"ok": True}
        assert pont.redimensionner_haut() == {"ok": True}
        assert gestion.appels == ["reduire", "agrandir", "deplacer", "haut"]
    finally:
        pont.fermer_ressources()


def test_le_pont_ne_montre_que_des_commandes(donnees):
    """pywebview dresse la liste des methodes en parcourant les attributs
    publics de l'objet, et descend dans chacun. Une fenetre gardee en clair
    l'entrainait jusque dans les objets .NET de WebView2, ou la comparaison
    d'un rectangle levait une erreur de type.
    """
    pont = module_api.Api()
    try:
        publics = [nom for nom in vars(pont) if not nom.startswith("_")]
        assert publics == [], f"attributs exposes : {publics}"
    finally:
        pont.fermer_ressources()

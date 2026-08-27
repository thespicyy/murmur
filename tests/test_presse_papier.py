"""T2.3 — sauvegarde et restauration du presse-papier.

Le presse-papier est une ressource globale du systeme : ces tests le
manipulent reellement, et le rendent tel qu'ils l'ont trouve.
"""

import time

import pytest

from murmur import config as cfg
from murmur import inject


@pytest.fixture
def conf(donnees):
    configuration = cfg.charger()
    # Delai raccourci : on ne colle nulle part dans ces tests, inutile
    # d'attendre le quart de seconde prevu pour un vrai collage.
    configuration.definir("injection.delai_restauration_ms", 30)
    return configuration


@pytest.fixture
def presse_papier_preserve():
    try:
        avant = inject.contenu_presse_papier()
    except inject.ErreurInjection:
        avant = None
    yield
    if avant is not None and avant.texte is not None:
        try:
            inject.ecrire_presse_papier(avant.texte)
        except inject.ErreurInjection:
            pass


# --------------------------------------------------------------------------
# Description du contenu — logique pure
# --------------------------------------------------------------------------

def test_presse_papier_vide_na_rien_a_perdre():
    contenu = inject.ContenuPressePapier(texte=None, formats=(), noms=())
    assert contenu.vide
    assert contenu.restaurable
    assert contenu.perte is None


def test_texte_seul_est_restaurable_sans_perte():
    contenu = inject.ContenuPressePapier(
        texte="bonjour", formats=(13,), noms=("du texte",))
    assert contenu.restaurable
    assert contenu.perte is None


def test_texte_enrichi_signale_la_perte_de_mise_en_forme():
    """Copier depuis Word puis dicter fait perdre le formatage : le dire."""
    contenu = inject.ContenuPressePapier(
        texte="bonjour", formats=(13, 49500),
        noms=("du texte", "Rich Text Format"))
    assert contenu.restaurable
    perte = contenu.perte
    assert perte and "mise en forme" in perte
    assert "Rich Text Format" in perte


def test_image_est_signalee_comme_non_restaurable():
    """Le cas identifie au PLAN : on previent plutot que de prendre en silence."""
    contenu = inject.ContenuPressePapier(
        texte=None, formats=(2, 8), noms=("une image", "une image"))
    assert not contenu.restaurable
    perte = contenu.perte
    assert perte and "une image" in perte
    assert "perdu" in perte


def test_fichiers_sont_signales():
    contenu = inject.ContenuPressePapier(
        texte=None, formats=(15,), noms=("des fichiers",))
    assert not contenu.restaurable
    assert "des fichiers" in contenu.perte


# --------------------------------------------------------------------------
# Lecture reelle
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_contenu_lit_le_texte_et_ses_formats(presse_papier_preserve):
    inject.ecrire_presse_papier("valeur temoin")
    contenu = inject.contenu_presse_papier()
    assert contenu.texte == "valeur temoin"
    assert inject.CF_UNICODETEXT in contenu.formats
    assert contenu.restaurable


@pytest.mark.materiel
def test_presse_papier_vide_est_reconnu(presse_papier_preserve):
    inject.vider_presse_papier()
    contenu = inject.contenu_presse_papier()
    assert contenu.vide
    assert contenu.texte is None
    assert contenu.perte is None


# --------------------------------------------------------------------------
# Restauration — le critere de fin de T2.3
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_le_texte_precedent_est_rendu_apres_une_dictee(conf,
                                                       presse_papier_preserve,
                                                       monkeypatch):
    """Critere de fin : le presse-papier retrouve son contenu.

    Le collage lui-meme est neutralise : on verifie la sauvegarde et la
    restauration, pas l'arrivee du texte, deja couverte par T1.5.
    """
    monkeypatch.setattr(inject, "_envoyer", lambda evenements: None)

    inject.ecrire_presse_papier("contenu precieux")
    resultat = inject.Injecteur(conf).injecter("texte dicte")

    assert inject.lire_presse_papier() == "contenu precieux"
    assert resultat.restaure
    assert resultat.avertissement is None


@pytest.mark.materiel
def test_un_presse_papier_vide_le_reste(conf, presse_papier_preserve,
                                        monkeypatch):
    """Ne pas laisser la dictee trainer dans un presse-papier qui etait vide."""
    monkeypatch.setattr(inject, "_envoyer", lambda evenements: None)

    inject.vider_presse_papier()
    inject.Injecteur(conf).injecter("texte dicte")

    assert inject.contenu_presse_papier().vide


@pytest.mark.materiel
def test_la_dictee_est_bien_passee_par_le_presse_papier(conf, monkeypatch,
                                                        presse_papier_preserve):
    """Verifie qu'on colle bien la dictee, et pas autre chose.

    Sans ce controle, une restauration trop hative passerait inapercue : le
    test precedent serait vert alors que l'utilisateur collerait l'ancien
    contenu a la place de sa dictee.
    """
    vu = []

    def espion(evenements):
        vu.append(inject.lire_presse_papier())

    monkeypatch.setattr(inject, "_envoyer", espion)

    inject.ecrire_presse_papier("ancien")
    inject.Injecteur(conf).injecter("la dictee")

    assert vu == ["la dictee"], \
        "au moment du collage, le presse-papier doit contenir la dictee"
    assert inject.lire_presse_papier() == "ancien"


@pytest.mark.materiel
def test_restauration_desactivee_laisse_la_dictee(conf, presse_papier_preserve,
                                                  monkeypatch):
    monkeypatch.setattr(inject, "_envoyer", lambda evenements: None)
    conf.definir("injection.restaurer_presse_papier", False)

    inject.ecrire_presse_papier("ancien")
    resultat = inject.Injecteur(conf).injecter("la dictee")

    assert inject.lire_presse_papier() == "la dictee"
    assert not resultat.restaure


@pytest.mark.materiel
def test_la_duree_mesuree_exclut_l_attente_de_restauration(conf, monkeypatch,
                                                           presse_papier_preserve):
    """La latence annoncee doit refleter ce que l'utilisateur percoit."""
    monkeypatch.setattr(inject, "_envoyer", lambda evenements: None)
    conf.definir("injection.delai_restauration_ms", 300)

    inject.ecrire_presse_papier("ancien")
    debut = time.perf_counter()
    resultat = inject.Injecteur(conf).injecter("la dictee")
    total = (time.perf_counter() - debut) * 1000

    assert total >= 300, "la restauration doit bien avoir attendu"
    assert resultat.duree_pose_ms < 250, (
        f"la duree annoncee ({resultat.duree_pose_ms:.0f} ms) inclut l'attente "
        f"de restauration")


@pytest.mark.materiel
def test_un_presse_papier_illisible_nempeche_pas_la_dictee(conf, monkeypatch):
    """Le texte compte plus que la sauvegarde de ce qu'il remplace."""
    colles = []
    monkeypatch.setattr(inject, "_envoyer", lambda e: colles.append(1))
    monkeypatch.setattr(
        inject, "contenu_presse_papier",
        lambda: (_ for _ in ()).throw(inject.ErreurInjection("occupe")))

    resultat = inject.Injecteur(conf).injecter("la dictee")

    assert colles, "la dictee doit avoir ete collee malgre tout"
    assert "sauvegarde" in resultat.avertissement


@pytest.mark.materiel
def test_un_echec_de_restauration_ne_casse_pas_la_dictee(conf, monkeypatch,
                                                         presse_papier_preserve):
    monkeypatch.setattr(inject, "_envoyer", lambda e: None)
    inject.ecrire_presse_papier("ancien")

    injecteur = inject.Injecteur(conf)
    monkeypatch.setattr(
        inject, "ecrire_presse_papier",
        lambda t: (_ for _ in ()).throw(inject.ErreurInjection("verrouille"))
        if t == "ancien" else None)

    # Ne doit pas lever : la dictee est posee, le reste est secondaire.
    injecteur.injecter("la dictee")


@pytest.mark.materiel
def test_deux_dictees_enchainees_restaurent_le_bon_contenu(conf, monkeypatch,
                                                           presse_papier_preserve):
    """Le verrou doit empecher deux restaurations de se marcher dessus."""
    monkeypatch.setattr(inject, "_envoyer", lambda e: None)
    injecteur = inject.Injecteur(conf)

    inject.ecrire_presse_papier("origine")
    injecteur.injecter("premiere dictee")
    injecteur.injecter("seconde dictee")

    assert inject.lire_presse_papier() == "origine"

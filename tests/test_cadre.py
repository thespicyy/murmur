"""Le cadre de la fenetre : ce que Windows cesse de fournir sans bandeau.

Le coeur de ce fichier tient en un test — `test_le_retrait_du_bandeau_ne_coute
_ni_le_redimensionnement_ni_l_ancrage`. C'est la difference exacte entre les
deux voies possibles, et celle qui avait ete prise a tort : le mode « sans
cadre » de pywebview ote aussi le cadre epais, donc les poignees et
l'agrandissement, tandis que retirer `WS_CAPTION` seul les laisse tous.

Le glisser est eprouve avec une source d'entree scriptee, jamais avec de vrais
clics : synthetiser un glisser reviendrait a prendre la souris de
l'utilisateur, et le moindre geste de sa part melangerait ses mouvements aux
consignes du test.

Une fenetre Tk sert de sujet : elle porte un vrai descripteur Windows, ce qui
suffit — aucun de ces appels ne connait la difference entre une fenetre Tk et
une fenetre WebView2.
"""

import time
import tkinter as tk

import pytest

from murmur import cadre


@pytest.fixture
def fenetre(racine_tk):
    f = tk.Toplevel(racine_tk)
    f.geometry("640x480+220+180")
    f.update()
    _stabiliser(f)
    yield f
    f.destroy()


@pytest.fixture
def hwnd(fenetre):
    from murmur import chrome
    return chrome.descripteur(fenetre)


def _stabiliser(fenetre, secondes: float = 0.35) -> None:
    """Laisse le gestionnaire de bureau rattraper la geometrie.

    `DwmGetWindowAttribute` ne repond pas a la question « ou est cette fenetre
    maintenant ? » mais « ou l'ai-je composee la derniere fois ? ». Sur une
    fenetre qui vient de naitre ou de bouger, il rend encore l'ancien
    rectangle — mesure : 802 px de large annonces pour une fenetre de 656.
    """
    fin = time.monotonic() + secondes
    while time.monotonic() < fin:
        fenetre.update()
        time.sleep(0.01)


class EntreeScriptee(cadre.SourceEntree):
    """Un glisser ecrit d'avance : positions successives, puis relachement."""

    def __init__(self, positions):
        self._positions = list(positions)
        self._rang = 0

    def curseur(self):
        rang = min(self._rang, len(self._positions) - 1)
        return self._positions[rang]

    def bouton_enfonce(self):
        enfonce = self._rang < len(self._positions)
        self._rang += 1
        return enfonce


def _milieu(hwnd) -> tuple[int, int]:
    """Un point franchement au milieu de l'ecran portant la fenetre.

    Les glissers du test partent d'ici, jamais de la position reelle de la
    souris : posee par hasard contre un bord, celle-ci armerait une zone
    d'ancrage et la fenetre finirait ancree au lieu de simplement deplacee.
    C'est arrive, et le test a d'abord semble denoncer un defaut du code.
    """
    x, y, largeur, hauteur = cadre.zone_travail(hwnd)
    return x + largeur // 2, y + hauteur // 2


def _attendre(gestion, fenetre, secondes: float = 3.0) -> None:
    """Attend la fin du suivi **en pompant la file de messages**.

    Sans cela, le test se bloque avec le code qu'il eprouve : `SetWindowPos`
    est synchrone — il poste `WM_WINDOWPOSCHANGING` a la procedure de la
    fenetre et attend la reponse. Cette procedure tourne sur le fil qui a cree
    la fenetre, c'est-a-dire celui du test ; s'il dort au lieu de traiter ses
    messages, le fil de suivi l'attend et le test attend le fil de suivi.
    """
    fin = time.monotonic() + secondes
    while gestion._occupe and time.monotonic() < fin:
        fenetre.update()
        time.sleep(0.005)
    assert not gestion._occupe, "le suivi ne s'est pas termine"
    _stabiliser(fenetre)


# --------------------------------------------------------------------------
# Le bandeau, et ce qu'il ne doit pas emporter
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_le_retrait_du_bandeau_ne_coute_ni_le_redimensionnement_ni_l_ancrage(
        hwnd):
    """La raison d'etre de ce module.

    Le tableau de bord naissait « sans cadre » : la fenetre perdait alors le
    cadre epais avec le bandeau, et ne pouvait plus etre ni redimensionnee par
    les bords, ni ancree, ni agrandie. En ne retirant que `WS_CAPTION`, tout
    cela survit — et c'est cela qu'on verifie, plutot que de le supposer.
    """
    assert cadre.retirer_bandeau(hwnd)

    styles = cadre.styles_conserves(hwnd)
    assert not styles["bandeau"], "le bandeau est reste"
    assert styles["cadre_redimensionnable"], "les poignees de bord sont perdues"
    assert styles["bouton_agrandir"], "l'agrandissement est perdu"
    assert styles["menu_systeme"], "la barre des taches et Alt+Tab sont perdus"
    assert styles["bouton_reduire"], "la reduction est perdue"


@pytest.mark.materiel
def test_retirer_le_bandeau_deux_fois_ne_change_rien(hwnd):
    cadre.retirer_bandeau(hwnd)
    premier = cadre.styles_conserves(hwnd)
    cadre.retirer_bandeau(hwnd)
    assert cadre.styles_conserves(hwnd) == premier


@pytest.mark.materiel
def test_la_procedure_derivee_se_pose_et_se_retire(hwnd):
    """Elle rend a la page les pixels de cadre restes en haut."""
    derivee = cadre.Subclasse(hwnd)
    assert derivee.poser()
    assert derivee.active
    derivee._retablir()


@pytest.mark.materiel
def test_la_procedure_derivee_ne_se_pose_pas_deux_fois(hwnd):
    """Se poser sur soi-meme ferait boucler la chaine des procedures."""
    derivee = cadre.Subclasse(hwnd)
    derivee.poser()
    ancien = derivee._ancien
    derivee.poser()
    assert derivee._ancien == ancien
    derivee._retablir()


# --------------------------------------------------------------------------
# Geometrie
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_le_cadre_visible_tient_dans_le_rectangle_systeme(hwnd, fenetre):
    """`GetWindowRect` compte en plus la bordure de redimensionnement
    transparente : le rectangle peint est donc toujours contenu dans lui."""
    _stabiliser(fenetre)
    fx, fy, flarg, fhaut = cadre.rectangle(hwnd)
    vx, vy, vlarg, vhaut = cadre.cadre_visible(hwnd)
    assert fx <= vx and fy <= vy
    assert fx + flarg >= vx + vlarg
    assert fy + fhaut >= vy + vhaut


@pytest.mark.materiel
def test_les_marges_invisibles_restent_plausibles(hwnd):
    for marge in cadre.marges_invisibles(hwnd):
        assert 0 <= marge <= cadre.MARGE_MAX


def test_les_marges_du_systeme_sont_nulles_en_haut():
    """La bordure transparente n'existe que sur les cotes et en bas."""
    assert cadre.marges_systeme()[1] == 0


@pytest.mark.materiel
def test_poser_visible_vise_le_rectangle_peint(hwnd, fenetre):
    """C'est toute la difference avec `poser` : viser le rectangle systeme
    laisserait apparaitre le bureau de l'epaisseur de la bordure invisible."""
    cadre.retirer_bandeau(hwnd)
    cible = (240, 160, 700, 520)
    cadre.poser_visible(hwnd, *cible)
    _stabiliser(fenetre)

    obtenu = cadre.cadre_visible(hwnd)
    for attendu, mesure in zip(cible, obtenu):
        assert abs(attendu - mesure) <= 2, f"{cible} vise, {obtenu} obtenu"


@pytest.mark.materiel
def test_la_zone_de_travail_exclut_la_barre_des_taches(hwnd):
    """Sans cela, une fenetre agrandie passerait sous la barre des taches."""
    _, _, largeur, hauteur = cadre.zone_travail(hwnd)
    assert largeur > 0 and hauteur > 0
    ecran, travail = cadre.ecrans_du_point(*cadre.rectangle(hwnd)[:2])
    assert travail[3] <= ecran[3]


# --------------------------------------------------------------------------
# Zones d'ancrage
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_le_bord_gauche_arme_la_moitie_gauche():
    (mx, my, _mlarg, mhaut), (tx, ty, tlarg, thaut) = \
        cadre.ecrans_du_point(0, 0)
    zone, rect = cadre.zone_ancrage(mx, my + mhaut // 2)
    assert zone == "moitie gauche"
    assert rect == (tx, ty, tlarg // 2, thaut)


@pytest.mark.materiel
def test_le_bord_droit_arme_la_moitie_droite():
    (mx, my, mlarg, mhaut), (tx, ty, tlarg, _thaut) = \
        cadre.ecrans_du_point(0, 0)
    zone, rect = cadre.zone_ancrage(mx + mlarg - 1, my + mhaut // 2)
    assert zone == "moitie droite"
    assert rect[0] == tx + tlarg - tlarg // 2


@pytest.mark.materiel
def test_le_coin_haut_gauche_arme_un_quart():
    (mx, my, _mlarg, mhaut), _travail = cadre.ecrans_du_point(0, 0)
    zone, rect = cadre.zone_ancrage(mx, my + int(mhaut * 0.05))
    assert zone == "quart haut gauche"
    assert rect[3] < cadre.ecrans_du_point(0, 0)[1][3]


@pytest.mark.materiel
def test_le_bord_haut_arme_le_plein_ecran():
    (mx, my, mlarg, _mhaut), travail = cadre.ecrans_du_point(0, 0)
    zone, rect = cadre.zone_ancrage(mx + mlarg // 2, my)
    assert zone == "plein ecran"
    assert rect == travail


@pytest.mark.materiel
def test_le_milieu_de_l_ecran_n_arme_rien():
    (mx, my, mlarg, mhaut), _travail = cadre.ecrans_du_point(0, 0)
    assert cadre.zone_ancrage(mx + mlarg // 2, my + mhaut // 2) == (None, None)


# --------------------------------------------------------------------------
# Glisser, ancrage, agrandissement
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_un_glisser_deplace_la_fenetre_du_meme_ecart(hwnd, fenetre):
    """Le deplacement suit le curseur exactement : un facteur d'echelle
    oublie se verrait ici, la fenetre partant plus vite que la main."""
    cadre.retirer_bandeau(hwnd)
    depart = cadre.rectangle(hwnd)[:2]
    curseur = _milieu(hwnd)

    gestion = cadre.Gestion(lambda: hwnd, EntreeScriptee(
        [curseur, (curseur[0] + 60, curseur[1] + 40)] * 3))
    assert gestion.commencer_deplacement()
    _attendre(gestion, fenetre)

    arrivee = cadre.rectangle(hwnd)[:2]
    assert (arrivee[0] - depart[0], arrivee[1] - depart[1]) == (60, 40)
    gestion.fermer()


@pytest.mark.materiel
def test_un_glisser_jusqu_au_bord_gauche_ancre_a_la_moitie(hwnd, fenetre):
    cadre.retirer_bandeau(hwnd)
    (mx, my, _mlarg, mhaut), travail = cadre.ecrans_du_point(*_milieu(hwnd))
    bord = (mx, my + mhaut // 2)

    gestion = cadre.Gestion(lambda: hwnd,
                            EntreeScriptee([_milieu(hwnd), bord, bord]))
    assert gestion.commencer_deplacement()
    _attendre(gestion, fenetre)

    assert gestion.dernier_ancrage == "moitie gauche"
    x, y, largeur, hauteur = cadre.cadre_visible(hwnd)
    assert abs(largeur - travail[2] // 2) <= 2
    assert abs(hauteur - travail[3]) <= 2
    gestion.fermer()


@pytest.mark.materiel
def test_l_apercu_previent_avant_que_la_fenetre_ne_saute(hwnd, fenetre):
    """Sans lui, l'ancrage se produirait sans prevenir au relachement."""
    cadre.retirer_bandeau(hwnd)
    (mx, my, _mlarg, mhaut), _t = cadre.ecrans_du_point(*_milieu(hwnd))
    bord = (mx, my + mhaut // 2)

    gestion = cadre.Gestion(lambda: hwnd,
                            EntreeScriptee([_milieu(hwnd), bord, bord]))
    gestion.commencer_deplacement()
    _attendre(gestion, fenetre)

    # Le compteur ne retient que les apercus reellement affiches : compter
    # les tentatives laissait passer une fenetre d'apercu qui ne se creait
    # jamais — c'est arrive, un descripteur de module tronque a 32 bits.
    assert gestion.apercus_montres >= 1
    assert not gestion.apercu.visible(), "l'apercu est reste a l'ecran"
    gestion.fermer()


@pytest.mark.materiel
def test_un_glisser_au_milieu_n_ancre_pas(hwnd, fenetre):
    cadre.retirer_bandeau(hwnd)
    milieu = _milieu(hwnd)

    gestion = cadre.Gestion(lambda: hwnd,
                            EntreeScriptee([milieu, milieu, milieu]))
    gestion.commencer_deplacement()
    _attendre(gestion, fenetre)

    assert gestion.dernier_ancrage is None
    assert gestion.apercus_montres == 0
    gestion.fermer()


@pytest.mark.materiel
def test_deux_glissers_ne_se_chevauchent_pas(hwnd, fenetre):
    """Deux fils qui poseraient la meme fenetre se disputeraient sa position."""
    gestion = cadre.Gestion(lambda: hwnd, EntreeScriptee([_milieu(hwnd)] * 40))
    assert gestion.commencer_deplacement()
    assert not gestion.commencer_deplacement()
    _attendre(gestion, fenetre)
    gestion.fermer()


@pytest.mark.materiel
def test_l_agrandissement_couvre_la_zone_de_travail_et_pas_plus(hwnd, fenetre):
    """Confie a l'etat « agrandi » du systeme, il deborderait de la largeur du
    cadre sur chaque cote et recouvrirait la barre des taches."""
    cadre.retirer_bandeau(hwnd)
    gestion = cadre.Gestion(lambda: hwnd)

    assert gestion.basculer_agrandissement() == {"agrandie": True}
    travail = cadre.zone_travail(hwnd)
    for attendu, mesure in zip(travail, cadre.cadre_visible(hwnd)):
        assert abs(attendu - mesure) <= 2
    gestion.fermer()


@pytest.mark.materiel
def test_l_agrandissement_rend_la_geometrie_d_avant(hwnd):
    cadre.retirer_bandeau(hwnd)
    gestion = cadre.Gestion(lambda: hwnd)
    avant = cadre.rectangle(hwnd)

    gestion.basculer_agrandissement()
    assert gestion.basculer_agrandissement() == {"agrandie": False}

    assert cadre.rectangle(hwnd) == avant
    gestion.fermer()


@pytest.mark.materiel
def test_glisser_une_fenetre_agrandie_la_ramene_a_sa_taille(hwnd, fenetre):
    """Comme le ferait un bandeau ordinaire : la fenetre reprend sa taille et
    reste sous le curseur, au lieu de se trainer en plein ecran."""
    cadre.retirer_bandeau(hwnd)
    gestion = cadre.Gestion(lambda: hwnd)
    avant = cadre.rectangle(hwnd)[2:]
    gestion.basculer_agrandissement()

    milieu = _milieu(hwnd)
    gestion._entree = EntreeScriptee([milieu, milieu])
    gestion.commencer_deplacement()
    _attendre(gestion, fenetre)

    assert cadre.rectangle(hwnd)[2:] == avant
    assert not gestion.agrandie
    gestion.fermer()


@pytest.mark.materiel
def test_le_redimensionnement_par_le_haut_garde_le_bas_en_place(hwnd, fenetre):
    """C'est ce qui distingue un redimensionnement d'un deplacement."""
    cadre.retirer_bandeau(hwnd)
    x, y, largeur, hauteur = cadre.rectangle(hwnd)
    bas = y + hauteur
    cible = (x + 5, y + 80)

    gestion = cadre.Gestion(lambda: hwnd, EntreeScriptee([cible, cible]))
    assert gestion.commencer_redimensionnement_haut()
    _attendre(gestion, fenetre)

    nx, ny, nlargeur, nhauteur = cadre.rectangle(hwnd)
    assert ny + nhauteur == bas
    assert nlargeur == largeur
    gestion.fermer()


@pytest.mark.materiel
def test_le_redimensionnement_par_le_haut_garde_une_hauteur_minimale(hwnd, fenetre):
    """Sans cette borne, la fenetre se replierait sur elle-meme et il n'y
    aurait plus de bord a saisir pour la rouvrir."""
    cadre.retirer_bandeau(hwnd)
    _x, _y, _largeur, hauteur = cadre.rectangle(hwnd)
    bas = cadre.rectangle(hwnd)[1] + hauteur
    tres_bas = (0, bas + 400)

    gestion = cadre.Gestion(lambda: hwnd, EntreeScriptee([tres_bas] * 2))
    gestion.commencer_redimensionnement_haut()
    _attendre(gestion, fenetre)

    assert cadre.rectangle(hwnd)[3] >= cadre.Gestion.HAUTEUR_MINI
    gestion.fermer()


# --------------------------------------------------------------------------
# Sans fenetre
# --------------------------------------------------------------------------

def test_les_commandes_sans_fenetre_ne_levent_pas():
    """Le descripteur n'existe pas avant l'affichage : les commandes doivent
    repondre non, pas tomber."""
    gestion = cadre.Gestion(lambda: None)
    assert gestion.hwnd is None
    assert not gestion.preparer()
    assert not gestion.reduire()
    assert not gestion.montrer()
    assert not gestion.commencer_deplacement()
    assert gestion.basculer_agrandissement() == {"agrandie": False}


def test_un_descripteur_qui_leve_est_traite_comme_absent():
    def casse():
        raise RuntimeError("fenetre detruite")

    assert cadre.Gestion(casse).hwnd is None

"""Symbole de la marque — geometrie et rendu."""

import tkinter as tk

import pytest

from murmur import marque


# --------------------------------------------------------------------------
# Geometrie
# --------------------------------------------------------------------------

def test_la_version_complete_a_deux_arcs():
    forme = marque.geometrie(96, compacte=False)
    assert len(forme["arcs"]) == 2
    assert not forme["compacte"]


def test_la_version_compacte_na_quun_arc():
    """A petite taille, deux arcs fins se confondent."""
    forme = marque.geometrie(16, compacte=True)
    assert len(forme["arcs"]) == 1
    assert forme["compacte"]


def test_les_petites_tailles_basculent_seules_en_compacte():
    assert marque.geometrie(16)["compacte"]
    assert not marque.geometrie(96)["compacte"]


def test_la_geometrie_respecte_les_proportions_du_kit():
    """A 96 pixels, on doit retrouver exactement les valeurs du SVG."""
    forme = marque.geometrie(96, compacte=False)
    assert forme["centre"] == 48
    assert forme["rayon_point"] == pytest.approx(7)
    assert forme["epaisseur"] == pytest.approx(6)
    rayons = sorted(rayon for rayon, _ in forme["arcs"])
    assert rayons == pytest.approx([26, 40])


def test_la_geometrie_est_proportionnelle():
    petite = marque.geometrie(48, compacte=False)
    grande = marque.geometrie(96, compacte=False)
    assert grande["rayon_point"] == pytest.approx(petite["rayon_point"] * 2)


def test_lepaisseur_ne_descend_jamais_sous_un_pixel():
    """Un trait de zero pixel ne se dessine pas du tout."""
    assert marque.geometrie(4)["epaisseur"] >= 1.0


def test_le_symbole_tient_dans_son_carre():
    """L'arc le plus large ne doit pas deborder du cadre."""
    for taille in (16, 32, 64, 96, 256):
        forme = marque.geometrie(taille)
        rayon_max = max(rayon for rayon, _ in forme["arcs"])
        debord = rayon_max + forme["epaisseur"] / 2
        assert debord <= forme["centre"] + 0.5, f"deborde a {taille} px"


# --------------------------------------------------------------------------
# Centrage optique
# --------------------------------------------------------------------------

def test_le_decalage_optique_pousse_vers_la_droite():
    """Les arcs occupent la gauche : le trace doit etre ramene vers la droite."""
    assert marque.decalage_optique(96, compacte=True) > 0
    assert marque.decalage_optique(96, compacte=False) > 0


def test_la_version_compacte_demande_plus_de_correction():
    """Elle n'a aucun arc a droite, son desequilibre est plus marque."""
    assert (marque.decalage_optique(96, compacte=True)
            > marque.decalage_optique(96, compacte=False))


def test_sans_arcs_aucune_correction_nest_necessaire():
    """Le point seul est deja symetrique."""
    assert marque.decalage_optique(96, compacte=True,
                                   avec_arcs=False) == pytest.approx(0)


def test_le_trace_est_optiquement_centre():
    """Mesure sur l'image reelle : la matiere doit etre repartie egalement.

    Le point est au centre geometrique, mais les arcs tirent l'ensemble vers
    la gauche. Sans correction, l'icone parait mal alignee dans la barre des
    taches — un defaut discret et permanent.
    """
    for compacte in (True, False):
        image = marque.dessiner_image(96, "#ffffff", "#ffffff",
                                      compacte=compacte)
        alpha = image.getchannel("A")
        colonnes = [x for x in range(96)
                    if any(alpha.getpixel((x, y)) > 128 for y in range(96))]
        milieu = (colonnes[0] + colonnes[-1]) / 2
        assert abs(milieu - 47.5) <= 1.5, (
            f"{'compacte' if compacte else 'complete'} : trace centre sur "
            f"{milieu:.1f} au lieu de 47.5")


def test_le_recentrage_peut_etre_desactive():
    centre = marque.dessiner_image(96, "#ffffff", "#ffffff", recentrer=True)
    brut = marque.dessiner_image(96, "#ffffff", "#ffffff", recentrer=False)
    assert centre.tobytes() != brut.tobytes()


# --------------------------------------------------------------------------
# Rendu image
# --------------------------------------------------------------------------

def test_limage_a_la_bonne_taille_et_un_fond_transparent():
    image = marque.dessiner_image(64, "#3fb950", "#ffffff")
    assert image.size == (64, 64)
    assert image.mode == "RGBA"
    assert image.getpixel((0, 0))[3] == 0, "le coin doit rester transparent"


def test_le_point_porte_sa_couleur():
    """Echantillonne le centre du point, non celui de l'image : le symbole est
    recentre optiquement, et son point n'est donc pas au milieu du carre.

    L'ancienne version visait le milieu de l'image et ne passait que par
    l'effet du crenelage — le trace lisse a decouvert l'erreur en tombant
    juste sur le bord du disque."""
    taille = 64
    image = marque.dessiner_image(taille, "#ff0000", "#0000ff")
    x = round(taille / 2 + marque.decalage_optique(taille))
    y = taille // 2

    rouge, vert, bleu, alpha = image.getpixel((x, y))
    assert alpha == 255
    assert rouge > 200 and vert < 60 and bleu < 60


def test_le_centre_du_point_est_bien_decale():
    """Sans ce controle, viser le mauvais pixel redeviendrait invisible."""
    assert marque.decalage_optique(64) > 0


def _pixels_opaques(image) -> int:
    """Compte les pixels visibles, via l'histogramme du canal alpha.

    `getdata()` ferait l'affaire mais disparait avec Pillow 14.
    """
    return sum(image.getchannel("A").histogram()[1:])


def test_sans_arcs_seul_le_point_subsiste():
    """C'est ainsi qu'on represente l'etat suspendu : plus d'ondes."""
    avec = marque.dessiner_image(64, "#ffffff", "#ffffff", avec_arcs=True)
    sans = marque.dessiner_image(64, "#ffffff", "#ffffff", avec_arcs=False)

    assert _pixels_opaques(sans) < _pixels_opaques(avec), \
        "les arcs n'ont pas disparu"
    assert _pixels_opaques(sans) > 0, "le point doit rester"


def test_les_deux_declinaisons_different_visuellement():
    complete = marque.dessiner_image(64, "#ffffff", "#ffffff", compacte=False)
    compacte = marque.dessiner_image(64, "#ffffff", "#ffffff", compacte=True)
    assert complete.tobytes() != compacte.tobytes()


def test_la_pastille_a_un_fond_opaque():
    """Un trace transparent se perd sur une barre des taches sombre."""
    image = marque.dessiner_pastille(64, "#ffffff")
    centre = image.getpixel((32, 32))
    coin_interieur = image.getpixel((32, 4))   # sous le bord haut, hors coins
    assert centre[3] == 255
    assert coin_interieur[3] == 255, "le fond doit couvrir la pastille"


def test_la_pastille_a_des_coins_arrondis():
    image = marque.dessiner_pastille(64, "#ffffff")
    assert image.getpixel((0, 0))[3] == 0, "le coin doit rester transparent"


def test_le_symbole_de_la_pastille_contraste_avec_son_fond():
    image = marque.dessiner_pastille(64, "#ffffff", couleur_arcs="#ffffff",
                                     fond="#0b0b0d")
    centre = image.getpixel((32, 32))
    assert sum(centre[:3]) > 600, "le point central doit etre clair"


def test_la_pastille_sans_arcs_reste_lisible():
    avec = marque.dessiner_pastille(64, "#ffffff", avec_arcs=True)
    sans = marque.dessiner_pastille(64, "#ffffff", avec_arcs=False)
    assert avec.tobytes() != sans.tobytes()
    assert sans.getpixel((32, 32))[3] == 255


@pytest.mark.parametrize("taille", [16, 24, 32, 48, 64, 128, 256])
def test_le_rendu_tient_a_toutes_les_tailles(taille):
    image = marque.dessiner_image(taille, "#3fb950", "#f2f2f4")
    assert image.size == (taille, taille)
    assert _pixels_opaques(image) > 0, "image vide"


# --------------------------------------------------------------------------
# Rendu canevas
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_le_canevas_recoit_les_arcs_et_le_point(racine_tk):
    canevas = tk.Canvas(racine_tk, width=100, height=100)
    marque.dessiner_canvas(canevas, 50, 50, 60, "#3fb950", "#ffffff")

    elements = canevas.find_withtag("marque")
    types = [canevas.type(e) for e in elements]
    assert types.count("arc") == 2
    assert types.count("oval") == 1
    canevas.destroy()


@pytest.mark.materiel
def test_le_canevas_sans_arcs_ne_trace_que_le_point(racine_tk):
    canevas = tk.Canvas(racine_tk, width=100, height=100)
    marque.dessiner_canvas(canevas, 50, 50, 60, "#3fb950", "#ffffff",
                           avec_arcs=False)
    types = [canevas.type(e) for e in canevas.find_withtag("marque")]
    assert types == ["oval"]
    canevas.destroy()


@pytest.mark.materiel
def test_les_arcs_du_canevas_sont_ouverts_et_orientes(racine_tk):
    """Les angles Pillow doivent etre convertis, pas recopies tels quels."""
    canevas = tk.Canvas(racine_tk, width=200, height=200)
    marque.dessiner_canvas(canevas, 100, 100, 120, "#000000", "#000000")

    arcs = [e for e in canevas.find_withtag("marque")
            if canevas.type(e) == "arc"]
    for arc in arcs:
        assert canevas.itemcget(arc, "style") == "arc", \
            "un arc ferme dessinerait un camembert"
        etendue = float(canevas.itemcget(arc, "extent"))
        assert abs(etendue) == pytest.approx(180), \
            f"demi-cercle attendu, obtenu {etendue}"
    canevas.destroy()

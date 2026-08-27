"""Cadres a coins arrondis, habillage de fenetre et trace des barres.

Trois modules qui existent tous pour la meme raison : Tk et Windows dessinent
eux-memes certaines choses, et ne se laissent pas recolorier. Ce qui est
verifiable sans regarder l'ecran l'est ici — geometrie, cache, conversions.
"""

import tkinter as tk

import pytest

from murmur import arrondi, chrome, graphe, theme as module_theme


@pytest.fixture(autouse=True)
def cache_propre():
    arrondi.oublier()
    yield
    arrondi.oublier()


@pytest.fixture
def racine(racine_tk):
    return racine_tk


# --------------------------------------------------------------------------
# Coins
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_quatre_coins_a_la_bonne_taille(racine):
    quatre = arrondi.coins(12, "#111113", "#0a0a0b", "#2c2c32", widget=racine)
    assert len(quatre) == 4
    for image in quatre:
        assert image.width() == 12
        assert image.height() == 12


@pytest.mark.materiel
def test_les_coins_sont_mis_en_cache(racine):
    """Le cache ne depend que du rayon et des couleurs, pas de la taille du
    widget : sinon chaque pixel de redimensionnement en creerait un jeu."""
    premier = arrondi.coins(10, "#111113", "#0a0a0b", widget=racine)
    second = arrondi.coins(10, "#111113", "#0a0a0b", widget=racine)
    assert premier is second


@pytest.mark.materiel
def test_un_rayon_different_donne_un_autre_jeu(racine):
    assert arrondi.coins(10, "#111113", "#0a0a0b", widget=racine) is not \
        arrondi.coins(14, "#111113", "#0a0a0b", widget=racine)


@pytest.mark.materiel
def test_oublier_vide_le_cache(racine):
    """Au changement de theme, les coins gardent les anciennes couleurs."""
    premier = arrondi.coins(10, "#111113", "#0a0a0b", widget=racine)
    arrondi.oublier()
    assert arrondi.coins(10, "#111113", "#0a0a0b", widget=racine) is not premier


@pytest.mark.materiel
def test_un_autre_interpreteur_refait_ses_images(racine):
    """Une PhotoImage appartient a l'interpreteur Tcl qui l'a creee : reprise
    apres sa disparition, elle donne « image "pyimage7" doesn't exist »."""
    premier = arrondi.coins(10, "#111113", "#0a0a0b", widget=racine)

    # Simule un second interpreteur sans en creer un : Tk n'en supporte pas
    # deux dans le meme processus.
    cle, (_, photos) = next(iter(arrondi._photos.items()))
    arrondi._photos[cle] = (object(), photos)

    assert arrondi.coins(10, "#111113", "#0a0a0b",
                         widget=racine) is not premier


@pytest.mark.materiel
def test_le_trace_pillow_nest_pas_refait_pour_autant(racine):
    """Seule la conversion vers Tk depend de l'interpreteur ; le dessin, lui,
    coute cher et n'appartient a personne."""
    arrondi.coins(10, "#111113", "#0a0a0b", widget=racine)
    cle, images = next(iter(arrondi._pillow.items()))

    arrondi._photos.clear()
    arrondi.coins(10, "#111113", "#0a0a0b", widget=racine)

    assert arrondi._pillow[cle] is images


# --------------------------------------------------------------------------
# Carte
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_la_carte_se_dimensionne_sur_son_contenu(racine):
    """Un canevas seul ne le saurait pas : Tk ne lui donne jamais la taille de
    ce qu'il porte."""
    fenetre = tk.Toplevel(racine)
    carte = arrondi.Carte(fenetre, "#111113", "#0a0a0b", rayon=10)
    tk.Label(carte.interieur, text="contenu", bg="#111113",
             fg="#ffffff").pack(pady=20)
    carte.pack()
    fenetre.update_idletasks()

    assert carte.winfo_reqheight() > 40
    assert carte.winfo_reqwidth() > 40
    fenetre.destroy()


@pytest.mark.materiel
def test_l_interieur_laisse_les_coins_decouverts(racine):
    """C'est la seule chose qui fait voir l'arrondi : un interieur pose bord a
    bord recouvrirait les quatre coins et la carte redeviendrait carree."""
    fenetre = tk.Toplevel(racine)
    carte = arrondi.Carte(fenetre, "#111113", "#0a0a0b", rayon=12)
    carte.pack(fill="x")
    fenetre.update_idletasks()

    # `winfo_x` vaut zero tant que la fenetre n'est pas affichee : le retrait
    # se lit sur la mise en page demandee, pas sur la position obtenue.
    assert int(carte.interieur.pack_info()["padx"]) == 12
    fenetre.destroy()


@pytest.mark.materiel
def test_repeindre_change_le_fond_sans_reconstruire(racine):
    fenetre = tk.Toplevel(racine)
    carte = arrondi.Carte(fenetre, "#111113", "#0a0a0b", rayon=10)
    carte.pack()
    fenetre.update_idletasks()

    interieur = carte.interieur
    carte.repeindre(fond="#1c1c20")

    assert carte.interieur is interieur, "l'interieur a ete recree"
    assert carte.interieur.cget("bg") == "#1c1c20"
    fenetre.destroy()


@pytest.mark.materiel
def test_une_carte_minuscule_ne_tronque_pas_ses_coins(racine):
    """Sous deux fois le rayon, l'arrondi couperait sa propre courbe."""
    fenetre = tk.Toplevel(racine)
    canevas = tk.Canvas(fenetre, width=10, height=6)
    arrondi.peindre(canevas, 10, 6, 12, "#111113", "#0a0a0b", "#2c2c32")
    assert len(canevas.find_all()) == 1, "un simple rectangle etait attendu"
    fenetre.destroy()


# --------------------------------------------------------------------------
# Habillage de la fenetre
# --------------------------------------------------------------------------

def test_conversion_de_couleur():
    """Windows attend l'ordre bleu-vert-rouge, l'inverse du web."""
    assert chrome.vers_colorref("#000000") == 0x000000
    assert chrome.vers_colorref("#ffffff") == 0xffffff
    assert chrome.vers_colorref("#112233") == 0x332211
    assert chrome.vers_colorref("112233") == 0x332211


def test_une_couleur_mal_formee_est_refusee():
    with pytest.raises(ValueError):
        chrome.vers_colorref("#abc")


@pytest.mark.materiel
def test_habiller_ne_leve_jamais(racine):
    """Sur une version anterieure a Windows 11 l'appel echoue : l'application
    doit rester utilisable, seulement moins jolie."""
    fenetre = tk.Toplevel(racine)
    fenetre.update_idletasks()
    assert isinstance(chrome.habiller(fenetre, module_theme.SOMBRE), bool)
    fenetre.destroy()


@pytest.mark.materiel
def test_le_descripteur_designe_le_niveau_superieur(racine):
    """Tk cree une fenetre fille : c'est le parent qui porte le bandeau."""
    fenetre = tk.Toplevel(racine)
    fenetre.update_idletasks()
    assert chrome.descripteur(fenetre) != 0
    fenetre.destroy()


# --------------------------------------------------------------------------
# Barres
# --------------------------------------------------------------------------

def test_melange_des_couleurs():
    assert graphe.melange("#000000", "#ffffff", 0.0) == "#000000"
    assert graphe.melange("#000000", "#ffffff", 1.0) == "#ffffff"
    assert graphe.melange("#000000", "#ffffff", 0.5) == "#808080"


def test_le_sommet_respecte_la_marge_du_haut():
    """Sans elle, le chiffre pose au-dessus de la plus haute barre sortirait
    du cadre — c'est justement celui qu'on vient lire."""
    assert graphe.sommet(100, 100, 200, marge_haut=20) == pytest.approx(20)


def test_le_sommet_sans_marge_touche_le_haut():
    assert graphe.sommet(100, 100, 200) == pytest.approx(0)


def test_une_petite_valeur_garde_une_hauteur_visible():
    """Une barre d'un pixel se confondrait avec une journee vide."""
    haut = graphe.sommet(1, 10_000, 200, marge_haut=20)
    assert 200 - haut >= graphe.MINIMUM


def test_une_journee_vide_laisse_une_trace():
    """Zero doit rester distinct d'une valeur minuscule, sans disparaitre :
    une serie interrompue se lirait comme une panne."""
    vide = graphe.sommet(0, 100, 200)
    petite = graphe.sommet(1, 100, 200)
    assert 200 - vide == graphe.CREUX
    assert vide > petite


def test_le_sommet_ne_divise_pas_par_zero():
    assert graphe.sommet(0, 0, 200) == 200 - graphe.CREUX


def test_les_barres_ont_la_taille_demandee():
    image = graphe.barres(300, 120, [3, 0, 7, 2], fond="#111113",
                          couleur="#333333", couleur_vive="#ffffff")
    assert image.size == (300, 120)


def test_les_barres_survivent_a_une_serie_vide():
    image = graphe.barres(300, 120, [], fond="#111113", couleur="#333333",
                          couleur_vive="#ffffff")
    assert image.size[0] > 0


def test_les_barres_survivent_a_une_serie_de_zeros():
    """La page masque ce cas, mais le module ne doit pas dependre de l'appelant."""
    image = graphe.barres(300, 120, [0, 0, 0], fond="#111113",
                          couleur="#333333", couleur_vive="#ffffff")
    assert image.size == (300, 120)


# --------------------------------------------------------------------------
# Descripteur de fenetre
# --------------------------------------------------------------------------

def test_le_descripteur_accepte_un_entier():
    """Les fenetres du moteur web n'ont pas de widget Tk derriere elles."""
    assert chrome.descripteur(4242) == 4242


class _IntPtr:
    """Le `System.IntPtr` du monde .NET, tel que pywebview le rend.

    Ce n'est pas un entier Python et il refuse de le devenir : `int()` sur cet
    objet leve une TypeError. La doublure le refuse donc aussi — c'est
    precisement ce qu'une doublure trop accommodante avait laisse passer. Le
    test vert, la fenetre gardait sa barre de titre.
    """

    def __init__(self, valeur: int):
        self._valeur = valeur

    def ToInt64(self) -> int:
        return self._valeur

    def __int__(self):
        raise TypeError("int() argument must be a string, a bytes-like "
                        "object or a real number, not 'IntPtr'")


def test_le_descripteur_lit_une_fenetre_du_moteur_web():
    """pywebview expose le descripteur .NET sous `native.Handle`."""
    class Fenetre:
        native = type("Native", (), {"Handle": _IntPtr(777)})()

    assert chrome.descripteur(Fenetre()) == 777


def test_un_descripteur_deja_entier_reste_accepte():
    """Toutes les fenetres ne viennent pas de .NET."""
    class Fenetre:
        native = type("Native", (), {"Handle": 4242})()

    assert chrome.descripteur(Fenetre()) == 4242


@pytest.mark.materiel
def test_la_fenetre_ne_demande_aucune_bordure(racine, monkeypatch):
    """Une bordure teintee de la couleur du fond reste une bordure.

    Elle se voyait en fin lisere clair autour de la fenetre, et jusque contre
    le rouge du bouton de fermeture au survol. Seule la valeur reservee
    « aucune couleur » la supprime.

    On observe la DEMANDE faite a Windows et non le resultat : l'attribut de
    bordure est en ecriture seule, et le relire rend « parametre incorrect ».
    """
    demandes = {}
    vrai_poser = chrome._poser

    def espion(hwnd, attribut, valeur, taille):
        demandes[attribut] = getattr(valeur, "value", valeur)
        return vrai_poser(hwnd, attribut, valeur, taille)

    monkeypatch.setattr(chrome, "_poser", espion)

    fenetre = tk.Toplevel(racine)
    fenetre.update_idletasks()
    chrome.habiller(fenetre, module_theme.CLAIR)

    assert demandes.get(chrome.COULEUR_BORD) == chrome.COULEUR_AUCUNE,         "une couleur de bordure a ete demandee au lieu de « aucune »"
    fenetre.destroy()

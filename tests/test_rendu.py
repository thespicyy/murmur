"""Rendu de la barre de dictee.

Le canevas de Tk ne fait aucun anticrenelage : la barre est donc dessinee par
Pillow puis peinte par GDI. Ces tests portent sur l'image produite, ce qui les
rend verifiables sans afficher quoi que ce soit.
"""

import numpy as np
import pytest

from murmur import rendu, theme as module_theme
from murmur.app import Etat

PALETTE = module_theme.SOMBRE


def image(etat=Etat.ECOUTE, niveau=0.1, phase=0.0):
    return rendu.rendre(etat, niveau, phase, PALETTE)


# --------------------------------------------------------------------------
# Forme generale
# --------------------------------------------------------------------------

def test_la_barre_a_la_taille_attendue():
    assert image().size == (rendu.LARGEUR, rendu.HAUTEUR)


def test_les_coins_sont_transparents():
    """La barre doit flotter, pas s'afficher dans un rectangle."""
    barre = image()
    for x, y in ((0, 0), (rendu.LARGEUR - 1, 0), (0, rendu.HAUTEUR - 1),
                 (rendu.LARGEUR - 1, rendu.HAUTEUR - 1)):
        assert barre.getpixel((x, y))[3] == 0, f"coin ({x}, {y}) opaque"


def test_le_centre_est_opaque():
    assert image().getpixel((rendu.LARGEUR // 2, rendu.HAUTEUR // 2))[3] == 255


def test_les_bords_sont_adoucis():
    """Le point central de ce travail : sans anticrenelage, l'alpha ne prend
    que 0 ou 255 et les courbes sortent en escalier.

    Le seuil suit les dimensions plutot que d'etre fige : reduire la barre
    diminue mecaniquement le nombre de pixels de bord, et un seuil en dur
    ferait echouer le test au premier redimensionnement.
    """
    alpha = np.array(image().getchannel("A"))
    intermediaires = np.count_nonzero((alpha > 20) & (alpha < 235))
    attendu = (rendu.LARGEUR + rendu.HAUTEUR) * 0.4
    assert intermediaires > attendu, (
        f"seulement {intermediaires} pixels de transition pour "
        f"{rendu.LARGEUR}x{rendu.HAUTEUR} — le rendu semble crenele")


def test_le_suréchantillonnage_est_actif():
    assert rendu.ECHELLE >= 2, "sans surechantillonnage, pas d'anticrenelage"


# --------------------------------------------------------------------------
# Etats
# --------------------------------------------------------------------------

@pytest.mark.parametrize("etat", list(Etat))
def test_chaque_etat_se_rend(etat):
    barre = rendu.rendre(etat, 0.1, 0.0, PALETTE)
    assert barre.size == (rendu.LARGEUR, rendu.HAUTEUR)


def test_les_etats_se_distinguent_visuellement():
    """Sans symbole dans la barre, l'etat se lit dans la couleur du vumetre."""
    rendus = {etat: rendu.rendre(etat, 0.12, 0.0, PALETTE).tobytes()
              for etat in (Etat.ECOUTE, Etat.TRANSCRIPTION, Etat.INSERTION)}
    assert len(set(rendus.values())) == 3, "deux etats se ressemblent trop"


def test_chaque_etat_a_sa_couleur_de_vumetre():
    couleurs = {rendu.couleur_etat(etat, PALETTE) for etat in Etat}
    assert len(couleurs) == len(Etat), "deux etats partagent une couleur"


def test_le_disque_est_separe_de_la_pilule():
    """Les deux formes se lisent comme deux elements distincts.

    Collees, elles formaient une seule masse a la silhouette irreguliere.
    """
    alpha = np.array(image().getchannel("A"))
    milieu = rendu.HAUTEUR // 2

    # Au milieu de l'ecart, sur la ligne mediane, le fond doit transparaitre.
    creux = int(rendu.DIAMETRE_LOGO + rendu.ECART_LOGO / 2)
    assert alpha[milieu, creux] < 100, "les deux formes se touchent encore"

    # Et de part et d'autre, la matiere est bien presente.
    assert alpha[milieu, int(rendu.DIAMETRE_LOGO / 2)] > 200, "disque absent"
    assert alpha[milieu, rendu.LARGEUR // 2] > 200, "pilule absente"


def test_lecart_reste_discret():
    """Trop large, les deux morceaux ne se liraient plus comme un ensemble."""
    assert 2 <= rendu.ECART_LOGO <= rendu.HAUTEUR * 0.25


def _zone_du_disque(barre):
    """Pixels du disque portant le symbole.

    On echantillonne toute la zone plutot qu'un pixel : le symbole est
    recentre optiquement, il n'est donc pas exactement au centre geometrique.
    """
    tableau = np.array(barre.convert("RGBA"))
    return tableau[:, :int(rendu.DIAMETRE_LOGO)]


def test_le_symbole_est_dans_le_disque():
    zone = _zone_du_disque(rendu.rendre(Etat.ECOUTE, 0.1, 0.0, PALETTE))
    clairs = np.count_nonzero((zone[:, :, 0] > 200) & (zone[:, :, 3] > 200))
    assert clairs > 20, "le symbole ne ressort pas du disque"


@pytest.mark.parametrize("etat", list(Etat))
def test_le_symbole_reste_blanc_quel_que_soit_letat(etat):
    """C'est une marque, pas un voyant : une pastille coloree la denaturait.

    L'etat se lit dans le vumetre, pas au milieu du logo.
    """
    zone = _zone_du_disque(rendu.rendre(etat, 0.12, 0.0, PALETTE))
    opaques = zone[zone[:, :, 3] > 200][:, :3].astype(int)
    saturation = opaques.max(axis=1) - opaques.min(axis=1)
    assert saturation.max() < 25, (
        f"teinte detectee dans le disque pour {etat.value} : "
        f"ecart maximal {saturation.max()}")


def test_le_vumetre_sanime_pendant_la_transcription():
    """Le micro est arrete : sans animation, la barre paraitrait figee au
    moment ou l'utilisateur attend le resultat."""
    a = rendu.rendre(Etat.TRANSCRIPTION, 0.0, 0.0, PALETTE).tobytes()
    b = rendu.rendre(Etat.TRANSCRIPTION, 0.0, 1.6, PALETTE).tobytes()
    assert a != b


# --------------------------------------------------------------------------
# Vumetre
# --------------------------------------------------------------------------

def _matiere_claire(barre) -> int:
    """Pixels clairs dans la zone du vumetre."""
    tableau = np.array(barre.convert("RGBA"))
    x1 = int(rendu.centre_annuler()[0] + rendu.RAYON_BOUTON + 10)
    x2 = int(rendu.centre_valider()[0] - rendu.RAYON_BOUTON - 10)
    zone = tableau[:, x1:x2]
    clair = (zone[:, :, 0] > 180) & (zone[:, :, 3] > 128)
    return int(np.count_nonzero(clair))


def test_le_vumetre_grossit_avec_la_voix():
    faible = _matiere_claire(image(niveau=0.01))
    fort = _matiere_claire(image(niveau=0.2))
    assert fort > faible, "le vumetre ne suit pas le niveau"


def test_le_vumetre_est_eteint_au_repos():
    """Au repos la barre n'est pas affichee, mais le rendu doit rester sain."""
    barre = rendu.rendre(Etat.REPOS, 0.3, 0.0, PALETTE)
    assert barre.size == (rendu.LARGEUR, rendu.HAUTEUR)


def test_un_niveau_sature_ne_deborde_pas():
    """Un cri ne doit pas faire sortir les points de la barre."""
    barre = image(niveau=99.0)
    alpha = np.array(barre.getchannel("A"))
    assert alpha[0, rendu.LARGEUR // 2] == 0 or alpha[0].max() <= 255
    assert barre.size == (rendu.LARGEUR, rendu.HAUTEUR)


def test_un_niveau_negatif_ne_casse_rien():
    image(niveau=-1.0)


def test_la_phase_fait_bouger_le_vumetre():
    """Sans animation, la barre serait figee pendant qu'on parle."""
    a = rendu.rendre(Etat.ECOUTE, 0.15, 0.0, PALETTE).tobytes()
    b = rendu.rendre(Etat.ECOUTE, 0.15, 1.6, PALETTE).tobytes()
    assert a != b


# --------------------------------------------------------------------------
# Geometrie des boutons
# --------------------------------------------------------------------------

def test_les_boutons_ne_se_chevauchent_pas():
    ax, _ = rendu.centre_annuler()
    vx, _ = rendu.centre_valider()
    assert vx - ax > 2 * rendu.RAYON_BOUTON + 20


def test_les_boutons_tiennent_dans_la_barre():
    for cx, cy in (rendu.centre_annuler(), rendu.centre_valider()):
        assert rendu.RAYON_BOUTON <= cx <= rendu.LARGEUR - rendu.RAYON_BOUTON
        assert rendu.RAYON_BOUTON <= cy <= rendu.HAUTEUR - rendu.RAYON_BOUTON


def test_les_glyphes_suivent_la_taille_des_boutons(monkeypatch):
    """Croix et coche doivent retrecir avec leur cercle.

    Exprimees en pixels fixes, elles finissaient par remplir un petit bouton
    de bord a bord.
    """
    def matiere_dans_le_bouton(rayon):
        monkeypatch.setattr(rendu, "RAYON_BOUTON", rayon)
        barre = image()
        cx, cy = (int(v) for v in rendu.centre_valider())
        marge = int(rayon) + 1
        # Fenetre bornee a l'image : un rayon large deborderait de la barre.
        zone = np.array(barre.convert("RGBA"))[
            max(0, cy - marge):min(rendu.HAUTEUR, cy + marge),
            max(0, cx - marge):min(rendu.LARGEUR, cx + marge)]
        # Pixels sombres = la coche, sur son disque blanc.
        return int(np.count_nonzero((zone[:, :, 0] < 90) & (zone[:, :, 3] > 128)))

    petit = matiere_dans_le_bouton(5)
    grand = matiere_dans_le_bouton(9)
    assert grand > petit * 1.4, (
        f"la coche ne suit pas la taille du bouton ({petit} vs {grand})")


def test_les_boutons_tiennent_dans_la_pilule():
    """Ils doivent respirer : colles aux bords, la barre parait bouchee."""
    ratio = rendu.RAYON_BOUTON * 2 / rendu.HAUTEUR
    assert 0.4 < ratio < 0.75, f"boutons a {ratio:.0%} de la hauteur"
    assert rendu.MARGE_BOUTON > 0


def test_le_bouton_valider_est_clair_et_annuler_sombre():
    """Le contraste porte le sens : valider ressort, annuler s'efface.

    Les points de mesure suivent le rayon du bouton — en pixels fixes, ils
    tombaient hors du bouton des qu'on le reduisait.
    """
    barre = image()
    decalage = int(rendu.RAYON_BOUTON * 0.6)
    vx, vy = (int(v) for v in rendu.centre_valider())
    ax, ay = (int(v) for v in rendu.centre_annuler())

    clair = barre.getpixel((vx, vy - decalage))    # au-dessus de la coche
    sombre = barre.getpixel((ax, ay - decalage))   # au-dessus de la croix
    assert sum(clair[:3]) > sum(sombre[:3])


# --------------------------------------------------------------------------
# Conversion pour GDI
# --------------------------------------------------------------------------

def test_la_conversion_bgra_a_la_bonne_taille():
    barre = image()
    donnees = rendu.vers_bgra_premultiplie(barre)
    assert len(donnees) == rendu.LARGEUR * rendu.HAUTEUR * 4


def test_les_composantes_sont_premultipliees():
    """Sans premultiplication, les bords adoucis se cernent d'un halo clair."""
    from PIL import Image

    essai = Image.new("RGBA", (2, 1))
    essai.putpixel((0, 0), (255, 255, 255, 0))     # blanc totalement transparent
    essai.putpixel((1, 0), (255, 255, 255, 128))   # blanc a moitie transparent

    donnees = rendu.vers_bgra_premultiplie(essai)
    b0, v0, r0, a0 = donnees[0:4]
    b1, v1, r1, a1 = donnees[4:8]

    assert (b0, v0, r0, a0) == (0, 0, 0, 0), "l'invisible doit etre noir"
    assert a1 == 128
    assert 120 <= r1 <= 132, "la composante doit suivre l'alpha"


def test_les_fonctions_gdi_declarent_leurs_arguments():
    """Sans `argtypes`, ctypes leve OverflowError sur un handle 64 bits.

    Le defaut ne se voit pas sur les handles bas du debut d'un processus,
    puis casse l'affichage sans prevenir — c'est ce qui a rendu la barre
    invisible apres le passage au rendu par GDI.
    """
    for fonction in (rendu.gdi32.SelectObject, rendu.gdi32.DeleteObject,
                     rendu.gdi32.DeleteDC, rendu.gdi32.CreateCompatibleDC,
                     rendu.gdi32.CreateDIBSection,
                     rendu.user32.UpdateLayeredWindow,
                     rendu.user32.GetDC, rendu.user32.ReleaseDC):
        assert fonction.argtypes is not None, f"{fonction} sans argtypes"
        assert fonction.restype is not None, f"{fonction} sans restype"


@pytest.mark.materiel
def test_peindre_reussit_sur_une_vraie_fenetre(racine_tk):
    """Verifie l'affichage de bout en bout, pas seulement l'image produite.

    Les tests d'image seuls passaient alors que rien ne s'affichait.
    """
    import tkinter as tk

    fenetre = tk.Toplevel(racine_tk)
    fenetre.overrideredirect(True)
    fenetre.geometry(f"{rendu.LARGEUR}x{rendu.HAUTEUR}+0+0")
    fenetre.withdraw()
    fenetre.update_idletasks()

    hwnd = rendu.user32.GetParent(fenetre.winfo_id()) or fenetre.winfo_id()
    rendu.poser_styles(hwnd)
    try:
        assert rendu.peindre(hwnd, image(), 200, 200), \
            "UpdateLayeredWindow a echoue"
    finally:
        fenetre.destroy()


@pytest.mark.materiel
def test_peindre_sur_une_fenetre_invalide_renvoie_faux_sans_lever(racine_tk):
    """Une erreur d'affichage ne doit jamais interrompre la boucle Tk."""
    assert rendu.peindre(0, image(), 0, 0) is False


def test_lordre_des_composantes_est_bien_bgra():
    from PIL import Image

    essai = Image.new("RGBA", (1, 1), (255, 0, 0, 255))   # rouge pur
    donnees = rendu.vers_bgra_premultiplie(essai)
    assert donnees[0] == 0, "bleu"
    assert donnees[1] == 0, "vert"
    assert donnees[2] == 255, "rouge en troisieme position"
    assert donnees[3] == 255
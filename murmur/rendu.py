"""Rendu de la barre de dictee, et affichage en fenetre transparente.

Deux problemes que Tkinter ne sait pas resoudre, traites ici :

**Le crenelage.** Le canevas de Tk ne fait aucun anticrenelage : cercles, arcs
et courbes sortent en escalier. La barre est donc dessinee avec Pillow, a
quatre fois la taille finale puis reduite — chaque pixel du resultat est la
moyenne de seize, ce qui donne des bords lisses.

**La transparence.** L'attribut `-transparentcolor` de Tk fonctionne par
couleur-cle : tout pixel de la teinte choisie devient transparent, sans demi-
teinte. Les bords adoucis se mettraient donc a baver en halos colores, ce qui
annulerait le benefice de l'anticrenelage. On passe par une fenetre en couches
(`UpdateLayeredWindow`), seule voie offrant une transparence par pixel.
"""

from __future__ import annotations

import ctypes
import math
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageDraw

from . import marque as module_marque
from .app import Etat

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

#: Facteur de suréchantillonnage. Au-dela de 4, le gain devient invisible et
#: le cout de reduction augmente inutilement.
ECHELLE = 4

# --- geometrie, en pixels de l'affichage final ----------------------------
#
# Un disque portant le symbole, puis une pilule : annuler, vumetre, valider.
#
# Toutes les proportions sont exprimees en fraction de la hauteur : changer la
# taille ne demande alors de toucher qu'a une seule constante. Les exprimer en
# pixels obligeait a recalculer une dizaine de valeurs a chaque essai, et
# laissait des glyphes disproportionnes des qu'on en oubliait une.

#: Hauteur de la barre sur un ecran a cent pour cent. Toutes les autres
#: mesures en descendent : c'est la seule valeur a changer pour redimensionner
#: la barre entiere.
HAUTEUR_REFERENCE = 31

#: Largeur de la pilule, en hauteurs de barre. La seule proportion qui ne se
#: lise pas directement dans le dessin : la pilule est bien plus large que
#: haute, et la ratio est ce qui la garde a la meme forme a toute echelle.
RATIO_PILULE = 119 / 31

NOMBRE_POINTS = 7

#: Niveau efficace au-dela duquel le vumetre est au maximum. Une voix normale
#: tourne autour de 0.05 : saturer plus haut le rendrait presque immobile.
NIVEAU_PLEIN = 0.16


def _poser(hauteur: int) -> None:
    """Recalcule toute la geometrie a partir de la hauteur.

    Les constantes sont relues a chaque appel de dessin, jamais capturees :
    c'est ce qui permet de changer l'echelle une fois au demarrage sans que
    rien d'autre ait a le savoir.
    """
    global HAUTEUR, LARGEUR, LARGEUR_PILULE, DIAMETRE_LOGO, ECART_LOGO
    global TAILLE_SYMBOLE, RAYON_BOUTON, MARGE_BOUTON, ECART_POINTS
    global RAYON_POINT_MIN, RAYON_POINT_MAX

    HAUTEUR = hauteur
    LARGEUR_PILULE = round(hauteur * RATIO_PILULE)
    DIAMETRE_LOGO = hauteur
    # Espace entre le disque et la pilule. Les deux formes se lisent alors
    # comme deux elements distincts — l'identite d'un cote, les commandes de
    # l'autre — plutot que comme une seule masse a la silhouette irreguliere.
    ECART_LOGO = hauteur * 0.16
    LARGEUR = round(DIAMETRE_LOGO + ECART_LOGO + LARGEUR_PILULE)

    TAILLE_SYMBOLE = round(hauteur * 0.62)

    RAYON_BOUTON = hauteur * 0.30
    MARGE_BOUTON = hauteur * 0.18   # entre le bord de la pilule et le bouton
    ECART_POINTS = hauteur * 0.26   # entre un bouton et le vumetre

    RAYON_POINT_MIN = hauteur * 0.043
    RAYON_POINT_MAX = hauteur * 0.105


def accorder(echelle: float = 1.0) -> int:
    """Met la barre a l'echelle de l'ecran. Renvoie sa nouvelle hauteur.

    Depuis que l'application se declare consciente du DPI, Windows n'agrandit
    plus son image : a 125 %, une barre laissee a 31 pixels serait nette mais
    un cinquieme trop petite. Elle est donc dessinee plus grande, a la taille
    reelle qu'elle doit occuper.

    Jamais en dessous de la reference : une echelle inferieure a 100 % n'a pas
    de sens, et arrondirait les cercles a rien.
    """
    _poser(max(HAUTEUR_REFERENCE, round(HAUTEUR_REFERENCE * echelle)))
    return HAUTEUR


_poser(HAUTEUR_REFERENCE)

NOIR = "#0b0b0d"
GRIS_BOUTON = "#3a3a40"
BLANC = "#ffffff"
POINT_ETEINT = "#5a5a62"


def centre_logo() -> tuple[float, float]:
    return DIAMETRE_LOGO / 2, HAUTEUR / 2


def debut_pilule() -> float:
    return DIAMETRE_LOGO + ECART_LOGO


def centre_annuler() -> tuple[float, float]:
    return debut_pilule() + MARGE_BOUTON + RAYON_BOUTON, HAUTEUR / 2


def centre_valider() -> tuple[float, float]:
    return LARGEUR - MARGE_BOUTON - RAYON_BOUTON, HAUTEUR / 2


# --------------------------------------------------------------------------
# Dessin
# --------------------------------------------------------------------------

def couleur_etat(etat: Etat, palette) -> str:
    """Couleur du vumetre selon l'etat.

    Le symbole, lui, reste blanc en toutes circonstances : c'est une marque,
    pas un voyant. Une pastille de couleur au milieu du logo le denaturait.

    L'ecoute garde donc des points blancs — c'est deja l'etat le plus lisible,
    puisque le vumetre y suit la voix. Les phases suivantes, breves et sans
    niveau sonore a montrer, se distinguent par leur teinte.
    """
    return {
        Etat.REPOS: POINT_ETEINT,
        Etat.ECOUTE: BLANC,
        Etat.TRANSCRIPTION: palette.transcription,
        Etat.INSERTION: palette.insertion,
    }[etat]


def rendre(etat: Etat, niveau: float, phase: float,
           palette) -> Image.Image:
    """Dessine la barre en RGBA, bords lisses, fond transparent."""
    k = ECHELLE
    image = Image.new("RGBA", (LARGEUR * k, HAUTEUR * k), (0, 0, 0, 0))
    trace = ImageDraw.Draw(image)

    # Deux formes separees, chacune posee sur le fond transparent.
    trace.ellipse([0, 0, DIAMETRE_LOGO * k - 1, HAUTEUR * k - 1], fill=NOIR)
    trace.rounded_rectangle(
        [debut_pilule() * k, 0, LARGEUR * k - 1, HAUTEUR * k - 1],
        radius=HAUTEUR * k / 2, fill=NOIR)

    # Symbole entierement blanc : une marque, pas un voyant.
    symbole = module_marque.dessiner_image(TAILLE_SYMBOLE * k, BLANC, BLANC)
    cx, cy = centre_logo()
    image.paste(symbole, (int(cx * k - symbole.size[0] / 2),
                          int(cy * k - symbole.size[1] / 2)), symbole)

    _bouton_annuler(trace, k)
    _vumetre(trace, k, etat, niveau, phase, couleur_etat(etat, palette))
    _bouton_valider(trace, k)

    # LANCZOS plutot que BILINEAR : les traits fins du symbole et de la coche
    # y gagnent nettement en nettete.
    return image.resize((LARGEUR, HAUTEUR), Image.LANCZOS)


#: Proportions des glyphes, rapportees au rayon du bouton. Les exprimer en
#: pixels fixes laissait une croix et une coche inchangees quand le cercle
#: retrecissait — elles finissaient par le remplir entierement.
BRAS_CROIX = 0.34
EPAISSEUR_TRAIT = 0.14
COCHE = ((-0.37, 0.03), (-0.10, 0.30), (0.37, -0.27))


def _trait_arrondi(trace: ImageDraw.ImageDraw, points, couleur: str,
                   epaisseur: float, k: int) -> None:
    """Trait a extremites rondes.

    Pillow ne sait pas arrondir les bouts : on pose un disque a chaque sommet,
    sans quoi croix et coche paraissent taillees a la serpe.
    """
    largeur = max(1, int(round(epaisseur * k)))
    trace.line([(x * k, y * k) for x, y in points], fill=couleur,
               width=largeur, joint="curve")
    rayon = largeur / 2
    for x, y in points:
        trace.ellipse([x * k - rayon, y * k - rayon,
                       x * k + rayon, y * k + rayon], fill=couleur)


def _bouton_annuler(trace: ImageDraw.ImageDraw, k: int) -> None:
    cx, cy = centre_annuler()
    r = RAYON_BOUTON
    trace.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k],
                  fill=GRIS_BOUTON)

    bras = r * BRAS_CROIX
    for dx, dy in ((1, 1), (1, -1)):
        _trait_arrondi(trace,
                       [(cx - bras * dx, cy - bras * dy),
                        (cx + bras * dx, cy + bras * dy)],
                       BLANC, r * EPAISSEUR_TRAIT, k)


def _bouton_valider(trace: ImageDraw.ImageDraw, k: int) -> None:
    cx, cy = centre_valider()
    r = RAYON_BOUTON
    trace.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k],
                  fill=BLANC)

    points = [(cx + dx * r, cy + dy * r) for dx, dy in COCHE]
    _trait_arrondi(trace, points, NOIR, r * EPAISSEUR_TRAIT * 1.1, k)


def _vumetre(trace: ImageDraw.ImageDraw, k: int, etat: Etat,
             niveau: float, phase: float, couleur_active: str) -> None:
    """Les points enflent avec la voix, en vague le long de la rangee.

    Une onde qui parcourt la rangee informe mieux qu'un clignotement
    synchrone, qui attire l'oeil sans rien dire.
    """
    depart = centre_annuler()[0] + RAYON_BOUTON + ECART_POINTS
    fin = centre_valider()[0] - RAYON_BOUTON - ECART_POINTS
    pas = (fin - depart) / max(1, NOMBRE_POINTS - 1)
    cy = HAUTEUR / 2

    if etat is Etat.ECOUTE:
        actif = True
        intensite = min(1.0, max(0.0, niveau) / NIVEAU_PLEIN)
    elif etat in (Etat.TRANSCRIPTION, Etat.INSERTION):
        # Le micro est arrete : il n'y a plus de niveau a suivre. On anime a
        # intensite fixe, sans quoi la barre paraitrait figee juste au moment
        # ou l'utilisateur attend le resultat.
        actif, intensite = True, 0.7
    else:
        actif, intensite = False, 0.0

    for i in range(NOMBRE_POINTS):
        if actif:
            onde = 0.55 + 0.45 * ((math.cos(phase - i * 0.7) + 1) / 2)
            rayon = RAYON_POINT_MIN + (
                RAYON_POINT_MAX - RAYON_POINT_MIN) * intensite * onde
            # En dessous d'un souffle, les points restent gris : un vumetre
            # allume en permanence ne dirait plus rien.
            couleur = couleur_active if intensite > 0.08 else POINT_ETEINT
        else:
            rayon, couleur = RAYON_POINT_MIN, POINT_ETEINT

        x = depart + i * pas
        trace.ellipse([(x - rayon) * k, (cy - rayon) * k,
                       (x + rayon) * k, (cy + rayon) * k], fill=couleur)


# --------------------------------------------------------------------------
# Fenetre en couches
# --------------------------------------------------------------------------

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte),
                ("AlphaFormat", ctypes.c_byte)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


# Signatures completes — restype ET argtypes. Sans argtypes, ctypes tente de
# faire tenir un handle 64 bits dans un entier 32 bits et leve OverflowError
# des que la valeur depasse 2^31. Le defaut ne se voit pas sur les handles
# bas du debut d'un processus, puis casse tout sans prevenir.
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = (
    wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = (wintypes.HDC,)

user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = (wintypes.HWND,)
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.UpdateLayeredWindow.argtypes = (
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(POINT), ctypes.POINTER(SIZE),
    wintypes.HDC, ctypes.POINTER(POINT), wintypes.DWORD,
    ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD)


def vers_bgra_premultiplie(image: Image.Image) -> bytes:
    """Convertit une image RGBA au format attendu par GDI.

    Windows veut du BGRA dont les composantes sont deja multipliees par
    l'alpha. Sans cette premultiplication, les bords adoucis apparaissent
    cernes d'un halo clair.
    """
    tableau = np.array(image.convert("RGBA"), dtype=np.uint8)
    alpha = tableau[:, :, 3].astype(np.uint16)
    rouge, vert, bleu = (tableau[:, :, i].astype(np.uint16) for i in range(3))

    return np.dstack([
        ((bleu * alpha) // 255).astype(np.uint8),
        ((vert * alpha) // 255).astype(np.uint8),
        ((rouge * alpha) // 255).astype(np.uint8),
        tableau[:, :, 3],
    ]).tobytes()


def poser_styles(hwnd: int) -> None:
    """Rend la fenetre transparente par pixel, et incapable de voler le focus."""
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        user32.GetWindowLongPtrW.restype = ctypes.c_longlong
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int,
                                             ctypes.c_longlong)
        lire, ecrire = user32.GetWindowLongPtrW, user32.SetWindowLongPtrW
    else:
        lire, ecrire = user32.GetWindowLongW, user32.SetWindowLongW

    style = lire(hwnd, GWL_EXSTYLE)
    ecrire(hwnd, GWL_EXSTYLE,
           style | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


def peindre(hwnd: int, image: Image.Image, x: int, y: int) -> bool:
    """Affiche l'image dans la fenetre, alpha compris.

    Chaque ressource GDI est liberee dans un `finally` : une fuite ici
    s'accumulerait a chaque image d'animation et finirait par epuiser le quota
    de handles du processus.
    """
    largeur, hauteur = image.size
    donnees = vers_bgra_premultiplie(image)

    hdc_ecran = user32.GetDC(None)
    if not hdc_ecran:
        return False

    hdc_memoire = bitmap = ancien = None
    try:
        hdc_memoire = gdi32.CreateCompatibleDC(hdc_ecran)
        if not hdc_memoire:
            return False

        infos = BITMAPINFO()
        infos.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        infos.bmiHeader.biWidth = largeur
        # Hauteur negative : image orientee du haut vers le bas, comme Pillow.
        infos.bmiHeader.biHeight = -hauteur
        infos.bmiHeader.biPlanes = 1
        infos.bmiHeader.biBitCount = 32
        infos.bmiHeader.biCompression = 0

        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(hdc_ecran, ctypes.byref(infos),
                                        DIB_RGB_COLORS, ctypes.byref(bits),
                                        None, 0)
        if not bitmap:
            return False
        ctypes.memmove(bits, donnees, len(donnees))
        ancien = gdi32.SelectObject(hdc_memoire, bitmap)

        taille = SIZE(largeur, hauteur)
        source = POINT(0, 0)
        destination = POINT(int(x), int(y))
        melange = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)

        return bool(user32.UpdateLayeredWindow(
            wintypes.HWND(hwnd), hdc_ecran, ctypes.byref(destination),
            ctypes.byref(taille), hdc_memoire, ctypes.byref(source), 0,
            ctypes.byref(melange), ULW_ALPHA))
    except (ctypes.ArgumentError, OSError):
        # Ne jamais laisser une erreur d'affichage remonter : elle
        # interromprait la boucle Tk et emporterait toute l'interface.
        return False
    finally:
        if ancien and hdc_memoire:
            gdi32.SelectObject(hdc_memoire, ancien)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if hdc_memoire:
            gdi32.DeleteDC(hdc_memoire)
        user32.ReleaseDC(None, hdc_ecran)

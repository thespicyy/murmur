"""Habillage de la fenetre par Windows lui-meme.

La barre de titre, les boutons de fenetre et les bords ne sont pas dessines
par Tk mais par le gestionnaire de fenetres : aucun reglage de widget ne les
atteint. Laissee telle quelle, elle reste un bandeau etranger pose au-dessus
de l'application — d'une autre teinte, aux boutons d'un autre style.

Deux degres de reponse, tous deux fournis ici :

  habiller()        impose au gestionnaire de fenetres la couleur du bandeau,
                    du texte et du bord, et arrondit les coins. Suffisant
                    quand on garde la barre du systeme.
  retirer_bandeau() supprime purement le bandeau (`WS_CAPTION`) en gardant le
                    cadre redimensionnable, la presence dans la barre des
                    taches et Alt+Tab. L'application dessine alors sa propre
                    barre, et rien ne trahit plus la couture.

La seconde voie demande de reprendre a la main ce que le bandeau assurait :
deplacement, agrandissement, reduction, fermeture. C'est le prix a payer pour
qu'il n'y ait plus qu'une seule fenetre a l'oeil, et non deux morceaux colles.

Sur une version de Windows anterieure, les appels echouent proprement et la
fenetre garde son habillage par defaut : l'application reste utilisable,
seulement moins jolie.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from . import journal

_log = journal.obtenir("chrome")

# -- attributs du gestionnaire de fenetres --------------------------------
MODE_SOMBRE = 20            # DWMWA_USE_IMMERSIVE_DARK_MODE
FORME_DES_COINS = 33        # DWMWA_WINDOW_CORNER_PREFERENCE
COULEUR_BORD = 34           # DWMWA_BORDER_COLOR
COULEUR_BANDEAU = 35        # DWMWA_CAPTION_COLOR
COULEUR_TEXTE = 36          # DWMWA_TEXT_COLOR

COINS_ARRONDIS = 2          # DWMWCP_ROUND
COINS_PEU_ARRONDIS = 3      # DWMWCP_ROUNDSMALL

#: Valeur reservee : « pas de bordure du tout ». Toute autre valeur PEINT un
#: filet d'un pixel autour de la fenetre — et un filet clair se voit, quelle
#: que soit la teinte qu'on lui donne : contre le bureau d'un cote, contre le
#: rouge du bouton de fermeture de l'autre.
COULEUR_AUCUNE = 0xFFFFFFFE

# -- styles de fenetre -----------------------------------------------------
GWL_STYLE = -16
WS_CAPTION = 0x00C00000

SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

MONITOR_DEFAULTTONEAREST = 2

_user32 = ctypes.WinDLL("user32")
_user32.GetParent.restype = wintypes.HWND
_user32.GetParent.argtypes = [wintypes.HWND]

_user32.GetWindowLongPtrW.restype = ctypes.c_longlong
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_longlong
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int,
                                      ctypes.c_longlong]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 wintypes.UINT]
_user32.MonitorFromWindow.restype = wintypes.HANDLE
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.GetWindowRect.argtypes = [wintypes.HWND,
                                  ctypes.POINTER(wintypes.RECT)]
_user32.GetMonitorInfoW.restype = wintypes.BOOL


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


_user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE,
                                    ctypes.POINTER(MONITORINFO)]

try:
    _dwmapi = ctypes.WinDLL("dwmapi")
    # restype ET argtypes : sans les seconds, ctypes suppose des entiers
    # signes de 32 bits et tronque le descripteur de fenetre.
    _dwmapi.DwmSetWindowAttribute.restype = ctypes.HRESULT
    _dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                              ctypes.c_void_p, wintypes.DWORD]
    # Relue par les tests : ce qu'on a demande a Windows et ce qu'il a retenu
    # ne sont pas la meme chose.
    _dwmapi.DwmGetWindowAttribute.restype = ctypes.HRESULT
    _dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                              ctypes.c_void_p, wintypes.DWORD]
except OSError:             # pragma: no cover - Windows fournit toujours dwmapi
    _dwmapi = None


def descripteur(fenetre) -> int:
    """Descripteur du niveau superieur portant la barre de titre.

    Trois sources possibles : un entier deja pret, une fenetre du moteur web
    — qui expose son descripteur .NET — ou un widget Tk. Ce dernier demande un
    detour : Tk cree une fenetre fille a l'interieur du cadre, et c'est le
    parent qui porte le bandeau.
    """
    if isinstance(fenetre, int):
        return fenetre
    natif = getattr(fenetre, "native", None)
    poignee = getattr(natif, "Handle", None)
    if poignee is not None:
        # `Handle` n'est pas un entier Python mais un `IntPtr` du monde .NET :
        # `int()` sur cet objet leve une TypeError. Il se convertit par
        # `ToInt64`. Le piege est d'autant plus insidieux qu'il ne se voit
        # jamais : chaque appelant enveloppe cette fonction dans un garde-fou,
        # et l'echec passait pour « le systeme a refuse » — la fenetre gardait
        # sa barre de titre, le glisser ne repondait pas, et rien ne le disait.
        vers_entier = getattr(poignee, "ToInt64", None)
        return int(vers_entier()) if vers_entier is not None else int(poignee)

    interne = wintypes.HWND(fenetre.winfo_id())
    parent = _user32.GetParent(interne)
    return int(parent) if parent else int(interne.value)


def vers_colorref(couleur: str) -> int:
    """« #1c1c20 » vers l'entier attendu par Windows, en ordre bleu-vert-rouge."""
    valeur = couleur.lstrip("#")
    if len(valeur) != 6:
        raise ValueError(f"couleur inattendue : {couleur!r}")
    rouge, vert, bleu = (int(valeur[i:i + 2], 16) for i in (0, 2, 4))
    return (bleu << 16) | (vert << 8) | rouge


def _poser(hwnd: int, attribut: int, valeur: ctypes.Structure | None,
           taille: int) -> bool:
    if _dwmapi is None:
        return False
    try:
        resultat = _dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), wintypes.DWORD(attribut),
            ctypes.byref(valeur), wintypes.DWORD(taille))
    except OSError:
        # Antérieur a Windows 11 : l'attribut n'existe pas.
        return False
    return resultat == 0


def habiller(fenetre, palette, arrondir: bool = True) -> bool:
    """Aligne la barre de titre sur la palette. Vrai si Windows a suivi.

    Le retour interesse surtout les tests : l'application ne change rien a son
    comportement selon que l'habillage a pris ou non.
    """
    try:
        hwnd = descripteur(fenetre)
    except Exception:
        _log.debug("descripteur de fenetre indisponible", exc_info=True)
        return False

    sombre = wintypes.BOOL(palette.nom == "sombre")
    pris = _poser(hwnd, MODE_SOMBRE, sombre, ctypes.sizeof(sombre))

    # Le bandeau prend la couleur du **fond de la fenetre**, non celle du
    # panneau. Meme retire, Windows garde quelques pixels de cadre en haut et
    # les peint de cette couleur : une teinte de panneau y dessinait une bande
    # claire au-dessus de la barre de titre de l'application.
    for attribut, couleur in ((COULEUR_BANDEAU, palette.fond),
                              (COULEUR_TEXTE, palette.texte_doux)):
        valeur = wintypes.DWORD(vers_colorref(couleur))
        pris = _poser(hwnd, attribut, valeur, ctypes.sizeof(valeur)) or pris

    # Pas de bordure, plutot qu'une bordure de la couleur du fond : la teindre
    # ne la fait pas disparaitre. Elle restait visible en fin lisere clair
    # autour de la fenetre, et jusque contre le rouge du bouton de fermeture.
    aucune = wintypes.DWORD(COULEUR_AUCUNE)
    pris = _poser(hwnd, COULEUR_BORD, aucune, ctypes.sizeof(aucune)) or pris

    if arrondir:
        forme = wintypes.DWORD(COINS_ARRONDIS)
        pris = _poser(hwnd, FORME_DES_COINS, forme,
                      ctypes.sizeof(forme)) or pris

    if not pris:
        _log.debug("habillage de fenetre refuse par Windows")
    return pris


# --------------------------------------------------------------------------
# Fenetre sans bandeau
# --------------------------------------------------------------------------

def retirer_bandeau(fenetre) -> bool:
    """Retire la barre de titre du systeme, sans rien perdre d'autre.

    Seul `WS_CAPTION` est ote : le cadre epais reste, donc le
    redimensionnement par les bords, la presence dans la barre des taches et
    Alt+Tab. C'est la difference avec `overrideredirect`, qui detache la
    fenetre du gestionnaire et oblige a tout reimplementer.

    La zone liberee devient du client ordinaire : l'application y dessine sa
    propre barre.
    """
    try:
        hwnd = descripteur(fenetre)
        style = _user32.GetWindowLongPtrW(wintypes.HWND(hwnd), GWL_STYLE)
        _user32.SetWindowLongPtrW(wintypes.HWND(hwnd), GWL_STYLE,
                                  style & ~WS_CAPTION)
        # Sans SWP_FRAMECHANGED, Windows garde en cache l'ancienne zone non
        # cliente et la fenetre reste dessinee avec son bandeau.
        _user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(0), 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                             | SWP_FRAMECHANGED)
        return True
    except Exception:
        _log.debug("bandeau non retire", exc_info=True)
        return False


def zone_travail(fenetre) -> tuple[int, int, int, int]:
    """Rectangle utile de l'ecran portant la fenetre : (x, y, largeur, hauteur).

    La barre des taches en est exclue. Une fenetre sans bandeau que l'on
    agrandit par l'etat « zoomed » de Tk la recouvrirait, l'agrandissement du
    systeme visant l'ecran entier pour ce genre de fenetre.
    """
    hwnd = descripteur(fenetre)
    ecran = _user32.MonitorFromWindow(wintypes.HWND(hwnd),
                                      MONITOR_DEFAULTTONEAREST)
    infos = MONITORINFO()
    infos.cbSize = ctypes.sizeof(MONITORINFO)
    if not _user32.GetMonitorInfoW(ecran, ctypes.byref(infos)):
        return 0, 0, fenetre.winfo_screenwidth(), fenetre.winfo_screenheight()

    zone = infos.rcWork
    return (zone.left, zone.top, zone.right - zone.left,
            zone.bottom - zone.top)


def rectangle(fenetre) -> tuple[int, int, int, int]:
    """Position et taille reelles de la fenetre : (x, y, largeur, hauteur).

    Mesurees aupres de Windows, non aupres de Tk : celui-ci ajoute a la taille
    demandee les marges du cadre telles qu'il les a relevees au premier
    affichage. Le bandeau ayant ete retire depuis, sa comptabilite est fausse
    de deux pixels — et l'ecart s'accumulait a chaque agrandissement.
    """
    hwnd = descripteur(fenetre)
    zone = wintypes.RECT()
    _user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(zone))
    return (zone.left, zone.top, zone.right - zone.left,
            zone.bottom - zone.top)


def placer(fenetre, x: int, y: int, largeur: int, hauteur: int) -> bool:
    """Impose la position et la taille exactes, sans arithmetique de cadre."""
    try:
        hwnd = descripteur(fenetre)
        return bool(_user32.SetWindowPos(
            wintypes.HWND(hwnd), wintypes.HWND(0), int(x), int(y),
            int(largeur), int(hauteur), SWP_NOZORDER | SWP_NOACTIVATE))
    except Exception:
        _log.debug("fenetre non placee", exc_info=True)
        return False

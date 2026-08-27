"""Conscience de la resolution d'affichage.

Sans declaration explicite, Windows considere une application comme ecrite
pour un ecran a 96 points par pouce : il la dessine a cette taille, puis
**etire l'image** a l'echelle reelle. Sur un ecran a 125 %, chaque trait et
chaque lettre passent par un agrandissement d'un facteur 1,25 — d'ou le flou
qu'aucun reglage de police ne corrige.

La declaration doit precede toute creation de fenetre : posee ensuite, elle
laisse les fenetres deja nees dans l'ancien referentiel.

Piege a ne pas reproduire : `SetProcessDpiAwarenessContext` prend une valeur
de la taille d'un pointeur. Sans `argtypes`, ctypes envoie un entier signe de
32 bits, l'appel echoue **sans rien dire**, et le processus reste inconscient
du DPI. C'est le meme piege que celui qui avait tue le moteur a travers son
job object, et que celui qui rendait la barre de dictee invisible.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from . import journal

_log = journal.obtenir("ecran")

#: DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2. Chaque fenetre suit l'ecran qui
#: la porte, et l'application est prevenue quand il change.
PAR_MONITEUR_V2 = -4

#: Reference de Windows : un ecran « a cent pour cent » compte 96 points par
#: pouce.
REFERENCE = 96


def declarer() -> bool:
    """Declare l'application consciente du DPI. Vrai si Windows a accepte.

    A appeler le plus tot possible, avant toute fenetre.
    """
    try:
        user32 = ctypes.WinDLL("user32")
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        pris = bool(user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(PAR_MONITEUR_V2)))
    except (AttributeError, OSError):
        # Anterieur a Windows 10 1703 : on se rabat sur l'ancienne API, qui
        # ne connait qu'une echelle pour tout le bureau.
        try:
            pris = ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0
        except (AttributeError, OSError):
            _log.debug("conscience du DPI indisponible")
            return False

    if not pris:
        _log.debug("conscience du DPI refusee")
    return pris


def facteur() -> float:
    """Echelle d'affichage du systeme : 1.0 a cent pour cent, 1.25 a 125 %.

    A ne lire qu'apres `declarer` : un processus inconscient du DPI recoit
    invariablement 96, quelle que soit la realite de l'ecran.
    """
    try:
        return ctypes.WinDLL("user32").GetDpiForSystem() / REFERENCE
    except (AttributeError, OSError):
        return 1.0


def facteur_de(fenetre) -> float:
    """Echelle de l'ecran qui porte cette fenetre.

    Un poste a plusieurs ecrans peut melanger les echelles — c'est le cas
    ici : deux ecrans a 125 %, un a 100 %.
    """
    try:
        user32 = ctypes.WinDLL("user32")
        user32.GetDpiForWindow.restype = wintypes.UINT
        user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        from . import chrome

        dpi = user32.GetDpiForWindow(wintypes.HWND(chrome.descripteur(fenetre)))
        return dpi / REFERENCE if dpi else facteur()
    except Exception:
        return facteur()


def accorder_tk(racine, echelle: float | None = None) -> float:
    """Aligne Tk sur l'echelle de l'ecran, et renvoie le facteur applique.

    Tk exprime ses tailles de police en points et les convertit lui-meme en
    pixels, avec un rapport qu'il faut lui donner. Sans ce reglage, une
    application declaree consciente du DPI devient nette **et minuscule** :
    Windows cesse d'agrandir, mais rien ne prend le relais.
    """
    echelle = facteur() if echelle is None else echelle
    try:
        # `tk scaling` attend des pixels par point typographique : 72 points
        # font un pouce.
        racine.tk.call("tk", "scaling", echelle * REFERENCE / 72)
    except Exception:
        _log.debug("mise a l'echelle de Tk refusee", exc_info=True)
    return echelle

"""Ce que Windows cesse de fournir quand on lui retire le bandeau.

POURQUOI CE MODULE EXISTE

Le tableau de bord etait cree en mode « sans cadre » de pywebview. Ce mode
passe la fenetre en `FormBorderStyle.None`, ce qui n'ote pas seulement la
barre de titre : il ote aussi le **cadre epais**, dont les bords portent le
redimensionnement, et le droit d'etre agrandie. Rendre `WS_THICKFRAME` a la
main ensuite ne suffit pas — WinForms reimpose ses propres `CreateParams` au
premier recalcul de cadre, et le style repart.

La bonne voie est l'inverse : creer une fenetre **ordinaire**, puis lui retirer
`WS_CAPTION` seul. Tout le reste survit — redimensionnement par les bords,
menu systeme, Alt+Tab, barre des taches — et la zone liberee devient du client
que la page peint elle-meme. C'est l'approche deja eprouvee dans l'app
une autre application maison, portee ici.

CE QU'IL FAUT REPRENDRE A LA MAIN

Le deplacement et l'ancrage aux bords sont normalement assures par la boucle
modale que Windows lance quand on saisit un bandeau. Lui passer la main
suppose que notre fenetre recoive le clic — or elle ne le recoit jamais : le
composant WebView2 place la fenetre qui capte la souris dans un *autre
processus*, et la couche d'hebergement ne relaie pas les zones non clientes
vers la fenetre hote. Cinq voies ont ete essayees et mesurees ailleurs,
toutes sans effet sur cette pile (`WM_NCLBUTTONDOWN`/`HTCAPTION`,
`WM_SYSCOMMAND`/`SC_MOVE`, appel direct a `DefWindowProc`, `AttachThreadInput`,
et `IsNonClientRegionSupportEnabled` avec `app-region: drag`).

Le glisser et l'ancrage sont donc menes ici, dans un fil dedie qui interroge la
souris directement. Le **redimensionnement par les bords**, lui, reste celui de
Windows : c'est justement ce que le mode sans cadre faisait perdre.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes

from . import journal

_log = journal.obtenir("cadre")

# -- styles et messages ----------------------------------------------------
GWL_STYLE = -16
GWLP_WNDPROC = -4
WS_CAPTION = 0x00C00000
WS_POPUP = 0x80000000

#: Ce que le retrait du bandeau ne doit surtout pas emporter. `WS_CAPTION` vaut
#: `WS_BORDER | WS_DLGFRAME` et ne recouvre aucun de ces bits — mais c'est le
#: genre d'affirmation qu'il vaut mieux verifier que supposer, d'ou
#: `styles_conserves` plus bas, appelee par les tests.
WS_THICKFRAME = 0x00040000   # redimensionnement par les bords
WS_SYSMENU = 0x00080000      # menu systeme, presence en barre des taches
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
LWA_ALPHA = 0x00000002

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1

SW_HIDE = 0
SW_MINIMIZE = 6
SW_RESTORE = 9

WM_NCCALCSIZE = 0x0083
WM_DESTROY = 0x0002
WM_ENTERSIZEMOVE = 0x0231

VK_LBUTTON = 0x01
MONITOR_DEFAULTTONEAREST = 2

FORME_DES_COINS = 33         # DWMWA_WINDOW_CORNER_PREFERENCE
COINS_ARRONDIS = 2           # DWMWCP_ROUND
COINS_DROITS = 1             # DWMWCP_DONOTROUND

#: Rectangle reellement peint de la fenetre, ombre et bordure invisible
#: exclues. Il differe de `GetWindowRect`, qui compte en plus la bordure de
#: redimensionnement transparente.
CADRE_ETENDU = 9             # DWMWA_EXTENDED_FRAME_BOUNDS

SM_CXSIZEFRAME = 32
SM_CYSIZEFRAME = 33
SM_CXPADDEDBORDER = 92

#: Epaisseur au-dela de laquelle une bordure mesuree est jugee aberrante.
MARGE_MAX = 40

#: Windows renvoie cette erreur quand la classe de fenetre est deja enregistree
#: par une execution precedente dans le meme processus. Sans gravite.
ERREUR_CLASSE_DEJA_ENREGISTREE = 1410

_ACTIF = sys.platform == "win32"

if _ACTIF:
    _user32 = ctypes.WinDLL("user32")
    _gdi32 = ctypes.WinDLL("gdi32")
    _kernel32 = ctypes.WinDLL("kernel32")

    # restype ET argtypes : sans les seconds, ctypes suppose des entiers signes
    # de 32 bits et tronque les descripteurs de fenetre sur un systeme 64 bits.
    # L'appel echoue alors sans un mot.
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int,
                                          ctypes.c_ssize_t]
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     wintypes.UINT]
    _user32.GetWindowRect.argtypes = [wintypes.HWND,
                                      ctypes.POINTER(wintypes.RECT)]
    _user32.MonitorFromWindow.restype = wintypes.HANDLE
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromPoint.restype = wintypes.HANDLE
    _user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.CallWindowProcW.restype = ctypes.c_ssize_t
    _user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND,
                                        ctypes.c_uint, ctypes.c_size_t,
                                        ctypes.c_ssize_t]
    _user32.DefWindowProcW.restype = ctypes.c_ssize_t
    _user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                       ctypes.c_size_t, ctypes.c_ssize_t]
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.DestroyWindow.argtypes = [wintypes.HWND]
    _user32.SetLayeredWindowAttributes.argtypes = [
        wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte, wintypes.DWORD]
    _gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
    _gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]

    # Les fonctions de l'apercu, declarees avec le meme soin. Sans elles,
    # `GetModuleHandleW` rendait un entier tronque a 32 bits, ecrit tel quel
    # dans le champ `hInstance` de la classe de fenetre : `RegisterClassW`
    # tombait alors sur une violation d'acces, que ctypes convertit en OSError
    # et que le garde-fou avalait — l'apercu d'ancrage ne s'affichait jamais,
    # sans un mot dans le journal.
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetLastError.restype = wintypes.DWORD
    _kernel32.GetLastError.argtypes = []
    _user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
        wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    _user32.DestroyWindow.restype = wintypes.BOOL
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetCursorPos.restype = wintypes.BOOL
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.GetMonitorInfoW.restype = wintypes.BOOL

    #: Signature d'une procedure de fenetre Win32 sur 64 bits.
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND,
                                 ctypes.c_uint, ctypes.c_size_t,
                                 ctypes.c_ssize_t)

    class NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    class WNDCLASS(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR)]

    _user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE,
                                        ctypes.POINTER(MONITORINFO)]
    _user32.RegisterClassW.restype = wintypes.ATOM
    _user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]

    try:
        _dwmapi = ctypes.WinDLL("dwmapi")
        _dwmapi.DwmSetWindowAttribute.restype = ctypes.HRESULT
        _dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        _dwmapi.DwmGetWindowAttribute.restype = ctypes.HRESULT
        _dwmapi.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    except OSError:                               # pragma: no cover
        _dwmapi = None
else:                                             # pragma: no cover
    _user32 = _gdi32 = _kernel32 = _dwmapi = None


# --------------------------------------------------------------- bandeau

def retirer_bandeau(hwnd: int) -> bool:
    """Retire la barre de titre du systeme, sans rien perdre d'autre.

    Seul `WS_CAPTION` est ote. Le retour dit si Windows a suivi, verifie en
    relisant le style plutot qu'en supposant que l'ecriture a pris.
    """
    if not _ACTIF:
        return False
    try:
        style = _user32.GetWindowLongPtrW(wintypes.HWND(hwnd), GWL_STYLE)
        _user32.SetWindowLongPtrW(wintypes.HWND(hwnd), GWL_STYLE,
                                  style & ~WS_CAPTION)
        # Sans SWP_FRAMECHANGED, Windows garde en cache l'ancienne zone non
        # cliente et continue de dessiner la fenetre avec son bandeau.
        _user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(0), 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                             | SWP_FRAMECHANGED)
        return not (_user32.GetWindowLongPtrW(wintypes.HWND(hwnd), GWL_STYLE)
                    & WS_CAPTION)
    except Exception:
        _log.debug("bandeau non retire", exc_info=True)
        return False


def styles_conserves(hwnd: int) -> dict:
    """Ce qui subsiste du style apres le retrait du bandeau.

    Utilise par les tests : retirer `WS_CAPTION` ne doit couter ni le
    redimensionnement, ni le menu systeme, ni les boutons reduire/agrandir —
    c'est toute la difference avec le mode « sans cadre » de pywebview.
    """
    if not _ACTIF:
        return {}
    style = _user32.GetWindowLongPtrW(wintypes.HWND(hwnd), GWL_STYLE)
    return {
        "cadre_redimensionnable": bool(style & WS_THICKFRAME),
        "menu_systeme": bool(style & WS_SYSMENU),
        "bouton_reduire": bool(style & WS_MINIMIZEBOX),
        "bouton_agrandir": bool(style & WS_MAXIMIZEBOX),
        "bandeau": bool(style & WS_CAPTION),
    }


def poser_coins(hwnd: int, arrondis: bool) -> bool:
    """Coins arrondis ou d'equerre, selon que la fenetre couvre l'ecran."""
    if not _ACTIF or _dwmapi is None:
        return False
    valeur = wintypes.DWORD(COINS_ARRONDIS if arrondis else COINS_DROITS)
    try:
        return _dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), wintypes.DWORD(FORME_DES_COINS),
            ctypes.byref(valeur), ctypes.sizeof(valeur)) == 0
    except OSError:                               # anterieur a Windows 11
        return False


# --------------------------------------------------------- geometrie & etat

def rectangle(hwnd: int) -> tuple[int, int, int, int]:
    """(x, y, largeur, hauteur) de la fenetre, en pixels ecran."""
    r = wintypes.RECT()
    _user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def _info_ecran(ecran) -> "MONITORINFO":
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    _user32.GetMonitorInfoW(ecran, ctypes.byref(info))
    return info


def zone_travail(hwnd: int) -> tuple[int, int, int, int]:
    """Rectangle utile de l'ecran portant la fenetre, barre des taches exclue.

    C'est lui, et non l'ecran entier, qui sert de cible a l'agrandissement :
    une fenetre sans bandeau confiee a l'agrandissement du systeme recouvrirait
    la barre des taches, Windows visant l'ecran complet pour ce genre de
    fenetre.
    """
    ecran = _user32.MonitorFromWindow(wintypes.HWND(hwnd),
                                      MONITOR_DEFAULTTONEAREST)
    w = _info_ecran(ecran).rcWork
    return w.left, w.top, w.right - w.left, w.bottom - w.top


def ecrans_du_point(x: int, y: int) -> tuple[tuple[int, int, int, int],
                                             tuple[int, int, int, int]]:
    """(rectangle du moniteur, zone de travail) du moniteur sous le point.

    Les deux sont necessaires et ne servent pas a la meme chose : le bord est
    detecte sur le **moniteur**, puisque c'est la que le curseur bute, tandis
    que le rectangle d'ancrage est calcule sur la **zone de travail**, pour ne
    pas passer sous la barre des taches.
    """
    ecran = _user32.MonitorFromPoint(wintypes.POINT(x, y),
                                     MONITOR_DEFAULTTONEAREST)
    info = _info_ecran(ecran)
    m, w = info.rcMonitor, info.rcWork
    return ((m.left, m.top, m.right - m.left, m.bottom - m.top),
            (w.left, w.top, w.right - w.left, w.bottom - w.top))


def poser(hwnd: int, x: int, y: int, largeur: int | None = None,
          hauteur: int | None = None) -> None:
    """Deplace, et redimensionne si demande, en coordonnees systeme."""
    drapeaux = SWP_NOZORDER | SWP_NOACTIVATE
    if largeur is None or hauteur is None:
        drapeaux |= SWP_NOSIZE
        largeur = hauteur = 0
    _user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(0),
                         int(x), int(y), int(largeur), int(hauteur), drapeaux)


def cadre_visible(hwnd: int) -> tuple[int, int, int, int]:
    """Rectangle reellement peint : ce que l'utilisateur voit.

    `GetWindowRect` compte en plus la **bordure de redimensionnement
    transparente** que Windows pose autour des fenetres a cadre epais. Les deux
    rectangles ne coincident pas, et confondre l'un avec l'autre se voit
    immediatement : une fenetre agrandie sur la zone de travail laisse alors
    apparaitre le bureau sur quelques pixels a gauche, a droite et en bas.
    """
    if _dwmapi is None:
        return rectangle(hwnd)
    r = wintypes.RECT()
    try:
        if _dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd), wintypes.DWORD(CADRE_ETENDU),
                ctypes.byref(r), ctypes.sizeof(r)) != 0:
            return rectangle(hwnd)
    except OSError:
        return rectangle(hwnd)
    return r.left, r.top, r.right - r.left, r.bottom - r.top


#: Derniere mesure jugee plausible, conservee comme repli.
_marges_connues: tuple[int, int, int, int] | None = None


def marges_systeme() -> tuple[int, int, int, int]:
    """Bordure invisible d'apres les metriques du systeme, en dernier recours.

    Moins exacte que la mesure, mais toujours disponible et du bon ordre de
    grandeur. Le haut est a zero : la bordure transparente n'existe que sur les
    cotes et en bas.
    """
    if not _ACTIF:
        return (0, 0, 0, 0)
    marge = _user32.GetSystemMetrics(SM_CXPADDEDBORDER)
    horizontale = _user32.GetSystemMetrics(SM_CXSIZEFRAME) + marge
    basse = _user32.GetSystemMetrics(SM_CYSIZEFRAME) + marge
    return (horizontale, 0, horizontale, basse)


def marges_invisibles(hwnd: int) -> tuple[int, int, int, int]:
    """Epaisseur de la bordure transparente : (gauche, haut, droite, bas).

    La mesure est prise sur la fenetre elle-meme, plus exacte que les metriques
    du systeme. Mais elle n'est **pas fiable partout** : posee dans l'espace
    mort entre deux moniteurs, la fenetre rend des valeurs absurdes — et c'est
    precisement la qu'on se trouve juste avant un ancrage au bord droit, la
    fenetre ayant suivi le curseur jusque-la.

    On valide donc la mesure, on retient la derniere plausible, et on retombe
    sur les metriques du systeme si l'on n'en a jamais eu.
    """
    global _marges_connues
    fx, fy, flarg, fhaut = rectangle(hwnd)
    vx, vy, vlarg, vhaut = cadre_visible(hwnd)
    mesure = (vx - fx, vy - fy,
              (fx + flarg) - (vx + vlarg), (fy + fhaut) - (vy + vhaut))
    if all(0 <= m <= MARGE_MAX for m in mesure):
        _marges_connues = mesure
        return mesure
    return _marges_connues if _marges_connues is not None else marges_systeme()


def poser_visible(hwnd: int, x: int, y: int, largeur: int,
                  hauteur: int) -> None:
    """Pose la fenetre pour que **sa partie visible** occupe ce rectangle.

    A utiliser des que la cible est une surface d'ecran — zone de travail,
    moitie, quart. `poser` seul viserait le rectangle systeme, bordure
    invisible comprise, et la fenetre resterait en retrait de sa cible de
    l'epaisseur de cette bordure.
    """
    gauche, haut, droite, bas = marges_invisibles(hwnd)
    poser(hwnd, x - gauche, y - haut,
          largeur + gauche + droite, hauteur + haut + bas)


def curseur() -> tuple[int, int]:
    p = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def bouton_gauche_enfonce() -> bool:
    """Etat physique du bouton gauche.

    `GetAsyncKeyState` interroge la souris directement, sans passer par la file
    de messages de la fenetre : c'est ce qui permet de suivre un glisser depuis
    un fil separe, alors que les evenements de la page, eux, cessent d'arriver
    des que le curseur sort de la fenetre.
    """
    return bool(_user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)


def reduire(hwnd: int) -> None:
    _user32.ShowWindow(wintypes.HWND(hwnd), SW_MINIMIZE)


def restaurer(hwnd: int) -> None:
    """Sort de l'etat reduit et ramene au premier plan."""
    if _user32.IsIconic(wintypes.HWND(hwnd)):
        _user32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
    _user32.SetForegroundWindow(wintypes.HWND(hwnd))


# ------------------------------------------ procedure de fenetre derivee

class Subclasse:
    """Intercepte un seul message de la fenetre, et laisse passer le reste.

    `WM_NCCALCSIZE` — meme privee de son bandeau, la fenetre garde quelques
    pixels visibles en haut, contre un seul sur les autres bords : le reste du
    cadre de la legende. La page commencerait donc sous le bord reel, et le
    survol du bouton « fermer » ne colorerait pas le coin, qui ne lui
    appartient pas. On laisse Windows calculer la zone cliente comme
    d'habitude, puis on lui rend ces pixels du haut. Les bords gauche, droit et
    bas sont laisses intacts : ce sont eux qui portent le redimensionnement.
    """

    def __init__(self, hwnd: int):
        self._hwnd = hwnd
        self._ancien = None
        #: Nombre de boucles modales de deplacement menees par Windows. Sert
        #: aux tests a distinguer « c'est Windows qui deplace » de « c'est
        #: nous ».
        self.boucles_systeme = 0
        # La reference doit rester vivante aussi longtemps que la fenetre : si
        # le ramasse-miettes liberait l'objet WNDPROC, Windows appellerait un
        # pointeur de fonction mort et le processus tomberait.
        self._proc = WNDPROC(self._traiter) if _ACTIF else None

    @property
    def active(self) -> bool:
        return self._ancien is not None

    def poser(self) -> bool:
        if not _ACTIF or self._ancien is not None:
            return self.active
        try:
            ancien = _user32.SetWindowLongPtrW(
                wintypes.HWND(self._hwnd), GWLP_WNDPROC,
                ctypes.cast(self._proc, ctypes.c_void_p).value)
            if not ancien:
                return False
            self._ancien = ancien
            # Sans SWP_FRAMECHANGED, Windows ne redemande pas le calcul de la
            # zone cliente et garde en cache l'ancienne, bordure haute
            # comprise.
            _user32.SetWindowPos(wintypes.HWND(self._hwnd), wintypes.HWND(0),
                                 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE
                                 | SWP_NOZORDER | SWP_FRAMECHANGED)
            return True
        except Exception:
            self._ancien = None
            return False

    def _traiter(self, hwnd, message, wparam, lparam):
        # Rien ici ne doit lever : une exception dans une procedure de fenetre
        # est avalee par ctypes, qui renvoie alors une valeur arbitraire a
        # Windows — et le comportement devient inexplicable.
        try:
            if message == WM_NCCALCSIZE and wparam:
                return self._rendre_le_haut(hwnd, message, wparam, lparam)
            if message == WM_ENTERSIZEMOVE:
                self.boucles_systeme += 1
            if message == WM_DESTROY:
                self._retablir()
        except Exception:
            pass
        return _user32.CallWindowProcW(ctypes.c_void_p(self._ancien), hwnd,
                                       message, wparam, lparam)

    def _rendre_le_haut(self, hwnd, message, wparam, lparam):
        """Laisse Windows calculer la zone cliente, puis lui rend le bord haut."""
        params = ctypes.cast(lparam,
                             ctypes.POINTER(NCCALCSIZE_PARAMS)).contents
        haut_propose = params.rgrc[0].top
        resultat = _user32.CallWindowProcW(ctypes.c_void_p(self._ancien), hwnd,
                                           message, wparam, lparam)
        params.rgrc[0].top = haut_propose
        return resultat

    def _retablir(self) -> None:
        """Remet la procedure d'origine avant que la fenetre ne disparaisse."""
        if self._ancien is None:
            return
        try:
            _user32.SetWindowLongPtrW(wintypes.HWND(self._hwnd), GWLP_WNDPROC,
                                      self._ancien)
        except Exception:
            pass


# ------------------------------------------------------------------ ancrage

#: Distance au bord de l'ecran, en pixels, a partir de laquelle une zone
#: d'ancrage s'arme. Windows arme au contact ; on garde deux pixels.
MARGE_BORD = 2

#: Hauteur des coins, en fraction de la hauteur de l'ecran : au-dela, on ancre
#: en quart d'ecran plutot qu'en moitie.
FRACTION_COIN = 0.25


def zone_ancrage(x: int, y: int) -> tuple[str | None,
                                          tuple[int, int, int, int] | None]:
    """Zone d'ancrage armee par la position du curseur, et son rectangle."""
    (mx, my, mlarg, mhaut), (tx, ty, tlarg, thaut) = ecrans_du_point(x, y)

    gauche = x <= mx + MARGE_BORD
    droite = x >= mx + mlarg - 1 - MARGE_BORD
    haut = y <= my + MARGE_BORD

    demi_l, demi_h = tlarg // 2, thaut // 2
    seuil_coin = mhaut * FRACTION_COIN

    if gauche or droite:
        cote_x = tx if gauche else tx + tlarg - demi_l
        # « quart » est masculin, « moitie » feminine : deux formes, pas une.
        cote_m = "gauche" if gauche else "droit"
        cote_f = "gauche" if gauche else "droite"
        if y <= my + seuil_coin:
            return f"quart haut {cote_m}", (cote_x, ty, demi_l, demi_h)
        if y >= my + mhaut - seuil_coin:
            return (f"quart bas {cote_m}",
                    (cote_x, ty + thaut - demi_h, demi_l, demi_h))
        return f"moitie {cote_f}", (cote_x, ty, demi_l, thaut)

    if haut:
        return "plein ecran", (tx, ty, tlarg, thaut)
    return None, None


class Apercu:
    """Rectangle translucide montrant ou la fenetre ira si on relache.

    Sans lui, l'ancrage se produirait sans prevenir au relachement : la fenetre
    sauterait, et l'utilisateur ne saurait qu'apres coup ce qu'il a declenche.

    C'est une fenetre a part, superposee : transparente au clic
    (`WS_EX_TRANSPARENT`, sinon elle intercepterait le glisser en cours),
    jamais activee (`WS_EX_NOACTIVATE`, pour ne pas voler le focus a
    l'application), et absente de la barre des taches et d'Alt+Tab
    (`WS_EX_TOOLWINDOW`).
    """

    NOM_CLASSE = "MurmurApercuAncrage"
    #: Sur 255 : assez pour se voir, assez pour laisser deviner le dessous.
    ALPHA = 70
    COULEUR = 0xFFFFFF          # blanc, en bleu-vert-rouge

    def __init__(self):
        self._hwnd = None
        self._classe = None
        self._proc = None

    def _enregistrer_classe(self) -> bool:
        if self._classe is not None:
            return True
        try:
            # La procedure ne fait rien de particulier : c'est le pinceau de
            # fond de la classe qui peint le rectangle.
            self._proc = WNDPROC(lambda h, m, w, l: _user32.DefWindowProcW(
                wintypes.HWND(h), m, ctypes.c_size_t(w), ctypes.c_ssize_t(l)))
            classe = WNDCLASS()
            classe.lpfnWndProc = ctypes.cast(self._proc, ctypes.c_void_p)
            classe.hInstance = _kernel32.GetModuleHandleW(None)
            classe.lpszClassName = self.NOM_CLASSE
            classe.hbrBackground = _gdi32.CreateSolidBrush(self.COULEUR)
            atome = _user32.RegisterClassW(ctypes.byref(classe))
            if not atome and (_kernel32.GetLastError()
                              != ERREUR_CLASSE_DEJA_ENREGISTREE):
                return False
            self._classe = classe       # reference gardee, comme la procedure
            return True
        except Exception:
            return False

    def _creer(self) -> bool:
        if self._hwnd:
            return True
        if not self._enregistrer_classe():
            return False
        try:
            self._hwnd = _user32.CreateWindowExW(
                WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
                | WS_EX_NOACTIVATE,
                self.NOM_CLASSE, None, WS_POPUP, 0, 0, 0, 0, None, None,
                _kernel32.GetModuleHandleW(None), None)
            if not self._hwnd:
                return False
            _user32.SetLayeredWindowAttributes(wintypes.HWND(self._hwnd), 0,
                                               self.ALPHA, LWA_ALPHA)
            return True
        except Exception:
            self._hwnd = None
            return False

    def montrer(self, rect: tuple[int, int, int, int]) -> bool:
        if not _ACTIF or not self._creer():
            return False
        x, y, largeur, hauteur = rect
        _user32.SetWindowPos(wintypes.HWND(self._hwnd),
                             wintypes.HWND(HWND_TOPMOST), int(x), int(y),
                             int(largeur), int(hauteur),
                             SWP_NOACTIVATE | SWP_SHOWWINDOW)
        return True

    def visible(self) -> bool:
        """Utilise par les tests."""
        return bool(self._hwnd
                    and _user32.IsWindowVisible(wintypes.HWND(self._hwnd)))

    def cacher(self) -> None:
        if self._hwnd:
            _user32.ShowWindow(wintypes.HWND(self._hwnd), SW_HIDE)

    def detruire(self) -> None:
        if self._hwnd:
            try:
                _user32.DestroyWindow(wintypes.HWND(self._hwnd))
            except Exception:
                pass
            self._hwnd = None


# ------------------------------------------------------ reprise du bandeau

class SourceEntree:
    """D'ou viennent la position du curseur et l'etat du bouton.

    Cette indirection existe pour les tests. Eprouver un glisser en
    synthetisant de vrais clics revient a prendre la souris de l'utilisateur
    pendant une demi-minute — et ce n'est meme pas fiable : s'il touche sa
    souris, ses mouvements se melangent aux consignes du test et les mesures
    deviennent du bruit.

    En injectant une source scriptee, le test eprouve exactement le meme code —
    detection des zones, apercu, positionnement — sans toucher au materiel.
    """

    def curseur(self) -> tuple[int, int]:
        return curseur()

    def bouton_enfonce(self) -> bool:
        return bouton_gauche_enfonce()


class Gestion:
    """Deplacement, ancrage, agrandissement et reduction d'une fenetre sans
    bandeau.

    L'agrandissement est fait **a la main** — memoriser le rectangle, se poser
    sur la zone de travail — plutot que confie a l'etat « agrandi » du systeme.
    Pour une fenetre sans bandeau mais a cadre epais, Windows calcule une
    taille agrandie qui deborde de la largeur du cadre sur chaque cote et
    recouvre la barre des taches.
    """

    #: Cadence des boucles de suivi. Environ 140 fois par seconde : au-dela on
    #: n'occupe qu'un coeur pour rien, en deca le deplacement accroche.
    PAS_S = 0.007

    #: Hauteur minimale conservee lors d'un redimensionnement par le haut.
    HAUTEUR_MINI = 420

    #: Duree au-dela de laquelle un glisser n'en est plus un.
    #:
    #: Ces boucles repositionnent la fenetre cent quarante fois par seconde et
    #: gardent un apercu au-dessus de tout. Bloquees — un relachement que
    #: `GetAsyncKeyState` manquerait, un ecran qui se deconnecte — elles
    #: agiteraient une fenetre toujours au premier plan indefiniment, ce qui
    #: rend le bureau inutilisable : ni Alt+Tab ni la vue des taches ne
    #: passent devant. Une minute est deja dix fois plus qu'un glisser reel.
    DUREE_MAX_S = 60.0

    def __init__(self, obtenir_hwnd, entree: SourceEntree | None = None):
        # Le descripteur n'existe pas encore a la construction : la fenetre
        # n'est creee que plus tard par la boucle graphique.
        self._obtenir_hwnd = obtenir_hwnd
        self._entree = entree or SourceEntree()
        self._rect_restaure: tuple[int, int, int, int] | None = None
        self._agrandie = False
        self._occupe = False
        self._verrou = threading.Lock()
        self._subclasse: Subclasse | None = None
        self.apercu = Apercu()
        #: Derniere zone d'ancrage appliquee, relue par les tests.
        self.dernier_ancrage: str | None = None
        #: Nombre de fois ou l'apercu a ete affiche. Compte plutot que guette :
        #: un test qui sonderait `apercu.visible()` de l'exterieur courrait
        #: derriere une fenetre qui n'apparait que sur les dernieres
        #: millisecondes du glisser.
        self.apercus_montres = 0

    @property
    def hwnd(self) -> int | None:
        try:
            return self._obtenir_hwnd()
        except Exception:
            # Journalise, meme si l'appelant se contente d'un « non ». Muet,
            # ce garde-fou a masque pendant une bascule entiere une conversion
            # de descripteur qui echouait : la fenetre gardait sa barre de
            # titre et le glisser ne repondait pas, sans un mot nulle part.
            _log.warning("descripteur de fenetre indisponible", exc_info=True)
            return None

    def preparer(self) -> bool:
        """Retire le bandeau, puis derive la procedure de fenetre.

        L'ordre compte : la procedure derivee doit etre posee **apres** le
        retrait du bandeau, pour que le recalcul de la zone cliente qu'elle
        declenche parte du style definitif.
        """
        hwnd = self.hwnd
        if not hwnd:
            return False
        retire = retirer_bandeau(hwnd)
        self._subclasse = Subclasse(hwnd)
        self._subclasse.poser()
        # Amorce la mesure de la bordure invisible pendant que la fenetre est
        # posee normalement : c'est le seul moment garanti fiable.
        marges_invisibles(hwnd)
        return retire

    @property
    def boucles_systeme(self) -> int:
        return self._subclasse.boucles_systeme if self._subclasse else 0

    @property
    def agrandie(self) -> bool:
        return self._agrandie

    def etat(self) -> dict:
        return {"agrandie": self._agrandie}

    def basculer_agrandissement(self) -> dict:
        hwnd = self.hwnd
        if not hwnd:
            return self.etat()
        if self._agrandie and self._rect_restaure is not None:
            self._restaurer_geometrie(hwnd)
        else:
            self._rect_restaure = rectangle(hwnd)
            poser_visible(hwnd, *zone_travail(hwnd))
            self._agrandie = True
            self._appliquer_coins(hwnd)
        return self.etat()

    def _restaurer_geometrie(self, hwnd: int) -> None:
        x, y, largeur, hauteur = self._rect_restaure
        self._rect_restaure = None
        self._agrandie = False
        poser(hwnd, x, y, largeur, hauteur)
        self._appliquer_coins(hwnd)

    def _appliquer_coins(self, hwnd: int) -> None:
        """D'equerre quand la fenetre couvre l'ecran, arrondie sinon.

        Sans cela, une fenetre agrandie garderait ses coins arrondis dans les
        angles carres de l'ecran, et le bureau se verrait dans les quatre
        trous.
        """
        poser_coins(hwnd, arrondis=not self._agrandie)

    def reduire(self) -> bool:
        hwnd = self.hwnd
        if not hwnd:
            return False
        reduire(hwnd)
        return True

    def montrer(self) -> bool:
        """Sort de l'etat reduit et passe au premier plan."""
        hwnd = self.hwnd
        if not hwnd:
            return False
        restaurer(hwnd)
        return True

    def fermer(self) -> None:
        self.apercu.detruire()

    # ---------------------------------------------------- suivi du curseur

    def commencer_deplacement(self) -> bool:
        """Lance le suivi du curseur, ancrage compris, dans un fil dedie."""
        return self._lancer(self._suivre_curseur)

    def commencer_redimensionnement_haut(self) -> bool:
        """Lance le suivi du bord haut dans un fil dedie."""
        return self._lancer(self._suivre_bord_haut)

    def _lancer(self, travail) -> bool:
        """Demarre `travail` dans un fil dedie, un seul a la fois.

        Un fil separe, et non la boucle du pont : celui-ci reste ainsi libre de
        traiter les autres appels pendant tout le glisser.
        """
        hwnd = self.hwnd
        if not hwnd:
            return False
        with self._verrou:
            if self._occupe:
                return False
            self._occupe = True
        threading.Thread(target=self._executer, args=(travail, hwnd),
                         name="cadre", daemon=True).start()
        return True

    def _executer(self, travail, hwnd: int) -> None:
        try:
            travail(hwnd)
        except Exception:
            _log.warning("suivi de fenetre interrompu", exc_info=True)
        finally:
            # Sans faute : un apercu laisse a l'ecran est une fenetre
            # translucide au-dessus de tout, que rien ne permet de fermer.
            self.apercu.cacher()
            with self._verrou:
                self._occupe = False

    def _echeance(self) -> float:
        return time.monotonic() + self.DUREE_MAX_S

    def _tient_toujours(self, echeance: float) -> bool:
        if not self._entree.bouton_enfonce():
            return False
        if time.monotonic() < echeance:
            return True
        _log.warning("glisser interrompu : plus de %.0f s sans relachement",
                     self.DUREE_MAX_S)
        return False

    def _suivre_curseur(self, hwnd: int) -> None:
        echeance = self._echeance()
        depart_x, depart_y = self._entree.curseur()
        x, y, largeur, hauteur = rectangle(hwnd)

        if self._rect_restaure is not None:
            # Glisser une fenetre agrandie ou ancree la ramene a sa taille,
            # comme le ferait un bandeau ordinaire. On la replace sous le
            # curseur en gardant sa position relative sur la barre, pour
            # qu'elle ne saute pas brusquement hors de la main.
            part = (depart_x - x) / largeur if largeur else 0.5
            _, _, largeur, hauteur = self._rect_restaure
            self._rect_restaure = None
            self._agrandie = False
            # Seul l'axe horizontal est recalcule : la barre de titre est en
            # haut dans les deux etats, l'ordonnee garde donc le curseur
            # dessus.
            x = int(depart_x - part * largeur)
            poser(hwnd, x, y, largeur, hauteur)
            self._appliquer_coins(hwnd)

        zone_armee = rect_armee = None
        while self._tient_toujours(echeance):
            cx, cy = self._entree.curseur()
            poser(hwnd, x + (cx - depart_x), y + (cy - depart_y))
            zone, rect = zone_ancrage(cx, cy)
            if zone != zone_armee:
                zone_armee, rect_armee = zone, rect
                if zone:
                    # Compte les apercus **reellement affiches**, pas les
                    # tentatives : compter les secondes laissait passer une
                    # fenetre d'apercu qui ne se creait jamais.
                    if self.apercu.montrer(rect):
                        self.apercus_montres += 1
                    else:
                        _log.warning("apercu d'ancrage indisponible")
                else:
                    self.apercu.cacher()
            time.sleep(self.PAS_S)

        self.apercu.cacher()
        if zone_armee and rect_armee:
            # La taille d'avant l'ancrage est memorisee : un nouveau glisser la
            # rendra, comme le fait Windows.
            self._rect_restaure = (x, y, largeur, hauteur)
            self._agrandie = (zone_armee == "plein ecran")
            poser_visible(hwnd, *rect_armee)
            self._appliquer_coins(hwnd)
            self.dernier_ancrage = zone_armee
        else:
            self.dernier_ancrage = None

    def _suivre_bord_haut(self, hwnd: int) -> None:
        """Redimensionnement par le bord haut.

        Ce bord appartient desormais a la page (cf. `Subclasse`), donc Windows
        n'y voit plus une poignee : c'est la page qui reconnait la bande de
        quelques pixels et redemande la manipulation.
        """
        echeance = self._echeance()
        x, y, largeur, hauteur = rectangle(hwnd)
        bas = y + hauteur
        while self._tient_toujours(echeance):
            _, cy = self._entree.curseur()
            haut = min(cy, bas - self.HAUTEUR_MINI)
            poser(hwnd, x, haut, largeur, bas - haut)
            time.sleep(self.PAS_S)

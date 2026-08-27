"""Insertion du texte dans l'application active.

Decision D4, tranchee par les mesures de T0.1 :

  presse-papier + Ctrl+V   5 applications sur 5, ~3 ms, insensible a la
                           longueur du texte. Strategie par defaut.
  frappe Unicode           16 ms par caractere, et surtout VULNERABLE aux
                           autocorrections de l'application cible. Dernier
                           recours uniquement.

Ce dernier point est le moins evident et le plus important : les applications
corrigent ce qui est TAPE, jamais ce qui est COLLE. Le Bloc-notes de Windows 11
transforme « aeiou » en « Aeiou » a la frappe, alors que le collage passe
intact. Word, les navigateurs avec correcteur et beaucoup de champs de saisie
font de meme. Le presse-papier est donc la seule voie qui garantisse que le
texte insere est exactement celui qui a ete transcrit.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56
VK_C = 0x43

#: Les modificateurs qu'un raccourci peut laisser enfonces derriere lui.
VK_MENU = 0x12          # Alt
VK_SHIFT = 0x10
VK_LWIN = 0x5B
VK_RWIN = 0x5C
MODIFICATEURS = (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

#: Formats standards que l'on sait nommer, pour expliquer a l'utilisateur ce
#: qu'il perdrait plutot que de le lui prendre en silence.
FORMATS_CONNUS = {
    1: "du texte brut",
    2: "une image",
    3: "un trace vectoriel",
    8: "une image",
    14: "une image",
    15: "des fichiers",
    13: "du texte",
    16: "une locale",
    17: "une image",
}

#: Formats qui accompagnent souvent du texte sans etre du texte : les perdre
#: revient a perdre la mise en forme, pas le contenu.
FORMATS_ENRICHIS = {"HTML Format", "Rich Text Format", "RTF As Text"}


class ErreurInjection(Exception):
    """Le texte n'a pas pu etre insere."""


# --------------------------------------------------------------------------
# Structures Win32
# --------------------------------------------------------------------------

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _Union(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _Union)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.GetForegroundWindow.restype = wintypes.HWND


# --------------------------------------------------------------------------
# Construction des evenements — pur, donc testable sans rien envoyer
# --------------------------------------------------------------------------

def _touche(code: int, monte: bool = False) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD,
                 ki=KEYBDINPUT(wVk=code, wScan=0,
                               dwFlags=KEYEVENTF_KEYUP if monte else 0,
                               time=0, dwExtraInfo=0))


def _caractere(code: int, monte: bool = False) -> INPUT:
    drapeaux = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if monte else 0)
    return INPUT(type=INPUT_KEYBOARD,
                 ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=drapeaux,
                               time=0, dwExtraInfo=0))


def _raccourci_controle(touche: int) -> list[INPUT]:
    """Ctrl enfonce, la touche, puis tout relache — dans cet ordre."""
    return [_touche(VK_CONTROL), _touche(touche),
            _touche(touche, monte=True), _touche(VK_CONTROL, monte=True)]


def evenements_collage() -> list[INPUT]:
    return _raccourci_controle(VK_V)


def evenements_copie() -> list[INPUT]:
    return _raccourci_controle(VK_C)


def touche_enfoncee(code: int) -> bool:
    """Etat PHYSIQUE d'une touche, sans passer par la file de messages."""
    return bool(user32.GetAsyncKeyState(code) & 0x8000)


def attendre_les_doigts(limite_s: float = 1.0, pas_s: float = 0.02) -> bool:
    """Attend que plus aucun modificateur ne soit enfonce. Vrai s'ils le sont.

    Indispensable avant d'envoyer un raccourci depuis un raccourci. Quand
    l'utilisateur declenche l'apprentissage par Ctrl+Alt+C, il tient encore
    Ctrl et Alt au moment ou l'on voudrait envoyer le Ctrl+C : le systeme voit
    alors Ctrl+Alt+C — la combinaison de depart — et l'application ne copie
    rien. C'est exactement ce qui se passait, selection a l'ecran et
    presse-papier inchange.

    On ne peut pas relacher une touche que l'utilisateur tient : on attend
    qu'il la lache, ce qui prend le temps d'un clignement.
    """
    fin = time.monotonic() + limite_s
    while time.monotonic() < fin:
        if not any(touche_enfoncee(code) for code in MODIFICATEURS):
            return True
        time.sleep(pas_s)
    return False


def copier_la_selection(delai_s: float = 0.14) -> None:
    """Demande a l'application au premier plan de copier sa selection.

    Le delai laisse a l'application le temps de repondre : `SendInput` ne fait
    que deposer la frappe dans sa file, et rien ne garantit qu'elle l'ait
    traitee au retour.
    """
    attendre_les_doigts()
    _envoyer(evenements_copie())
    time.sleep(delai_s)




def evenements_frappe(texte: str) -> list[INPUT]:
    """Un couple appui/relachement par caractere.

    Les caracteres hors du plan multilingue de base sont emis en paire de
    substitution, faute de quoi les emojis seraient tronques.
    """
    evenements: list[INPUT] = []
    for caractere in texte:
        code = ord(caractere)
        if code > 0xFFFF:
            code -= 0x10000
            unites = (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF))
        else:
            unites = (code,)
        for unite in unites:
            evenements.append(_caractere(unite))
            evenements.append(_caractere(unite, monte=True))
    return evenements


def _envoyer(evenements: list[INPUT]) -> None:
    if not evenements:
        return
    nombre = len(evenements)
    tableau = (INPUT * nombre)(*evenements)
    envoyes = user32.SendInput(nombre, tableau, ctypes.sizeof(INPUT))
    if envoyes != nombre:
        raise ErreurInjection(
            f"SendInput a rejete {nombre - envoyes}/{nombre} evenements "
            f"(code {ctypes.get_last_error()})")


# --------------------------------------------------------------------------
# Presse-papier
# --------------------------------------------------------------------------

def _ouvrir_presse_papier(tentatives: int = 12) -> bool:
    """Le presse-papier est une ressource globale ; une autre application peut
    le detenir un instant. On reessaie brievement plutot que d'abandonner."""
    for _ in range(tentatives):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def lire_presse_papier() -> str | None:
    """Texte du presse-papier, ou None s'il est vide ou non textuel."""
    if not _ouvrir_presse_papier():
        raise ErreurInjection("presse-papier inaccessible en lecture")
    try:
        poignee = user32.GetClipboardData(CF_UNICODETEXT)
        if not poignee:
            return None
        pointeur = kernel32.GlobalLock(poignee)
        if not pointeur:
            return None
        try:
            return ctypes.wstring_at(pointeur)
        finally:
            kernel32.GlobalUnlock(poignee)
    finally:
        user32.CloseClipboard()


def ecrire_presse_papier(texte: str) -> None:
    donnees = texte + "\0"
    taille = len(donnees) * ctypes.sizeof(ctypes.c_wchar)
    poignee = kernel32.GlobalAlloc(GMEM_MOVEABLE, taille)
    if not poignee:
        raise ErreurInjection("GlobalAlloc a echoue")
    pointeur = kernel32.GlobalLock(poignee)
    if not pointeur:
        raise ErreurInjection("GlobalLock a echoue")
    ctypes.memmove(pointeur, ctypes.create_unicode_buffer(donnees), taille)
    kernel32.GlobalUnlock(poignee)

    if not _ouvrir_presse_papier():
        raise ErreurInjection("presse-papier inaccessible en ecriture")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, poignee):
            raise ErreurInjection("SetClipboardData a echoue")
        # Le systeme possede desormais la poignee : ne pas la liberer.
    finally:
        user32.CloseClipboard()


# --------------------------------------------------------------------------
# Inspection du presse-papier
# --------------------------------------------------------------------------

def _nom_format(identifiant: int) -> str:
    if identifiant in FORMATS_CONNUS:
        return FORMATS_CONNUS[identifiant]
    tampon = ctypes.create_unicode_buffer(256)
    if user32.GetClipboardFormatNameW(identifiant, tampon, 256):
        return tampon.value
    return f"format {identifiant}"


def formats_presse_papier() -> list[int]:
    """Identifiants des formats presents. Presse-papier deja ouvert requis."""
    formats = []
    identifiant = 0
    while True:
        identifiant = user32.EnumClipboardFormats(identifiant)
        if not identifiant:
            break
        formats.append(identifiant)
    return formats


@dataclass(frozen=True)
class ContenuPressePapier:
    """Ce que contenait le presse-papier avant qu'on s'en serve.

    On ne sait restaurer que le texte : sauvegarder fidelement une image ou
    une liste de fichiers demanderait de recopier chaque format, dont certains
    sont produits a la demande par l'application source et ne survivraient pas
    a la manipulation. Plutot que de pretendre le contraire, on constate ce
    qu'on va perdre et on le dit.
    """

    texte: str | None
    formats: tuple[int, ...] = ()
    noms: tuple[str, ...] = ()

    @property
    def vide(self) -> bool:
        return not self.formats

    @property
    def restaurable(self) -> bool:
        """Vrai si rendre le texte suffit a remettre les choses en etat."""
        return self.vide or self.texte is not None

    @property
    def perte(self) -> str | None:
        """Ce qui sera perdu, formule pour un humain — ou None si rien."""
        if self.vide:
            return None

        if self.texte is None:
            autres = {n for n in self.noms if n not in FORMATS_ENRICHIS}
            quoi = ", ".join(sorted(autres)) if autres else "un contenu"
            return f"le presse-papier contenait {quoi}, qui sera perdu"

        enrichis = sorted(n for n in self.noms if n in FORMATS_ENRICHIS)
        if enrichis:
            return ("la mise en forme du presse-papier sera perdue "
                    f"({', '.join(enrichis)}), le texte sera rendu")
        return None


def contenu_presse_papier() -> ContenuPressePapier:
    """Photographie du presse-papier : texte si possible, formats presents."""
    if not _ouvrir_presse_papier():
        raise ErreurInjection("presse-papier inaccessible en lecture")
    try:
        formats = formats_presse_papier()
        noms = tuple(_nom_format(f) for f in formats)

        texte = None
        if CF_UNICODETEXT in formats:
            poignee = user32.GetClipboardData(CF_UNICODETEXT)
            if poignee:
                pointeur = kernel32.GlobalLock(poignee)
                if pointeur:
                    try:
                        texte = ctypes.wstring_at(pointeur)
                    finally:
                        kernel32.GlobalUnlock(poignee)
        return ContenuPressePapier(texte=texte, formats=tuple(formats),
                                   noms=noms)
    finally:
        user32.CloseClipboard()


def vider_presse_papier() -> None:
    if not _ouvrir_presse_papier():
        raise ErreurInjection("presse-papier inaccessible")
    try:
        user32.EmptyClipboard()
    finally:
        user32.CloseClipboard()


# --------------------------------------------------------------------------
# Fenetre active
# --------------------------------------------------------------------------

def fenetre_active() -> tuple[str, str]:
    """Titre et nom d'executable de la fenetre au premier plan.

    Sert aux journaux, et servira au lexique contextuel (F11) : le vocabulaire
    d'un editeur de code n'est pas celui d'un courriel.
    """
    poignee = user32.GetForegroundWindow()
    if not poignee:
        return "", ""

    longueur = user32.GetWindowTextLengthW(poignee)
    tampon = ctypes.create_unicode_buffer(longueur + 1)
    user32.GetWindowTextW(poignee, tampon, longueur + 1)
    titre = tampon.value

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(poignee, ctypes.byref(pid))
    executable = ""
    if pid.value:
        # 0x1000 = PROCESS_QUERY_LIMITED_INFORMATION : suffisant pour lire le
        # chemin, et accorde meme sans privileges eleves.
        processus = kernel32.OpenProcess(0x1000, False, pid.value)
        if processus:
            try:
                chemin = ctypes.create_unicode_buffer(260)
                taille = wintypes.DWORD(260)
                if kernel32.QueryFullProcessImageNameW(
                        processus, 0, chemin, ctypes.byref(taille)):
                    executable = chemin.value.rsplit("\\", 1)[-1]
            finally:
                kernel32.CloseHandle(processus)
    return titre, executable


# --------------------------------------------------------------------------
# Strategies
# --------------------------------------------------------------------------

def injecter_par_presse_papier(texte: str, delai_collage: float = 0.05) -> None:
    ecrire_presse_papier(texte)
    time.sleep(delai_collage)  # laisse le presse-papier se stabiliser
    _envoyer(evenements_collage())


def injecter_par_frappe(texte: str, pause_ms: int = 15) -> None:
    """Frappe caractere par caractere.

    Le rythme est impose par la mesure : en dessous d'une quinzaine de
    millisecondes, l'application cible perd des evenements et le texte arrive
    tronque ou avec des caracteres repetes.
    """
    pause = pause_ms / 1000.0
    for evenement in evenements_frappe(texte):
        _envoyer([evenement])
        if evenement.ki.dwFlags & KEYEVENTF_KEYUP:
            time.sleep(pause)


@dataclass(frozen=True)
class ResultatInjection:
    """Ce qui s'est passe pendant l'insertion.

    `duree_pose_ms` s'arrete a l'arrivee du texte, pas a la fin de la
    restauration du presse-papier : celle-ci a lieu ensuite, alors que
    l'utilisateur a deja son texte sous les yeux. La compter fausserait la
    latence percue.
    """

    duree_pose_ms: float = 0.0
    avertissement: str | None = None
    restaure: bool = False


class Injecteur:
    """Insere du texte selon la strategie configuree.

    Quand la restauration du presse-papier est active, le contenu precedent
    est remis en place APRES que le collage a eu lieu. Le delai n'est pas
    cosmetique : restaurer trop tot ferait coller l'ancienne valeur a la place
    de la dictee.
    """

    def __init__(self, conf):
        self.conf = conf
        # Serialise l'usage du presse-papier : une restauration en cours ne
        # doit pas se superposer a l'injection suivante.
        self._verrou = threading.Lock()

    @property
    def strategie(self) -> str:
        return self.conf["injection.strategie"]

    def injecter(self, texte: str) -> ResultatInjection:
        if not texte:
            return ResultatInjection()

        debut = time.perf_counter()

        if self.strategie == "frappe":
            injecter_par_frappe(texte, self.conf["injection.frappe_pause_ms"])
            return ResultatInjection(
                duree_pose_ms=(time.perf_counter() - debut) * 1000)

        if self.strategie != "presse_papier":  # la validation l'interdit deja
            raise ErreurInjection(f"strategie inconnue : {self.strategie!r}")

        if not self.conf["injection.restaurer_presse_papier"]:
            with self._verrou:
                injecter_par_presse_papier(texte)
            return ResultatInjection(
                duree_pose_ms=(time.perf_counter() - debut) * 1000)

        return self._injecter_en_preservant(texte, debut)

    def _injecter_en_preservant(self, texte: str,
                                debut: float) -> ResultatInjection:
        with self._verrou:
            try:
                avant = contenu_presse_papier()
            except ErreurInjection:
                # Ne pas renoncer a la dictee parce qu'on n'a pas pu lire le
                # presse-papier : le texte compte plus que sa sauvegarde.
                avant = None

            injecter_par_presse_papier(texte)
            pose = (time.perf_counter() - debut) * 1000

            if avant is None:
                return ResultatInjection(
                    duree_pose_ms=pose,
                    avertissement="presse-papier illisible : son contenu n'a "
                                  "pas ete sauvegarde")

            time.sleep(self.conf["injection.delai_restauration_ms"] / 1000.0)
            self._restaurer(avant)
            return ResultatInjection(duree_pose_ms=pose,
                                     avertissement=avant.perte,
                                     restaure=avant.restaurable)

    def _restaurer(self, avant: ContenuPressePapier) -> None:
        try:
            if avant.vide:
                vider_presse_papier()
            elif avant.texte is not None:
                ecrire_presse_papier(avant.texte)
            # Contenu non textuel : rien a remettre. La dictee reste dans le
            # presse-papier, ce qui vaut mieux qu'un presse-papier vide.
        except ErreurInjection:
            pass  # la dictee est posee : un echec ici ne doit rien casser

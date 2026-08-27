"""Raccourcis clavier globaux, sans hook clavier.

Decision D2 : le maintien impose de detecter le RELACHEMENT de la touche, ce
que `RegisterHotKey` ne signale pas. La solution habituelle est un hook
`WH_KEYBOARD_LL`, mais il intercepte toutes les frappes du systeme : c'est
techniquement un enregistreur de frappe, souvent signale par les antivirus, et
absurde dans un outil choisi pour sa confidentialite.

On combine donc deux mecanismes officiels :

  RegisterHotKey     signale l'appui, et uniquement sur notre combinaison ;
  GetAsyncKeyState   scrute le relachement, uniquement pendant une dictee.

L'application ne voit jamais une frappe qui ne la concerne pas.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from typing import Callable

from . import journal

_log = journal.obtenir("hotkeys")

user32 = ctypes.WinDLL("user32", use_last_error=True)

# Modificateurs acceptes par RegisterHotKey
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
# Sans MOD_NOREPEAT, maintenir la touche declenche WM_HOTKEY en rafale.
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MODIFICATEURS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT, "maj": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN,
}

#: Touches nommees, au-dela des lettres et chiffres.
TOUCHES = {
    "espace": 0x20, "space": 0x20,
    "entree": 0x0D, "enter": 0x0D,
    "tab": 0x09,
    "echap": 0x1B, "esc": 0x1B,
    "inser": 0x2D, "insert": 0x2D,
    "suppr": 0x2E, "delete": 0x2E,
    "haut": 0x26, "bas": 0x28, "gauche": 0x25, "droite": 0x27,
    **{f"f{n}": 0x6F + n for n in range(1, 25)},
}


class ErreurRaccourci(Exception):
    """Raccourci invalide ou impossible a enregistrer."""


def analyser(raccourci: str) -> tuple[int, int]:
    """Traduit « ctrl+alt+d » en (modificateurs, code de touche).

    Leve une erreur explicite plutot que de rendre un raccourci muet : un
    raccourci silencieusement inactif est le pire des defauts, l'utilisateur
    croit que l'application est cassee.
    """
    morceaux = [m.strip().lower() for m in raccourci.split("+") if m.strip()]
    if not morceaux:
        raise ErreurRaccourci(f"raccourci vide : {raccourci!r}")

    *noms_mods, nom_touche = morceaux

    modificateurs = 0
    for nom in noms_mods:
        if nom not in MODIFICATEURS:
            raise ErreurRaccourci(
                f"modificateur inconnu : {nom!r} dans {raccourci!r}. "
                f"Attendus : {', '.join(sorted(set(MODIFICATEURS)))}.")
        modificateurs |= MODIFICATEURS[nom]

    if not modificateurs:
        raise ErreurRaccourci(
            f"{raccourci!r} n'a aucun modificateur. Un raccourci global sans "
            f"Ctrl, Alt ou Win capterait la touche dans toutes les "
            f"applications.")

    if nom_touche in TOUCHES:
        code = TOUCHES[nom_touche]
    elif len(nom_touche) == 1 and nom_touche.isalnum():
        code = ord(nom_touche.upper())
    else:
        raise ErreurRaccourci(
            f"touche inconnue : {nom_touche!r} dans {raccourci!r}. "
            f"Attendu une lettre, un chiffre, ou l'un de : "
            f"{', '.join(sorted(TOUCHES))}.")

    return modificateurs | MOD_NOREPEAT, code


def touche_enfoncee(code: int) -> bool:
    """Etat instantane d'une touche, sans intercepter quoi que ce soit."""
    return bool(user32.GetAsyncKeyState(code) & 0x8000)


class Raccourci:
    """Un raccourci enregistre, et ce qu'il declenche."""

    def __init__(self, nom: str, combinaison: str, maintien: bool,
                 debut: Callable[[], None], fin: Callable[[], None] | None = None):
        self.nom = nom
        self.combinaison = combinaison
        self.maintien = maintien
        self.debut = debut
        self.fin = fin
        self.modificateurs, self.code = analyser(combinaison)
        self.actif = False


class Gestionnaire:
    """Boucle de messages Win32 dediee aux raccourcis globaux.

    RegisterHotKey lie le raccourci au fil qui l'enregistre : enregistrement,
    boucle de messages et desenregistrement doivent donc vivre sur le meme
    fil, d'ou ce fil dedie.
    """

    PERIODE_SCRUTATION = 0.02  # 50 Hz : imperceptible, cout negligeable

    def __init__(self):
        self._raccourcis: dict[int, Raccourci] = {}
        self._prochain_id = 1
        self._fil: threading.Thread | None = None
        self._id_fil: int | None = None
        self._pret = threading.Event()
        self._erreur: Exception | None = None
        self._arret = threading.Event()

    def ajouter(self, nom: str, combinaison: str, debut: Callable[[], None],
                fin: Callable[[], None] | None = None,
                maintien: bool = False) -> None:
        """Declare un raccourci. A appeler avant `demarrer()`."""
        if self._fil is not None:
            raise ErreurRaccourci("ajouter() doit etre appele avant demarrer()")
        if maintien and fin is None:
            raise ErreurRaccourci(
                f"le raccourci {nom!r} est en mode maintien mais n'a pas de "
                f"rappel de fin : le relachement ne servirait a rien.")
        self._raccourcis[self._prochain_id] = Raccourci(
            nom, combinaison, maintien, debut, fin)
        self._prochain_id += 1

    # -- fil dedie ---------------------------------------------------------

    def _enregistrer_tout(self) -> None:
        enregistres: list[int] = []
        for identifiant, raccourci in self._raccourcis.items():
            ok = user32.RegisterHotKey(None, identifiant,
                                       raccourci.modificateurs, raccourci.code)
            if not ok:
                code_erreur = ctypes.get_last_error()
                for deja in enregistres:
                    user32.UnregisterHotKey(None, deja)
                indice = (" Ce raccourci est probablement deja pris par une "
                          "autre application." if code_erreur == 1409 else "")
                raise ErreurRaccourci(
                    f"impossible d'enregistrer {raccourci.combinaison!r} "
                    f"pour « {raccourci.nom} » (code {code_erreur}).{indice}")
            enregistres.append(identifiant)

    def _surveiller_relachement(self, raccourci: Raccourci) -> None:
        """Attend le relachement de la touche principale, puis signale la fin.

        Tourne sur un fil dedie pour ne pas bloquer la boucle de messages : un
        second appui pendant une dictee doit rester recevable.
        """
        while not self._arret.is_set():
            if not touche_enfoncee(raccourci.code):
                break
            time.sleep(self.PERIODE_SCRUTATION)
        raccourci.actif = False
        if raccourci.fin is not None:
            try:
                raccourci.fin()
            except Exception:
                _log.exception("la fin du raccourci « %s » a echoue",
                               raccourci.nom)

    def _traiter(self, identifiant: int) -> None:
        raccourci = self._raccourcis.get(identifiant)
        if raccourci is None:
            return

        if not raccourci.maintien:
            raccourci.debut()
            return

        if raccourci.actif:
            return  # deja en cours : on ignore la repetition
        raccourci.actif = True
        raccourci.debut()
        threading.Thread(target=self._surveiller_relachement,
                         args=(raccourci,), daemon=True,
                         name=f"relachement-{raccourci.nom}").start()

    def _boucle(self) -> None:
        self._id_fil = ctypes.windll.kernel32.GetCurrentThreadId()
        try:
            self._enregistrer_tout()
        except Exception as exc:
            self._erreur = exc
            self._pret.set()
            return

        self._pret.set()

        message = wintypes.MSG()
        try:
            while not self._arret.is_set():
                obtenu = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if obtenu in (0, -1):  # WM_QUIT ou erreur
                    break
                if message.message == WM_HOTKEY:
                    try:
                        self._traiter(message.wParam)
                    except Exception:
                        # Sans cette prise, une seule exception dans un rappel
                        # emportait la boucle : le `finally` ci-dessous rendait
                        # TOUS les raccourcis, l'application continuait de
                        # tourner, icone comprise, et ne repondait plus jamais
                        # au clavier. Rien dans le journal, rien a l'ecran —
                        # une application compilee sans console n'a pas meme
                        # de sortie d'erreur ou deposer la trace.
                        nom = getattr(self._raccourcis.get(message.wParam),
                                      "nom", message.wParam)
                        _log.exception("le rappel du raccourci « %s » a "
                                       "echoue ; les autres restent actifs",
                                       nom)
        finally:
            for identifiant in self._raccourcis:
                user32.UnregisterHotKey(None, identifiant)
            if not self._arret.is_set():
                _log.error("la boucle des raccourcis s'est arretee toute "
                           "seule : plus aucune combinaison n'est ecoutee")

    def demarrer(self, timeout: float = 5.0) -> None:
        """Lance la boucle et attend que les raccourcis soient enregistres."""
        if self._fil is not None:
            return
        if not self._raccourcis:
            raise ErreurRaccourci("aucun raccourci declare")

        self._arret.clear()
        self._pret.clear()
        self._erreur = None
        self._fil = threading.Thread(target=self._boucle, daemon=True,
                                     name="raccourcis")
        self._fil.start()

        if not self._pret.wait(timeout):
            self.arreter()
            raise ErreurRaccourci("le fil des raccourcis n'a pas demarre a temps")
        if self._erreur is not None:
            erreur, self._erreur = self._erreur, None
            self._fil = None
            raise erreur

    def arreter(self, timeout: float = 3.0) -> None:
        self._arret.set()
        fil, self._fil = self._fil, None
        if self._id_fil is not None:
            # Debloque GetMessageW, qui attend sans consommer de processeur.
            ctypes.windll.user32.PostThreadMessageW(self._id_fil, WM_QUIT, 0, 0)
        if fil is not None and fil.is_alive():
            fil.join(timeout=timeout)
        self._id_fil = None

    @property
    def en_cours(self) -> bool:
        return self._fil is not None and self._fil.is_alive()

    def __enter__(self) -> Gestionnaire:
        self.demarrer()
        return self

    def __exit__(self, *_) -> None:
        self.arreter()

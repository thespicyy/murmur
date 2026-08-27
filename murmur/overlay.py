"""Indicateur de dictee.

Une barre flottante, posee au-dessus de tout : le symbole a gauche, un bouton
pour annuler, un vumetre qui suit la voix, un bouton pour valider.

Le dessin lui-meme vit dans `rendu.py` — le canevas de Tk ne fait aucun
anticrenelage, et son unique mode de transparence est une couleur-cle, sans
demi-teinte. La barre est donc peinte par GDI en fenetre a couches.

Contrainte absolue : elle ne doit JAMAIS prendre le focus. Sans
`WS_EX_NOACTIVATE`, son apparition volerait le focus a l'application cible et
le texte s'insererait au mauvais endroit — le defaut qui rendrait l'outil
inutilisable. Ce style laisse neanmoins passer les clics, ce qui permet les
deux boutons.

Tkinter doit tourner sur le fil principal : l'indicateur expose donc une file
de commandes que les autres fils alimentent sans le toucher directement.
"""

from __future__ import annotations

import ctypes
import queue
import tkinter as tk
from ctypes import wintypes
from typing import Callable

from . import journal, rendu, theme as module_theme
from .app import Etat

user32 = ctypes.WinDLL("user32", use_last_error=True)

#: Les dimensions ne sont pas recopiees ici : `rendu` les recalcule au
#: demarrage selon l'echelle de l'ecran, et une copie prise a l'import
#: resterait a la taille de reference.

#: Distance au bas de l'ecran, en hauteurs de barre. Exprimee ainsi plutot
#: qu'en pixels : sur un ecran a 125 %, une marge fixe rapprocherait la barre
#: du bord a mesure qu'elle grandit.
MARGES_BASSES = 96 / 31

#: Tolerance autour des boutons, en hauteurs de barre : viser un disque de
#: quinze pixels a la souris demande une precision inutile.
MARGE_CLIC = 7 / 31


class Indicateur:
    """Barre de dictee. Toutes les methodes publiques sont sures entre fils."""

    def __init__(self, racine: tk.Tk, conf, theme: module_theme.Theme,
                 sur_annuler: Callable[[], None] | None = None,
                 sur_valider: Callable[[], None] | None = None,
                 niveau: Callable[[], float] | None = None):
        self.conf = conf
        self.theme = theme
        self.racine = racine
        self.sur_annuler = sur_annuler
        self.sur_valider = sur_valider
        self.niveau = niveau or (lambda: 0.0)

        self._commandes: queue.Queue = queue.Queue()
        self._etat = Etat.REPOS
        self._visible = False
        self._phase = 0.0
        self._position = (0, 0)
        self._echecs_peinture = 0
        self._log = journal.obtenir("overlay")

        self.fenetre = tk.Toplevel(racine)
        self.fenetre.withdraw()
        self.fenetre.overrideredirect(True)
        self.fenetre.attributes("-topmost", True)
        self.fenetre.geometry(f"{rendu.LARGEUR}x{rendu.HAUTEUR}+0+0")
        self.fenetre.bind("<Button-1>", self._clic)

        self.fenetre.update_idletasks()
        self.hwnd = user32.GetParent(self.fenetre.winfo_id()) \
            or self.fenetre.winfo_id()
        rendu.poser_styles(self.hwnd)
        self.non_focusable = self._verifier_non_focusable()

        self.racine.after(60, self._traiter_commandes)

    def _verifier_non_focusable(self) -> bool:
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            user32.GetWindowLongPtrW.restype = ctypes.c_longlong
            user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
            lire = user32.GetWindowLongPtrW
        else:
            lire = user32.GetWindowLongW
        return bool(lire(self.hwnd, rendu.GWL_EXSTYLE) & rendu.WS_EX_NOACTIVATE)

    # -- zones sensibles ---------------------------------------------------

    def _zone(self, centre: tuple[float, float], x: float, y: float) -> bool:
        cx, cy = centre
        rayon = rendu.RAYON_BOUTON + MARGE_CLIC * rendu.HAUTEUR
        return (x - cx) ** 2 + (y - cy) ** 2 <= rayon ** 2

    def _clic(self, evenement) -> None:
        if self._zone(rendu.centre_annuler(), evenement.x, evenement.y):
            if self.sur_annuler:
                self.sur_annuler()
        elif self._zone(rendu.centre_valider(), evenement.x, evenement.y):
            if self.sur_valider:
                self.sur_valider()

    # -- affichage ---------------------------------------------------------

    def _calculer_position(self) -> tuple[int, int]:
        position = self.conf["interface.indicateur_position"]
        largeur_ecran = self.fenetre.winfo_screenwidth()
        hauteur_ecran = self.fenetre.winfo_screenheight()

        largeur, hauteur = rendu.LARGEUR, rendu.HAUTEUR

        if position == "curseur":
            point = rendu.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            x, y = point.x - largeur // 2, point.y + hauteur
            x = max(0, min(x, largeur_ecran - largeur))
            y = max(0, min(y, hauteur_ecran - hauteur))
        elif position == "haut":
            x, y = (largeur_ecran - largeur) // 2, round(hauteur * 2)
        else:
            x, y = ((largeur_ecran - largeur) // 2,
                    hauteur_ecran - round(MARGES_BASSES * hauteur))
        return int(x), int(y)

    def _peindre(self) -> None:
        image = rendu.rendre(self._etat, self.niveau(), self._phase,
                             self.theme.palette)
        x, y = self._position
        if rendu.peindre(self.hwnd, image, x, y):
            self._echecs_peinture = 0
            return

        # Un echec silencieux laisserait l'utilisateur sans indicateur, sans
        # savoir pourquoi — exactement ce qui s'est produit lors du passage
        # au rendu par GDI.
        self._echecs_peinture += 1
        if self._echecs_peinture == 1:
            self._log.error(
                "impossible de peindre l'indicateur — la dictee fonctionne, "
                "mais la barre reste invisible")

    # -- commandes, depuis n'importe quel fil ------------------------------

    def montrer(self, etat: Etat) -> None:
        self._commandes.put(("etat", etat))

    def cacher(self) -> None:
        self._commandes.put(("cacher", None))

    def rafraichir_theme(self) -> None:
        self._commandes.put(("theme", None))

    def _traiter_commandes(self) -> None:
        try:
            while True:
                nom, valeur = self._commandes.get_nowait()
                if nom == "etat":
                    self._appliquer_etat(valeur)
                elif nom == "cacher":
                    self._masquer()
                elif nom == "theme" and self._visible:
                    self._peindre()
        except queue.Empty:
            pass

        if self._visible:
            self._phase += 0.42
            self._peindre()

        # Cadence rapide seulement quand la barre est affichee : au repos,
        # repeindre seize fois par seconde ne servirait a rien.
        self.racine.after(60 if self._visible else 150,
                          self._traiter_commandes)

    def _appliquer_etat(self, etat: Etat) -> None:
        if etat is Etat.REPOS:
            self._masquer()
            return
        self._etat = etat
        if not self._visible:
            self._position = self._calculer_position()
            self._visible = True
            # Peindre AVANT d'afficher : une fenetre a couches montree sans
            # contenu apparait un instant en rectangle noir.
            self._peindre()
            self.fenetre.deiconify()
            self.fenetre.lift()
        self._peindre()

    def _masquer(self) -> None:
        if self._visible:
            self.fenetre.withdraw()
            self._visible = False
        self._etat = Etat.REPOS
        self._phase = 0.0

    def detruire(self) -> None:
        try:
            self.fenetre.destroy()
        except tk.TclError:
            pass

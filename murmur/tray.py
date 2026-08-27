"""Icone de zone de notification.

L'application vit en arriere-plan : l'icone est son seul point de contact
permanent. Elle reflete l'etat en couleur — une dictee en cours doit se voir
sans ouvrir quoi que ce soit.

L'icone est dessinee a la volee plutot que chargee depuis un fichier : elle
change de couleur selon l'etat et de contraste selon le theme. Un jeu
d'images figees demanderait huit fichiers pour le meme resultat.
"""

from __future__ import annotations

import threading
from typing import Callable

from . import journal, marque, systeme, theme as module_theme
from .app import Etat

TAILLE = 64  # Windows redimensionne ensuite ; dessiner grand evite l'escalier

#: L'icone garde ses couleurs propres, independamment du theme de Windows :
#: c'est ce qui la rend reconnaissable d'un poste a l'autre.
NOIR = "#0b0b0d"
BLANC = "#ffffff"

LIBELLES = {
    Etat.REPOS: "Murmur — pret",
    Etat.ECOUTE: "Murmur — ecoute",
    Etat.TRANSCRIPTION: "Murmur — transcription",
    Etat.INSERTION: "Murmur — insertion",
}


def dessiner_icone(couleur: str, contour: str, en_pause: bool = False):
    """Symbole blanc sur pastille noire, le point portant l'etat.

    La pastille n'est pas decorative : un trace transparent se perd sur une
    barre des taches sombre, alors qu'un fond constant garde son contraste
    quel que soit le theme de Windows.

    Suspendue, l'icone perd ses arcs et ne garde que le point : plus d'ondes,
    donc plus d'ecoute. Un symbole inchange laisserait croire l'application
    active.

    On force la declinaison compacte : l'icone est dessinee a 64 pixels mais
    Windows la reduit a 16 dans la barre des taches, ou la version a deux arcs
    fins devient une bouillie.
    """
    return marque.dessiner_pastille(
        TAILLE, couleur_point=couleur, couleur_arcs=BLANC, fond=NOIR,
        avec_arcs=not en_pause, compacte=True)


class Icone:
    """Icone de notification, pilotable depuis n'importe quel fil."""

    def __init__(self, conf, theme: module_theme.Theme,
                 sur_pause: Callable[[bool], None],
                 sur_quitter: Callable[[], None],
                 sur_ouvrir: Callable[[], None] | None = None,
                 sur_reglages: Callable[[], None] | None = None):
        self.conf = conf
        self.theme = theme
        self.sur_pause = sur_pause
        self.sur_quitter = sur_quitter
        self.sur_ouvrir = sur_ouvrir
        self.sur_reglages = sur_reglages

        self._log = journal.obtenir("tray")
        self._etat = Etat.REPOS
        self._en_pause = False
        self._icone = None
        self._fil: threading.Thread | None = None

    # -- construction ------------------------------------------------------

    def _image(self):
        palette = self.theme.palette
        couleur = {
            # Au repos le symbole est entierement blanc : une couleur d'etat
            # permanente attirerait l'oeil sans rien signaler.
            Etat.REPOS: BLANC,
            Etat.ECOUTE: palette.ecoute,
            Etat.TRANSCRIPTION: palette.transcription,
            Etat.INSERTION: palette.insertion,
        }[self._etat]
        return dessiner_icone(couleur, BLANC, self._en_pause)

    def _menu(self):
        import pystray

        elements = [
            pystray.MenuItem(lambda _: LIBELLES[self._etat], None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Suspendre la dictee", self._basculer_pause,
                checked=lambda _: self._en_pause),
            pystray.MenuItem(
                "Demarrer avec Windows", self._basculer_demarrage,
                checked=lambda _: systeme.demarrage_auto_actif()),
        ]
        if self.sur_ouvrir is not None:
            elements.append(pystray.MenuItem("Ouvrir Murmur", self._ouvrir,
                                             default=True))
        if self.sur_reglages is not None:
            elements.append(pystray.MenuItem("Reglages", self._reglages))
        elements += [pystray.Menu.SEPARATOR,
                     pystray.MenuItem("Quitter", self._quitter)]
        return pystray.Menu(*elements)

    # -- actions -----------------------------------------------------------

    def _basculer_pause(self) -> None:
        self._en_pause = not self._en_pause
        self._log.info("dictee %s", "suspendue" if self._en_pause else "reprise")
        try:
            self.sur_pause(not self._en_pause)
        except Exception:
            self._log.exception("echec du basculement de pause")
        self._redessiner()

    def _basculer_demarrage(self) -> None:
        """Inscrit ou retire Murmur du demarrage de Windows.

        L'etat est relu depuis le registre a chaque ouverture du menu plutot
        que memorise : l'utilisateur peut l'avoir modifie ailleurs, et une
        case a cocher qui ment est pire que pas de case du tout.
        """
        try:
            nouvel_etat = not systeme.demarrage_auto_actif()
            systeme.definir_demarrage_auto(nouvel_etat)
            self._log.info("demarrage automatique %s",
                           "active" if nouvel_etat else "desactive")
        except OSError:
            self._log.exception("impossible de modifier le demarrage automatique")

    def _ouvrir(self) -> None:
        if self.sur_ouvrir:
            try:
                self.sur_ouvrir()
            except Exception:
                self._log.exception("echec de l'ouverture de la fenetre")

    def _reglages(self) -> None:
        if self.sur_reglages:
            try:
                self.sur_reglages()
            except Exception:
                self._log.exception("echec de l'ouverture des reglages")

    def _quitter(self) -> None:
        """Prevenir l'application, puis retirer l'icone.

        `arreter` n'est PAS appele ici : cette methode s'execute sur le fil de
        l'icone, et `arreter` attend la fin de ce meme fil — Python refuse de
        joindre le fil courant et leve. L'exception remontait dans la boucle
        de pystray, ou elle se perdait. C'est l'application qui arretera
        l'icone, depuis son propre fil.
        """
        try:
            self.sur_quitter()
        except Exception:
            self._log.exception("echec de la demande d'arret")
        icone, self._icone = self._icone, None
        if icone is not None:
            try:
                icone.stop()
            except Exception:
                self._log.debug("icone deja arretee", exc_info=True)

    # -- etat --------------------------------------------------------------

    def changer_etat(self, etat: Etat) -> None:
        if etat is self._etat:
            return
        self._etat = etat
        self._redessiner()

    def rafraichir_theme(self) -> None:
        self._redessiner()

    def _redessiner(self) -> None:
        if self._icone is None:
            return
        try:
            self._icone.icon = self._image()
            self._icone.title = (LIBELLES[self._etat] if not self._en_pause
                                 else "Murmur — suspendu")
            self._icone.update_menu()
        except Exception:
            # Une icone qui refuse de se redessiner ne doit pas emporter
            # l'application : la dictee, elle, continue de fonctionner.
            self._log.exception("echec du rafraichissement de l'icone")

    # -- cycle de vie ------------------------------------------------------

    def demarrer(self) -> None:
        import pystray

        self._icone = pystray.Icon("murmur", self._image(),
                                   LIBELLES[self._etat], self._menu())
        self._fil = threading.Thread(target=self._icone.run, daemon=True,
                                     name="icone")
        self._fil.start()

    def arreter(self) -> None:
        icone, self._icone = self._icone, None
        if icone is not None:
            try:
                icone.stop()
            except Exception:
                pass
        fil, self._fil = self._fil, None
        # Jamais depuis le fil de l'icone : Python refuse de joindre le fil
        # courant et leve une RuntimeError qui se perdrait dans pystray.
        if fil is not None and fil is not threading.current_thread():
            fil.join(timeout=2.0)

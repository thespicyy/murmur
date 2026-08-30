"""Le programme Murmur : construction, demarrage, arret.

Le corps vit ici et non dans `__main__.py`, qui n'en est qu'une amorce de
trois lignes. La raison est concrete : PyInstaller ecarte de son analyse les
modules nommes `__main__` a l'interieur d'un paquet, les confondant avec le
script d'entree. L'executable se construisait alors sans une erreur et
tombait au lancement sur « No module named 'murmur.__main__' ».

L'application vit en arriere-plan : une icone pres de l'horloge, un
indicateur qui apparait pendant la dictee, et rien d'autre a l'ecran. Le
tableau de bord, lui, vit dans son propre processus, lance a la demande.

Tkinter impose sa boucle sur le fil principal. C'est donc elle qui mene la
danse : l'icone tourne sur son propre fil, le traitement des dictees aussi, et
tous poussent leurs demandes d'affichage vers le fil principal plutot que de
toucher aux fenetres directement.

    python -m murmur              lance l'application
    python -m murmur --console    ajoute les traces dans une console
    python -m murmur --tableau    ouvre le tableau de bord (usage interne)
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk

from . import canal as module_canal
from . import config as configuration
from . import correction as module_correction
from . import ecran
from . import sorties
from . import journal, overlay, premier_lancement, rendu
from . import systeme, tableau
from . import theme as module_theme, tray
from .app import Application, Etat, Resultat


class Murmur:
    def __init__(self, conf, verbeux: bool = False, verrou=None,
                 racine=None):
        self.conf = conf
        self.verrou = verrou
        self.verbeux = verbeux
        self.log = journal.obtenir("main")

        self.theme = module_theme.Theme(conf)
        self.application = Application(conf)

        # Tout ce qui vient d'un autre fil passe par ici.
        #
        # `after` de Tk n'est PAS sur entre fils : appele depuis le fil de
        # l'icone ou celui du canal, il ecrit dans les structures de
        # l'interpreteur Tcl pendant que la boucle les lit. Le plus souvent
        # rien ne se produit — la demande est simplement perdue. C'est ce qui
        # arrivait a « Quitter » : le menu repondait, l'icone disparaissait,
        # et l'application continuait de tourner.
        #
        # La file est videe par la boucle principale, seule autorisee a
        # toucher a Tk.
        self._commandes: queue.Queue = queue.Queue()
        self._arret = threading.Event()

        # Fenetre racine invisible : Tk en exige une, mais l'application n'a
        # pas de fenetre principale — le tableau de bord vit ailleurs.
        #
        # Une seule par processus, d'ou le passage de temoin : la fenetre de
        # premier lancement en a besoin AVANT que l'application existe, et en
        # creer une seconde ici ferait planter Tk (code 0x80000003, sans une
        # ligne de journal).
        self.racine = racine if racine is not None else tk.Tk()
        self.racine.withdraw()
        self.racine.title("Murmur")

        # La conscience du DPI est declaree dans `main`, avant toute fenetre.
        # Il reste a le dire a Tk : il exprime ses tailles de police en points
        # et les convertit lui-meme en pixels. Sans ce reglage, l'application
        # devient nette **et minuscule** — Windows cesse d'agrandir, et rien
        # ne prend le relais.
        self.echelle = ecran.accorder_tk(self.racine)

        # La barre de dictee est peinte par Pillow, pixel par pixel : Windows
        # ne l'agrandit plus depuis que l'application se declare consciente du
        # DPI. Elle est donc dessinee a la taille reelle qu'elle doit occuper.
        hauteur_barre = rendu.accorder(self.echelle)
        self.log.info("echelle d'affichage : %.0f %% (barre : %d px)",
                      self.echelle * 100, hauteur_barre)

        self.indicateur = (
            overlay.Indicateur(
                self.racine, conf, self.theme,
                sur_annuler=self.application.annuler_ecoute,
                sur_valider=self.application.terminer_ecoute,
                niveau=lambda: self.application.niveau_sonore)
            if conf["interface.indicateur_actif"] else None)

        self.correction = module_correction.Boite(self.racine, conf,
                                                  self.theme)

        self.icone = tray.Icone(
            conf, self.theme,
            sur_pause=self._definir_actif,
            sur_quitter=self._quitter,
            sur_ouvrir=self._ouvrir_tableau,
            sur_reglages=self._ouvrir_reglages)

        # Le tableau de bord vit dans un autre processus : quand il modifie un
        # reglage ou le dictionnaire, il nous previent par le canal, faute de
        # quoi la modification n'aurait effet qu'au prochain lancement.
        self.canal = None
        if verrou is not None and verrou.prise is not None:
            self.canal = module_canal.Serveur(verrou.prise, {
                "reglages_modifies": self._sur_reglages_modifies,
                "lexique_modifie": self._sur_lexique_modifie,
                "ouvrir": lambda args: self._ouvrir_tableau(
                    args.get("page", tableau.PAGE_PAR_DEFAUT)),
            })

        self.application.ecouteurs.etat.append(self._sur_etat)
        self.application.ecouteurs.resultat.append(self._sur_resultat)
        self.application.ecouteurs.correction.append(self._sur_correction)

    # -- reactions ---------------------------------------------------------

    def _sur_etat(self, etat: Etat) -> None:
        if self.indicateur is not None:
            self.indicateur.montrer(etat)
        self.icone.changer_etat(etat)
        if self.verbeux:
            print(f"  [{etat.value}]")

    def _sur_resultat(self, resultat: Resultat) -> None:
        # Le tableau de bord n'est plus prevenu d'une nouvelle dictee : il
        # redemande ses donnees toutes les deux secondes tant qu'il est
        # ouvert. Une requete d'une ligne coute moins qu'un canal permanent
        # dans l'autre sens.
        if not self.verbeux:
            return
        if resultat.erreur:
            print(f"  [erreur] {resultat.erreur}")
        elif resultat.rejete:
            print(f"  [ignore] {resultat.rejete}")
        elif resultat.texte:
            print(f"  « {resultat.texte} »")
            print(f"    latence {resultat.latence_ms:.0f} ms")
        if resultat.avertissement:
            print(f"    [!] {resultat.avertissement}")

    def _sur_correction(self, analyse) -> None:
        # L'analyse tourne sur son propre fil : l'affichage doit repasser par
        # la file de Tk.
        diagnostic = self.application.dernier_diagnostic
        self._demander(lambda: self.correction.montrer(
            analyse, self.application.enregistrer_correction,
            diagnostic=diagnostic))
        if self.verbeux:
            if analyse is None:
                print("  [apprentissage] aucune dictee ne correspond")
            else:
                print(f"  [apprentissage] {len(analyse.propositions)} "
                      f"proposition(s)")

    # -- commandes venues du tableau de bord -------------------------------
    #
    # Les rappels s'executent sur le fil du canal. Tout ce qui touche aux
    # fenetres ou aux raccourcis est renvoye vers le fil principal : Windows
    # lie une combinaison au fil qui l'a enregistree, et Tk n'accepte ses
    # widgets que du sien.

    def _sur_reglages_modifies(self, _arguments: dict) -> dict:
        self._demander(self._reprendre_les_reglages)
        return {"pris": True}

    def _reprendre_les_reglages(self) -> None:
        # Relue sur place : l'objet est deja detenu par l'application, le
        # theme, l'indicateur et l'icone.
        self.conf.recharger()
        self.theme.rafraichir()
        self.application.recharger_raccourcis()
        self.log.info("reglages repris du tableau de bord")

    def _sur_lexique_modifie(self, _arguments: dict) -> dict:
        self.application.recharger_lexique()
        return {"pris": True}

    def _definir_actif(self, actif: bool) -> None:
        self.application.actif = actif

    def _ouvrir_tableau(self, page: str = "dictees") -> dict:
        """Ouvre le tableau de bord, dans son processus.

        Appele depuis le fil de l'icone comme depuis celui du canal, sans
        passer par la file de Tk : plus rien ici n'est une fenetre Tk, et
        `tableau.ouvrir` ne fait qu'ecrire sur une prise puis lancer un
        processus.
        """
        return {"ouvert": tableau.ouvrir(page)}

    def _ouvrir_reglages(self) -> None:
        self._ouvrir_tableau("reglages")

    # -- file de commandes -------------------------------------------------

    #: Cadence de relecture de la file. Assez court pour qu'un clic sur
    #: « Quitter » paraisse immediat, assez long pour ne rien couter au repos.
    PAS_FILE_MS = 50

    def _demander(self, action) -> None:
        """Depose une action pour le fil principal. Sur depuis n'importe ou."""
        self._commandes.put(action)

    def _traiter_commandes(self) -> None:
        while True:
            try:
                action = self._commandes.get_nowait()
            except queue.Empty:
                break
            try:
                action()
            except Exception:
                self.log.exception("commande non traitee")
        if not self._arret.is_set():
            self.racine.after(self.PAS_FILE_MS, self._traiter_commandes)

    def _quitter(self) -> None:
        """Demande l'arret. Appele depuis le fil de l'icone."""
        self._arret.set()
        self._demander(self.racine.quit)

    # -- theme -------------------------------------------------------------

    def _suivre_theme(self) -> None:
        """Relit periodiquement le reglage d'apparence de Windows.

        Windows diffuse bien un message lors du changement, mais l'ecouter
        depuis Tk demanderait un sous-classement de fenetre en ctypes. Une
        relecture toutes les cinq secondes coute une lecture de registre et
        suffit largement pour un changement que l'utilisateur declenche a la
        main.
        """
        if self.theme.rafraichir():
            self.log.info("theme systeme change : %s", self.theme.palette.nom)
            if self.indicateur is not None:
                self.indicateur.rafraichir_theme()
            self.icone.rafraichir_theme()
        self.racine.after(5000, self._suivre_theme)

    # -- cycle de vie ------------------------------------------------------

    def demarrer(self) -> None:
        self.application.demarrer()
        self.icone.demarrer()
        if self.canal is not None:
            self.canal.demarrer()
        self.racine.after(self.PAS_FILE_MS, self._traiter_commandes)
        self.racine.after(5000, self._suivre_theme)

    def boucler(self) -> None:
        try:
            self.racine.mainloop()
        except KeyboardInterrupt:
            pass

    def arreter(self) -> None:
        self._arret.set()
        # Le tableau de bord vit dans un autre processus : il ne meurt pas
        # avec l'application. Reste ouvert, il laisse une fenetre — et un
        # « Murmur.exe » — apres qu'on a demande a quitter.
        tableau.fermer()
        if self.canal is not None:
            self.canal.arreter()
        self.icone.arreter()
        if self.indicateur is not None:
            self.indicateur.detruire()
        self.application.arreter()
        try:
            self.racine.destroy()
        except tk.TclError:
            pass


class _SortieMuette:
    """Remplace une sortie standard absente.

    Empaquetee avec `--windowed`, l'application n'a ni stdout ni stderr :
    PyInstaller les met a None. Le moindre `print` leve alors une
    AttributeError — y compris celui charge de rapporter l'erreur, qui se
    transforme ainsi en « Unhandled exception in script ».
    """

    def write(self, _texte: str) -> int:
        return 0

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def assurer_les_sorties() -> None:
    """A appeler en tout premier : rend `print` inoffensif sans console."""
    sorties.assurer()


def signaler(titre: str, message: str) -> None:
    """Porte un message a l'utilisateur, console ou non.

    Sans console, un message ecrit sur la sortie d'erreur disparaitrait
    purement et simplement, et un echec de demarrage se traduirait par « rien
    ne se passe ». On ouvre donc une boite de dialogue.
    """
    assurer_les_sorties()
    print(f"{titre} : {message}", file=sys.stderr)
    if not configuration.EMPAQUETE:
        return
    try:
        import tkinter as tk
        from tkinter import messagebox

        racine = tk.Tk()
        racine.withdraw()
        messagebox.showerror(f"Murmur — {titre}", message)
        racine.destroy()
    except Exception:
        pass  # dernier recours : on ne peut plus rien dire


def _page_demandee() -> str:
    """Page passee apres `--tableau`, si elle en vaut une."""
    rang = sys.argv.index("--tableau") + 1
    if rang < len(sys.argv) and not sys.argv[rang].startswith("-"):
        return sys.argv[rang]
    return tableau.PAGE_PAR_DEFAUT


#: Sans eux l'application demarre, mais ne dicte pas.
MODULES_VITAUX = ("sounddevice", "numpy", "webview", "pystray", "PIL")


def _verifier_les_modules() -> int:
    """Importe les modules vitaux. Code 0 si tous repondent."""
    manquants = []
    for nom in MODULES_VITAUX:
        try:
            __import__(nom)
        except Exception as exc:
            manquants.append(f"{nom} ({exc})")
    if manquants:
        print("manquant : " + ", ".join(manquants), file=sys.stderr)
        return 1
    print("modules vitaux : tous presents")
    return 0


def main() -> int:
    # En tout premier : sans console, le moindre print ferait tout echouer.
    assurer_les_sorties()

    # Le tableau de bord est lance comme un second exemplaire de ce meme
    # programme : empaquete, `sys.executable` **est** Murmur, et il n'y a pas
    # d'autre executable a viser. L'aiguillage se fait avant tout le reste,
    # notamment avant le verrou d'instance — le tableau a le sien.
    if "--verifier" in sys.argv:
        # Controle d'apres construction, invisible a l'usage. Un module
        # manquant ne se voit pas au demarrage : l'application se lance,
        # affiche son icone, charge le moteur — et tombe a la premiere
        # dictee. C'est arrive. On le demande donc a l'executable
        # lui-meme, seul juge de ce qu'il embarque vraiment.
        return _verifier_les_modules()

    if "--tableau" in sys.argv:
        # Une panne ici serait parfaitement muette : pas de console, et le
        # tableau meurt avant d'avoir ecrit sa premiere ligne de journal.
        # C'est arrive au premier essai de l'executable — le processus
        # disparaissait sans trace.
        try:
            from .tableau.lancement import main as ouvrir_tableau
            return ouvrir_tableau(_page_demandee())
        except Exception as exc:
            journal.obtenir("tableau").exception("tableau de bord impossible")
            signaler("Tableau de bord impossible",
                     f"{exc}\n\nJournal : "
                     f"{configuration.dossier_journaux() / 'murmur.log'}")
            return 1

    # Avant la moindre fenetre : declaree ensuite, elle laisserait celles qui
    # existent deja dans l'ancien referentiel, et Windows continuerait
    # d'etirer leur image.
    ecran.declarer()

    verbeux = "--console" in sys.argv

    try:
        conf = configuration.charger()
    except configuration.ErreurConfig as exc:
        signaler("Configuration invalide", str(exc))
        return 1

    verrou = systeme.InstanceUnique()
    try:
        verrou.prendre()
    except systeme.DejaLance as exc:
        signaler("Deja lance", str(exc))
        return 1

    # Le modele avant tout le reste : sans lui rien ne peut transcrire, et
    # c'est le seul moment ou Murmur touche au reseau. Le verrou est deja pris
    # — deux telechargements simultanes du meme fichier n'auraient aucun sens.
    # L'unique racine Tk du processus, creee ici parce que deux modules en
    # ont besoin l'un apres l'autre.
    racine = tk.Tk()
    racine.withdraw()

    if not premier_lancement.assurer_le_modele(conf, module_theme.Theme(conf),
                                               racine):
        verrou.liberer()
        return 1

    # L'entree de demarrage designe un chemin, et un chemin change. On la
    # remet sur l'executable courant plutot que de laisser Windows lancer une
    # copie qui n'est plus la bonne.
    corrigee = systeme.rafraichir_demarrage_auto()
    if corrigee:
        journal.obtenir("main").info("demarrage automatique remis a jour : %s",
                                     corrigee)

    murmur = Murmur(conf, verbeux=verbeux, verrou=verrou, racine=racine)
    try:
        murmur.demarrer()
    except Exception as exc:
        murmur.log.exception("demarrage impossible")
        signaler("Demarrage impossible",
                 f"{exc}\n\nJournal : "
                 f"{configuration.dossier_journaux() / 'murmur.log'}")
        murmur.arreter()
        verrou.liberer()
        return 1

    if verbeux:
        print("Murmur — dictee vocale locale")
        print(f"  maintien : {conf['raccourcis.maintien']}")
        print(f"  bascule  : {conf['raccourcis.bascule']}")
        print(f"  theme    : {murmur.theme.palette.nom}")
        print("\nL'icone est pres de l'horloge. Ctrl+C pour quitter.\n")

    try:
        murmur.boucler()
    finally:
        murmur.arreter()
        verrou.liberer()
    return 0


"""Integration a Windows : instance unique et demarrage automatique.

Deux mecanismes independants, tous deux reversibles et inspectables :

  instance unique   un verrou pris sur un port local. Le systeme le libere
                    automatiquement a la mort du processus, meme brutale —
                    contrairement a un fichier verrou, qui survit a un
                    plantage et bloque tous les lancements suivants.

  demarrage auto    une valeur dans la cle Run de l'utilisateur courant.
                    Pas de tache planifiee, pas de droits administrateur, et
                    l'utilisateur peut la retirer lui-meme.
"""

from __future__ import annotations

import os
import socket
import sys
import winreg
from pathlib import Path

from . import config as configuration, journal

_log = journal.obtenir("systeme")

#: Port du verrou. Distinct de celui du moteur : ce sont deux ressources sans
#: rapport, les confondre rendrait un conflit incomprehensible.
PORT_VERROU = 8643

#: Verrou du tableau de bord, qui vit dans son propre processus. Un port a lui,
#: parce qu'il nait et meurt independamment de l'application : la prise du
#: verrou principal ne dirait rien de sa presence a lui. Elle porte de meme les
#: commandes qu'on lui adresse — « montre-toi sur telle page ».
PORT_TABLEAU = 8644

CLE_DEMARRAGE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM_DEMARRAGE = "Murmur"


class DejaLance(Exception):
    """Une autre instance de Murmur tourne deja."""


class InstanceUnique:
    """Verrou d'instance, tenu tant que l'objet vit."""

    def __init__(self, port: int = PORT_VERROU):
        self.port = port
        self._prise: socket.socket | None = None

    def prendre(self) -> None:
        prise = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            prise.bind(("127.0.0.1", self.port))
            prise.listen(1)
        except OSError as exc:
            prise.close()
            raise DejaLance(
                "Murmur est deja lance. Regarde l'icone pres de l'horloge."
            ) from exc
        self._prise = prise

    def liberer(self) -> None:
        prise, self._prise = self._prise, None
        if prise is not None:
            prise.close()

    @property
    def detenu(self) -> bool:
        return self._prise is not None

    @property
    def prise(self):
        """La prise qui ecoute, pour que le canal la reprenne.

        Elle ecoutait depuis toujours sans jamais rien accepter : lui faire
        porter les commandes du tableau de bord evite un second port, et
        garantit que le canal existe exactement quand l'application tourne.
        """
        return self._prise

    def est_libre(self) -> bool:
        """Vrai si aucune instance de Murmur ne tourne.

        Prendre puis relacher aussitot le verrou est le moyen le plus sur de
        le savoir : chercher un processus par son nom se ferait piéger par un
        homonyme, et ne dirait rien d'une instance lancee depuis les sources.
        """
        if self.detenu:
            return True
        try:
            self.prendre()
        except DejaLance:
            return False
        self.liberer()
        return True

    def __enter__(self) -> InstanceUnique:
        self.prendre()
        return self

    def __exit__(self, *_) -> None:
        self.liberer()


# --------------------------------------------------------------------------
# Demarrage automatique
# --------------------------------------------------------------------------

def commande_de_lancement() -> str:
    """Commande a inscrire dans la cle Run.

    Deux cas, et il faut les distinguer : lance depuis les sources, on vise
    `pythonw.exe` du meme environnement — sans lui, une console noire
    s'ouvrirait a chaque demarrage de Windows. Empaquete, `sys.executable`
    **est** l'application : lui passer « -m murmur » reviendrait a lui donner
    un argument qu'elle ne comprend pas.

    Le chemin est resolu dynamiquement, jamais ecrit en dur : deplacer le
    projet et relancer l'activation suffit a corriger l'entree.
    """
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return f'"{executable}"'

    sans_console = executable.with_name("pythonw.exe")
    if sans_console.exists():
        executable = sans_console
    return f'"{executable}" -m murmur'


def demarrage_auto_actif() -> bool:
    """Vrai si l'une des deux inscriptions est en place."""
    if chemin_raccourci_demarrage().exists():
        return True
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_DEMARRAGE) as cle:
            valeur, _ = winreg.QueryValueEx(cle, NOM_DEMARRAGE)
            return bool(valeur)
    except OSError:
        return False


def activer_demarrage_auto() -> str:
    """Inscrit Murmur au demarrage, par les deux voies. Rend la commande.

    Deux voies plutot qu'une, parce que la premiere a echoue en silence : sur
    un poste, cinq entrees `Run` activees, deux lancees, sans trace nulle
    part. Un raccourci dans le dossier de demarrage emprunte un chemin
    different, se voit dans l'explorateur et se supprime a la main.

    Si les deux aboutissent, l'instance unique empeche le second lancement.
    """
    commande = commande_de_lancement()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_DEMARRAGE, 0,
                        winreg.KEY_SET_VALUE) as cle:
        winreg.SetValueEx(cle, NOM_DEMARRAGE, 0, winreg.REG_SZ, commande)

    try:
        poser_raccourci_demarrage()
    except OSError:
        # La cle suffit a rendre le service attendu : on ne fait pas echouer
        # l'activation entiere pour la ceinture quand les bretelles tiennent.
        _log.warning("raccourci de demarrage impossible", exc_info=True)
    return commande


def poser_raccourci_demarrage() -> Path | None:
    """Depose le raccourci dans le dossier de demarrage de l'utilisateur.

    Rien a faire quand Murmur tourne depuis les sources : un raccourci vers
    `pythonw.exe` avec ses arguments n'a pas de sens ici, et la cle `Run` s'en
    charge.
    """
    if not getattr(sys, "frozen", False):
        return None
    return creer_raccourci(Path(sys.executable),
                           lien=chemin_raccourci_demarrage())


def desactiver_demarrage_auto() -> None:
    """Retire les DEUX inscriptions : en laisser une reviendrait a ne rien
    desactiver du tout."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_DEMARRAGE, 0,
                            winreg.KEY_SET_VALUE) as cle:
            winreg.DeleteValue(cle, NOM_DEMARRAGE)
    except FileNotFoundError:
        pass  # deja absent : le resultat voulu est atteint

    lien = chemin_raccourci_demarrage()
    if lien.exists():
        lien.unlink()


def dossier_demarrage() -> Path:
    """Le dossier « Demarrage » de l'utilisateur courant.

    POURQUOI PAS SEULEMENT LA CLE `Run`

    La cle marche — jusqu'a ce qu'elle ne marche plus, sans rien dire. Releve
    sur un poste : cinq entrees activees, deux lancees. Murmur, valide et non
    desactive, n'a pas ete execute, et aucun journal, aucun evenement systeme
    n'en garde trace.

    Un raccourci dans le dossier de demarrage a trois avantages sur elle : il
    se voit dans l'explorateur, se supprime a la main, et emprunte un chemin
    different de celui qui vient d'echouer. Les deux mecanismes coexistent —
    l'instance unique empeche que Murmur se lance deux fois.
    """
    appdata = os.getenv("APPDATA")
    base = (Path(appdata) if appdata else Path.home() / "AppData" / "Roaming")
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def chemin_raccourci_demarrage() -> Path:
    return dossier_demarrage() / f"{NOM_DEMARRAGE}.lnk"


def commande_inscrite() -> str | None:
    """Ce que la cle Run contient aujourd'hui, ou rien."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_DEMARRAGE) as cle:
            valeur, _ = winreg.QueryValueEx(cle, NOM_DEMARRAGE)
            return valeur
    except OSError:
        return None


def rafraichir_demarrage_auto() -> str | None:
    """Remet l'entree de demarrage sur l'executable courant si elle a bouge.

    Une entree de demarrage vieillit mal : elle designe un chemin, et le
    chemin change. Deplacer le dossier de l'application, passer des sources a
    la version empaquetee, reinstaller ailleurs — a chaque fois Windows
    continue de lancer ce qui n'existe plus, ou pire, une ancienne copie.

    C'est arrive ici : la cle designait `pythonw.exe -m murmur` dans
    l'environnement de developpement, alors que l'application installee etait
    l'executable. Rien ne le signalait — les deux se lancent.

    On ne touche a rien tant que le demarrage automatique n'est pas demande :
    ce n'est pas a l'application de decider qu'elle doit s'inscrire.

    Renvoie la nouvelle commande si elle a ete corrigee, sinon `None`.
    """
    actuelle = commande_inscrite()
    lien = chemin_raccourci_demarrage()
    if not actuelle and not lien.exists():
        return None

    attendue = commande_de_lancement()
    if actuelle == attendue and lien.exists():
        return None

    activer_demarrage_auto()
    return attendue


def definir_demarrage_auto(actif: bool) -> None:
    if actif:
        activer_demarrage_auto()
    else:
        desactiver_demarrage_auto()


def ouvrir_dossier_donnees() -> None:
    """Ouvre l'explorateur sur les donnees utilisateur (config, journaux)."""
    import subprocess
    subprocess.Popen(["explorer", str(configuration.dossier_donnees())])


# --------------------------------------------------------------------------
# Raccourci du menu Demarrer
# --------------------------------------------------------------------------

NOM_RACCOURCI = "Murmur"


def dossier_menu_demarrer() -> Path:
    """Dossier des programmes de l'utilisateur courant.

    Celui de l'utilisateur, pas celui de la machine : ecrire dans
    `%ProgramData%` demanderait des droits administrateur pour un raccourci
    qui ne concerne qu'une personne.
    """
    appdata = os.getenv("APPDATA")
    base = (Path(appdata) if appdata
            else Path.home() / "AppData" / "Roaming")
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def chemin_raccourci() -> Path:
    return dossier_menu_demarrer() / f"{NOM_RACCOURCI}.lnk"


def creer_raccourci(cible: Path, description: str = "Dictee vocale locale",
                    icone: Path | None = None, lien: Path | None = None) -> Path:
    """Cree le raccourci du menu Demarrer et renvoie son chemin.

    Un fichier `.lnk` est un format binaire COM : on passe par le
    `WScript.Shell` de Windows plutot que d'en fabriquer un a la main.

    Depuis le menu Demarrer, l'utilisateur peut ensuite epingler l'entree ou
    il veut — Windows 11 ne permet plus d'epingler a la barre des taches par
    programme, c'est une action volontaire de sa part.
    """
    import subprocess

    cible = cible.resolve()
    if not cible.exists():
        raise FileNotFoundError(f"cible introuvable : {cible}")

    lien = lien or chemin_raccourci()
    lien.parent.mkdir(parents=True, exist_ok=True)

    # L'executable porte deja son icone : s'y referer evite un fichier .ico
    # separe, qui pourrait etre supprime et laisser un raccourci sans image.
    source_icone = str((icone or cible).resolve())

    script = "\n".join([
        "$s = New-Object -ComObject WScript.Shell",
        f"$l = $s.CreateShortcut('{lien}')",
        f"$l.TargetPath = '{cible}'",
        f"$l.WorkingDirectory = '{cible.parent}'",
        f"$l.IconLocation = '{source_icone},0'",
        f"$l.Description = '{description}'",
        "$l.Save()",
    ])

    resultat = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True)
    if resultat.returncode != 0 or not lien.exists():
        raise OSError(
            f"creation du raccourci impossible : "
            f"{resultat.stderr.strip() or 'echec silencieux'}")
    return lien


def raccourci_existe() -> bool:
    return chemin_raccourci().exists()


def supprimer_raccourci() -> bool:
    lien = chemin_raccourci()
    if not lien.exists():
        return False
    lien.unlink()
    return True

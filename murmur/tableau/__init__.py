"""Tableau de bord de Murmur, rendu par un moteur web.

Il vit dans son propre processus, lance a la demande et arrete avec sa
fenetre. Deux raisons a cette separation :

  - Tk, qui porte la barre de dictee et l'icone, veut le fil principal ;
    pywebview aussi. Les faire cohabiter demanderait de reléguer l'un des
    deux sur un fil secondaire, ce qu'aucune des deux bibliotheques ne
    garantit.
  - Le tableau de bord ouvert pese quinze processus et 374 Mo de memoire
    privee mesures — plus que tout le reste de l'application reunie. Les
    laisser mourir avec la fenetre ramene Murmur au repos a son empreinte
    d'origine.

Le tableau lit la base directement — SQLite accepte plusieurs lecteurs — et
previent l'application par le canal quand il modifie quelque chose.

    python -m murmur.tableau [page]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .. import canal, journal, systeme

_log = journal.obtenir("tableau")

#: Pages que la barre laterale sait afficher. Le nom est celui que la page
#: emploie, pas son libelle : celui-ci depend de la langue.
PAGES = ("dictees", "dictionnaire", "statistiques", "reglages")

#: Page ouverte par defaut.
PAGE_PAR_DEFAUT = "statistiques"

#: Sans fenetre visible : le processus du tableau de bord ne doit pas faire
#: clignoter une console au lancement.
_SANS_CONSOLE = 0x08000000     # CREATE_NO_WINDOW

#: Le tableau lance par cette application, tant qu'il vit.
#:
#: On le retient pour n'avoir pas a demander au reseau ce qu'on sait deja.
#: Frapper a une porte fermee coute un quart de seconde ici — les paquets
#: sont avales plutot que refuses — et c'est un quart de seconde ajoute a
#: chaque ouverture, pour apprendre une absence dont on est certain.
_processus = None


def tourne() -> bool:
    """Un tableau lance par nous est-il encore en vie ?

    `poll` ne bloque pas : il lit le code de sortie s'il y en a un.
    """
    return _processus is not None and _processus.poll() is None


def ouvrir(page: str = PAGE_PAR_DEFAUT) -> bool:
    """Ouvre le tableau de bord, ou ramene celui qui tourne deja.

    Deux appels de suite ne doivent pas donner deux fenetres. On frappe donc
    d'abord a la porte du tableau : s'il repond, il passe au premier plan sur
    la page demandee ; sinon, on lance le processus.

    Le lancement n'attend pas : WebView2 met une seconde a ouvrir sa fenetre,
    et l'icone pres de l'horloge ne doit pas rester figee pendant ce temps.
    """
    global _processus
    page = page if page in PAGES else PAGE_PAR_DEFAUT

    # On ne frappe que si l'on a lieu de croire que quelqu'un est la. Sinon on
    # lance directement : le nouveau venu prendra le verrou, ou le trouvera
    # pris et transmettra lui-meme la demande.
    if tourne():
        reponse = canal.envoyer("montrer", {"page": page},
                                port=systeme.PORT_TABLEAU)
        if reponse.get("ok"):
            return True

    try:
        _processus = subprocess.Popen(
            commande(page), creationflags=_SANS_CONSOLE,
            cwd=str(Path(__file__).resolve().parents[2]))
    except OSError:
        _log.exception("tableau de bord non lance")
        return False
    return True


def fermer() -> bool:
    """Ferme le tableau de bord s'il est ouvert. Vrai s'il a repondu.

    Il vit dans son propre processus et ne meurt donc pas avec l'application.
    Laisse ouvert, il garde une fenetre a l'ecran et un « Murmur.exe » dans la
    liste des taches apres qu'on a demande a quitter — ce qui se lit, a juste
    titre, comme un refus de se fermer.
    """
    global _processus
    if _processus is not None and not tourne():
        _processus = None
        return False
    ferme = bool(canal.envoyer("fermer", {},
                               port=systeme.PORT_TABLEAU).get("ok"))
    if ferme:
        _processus = None
    return ferme


def commande(page: str = PAGE_PAR_DEFAUT) -> list[str]:
    """Ligne de commande qui ouvre le tableau de bord.

    Empaquete, `sys.executable` **est** Murmur : on lui passe l'indicateur que
    son point d'entree reconnait. Depuis les sources, on vise `pythonw.exe` du
    meme environnement — `python.exe` ferait clignoter une console noire.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--tableau", page]

    executable = Path(sys.executable)
    sans_console = executable.with_name("pythonw.exe")
    if sans_console.exists():
        executable = sans_console
    return [str(executable), "-m", "murmur", "--tableau", page]

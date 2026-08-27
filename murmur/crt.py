"""Les bibliotheques Visual C++ que le moteur reclame, fournies avec lui.

Le moteur whisper est compile avec Visual C++. Ses binaires importent des
bibliotheques que Visual Studio installe sur la machine qui compile et que
Windows ne fournit pas : sur un poste ordinaire, elles manquent — et rien, en
developpement, ne le laisse deviner.

CE QUE COUTE UNE LISTE ECRITE A LA MAIN

Le premier essai sur machine vierge a bute sur `MSVCP140.dll`. Corrige, le
deuxieme a bute sur `VCOMP140.DLL`, la bibliotheque OpenMP — que la premiere
liste ne contenait pas, parce qu'elle avait ete etablie en cherchant des noms
plausibles. Une liste devinee se corrige a raison d'un demarrage par oubli.

D'ou la regle appliquee ici, qui ne devine rien :

    est a fournir toute bibliotheque que le moteur importe ET que Visual
    Studio range dans son dossier « redistribuable »

Ce dossier est precisement la liste de ce que Microsoft autorise a distribuer
avec une application — c'est-a-dire de ce qu'il ne garantit pas present. La
correspondance est exacte, et elle se met a jour toute seule : recompiler le
moteur avec d'autres options amenera les bonnes bibliotheques sans que
personne ait a y penser.

Poser les fichiers a cote de l'executable plutot qu'exiger l'installation du
redistribuable Visual C++ evite a l'utilisateur un telechargement et une
demande de droits administrateur. Les termes de licence de Visual Studio
autorisent explicitement cette distribution.

Ce module sert a la construction. L'application, elle, ne fait que constater.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import pe

#: Ou Visual Studio range ce qu'il autorise a redistribuer. Les dossiers de
#: programmes sont demandes a Windows plutot qu'ecrits en dur : ils ne sont pas
#: toujours sur C:, et pas toujours en anglais.
DOSSIERS_PROGRAMMES = ("ProgramFiles(x86)", "ProgramFiles")


def racines_vs() -> tuple[Path, ...]:
    """Les installations de Visual Studio possibles sur cette machine."""
    return tuple(Path(os.environ[cle]) / "Microsoft Visual Studio"
                 for cle in DOSSIERS_PROGRAMMES if os.environ.get(cle))

#: Les dossiers a ecarter : les versions de deboguage ne sont PAS
#: redistribuables, et `onecore` vise un autre Windows que le notre.
ECARTES = ("debug_nonredist", "onecore")


def catalogue() -> dict[str, Path]:
    """Toutes les bibliotheques x64 redistribuables de cette machine.

    Du plus recent au plus ancien : le dossier porte le numero de version, et
    l'ordre alphabetique inverse suffit. La premiere trouvee l'emporte.
    """
    trouvees: dict[str, Path] = {}
    for racine in racines_vs():
        if not racine.is_dir():
            continue
        dossiers = sorted(racine.glob("*/*/VC/Redist/MSVC/*/x64/Microsoft.VC*"),
                          reverse=True)
        for dossier in dossiers:
            if any(part in ECARTES for part in dossier.parts):
                continue
            for fichier in dossier.glob("*.dll"):
                trouvees.setdefault(fichier.name.lower(), fichier)
    return trouvees


def reclamees(dossier: Path) -> set[str]:
    """Bibliotheques importees par les binaires de ce dossier, en minuscules.

    Les fichiers deja poses par nous sont inspectes eux aussi : une
    bibliotheque redistribuable peut en reclamer une autre, et ne pas suivre
    cette chaine ramenerait le probleme un cran plus loin.
    """
    noms: set[str] = set()
    for fichier in list(dossier.glob("*.exe")) + list(dossier.glob("*.dll")):
        noms.update(nom.lower() for nom in pe.imports(fichier))
    return noms


def necessaires(dossier: Path) -> list[str]:
    """Ce que ce dossier doit contenir pour tourner ailleurs qu'ici.

    Demande le catalogue de la machine : ne repond donc que sur un poste
    equipe de Visual Studio, c'est-a-dire au moment de construire.
    """
    connues = catalogue()
    return sorted(nom for nom in reclamees(dossier) if nom in connues)


def manquants(dossier: Path, attendus: tuple[str, ...] | None = None
              ) -> list[str]:
    """Ceux des fichiers attendus qui ne sont pas dans ce dossier.

    `attendus` permet de poser la question sans catalogue — c'est ainsi que
    l'application interroge un dossier livre, sur une machine qui n'a jamais
    vu Visual Studio.
    """
    liste = attendus if attendus is not None else tuple(necessaires(dossier))
    return [nom for nom in liste if not (dossier / nom).exists()]


def fournir(dossier: Path) -> list[str]:
    """Copie ce qui manque a cote du moteur. Rend la liste des ajouts.

    Repete l'operation tant qu'elle amene du nouveau : un fichier tout juste
    pose peut en reclamer un autre, et l'inspection ne pouvait pas le savoir
    avant qu'il soit la.
    """
    connues = catalogue()
    poses: list[str] = []
    while True:
        attendus = necessaires(dossier)
        a_poser = [nom for nom in attendus
                   if not (dossier / nom).exists()]
        if not a_poser:
            ecrire_manifeste(dossier, attendus)
            return sorted(poses)
        if not connues:
            raise FileNotFoundError(
                "bibliotheques Visual C++ introuvables sur cette machine.\n"
                "    manquantes dans le moteur : " + ", ".join(a_poser) + "\n"
                "    Elles sont fournies avec les outils de compilation "
                "Visual Studio, qui ont deja servi a compiler le moteur.")
        for nom in a_poser:
            shutil.copy2(connues[nom], dossier / nom)
            poses.append(nom)


# --------------------------------------------------------------------------
# Ce que l'application peut verifier, elle, sans Visual Studio
# --------------------------------------------------------------------------

#: Depose a cote du moteur au moment de la construction. Sans lui, une machine
#: sans Visual Studio n'a aucun moyen de savoir ce qui devrait etre la : le
#: catalogue qui donne la reponse n'existe que sur un poste de developpement.
MANIFESTE = "bibliotheques.txt"


def ecrire_manifeste(dossier: Path, noms: list[str]) -> None:
    entete = ("# Bibliotheques Visual C++ livrees avec le moteur.\n"
              "# Ecrit par construire.py — ne pas modifier a la main.\n")
    (dossier / MANIFESTE).write_text(
        entete + "\n".join(noms) + "\n", encoding="utf-8")


def lire_manifeste(dossier: Path) -> tuple[str, ...]:
    """Ce que la construction a declare livrer. Vide si rien n'est declare."""
    fichier = dossier / MANIFESTE
    if not fichier.exists():
        return ()
    return tuple(ligne.strip()
                 for ligne in fichier.read_text(encoding="utf-8").splitlines()
                 if ligne.strip() and not ligne.startswith("#"))

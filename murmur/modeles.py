"""Le modele de transcription : lequel, ou, et comment l'obtenir.

POURQUOI IL N'EST PAS DANS L'ARCHIVE

Le modele pese 574 Mo, l'application 138. Le livrer avec ferait une archive
que personne ne telecharge pour essayer — et la moitie de ceux qui la
telechargent n'en ont pas besoin : sur une machine sans carte graphique
exploitable, ce modele-la demande neuf secondes par phrase et c'est un autre
qu'il faut.

Il est donc pris au premier lancement, une fois, quand on sait sur quelle
machine on est tombe. Ensuite plus rien ne sort ni n'entre : la promesse
« hors ligne » porte sur l'usage, pas sur l'installation.

LEQUEL

Mesure sur une phrase de huit secondes, meme fichier, meme conditions :

    large-v3-turbo   carte graphique      250 ms    574 Mo
    large-v3-turbo   processeur         9 400 ms    574 Mo
    small            processeur         2 050 ms    190 Mo
    base             processeur           650 ms     60 Mo

`base` a ete ecarte malgre sa vitesse : il n'entend pas, il invente. Sur la
meme phrase il a rendu « le batiment cloude flare » et « le pogui market » la
ou `small` rendait « le bot cloude flare » et « Playwright ». Les fautes de
`small` portent sur le vocabulaire technique — precisement ce que le
dictionnaire de Murmur corrige.

OU

Dans les donnees de l'utilisateur, et non a cote de l'executable : une mise a
jour de l'application ne doit pas jeter 574 Mo, et le dossier du programme
n'est pas toujours accessible en ecriture. Un modele pose a la main a cote du
moteur reste prioritaire — c'est ainsi que fonctionne le poste de
developpement.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import config as configuration, journal

_log = journal.obtenir("modeles")

#: D'ou viennent les modeles. Le depot officiel de whisper.cpp.
DEPOT = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"


@dataclass(frozen=True)
class Modele:
    """Un modele de transcription, et de quoi verifier qu'il est intact."""

    fichier: str
    octets: int
    empreinte: str
    #: Cle de traduction du descriptif montre a l'utilisateur. Une cle et
    #: non un texte : la phrase qui l'accueille est traduite, lui aussi
    #: doit l'etre.
    resume: str

    @property
    def url(self) -> str:
        return DEPOT + self.fichier

    @property
    def megaoctets(self) -> int:
        return round(self.octets / 1_000_000)


#: Pour une machine avec carte graphique Vulkan exploitable.
AVEC_CARTE = Modele(
    fichier="ggml-large-v3-turbo-q5_0.bin",
    octets=574_041_195,
    empreinte="394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2",
    resume="modele.avec_carte")

#: Pour une machine sans. Le grand modele y demanderait neuf secondes.
SANS_CARTE = Modele(
    fichier="ggml-small-q5_1.bin",
    octets=190_085_487,
    empreinte="ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb",
    resume="modele.sans_carte")


def choisir(a_une_carte: bool) -> Modele:
    """Le modele qui convient a cette machine."""
    return AVEC_CARTE if a_une_carte else SANS_CARTE


# --------------------------------------------------------------------------
# Ou le chercher
# --------------------------------------------------------------------------

def dossier() -> Path:
    """Ou sont ranges les modeles telecharges.

    Dans les donnees de l'utilisateur : une mise a jour de l'application ne
    doit pas emporter 574 Mo, et le dossier du programme n'est pas toujours
    accessible en ecriture.
    """
    chemin = configuration.dossier_donnees() / "modeles"
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def emplacement(fichier: str) -> Path | None:
    """Ou se trouve ce modele, s'il est deja la.

    A cote du moteur d'abord : c'est la que le poste de developpement garde le
    sien, et un modele pose a la main doit primer sur un telechargement.
    """
    for candidat in (configuration.MOTEUR / fichier, dossier() / fichier):
        if candidat.exists():
            return candidat
    return None


def empreinte_de(chemin: Path,
                 progression: Callable[[int, int], None] | None = None) -> str:
    """Empreinte SHA-256 du fichier, lue par blocs d'un megaoctet."""
    total = chemin.stat().st_size
    lus = 0
    condensat = hashlib.sha256()
    with chemin.open("rb") as fichier:
        for bloc in iter(lambda: fichier.read(1 << 20), b""):
            condensat.update(bloc)
            lus += len(bloc)
            if progression is not None:
                progression(lus, total)
    return condensat.hexdigest()


def verifier(chemin: Path, modele: Modele,
             progression: Callable[[int, int], None] | None = None) -> bool:
    """Le fichier est-il bien celui qu'on attend ?

    La taille d'abord : elle ecarte un telechargement tronque en une lecture
    de rien du tout, ce qui est le cas de loin le plus frequent.
    """
    if not chemin.exists() or chemin.stat().st_size != modele.octets:
        return False
    return empreinte_de(chemin, progression) == modele.empreinte


# --------------------------------------------------------------------------
# Le telechargement
# --------------------------------------------------------------------------

class ErreurTelechargement(Exception):
    """Le modele n'a pas pu etre obtenu."""


#: Taille des blocs lus sur le reseau. Assez gros pour ne pas rappeler la
#: progression a chaque paquet, assez petit pour que l'annulation reponde.
BLOC = 1 << 18

#: Suffixe du fichier en cours. Le modele definitif n'apparait qu'une fois
#: verifie : une application qui trouve `ggml-...bin` doit pouvoir s'y fier
#: sans le relire en entier a chaque demarrage.
EN_COURS = ".partiel"


def telecharger(modele: Modele,
                progression: Callable[[int, int], None] | None = None,
                arret: Callable[[], bool] | None = None) -> Path:
    """Obtient le modele, en reprenant un telechargement interrompu.

    574 Mo sur une connexion ordinaire, c'est plusieurs minutes : une coupure
    en cours de route est un evenement normal, pas un incident. Le fichier
    partiel est donc conserve et l'octet de reprise demande au serveur.

    `arret` permet a l'appelant d'interrompre — l'utilisateur ferme la
    fenetre. Le fichier partiel survit, et le telechargement suivant reprendra
    la ou celui-ci s'est arrete.
    """
    import requests

    cible = dossier() / modele.fichier
    if verifier(cible, modele):
        return cible

    partiel = cible.with_suffix(cible.suffix + EN_COURS)
    deja = partiel.stat().st_size if partiel.exists() else 0
    if deja > modele.octets:
        # Un reste d'une version precedente : on repart de zero plutot que de
        # coller des octets a la suite d'un fichier deja trop long.
        partiel.unlink()
        deja = 0

    entetes = {"Range": f"bytes={deja}-"} if deja else {}
    try:
        reponse = requests.get(modele.url, headers=entetes, stream=True,
                               timeout=30)
        reponse.raise_for_status()
    except requests.RequestException as exc:
        raise ErreurTelechargement(
            f"telechargement impossible : {exc}") from exc

    # Un serveur qui ignore la reprise renvoie 200 et le fichier entier : on
    # recommence alors depuis le debut, sinon les octets se chevaucheraient.
    if deja and reponse.status_code != 206:
        deja = 0

    recus = deja
    try:
        with partiel.open("ab" if deja else "wb") as sortie:
            for bloc in reponse.iter_content(BLOC):
                if arret is not None and arret():
                    raise ErreurTelechargement("telechargement interrompu")
                sortie.write(bloc)
                recus += len(bloc)
                if progression is not None:
                    progression(recus, modele.octets)
    except requests.RequestException as exc:
        raise ErreurTelechargement(
            f"telechargement interrompu : {exc}") from exc
    finally:
        reponse.close()

    if not verifier(partiel, modele, progression):
        # On garde le fichier : sa taille dira au prochain essai s'il est
        # simplement incomplet. Une empreinte fausse a taille juste, elle,
        # est une corruption — le suivant la detectera aussi.
        raise ErreurTelechargement(
            "le fichier telecharge ne correspond pas a ce qui etait attendu")

    partiel.replace(cible)
    _log.info("modele %s obtenu (%d Mo)", modele.fichier, modele.megaoctets)
    return cible

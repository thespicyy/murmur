"""Choix de la carte graphique, sur une machine qu'on ne connait pas.

POURQUOI CE MODULE EXISTE

Le moteur est compile pour Vulkan, une interface commune a tous les fabricants :
le meme binaire tourne sur une carte AMD, Nvidia ou Intel. Sa seule dependance
exterieure est `vulkan-1.dll`, le chargeur que tout pilote graphique installe.
Rien n'y designe une carte en particulier — les programmes sont compiles a
l'execution pour le materiel present. Ce n'est donc pas le moteur qui pose
probleme d'une machine a l'autre.

C'est le CHOIX du peripherique. La configuration portait `device_vulkan: 0`,
ecrit pour ce poste-ci. Or l'ordre d'enumeration n'est pas stable — releve sur
la meme machine, le meme binaire, a quelques minutes d'intervalle :

    0 = AMD Radeon RX 9070 XT      0 = AMD Radeon(TM) Graphics
    1 = AMD Radeon(TM) Graphics    1 = AMD Radeon RX 9070 XT

Prendre le numero zero, c'est donc tirer au sort entre la carte dediee et le
circuit integre au processeur. Sur une machine a une seule carte cela ne se
voit pas ; sur une machine mixte — un portable, une tour avec un processeur
graphique — cela donne une dictee trois a dix fois plus lente, sans rien dire.

CE QU'ON FAIT A LA PLACE

Le moteur sait enumerer les peripheriques : lance avec `--help`, il les liste
et rend la main en deux cent trente millisecondes. On lui demande, on choisit,
on retient le NOM de la carte retenue plutot que son numero — un numero ne veut
rien dire d'une session a l'autre, un nom si.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import journal

_log = journal.obtenir("vulkan")

#: Le moteur ecrit une ligne par peripherique, sur la sortie d'erreur :
#:
#:   ggml_vulkan: 0 = AMD Radeon RX 9070 XT (AMD proprietary driver) | uma: 0 |
#:   fp16: 1 | ... | matrix cores: KHR_coopmat
LIGNE = re.compile(
    r"ggml_vulkan:\s*(?P<numero>\d+)\s*=\s*(?P<nom>.+?)\s*\|"
    r"(?P<details>.*)$")

#: Au-dela, l'enumeration a echoue d'une facon ou d'une autre. Elle prend
#: normalement un quart de seconde.
DELAI_S = 20.0


@dataclass(frozen=True)
class Peripherique:
    """Une carte graphique vue par Vulkan."""

    numero: int
    nom: str
    #: Memoire unifiee : la carte partage la memoire du processeur. C'est la
    #: signature d'un circuit graphique integre, toujours le plus lent des
    #: deux quand une carte dediee est presente.
    integre: bool
    #: Unites de calcul matriciel dediees. Leur presence distingue les cartes
    #: recentes, nettement plus rapides sur ce travail.
    matriciel: bool

    def __str__(self) -> str:
        genre = "integre" if self.integre else "dediee"
        return f"{self.numero} = {self.nom} ({genre})"


def enumerer(serveur: Path) -> list[Peripherique]:
    """Demande au moteur la liste des peripheriques Vulkan.

    Rend une liste vide si le moteur ne repond pas, ou si aucun peripherique
    n'est visible : l'appelant retombera alors sur le processeur.
    """
    try:
        resultat = subprocess.run(
            [str(serveur), "--help"], capture_output=True, text=True,
            errors="replace", timeout=DELAI_S, cwd=str(serveur.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as exc:
        _log.warning("enumeration Vulkan impossible : %s", exc)
        return []

    return analyser(resultat.stderr + resultat.stdout)


def analyser(texte: str) -> list[Peripherique]:
    """Lit les lignes d'enumeration du moteur."""
    trouves: list[Peripherique] = []
    for ligne in texte.splitlines():
        capture = LIGNE.search(ligne)
        if capture is None:
            continue
        details = capture["details"]
        trouves.append(Peripherique(
            numero=int(capture["numero"]),
            nom=capture["nom"].strip(),
            integre="uma: 1" in details,
            matriciel=("matrix cores:" in details
                       and "matrix cores: none" not in details)))
    return trouves


def choisir(peripheriques: list[Peripherique]) -> Peripherique | None:
    """Le meilleur peripherique de la liste, ou rien si elle est vide.

    Deux criteres, dans cet ordre : une carte dediee plutot qu'un circuit
    integre, puis le calcul matriciel. On ne cherche pas plus loin — departager
    deux cartes dediees demanderait de mesurer, et l'ecart entre elles est sans
    commune mesure avec l'ecart entre une carte et un circuit integre.
    """
    if not peripheriques:
        return None
    return min(peripheriques,
               key=lambda p: (p.integre, not p.matriciel, p.numero))


def retrouver(peripheriques: list[Peripherique], nom: str
              ) -> Peripherique | None:
    """Le peripherique portant ce nom, si l'enumeration le montre encore.

    C'est le nom qui est retenu d'une session a l'autre, et non le numero :
    l'ordre change d'un demarrage a l'autre. Une carte changee ou un pilote
    remplace fait simplement echouer la recherche, et le choix est refait.
    """
    for peripherique in peripheriques:
        if peripherique.nom == nom:
            return peripherique
    return None

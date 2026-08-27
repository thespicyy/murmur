"""Lecture de la table des imports d'un binaire Windows.

Une centaine de lignes pour eviter une dependance de plus, et surtout pour
obtenir la reponse exacte : la liste que le chargeur de Windows consultera au
demarrage, et non les noms qu'on peut deviner en cherchant des chaines dans le
fichier.

Ce n'est pas une curiosite. Sur la machine qui compile, tout est installe ; une
bibliotheque fournie par Visual Studio y est indiscernable d'une bibliotheque
fournie par Windows. La table des imports, elle, ne fait pas la difference non
plus — mais croisee avec ce que Visual Studio se dit autorise a redistribuer,
elle la donne.
"""

from __future__ import annotations

import struct
from pathlib import Path

#: Signature d'un entete optionnel 64 bits (PE32+).
PE32_PLUS = 0x20B


def imports(chemin: Path) -> list[str]:
    """Noms des bibliotheques importees par ce fichier PE.

    Rend une liste vide si le fichier n'importe rien, ou n'est pas un PE
    lisible : ce module sert a decrire, pas a valider.
    """
    try:
        donnees = chemin.read_bytes()
        return _lire(donnees)
    except (OSError, struct.error, ValueError, IndexError):
        return []


def _lire(donnees: bytes) -> list[str]:
    debut_pe = struct.unpack_from("<I", donnees, 0x3C)[0]
    if donnees[debut_pe:debut_pe + 4] != b"PE\0\0":
        return []

    sections = struct.unpack_from("<H", donnees, debut_pe + 6)[0]
    taille_optionnel = struct.unpack_from("<H", donnees, debut_pe + 20)[0]
    magie = struct.unpack_from("<H", donnees, debut_pe + 24)[0]

    # Les repertoires de donnees suivent l'entete optionnel, dont la taille
    # depend de l'architecture. Le repertoire des imports est le deuxieme.
    repertoires = debut_pe + 24 + (112 if magie == PE32_PLUS else 96)
    rva_import = struct.unpack_from("<I", donnees, repertoires + 8)[0]
    if not rva_import:
        return []

    # Les adresses de la table sont virtuelles : elles designent la place du
    # module une fois charge en memoire, pas sa place dans le fichier. Les
    # sections donnent la correspondance.
    base_sections = debut_pe + 24 + taille_optionnel
    plan = []
    for rang in range(sections):
        entree = base_sections + rang * 40
        plan.append((
            struct.unpack_from("<I", donnees, entree + 12)[0],   # rva
            struct.unpack_from("<I", donnees, entree + 8)[0],    # taille
            struct.unpack_from("<I", donnees, entree + 20)[0]))  # position

    def position(rva: int) -> int | None:
        for depart, taille, brute in plan:
            if depart <= rva < depart + max(taille, 1):
                return brute + (rva - depart)
        return None

    noms: list[str] = []
    curseur = position(rva_import)
    if curseur is None:
        return []

    # Le tableau se termine par une entree entierement nulle.
    while True:
        rva_nom = struct.unpack_from("<I", donnees, curseur + 12)[0]
        if rva_nom == 0:
            break
        debut = position(rva_nom)
        if debut is None:
            break
        fin = donnees.index(b"\0", debut)
        noms.append(donnees[debut:fin].decode("ascii", "replace"))
        curseur += 20
    return noms

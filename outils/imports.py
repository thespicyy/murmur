r"""Que reclame le moteur, et qu'est-ce qui manquerait ailleurs qu'ici ?

    .venv\Scripts\python.exe outils\imports.py

Croise deux choses :

  - la table des imports de chaque binaire du moteur, c'est-a-dire la liste
    exacte que le chargeur de Windows consultera au demarrage ;
  - le catalogue de ce que Visual Studio se dit autorise a redistribuer,
    c'est-a-dire de ce que Windows ne garantit pas.

L'intersection est ce qu'il faut livrer. Le reste se repartit en deux : ce que
Windows fournit toujours (`kernel32`, l'API CRT universelle), et le pilote
graphique (`vulkan-1.dll`), qu'on ne peut pas distribuer et dont l'absence
doit seulement faire retomber le moteur sur le processeur.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: La racine du projet, un cran au-dessus de `outils/`.
RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from murmur import crt, pe  # noqa: E402

MOTEUR = RACINE / "engine"

#: Fournie par le pilote graphique. Ni distribuable, ni indispensable : sans
#: elle, le moteur doit se rabattre sur le processeur.
PILOTE = "vulkan-1.dll"


def main() -> int:
    if not MOTEUR.is_dir():
        sys.exit(f"dossier du moteur introuvable : {MOTEUR}")

    connues = catalogue = crt.catalogue()
    if not catalogue:
        print("  (aucun redistribuable Visual Studio sur cette machine :")
        print("   impossible de dire ce qui est a fournir)")

    binaires = sorted(MOTEUR.glob("*.exe")) + sorted(MOTEUR.glob("*.dll"))
    for fichier in binaires:
        reclame = [nom for nom in pe.imports(fichier)
                   if nom.lower() in connues or nom.lower() == PILOTE]
        print(f"  {fichier.name:<26} {', '.join(sorted(reclame)) or '-'}")

    print()
    print("  a livrer avec l'application :")
    for nom in crt.necessaires(MOTEUR):
        etat = "present" if (MOTEUR / nom).exists() else "ABSENT"
        print(f"    {nom:<22} {etat}")

    declarees = crt.lire_manifeste(MOTEUR)
    print()
    print(f"  manifeste  : {', '.join(declarees) if declarees else 'absent'}")
    print(f"  {PILOTE:<10} : fourni par le pilote graphique, jamais par nous")
    return 0


if __name__ == "__main__":
    sys.exit(main())

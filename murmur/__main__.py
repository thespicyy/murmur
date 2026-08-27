"""Amorce : `python -m murmur`.

Tout le programme est dans `lancement.py` — voir sa docstring pour la raison,
qui tient a l'empaquetage et non au style.

    python -m murmur              lance l'application
    python -m murmur --console    ajoute les traces dans une console
    python -m murmur --tableau    ouvre le tableau de bord (usage interne)
"""

import sys

from .lancement import main

if __name__ == "__main__":
    sys.exit(main())

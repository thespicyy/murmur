"""Amorce : `python -m murmur.tableau [page]`.

Le corps est dans `lancement.py` — voir sa docstring.
"""

import sys

from . import PAGE_PAR_DEFAUT
from .lancement import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else PAGE_PAR_DEFAUT))

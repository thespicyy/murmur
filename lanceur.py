#!/usr/bin/env python3
"""Point d'entree pour l'empaquetage.

PyInstaller execute le script qu'on lui donne comme programme principal, et
non comme module d'un paquet. Lui passer `murmur/__main__.py` directement
casse donc tous les imports relatifs : « attempted relative import with no
known parent package ».

Ce fichier importe le paquet normalement, ce qui retablit son contexte.

En developpement, `python -m murmur` reste la voie habituelle : le paquet y
est charge correctement, et ce defaut n'y apparait pas — raison pour laquelle
il ne se manifeste qu'a la construction de l'executable.
"""

import sys

from murmur.lancement import main

if __name__ == "__main__":
    sys.exit(main())

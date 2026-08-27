"""Sorties standard d'un programme sans console.

Lance par `pythonw.exe` ou empaquete avec `--windowed`, un programme Python
n'a ni sortie standard ni sortie d'erreur : `sys.stdout` et `sys.stderr`
valent `None`. Le moindre `print`, la moindre trace ecrite par une
bibliotheque, leve alors une erreur d'attribut — et l'echec se produit
souvent dans un fil secondaire, ou personne ne le voit.

C'est ainsi que le tableau de bord demarrait ses processus WebView2 sans
jamais afficher sa fenetre : quelque chose ecrivait sur une sortie inexistante
pendant l'ouverture, et le fil mourait sans un mot.
"""

from __future__ import annotations

import sys


class _Muette:
    """Avale ce qu'on lui ecrit. Un `None` ne sait pas faire semblant."""

    def write(self, _texte: str) -> int:
        return 0

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def assurer() -> None:
    """A appeler en tout premier : rend `print` inoffensif sans console."""
    if sys.stdout is None:
        sys.stdout = _Muette()
    if sys.stderr is None:
        sys.stderr = _Muette()

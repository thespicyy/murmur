"""Cadres a coins arrondis.

Tk ne connait que le rectangle : `highlightthickness` trace un cadre net a
angles droits, et les arcs du canevas ne sont pas lisses — a dix pixels de
rayon, l'escalier se voit plus que l'arrondi. Comme pour la barre de dictee,
les coins sont donc dessines par Pillow a quatre fois la taille puis reduits.

Seuls les **coins** sont des images : les bords et le fond restent des
rectangles du canevas. Une carte redimensionnee ne recalcule donc rien, et le
cache ne depend que du rayon et des couleurs — pas de la taille du widget, qui
change a chaque coup de souris sur le bord de la fenetre.
"""

from __future__ import annotations

import tkinter as tk

ECHELLE = 4

#: Coins deja dessines, indexes par (rayon, fond, dehors, bordure, epaisseur).
#: Une entree par couleur et par rayon, pas une par taille de widget.
#:
#: Deux niveaux, et non un seul : une PhotoImage appartient a l'interpreteur
#: Tcl qui l'a creee et devient inutilisable des qu'il disparait — « image
#: "pyimage7" doesn't exist ». Les images Pillow, elles, n'appartiennent a
#: personne et se conservent indefiniment.
_pillow: dict[tuple, list] = {}
_photos: dict[tuple, tuple] = {}


def _dessiner_coins(rayon: int, fond: str, dehors: str,
                    bordure: str | None, epaisseur: int) -> list:
    from PIL import Image, ImageDraw

    taille = rayon * ECHELLE
    image = Image.new("RGB", (taille, taille), dehors)
    dessin = ImageDraw.Draw(image)
    # Cercle de rayon `taille` centre au coin oppose : la portion visible est
    # exactement le quart superieur gauche.
    dessin.ellipse([0, 0, 2 * taille - 1, 2 * taille - 1], fill=fond)
    if bordure and epaisseur:
        marge = epaisseur * ECHELLE / 2
        dessin.arc([marge, marge, 2 * taille - 1 - marge,
                    2 * taille - 1 - marge],
                   start=180, end=270, fill=bordure,
                   width=epaisseur * ECHELLE)

    haut_gauche = image.resize((rayon, rayon), Image.LANCZOS)
    return [
        haut_gauche,
        haut_gauche.transpose(Image.FLIP_LEFT_RIGHT),
        haut_gauche.transpose(Image.ROTATE_180),
        haut_gauche.transpose(Image.FLIP_TOP_BOTTOM),
    ]


def coins(rayon: int, fond: str, dehors: str, bordure: str | None = None,
          epaisseur: int = 1, widget=None) -> list:
    """Les quatre coins, en PhotoImage, dans l'ordre HG, HD, BD, BG.

    Le dehors est peint plutot que laisse transparent : la couleur du parent
    est toujours connue, et une image opaque evite de dependre de la facon
    dont Tk compose l'alpha selon la version.
    """
    from PIL import ImageTk

    cle = (rayon, fond, dehors, bordure, epaisseur)
    if cle not in _pillow:
        _pillow[cle] = _dessiner_coins(rayon, fond, dehors, bordure, epaisseur)

    interpreteur = getattr(widget, "tk", None)
    connu = _photos.get(cle)
    if connu is not None and connu[0] is interpreteur:
        return connu[1]

    photos = [ImageTk.PhotoImage(image) for image in _pillow[cle]]
    _photos[cle] = (interpreteur, photos)
    return photos


def oublier() -> None:
    """Vide le cache. A appeler au changement de theme, les couleurs changeant."""
    _pillow.clear()
    _photos.clear()


def peindre(canevas: tk.Canvas, largeur: int, hauteur: int, rayon: int,
            fond: str, dehors: str, bordure: str | None = None,
            epaisseur: int = 1, lisere: str | None = None,
            assise: str | None = None) -> None:
    """Trace un rectangle arrondi occupant tout le canevas.

    `lisere` pose un trait clair sous le bord haut, `assise` un trait sombre
    au-dessus du bord bas. C'est ainsi que les interfaces paraissent avoir du
    relief sans degrade : une arete claire en haut se lit comme une surface
    eclairee, une arete sombre en bas comme une ombre portee. Un vrai degrade
    demanderait de peindre **sous** le contenu, ce qu'un cadre Tk opaque
    interdit.

    Lequel des deux selon le theme : sur une carte presque blanche, une arete
    claire ne se voit pas ; sur une carte sombre, une arete sombre non plus.
    """
    canevas.delete("all")
    if largeur < 2 * rayon or hauteur < 2 * rayon:
        # Trop petit pour l'arrondi : mieux vaut un rectangle franc qu'un
        # coin tronque au milieu de sa courbe.
        canevas.create_rectangle(0, 0, largeur, hauteur, fill=fond,
                                 outline=bordure or fond, width=epaisseur)
        return

    quatre = coins(rayon, fond, dehors, bordure, epaisseur,
                   widget=canevas)
    canevas.create_image(0, 0, anchor="nw", image=quatre[0])
    canevas.create_image(largeur, 0, anchor="ne", image=quatre[1])
    canevas.create_image(largeur, hauteur, anchor="se", image=quatre[2])
    canevas.create_image(0, hauteur, anchor="sw", image=quatre[3])

    canevas.create_rectangle(rayon, 0, largeur - rayon, hauteur,
                             fill=fond, outline="")
    canevas.create_rectangle(0, rayon, largeur, hauteur - rayon,
                             fill=fond, outline="")

    if lisere:
        # Un rectangle d'un pixel plutot qu'une ligne : Tk centre ses lignes
        # sur leur ordonnee et melange le trait avec ce qu'il recouvre, ce qui
        # delavait le lisere jusqu'a le rendre invisible.
        canevas.create_rectangle(rayon, 0, largeur - rayon, 1, fill=lisere,
                                 outline="")

    if assise:
        canevas.create_rectangle(rayon, hauteur - 1, largeur - rayon, hauteur,
                                 fill=assise, outline="")

    if bordure and epaisseur:
        decalage = epaisseur / 2
        canevas.create_line(rayon, decalage, largeur - rayon, decalage,
                            fill=bordure, width=epaisseur)
        canevas.create_line(rayon, hauteur - decalage, largeur - rayon,
                            hauteur - decalage, fill=bordure, width=epaisseur)
        canevas.create_line(decalage, rayon, decalage, hauteur - rayon,
                            fill=bordure, width=epaisseur)
        canevas.create_line(largeur - decalage, rayon, largeur - decalage,
                            hauteur - rayon, fill=bordure, width=epaisseur)


class Carte(tk.Frame):
    """Cadre a coins arrondis qui s'ajuste a son contenu.

    Le contenu va dans `interieur`, un cadre ordinaire pose au-dessus du
    canevas et **retreci de la valeur du rayon** sur les cotes : les quatre
    coins restent ainsi decouverts, seuls endroits ou l'arrondi se voit. Le
    cadre exterieur, lui, se dimensionne normalement sur son contenu — un
    canevas seul ne saurait pas le faire, Tk ne lui donnant jamais la taille
    de ce qu'il porte.
    """

    def __init__(self, parent, fond: str, dehors: str | None = None,
                 rayon: int = 10, bordure: str | None = None,
                 epaisseur: int = 1, lisere: str | None = None,
                 assise: str | None = None):
        # Par defaut, la couleur du parent : c'est celle qui doit reapparaitre
        # dans les coins. La supposer donnait des equerres sombres autour des
        # champs poses dans une carte claire, la couleur de fenetre etant
        # peinte la ou se voyait celle de la carte.
        if dehors is None:
            dehors = parent.cget("bg")
        super().__init__(parent, bg=dehors)
        self.fond = fond
        self.dehors = dehors
        self.rayon = rayon
        self.bordure = bordure
        self.lisere = lisere
        self.assise = assise
        self.epaisseur = epaisseur if bordure else 0
        # Ces aretes occupent le premier et le dernier pixel : sans ce
        # retrait, le cadre interieur les recouvrirait, comme le reste.
        self.marge_haute = max(self.epaisseur, 1 if lisere else 0)
        self.marge_basse = max(self.epaisseur, 1 if assise else 0)

        self._canevas = tk.Canvas(self, bg=dehors, highlightthickness=0, bd=0,
                                  takefocus=0)
        self._canevas.place(x=0, y=0, relwidth=1, relheight=1)

        self.interieur = tk.Frame(self, bg=fond)
        self.interieur.pack(fill="both", expand=True, padx=rayon,
                            pady=(self.marge_haute, self.marge_basse))

        self.bind("<Configure>", self._redessiner)

    def _redessiner(self, evenement) -> None:
        peindre(self._canevas, evenement.width, evenement.height, self.rayon,
                self.fond, self.dehors, self.bordure, self.epaisseur,
                self.lisere, self.assise)

    def repeindre(self, fond: str | None = None,
                  bordure: str | None = None) -> None:
        """Change les couleurs sans reconstruire la carte — pour le survol."""
        if fond is not None:
            self.fond = fond
            self.interieur.configure(bg=fond)
        if bordure is not None:
            self.bordure = bordure
        peindre(self._canevas, self.winfo_width(), self.winfo_height(),
                self.rayon, self.fond, self.dehors, self.bordure,
                self.epaisseur, self.lisere, self.assise)

"""Identite visuelle : le symbole Murmur.

Un point central d'ou rayonnent deux arcs — la voix qui se propage. Deux
declinaisons fournies par le kit de marque :

  complete    deux arcs (rayons 26 et 40), trait fin. Pour les grandes tailles.
  compacte    un seul arc, trait epais et point plus gros. Concue pour les
              petites tailles, ou la version complete devient illisible une
              fois reduite.

Le symbole est dessine plutot que charge depuis un fichier image : il doit
changer de couleur selon l'etat de la dictee et selon le theme, ce qui
demanderait autrement une image par combinaison.

Geometrie de reference, sur un carre de 96 (kit de marque) :

    point     centre (48, 48), rayon 7   · compacte : 11
    arc droit centre (48, 48), rayon 26, du haut vers le bas par la droite
    arc gauche centre (48, 48), rayon 40, du bas vers le haut par la gauche
"""

from __future__ import annotations

#: En dessous de cette taille, la version complete devient illisible.
SEUIL_COMPACTE = 40

REFERENCE = 96.0

#: Facteur de surechantillonnage. Pillow ne lisse pas ses traces : on dessine
#: en grand et on reduit.
ECHELLE_RENDU = 8

# Angles Pillow et Tk : 0 degre a 3 h. Pillow tourne dans le sens horaire,
# Tk dans le sens trigonometrique — d'ou deux conventions distinctes plus bas.
_ARC_DROIT_PILLOW = (270, 90)    # du haut au bas, par la droite
_ARC_GAUCHE_PILLOW = (90, 270)   # du bas au haut, par la gauche


def _echelle(taille: int) -> float:
    return taille / REFERENCE


def geometrie(taille: int, compacte: bool | None = None) -> dict:
    """Coordonnees du symbole pour une taille donnee, en pixels."""
    if compacte is None:
        compacte = taille < SEUIL_COMPACTE

    k = _echelle(taille)
    centre = taille / 2

    if compacte:
        return {"compacte": True, "centre": centre,
                "rayon_point": 11 * k, "epaisseur": max(1.0, 12 * k),
                "arcs": [(34 * k, _ARC_GAUCHE_PILLOW)]}

    return {"compacte": False, "centre": centre,
            "rayon_point": 7 * k, "epaisseur": max(1.0, 6 * k),
            "arcs": [(26 * k, _ARC_DROIT_PILLOW),
                     (40 * k, _ARC_GAUCHE_PILLOW)]}


def decalage_optique(taille: int, compacte: bool | None = None,
                     avec_arcs: bool = True) -> float:
    """Correction horizontale pour centrer le symbole a l'oeil.

    Les arcs ne sont pas repartis symetriquement : en version compacte, le
    seul arc occupe toute la moitie gauche et rien a droite. Le point a beau
    etre au centre geometrique, l'ensemble parait pousse vers la droite.

    On calcule donc l'etendue reelle du trace et on la recentre. Sans cela,
    l'icone semble mal alignee dans la barre des taches — un defaut discret
    mais permanent.
    """
    forme = geometrie(taille, compacte)

    gauche = -forme["rayon_point"]
    droite = forme["rayon_point"]
    if avec_arcs:
        for rayon, (depart, _fin) in forme["arcs"]:
            # Le rayon donne l'extension exacte : Pillow epaissit l'arc vers
            # l'INTERIEUR du cercle, pas de part et d'autre. Ajouter une
            # demi-epaisseur surcorrigeait de plusieurs pixels.
            #
            # L'arc gauche part du bas (90 deg), l'arc droit du haut (270).
            if depart == _ARC_GAUCHE_PILLOW[0]:
                gauche = min(gauche, -rayon)
            else:
                droite = max(droite, rayon)

    return -(gauche + droite) / 2


def dessiner_image(taille: int, couleur_point: str, couleur_arcs: str,
                   avec_arcs: bool = True, compacte: bool | None = None,
                   recentrer: bool = True):
    """Rend le symbole en image RGBA transparente (Pillow).

    `avec_arcs=False` ne laisse que le point : c'est ainsi qu'on represente
    l'etat suspendu — plus d'ondes, donc plus d'ecoute. Le sens est immediat,
    la ou un symbole inchange laisserait croire l'application active.

    Le trace est fait a huit fois la taille puis reduit par moyenne de zone.
    Pillow ne lisse ni ses arcs ni ses ellipses : dessine directement a
    vingt-huit pixels, le symbole montrait ses marches d'escalier. La moyenne
    de zone plutot que Lanczos, qui ajoute un lisere clair le long des traits
    fins — bien visible sur un arc de deux pixels.
    """
    from PIL import Image, ImageDraw

    if compacte is None:
        compacte = taille < SEUIL_COMPACTE

    grand = taille * ECHELLE_RENDU
    image = Image.new("RGBA", (grand, grand), (0, 0, 0, 0))
    trace = ImageDraw.Draw(image)
    forme = geometrie(grand, compacte)

    cx = forme["centre"] + (decalage_optique(grand, compacte, avec_arcs)
                            if recentrer else 0.0)
    cy = forme["centre"]

    if avec_arcs:
        epaisseur = int(round(forme["epaisseur"]))
        for rayon, (depart, fin) in forme["arcs"]:
            trace.arc([cx - rayon, cy - rayon, cx + rayon, cy + rayon],
                      start=depart, end=fin, fill=couleur_arcs,
                      width=max(1, epaisseur))

    rayon = forme["rayon_point"]
    trace.ellipse([cx - rayon, cy - rayon, cx + rayon, cy + rayon],
                  fill=couleur_point)
    return image.resize((taille, taille), Image.BOX)


def dessiner_pastille(taille: int, couleur_point: str,
                      couleur_arcs: str = "#ffffff",
                      fond: str = "#0b0b0d", avec_arcs: bool = True,
                      compacte: bool | None = None, rayon_coins: float = 0.22):
    """Symbole clair sur pastille sombre a coins arrondis.

    Forme retenue pour l'icone de la zone de notification : un trace
    transparent disparait sur une barre des taches sombre, alors qu'une
    pastille garde son contraste quel que soit le fond.
    """
    from PIL import Image, ImageDraw

    grand = taille * ECHELLE_RENDU
    image = Image.new("RGBA", (grand, grand), (0, 0, 0, 0))
    trace = ImageDraw.Draw(image)
    trace.rounded_rectangle([0, 0, grand - 1, grand - 1],
                            radius=grand * rayon_coins, fill=fond)
    image = image.resize((taille, taille), Image.BOX)

    symbole = dessiner_image(int(taille * 0.74), couleur_point, couleur_arcs,
                             avec_arcs=avec_arcs, compacte=compacte)
    decalage = (taille - symbole.size[0]) // 2
    image.paste(symbole, (decalage, decalage), symbole)
    return image


def dessiner_canvas(canevas, x: float, y: float, taille: int,
                    couleur_point: str, couleur_arcs: str,
                    avec_arcs: bool = True, etiquette: str = "marque",
                    compacte: bool | None = None,
                    recentrer: bool = True) -> None:
    """Trace le symbole sur un Canvas Tk, centre optiquement sur (x, y).

    Tk mesure les angles dans le sens trigonometrique et attend une etendue
    plutot qu'un angle final : les valeurs Pillow sont converties ici, pour
    que la geometrie ne soit definie qu'a un seul endroit.
    """
    forme = geometrie(taille, compacte)
    if recentrer:
        x += decalage_optique(taille, compacte, avec_arcs)

    if avec_arcs:
        epaisseur = max(1, int(round(forme["epaisseur"])))
        for rayon, (depart, fin) in forme["arcs"]:
            # Sens horaire (Pillow) -> sens trigonometrique (Tk).
            debut_tk = -depart
            etendue = -((fin - depart) % 360)
            canevas.create_arc(x - rayon, y - rayon, x + rayon, y + rayon,
                               start=debut_tk, extent=etendue, style="arc",
                               outline=couleur_arcs, width=epaisseur,
                               tags=etiquette)

    rayon = forme["rayon_point"]
    canevas.create_oval(x - rayon, y - rayon, x + rayon, y + rayon,
                        fill=couleur_point, outline="", tags=etiquette)

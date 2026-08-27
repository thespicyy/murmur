"""Pictogrammes de la barre laterale.

Traces plutot que charges depuis des fichiers, pour la meme raison que le
symbole de la marque : ils doivent suivre la couleur du theme et l'etat de
selection, ce qui demanderait autrement une image par combinaison.

Tous sont dessines dans un carre de reference de 24, au trait, avec une
epaisseur commune — ce qui les fait cohabiter sans que l'un paraisse plus
gras que les autres.
"""

from __future__ import annotations

#: Facteur de surechantillonnage. Huit plutot que quatre : a dix-huit pixels,
#: un trait de deux pixels reduit depuis quatre reste terne et mal defini.
ECHELLE = 8

REFERENCE = 24.0
EPAISSEUR = 1.9

#: Un trace est une liste de primitives, dessinees dans l'ordre donne :
#:   ("ligne", [(x, y), ...])
#:   ("cercle", cx, cy, rayon)               contour seul
#:   ("ellipse", cx, cy, rayon_x, rayon_y)  contour seul
#:   ("disque", cx, cy, rayon)               plein — masque ce qu'il recouvre
#:   ("arc", cx, cy, rayon, debut, fin)      angles en degres, sens horaire
#:   ("rect", x1, y1, x2, y2, rayon_coins)       contour seul
#:   ("rect_plein", x1, y1, x2, y2, rayon_coins)  plein
TRACES: dict[str, list] = {
    # Micro : capsule, arceau et pied.
    "dictees": [
        ("rect", 9.5, 3, 14.5, 13.5, 2.5),
        ("arc", 12, 11, 5.5, 0, 180),
        ("ligne", [(12, 16.5), (12, 20)]),
        ("ligne", [(8.5, 20), (15.5, 20)]),
    ],
    # Livre ouvert.
    "dictionnaire": [
        ("ligne", [(12, 6.5), (12, 19)]),
        ("ligne", [(12, 6.5), (5, 5), (5, 17.5), (12, 19)]),
        ("ligne", [(12, 6.5), (19, 5), (19, 17.5), (12, 19)]),
    ],
    # Histogramme a barres pleines : au trait, il se perdait a dix-huit
    # pixels a cote des autres pictogrammes, plus charpentes.
    "statistiques": [
        ("rect_plein", 4.5, 13, 8, 19.5, 1),
        ("rect_plein", 10.25, 5.5, 13.75, 19.5, 1),
        ("rect_plein", 16, 10, 19.5, 19.5, 1),
    ],
    # Pictogrammes d'usage de la page Statistiques. Au trait et d'une seule
    # couleur, comme le reste : les emoji en couleur juraient a cote d'une
    # interface qui n'en compte aucune.
    "app_navigateur": [
        ("cercle", 12, 12, 8),
        ("ligne", [(4, 12), (20, 12)]),
        # Le meridien est une ellipse etroite : deux arcs de cercle en
        # donnaient une croix, et le globe passait pour une cible.
        ("ellipse", 12, 12, 4, 8),
    ],
    "app_code": [
        ("ligne", [(9, 8), (4.5, 12), (9, 16)]),
        ("ligne", [(15, 8), (19.5, 12), (15, 16)]),
    ],
    "app_terminal": [
        ("rect", 3.5, 5, 20.5, 19, 2.5),
        ("ligne", [(7, 10), (10, 12.5), (7, 15)]),
        ("ligne", [(12.5, 15.5), (17, 15.5)]),
    ],
    "app_message": [
        ("ligne", [(5, 17), (5, 7.5), (19, 7.5), (19, 15.5), (9.5, 15.5),
                   (5, 19)]),
    ],
    "app_courriel": [
        ("rect", 3.5, 6, 20.5, 18, 2),
        ("ligne", [(3.5, 7.5), (12, 13.5), (20.5, 7.5)]),
    ],
    "app_document": [
        ("ligne", [(6, 20), (6, 4), (15, 4), (18, 7), (18, 20), (6, 20)]),
        ("ligne", [(9, 11), (15, 11)]),
        ("ligne", [(9, 15), (15, 15)]),
    ],
    "app_note": [
        ("ligne", [(5.5, 18.5), (5.5, 5.5), (18.5, 5.5), (18.5, 18.5),
                   (5.5, 18.5)]),
        ("ligne", [(9, 10), (15, 10)]),
        ("ligne", [(9, 14), (13, 14)]),
    ],
    "app_media": [
        ("cercle", 8, 17, 3),
        ("ligne", [(11, 17), (11, 5), (18, 7), (18, 15)]),
        ("cercle", 15, 15, 3),
    ],
    "app_jeu": [
        ("rect", 3, 8, 21, 17, 4),
        ("ligne", [(7.5, 10.5), (7.5, 14.5)]),
        ("ligne", [(5.5, 12.5), (9.5, 12.5)]),
        ("disque", 16, 11.5, 1.3),
        ("disque", 18.5, 14, 1.3),
    ],
    "app_ia": [
        ("ligne", [(12, 3.5), (13.6, 9.4), (19.5, 11), (13.6, 12.6),
                   (12, 18.5), (10.4, 12.6), (4.5, 11), (10.4, 9.4),
                   (12, 3.5)]),
        ("ligne", [(18.5, 16), (19.2, 18.3), (21.5, 19), (19.2, 19.7),
                   (18.5, 22), (17.8, 19.7), (15.5, 19), (17.8, 18.3),
                   (18.5, 16)]),
    ],
    "app_dossier": [
        ("ligne", [(3.5, 8), (3.5, 18.5), (20.5, 18.5), (20.5, 8)]),
        ("ligne", [(3.5, 8), (3.5, 5.5), (9.5, 5.5), (11.5, 8), (20.5, 8)]),
    ],
    "app_autre": [
        ("rect", 3.5, 5, 20.5, 16, 2),
        ("ligne", [(9, 20), (15, 20)]),
        ("ligne", [(12, 16), (12, 20)]),
    ],
    # Commandes de fenetre. Redessinees parce que la barre de titre du
    # systeme a ete retiree : ce sont elles qui la remplacent.
    "reduire": [
        ("ligne", [(6, 12), (18, 12)]),
    ],
    "agrandir": [
        ("rect", 6, 6, 18, 18, 1.5),
    ],
    "restaurer": [
        ("rect", 8.5, 5.5, 18.5, 15.5, 1.5),
        ("ligne", [(5.5, 8.5), (5.5, 18.5), (15.5, 18.5)]),
    ],
    "fermer": [
        ("ligne", [(6.5, 6.5), (17.5, 17.5)]),
        ("ligne", [(17.5, 6.5), (6.5, 17.5)]),
    ],
    # Volet : un cadre et sa cloison. Le meme pictogramme sert a replier et a
    # deplier — c'est le volet qu'il designe, pas le sens du mouvement.
    "panneau": [
        ("rect", 3.5, 5, 20.5, 19, 2.5),
        ("ligne", [(9.5, 5), (9.5, 19)]),
    ],
    # Dossier : languette puis corps. Sans lui, le lien du bas de la barre
    # laterale n'aurait pas de pictogramme et son libelle ne s'alignerait pas
    # sur les autres.
    "dossier": [
        ("ligne", [(3.5, 8), (3.5, 18.5), (20.5, 18.5), (20.5, 8)]),
        ("ligne", [(3.5, 8), (3.5, 5.5), (9.5, 5.5), (11.5, 8), (20.5, 8)]),
    ],
    # Curseurs. Un engrenage circulaire se confondrait avec le symbole de la
    # marque, lui aussi fait d'un cercle et d'un arc.
    "reglages": [
        ("ligne", [(4.5, 7), (19.5, 7)]),
        ("ligne", [(4.5, 12), (19.5, 12)]),
        ("ligne", [(4.5, 17), (19.5, 17)]),
        # Poignees pleines, posees apres les rails : elles les masquent,
        # comme un curseur reel.
        ("disque", 15, 7, 2.6),
        ("disque", 8.5, 12, 2.6),
        ("disque", 16, 17, 2.6),
    ],
}


def dessiner(trace, image, couleur: str, taille: int, k: int = 8) -> None:
    """Trace un pictogramme sur une image Pillow deja creee."""
    from PIL import ImageDraw

    dessin = ImageDraw.Draw(image)
    echelle = taille * k / REFERENCE
    largeur = max(1, round(EPAISSEUR * echelle))

    def point(x, y):
        return x * echelle, y * echelle

    for primitive in trace:
        genre = primitive[0]

        if genre == "ligne":
            points = [point(x, y) for x, y in primitive[1]]
            dessin.line(points, fill=couleur, width=largeur, joint="curve")
            # Pillow n'arrondit pas les extremites : sans ces disques, les
            # angles paraissent ebreches.
            for x, y in points:
                r = largeur / 2
                dessin.ellipse([x - r, y - r, x + r, y + r], fill=couleur)

        elif genre == "ellipse":
            _, cx, cy, rayon_x, rayon_y = primitive
            x, y = point(cx, cy)
            rx, ry = rayon_x * echelle, rayon_y * echelle
            dessin.ellipse([x - rx, y - ry, x + rx, y + ry],
                           outline=couleur, width=largeur)

        elif genre == "cercle":
            _, cx, cy, rayon = primitive
            x, y = point(cx, cy)
            r = rayon * echelle
            dessin.ellipse([x - r, y - r, x + r, y + r],
                           outline=couleur, width=largeur)

        elif genre == "disque":
            _, cx, cy, rayon = primitive
            x, y = point(cx, cy)
            r = rayon * echelle
            dessin.ellipse([x - r, y - r, x + r, y + r], fill=couleur)

        elif genre == "arc":
            _, cx, cy, rayon, debut, fin = primitive
            x, y = point(cx, cy)
            r = rayon * echelle
            dessin.arc([x - r, y - r, x + r, y + r], start=debut, end=fin,
                       fill=couleur, width=largeur)

        elif genre == "rect_plein":
            _, x1, y1, x2, y2, coins = primitive
            a = point(x1, y1)
            b = point(x2, y2)
            dessin.rounded_rectangle([a[0], a[1], b[0], b[1]],
                                     radius=coins * echelle, fill=couleur)

        elif genre == "rect":
            _, x1, y1, x2, y2, coins = primitive
            a = point(x1, y1)
            b = point(x2, y2)
            dessin.rounded_rectangle([a[0], a[1], b[0], b[1]],
                                     radius=coins * echelle,
                                     outline=couleur, width=largeur)


def rendre(nom: str, couleur: str, taille: int = 18):
    """Pictogramme en image RGBA, bords lisses.

    Dessine a huit fois la taille puis reduit par moyenne de zone : le canevas
    de Tk ne fait pas d'anticrenelage, et des traits fins en escalier se
    remarquent d'autant plus qu'ils sont petits. La moyenne de zone plutot que
    Lanczos, qui borde chaque trait d'un lisere clair.
    """
    from PIL import Image

    k = ECHELLE
    image = Image.new("RGBA", (taille * k, taille * k), (0, 0, 0, 0))
    dessiner(TRACES[nom], image, couleur, taille, k)
    return image.resize((taille, taille), Image.BOX)


def case(cochee: bool, taille: int, fond: str, bordure: str,
         accent: str, couleur_coche: str):
    """Case a cocher dessinee, en image RGB.

    Celle de Tk est rendue par Windows : bord gris, coins droits, coche
    anguleuse — elle traverse le theme sans se laisser recolorier, et se
    reconnait au premier coup d'oeil comme un element etranger.
    """
    from PIL import Image, ImageDraw

    k = ECHELLE
    grand = taille * k
    image = Image.new("RGB", (grand, grand), fond)
    dessin = ImageDraw.Draw(image)
    rayon = grand * 0.28

    if cochee:
        dessin.rounded_rectangle([0, 0, grand - 1, grand - 1], radius=rayon,
                                 fill=accent)
        # Coche en deux segments, aux proportions du trace des pictogrammes.
        epaisseur = max(1, round(grand * 0.11))
        points = [(grand * 0.26, grand * 0.52),
                  (grand * 0.43, grand * 0.69),
                  (grand * 0.75, grand * 0.33)]
        dessin.line(points, fill=couleur_coche, width=epaisseur, joint="curve")
        for x, y in points:
            r = epaisseur / 2
            dessin.ellipse([x - r, y - r, x + r, y + r], fill=couleur_coche)
    else:
        epaisseur = max(1, round(grand * 0.055))
        dessin.rounded_rectangle([epaisseur / 2, epaisseur / 2,
                                  grand - 1 - epaisseur / 2,
                                  grand - 1 - epaisseur / 2],
                                 radius=rayon, outline=bordure,
                                 width=epaisseur)

    return image.resize((taille, taille), Image.BOX)


def noms() -> list[str]:
    return list(TRACES)

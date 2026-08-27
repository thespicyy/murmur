"""Trace des barres pour la page Statistiques.

Le canevas de Tk sait tracer des rectangles, mais ni sommets arrondis ni
anticrenelage : a cette taille, l'escalier des bords se remarque plus que la
courbe des donnees. Les barres sont donc peintes par Pillow au double de la
taille puis reduites, et posees en image sur le canevas.

Les **libelles** restent du texte de canevas : contrairement aux traces, le
texte est rendu par le moteur de polices du systeme, qui le lisse deja. Les
dessiner dans l'image obligerait a retrouver un fichier de police sur le
disque, pour un resultat identique.

La geometrie des barres est calculee par `sommet`, appelee aussi bien ici que
par l'appelant qui pose les libelles : deux calculs paralleles finiraient par
diverger, et un chiffre flottant a cote de sa barre se remarque.
"""

from __future__ import annotations

ECHELLE = 2

#: Hauteur minimale d'une barre non nulle, en pixels. Une barre d'un pixel se
#: confondrait avec la trace laissee par une journee vide.
MINIMUM = 6

#: Trace d'une journee sans dictee. Sans elle, la serie parait interrompue.
CREUX = 3


def melange(couleur: str, autre: str, part: float) -> str:
    """Interpole deux couleurs, `part` allant de 0 (la premiere) a 1."""
    def canaux(valeur: str) -> tuple[int, ...]:
        valeur = valeur.lstrip("#")
        return tuple(int(valeur[i:i + 2], 16) for i in (0, 2, 4))

    a, b = canaux(couleur), canaux(autre)
    return "#%02x%02x%02x" % tuple(
        round(x + (y - x) * part) for x, y in zip(a, b))


def sommet(valeur: int, maximum: int, hauteur: int,
           marge_haut: int = 0) -> float:
    """Ordonnee du haut d'une barre, origine en haut du cadre.

    La marge reserve la place des chiffres poses au-dessus des barres : sans
    elle, la valeur du jour le plus charge sortirait du cadre par le haut.
    """
    if not valeur or maximum <= 0:
        return hauteur - CREUX
    utile = max(1, hauteur - marge_haut)
    return hauteur - max(MINIMUM, (valeur / maximum) * utile)


def barres(largeur: int, hauteur: int, valeurs: list[int], fond: str,
           couleur: str, couleur_vive: str, reperes: str | None = None,
           marge_haut: int = 0, epaisseur_max: int = 30):
    """Image des barres, sans libelles, la derniere valeur mise en avant.

    La derniere barre est celle d'aujourd'hui : c'est la seule que l'on
    cherche du regard en ouvrant la page, elle porte donc la couleur vive.
    """
    from PIL import Image, ImageDraw

    k = ECHELLE
    image = Image.new("RGB", (largeur * k, hauteur * k), fond)
    if not valeurs or largeur < 20 or hauteur < 20:
        return image

    dessin = ImageDraw.Draw(image)
    base = hauteur * k
    maximum = max(valeurs)
    pas = largeur * k / len(valeurs)
    epaisseur = min(epaisseur_max * k, pas * 0.62)
    creux = melange(fond, couleur, 0.7)

    if reperes:
        # Trois reperes horizontaux : assez pour situer une hauteur, trop peu
        # pour quadriller le fond.
        teinte = melange(fond, reperes, 0.32)
        utile = hauteur - marge_haut
        for part in (0.34, 0.67, 1.0):
            y = (hauteur - part * utile) * k
            dessin.line([(0, y), (largeur * k, y)], fill=teinte, width=1)

    for rang, valeur in enumerate(valeurs):
        centre = pas * (rang + 0.5)
        gauche = centre - epaisseur / 2
        droite = centre + epaisseur / 2
        dernier = rang == len(valeurs) - 1
        teinte = couleur_vive if dernier else couleur
        haut = sommet(valeur, maximum, hauteur, marge_haut) * k

        if not valeur:
            dessin.rounded_rectangle([gauche, haut, droite, base],
                                     radius=CREUX * k / 2, fill=creux)
            continue

        rayon = epaisseur / 2
        dessin.rounded_rectangle([gauche, haut, droite, base], radius=rayon,
                                 fill=teinte)
        # Pillow arrondit les quatre coins : on redonne un pied droit, la
        # barre reposant sur une ligne de base.
        dessin.rectangle([gauche, base - rayon, droite, base], fill=teinte)

    return image.resize((largeur, hauteur), Image.LANCZOS)

# --------------------------------------------------------------------------
# Jauge
# --------------------------------------------------------------------------

def jauge(largeur: int, hauteur: int, part: float, fond: str, rail: str,
          couleur: str, epaisseur: int = 11):
    """Demi-anneau rempli a `part` (0 a 1), ouvert vers le bas.

    Un chiffre seul ne dit pas s'il est bon. L'arc situe la valeur dans une
    plage, ce que le nombre ne fait pas.
    """
    from PIL import Image, ImageDraw

    k = ECHELLE
    image = Image.new("RGB", (largeur * k, hauteur * k), fond)
    if largeur < 20 or hauteur < 20:
        return image

    dessin = ImageDraw.Draw(image)
    trait = epaisseur * k
    marge = trait / 2 + k
    boite = [marge, marge, largeur * k - marge, largeur * k - marge]

    dessin.arc(boite, start=180, end=360, fill=rail, width=int(trait))
    _bout(dessin, boite, 180, trait, rail)
    _bout(dessin, boite, 360, trait, rail)

    part = max(0.0, min(1.0, part))
    if part > 0:
        fin = 180 + 180 * part
        dessin.arc(boite, start=180, end=fin, fill=couleur, width=int(trait))
        # Pillow coupe ses arcs a l'equerre : sans ces deux disques, l'anneau
        # se termine par deux tranches nettes la ou toute jauge soignee
        # s'arrondit.
        _bout(dessin, boite, 180, trait, couleur)
        _bout(dessin, boite, fin, trait, couleur)

    return image.resize((largeur, hauteur), Image.BOX)


def _bout(dessin, boite, angle: float, trait: float, couleur: str) -> None:
    """Disque pose a l'extremite d'un arc, pour lui arrondir le bout."""
    import math

    gauche, haut, droite, bas = boite
    cx, cy = (gauche + droite) / 2, (haut + bas) / 2
    rayon = (droite - gauche) / 2 - trait / 2
    x = cx + rayon * math.cos(math.radians(angle))
    y = cy + rayon * math.sin(math.radians(angle))
    r = trait / 2
    dessin.ellipse([x - r, y - r, x + r, y + r], fill=couleur)


# --------------------------------------------------------------------------
# Calendrier d'activite
# --------------------------------------------------------------------------

#: Ecart entre deux cases, en pixels de sortie.
ECART_CASES = 3


def cote_case(hauteur: int, ecart: int = ECART_CASES) -> float:
    """Cote d'une case pour tenir sept rangees dans la hauteur donnee."""
    return max(4.0, (hauteur - 6 * ecart) / 7)


def semaines(serie: list) -> list[list]:
    """Repartit la serie en colonnes hebdomadaires, lundi en haut.

    Les debuts et fins incomplets sont combles par `None` : sans cela, les
    rangees ne correspondraient plus a des jours fixes et le calendrier
    deviendrait illisible.
    """
    if not serie:
        return []

    tete = [None] * serie[0][0].weekday()
    cases = tete + list(serie)
    while len(cases) % 7:
        cases.append(None)
    return [cases[i:i + 7] for i in range(0, len(cases), 7)]


def _teinte(valeur: int, maximum: int, paliers: list[str]) -> str:
    """Palier de couleur pour une valeur. Zero garde le palier le plus pale."""
    if valeur <= 0 or maximum <= 0:
        return paliers[0]
    rang = 1 + int((len(paliers) - 2) * min(1.0, valeur / maximum))
    return paliers[min(rang, len(paliers) - 1)]


def calendrier(largeur: int, hauteur: int, serie: list, fond: str,
               paliers: list[str], ecart: int = ECART_CASES):
    """Grille d'activite : une colonne par semaine, une rangee par jour."""
    from PIL import Image, ImageDraw

    k = ECHELLE
    image = Image.new("RGB", (largeur * k, hauteur * k), fond)
    colonnes = semaines(serie)
    if not colonnes or largeur < 20:
        return image

    dessin = ImageDraw.Draw(image)
    cote = cote_case(hauteur, ecart)
    maximum = max((valeur for _, valeur in serie), default=0)

    for rang, colonne in enumerate(colonnes):
        x = rang * (cote + ecart) * k
        if x > largeur * k:
            break
        for jour, case in enumerate(colonne):
            if case is None:
                continue
            y = jour * (cote + ecart) * k
            dessin.rounded_rectangle(
                [x, y, x + cote * k, y + cote * k], radius=cote * k * 0.28,
                fill=_teinte(case[1], maximum, paliers))

    return image.resize((largeur, hauteur), Image.BOX)

# --------------------------------------------------------------------------
# Rubans horizontaux
# --------------------------------------------------------------------------

#: Largeur minimale d'un ruban. Reduit a quelques pixels, il ne laisserait
#: pas la place d'y ecrire son pourcentage, qui est ce qu'on vient lire.
MINIMUM_RUBAN = 46


def rubans(largeur: int, hauteur_ruban: int, parts: list[float], fond: str,
           couleur: str, rail: str | None = None, ecart: int = 12,
           minimum: int = MINIMUM_RUBAN):
    """Une barre horizontale par valeur, empilees, coins arrondis.

    Chaque part vaut de 0 a 1. Une largeur minimale est garantie : un ruban
    reduit a quelques pixels ne laisserait pas la place d'y ecrire son
    pourcentage, qui est ce qu'on vient lire.
    """
    from PIL import Image, ImageDraw

    k = ECHELLE
    hauteur = len(parts) * hauteur_ruban + max(0, len(parts) - 1) * ecart
    image = Image.new("RGB", (largeur * k, max(1, hauteur) * k), fond)
    if not parts or largeur < 20:
        return image

    dessin = ImageDraw.Draw(image)
    # Coins a peine adoucis : une barre en forme de pilule prend l'allure
    # d'une etiquette et se lit moins bien comme une mesure.
    rayon = min(5 * k, hauteur_ruban * k / 2)

    for rang, part in enumerate(parts):
        haut = rang * (hauteur_ruban + ecart) * k
        bas = haut + hauteur_ruban * k
        if rail:
            dessin.rounded_rectangle([0, haut, largeur * k, bas], radius=rayon,
                                     fill=rail)
        longueur = max(minimum * k, largeur * k * max(0.0, min(1.0, part)))
        dessin.rounded_rectangle([0, haut, longueur, bas], radius=rayon,
                                 fill=couleur)

    return image.resize((largeur, max(1, hauteur)), Image.BOX)


def hauteur_rubans(nombre: int, hauteur_ruban: int, ecart: int = 12) -> int:
    """Hauteur totale occupee, pour dimensionner le canevas qui les porte."""
    return nombre * hauteur_ruban + max(0, nombre - 1) * ecart

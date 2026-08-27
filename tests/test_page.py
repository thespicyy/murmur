"""Les feuilles de la page du tableau de bord.

Rien ici n'ouvre de fenetre : on lit les fichiers. Ce qui se verifie ainsi est
limite, mais une famille de defauts precise s'y attrape — la collision de noms
de classe, qui ne se voit qu'a l'ecran, souvent sur une page qu'on regarde
rarement, et jamais depuis le code qu'on vient d'ecrire.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "murmur" / "tableau" / "web"
STYLE = (WEB / "style.css").read_text(encoding="utf-8")


def _classes(fichier: str) -> set[str]:
    texte = (WEB / fichier).read_text(encoding="utf-8")
    return {nom
            for attribut in re.findall(r'class="([^"$]*)"', texte)
            for nom in attribut.split()}


def _modificateurs() -> set[str]:
    """Classes posees EN PLUS d'une autre sur un meme element.

    Deux ecritures a lire : le second nom d'un `class="a b"`, et tout
    `classList.add(...)`.
    """
    source = "\n".join((WEB / f).read_text(encoding="utf-8")
                       for f in ("index.html", "app.js"))
    noms = {nom
            for attribut in re.findall(r'class="([^"$]*)"', source)
            for nom in attribut.split()[1:]}
    return noms | set(re.findall(r'classList\.add\("([^"]+)"\)', source))


def test_aucune_fiche_ne_reprend_un_nom_de_l_ossature():
    """La page a une ossature — `.corps`, `.panneau`, `.laterale`… — dont les
    regles sont ecrites pour la fenetre entiere : `display: flex`, hauteur
    calculee sur la hauteur disponible.

    Une fiche qui reutilise un de ces noms en herite en silence. C'est arrive :
    la fiche d'un terme du dictionnaire s'appelait `corps`. Ses deux lignes
    devenaient deux colonnes collees l'une a l'autre, dans une carte haute
    comme l'ecran, le nom du terme colle a son descriptif.
    """
    communes = _classes("index.html") & _classes("app.js")
    assert not communes, (
        f"noms repris de l'ossature de la page : {sorted(communes)}. "
        f"Les regles ecrites pour la fenetre entiere s'appliqueraient a une "
        f"fiche.")


def test_aucun_modificateur_ne_porte_le_nom_d_un_composant():
    """Un nom pose en second sur un element ne doit pas etre aussi celui d'un
    composant a part entiere.

    C'est arrive, et le calendrier d'activite en est devenu illisible : une
    case de remplissage portait `vide`, qui est aussi le nom du message « rien
    a afficher » d'une liste — lequel impose 72 px de marge interne en haut et
    en bas. La case heritait donc de 144 px de hauteur minimale ;
    `aspect-ratio: 1` en tirait la largeur, et toute la grille passait a 144 px
    par case au lieu de 15.

    Un modificateur decrit un etat (`actif`, `creuse`, `danger`) ; un composant
    porte une mise en page. Les deux ne peuvent pas partager un nom.
    """
    composants = set(re.findall(r"^\.([a-z0-9-]+)\s*\{", STYLE, re.M))

    collisions = _modificateurs() & composants
    assert not collisions, (
        f"noms a la fois modificateur et composant : {sorted(collisions)}. "
        f"La mise en page du composant s'appliquerait a l'element modifie.")


def test_toute_classe_de_l_ossature_est_stylee():
    """Un nom d'ossature sans regle est soit une faute de frappe, soit un
    reste : dans les deux cas la page ne ressemble plus a ce qu'on croit."""
    for nom in _classes("index.html"):
        assert re.search(rf"\.{re.escape(nom)}\b", STYLE), \
            f"« {nom} » ne correspond a aucune regle de style"

r"""Capture le tableau de bord, page par page, sur les donnees de demonstration.

    .venv\Scripts\python.exe outils\demo.py
    .venv\Scripts\python.exe outils\captures.py

PAS DE CAPTURE D'ECRAN, ET C'EST DELIBERE

La voie evidente — poser la vraie fenetre au premier plan et photographier le
rectangle qu'elle occupe — ne marche pas et ne doit pas etre tentee. Windows
refuse le passage au premier plan a un processus qui n'a pas la main, si bien
que la photo garde ce qui se trouvait a l'ecran : les fenetres de
l'utilisateur, ce qu'il lisait, ce qu'il regardait. Essaye ici, elle a rendu
une video en cours de lecture. Les images ont ete effacees.

On rend donc la page hors ecran, dans un navigateur sans fenetre, a partir de
l'apercu autonome que `apercu.py` sait fabriquer. Rien de ce qui est
capture ne vient de l'ecran de qui que ce soit.

Ce qu'on y perd : les coins arrondis et l'ombre que Windows compose autour de
la fenetre. La barre de titre, elle, appartient a la page et figure bien sur
les images.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

#: La racine du projet, un cran au-dessus de `outils/`.
RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

#: Le navigateur repart parfois les mains vides quand l'instance
#: precedente n'a pas fini de se retirer. On reessaie plutot que de
#: laisser une image de la veille en place.
ESSAIS = 4
REPOS_S = 2.0

DOSSIER_DONNEES = RACINE / "docs" / "captures" / "donnees"
SORTIE = RACINE / "docs" / "captures"

#: Taille de rendu. Celle de la fenetre au repos, en pixels reels d'un ecran a
#: cent pour cent : les captures ne doivent pas dependre de l'echelle du poste
#: qui les produit.
LARGEUR, HAUTEUR = 1060, 700

#: Les images sont rendues a une fois et demie cette taille — 1600 x 1057.
#: C'est la definition attendue par le portfolio, et elle vaut mieux qu'un
#: agrandissement apres coup : le texte est vraiment trace a cette echelle.
ECHELLE = 1.5094

#: Navigateurs capables de rendre une page sans ouvrir de fenetre, dans
#: l'ordre de preference. Edge est present sur toute machine Windows.
NAVIGATEURS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
]

#: Page, langue, theme, nom du fichier.
PLANCHE = [
    ("statistiques", "en", "clair", "insights"),
    ("dictees", "en", "clair", "dictation"),
    ("dictionnaire", "en", "clair", "dictionary"),
    ("reglages", "en", "clair", "settings"),
    ("statistiques", "en", "sombre", "insights-sombre"),
    ("dictees", "en", "sombre", "dictation-sombre"),
]


def navigateur() -> Path:
    for chemin in NAVIGATEURS:
        if chemin.exists():
            return chemin
    sys.exit("aucun navigateur capable de rendre sans fenetre n'a ete trouve")


def rendre(exe: Path, page: Path, image: Path) -> bool:
    """Rend la page dans un navigateur sans fenetre, vers un PNG.

    Un profil jetable a chaque fois : sans lui, le navigateur refuse de
    demarrer si l'utilisateur en a deja un ouvert.

    On tolere que ce profil resiste a l'effacement : le navigateur laisse
    derriere lui un dossier « Crashpad » qu'il tient encore au moment ou il
    rend la main. Sans cette tolerance, la planche s'arretait en son milieu et
    les captures suivantes n'etaient jamais refaites — celles de la veille
    restaient en place, ressemblantes, et personne ne le voyait.
    """
    for essai in range(ESSAIS):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profil:
            resultat = subprocess.run(
                [str(exe), "--headless=new", "--disable-gpu",
                 f"--user-data-dir={profil}",
                 f"--window-size={LARGEUR},{HAUTEUR}",
                 f"--force-device-scale-factor={ECHELLE}",
                 "--hide-scrollbars",
                 # Le temps que les animations d'entree se posent : les barres
                 # d'usage poussent en 700 ms, la jauge en 900.
                 "--virtual-time-budget=2500",
                 f"--screenshot={image}", page.as_uri()],
                capture_output=True, text=True, timeout=120)
        if image.exists():
            return True
        # L'instance precedente n'a pas fini de rendre la main : le navigateur
        # repart alors sans rien dire, code de retour zero et sortie vide. Une
        # pause suffit — inutile de chercher plus loin, il n'y a rien a lire.
        time.sleep(REPOS_S)
    print(f"     {resultat.stderr.strip()[:200]}")
    return False


def main() -> int:
    if not (DOSSIER_DONNEES / "historique.sqlite3").exists():
        sys.exit("donnees de demonstration absentes — lance outils/demo.py")

    # Avant tout import de `murmur` : c'est cette variable qui decide quelle
    # base est lue, et les donnees reelles ne doivent jamais l'etre ici.
    os.environ["MURMUR_DONNEES"] = str(DOSSIER_DONNEES)
    import apercu

    exe = navigateur()
    print(f"  rendu par : {exe.name}")
    pages = SORTIE / "pages"
    SORTIE.mkdir(parents=True, exist_ok=True)

    for page, langue, theme, nom in PLANCHE:
        source = apercu.batir(langue, theme, ouvrir_sur=page,
                                     sortie=pages)
        image = SORTIE / f"{nom}.png"
        image.unlink(missing_ok=True)
        if rendre(exe, source, image):
            poids = image.stat().st_size / 1024
            from PIL import Image
            taille = Image.open(image).size
            print(f"  {nom:<18} {taille[0]} x {taille[1]}   {poids:5.0f} Ko")
        else:
            print(f"  {nom:<18} echec du rendu")

    shutil.rmtree(pages, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

r"""Fabrique l'archive a distribuer.

    .venv\Scripts\python.exe outils\construire.py
    .venv\Scripts\python.exe outils\empaqueter.py

Produit `Murmur-<version>-windows-x64.zip` : l'application, le moteur, ses
bibliotheques — et PAS le modele de reconnaissance vocale.

POURQUOI LE MODELE RESTE DEHORS

Il pese 574 Mo, contre 138 pour tout le reste. Le mettre dedans quadruplerait
l'archive pour un fichier que Murmur sait aller chercher lui-meme au premier
lancement, en choisissant celui qui convient a la machine — et sur une machine
sans carte graphique, ce n'est pas celui-la qu'il faut.

Le modele de detection de parole, lui, reste dans l'archive : 885 Ko, et sans
lui le moteur ne saurait pas ou s'arreter.

CE QUE L'ARCHIVE NE CONTIENT PAS NON PLUS

Ni configuration, ni historique, ni dictionnaire : ils vivent dans les donnees
de l'utilisateur. Une archive qui en emporterait diffuserait des dictees.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

#: La racine du projet, un cran au-dessus de `outils/`.
RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from murmur import modeles  # noqa: E402

NOM = "Murmur"
DIST = RACINE / "dist" / NOM
SORTIE = RACINE / "dist"

#: Les modeles de transcription, obtenus au premier lancement. Le motif couvre
#: les deux — celui du poste de developpement comme celui d'une machine sans
#: carte — et tout autre qu'on essaierait plus tard.
MODELES_TRANSCRIPTION = re.compile(r"^ggml-(tiny|base|small|medium|large).*\.bin$")

#: Ce qui ne doit jamais partir : des dictees, une configuration personnelle.
INTERDITS = ("config.json", "historique.sqlite3", "lexique.json")


def a_emporter(chemin: Path) -> bool:
    """Ce fichier va-t-il dans l'archive ?"""
    if chemin.name in INTERDITS:
        return False
    return not MODELES_TRANSCRIPTION.match(chemin.name)


def version() -> str:
    """Version declaree par le paquet, pour nommer l'archive."""
    texte = (RACINE / "murmur" / "__init__.py").read_text(encoding="utf-8")
    trouve = re.search(r'__version__\s*=\s*["\']([^"\']+)', texte)
    return trouve.group(1) if trouve else "0.0.0"


def verifier_fraicheur() -> None:
    """L'executable est-il plus recent que les sources ?

    Piege vecu : l'archive a ete fabriquee a partir d'un executable construit
    une demi-heure plus tot, donc depourvu de la fonctionnalite qu'elle etait
    censee livrer. L'essai a echoue sur un symptome parfaitement trompeur —
    « modele introuvable » — qui decrivait l'ancienne version.

    Empaqueter ne construit pas : ce n'est pas son role, et lancer une
    construction de plusieurs minutes en douce serait pire. Mais se taire
    l'etait aussi.
    """
    executable = DIST / f"{NOM}.exe"
    if not executable.exists():
        return

    fait_le = executable.stat().st_mtime
    plus_recents = [
        source for source in (RACINE / "murmur").rglob("*.py")
        if source.stat().st_mtime > fait_le]
    if plus_recents:
        noms = ", ".join(sorted(s.name for s in plus_recents)[:5])
        reste = f" (+{len(plus_recents) - 5})" if len(plus_recents) > 5 else ""
        sys.exit(f"""l'executable est plus ancien que les sources.
    modifie(s) depuis : {noms}{reste}
    L'archive livrerait une version depassee. Reconstruis d'abord :
        .venv\Scripts\python.exe outils\construire.py""")


def fabriquer() -> Path:
    verifier_fraicheur()
    if not (DIST / f"{NOM}.exe").exists():
        sys.exit(f"application introuvable dans {DIST}.\n"
                 f"    Lance d'abord : .venv\\Scripts\\python.exe outils\construire.py")

    moteur = DIST / "engine"
    if not (moteur / "whisper-server.exe").exists():
        sys.exit(f"moteur introuvable dans {moteur}")

    archive = SORTIE / f"{NOM}-{version()}-windows-x64.zip"
    archive.unlink(missing_ok=True)

    emportes = ecartes = 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zip_:
        for fichier in sorted(DIST.rglob("*")):
            if not fichier.is_file():
                continue
            if not a_emporter(fichier):
                ecartes += 1
                continue
            zip_.write(fichier, Path(NOM) / fichier.relative_to(DIST))
            emportes += 1

    return archive, emportes, ecartes


def main() -> int:
    print("=" * 62)
    print(f"  Archive de {NOM}")
    print("=" * 62)

    archive, emportes, ecartes = fabriquer()
    poids = archive.stat().st_size / 1e6

    print(f"  fichiers  : {emportes} emportes, {ecartes} ecarte(s)")
    print(f"  archive   : {archive.name}  ({poids:.0f} Mo)")
    print()
    print("  Le modele de reconnaissance vocale n'y est pas : Murmur le prend")
    print("  au premier lancement, en choisissant celui qui convient.")
    print(f"    avec carte graphique : {modeles.AVEC_CARTE.megaoctets} Mo")
    print(f"    sans                 : {modeles.SANS_CARTE.megaoctets} Mo")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Construit Murmur.exe.

    .venv\\Scripts\\python.exe outils\\construire.py

Produit `dist/Murmur/`, un dossier contenant l'executable et ses dependances.

UN DOSSIER PLUTOT QU'UN FICHIER UNIQUE, ET POURQUOI

Un executable « un seul fichier » porte son contenu compresse et le **reextrait
dans un dossier temporaire a chaque lancement**. C'est invisible tant qu'on
lance l'application une fois par jour, et ruineux des qu'on ouvre le tableau de
bord : celui-ci est un second exemplaire du meme executable, qui paie donc
l'extraction une seconde fois.

Mesure, sur trois tours, du clic a la fenetre repondante :

    un fichier    2 200 a 2 370 ms   dont 1 400 a 1 560 avant Python
    un dossier    1 130 a 1 760 ms   dont   310 a  450 avant Python

Le dossier est aussi rapide qu'un lancement depuis les sources. Le prix a
payer est cosmetique : quatre-vingts fichiers a cote de l'executable au lieu
d'un seul, dans un dossier qu'on n'ouvre jamais.

Le moteur (`engine/`, environ 600 Mo de binaires et de modeles) n'est
volontairement PAS embarque : PyInstaller le reextrairait a chaque lancement,
et le modele Whisper se remplace ou se change de taille sans qu'il y ait a
reconstruire l'application. L'executable le cherche a cote de lui.

Arborescence attendue apres construction :

    dist/Murmur/
        Murmur.exe
        _internal/          dependances, page du tableau de bord
        engine/             whisper-server.exe, *.dll, ggml-*.bin
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

#: La racine du projet, un cran au-dessus de `outils/`. Posee sur le chemin de
#: recherche avant tout import du paquet : Python ajoute de lui-meme le dossier
#: du script — `outils/` — et non celui du projet.
RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from murmur import crt  # noqa: E402

NOM = "Murmur"
ICONE = RACINE / "build" / "murmur.ico"

#: Tailles exigees par Windows pour une icone complete : barre des taches,
#: explorateur, raccourcis, ecrans haute densite.
TAILLES_ICONE = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def generer_icone() -> Path:
    """Produit le .ico depuis le symbole de la marque.

    Chaque taille est dessinee separement plutot que reduite depuis la plus
    grande : la declinaison compacte prend le relais sous 40 pixels, la ou les
    deux arcs fins de la version complete se confondent.
    """
    sys.path.insert(0, str(RACINE))
    from murmur import marque

    ICONE.parent.mkdir(parents=True, exist_ok=True)
    images = [marque.dessiner_image(taille, "#ffffff", "#ffffff")
              for taille in TAILLES_ICONE]
    principale, *autres = sorted(images, key=lambda i: -i.size[0])
    principale.save(ICONE, format="ICO",
                    sizes=[(t, t) for t in sorted(TAILLES_ICONE)])
    print(f"  icone   : {ICONE.name} ({len(TAILLES_ICONE)} tailles)")
    return ICONE


#: Modules sans lesquels l'application demarre mais ne dicte pas. PyInstaller
#: n'embarque que ce que TROUVE l'interpreteur qui le lance : construit avec le
#: Python du systeme plutot que celui du projet, il produit sans broncher un
#: executable ampute.
INDISPENSABLES = ("sounddevice", "numpy", "webview", "pystray", "PIL")


def verifier_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("PyInstaller absent. Installe-le avec :\n"
                 "    .venv\\Scripts\\python.exe -m pip install pyinstaller")


def verifier_interpreteur() -> None:
    """L'interpreteur qui construit a-t-il de quoi construire ?

    Panne vecue : construite avec le Python du systeme, l'application se
    lancait normalement — icone, tableau de bord, moteur Whisper chargé — et
    tombait a la premiere dictee, faute de `sounddevice`. L'exception
    emportait le fil des raccourcis, qui rendait toutes les combinaisons en
    mourant : plus aucun raccourci, et rien pour le dire.

    La construction ne doit pas pouvoir reussir a moitie.
    """
    import importlib.util

    manquants = [nom for nom in INDISPENSABLES
                 if importlib.util.find_spec(nom) is None]
    if manquants:
        sys.exit(f"""cet interpreteur n'a pas de quoi construire Murmur.
    interpreteur : {sys.executable}
    manquant     : {", ".join(manquants)}

    Construis avec celui du projet :
        .venv{os.sep}Scripts{os.sep}python.exe outils\\construire.py""")


def verifier_arret() -> None:
    """Refuse de construire par-dessus une application qui tourne.

    La construction commence par effacer `dist/`. Si Murmur tourne, Windows
    garde ses fichiers verrouilles : l'effacement en emporte une partie, puis
    bute. Il reste alors une installation amputee — l'executable est toujours
    la, mais il ne demarre plus. C'est arrive, et le message d'echec ne disait
    rien de la cause.

    Un executable en cours d'execution ne se laisse pas ouvrir en ecriture :
    cela suffit a le savoir, sans dependance supplementaire.
    """
    executable = RACINE / "dist" / NOM / f"{NOM}.exe"
    if not executable.exists():
        return
    try:
        with executable.open("r+b"):
            pass
    except PermissionError:
        sys.exit(f"""{NOM} tourne : ferme-le avant de reconstruire.
    (icone dans la zone de notification, « Quitter »)
    fichier verrouille : {executable}""")


def fournir_le_crt() -> None:
    """Pose la bibliotheque C++ a cote du moteur, si elle manque.

    Mesure sur machine vierge : sans elle, Windows ouvre « Impossible
    d'executer le code, car MSVCP140.dll est introuvable », le moteur ne
    demarre jamais, et l'application echoue trente secondes plus tard sur
    « le serveur n'a pas repondu » — un message qui designe la mauvaise
    cause. Rien dans les journaux ne mene au vrai motif.
    """
    moteur = RACINE / 'engine'
    if not moteur.is_dir():
        return
    poses = crt.fournir(moteur)
    livrees = crt.lire_manifeste(moteur)
    if poses:
        print(f"  runtime : {', '.join(poses)} ajoutee(s) au moteur")
    print(f"  runtime : {len(livrees)} bibliotheque(s) C++ livree(s)")


def construire() -> Path:
    verifier_pyinstaller()
    verifier_interpreteur()
    verifier_arret()
    fournir_le_crt()
    icone = generer_icone()

    # La jonction du moteur est defaite AVANT l'effacement : `rmtree` sur un
    # dossier qui en contient une pourrait la suivre et emporter les 600 Mo
    # qu'elle designe, hors du dossier de construction.
    jonction = RACINE / "dist" / NOM / "engine"
    if jonction.is_dir():
        subprocess.run(["cmd", "/c", "rmdir", str(jonction)],
                       capture_output=True)

    for dossier in (RACINE / "build" / NOM, RACINE / "dist"):
        if dossier.exists():
            try:
                shutil.rmtree(dossier)
            except OSError as erreur:
                sys.exit(f"""impossible d'effacer {dossier} : {erreur}
    un fichier y est verrouille par un programme ouvert. Rien n'a ete reconstruit.""")

    commande = [
        sys.executable, "-m", "PyInstaller",
        "--name", NOM,
        "--onedir",
        "--windowed",              # pas de console au lancement
        "--icon", str(icone),
        "--distpath", str(RACINE / "dist"),
        "--workpath", str(RACINE / "build"),
        "--specpath", str(RACINE / "build"),
        "--noconfirm",
        # La page du tableau de bord : HTML, CSS et JavaScript. PyInstaller
        # n'analyse que les imports Python et ne la verrait pas. La
        # destination reprend le chemin du paquet, ce qui fait tomber les
        # fichiers la ou le module les cherche par `__file__`.
        "--add-data", f"{RACINE / 'murmur' / 'tableau' / 'web'}"
                      f"{os.pathsep}murmur/tableau/web",
        # Les greffons choisis par leur nom a l'execution. Aucun `import`
        # litteral ne les designe : sans declaration ils manquent en silence,
        # et l'absence se voit seulement a l'usage — icone disparue, fenetre
        # qui ne s'ouvre pas.
        "--hidden-import", "pystray._win32",
        # Le tableau de bord est un second exemplaire de cet executable,
        # lance avec « --tableau ».
        "--hidden-import", "murmur.tableau.lancement",
        "--hidden-import", "webview.platforms.winforms",
        # Ecarte ce qui alourdit sans servir. matplotlib et consorts arrivent
        # dans les dependances de numpy et pesent des dizaines de megaoctets.
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "pytest",
        "--exclude-module", "PIL.ImageQt",
        # On empaquete `lanceur.py`, jamais `murmur/__main__.py` : PyInstaller
        # execute son script comme programme principal, ce qui priverait les
        # imports relatifs de leur paquet parent. C'est aussi pourquoi le
        # corps du programme vit dans `murmur/lancement.py` et non dans
        # `murmur/__main__.py` : PyInstaller ecarte de son analyse les modules
        # ainsi nommes a l'interieur d'un paquet, et l'executable tombait au
        # lancement sur « No module named 'murmur.__main__' ».
        str(RACINE / "outils" / "lanceur.py"),
    ]

    print(f"  build   : {NOM}/ (sans console, moteur externe)")
    resultat = subprocess.run(commande, cwd=RACINE)
    if resultat.returncode != 0:
        sys.exit(f"echec de la construction (code {resultat.returncode})")

    executable = RACINE / "dist" / NOM / f"{NOM}.exe"
    if not executable.exists():
        sys.exit(f"executable introuvable : {executable}")
    verifier_contenu(executable)
    return executable


def verifier_contenu(executable: Path) -> None:
    """L'executable embarque-t-il de quoi dicter ?

    Second garde-fou, apres `verifier_interpreteur` : celui-ci verifie ce
    qui est SORTI, et non ce qui etait disponible pour entrer. On ne peut
    pas le lire dans `_internal` — les modules en pur Python vivent dans
    l'archive embarquee dans l'executable, invisible de l'exterieur. On
    le demande donc a l'executable lui-meme.
    """
    controle = subprocess.run([str(executable), '--verifier'],
                              capture_output=True, text=True, timeout=120)
    if controle.returncode != 0:
        detail = (controle.stderr or controle.stdout).strip()
        sys.exit(f"""construction incomplete : l'executable ne peut pas dicter.
    {detail}
Il se lancerait normalement, et tomberait a la premiere dictee.""")


def rattacher_moteur(dossier: Path, copier: bool = False) -> str:
    """Rend `engine/` accessible a cote de l'executable.

    Par defaut une jonction NTFS plutot qu'une copie : le moteur pese 600 Mo,
    et le dupliquer a chaque construction remplirait le disque pour rien. La
    jonction ne demande aucun privilege particulier.

    `--copier` produit en revanche un dossier autonome, deplacable sur une
    autre machine.
    """
    source, cible = RACINE / "engine", dossier / "engine"

    if not source.exists():
        return f"engine/ introuvable dans {RACINE} — a mettre en place a la main"

    if cible.exists():
        if (cible / "whisper-server.exe").exists():
            return "moteur deja en place"
        # Jonction cassee : la refaire plutot que la laisser mentir.
        subprocess.run(["cmd", "/c", "rmdir", str(cible)],
                       capture_output=True)

    if copier:
        print("  moteur  : copie d'environ 600 Mo, patiente...")
        shutil.copytree(source, cible)
        return f"moteur copie dans {cible}"

    # Chemins absolus : mklink resout le relatif depuis le repertoire courant,
    # pas depuis l'emplacement du lien — une erreur qui cree une jonction
    # pointant dans le vide.
    resultat = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(cible.resolve()),
         str(source.resolve())], capture_output=True, text=True)
    if resultat.returncode != 0 or not (cible / "whisper-server.exe").exists():
        return (f"jonction impossible ({resultat.stderr.strip()}) — copie "
                f"engine/ a la main dans {dossier}")
    return f"jonction creee : {cible} -> {source}"


def poser_raccourci(executable: Path) -> str:
    sys.path.insert(0, str(RACINE))
    from murmur import systeme

    try:
        lien = systeme.creer_raccourci(executable)
    except (OSError, FileNotFoundError) as exc:
        return f"raccourci impossible : {exc}"
    return f"raccourci cree : {lien}"


def main(copier: bool = False, raccourci: bool = True) -> int:
    print("=" * 62)
    print(f"  Construction de {NOM}.exe")
    print("=" * 62)

    executable = construire()
    dossier = executable.parent
    taille = sum(f.stat().st_size for f in dossier.rglob("*")
                 if f.is_file()) / 1e6
    etat_moteur = rattacher_moteur(executable.parent, copier=copier)
    etat_lien = poser_raccourci(executable) if raccourci else "non demande"

    print()
    print("=" * 62)
    print(f"  OK : {dossier}  ({taille:.0f} Mo)")
    print("=" * 62)
    print(f"  moteur    : {etat_moteur}")
    print(f"  menu      : {etat_lien}")
    print()
    print("  Murmur apparait dans le menu Demarrer. Clic droit sur l'entree")
    print("  pour l'epingler au menu ou a la barre des taches.")
    if not copier:
        print()
        print("  Pour un dossier autonome, deplacable sur une autre machine :")
        print("      .venv\\Scripts\\python.exe outils\\construire.py --copier")
    return 0


if __name__ == "__main__":
    sys.exit(main(copier="--copier" in sys.argv,
                  raccourci="--sans-raccourci" not in sys.argv))

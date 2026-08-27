r"""Peuple un jeu de donnees de demonstration, pour les captures d'ecran.

    .venv\Scripts\python.exe outils_demo.py

Ecrit dans un dossier a part — JAMAIS dans les donnees reelles de
l'utilisateur, qui contiennent ses vraies dictees. Le dossier est designe par
la variable d'environnement que l'application lit deja pour les tests.

Le tirage est **deterministe** : meme graine, memes donnees, memes captures.
Une capture qui change a chaque execution ne se compare a rien.

Les donnees ne sont pas uniformes, et c'est voulu : une activite reguliere
donnerait un calendrier sans relief et des barres d'usage toutes egales, ce
qui ne montre rien de ce que la page sait faire. On imite donc un usage reel —
des jours creux, des semaines chargees, une nette preference pour une
application, une pointe le mois dernier.
"""

from __future__ import annotations

import os
import random
import shutil
import sys
import tempfile
from datetime import date, datetime, time as heure_du_jour, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

#: Dossier des donnees de demonstration. A cote du projet et non dans
#: %APPDATA% : il se supprime d'un seul geste et ne se confond avec rien.
DOSSIER = RACINE / "captures" / "donnees"

GRAINE = 20260823

#: Jours couverts. De quoi remplir le calendrier des dix-huit semaines
#: affichees, avec un peu d'histoire derriere pour les fleches.
JOURS = 170

#: Ou l'on dicte, et avec quel poids. La somme n'a pas a faire cent : les
#: parts sont tirees de la.
CIBLES = [
    ("Claude.exe — Claude", 46),
    ("brave.exe — Brave", 21),
    ("Code.exe — Visual Studio Code", 14),
    ("WindowsTerminal.exe — Terminal", 8),
    ("olk.exe — Outlook", 6),
    ("Notion.exe — Notion", 3),
    ("Discord.exe — Discord", 2),
]

#: Termes du dictionnaire, avec les variantes que le moteur produisait.
TERMES = [
    ("Murmur", ["murmure", "mur mur"], 34),
    ("Ollama", ["olama", "au lama"], 21),
    ("whisper.cpp", ["whisper c plus plus", "whisper cpp"], 17),
    ("Vulkan", ["vulcain", "vulkane"], 12),
    ("PyInstaller", ["py installer", "pie installer"], 9),
    ("WebView2", ["web view 2", "webview deux"], 8),
    ("SQLite", ["sequel light", "s q lite"], 7),
    ("Tkinter", ["t kinter", "tee kinter"], 5),
    ("Cloudflare", ["cloude flare"], 4),
    ("Supabase", ["super base", "soupa base"], 3),
    ("Kubernetes", ["coubernetes", "coubère nettes"], 2),
]

#: Phrases de demonstration. Volontairement de longueurs tres inegales : la
#: page ajuste la hauteur de chaque ligne au texte, ce qu'un corpus regulier
#: ne montrerait pas.
PHRASES = [
    "Ok.",
    "Merci, c'est parfait.",
    "Relance le build s'il te plaît.",
    "Tu peux me faire un résumé de ce fichier ?",
    "Ajoute un test pour le cas où le presse-papier est vide.",
    "Je pense que le problème vient du fil de l'icône, pas du canal lui-même.",
    "Peux-tu vérifier que la fenêtre garde bien ses poignées de "
    "redimensionnement après le retrait du bandeau ?",
    "Non, garde la version précédente. Celle-ci ajoute une dépendance pour "
    "un gain que personne ne mesurera.",
    "Il faudrait que le calendrier prenne toute la largeur de la carte, avec "
    "des cases carrées et un écart plus serré. Là il reste un grand vide en "
    "bas de l'encart.",
    "Écris-moi une fonction qui rééchantillonne un signal de 48 kHz vers "
    "16 kHz, avec un filtre anti-repliement — sans lui les fréquences hautes "
    "se replient dans la bande de la parole.",
    "Le raccourci ne répond plus depuis que j'ai changé de casque.",
    "Commit et push sur la branche courante.",
    "Rappelle-moi pourquoi on a choisi WASAPI plutôt que MME ?",
    "Parfait, on peut passer à la suite.",
    "Ajoute une entrée dans le suivi, avec la mesure et la cause.",
    "Le mode sombre ne s'applique pas quand le thème est sur automatique.",
    "Fais-moi une passe de relecture sur les commentaires du module audio, "
    "je trouve qu'ils expliquent le comment plutôt que le pourquoi.",
    "Deux secondes d'attente à chaque ouverture, c'est le pare-feu qui avale "
    "les paquets au lieu de refuser la connexion.",
    "Non, l'inverse : c'est la largeur qui doit commander la hauteur.",
    "Génial, merci.",
]


def cadence(jour: date, tirage: random.Random) -> int:
    """Nombre de dictees pour ce jour.

    Le week-end est creux, et une semaine sur cinq environ est vide : c'est ce
    qui donne au calendrier son relief. Le dernier mois est plus dense — on
    prend l'habitude.
    """
    if jour == date.today():
        # Le jour meme n'est jamais vide : la page annoncerait « 0 mot
        # aujourd'hui » et la premiere ligne de l'historique daterait de
        # l'avant-veille — une capture qui donne l'application pour
        # abandonnee.
        return tirage.randint(4, 9)
    if tirage.random() < 0.16:            # jour sans, meme en semaine
        return 0
    if jour.weekday() >= 5:
        return tirage.choice([0, 0, 1, 2, 3])

    recent = (date.today() - jour).days < 35
    haut = 22 if recent else 14
    return tirage.randint(3, haut)


def peupler(dossier: Path) -> dict:
    """Ecrit la base et le lexique. Renvoie de quoi rendre compte."""
    os.environ["MURMUR_DONNEES"] = str(dossier)

    from murmur import lexicon, store          # apres la variable, pas avant

    tirage = random.Random(GRAINE)
    cibles = [c for c, _poids in CIBLES]
    poids = [p for _c, p in CIBLES]

    total_mots = 0
    total_dictees = 0
    # Les dernieres phrases servies, pour ne pas en repeter une a deux lignes
    # d'intervalle : la page les afficherait cote a cote, et une liste qui se
    # repete se lit comme une donnee bidon plutot que comme un historique.
    recentes: list[str] = []
    with store.Historique() as base:
        for recul in range(JOURS, -1, -1):
            jour = date.today() - timedelta(days=recul)
            for _ in range(cadence(jour, tirage)):
                choix = [p for p in PHRASES if p not in recentes]
                texte = tirage.choice(choix or PHRASES)
                recentes = (recentes + [texte])[-8:]
                mots = len(texte.split())
                # Une cadence de parole plausible : entre 130 et 190 mots par
                # minute, plus une seconde d'amorce.
                duree = (mots / tirage.uniform(130, 190)) * 60_000 + 1_000
                moment = datetime.combine(jour, heure_du_jour(
                    tirage.randint(8, 22), tirage.randint(0, 59),
                    tirage.randint(0, 59)))
                base.ajouter(
                    texte,
                    duree_audio_ms=duree,
                    transcription_ms=duree * tirage.uniform(0.05, 0.12),
                    latence_ms=tirage.uniform(320, 480),
                    cible=tirage.choices(cibles, weights=poids)[0],
                    horodatage=moment)
                total_mots += mots
                total_dictees += 1

        for avant, apres, nombre in [(v, terme, usages)
                                     for terme, variantes, usages in TERMES
                                     for v in variantes[:1]
                                     for usages in [usages]]:
            for _ in range(min(nombre, 6)):   # un echantillon suffit
                base.ajouter_correction(avant, apres)

    lexique = lexicon.Lexique()
    for terme, variantes, usages in TERMES:
        lexique.ajouter(terme, variantes, epingle=(terme == "Murmur"))
        lexique.trouver(terme).usages = usages
    lexique.sauvegarder()

    return {"dictees": total_dictees, "mots": total_mots,
            "termes": len(TERMES)}


def main() -> int:
    if DOSSIER.exists():
        shutil.rmtree(DOSSIER, ignore_errors=True)
    DOSSIER.mkdir(parents=True, exist_ok=True)

    resume = peupler(DOSSIER)
    print(f"  donnees : {DOSSIER}")
    print(f"  {resume['dictees']} dictees, {resume['mots']} mots, "
          f"{resume['termes']} termes")
    print()
    print("  Pour ouvrir le tableau de bord sur ces donnees :")
    print(f"      set MURMUR_DONNEES={DOSSIER}")
    print("      .venv\\Scripts\\python.exe -m murmur.tableau")
    return 0


if __name__ == "__main__":
    sys.exit(main())

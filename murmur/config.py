"""Configuration et resolution des chemins.

Regle structurante : aucun chemin absolu n'est ecrit en dur. Tout se resout
soit relativement au paquet (`Path(__file__)`), soit depuis l'environnement
(`%APPDATA%`). L'application doit survivre a un changement de disque ou de
machine sans qu'une seule ligne soit modifiee.

Deux racines distinctes, a ne pas confondre :

  RACINE   le projet lui-meme (code, moteur, modeles) — en lecture seule
           a l'usage, deplacable avec le dossier.
  donnees  les fichiers produits par l'utilisateur (config, lexique,
           historique, journaux) — dans %APPDATA%, ils survivent a une
           reinstallation du projet.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Chemins
# --------------------------------------------------------------------------


def _racine() -> Path:
    """Dossier de reference du projet, en source comme en executable.

    Dans un executable PyInstaller, `__file__` pointe vers le dossier
    temporaire d'extraction : les 600 Mo du moteur n'y sont pas — ils restent
    a cote de l'executable, ou l'utilisateur peut les remplacer sans
    reconstruire quoi que ce soit. On se repere donc sur l'executable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # murmur/config.py -> murmur/ -> racine du projet
    return Path(__file__).resolve().parent.parent


RACINE = _racine()
MOTEUR = RACINE / "engine"

#: Vrai lorsque l'application tourne depuis un executable empaquete.
EMPAQUETE = bool(getattr(sys, "frozen", False))

#: Variable d'environnement permettant de rediriger les donnees.
#: Utilisee par les tests pour ne pas toucher au vrai %APPDATA%.
VAR_DONNEES = "MURMUR_DONNEES"


def dossier_donnees() -> Path:
    """Dossier des donnees utilisateur, cree si necessaire."""
    surcharge = os.getenv(VAR_DONNEES)
    if surcharge:
        base = Path(surcharge)
    else:
        appdata = os.getenv("APPDATA")
        base = (Path(appdata) if appdata
                else Path.home() / "AppData" / "Roaming") / "Murmur"
    base.mkdir(parents=True, exist_ok=True)
    return base


def fichier_config() -> Path:
    return dossier_donnees() / "config.json"


def fichier_lexique() -> Path:
    return dossier_donnees() / "lexique.json"


def fichier_historique() -> Path:
    return dossier_donnees() / "historique.sqlite3"


def dossier_journaux() -> Path:
    chemin = dossier_donnees() / "logs"
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


# --------------------------------------------------------------------------
# Valeurs par defaut
# --------------------------------------------------------------------------

DEFAUTS: dict[str, Any] = {
    "langue": "fr",

    "raccourcis": {
        # Ctrl+Alt+N est deja pris par l'app Notes : ne pas le reutiliser.
        "maintien": "ctrl+alt+d",
        "bascule": "ctrl+alt+shift+d",
        # Apprentissage : corriger le texte ou l'on travaille, tout copier,
        # puis appuyer ici. Murmur ne lit le presse-papier qu'a ce moment.
        "apprendre": "ctrl+alt+c",
        # Garde-fou du mode bascule : sans lui, un micro reste ouvert.
        "arret_auto_silence_s": 3.0,
    },

    "moteur": {
        "modele": "ggml-large-v3-turbo-q5_0.bin",
        "modele_vad": "ggml-silero-v5.1.2.bin",
        "hote": "127.0.0.1",
        "port": 8642,
        # Quelle carte graphique. « auto » choisit la mieux placee ; un
        # entier force un numero d'enumeration.
        #
        # Le numero seul ne suffit pas : l'ordre d'enumeration n'est pas
        # stable. Releve sur cette machine, meme binaire, a quelques minutes
        # d'intervalle, la carte dediee etait tantot 0 tantot 1 — et prendre
        # zero revenait a tirer au sort entre elle et le circuit integre.
        "device_vulkan": "auto",
        # Nom de la carte retenue, ecrit par l'application. C'est un nom et
        # non un numero, precisement parce que le numero ne veut rien dire
        # d'une session a l'autre.
        "carte_vulkan": "",
        # Repli sur le processeur si le moteur ne demarre pas avec la carte
        # graphique. Mesure sur ce poste : 250 ms avec la carte, 9 400 ms sans,
        # pour huit secondes de parole. C'est un secours, pas un mode d'usage —
        # mais mieux vaut une dictee lente qu'une application qui ne demarre
        # pas du tout.
        "repli_processeur": True,
        "demarrage_timeout_s": 30.0,
        # Un moteur qui tombe est relance, mais pas indefiniment : au-dela,
        # c'est une panne de fond et s'acharner masquerait le probleme.
        "max_redemarrages": 3,
        "fenetre_redemarrages_s": 300.0,
        "surveillance_s": 2.0,
    },

    "vad": {
        "actif": True,
        "seuil": 0.5,
        "min_parole_ms": 250,
        "min_silence_ms": 100,
        "suppress_nst": True,
    },

    "lexique": {
        "actif": True,
        # Nombre de dictees recentes comparees au presse-papier lors d'un
        # apprentissage. Au-dela, on risque de rapprocher une correction d'une
        # dictee ancienne qui lui ressemble par hasard.
        "dictees_comparees": 20,
        # Copier le texte de l'application avant de l'analyser, plutot que
        # d'exiger un Ctrl+C prealable. Envoie une frappe a l'application au
        # premier plan : a couper si elle en fait un usage inattendu.
        "copier_avant_analyse": True,
    },

    "interface": {
        # "auto" suit le reglage de Windows, "clair" et "sombre" le forcent.
        "theme": "auto",
        # Position de l'indicateur de dictee : "bas", "haut", "curseur".
        "indicateur_position": "bas",
        "indicateur_actif": True,
        # Barre laterale repliee sur ses pictogrammes. Retenu d'une session a
        # l'autre : c'est une preference d'espace, pas un geste a refaire.
        "barre_repliee": False,
        # Langue de l'interface : "fr" ou "en". L'anglais par defaut, pour le
        # vocabulaire de reference ; le francais reste a un clic.
        "langue": "en",
    },

    "audio": {
        # 16 kHz mono : le format attendu par whisper, capture nativement pour
        # eviter tout reechantillonnage.
        "taux": 16000,
        # None = peripherique d'entree par defaut du systeme.
        "peripherique": None,
        # Garde-fou du mode bascule : borne une dictee qu'on aurait oublie
        # d'arreter, plutot que de remplir la memoire indefiniment.
        "duree_max_s": 120.0,
    },

    "garde": {
        # Mesure en T0.3 : le VAD natif suffit sur les cas testes. Ces deux
        # garde-fous restent en defense supplementaire et evitent surtout un
        # aller-retour inutile vers le moteur.
        "duree_min_ms": 300,
        "rms_min": 0.005,
        # Volontairement vide : une phrase legitime inscrite ici serait
        # censuree dans toutes les dictees futures. Ne se remplit que sur
        # hallucination reellement observee.
        "liste_noire": [],
    },

    "injection": {
        # Tranche en T0.1 : le presse-papier passe 5/5 et echappe aux
        # autocorrections des applications, contrairement a la frappe simulee.
        "strategie": "presse_papier",
        "restaurer_presse_papier": True,
        "delai_restauration_ms": 250,
        # 16 ms/caractere mesures : acceptable en dernier recours seulement.
        "frappe_pause_ms": 15,
    },

    "nettoyage_ia": {
        "actif": False,
        "modele": "qwen3",
        "hote": "127.0.0.1",
        "port": 11434,
        "timeout_s": 10.0,
    },
}


class ErreurConfig(Exception):
    """Configuration illisible ou invalide."""


def _fusionner(defauts: dict, charges: dict) -> dict:
    """Complete les valeurs chargees par les defauts, recursivement.

    Une cle absente du fichier prend sa valeur par defaut : ajouter une option
    dans une version ulterieure ne casse pas les configurations existantes.
    """
    resultat = copy.deepcopy(defauts)
    for cle, valeur in charges.items():
        if (cle in resultat and isinstance(resultat[cle], dict)
                and isinstance(valeur, dict)):
            resultat[cle] = _fusionner(resultat[cle], valeur)
        else:
            resultat[cle] = valeur
    return resultat


def _valider(valeurs: dict) -> None:
    """Verifie les contraintes qui feraient echouer l'application plus tard.

    Mieux vaut une erreur explicite au demarrage qu'un comportement incoherent
    en pleine dictee.
    """
    port = valeurs["moteur"]["port"]
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ErreurConfig(f"moteur.port invalide : {port!r} (entier 1-65535 attendu)")

    if valeurs["langue"] not in ("fr", "en", "auto"):
        raise ErreurConfig(
            f"langue invalide : {valeurs['langue']!r} (fr, en ou auto attendu)")

    if valeurs["injection"]["strategie"] not in ("presse_papier", "frappe"):
        raise ErreurConfig(
            f"injection.strategie invalide : "
            f"{valeurs['injection']['strategie']!r} "
            f"(presse_papier ou frappe attendu)")

    seuil = valeurs["vad"]["seuil"]
    if not isinstance(seuil, (int, float)) or not (0.0 <= seuil <= 1.0):
        raise ErreurConfig(f"vad.seuil invalide : {seuil!r} (0.0 a 1.0 attendu)")

    duree = valeurs["garde"]["duree_min_ms"]
    if not isinstance(duree, int) or duree < 0:
        raise ErreurConfig(
            f"garde.duree_min_ms invalide : {duree!r} (entier positif attendu)")

    if not isinstance(valeurs["garde"]["liste_noire"], list):
        raise ErreurConfig("garde.liste_noire doit etre une liste")

    taux = valeurs["audio"]["taux"]
    if taux != 16000:
        raise ErreurConfig(
            f"audio.taux invalide : {taux!r}. Whisper attend 16000 Hz ; une "
            f"autre valeur imposerait un reechantillonnage et degraderait la "
            f"transcription.")

    duree_max = valeurs["audio"]["duree_max_s"]
    if not isinstance(duree_max, (int, float)) or duree_max <= 0:
        raise ErreurConfig(
            f"audio.duree_max_s invalide : {duree_max!r} (nombre positif attendu)")

    theme = valeurs["interface"]["theme"]
    if theme not in ("auto", "clair", "sombre"):
        raise ErreurConfig(
            f"interface.theme invalide : {theme!r} (auto, clair ou sombre attendu)")

    position = valeurs["interface"]["indicateur_position"]
    if position not in ("bas", "haut", "curseur"):
        raise ErreurConfig(
            f"interface.indicateur_position invalide : {position!r} "
            f"(bas, haut ou curseur attendu)")

    langue = valeurs["interface"]["langue"]
    if langue not in ("fr", "en"):
        raise ErreurConfig(
            f"interface.langue invalide : {langue!r} (fr ou en attendu)")


class Config:
    """Acces aux reglages, par chemin pointe : cfg["moteur.port"]."""

    def __init__(self, valeurs: dict):
        self._valeurs = valeurs

    def __getitem__(self, chemin: str) -> Any:
        courant: Any = self._valeurs
        for morceau in chemin.split("."):
            if not isinstance(courant, dict) or morceau not in courant:
                raise KeyError(f"reglage inconnu : {chemin}")
            courant = courant[morceau]
        return courant

    def get(self, chemin: str, defaut: Any = None) -> Any:
        try:
            return self[chemin]
        except KeyError:
            return defaut

    def definir(self, chemin: str, valeur: Any) -> None:
        morceaux = chemin.split(".")
        courant = self._valeurs
        for morceau in morceaux[:-1]:
            courant = courant.setdefault(morceau, {})
        courant[morceaux[-1]] = valeur

    @property
    def valeurs(self) -> dict:
        return copy.deepcopy(self._valeurs)

    def recharger(self) -> None:
        """Relit le fichier **dans cet objet**.

        Sur place, et non en rendant une nouvelle configuration : l'objet est
        deja detenu par l'application, l'indicateur, le theme et l'icone. En
        remplacer un seul laisserait tous les autres sur les anciennes
        valeurs.
        """
        self._valeurs = charger().valeurs

    # -- chemins derives, pour ne pas eparpiller la logique ----------------

    @property
    def chemin_modele(self) -> Path:
        """Ou est le modele de transcription.

        Deux emplacements possibles, et l'ordre compte. A cote du moteur
        d'abord : c'est la que le poste de developpement garde le sien, et un
        modele pose a la main doit primer. Dans les donnees ensuite : c'est la
        qu'atterrit celui qui est telecharge au premier lancement, pour qu'une
        mise a jour de l'application n'emporte pas 574 Mo avec elle.

        Le chemin rendu quand le modele est introuvable est celui du moteur :
        c'est celui qu'il faut montrer dans un message d'erreur.
        """
        nom = self["moteur.modele"]
        a_cote = MOTEUR / nom
        if a_cote.exists():
            return a_cote
        telecharge = dossier_donnees() / "modeles" / nom
        return telecharge if telecharge.exists() else a_cote

    @property
    def chemin_modele_vad(self) -> Path:
        return MOTEUR / self["moteur.modele_vad"]

    @property
    def chemin_serveur(self) -> Path:
        return MOTEUR / "whisper-server.exe"

    @property
    def url_moteur(self) -> str:
        return f"http://{self['moteur.hote']}:{self['moteur.port']}"

    def sauvegarder(self) -> Path:
        cible = fichier_config()
        cible.write_text(
            json.dumps(self._valeurs, indent=2, ensure_ascii=False),
            encoding="utf-8")
        return cible


def charger() -> Config:
    """Charge la configuration, en la creant au premier lancement."""
    cible = fichier_config()

    if not cible.exists():
        config = Config(copy.deepcopy(DEFAUTS))
        config.sauvegarder()
        return config

    try:
        brut = json.loads(cible.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ErreurConfig(
            f"{cible} est illisible (JSON invalide ligne {exc.lineno}) : {exc.msg}. "
            f"Corrige le fichier ou supprime-le pour repartir des defauts."
        ) from exc

    if not isinstance(brut, dict):
        raise ErreurConfig(f"{cible} doit contenir un objet JSON, pas "
                           f"{type(brut).__name__}")

    valeurs = _fusionner(DEFAUTS, brut)
    _reprendre_le_choix_de_carte(valeurs)
    _valider(valeurs)
    return Config(valeurs)


#: Ancienne valeur par defaut de `moteur.device_vulkan`, ecrite dans les
#: configurations existantes avant que le choix devienne automatique.
ANCIEN_DEFAUT_VULKAN = 0


def _reprendre_le_choix_de_carte(valeurs: dict) -> None:
    """Rend son automatisme au choix de la carte graphique.

    Les configurations ecrites avant portent `device_vulkan: 0` — non parce que
    quelqu'un l'a choisi, mais parce que c'etait le defaut. Or ce zero designe
    une carte differente d'un demarrage a l'autre : le laisser en place
    reviendrait a garder le tirage au sort qu'on vient de supprimer.

    Un numero pose a la main, lui, est respecte : seule l'ancienne valeur par
    defaut est reprise, et seulement si aucune carte n'a encore ete retenue.
    """
    moteur = valeurs.get("moteur")
    if not isinstance(moteur, dict):
        return
    if (moteur.get("device_vulkan") == ANCIEN_DEFAUT_VULKAN
            and not moteur.get("carte_vulkan")):
        moteur["device_vulkan"] = "auto"

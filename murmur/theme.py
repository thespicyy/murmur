"""Palettes claire et sombre, alignees sur le reglage de Windows.

Deux palettes completes, une seule regle : aucune couleur n'est ecrite en dur
ailleurs dans le code. Toute l'interface passe par ces jetons, faute de quoi
la bascule de theme laisserait des ilots incoherents.

Les couleurs d'etat (ecoute, transcription, erreur) sont volontairement
communes aux deux palettes : elles doivent rester reconnaissables d'un coup
d'oeil, et un vert qui change de teinte selon le fond se lit moins vite.
"""

from __future__ import annotations

import winreg
from dataclasses import dataclass

CLE_PERSONNALISATION = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


@dataclass(frozen=True)
class Palette:
    nom: str

    fond: str          # la fenetre elle-meme, visible en bande autour
    surface: str       # le panneau central et la barre des reglages
    surface_haute: str  # survol dans la barre laterale
    pilule: str        # onglet actif de la barre laterale
    carte: str         # cartes posees dans le panneau
    carte_survol: str
    bordure: str       # filets : champs, selecteur segmente

    texte: str
    texte_doux: str    # libelles secondaires, horodatages
    texte_faible: str  # elements desactives

    accent: str        # actions principales
    accent_texte: str  # texte pose sur l'accent

    # Etats de la dictee — identiques dans les deux themes.
    repos: str = "#8a8a94"
    ecoute: str = "#3fb950"
    transcription: str = "#d29922"
    insertion: str = "#4493f8"
    erreur: str = "#f85149"


#: Palette claire relevee sur Wispr Flow, a la demande de l'utilisateur :
#:
#:   #f5f4f0   le fond de la fenetre, blanc casse chaud
#:   #fcfcfb   le panneau central, presque blanc
#:   #312d37   le texte, un gris violace plutot qu'un noir neutre
#:
#: Les encarts poses dans le panneau reprennent le fond de la fenetre : c'est
#: ce qui donne l'etagement panneau clair / carte plus sourde, sans jamais
#: recourir a un filet.
#:
#: La palette sombre est batie sur la meme teinte violacee, inversee : un
#: sombre neutre a cote d'un clair violace donnerait deux applications
#: differentes selon le reglage de Windows.
SOMBRE = Palette(
    nom="sombre",
    fond="#15131a",
    surface="#1c1a22",
    surface_haute="#24212c",
    pilule="#2c2936",
    carte="#24212c",
    carte_survol="#2c2936",
    bordure="#332f3c",
    texte="#f5f4f0",
    texte_doux="#a9a3b3",
    texte_faible="#726d7d",
    accent="#f5f4f0",
    accent_texte="#312d37",
)

CLAIR = Palette(
    nom="clair",
    fond="#f5f4f0",
    surface="#fcfcfb",
    surface_haute="#efeee9",
    pilule="#e8e6e0",
    carte="#f5f4f0",
    carte_survol="#efeee9",
    bordure="#e6e4de",
    texte="#312d37",
    texte_doux="#6b6673",
    texte_faible="#9b96a3",
    accent="#312d37",
    accent_texte="#fcfcfb",
)

#: Police retenue pour toute l'interface, avec repli sur une police systeme.
POLICE = "Inter"
POLICE_REPLI = "Segoe UI"


def windows_en_clair() -> bool:
    """Lit le reglage d'apparence des applications dans Windows.

    En cas de doute on renvoie le mode clair : c'est le defaut de Windows, et
    une interface claire affichee par erreur sur un bureau sombre reste
    lisible, l'inverse l'est moins.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            CLE_PERSONNALISATION) as cle:
            valeur, _ = winreg.QueryValueEx(cle, "AppsUseLightTheme")
            return bool(valeur)
    except OSError:
        return True


def resoudre(preference: str) -> Palette:
    """Palette effective pour une preference « auto », « clair » ou « sombre »."""
    if preference == "clair":
        return CLAIR
    if preference == "sombre":
        return SOMBRE
    return CLAIR if windows_en_clair() else SOMBRE


def police_disponible(racine) -> str:
    """Renvoie POLICE si elle est installee, sinon le repli.

    Demander une police absente ne leve pas d'erreur avec Tk : il substitue
    silencieusement une police par defaut, souvent laide. Mieux vaut choisir
    explicitement.
    """
    try:
        from tkinter import font
        familles = set(font.families(racine))
        return POLICE if POLICE in familles else POLICE_REPLI
    except Exception:
        return POLICE_REPLI


class Theme:
    """Palette courante, relisible a la demande."""

    def __init__(self, conf):
        self.conf = conf
        self._palette = resoudre(conf["interface.theme"])

    @property
    def palette(self) -> Palette:
        return self._palette

    def rafraichir(self) -> bool:
        """Relit le reglage systeme. Vrai si la palette a change."""
        nouvelle = resoudre(self.conf["interface.theme"])
        if nouvelle.nom != self._palette.nom:
            self._palette = nouvelle
            return True
        return False

    def __getattr__(self, nom: str) -> str:
        # Acces direct aux jetons : theme.fond plutot que theme.palette.fond.
        #
        # Les attributs prives sont exclus : sans cette garde, un acces a
        # _palette avant son affectation rappellerait __getattr__ en boucle
        # jusqu'au debordement de pile, en masquant l'erreur reelle.
        if nom.startswith("_"):
            raise AttributeError(nom)
        try:
            return getattr(self._palette, nom)
        except AttributeError as exc:
            raise AttributeError(f"jeton de theme inconnu : {nom}") from exc

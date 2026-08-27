"""Garde-fous contre les dictees fantomes.

Whisper invente du texte quand on lui donne du silence. Mesure en T0.3 : sur
trois echantillons muets, trois hallucinations — le silence du micro produit
« Sous-titrage Societe Radio-Canada ». Avec le VAD Silero et `--suppress-nst`,
zero sur trois. La protection principale vit donc dans le moteur.

Ce module apporte les deux couches restantes :

  en amont   duree minimale et energie du signal. Rejette l'appui accidentel
             AVANT tout envoi — gratuit, et evite un aller-retour inutile.
  en aval    liste noire de phrases d'hallucination avérées. Dernier filet.

La liste noire est vide par defaut, et c'est deliberé. Une phrase legitime
qui y entrerait serait censuree dans toutes les dictees futures — le premier
essai de T0.3 avait justement failli y inscrire « mes notes dans Obsidian »,
qui etait une transcription parfaitement correcte.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from . import audio, config as configuration

PONCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
ESPACES = re.compile(r"\s+")

#: En dessous, il ne s'agit plus de silence mais d'absence de signal : micro
#: coupe, casque sans fil endormi, peripherique disparu. Une piece calme
#: mesure autour de 0.001 ; un micro muet descend a 0.00002.
SEUIL_MICRO_MUET = 0.0002


def normaliser(texte: str) -> str:
    """Forme comparable : sans casse, sans accents, sans ponctuation.

    Permet de reconnaitre une hallucination quelles que soient ses variations
    de ponctuation ou de capitalisation d'une fois sur l'autre.
    """
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte.lower())
        if unicodedata.category(c) != "Mn")
    return ESPACES.sub(" ", PONCTUATION.sub(" ", sans_accents)).strip()


@dataclass(frozen=True)
class Verdict:
    """Resultat d'un controle : accepte, ou rejete avec son motif."""

    accepte: bool
    motif: str | None = None

    @classmethod
    def ok(cls) -> Verdict:
        return cls(accepte=True)

    @classmethod
    def refus(cls, motif: str) -> Verdict:
        return cls(accepte=False, motif=motif)


class Garde:
    def __init__(self, conf: configuration.Config):
        self.conf = conf

    # -- en amont ----------------------------------------------------------

    def controler_capture(self, capture: audio.Capture) -> Verdict:
        """Decide si la capture merite d'etre transcrite."""
        if capture.vide:
            return Verdict.refus("aucun son capture")

        duree_min = self.conf["garde.duree_min_ms"]
        if capture.duree_ms < duree_min:
            return Verdict.refus(
                f"trop court ({capture.duree_ms:.0f} ms, minimum {duree_min} ms)")

        # Un micro coupe ou endormi ne rend pas du silence mais du VIDE : le
        # niveau tombe deux ordres de grandeur sous celui d'une piece calme.
        # Les confondre envoyait l'utilisateur parler plus fort dans un micro
        # eteint.
        if capture.rms < SEUIL_MICRO_MUET:
            return Verdict.refus(
                "aucun signal du micro — verifie qu'il est allume et "
                "que la sourdine est desactivee")

        rms_min = self.conf["garde.rms_min"]
        if capture.rms < rms_min:
            return Verdict.refus(
                f"trop faible (niveau {capture.rms:.4f}, minimum {rms_min}) — "
                f"parle plus pres du micro")

        return Verdict.ok()

    # -- en aval -----------------------------------------------------------

    def controler_texte(self, texte: str) -> Verdict:
        """Ecarte les hallucinations connues.

        La comparaison porte sur le texte ENTIER, pas sur une sous-chaine :
        une dictee legitime qui contiendrait par hasard une tournure listee ne
        doit jamais etre censuree.
        """
        if not texte.strip():
            return Verdict.refus("transcription vide")

        forme = normaliser(texte)
        if not forme:
            return Verdict.refus("transcription sans contenu")

        for suspecte in self.conf["garde.liste_noire"]:
            if forme == normaliser(suspecte):
                self._journaliser_blocage(texte)
                return Verdict.refus(f"hallucination connue : {texte!r}")

        return Verdict.ok()

    def _journaliser_blocage(self, texte: str) -> None:
        """Trace ce qui a ete bloque, pour pouvoir reexaminer la liste.

        Une liste noire qu'on ne peut pas auditer finit par censurer sans
        qu'on sache quoi.
        """
        try:
            chemin = configuration.dossier_journaux() / "bloques.log"
            horodatage = time.strftime("%Y-%m-%d %H:%M:%S")
            with chemin.open("a", encoding="utf-8") as fichier:
                fichier.write(f"{horodatage}\t{texte}\n")
        except OSError:
            pass  # journaliser ne doit jamais faire echouer une dictee

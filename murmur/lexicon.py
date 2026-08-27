"""Lexique personnel : vocabulaire que le modele doit reconnaitre.

Deux mecanismes complementaires, mesures en T0.2 sur dix termes de jargon :

  prompt de conditionnement   5/10 termes corrects sans, 8/10 avec. Agit en
                              amont, sur le decodage lui-meme.
  table de remplacement       rattrape ce que le prompt ne corrige pas. Agit
                              en aval, sur le texte produit.

Le prompt n'est pas monotone : `Grafana` passait SANS prompt et echouait AVEC.
Ajouter un terme peut donc en degrader un autre. C'est pourquoi la table de
remplacement n'est pas un complement facultatif mais le filet indispensable, et
pourquoi toute modification du lexique doit etre rejouee contre un echantillon
de reference.

Le prompt accepte environ 224 tokens. On raisonne en caracteres — un tokeniseur
exact demanderait d'embarquer celui de Whisper pour un gain nul — avec une
marge volontairement large : depasser tronque le prompt cote moteur, en coupant
n'importe ou.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import config as configuration

#: ~224 tokens, estimes a 4 caracteres par token, moins une marge de securite.
LIMITE_PROMPT = 800

VERSION = 1


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte)
                   if unicodedata.category(c) != "Mn")


@dataclass
class Terme:
    """Un mot du lexique et les formes erronees qu'il doit rattraper."""

    terme: str
    variantes: list[str] = field(default_factory=list)
    usages: int = 0
    epingle: bool = False   # toujours garde dans le prompt, meme sature

    def vers_dict(self) -> dict:
        return {"terme": self.terme, "variantes": self.variantes,
                "usages": self.usages, "epingle": self.epingle}

    @classmethod
    def depuis_dict(cls, donnees: dict) -> Terme:
        return cls(terme=donnees["terme"],
                   variantes=list(donnees.get("variantes", [])),
                   usages=int(donnees.get("usages", 0)),
                   epingle=bool(donnees.get("epingle", False)))


class Lexique:
    """Lexique personnel, persiste en JSON pour rester inspectable a la main.

    Le format doit rester lisible : un lexique auto-alimente peut deriver, et
    l'utilisateur doit pouvoir ouvrir le fichier pour comprendre ce qui s'y
    est glisse.
    """

    def __init__(self, chemin: Path | None = None):
        self.chemin = chemin or configuration.fichier_lexique()
        self._termes: list[Terme] = []
        self.charger()

    # -- persistance -------------------------------------------------------

    def charger(self) -> None:
        if not self.chemin.exists():
            self._termes = []
            return
        try:
            donnees = json.loads(self.chemin.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Un lexique illisible ne doit pas empecher de dicter : on repart
            # vide plutot que de refuser de demarrer.
            self._termes = []
            return
        self._termes = [Terme.depuis_dict(t) for t in donnees.get("termes", [])]

    def sauvegarder(self) -> None:
        self.chemin.write_text(json.dumps(
            {"version": VERSION,
             "termes": [t.vers_dict() for t in self._termes]},
            indent=2, ensure_ascii=False), encoding="utf-8")

    # -- consultation ------------------------------------------------------

    @property
    def termes(self) -> list[Terme]:
        return list(self._termes)

    def __len__(self) -> int:
        return len(self._termes)

    def trouver(self, terme: str) -> Terme | None:
        cible = terme.casefold()
        for existant in self._termes:
            if existant.terme.casefold() == cible:
                return existant
        return None

    def contient(self, terme: str) -> bool:
        return self.trouver(terme) is not None

    # -- modification ------------------------------------------------------

    def ajouter(self, terme: str, variantes: list[str] | None = None,
                epingle: bool = False) -> Terme:
        """Ajoute un terme, ou complete ses variantes s'il existe deja."""
        terme = terme.strip()
        if not terme:
            raise ValueError("terme vide")

        existant = self.trouver(terme)
        if existant is not None:
            for variante in (variantes or []):
                self._ajouter_variante(existant, variante)
            if epingle:
                existant.epingle = True
            return existant

        nouveau = Terme(terme=terme, epingle=epingle)
        for variante in (variantes or []):
            self._ajouter_variante(nouveau, variante)
        self._termes.append(nouveau)
        return nouveau

    def _ajouter_variante(self, terme: Terme, variante: str) -> None:
        variante = variante.strip()
        # Une variante identique au terme creerait un remplacement circulaire.
        if not variante or variante.casefold() == terme.terme.casefold():
            return
        if any(v.casefold() == variante.casefold() for v in terme.variantes):
            return
        terme.variantes.append(variante)

    def retirer(self, terme: str) -> bool:
        existant = self.trouver(terme)
        if existant is None:
            return False
        self._termes.remove(existant)
        return True

    def retirer_variante(self, terme: str, variante: str) -> bool:
        existant = self.trouver(terme)
        if existant is None:
            return False
        for connue in list(existant.variantes):
            if connue.casefold() == variante.casefold():
                existant.variantes.remove(connue)
                return True
        return False

    # -- prompt de conditionnement ----------------------------------------

    def _ordre_de_priorite(self) -> list[Terme]:
        """Epingles d'abord, puis les plus utilises.

        Quand le lexique depasse la capacite du prompt, ce sont les termes les
        moins utilises qui sortent — ils restent couverts par la table de
        remplacement.
        """
        return sorted(self._termes,
                      key=lambda t: (not t.epingle, -t.usages, t.terme.lower()))

    def prompt(self, limite: int = LIMITE_PROMPT) -> str:
        """Prompt de conditionnement, tronque par priorite si necessaire."""
        retenus: list[str] = []
        longueur = 0
        for terme in self._ordre_de_priorite():
            cout = len(terme.terme) + 2  # ", "
            if longueur + cout > limite:
                continue  # un terme long peut sauter sans bloquer les suivants
            retenus.append(terme.terme)
            longueur += cout
        return ", ".join(retenus) + ("." if retenus else "")

    def termes_hors_prompt(self, limite: int = LIMITE_PROMPT) -> list[str]:
        """Termes ecartes du prompt faute de place — utile a l'interface."""
        dans = set(self.prompt(limite).rstrip(".").split(", "))
        return [t.terme for t in self._termes if t.terme not in dans]

    # -- table de remplacement --------------------------------------------

    def corriger(self, texte: str) -> tuple[str, list[str]]:
        """Applique la table de remplacement. Renvoie (texte, termes corriges).

        Les remplacements respectent les limites de mots : sans cela,
        « Vulkan » corrigerait l'interieur de « vulcanologie ».
        """
        if not texte:
            return texte, []

        corriges: list[str] = []
        for terme in self._termes:
            for variante in terme.variantes:
                motif = re.compile(
                    r"\b" + re.escape(variante) + r"\b", re.IGNORECASE)
                texte, nombre = motif.subn(terme.terme, texte)
                if nombre:
                    if terme.terme not in corriges:
                        corriges.append(terme.terme)
                    terme.usages += nombre
        return texte, corriges

    # -- mesure ------------------------------------------------------------

    def verifier(self, texte: str, attendus: list[str]) -> dict[str, bool]:
        """Pour chaque terme attendu, dit s'il apparait exactement dans le texte.

        Sert au test de non-regression : le prompt n'etant pas monotone,
        ajouter un terme peut en casser un autre, et rien ne le signalerait.
        """
        resultats = {}
        for terme in attendus:
            motif = re.compile(r"\b" + re.escape(terme) + r"\b")
            resultats[terme] = bool(motif.search(texte))
        return resultats

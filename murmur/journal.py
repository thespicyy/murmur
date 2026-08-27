"""Journalisation rotative.

Un service qui tourne en permanence sans laisser de trace est indiagnosticable :
quand l'utilisateur signale « ca n'a pas marche tout a l'heure », il faut
pouvoir regarder. Mais un journal qui grossit indefiniment finit par remplir
le disque — d'ou la rotation.

Le journal vit dans %APPDATA%, avec les autres donnees utilisateur : il
survit a une reinstallation du projet.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys

from . import config as configuration

NOM = "murmur"
TAILLE_MAX = 1_000_000   # 1 Mo par fichier
SAUVEGARDES = 3          # soit 4 Mo au total, plafond assume

_configure = False


def configurer(niveau: int = logging.INFO) -> logging.Logger:
    """Installe le journal. Idempotent : appelable plusieurs fois sans degat."""
    global _configure

    enregistreur = logging.getLogger(NOM)
    if _configure:
        return enregistreur

    enregistreur.setLevel(niveau)
    enregistreur.propagate = False

    format_ = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")

    try:
        fichier = logging.handlers.RotatingFileHandler(
            configuration.dossier_journaux() / "murmur.log",
            maxBytes=TAILLE_MAX, backupCount=SAUVEGARDES,
            encoding="utf-8")
        fichier.setFormatter(format_)
        enregistreur.addHandler(fichier)
    except OSError as exc:
        # Ne jamais empecher l'application de demarrer parce qu'on ne peut pas
        # ecrire un journal.
        print(f"journal indisponible : {exc}", file=sys.stderr)

    _configure = True
    return enregistreur


def obtenir(nom: str | None = None) -> logging.Logger:
    """Journal du module appelant, rattache a la configuration commune."""
    configurer()
    return logging.getLogger(f"{NOM}.{nom}" if nom else NOM)


def reinitialiser() -> None:
    """Detache les gestionnaires — utilise par les tests pour repartir a neuf."""
    global _configure
    enregistreur = logging.getLogger(NOM)
    for gestionnaire in list(enregistreur.handlers):
        gestionnaire.close()
        enregistreur.removeHandler(gestionnaire)
    _configure = False

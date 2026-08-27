"""Historique des dictees et corpus de corrections.

Deux usages distincts pour une meme base :

  historique   retrouver un texte perdu, voir ce qu'on a dicte aujourd'hui.
  corpus       les corrections que l'utilisateur apporte a ses dictees.

Le corpus est journalise **des la V1**, alors que l'apprentissage n'arrive
qu'en V2. La raison est simple : les donnees qu'on ne collecte pas sont
definitivement perdues. Le jour ou l'apprentissage sera construit, il aura des
mois de matiere plutot que de repartir de zero.

SQLite plutot qu'un fichier plat : le volume croit sans limite, et retrouver
« ce que j'ai dicte mardi dernier » dans un journal texte devient vite
impraticable.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config as configuration

#: Version du schema. Toute evolution passe par une migration explicite,
#: jamais par une suppression de la base : elle contient le corpus.
SCHEMA = 1


@dataclass(frozen=True)
class Dictee:
    identifiant: int
    horodatage: datetime
    texte: str
    mots: int
    duree_audio_ms: float
    transcription_ms: float
    latence_ms: float
    cible: str

    @property
    def heure(self) -> str:
        return self.horodatage.strftime("%H:%M")

    @property
    def mots_par_minute(self) -> float:
        if self.duree_audio_ms <= 0:
            return 0.0
        return self.mots / (self.duree_audio_ms / 60_000)


@dataclass(frozen=True)
class Statistiques:
    total_mots: int
    total_dictees: int
    mots_par_minute: float
    jours_consecutifs: int
    mots_aujourdhui: int


def compter_mots(texte: str) -> int:
    return len(texte.split())


class Historique:
    """Acces a la base. Sur entre fils : toutes les ecritures sont serialisees."""

    def __init__(self, chemin: Path | None = None):
        self.chemin = chemin or configuration.fichier_historique()
        self._verrou = threading.Lock()
        self._connexion = sqlite3.connect(
            self.chemin, check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES)
        self._connexion.row_factory = sqlite3.Row
        self._migrer()

    # -- schema ------------------------------------------------------------

    def _migrer(self) -> None:
        with self._verrou, self._connexion as cx:
            version = cx.execute("PRAGMA user_version").fetchone()[0]

            if version < 1:
                cx.executescript("""
                    CREATE TABLE IF NOT EXISTS dictees (
                        id                INTEGER PRIMARY KEY,
                        horodatage        TEXT    NOT NULL,
                        texte             TEXT    NOT NULL,
                        mots              INTEGER NOT NULL,
                        duree_audio_ms    REAL    NOT NULL DEFAULT 0,
                        transcription_ms  REAL    NOT NULL DEFAULT 0,
                        latence_ms        REAL    NOT NULL DEFAULT 0,
                        cible             TEXT    NOT NULL DEFAULT ''
                    );
                    CREATE INDEX IF NOT EXISTS idx_dictees_horodatage
                        ON dictees (horodatage DESC);

                    CREATE TABLE IF NOT EXISTS corrections (
                        id          INTEGER PRIMARY KEY,
                        dictee_id   INTEGER REFERENCES dictees (id)
                                    ON DELETE SET NULL,
                        avant       TEXT NOT NULL,
                        apres       TEXT NOT NULL,
                        horodatage  TEXT NOT NULL
                    );
                """)
                cx.execute(f"PRAGMA user_version = {SCHEMA}")

    @property
    def version_schema(self) -> int:
        with self._verrou:
            return self._connexion.execute("PRAGMA user_version").fetchone()[0]

    # -- ecriture ----------------------------------------------------------

    def ajouter(self, texte: str, duree_audio_ms: float = 0.0,
                transcription_ms: float = 0.0, latence_ms: float = 0.0,
                cible: str = "", horodatage: datetime | None = None) -> int:
        moment = horodatage or datetime.now()
        with self._verrou, self._connexion as cx:
            curseur = cx.execute(
                "INSERT INTO dictees (horodatage, texte, mots, duree_audio_ms,"
                " transcription_ms, latence_ms, cible)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (moment.isoformat(timespec="seconds"), texte,
                 compter_mots(texte), duree_audio_ms, transcription_ms,
                 latence_ms, cible))
            return int(curseur.lastrowid)

    def ajouter_correction(self, avant: str, apres: str,
                           dictee_id: int | None = None) -> int:
        """Enregistre une correction pour le corpus d'apprentissage (V2)."""
        with self._verrou, self._connexion as cx:
            curseur = cx.execute(
                "INSERT INTO corrections (dictee_id, avant, apres, horodatage)"
                " VALUES (?, ?, ?, ?)",
                (dictee_id, avant, apres,
                 datetime.now().isoformat(timespec="seconds")))
            return int(curseur.lastrowid)

    def supprimer(self, identifiant: int) -> bool:
        with self._verrou, self._connexion as cx:
            curseur = cx.execute("DELETE FROM dictees WHERE id = ?",
                                 (identifiant,))
            return curseur.rowcount > 0

    def vider(self) -> None:
        """Efface l'historique — mais preserve le corpus de corrections."""
        with self._verrou, self._connexion as cx:
            cx.execute("DELETE FROM dictees")

    # -- lecture -----------------------------------------------------------

    def _vers_dictee(self, ligne: sqlite3.Row) -> Dictee:
        return Dictee(
            identifiant=ligne["id"],
            horodatage=datetime.fromisoformat(ligne["horodatage"]),
            texte=ligne["texte"], mots=ligne["mots"],
            duree_audio_ms=ligne["duree_audio_ms"],
            transcription_ms=ligne["transcription_ms"],
            latence_ms=ligne["latence_ms"], cible=ligne["cible"])

    def recentes(self, limite: int = 100, depuis: date | None = None
                 ) -> list[Dictee]:
        requete = "SELECT * FROM dictees"
        parametres: list = []
        if depuis is not None:
            requete += " WHERE horodatage >= ?"
            parametres.append(depuis.isoformat())
        # L'identifiant departage : l'horodatage est enregistre a la seconde,
          # et deux dictees d'une meme seconde se rangeaient dans l'ordre que
          # SQLite voulait — souvent le plus ancien en premier.
        requete += " ORDER BY horodatage DESC, id DESC LIMIT ?"
        parametres.append(limite)

        with self._verrou:
            lignes = self._connexion.execute(requete, parametres).fetchall()
        return [self._vers_dictee(ligne) for ligne in lignes]

    def chercher(self, terme: str, limite: int = 100) -> list[Dictee]:
        with self._verrou:
            lignes = self._connexion.execute(
                "SELECT * FROM dictees WHERE texte LIKE ?"
                " ORDER BY horodatage DESC, id DESC LIMIT ?",
                (f"%{terme}%", limite)).fetchall()
        return [self._vers_dictee(ligne) for ligne in lignes]

    # -- statistiques ------------------------------------------------------

    def statistiques(self) -> Statistiques:
        with self._verrou:
            ligne = self._connexion.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(mots), 0) AS mots,"
                " COALESCE(SUM(duree_audio_ms), 0) AS duree FROM dictees"
            ).fetchone()

            aujourdhui = self._connexion.execute(
                "SELECT COALESCE(SUM(mots), 0) AS mots FROM dictees"
                " WHERE horodatage >= ?", (date.today().isoformat(),)
            ).fetchone()["mots"]

            jours = [d[0] for d in self._connexion.execute(
                "SELECT DISTINCT substr(horodatage, 1, 10) FROM dictees"
                " ORDER BY 1 DESC").fetchall()]

        duree_minutes = ligne["duree"] / 60_000 if ligne["duree"] else 0
        return Statistiques(
            total_mots=ligne["mots"],
            total_dictees=ligne["n"],
            mots_par_minute=(ligne["mots"] / duree_minutes
                             if duree_minutes > 0 else 0.0),
            jours_consecutifs=self._serie(jours),
            mots_aujourdhui=aujourdhui)

    def mots_par_jour(self, jours: int = 14,
                      recul: int = 0) -> list[tuple[date, int]]:
        """Mots dictes pour chacun de `jours` jours consecutifs.

        `recul` remonte le temps d'autant de jours : le calendrier d'activite
        s'en sert pour paginer vers le passe sans tout relire.

        Les journees sans dictee valent zero et restent dans la liste : les
        omettre tasserait l'histogramme et laisserait croire a une regularite
        qui n'existe pas.
        """
        fin = date.today() - timedelta(days=max(0, recul))
        debut = fin - timedelta(days=jours - 1)
        suivant = fin + timedelta(days=1)
        with self._verrou:
            lignes = self._connexion.execute(
                "SELECT substr(horodatage, 1, 10) AS jour,"
                " COALESCE(SUM(mots), 0) AS mots FROM dictees"
                " WHERE horodatage >= ? AND horodatage < ? GROUP BY jour",
                (debut.isoformat(), suivant.isoformat())).fetchall()

        compte = {ligne["jour"]: ligne["mots"] for ligne in lignes}
        return [(debut + timedelta(days=rang),
                 compte.get((debut + timedelta(days=rang)).isoformat(), 0))
                for rang in range(jours)]

    def usage_par_application(self, limite: int = 6
                              ) -> list[tuple[str, int, int]]:
        """Applications les plus dictees : (cible, dictees, mots).

        La cible est le nom de l'executable au moment de l'insertion. Les
        dictees anterieures a son enregistrement portent une chaine vide :
        elles sont regroupees sous une cible inconnue plutot qu'ecartees, pour
        que les pourcentages continuent de faire cent.
        """
        with self._verrou:
            # La cible est enregistree sous la forme « programme.exe — titre
            # de la fenetre ». Regrouper sur la chaine entiere donnerait une
            # ligne par onglet de navigateur : on ne garde que le programme.
            lignes = self._connexion.execute(
                "SELECT CASE"
                "   WHEN cible = '' THEN 'inconnue'"
                "   WHEN instr(cible, ' — ') > 0"
                "     THEN substr(cible, 1, instr(cible, ' — ') - 1)"
                "   ELSE cible END AS application,"
                " COUNT(*) AS n, COALESCE(SUM(mots), 0) AS mots"
                " FROM dictees GROUP BY application"
                " ORDER BY mots DESC LIMIT ?", (limite,)).fetchall()
        return [(ligne["application"], ligne["n"], ligne["mots"])
                for ligne in lignes]

    def total_corrections(self) -> int:
        """Corrections versees au corpus depuis le premier jour."""
        with self._verrou:
            return int(self._connexion.execute(
                "SELECT COUNT(*) AS n FROM corrections").fetchone()["n"])

    def mots_du_mois(self, decalage: int = 0) -> int:
        """Mots dictes sur un mois calendaire. `decalage=1` vise le precedent.

        Le decoupage est calendaire et non glissant : « ce mois-ci » se compare
        a « le mois dernier », pas a une fenetre de trente jours qui ne
        correspondrait a rien de ce que l'utilisateur a en tete.
        """
        premier = date.today().replace(day=1)
        for _ in range(decalage):
            premier = (premier - timedelta(days=1)).replace(day=1)
        suivant = (premier + timedelta(days=32)).replace(day=1)

        with self._verrou:
            ligne = self._connexion.execute(
                "SELECT COALESCE(SUM(mots), 0) AS mots FROM dictees"
                " WHERE horodatage >= ? AND horodatage < ?",
                (premier.isoformat(), suivant.isoformat())).fetchone()
        return int(ligne["mots"])

    def plus_longue_serie(self, jours_max: int = 3650) -> int:
        """Plus longue suite de jours consecutifs jamais atteinte.

        La serie en cours dit ou l'on en est ; celle-ci dit ce dont on est
        capable, et c'est elle qui donne un sens a la premiere quand elle
        vient de retomber a zero.
        """
        with self._verrou:
            lignes = self._connexion.execute(
                "SELECT DISTINCT date(horodatage) AS jour FROM dictees"
                " ORDER BY jour DESC LIMIT ?", (jours_max,)).fetchall()
        jours = [date.fromisoformat(ligne["jour"]) for ligne in lignes]
        if not jours:
            return 0

        record = courante = 1
        for precedent, jour in zip(jours, jours[1:]):
            courante = courante + 1 if (precedent - jour).days == 1 else 1
            record = max(record, courante)
        return record

    @staticmethod
    def _serie(jours: list[str]) -> int:
        """Nombre de jours consecutifs d'usage, en terminant aujourd'hui ou hier.

        Tolerer la veille evite de remettre le compteur a zero parce qu'on
        consulte le matin avant d'avoir dicte.
        """
        if not jours:
            return 0
        aujourdhui = date.today()
        premier = date.fromisoformat(jours[0])
        if (aujourdhui - premier).days > 1:
            return 0

        serie = 1
        precedent = premier
        for texte in jours[1:]:
            jour = date.fromisoformat(texte)
            if (precedent - jour).days == 1:
                serie += 1
                precedent = jour
            else:
                break
        return serie

    # -- cycle de vie ------------------------------------------------------

    def fermer(self) -> None:
        with self._verrou:
            self._connexion.close()

    def __enter__(self) -> Historique:
        return self

    def __exit__(self, *_) -> None:
        self.fermer()

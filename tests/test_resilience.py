"""T2.4 et T2.5 — redemarrage du moteur, journalisation, survie aux pannes."""

import logging
import threading
import time

import numpy as np
import pytest

from murmur import audio, config as cfg, inject, journal, stt
from murmur.app import Application, Etat, Resultat


@pytest.fixture
def conf(donnees):
    configuration = cfg.charger()
    configuration.definir("moteur.port", 8757)
    configuration.definir("moteur.surveillance_s", 0.1)
    return configuration


def signal(duree_s: float = 0.5) -> audio.Capture:
    n = int(audio.TAUX * duree_s)
    t = np.linspace(0, duree_s, n, endpoint=False)
    return audio.Capture((0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32),
                         audio.TAUX)


def attendre(condition, timeout=3.0):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condition():
            return True
        time.sleep(0.02)
    return False


# --------------------------------------------------------------------------
# T2.4 — plafond de redemarrages
# --------------------------------------------------------------------------

def test_les_fonctions_job_ont_des_signatures_64_bits():
    """Sans `restype`, ctypes tronque les handles Windows a 32 bits.

    Le defaut reste invisible tant que les handles sont petits, puis corrompt
    tout des qu'ils depassent 2^31 — ce qui arrive dans un executable
    empaquete, ou davantage de handles sont ouverts. On manipule alors un
    handle qui ne designe plus le job, et le fermer tue le moteur au lieu de
    le proteger.
    """
    from ctypes import wintypes

    assert stt.kernel32.CreateJobObjectW.restype is wintypes.HANDLE
    assert stt.kernel32.AssignProcessToJobObject.argtypes == (
        wintypes.HANDLE, wintypes.HANDLE)
    assert stt.kernel32.OpenProcess.restype is wintypes.HANDLE


def test_le_handle_de_job_nest_pas_tronque():
    """Verification directe : le handle rendu doit tenir sur 64 bits."""
    job = stt.creer_job_suicide()
    assert job, "creation du job impossible"
    try:
        assert isinstance(job, int)
        assert job > 0, "un handle negatif trahit une troncature signee"
    finally:
        stt.kernel32.CloseHandle(job)


def test_moteur_vivant_na_pas_besoin_detre_relance(conf, monkeypatch):
    moteur = stt.Moteur(conf)
    monkeypatch.setattr(moteur, "est_vivant", lambda: True)
    monkeypatch.setattr(moteur, "demarrer", lambda: pytest.fail(
        "un moteur vivant ne doit pas etre redemarre"))
    assert moteur.assurer_disponibilite()


def test_le_moteur_est_relance_sil_est_tombe(conf, monkeypatch):
    moteur = stt.Moteur(conf)
    etat = {"vivant": False}
    monkeypatch.setattr(moteur, "est_vivant", lambda: etat["vivant"])
    monkeypatch.setattr(moteur, "demarrer",
                        lambda: etat.__setitem__("vivant", True))

    assert moteur.assurer_disponibilite()
    assert etat["vivant"]


def test_le_plafond_de_redemarrages_est_respecte(conf, monkeypatch):
    """Un moteur qui meurt en boucle signale une panne de fond.

    S'acharner la masquerait et consommerait la machine, alors qu'un message
    clair permet d'agir.
    """
    conf.definir("moteur.max_redemarrages", 3)
    moteur = stt.Moteur(conf)
    tentatives = []
    monkeypatch.setattr(moteur, "est_vivant", lambda: False)
    monkeypatch.setattr(moteur, "demarrer", lambda: tentatives.append(1))

    for _ in range(6):
        moteur.assurer_disponibilite()

    assert len(tentatives) == 3, "le plafond n'a pas ete respecte"
    assert moteur.epuise


def test_le_compteur_de_redemarrages_soublie_avec_le_temps(conf, monkeypatch):
    """Une panne isolee ne doit pas condamner la session entiere."""
    conf.definir("moteur.max_redemarrages", 2)
    conf.definir("moteur.fenetre_redemarrages_s", 0.3)
    moteur = stt.Moteur(conf)
    tentatives = []
    monkeypatch.setattr(moteur, "est_vivant", lambda: False)
    monkeypatch.setattr(moteur, "demarrer", lambda: tentatives.append(1))

    moteur.assurer_disponibilite()
    moteur.assurer_disponibilite()
    assert moteur.epuise

    time.sleep(0.35)
    assert not moteur.epuise, "le compteur aurait du s'oublier"
    moteur.assurer_disponibilite()
    assert len(tentatives) == 3


def test_un_echec_de_relance_est_signale_sans_lever(conf, monkeypatch):
    moteur = stt.Moteur(conf)
    monkeypatch.setattr(moteur, "est_vivant", lambda: False)
    monkeypatch.setattr(moteur, "demarrer", lambda: (_ for _ in ()).throw(
        stt.ErreurMoteur("port pris")))
    assert not moteur.assurer_disponibilite()


def test_transcrire_relance_un_moteur_tombe(conf, monkeypatch):
    """Une dictee ne doit pas etre perdue parce que le moteur vient de tomber."""
    moteur = stt.Moteur(conf)
    etat = {"vivant": False}
    monkeypatch.setattr(moteur, "est_vivant", lambda: etat["vivant"])
    monkeypatch.setattr(moteur, "demarrer",
                        lambda: etat.__setitem__("vivant", True))

    envoyes = []

    class ReponseFactice:
        status_code = 200

        @staticmethod
        def json():
            return {"text": "texte"}

    monkeypatch.setattr(stt.requests, "post",
                        lambda *a, **k: (envoyes.append(1), ReponseFactice())[1])

    assert moteur.transcrire(b"wav") == "texte"
    assert etat["vivant"], "le moteur aurait du etre relance"


def test_transcrire_echoue_clairement_si_la_relance_est_epuisee(conf, monkeypatch):
    conf.definir("moteur.max_redemarrages", 0)
    moteur = stt.Moteur(conf)
    monkeypatch.setattr(moteur, "est_vivant", lambda: False)

    with pytest.raises(stt.ErreurMoteur) as info:
        moteur.transcrire(b"wav")
    assert "n'a pas pu etre relance" in str(info.value)


# --------------------------------------------------------------------------
# T2.4 — surveillance depuis l'application
# --------------------------------------------------------------------------

def test_la_surveillance_relance_et_previent(conf, monkeypatch):
    application = Application(conf)
    etat = {"vivant": False}
    monkeypatch.setattr(application.moteur, "est_vivant",
                        lambda: etat["vivant"])
    monkeypatch.setattr(application.moteur, "assurer_disponibilite",
                        lambda: etat.__setitem__("vivant", True) or True)

    recus = []
    application.ecouteurs.resultat.append(recus.append)

    fil = threading.Thread(target=application._surveiller, daemon=True)
    fil.start()
    try:
        assert attendre(lambda: recus), "aucune alerte publiee"
        assert "relance" in recus[0].avertissement
    finally:
        application._arret.set()
        fil.join(timeout=2)


def test_la_surveillance_ne_repete_pas_son_alerte(conf, monkeypatch):
    """Une panne persistante ne doit pas noyer l'utilisateur d'alertes."""
    application = Application(conf)
    monkeypatch.setattr(application.moteur, "est_vivant", lambda: False)
    monkeypatch.setattr(application.moteur, "assurer_disponibilite",
                        lambda: False)

    recus = []
    application.ecouteurs.resultat.append(recus.append)

    fil = threading.Thread(target=application._surveiller, daemon=True)
    fil.start()
    try:
        assert attendre(lambda: recus)
        time.sleep(0.5)   # plusieurs tours de surveillance
    finally:
        application._arret.set()
        fil.join(timeout=2)

    assert len(recus) == 1, f"{len(recus)} alertes pour une seule panne"


def test_la_surveillance_survit_a_une_exception(conf, monkeypatch):
    """Le veilleur rattrape les pannes : il ne peut pas en etre la victime."""
    application = Application(conf)
    appels = []

    def est_vivant_capricieux():
        appels.append(1)
        if len(appels) < 3:
            raise RuntimeError("panne du controle lui-meme")
        return True

    monkeypatch.setattr(application.moteur, "est_vivant",
                        est_vivant_capricieux)

    fil = threading.Thread(target=application._surveiller, daemon=True)
    fil.start()
    try:
        assert attendre(lambda: len(appels) >= 4), \
            "le veilleur s'est arrete a la premiere exception"
    finally:
        application._arret.set()
        fil.join(timeout=2)


# --------------------------------------------------------------------------
# T2.5 — journalisation
# --------------------------------------------------------------------------

def test_le_journal_ecrit_dans_les_donnees_utilisateur(donnees):
    journal.reinitialiser()
    enregistreur = journal.obtenir("essai")
    enregistreur.info("message de test")

    fichier = cfg.dossier_journaux() / "murmur.log"
    assert fichier.exists()
    assert "message de test" in fichier.read_text(encoding="utf-8")
    journal.reinitialiser()


def test_le_journal_tourne_et_ne_grossit_pas_indefiniment(donnees, monkeypatch):
    """Un service permanent ne doit jamais remplir le disque."""
    journal.reinitialiser()
    monkeypatch.setattr(journal, "TAILLE_MAX", 2000)
    enregistreur = journal.obtenir("volume")
    for i in range(400):
        enregistreur.info("ligne de remplissage numero %d", i)

    dossier = cfg.dossier_journaux()
    fichiers = list(dossier.glob("murmur.log*"))
    assert len(fichiers) > 1, "la rotation n'a pas eu lieu"
    assert len(fichiers) <= journal.SAUVEGARDES + 1, "trop de fichiers conserves"
    journal.reinitialiser()


def test_configurer_deux_fois_nempile_pas_les_gestionnaires(donnees):
    journal.reinitialiser()
    journal.configurer()
    nombre = len(logging.getLogger(journal.NOM).handlers)
    journal.configurer()
    assert len(logging.getLogger(journal.NOM).handlers) == nombre
    journal.reinitialiser()


def test_un_journal_impossible_nempeche_pas_de_demarrer(donnees, monkeypatch,
                                                        capsys):
    journal.reinitialiser()
    monkeypatch.setattr(
        cfg, "dossier_journaux",
        lambda: (_ for _ in ()).throw(OSError("disque plein")))
    enregistreur = journal.configurer()          # ne doit pas lever
    enregistreur.info("perdu, mais sans degat")
    assert "journal indisponible" in capsys.readouterr().err
    journal.reinitialiser()


def test_les_dictees_sont_journalisees(conf, donnees, monkeypatch):
    journal.reinitialiser()
    application = Application(conf)
    monkeypatch.setattr(application.moteur, "transcrire",
                        lambda *a, **k: "bonjour")
    monkeypatch.setattr(application.injecteur, "injecter",
                        lambda t: inject.ResultatInjection(duree_pose_ms=2.0))

    application._traiter(signal(), "notepad.exe", time.perf_counter())

    contenu = (cfg.dossier_journaux() / "murmur.log").read_text(encoding="utf-8")
    assert "dictee" in contenu
    assert "notepad.exe" in contenu
    journal.reinitialiser()


def test_un_rejet_est_journalise_avec_son_motif(conf, donnees, monkeypatch):
    journal.reinitialiser()
    application = Application(conf)
    application._traiter(audio.Capture(np.zeros(0, dtype=np.float32),
                                       audio.TAUX),
                         "cible", time.perf_counter())

    contenu = (cfg.dossier_journaux() / "murmur.log").read_text(encoding="utf-8")
    assert "rejete" in contenu
    journal.reinitialiser()


def test_un_ecouteur_defaillant_est_journalise_sans_casser(conf, donnees,
                                                           monkeypatch):
    journal.reinitialiser()
    application = Application(conf)
    application.ecouteurs.resultat.append(
        lambda r: (_ for _ in ()).throw(RuntimeError("interface cassee")))
    monkeypatch.setattr(application.moteur, "transcrire",
                        lambda *a, **k: "bonjour")
    monkeypatch.setattr(application.injecteur, "injecter",
                        lambda t: inject.ResultatInjection())

    application._traiter(signal(), "cible", time.perf_counter())

    contenu = (cfg.dossier_journaux() / "murmur.log").read_text(encoding="utf-8")
    assert "interface cassee" in contenu
    assert application.etat is Etat.REPOS
    journal.reinitialiser()


def test_louvrier_survit_a_une_erreur_imprevue(conf, monkeypatch):
    """Si l'ouvrier mourait, l'application semblerait vivante mais inerte."""
    application = Application(conf)
    application._arret.clear()

    appels = []
    monkeypatch.setattr(application, "_traiter",
                        lambda *a: (appels.append(1),
                                    (_ for _ in ()).throw(RuntimeError("boum")))[0])

    fil = threading.Thread(target=application._travailler, daemon=True)
    fil.start()
    try:
        application._file.put((signal(), "cible", time.perf_counter()))
        assert attendre(lambda: len(appels) == 1)
        application._file.put((signal(), "cible", time.perf_counter()))
        assert attendre(lambda: len(appels) == 2), \
            "l'ouvrier est mort a la premiere exception"
    finally:
        application._arret.set()
        fil.join(timeout=2)

"""T1.6 — orchestration.

La machine a etats et la file se testent avec des doublures : ni micro, ni
moteur, ni frappe. Le test de bout en bout reel, lui, demande du materiel et
une voix — c'est le seul point de J1 qui reclame un humain.
"""

import threading
import time

import numpy as np
import pytest

from murmur import audio, config as cfg, inject
from murmur.app import Application, Etat, Resultat


@pytest.fixture
def conf(donnees):
    configuration = cfg.charger()
    configuration.definir("moteur.port", 8751)
    return configuration


@pytest.fixture
def application(conf, monkeypatch):
    """Application dont le moteur, le micro et l'insertion sont simules."""
    app = Application(conf)

    app._journal_injecte = []
    app._transcriptions = []

    monkeypatch.setattr(app.moteur, "demarrer", lambda: None)
    monkeypatch.setattr(app.moteur, "arreter", lambda *a, **k: None)
    monkeypatch.setattr(app.moteur, "est_vivant", lambda: True)
    monkeypatch.setattr(
        app.moteur, "transcrire",
        lambda wav, prompt=None, timeout=60.0: app._transcriptions.pop(0)
        if app._transcriptions else "texte transcrit")
    def injecter_double(texte):
        app._journal_injecte.append(texte)
        return inject.ResultatInjection(duree_pose_ms=3.0, restaure=True)

    monkeypatch.setattr(app.injecteur, "injecter", injecter_double)
    monkeypatch.setattr("murmur.app.inject.fenetre_active",
                        lambda: ("Bloc-notes", "notepad.exe"))
    return app


def signal(duree_s: float = 1.0, amplitude: float = 0.3) -> np.ndarray:
    n = int(audio.TAUX * duree_s)
    t = np.linspace(0, duree_s, n, endpoint=False)
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def attendre(condition, timeout=3.0, pas=0.02):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condition():
            return True
        time.sleep(pas)
    return False


# --------------------------------------------------------------------------
# Machine a etats
# --------------------------------------------------------------------------

def test_etat_initial_est_repos(application):
    assert application.etat is Etat.REPOS


def test_les_ecouteurs_recoivent_les_changements_detat(application, monkeypatch):
    vus = []
    application.ecouteurs.etat.append(vus.append)
    monkeypatch.setattr(application.enregistreur, "demarrer", lambda: None)

    application.commencer_ecoute()
    assert vus == [Etat.ECOUTE]
    assert application.etat is Etat.ECOUTE


def test_un_ecouteur_defaillant_ne_casse_pas_la_dictee(application, monkeypatch):
    """Une interface qui plante ne doit jamais faire perdre une dictee."""
    def ecouteur_casse(_):
        raise RuntimeError("interface cassee")

    application.ecouteurs.etat.append(ecouteur_casse)
    monkeypatch.setattr(application.enregistreur, "demarrer", lambda: None)

    application.commencer_ecoute()
    assert application.etat is Etat.ECOUTE


def test_deux_appuis_nouvrent_pas_deux_dictees(application, monkeypatch):
    demarrages = []
    monkeypatch.setattr(application.enregistreur, "demarrer",
                        lambda: demarrages.append(1))
    application.commencer_ecoute()
    application.commencer_ecoute()
    assert len(demarrages) == 1


def test_terminer_sans_ecoute_ne_fait_rien(application):
    application.terminer_ecoute()
    assert application.etat is Etat.REPOS
    assert application._file.empty()


def test_un_micro_indisponible_est_signale_sans_bloquer(application, monkeypatch):
    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    monkeypatch.setattr(
        application.enregistreur, "demarrer",
        lambda: (_ for _ in ()).throw(audio.ErreurAudio("micro absent")))

    application.commencer_ecoute()
    assert application.etat is Etat.REPOS, "on doit rester disponible"
    assert resultats and "micro absent" in resultats[0].erreur


# --------------------------------------------------------------------------
# Traitement
# --------------------------------------------------------------------------

def test_dictee_complete_produit_texte_et_insertion(application, monkeypatch):
    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    application._transcriptions = ["bonjour le monde"]

    monkeypatch.setattr(application.enregistreur, "demarrer", lambda: None)
    monkeypatch.setattr(application.enregistreur, "arreter",
                        lambda: audio.Capture(signal(1.0), audio.TAUX))

    application._arret.clear()
    ouvrier = threading.Thread(target=application._travailler, daemon=True)
    ouvrier.start()
    try:
        application.commencer_ecoute()
        application.terminer_ecoute()
        assert attendre(lambda: resultats), "aucun resultat produit"
    finally:
        application._arret.set()
        ouvrier.join(timeout=2)

    resultat = resultats[0]
    assert resultat.reussi
    assert resultat.texte == "bonjour le monde"
    assert application._journal_injecte == ["bonjour le monde"]
    assert resultat.duree_audio_ms == pytest.approx(1000, abs=20)
    assert resultat.latence_ms > 0
    assert resultat.cible == "notepad.exe — Bloc-notes"
    assert application.etat is Etat.REPOS


def test_capture_vide_est_rejetee_sans_appeler_le_moteur(application):
    """Un appui accidentel ne doit rien produire, ni couter une transcription."""
    resultat = Resultat()
    appels = []
    application.moteur.transcrire = lambda *a, **k: appels.append(1)

    application._traiter(audio.Capture(np.zeros(0, dtype=np.float32),
                                       audio.TAUX), "cible", time.perf_counter())
    assert appels == []


def test_transcription_vide_est_rejetee(application):
    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    application._transcriptions = [""]

    application._traiter(audio.Capture(signal(0.5), audio.TAUX), "cible",
                         time.perf_counter())

    assert resultats[0].rejete == "transcription vide"
    assert application._journal_injecte == []


def test_une_erreur_du_moteur_est_rapportee_et_lapp_reste_utilisable(application):
    from murmur import stt

    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    application.moteur.transcrire = lambda *a, **k: (
        _ for _ in ()).throw(stt.ErreurMoteur("moteur injoignable"))

    application._traiter(audio.Capture(signal(0.5), audio.TAUX), "cible",
                         time.perf_counter())

    assert "injoignable" in resultats[0].erreur
    assert not resultats[0].reussi
    assert application.etat is Etat.REPOS


def test_une_exception_imprevue_ne_tue_pas_louvrier(application):
    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    application.moteur.transcrire = lambda *a, **k: (
        _ for _ in ()).throw(ValueError("imprevu"))

    application._traiter(audio.Capture(signal(0.5), audio.TAUX), "cible",
                         time.perf_counter())

    assert "ValueError" in resultats[0].erreur
    assert application.etat is Etat.REPOS


def test_la_file_traite_dans_l_ordre(application):
    """La file serialise : deux dictees ne s'entremelent jamais.

    On enfile directement, sans passer par la capture : c'est bien l'ordre de
    traitement qu'on verifie ici, pas le declenchement.
    """
    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    application._transcriptions = ["premiere", "seconde", "troisieme"]

    application._arret.clear()
    ouvrier = threading.Thread(target=application._travailler, daemon=True)
    ouvrier.start()
    try:
        for _ in range(3):
            application._file.put((audio.Capture(signal(0.3), audio.TAUX),
                                   "cible", time.perf_counter()))
        assert attendre(lambda: len(resultats) == 3), "toutes n'ont pas ete traitees"
    finally:
        application._arret.set()
        ouvrier.join(timeout=2)

    assert [r.texte for r in resultats] == ["premiere", "seconde", "troisieme"]
    assert application._journal_injecte == ["premiere", "seconde", "troisieme"]


def test_une_nouvelle_dictee_est_refusee_pendant_le_traitement(application,
                                                               monkeypatch):
    """Limite assumee de J1, a rendre visible en J3.

    Tant qu'une dictee n'est pas posee, une nouvelle est ignoree. La fenetre
    concernee est courte (~250 ms), mais elle s'allongera si le nettoyage par
    IA est active. Sans retour visuel, l'utilisateur croirait avoir dicte dans
    le vide : c'est l'indicateur d'etat (T3.1) qui devra le signaler.
    """
    demarrages = []
    monkeypatch.setattr(application.enregistreur, "demarrer",
                        lambda: demarrages.append(1))
    monkeypatch.setattr(application.enregistreur, "arreter",
                        lambda: audio.Capture(signal(0.3), audio.TAUX))

    application.commencer_ecoute()
    application.terminer_ecoute()          # passe en TRANSCRIPTION
    assert application.etat is Etat.TRANSCRIPTION

    application.commencer_ecoute()         # doit etre ignoree
    assert len(demarrages) == 1
    assert application.etat is Etat.TRANSCRIPTION


def test_une_nouvelle_dictee_est_acceptee_une_fois_la_precedente_posee(
        application, monkeypatch):
    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    application._transcriptions = ["premiere", "seconde"]

    monkeypatch.setattr(application.enregistreur, "demarrer", lambda: None)
    monkeypatch.setattr(application.enregistreur, "arreter",
                        lambda: audio.Capture(signal(0.3), audio.TAUX))

    application._arret.clear()
    ouvrier = threading.Thread(target=application._travailler, daemon=True)
    ouvrier.start()
    try:
        for attendu in (1, 2):
            application.commencer_ecoute()
            application.terminer_ecoute()
            assert attendre(lambda n=attendu: len(resultats) == n), \
                f"dictee {attendu} non traitee"
            assert application.etat is Etat.REPOS
    finally:
        application._arret.set()
        ouvrier.join(timeout=2)

    assert [r.texte for r in resultats] == ["premiere", "seconde"]


# --------------------------------------------------------------------------
# Mode bascule
# --------------------------------------------------------------------------

def test_un_avertissement_dinjection_remonte_dans_le_resultat(application,
                                                              monkeypatch):
    """Ce qui a ete perdu doit atteindre l'utilisateur, pas rester enfoui."""
    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    application._transcriptions = ["texte"]
    monkeypatch.setattr(
        application.injecteur, "injecter",
        lambda t: inject.ResultatInjection(
            duree_pose_ms=2.0,
            avertissement="le presse-papier contenait une image, "
                          "qui sera perdu"))

    application._traiter(audio.Capture(signal(0.4), audio.TAUX), "cible",
                         time.perf_counter())

    assert "image" in resultats[0].avertissement
    assert resultats[0].reussi, "un avertissement n'est pas un echec"


def test_la_latence_exclut_l_attente_de_restauration(application, monkeypatch):
    """La latence annoncee doit refleter ce que l'utilisateur percoit.

    La restauration du presse-papier se produit apres l'arrivee du texte : la
    compter gonflerait artificiellement le chiffre et masquerait une vraie
    derive de performance.
    """
    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    application._transcriptions = ["texte"]

    def injecter_lent(_texte):
        time.sleep(0.30)   # simule l'attente avant restauration
        return inject.ResultatInjection(duree_pose_ms=5.0)

    monkeypatch.setattr(application.injecteur, "injecter", injecter_lent)

    application._traiter(audio.Capture(signal(0.4), audio.TAUX), "cible",
                         time.perf_counter())

    assert resultats[0].latence_ms < 200, (
        f"{resultats[0].latence_ms:.0f} ms — l'attente de restauration est "
        f"comptee dans la latence")


def test_la_bascule_demarre_puis_arrete(application, monkeypatch):
    monkeypatch.setattr(application.enregistreur, "demarrer", lambda: None)
    monkeypatch.setattr(application.enregistreur, "arreter",
                        lambda: audio.Capture(signal(0.3), audio.TAUX))

    application.basculer()
    assert application.etat is Etat.ECOUTE
    application.basculer()
    assert application.etat is Etat.TRANSCRIPTION
    assert not application._file.empty()


# --------------------------------------------------------------------------
# Copie automatique avant l'analyse
# --------------------------------------------------------------------------
#
# L'utilisateur corrige son texte DANS l'application puis appuie sur le
# raccourci — geste naturel. Sans cette copie, Murmur ne trouve dans le
# presse-papier que ce qu'il venait d'y ecrire pour coller la dictee, et
# compare la dictee a elle-meme.

class _PressePapierFactice:
    """Un presse-papier en memoire, plus une application qui repond au Ctrl+C.

    `selection` est ce que l'application copierait ; `None` signifie qu'il n'y
    a rien de selectionne — Ctrl+C ne fait alors rien du tout, ce qui est
    exactement le comportement de Windows.
    """

    ErreurInjection = inject.ErreurInjection

    def __init__(self, contenu: str, selection: str | None):
        self.contenu = contenu
        self.selection = selection
        self.copies = 0

    def lire_presse_papier(self):
        return self.contenu

    def ecrire_presse_papier(self, texte):
        self.contenu = texte

    def vider_presse_papier(self):
        self.contenu = ""

    def contenu_presse_papier(self):
        # Le format EST declare quand il y a du texte : « vide » se lit sur la
        # liste des formats, pas sur la chaine. Une doublure qui rendait du
        # texte sans format decrivait un presse-papier impossible — et faisait
        # croire a un defaut de restauration qui n'existait pas.
        formats = (inject.CF_UNICODETEXT,) if self.contenu else ()
        return inject.ContenuPressePapier(texte=self.contenu or None,
                                          formats=formats)

    def copier_la_selection(self, delai_s=0.0):
        self.copies += 1
        if self.selection is not None:
            self.contenu = self.selection


def _preparer(application, monkeypatch, contenu, selection):
    faux = _PressePapierFactice(contenu, selection)
    monkeypatch.setattr("murmur.app.inject", faux)
    return faux


def test_la_selection_est_copiee_avant_d_etre_lue(application, monkeypatch):
    faux = _preparer(application, monkeypatch,
                     contenu="ce que Murmur avait colle",
                     selection="la phrase corrigee")

    application._copier_le_texte_corrige()

    assert faux.contenu == "la phrase corrigee"
    assert faux.copies == 1


def test_sans_selection_le_presse_papier_est_rendu(application, monkeypatch):
    """Ctrl+C sans selection ne fait rien : on ne doit pas laisser la
    sentinelle derriere soi, ni perdre ce que l'utilisateur y gardait."""
    faux = _preparer(application, monkeypatch,
                     contenu="quelque chose que je gardais", selection=None)

    application._copier_le_texte_corrige()

    assert faux.contenu == "quelque chose que je gardais"


def test_la_copie_automatique_ne_selectionne_jamais_tout():
    """`SendInput` depose la frappe dans la file de la fenetre qui a le FOCUS,
    et Windows refuse le passage au premier plan a un processus qui ne l'a
    pas. Un Ctrl+A a l'aveugle part donc parfois ailleurs — au banc d'essai il
    a copie le contenu entier d'un autre document. Ctrl+C sans selection, lui,
    ne fait rien."""
    import inspect

    from murmur import app as module_app

    source = inspect.getsource(module_app.Application._copier_le_texte_corrige)
    assert "tout_selectionner" not in source
    assert not hasattr(inject, "tout_selectionner"), \
        "le geste ecarte reste disponible : il sera repris un jour"


def test_le_reglage_permet_de_couper_la_copie(application, monkeypatch):
    """Le geste envoie une frappe a une autre application : il doit pouvoir
    etre refuse."""
    faux = _preparer(application, monkeypatch,
                     contenu="inchange", selection="la phrase corrigee")
    application.conf.definir("lexique.copier_avant_analyse", False)
    application.historique.ajouter("une dictee quelconque")

    application.apprendre_depuis_presse_papier()

    assert faux.copies == 0
    assert faux.contenu == "inchange"


# --------------------------------------------------------------------------
# Le clavier ne doit pas pouvoir disparaitre en silence
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_le_veilleur_reprend_les_raccourcis_disparus(application):
    """Panne observee : l'application tournait, sourde, sans rien dire.

    Le fil qui portait les raccourcis s'etait arrete ; Windows lie une
    combinaison a ce fil, elle etait donc rendue au systeme. Icone, tableau de
    bord, tout repondait — sauf le clavier. Le veilleur les reprend desormais
    au tour suivant, quelle que soit la cause de la disparition.
    """
    application.conf.definir("raccourcis.maintien", "ctrl+alt+shift+f15")
    application.conf.definir("raccourcis.bascule", "ctrl+alt+shift+f16")
    application.conf.definir("lexique.actif", False)
    application._declarer_raccourcis(application.raccourcis)
    application.raccourcis.demarrer()
    application._poses = True
    try:
        application.raccourcis.arreter()
        assert not application.raccourcis.en_cours

        application._verifier_les_raccourcis()

        assert application.raccourcis.en_cours, "le clavier est reste muet"
    finally:
        application.raccourcis.arreter()


@pytest.mark.materiel
def test_le_veilleur_ne_reprend_rien_avant_le_demarrage(application):
    """Le veilleur est lance AVANT les raccourcis : son premier tour ne doit
    pas les enregistrer a leur place, ni echouer d'avoir essaye."""
    assert not application._poses
    avant = application.raccourcis

    application._verifier_les_raccourcis()

    assert application.raccourcis is avant

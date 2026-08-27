"""T1.2 — cycle de vie du moteur et transcription.

Les tests marques `lent` demarrent reellement whisper-server et chargent le
modele (environ 600 Mo, quelques secondes). Pour ne lancer que les tests
rapides :

    pytest -m "not lent"
"""

import os
import subprocess
import sys
import time

import pytest

from murmur import config as cfg
from murmur import stt

# jfk.wav est fourni avec les sources de whisper.cpp et sert de reference
# stable : son contenu est connu et ne depend d'aucun enregistrement local.
ECHANTILLON = (cfg.RACINE / ".." / "WhisperBench" / "whisper.cpp" / "samples"
               / "jfk.wav").resolve()

MOTEUR_PRESENT = (cfg.MOTEUR / "whisper-server.exe").exists() and \
                 (cfg.MOTEUR / "ggml-large-v3-turbo-q5_0.bin").exists()

besoin_moteur = pytest.mark.skipif(
    not MOTEUR_PRESENT, reason="engine/ incomplet (serveur ou modele absent)")
besoin_echantillon = pytest.mark.skipif(
    not ECHANTILLON.exists(), reason="jfk.wav introuvable")


@pytest.fixture
def conf(donnees):
    """Configuration isolee, sur un port improbable pour ne rien percuter."""
    configuration = cfg.charger()
    configuration.definir("moteur.port", 8749)
    configuration.definir("langue", "en")  # jfk.wav est en anglais
    return configuration


# --------------------------------------------------------------------------
# Rapide — sans demarrer le moteur
# --------------------------------------------------------------------------

def test_arguments_contiennent_le_modele_et_le_port(conf):
    args = stt.Moteur(conf)._arguments()
    assert str(conf.chemin_modele) in args
    assert "8749" in args
    assert "--no-timestamps" in args


def test_vad_actif_ajoute_ses_options(conf):
    args = stt.Moteur(conf)._arguments()
    assert "--vad" in args
    assert str(conf.chemin_modele_vad) in args
    assert "--suppress-nst" in args


def test_vad_desactive_retire_ses_options(conf):
    conf.definir("vad.actif", False)
    conf.definir("vad.suppress_nst", False)
    args = stt.Moteur(conf)._arguments()
    assert "--vad" not in args
    assert "--suppress-nst" not in args


def test_transcrire_sans_moteur_disponible_leve_une_erreur_explicite(conf):
    """Depuis T2.4, transcrire tente d'abord de relancer un moteur tombe.

    On desactive la relance pour verifier le message d'echec — sinon ce test
    demarrerait un vrai serveur, ce qui n'est pas son objet.
    """
    conf.definir("moteur.max_redemarrages", 0)
    with pytest.raises(stt.ErreurMoteur, match="n'a pas pu etre relance"):
        stt.Moteur(conf).transcrire(b"")


def test_fichier_manquant_signale_le_chemin(conf, tmp_path, monkeypatch):
    """L'erreur doit nommer ce qui manque, pas echouer obscurement."""
    monkeypatch.setattr(cfg, "MOTEUR", tmp_path / "vide")
    conf_vide = cfg.charger()
    with pytest.raises(stt.ErreurMoteur) as info:
        stt.Moteur(conf_vide)._verifier_fichiers()
    message = str(info.value)
    assert "introuvable" in message
    assert "serveur" in message


def test_port_occupe_est_detecte(conf):
    """Demarrer sur un port pris doit echouer clairement, pas silencieusement."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prise:
        prise.bind((conf["moteur.hote"], 0))
        prise.listen(5)
        port = prise.getsockname()[1]
        assert not stt.port_disponible(conf["moteur.hote"], port)
        conf.definir("moteur.port", port)
        with pytest.raises(stt.ErreurMoteur, match="deja occupe"):
            stt.Moteur(conf).demarrer()


def test_port_libre_est_signale_disponible(conf):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prise:
        prise.bind((conf["moteur.hote"], 0))
        port = prise.getsockname()[1]
    assert stt.port_disponible(conf["moteur.hote"], port)


def test_disponibilite_et_reponse_sont_deux_questions_distinctes(conf):
    """Un port libre n'a personne qui repond ; un port en ecoute repond.

    Confondre les deux a produit un faux negatif : la detection par connexion
    echouait quand le backlog etait plein, laissant demarrer un serveur sur un
    port deja pris.
    """
    import socket
    hote = conf["moteur.hote"]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prise:
        prise.bind((hote, 0))
        port = prise.getsockname()[1]
        prise.listen(5)
        assert not stt.port_disponible(hote, port)
        assert stt.serveur_repond(hote, port)

    # Une fois le socket ferme, les deux reponses s'inversent.
    assert stt.port_disponible(hote, port)
    assert not stt.serveur_repond(hote, port)


def test_arreter_sans_avoir_demarre_ne_casse_rien(conf):
    stt.Moteur(conf).arreter()


# --------------------------------------------------------------------------
# Lent — le moteur tourne pour de vrai
# --------------------------------------------------------------------------

@pytest.mark.lent
@besoin_moteur
@besoin_echantillon
def test_transcription_bout_en_bout(conf):
    """Le critere de fin de T1.2 : un WAV envoye revient en texte."""
    with stt.Moteur(conf) as moteur:
        assert moteur.est_vivant()
        texte = moteur.transcrire(ECHANTILLON.read_bytes())

    assert texte, "transcription vide"
    assert "country" in texte.lower(), f"texte inattendu : {texte!r}"
    assert "\n" not in texte, "le texte doit etre sur une seule ligne"


@pytest.mark.lent
@besoin_moteur
@besoin_echantillon
def test_le_prompt_est_accepte_par_requete(conf):
    """Le lexique contextuel repose entierement sur cette capacite."""
    with stt.Moteur(conf) as moteur:
        texte = moteur.transcrire(ECHANTILLON.read_bytes(),
                                  prompt="Kennedy, Americans, country.")
    assert texte


@pytest.mark.lent
@besoin_moteur
def test_arret_ne_laisse_pas_de_processus_orphelin(conf):
    """Second critere de T1.2, verifie au niveau du systeme."""
    moteur = stt.Moteur(conf)
    moteur.demarrer()
    pid = moteur._processus.pid
    assert moteur.est_vivant()

    moteur.arreter()
    assert not moteur.est_vivant()

    # Verification independante de l'objet : le systeme ne doit plus connaitre
    # ce processus.
    sortie = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    assert str(pid) not in sortie, f"processus {pid} toujours vivant"


def test_enumeration_des_processus_fonctionne():
    """Garde-fou : la detection ne doit pas echouer en silence.

    La premiere version s'appuyait sur `wmic`, absent des Windows 11 recents.
    Elle renvoyait donc toujours une liste vide, et le nettoyage des orphelins
    ne faisait rien — sans le moindre message. On verifie ici que
    l'enumeration voit bien des processus, en cherchant celui du test.
    """
    import os
    chemin = stt._chemin_du_processus(os.getpid())
    assert chemin, "impossible de lire le chemin de notre propre processus"
    assert chemin.lower().endswith(".exe")


def test_aucun_orphelin_hors_de_notre_dossier_nest_signale():
    """On ne doit jamais toucher a un binaire homonyme lance par autre chose."""
    for pid in stt.orphelins_du_moteur():
        chemin = stt._chemin_du_processus(pid)
        assert chemin and chemin.lower() == str(
            cfg.MOTEUR / "whisper-server.exe").lower()


def test_job_suicide_se_cree():
    job = stt.creer_job_suicide()
    assert job, "impossible de creer le job — le moteur pourrait survivre"
    stt.kernel32.CloseHandle(job)


@pytest.mark.lent
@besoin_moteur
def test_le_moteur_meurt_avec_un_parent_tue_brutalement(conf, tmp_path):
    """Le defaut rencontre au premier lancement reel.

    Fermer la console par la croix tuait l'application sans executer son arret
    propre, et le moteur restait vivant a occuper le port. Le job object doit
    garantir sa mort meme dans ce cas.
    """
    port = 8753
    code = (
        "import sys, time;"
        f"sys.path.insert(0, {str(cfg.RACINE)!r});"
        "from murmur import config, stt;"
        "c = config.charger();"
        f"c.definir('moteur.port', {port});"
        "c.definir('langue', 'en');"
        "m = stt.Moteur(c);"
        "m.demarrer();"
        "print(m._processus.pid, flush=True);"
        "time.sleep(120)"
    )
    environnement = {**os.environ, cfg.VAR_DONNEES: str(tmp_path / "donnees")}
    parent = subprocess.Popen([sys.executable, "-c", code], env=environnement,
                              stdout=subprocess.PIPE, text=True)
    try:
        ligne = parent.stdout.readline().strip()
        assert ligne.isdigit(), f"le parent n'a pas demarre le moteur : {ligne!r}"
        pid_moteur = int(ligne)
        assert stt._chemin_du_processus(pid_moteur), "moteur introuvable"

        parent.kill()          # arret brutal : aucun code de nettoyage ne tourne
        parent.wait(timeout=5)

        # Le job doit avoir emporte le moteur.
        limite = time.monotonic() + 8
        while time.monotonic() < limite:
            if stt._chemin_du_processus(pid_moteur) is None:
                break
            time.sleep(0.2)
        else:
            pytest.fail(f"le moteur {pid_moteur} a survecu a la mort du parent")
    finally:
        if parent.poll() is None:
            parent.kill()
        # Seulement ce que ce test a cree. Sans le filtre, le menage
        # emportait le moteur d'une application en cours d'utilisation :
        # chaque execution de la suite en tuait un.
        stt.tuer_orphelins([pid_moteur])


@pytest.mark.lent
@besoin_moteur
def test_un_orphelin_est_recupere_au_demarrage(conf):
    """Un port pris par un moteur a nous ne doit pas exiger d'intervention.

    On garde volontairement le handle du job ouvert : le fermer tuerait le
    moteur sur-le-champ, c'est precisement sa raison d'etre. On se contente
    d'oublier le processus, comme le ferait un parent disparu.
    """
    premier = stt.Moteur(conf)
    premier.demarrer()
    pid_orphelin = premier._processus.pid
    poignee_job = premier._job
    premier._job = None          # on garde le handle ouvert, sans le fermer
    premier._processus = None    # le moteur n'est plus suivi par personne

    try:
        assert pid_orphelin in stt.orphelins_du_moteur(), \
            "l'orphelin doit etre detecte"
        assert not stt.port_disponible(conf["moteur.hote"], conf["moteur.port"])

        second = stt.Moteur(conf)
        try:
            second.demarrer()    # doit nettoyer l'orphelin et reussir
            assert second.est_vivant()
            assert pid_orphelin not in stt.orphelins_du_moteur()
        finally:
            second.arreter()
    finally:
        if poignee_job:
            stt.kernel32.CloseHandle(poignee_job)
        stt.tuer_orphelins([pid_orphelin])


@pytest.mark.lent
@besoin_moteur
def test_un_port_pris_par_un_tiers_est_signale_sans_confusion(conf, monkeypatch):
    """Ne pas accuser un orphelin quand le coupable est un autre programme.

    L'hypothese du test — nous n'avons aucun moteur qui traine — est posee
    explicitement plutot que subie. Elle dependait de l'etat des processus de
    la machine : un moteur laisse par un test precedent, meme en train de
    s'eteindre, etait compte comme orphelin et changeait le message. Ce test
    echouait ainsi une fois sur trois, dans la suite complete seulement.
    """
    import socket

    monkeypatch.setattr(stt, "tuer_orphelins", lambda *_a, **_k: [])

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as intrus:
        intrus.bind((conf["moteur.hote"], 0))
        intrus.listen(5)
        conf.definir("moteur.port", intrus.getsockname()[1])

        moteur = stt.Moteur(conf)
        with pytest.raises(stt.ErreurMoteur) as info:
            moteur.demarrer()

    message = str(info.value)
    assert "autre programme" in message, \
        "le message doit distinguer un tiers d'un orphelin a nous"


@pytest.mark.lent
@besoin_moteur
def test_demarrage_est_idempotent(conf):
    """Appeler demarrer() deux fois ne doit pas lancer deux serveurs."""
    with stt.Moteur(conf) as moteur:
        premier = moteur._processus.pid
        moteur.demarrer()
        assert moteur._processus.pid == premier


@pytest.mark.lent
@besoin_moteur
@besoin_echantillon
def test_le_modele_reste_charge_entre_deux_dictees(conf):
    """Interet de l'architecture : la seconde dictee ne recharge pas le modele.

    C'est la mesure qui justifie le serveur resident plutot qu'un appel a
    whisper-cli : sans lui, chaque dictee paierait ~800 ms de chargement.
    """
    import time
    audio = ECHANTILLON.read_bytes()
    with stt.Moteur(conf) as moteur:
        moteur.transcrire(audio)          # prechauffage
        debut = time.perf_counter()
        moteur.transcrire(audio)
        duree = (time.perf_counter() - debut) * 1000

    # 11 s d'audio : mesure a ~250 ms en T0. On laisse une marge large, le
    # but est de detecter un rechargement complet du modele, pas de mesurer
    # finement.
    assert duree < 900, f"{duree:.0f} ms — le modele semble recharge a chaque fois"


# --------------------------------------------------------------------------
# Repli sur le processeur
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_le_repli_ajoute_no_gpu(conf):
    """`--no-gpu` est le levier : mesure sur ce poste, le moteur repond en
    moins de dix secondes ainsi lance, la ou il refusait de demarrer."""
    moteur = stt.Moteur(conf)

    assert "--no-gpu" not in moteur._arguments()
    assert "--no-gpu" in moteur._arguments(sans_gpu=True)


@pytest.mark.materiel
def test_un_echec_avec_la_carte_fait_reessayer_sans(conf, monkeypatch):
    """Une machine sans Vulkan exploitable doit dicter lentement plutot que
    ne pas demarrer du tout.

    Mesure sur le poste de developpement : huit secondes de parole demandent
    250 ms avec la carte graphique et 9 400 ms sans. Le repli est un secours,
    pas un mode d'usage.
    """
    moteur = stt.Moteur(conf)
    essais = []

    def demarrage_double():
        essais.append(moteur._sans_gpu)
        if not moteur._sans_gpu:
            raise stt.ErreurMoteur("carte indisponible")

    monkeypatch.setattr(moteur, "_demarrer_une_fois", demarrage_double)
    moteur.demarrer()

    assert essais == [False, True], "le repli n'a pas eu lieu"
    assert moteur._sans_gpu


@pytest.mark.materiel
def test_le_repli_ne_boucle_pas(conf, monkeypatch):
    """S'il echoue aussi sans la carte, l'erreur remonte — on ne reessaie pas
    indefiniment un moteur qui ne demarre pas."""
    moteur = stt.Moteur(conf)
    essais = []

    def toujours_en_echec():
        essais.append(moteur._sans_gpu)
        raise stt.ErreurMoteur("rien n'y fait")

    monkeypatch.setattr(moteur, "_demarrer_une_fois", toujours_en_echec)
    with pytest.raises(stt.ErreurMoteur):
        moteur.demarrer()

    assert essais == [False, True]


@pytest.mark.materiel
def test_le_repli_peut_etre_refuse(conf, monkeypatch):
    """Qui prefere savoir que sa carte ne repond plus doit pouvoir le
    choisir : une dictee douze fois plus lente ne passe pas inapercue, mais
    elle ne dit pas pourquoi."""
    conf.definir("moteur.repli_processeur", False)
    moteur = stt.Moteur(conf)
    essais = []

    def toujours_en_echec():
        essais.append(moteur._sans_gpu)
        raise stt.ErreurMoteur("carte indisponible")

    monkeypatch.setattr(moteur, "_demarrer_une_fois", toujours_en_echec)
    with pytest.raises(stt.ErreurMoteur):
        moteur.demarrer()

    assert essais == [False], "le repli a eu lieu malgre le reglage"


# --------------------------------------------------------------------------
# Choix de la carte graphique
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_la_carte_retenue_est_ecrite_sur_le_disque(conf, monkeypatch):
    """Sans ecriture, le choix serait refait a chaque session — et un choix
    corrige a la main ne survivrait pas a la fermeture."""
    from murmur import vulkan

    cartes = vulkan.analyser(
        "ggml_vulkan: 0 = Circuit integre (X) | uma: 1 | matrix cores: none\n"
        "ggml_vulkan: 1 = Carte dediee (X) | uma: 0 | matrix cores: KHR_coopmat")
    monkeypatch.setattr("murmur.stt.vulkan.enumerer", lambda _s: cartes)
    conf.definir("moteur.device_vulkan", "auto")
    conf.definir("moteur.carte_vulkan", "")

    numero = stt.Moteur(conf)._carte_a_utiliser()

    assert numero == 1, "le circuit integre a ete pris"
    relue = cfg.charger()
    assert relue["moteur.carte_vulkan"] == "Carte dediee (X)"


@pytest.mark.materiel
def test_un_numero_pose_a_la_main_court_circuite_l_enumeration(conf,
                                                               monkeypatch):
    """Enumerer coute un quart de seconde : inutile quand la reponse est deja
    donnee."""
    appels = []
    monkeypatch.setattr("murmur.stt.vulkan.enumerer",
                        lambda _s: appels.append(1) or [])
    conf.definir("moteur.device_vulkan", 3)

    assert stt.Moteur(conf)._carte_a_utiliser() == 3
    assert appels == [], "l'enumeration a eu lieu pour rien"


@pytest.mark.materiel
def test_sans_carte_on_ne_restreint_rien(conf, monkeypatch):
    """Montrer au moteur une carte inexistante serait pire que ne rien dire."""
    monkeypatch.setattr("murmur.stt.vulkan.enumerer", lambda _s: [])
    conf.definir("moteur.device_vulkan", "auto")

    assert stt.Moteur(conf)._carte_a_utiliser() is None


# --------------------------------------------------------------------------
# Un seul demarrage a la fois
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_deux_fils_ne_lancent_pas_deux_moteurs(conf, monkeypatch):
    """La panne la plus couteuse du projet, et la plus discrete.

    Deux fils appellent `assurer_disponibilite` : le veilleur toutes les deux
    secondes, et le fil de traitement quand une dictee arrive. Le demarrage
    dure plusieurs secondes — chargement du modele — et commence par tuer les
    moteurs orphelins pour liberer le port.

    Le second fil trouvait donc le moteur « mort » (le processus n'est pas
    encore affecte), entrait a son tour, et **tuait le moteur que le premier
    venait de lancer**. Le journal comptait 211 relances ; par-dessus le
    marche, l'echec faisait basculer l'application sur le processeur, trente-
    sept fois plus lent, pour rien.
    """
    import threading

    moteur = stt.Moteur(conf)
    lances = []
    en_cours = threading.Event()

    def demarrage_lent():
        en_cours.set()
        time.sleep(0.4)          # chargement du modele
        lances.append(1)
        moteur._processus = _ProcessusVivant()

    monkeypatch.setattr(moteur, "_demarrer_une_fois", demarrage_lent)

    premier = threading.Thread(target=moteur.assurer_disponibilite)
    premier.start()
    en_cours.wait(timeout=2)
    second = threading.Thread(target=moteur.assurer_disponibilite)
    second.start()
    premier.join(timeout=5)
    second.join(timeout=5)

    assert lances == [1], f"{len(lances)} demarrages au lieu d'un"
    assert len(moteur._redemarrages) == 1, "une relance de trop a ete comptee"


class _ProcessusVivant:
    """Doublure de processus : vivant tant qu'on ne dit pas le contraire."""

    returncode = None

    def poll(self):
        return None


# --------------------------------------------------------------------------
# Ne tuer que ce qui tient le port
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_seul_le_processus_qui_tient_le_port_est_tue(conf, monkeypatch):
    """Le defaut qui expliquait le reste des relances du moteur.

    Liberer le port revenait a tuer TOUS les moteurs issus de notre dossier.
    Sur une machine de developpement, cela emportait le moteur de
    l'application en cours d'utilisation, qui ecoutait paisiblement sur un
    autre port — chaque execution de la suite de tests en tuait un.

    Invisible autrement que par la mesure : le dossier livre est une jonction
    NTFS vers celui du projet, et Windows resout la jonction quand on lui
    demande le chemin d'un processus.
    """
    import socket

    monkeypatch.setattr(stt, "orphelins_du_moteur", lambda: [111, 222])
    monkeypatch.setattr(stt, "proprietaire_du_port", lambda _p: 222)
    vises = []
    monkeypatch.setattr(stt, "tuer_orphelins",
                        lambda pids=None: vises.append(pids) or [])

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as intrus:
        intrus.bind((conf["moteur.hote"], 0))
        intrus.listen(5)
        conf.definir("moteur.port", intrus.getsockname()[1])
        with pytest.raises(stt.ErreurMoteur):
            stt.Moteur(conf).demarrer()

    # Deux passages : le demarrage reessaie une fois sans la carte
    # graphique. Chacun doit viser le seul detenteur du port.
    assert vises and all(v == [222] for v in vises), vises


@pytest.mark.materiel
def test_un_port_tenu_par_un_tiers_n_emporte_aucun_moteur(conf, monkeypatch):
    """Le port est pris par un programme qui n'est pas de nous : nos moteurs
    n'y sont pour rien et ne doivent pas mourir."""
    import socket

    monkeypatch.setattr(stt, "orphelins_du_moteur", lambda: [111])
    monkeypatch.setattr(stt, "proprietaire_du_port", lambda _p: 999)
    vises = []
    monkeypatch.setattr(stt, "tuer_orphelins",
                        lambda pids=None: vises.append(pids) or [])

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as intrus:
        intrus.bind((conf["moteur.hote"], 0))
        intrus.listen(5)
        conf.definir("moteur.port", intrus.getsockname()[1])
        with pytest.raises(stt.ErreurMoteur):
            stt.Moteur(conf).demarrer()

    assert vises == [], "un moteur etranger au conflit a ete tue"


@pytest.mark.materiel
def test_le_proprietaire_du_port_est_bien_trouve():
    """La lecture de la table TCP repond sur un port qu'on tient soi-meme."""
    import os
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prise:
        prise.bind(("127.0.0.1", 0))
        prise.listen(5)
        port = prise.getsockname()[1]

        assert stt.proprietaire_du_port(port) == os.getpid()

"""Moteur de transcription : cycle de vie du serveur whisper et client HTTP.

Le moteur tourne dans un processus separe (decision D1). Le modele est charge
une seule fois au demarrage : c'est ce qui fait passer la latence de ~1 000 ms
a ~250 ms par dictee. Un plantage du moteur n'emporte pas l'application, qui
peut le relancer.

Le dialogue passe par HTTP en boucle locale : environ une milliseconde, soit
un millieme du temps d'inference. Si cela devenait genant, seul ce module
serait a reecrire en liaison directe.
"""

from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import threading
import time
from ctypes import wintypes
from typing import Any

import requests

from . import config as configuration, crt, journal, vulkan

_log = journal.obtenir("stt")


class ErreurMoteur(Exception):
    """Le moteur de transcription est indisponible ou a echoue."""


# --------------------------------------------------------------------------
# Job Object : le moteur ne doit jamais survivre a l'application
# --------------------------------------------------------------------------

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong)]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


# Signatures explicites, indispensables sur 64 bits : sans `restype`, ctypes
# suppose un entier 32 bits et TRONQUE les handles renvoyes par Windows.
# Le defaut passe longtemps inapercu — les handles sont petits au debut d'un
# processus — puis corrompt tout des qu'ils depassent 2^31, ce qui arrive dans
# un executable empaquete. On manipule alors un handle qui ne designe plus le
# job, et fermer ce handle-la tue le moteur au lieu de le proteger.
kernel32.CreateJobObjectW.restype = wintypes.HANDLE
kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
kernel32.SetInformationJobObject.restype = wintypes.BOOL
kernel32.SetInformationJobObject.argtypes = (
    wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)


SEM_FAILCRITICALERRORS = 0x0001
SEM_NOOPENFILEERRORBOX = 0x8000


#: Codes que le chargeur de Windows renvoie quand un binaire ne peut pas
#: demarrer. Ils arrivent en decimal non signe par `subprocess`, ou ils ne
#: ressemblent plus a rien : « code 3221225781 » n'a jamais mis personne
#: sur la voie.
ECHECS_DU_CHARGEUR = {
    0xC0000135: ("une bibliotheque manque a cote du moteur"),
    0xC0000139: ("une bibliotheque presente n'a pas la bonne version"),
    0xC000007B: ("une bibliotheque n'est pas dans la bonne architecture (32/64 bits)"),
}


def _expliquer(code: int | None) -> str:
    """Rend le code de sortie lisible, quand il l'est."""
    if code is None:
        return "sans code"
    motif = ECHECS_DU_CHARGEUR.get(code & 0xFFFFFFFF)
    if motif is None:
        return f"code {code}"
    return f"{motif} — code 0x{code & 0xFFFFFFFF:08X}"


def taire_les_boites_de_windows() -> None:
    """Empeche Windows d'ouvrir une boite d'erreur pour le moteur.

    Quand une bibliotheque manque, le chargeur de Windows affiche de lui-meme
    « Impossible d'executer le code, car X.dll est introuvable » — une fenetre
    modale, au nom du moteur, que l'application ne controle pas et dont elle
    ne sait rien. C'est arrive sur machine vierge : deux boites a l'ecran, et
    le journal qui parlait d'un serveur muet.

    Le mode d'erreur est herite par les processus enfants : pose ici, il vaut
    pour le moteur. L'echec devient alors un code de sortie que l'on peut
    lire et expliquer, au lieu d'une fenetre a cliquer.
    """
    kernel32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX)


def creer_job_suicide():
    """Cree un job qui tue ses membres des que son handle se ferme.

    Sur Windows, un processus enfant survit par defaut a la mort de son
    parent. Si l'application est fermee par la croix de la console ou tuee, le
    moteur resterait donc vivant a occuper le port — c'est exactement ce qui
    s'est produit au premier essai reel.

    Le handle du job se ferme automatiquement a la disparition du processus,
    quelle qu'en soit la cause : le moteur meurt avec l'application, y compris
    en cas d'arret brutal.
    """
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None

    infos = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    infos.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(
        job, JobObjectExtendedLimitInformation,
        ctypes.byref(infos), ctypes.sizeof(infos))
    if not ok:
        kernel32.CloseHandle(job)
        return None
    return job


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001

kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD))
kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE,
                                        ctypes.POINTER(wintypes.DWORD))
kernel32.K32EnumProcesses.argtypes = (
    ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD))


STILL_ACTIVE = 259


def _chemin_du_processus(pid: int) -> str | None:
    """Chemin de l'executable, ou None si le processus n'est plus vivant.

    Un processus termine reste enumerable tant qu'un handle reste ouvert sur
    lui — le notre, ou celui du job object. Son chemin est encore lisible : le
    prendre pour un processus vivant faisait signaler des orphelins
    imaginaires. On verifie donc son code de sortie.
    """
    poignee = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not poignee:
        return None
    try:
        code = wintypes.DWORD()
        if (kernel32.GetExitCodeProcess(poignee, ctypes.byref(code))
                and code.value != STILL_ACTIVE):
            return None

        tampon = ctypes.create_unicode_buffer(32768)
        taille = wintypes.DWORD(32768)
        if kernel32.QueryFullProcessImageNameW(poignee, 0, tampon,
                                               ctypes.byref(taille)):
            return tampon.value
        return None
    finally:
        kernel32.CloseHandle(poignee)


def orphelins_du_moteur() -> list[int]:
    """PID des whisper-server issus de notre dossier engine/.

    On ne s'interesse qu'aux notres : un binaire homonyme lance par autre
    chose ne doit jamais etre touche.

    L'enumeration passe par les API natives et non par `wmic`, absent des
    Windows 11 recents — s'appuyer dessus aurait produit un nettoyage qui
    echoue en silence.
    """
    attendu = str(configuration.MOTEUR / "whisper-server.exe").lower()

    capacite = 4096
    tableau = (wintypes.DWORD * capacite)()
    octets = wintypes.DWORD()
    if not kernel32.K32EnumProcesses(tableau, ctypes.sizeof(tableau),
                                     ctypes.byref(octets)):
        return []

    nombre = octets.value // ctypes.sizeof(wintypes.DWORD)
    trouves = []
    for indice in range(nombre):
        pid = tableau[indice]
        if not pid:
            continue
        chemin = _chemin_du_processus(pid)
        if chemin and chemin.lower() == attendu:
            trouves.append(pid)
    return trouves


def tuer_orphelins(pids: list[int] | None = None) -> list[int]:
    """Termine les moteurs restes en vie. Renvoie les PID effectivement tues.

    `pids` restreint l'action a une liste precise. Sans ce filtre, on tuerait
    aussi une instance de Murmur legitimement en cours d'utilisation.
    """
    tues = []
    for pid in (pids if pids is not None else orphelins_du_moteur()):
        poignee = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if not poignee:
            continue
        try:
            if kernel32.TerminateProcess(poignee, 1):
                tues.append(pid)
        finally:
            kernel32.CloseHandle(poignee)
    if tues:
        time.sleep(0.4)  # laisse le systeme liberer le port
    return tues


def port_disponible(hote: str, port: int) -> bool:
    """Vrai si l'on peut ouvrir un serveur sur ce port.

    On tente un bind, pas une connexion : c'est la question reellement posee
    avant de demarrer. Une detection par connexion donne un faux negatif quand
    le backlog du socket distant est plein, et repond de toute facon a une
    autre question.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prise:
        try:
            prise.bind((hote, port))
            return True
        except OSError:
            return False


def serveur_repond(hote: str, port: int, timeout: float = 0.3) -> bool:
    """Vrai si quelque chose accepte les connexions sur ce port.

    Utilise pour attendre que le moteur soit pret : il charge le modele avant
    de se mettre a ecouter.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prise:
        prise.settimeout(timeout)
        return prise.connect_ex((hote, port)) == 0


class Moteur:
    """Pilote whisper-server : demarrage, transcription, arret.

    S'utilise de preference comme gestionnaire de contexte, ce qui garantit
    l'arret du processus enfant meme en cas d'exception.
    """

    def __init__(self, conf: configuration.Config):
        self.conf = conf
        self._processus: subprocess.Popen | None = None
        self._journal = None
        self._job = None
        self.hote: str = conf["moteur.hote"]
        self.port: int = conf["moteur.port"]
        #: Horodatage des redemarrages automatiques, pour borner l'acharnement.
        self._redemarrages: list[float] = []
        #: Le moteur tourne-t-il en repli, sur le processeur ? Une fois pose,
        #: le repli tient pour la session : reessayer la carte a chaque
        #: demarrage ferait payer l'echec autant de fois.
        self._sans_gpu = False
        #: Un seul demarrage a la fois. Voir `demarrer` : deux fils lancent le
        #: moteur, et sans ce verrou le second tuait celui du premier.
        self._demarrage = threading.RLock()

    # -- cycle de vie ------------------------------------------------------

    def _arguments(self, sans_gpu: bool = False) -> list[str]:
        conf = self.conf
        args = [
            str(conf.chemin_serveur),
            "--model", str(conf.chemin_modele),
            "--host", self.hote,
            "--port", str(self.port),
            "--language", conf["langue"],
            "--no-timestamps",
        ]
        if conf["vad.actif"]:
            args += [
                "--vad",
                "--vad-model", str(conf.chemin_modele_vad),
                "--vad-threshold", str(conf["vad.seuil"]),
                "--vad-min-speech-duration-ms", str(conf["vad.min_parole_ms"]),
                "--vad-min-silence-duration-ms", str(conf["vad.min_silence_ms"]),
            ]
        if conf["vad.suppress_nst"]:
            args.append("--suppress-nst")
        if sans_gpu:
            args.append("--no-gpu")
        return args

    def _carte_a_utiliser(self) -> int | None:
        """Numero de la carte graphique a montrer au moteur, pour CE demarrage.

        Rend `None` quand il n'y a rien a montrer — aucune carte, ou repli sur
        le processeur : on laisse alors l'environnement tel quel plutot que de
        restreindre la vue du moteur a un peripherique inexistant.

        Le choix est refait a chaque demarrage, mais il est GUIDE par le nom
        retenu la fois precedente : c'est ce qui permet de respecter une carte
        choisie a la main tout en survivant a un ordre d'enumeration qui
        change. Deux cent trente millisecondes d'enumeration, une fois par
        demarrage du moteur.
        """
        if self._sans_gpu:
            return None

        demande = self.conf["moteur.device_vulkan"]
        if isinstance(demande, int):
            return demande

        cartes = vulkan.enumerer(self.conf.chemin_serveur)
        if not cartes:
            return None

        retenue = vulkan.retrouver(cartes, self.conf["moteur.carte_vulkan"])
        if retenue is None:
            retenue = vulkan.choisir(cartes)
            if retenue is None:
                return None
            self.conf.definir("moteur.carte_vulkan", retenue.nom)
            # Ecrit sur le disque : sans cela le choix serait refait a chaque
            # session, et surtout un choix corrige a la main ne survivrait pas
            # a la fermeture de l'application.
            self.conf.sauvegarder()
            _log.info("carte graphique retenue : %s (parmi %d)",
                      retenue.nom, len(cartes))
        return retenue.numero

    def _verifier_fichiers(self) -> None:
        manquants = [
            (nom, chemin) for nom, chemin in (
                ("serveur", self.conf.chemin_serveur),
                ("modele", self.conf.chemin_modele),
            ) if not chemin.exists()
        ]
        if self.conf["vad.actif"] and not self.conf.chemin_modele_vad.exists():
            manquants.append(("modele VAD", self.conf.chemin_modele_vad))

        # La bibliotheque C++ que le moteur importe. Absente, il ne demarre
        # pas : Windows ouvre sa propre boite d'erreur, l'attente expire trente
        # secondes plus tard, et le message parle alors du serveur qui n'a pas
        # repondu — ce qui est vrai, et n'apprend rien. On le dit ici.
        # Les bibliotheques Visual C++ que la construction a declare livrer.
        # Absentes, le moteur ne demarre pas : Windows ouvre sa propre boite
        # d'erreur, l'attente expire trente secondes plus tard, et le message
        # parle alors du serveur qui n'a pas repondu — exact, et sans rapport
        # avec la cause. On le dit ici, avant d'attendre pour rien.
        attendues = crt.lire_manifeste(configuration.MOTEUR)
        manquants += [(f"bibliotheque C++ ({nom})", configuration.MOTEUR / nom)
                      for nom in crt.manquants(configuration.MOTEUR, attendues)]

        if manquants:
            details = "\n".join(f"    {nom} : {chemin}" for nom, chemin in manquants)
            raise ErreurMoteur(f"fichier(s) introuvable(s) dans engine/ :\n{details}")

    def _liberer_le_port(self, tentatives: int = 4, pause: float = 0.5) -> None:
        """S'assure que le port est prenable, en corrigeant ce qui est de notre fait.

        Deux causes distinctes, deux remedes :

        - un moteur a nous survit a un arret brutal : on le termine, plutot
          que d'exiger une intervention manuelle pour un desordre dont nous
          sommes la cause ;
        - le port est encore retenu par des connexions en TIME_WAIT juste
          apres un arret : personne ne le detient, il faut seulement laisser
          au systeme le temps de le rendre.
        """
        if port_disponible(self.hote, self.port):
            return

        tues = tuer_orphelins()

        for essai in range(tentatives):
            if port_disponible(self.hote, self.port):
                return
            time.sleep(pause)

        if tues:
            details = (f" {len(tues)} moteur(s) orphelin(s) ont ete termines, "
                       f"mais le port reste pris apres "
                       f"{tentatives * pause:.0f} s.")
        else:
            details = (f" Aucun moteur de Murmur ne le detient : un autre "
                       f"programme l'utilise.")
        raise ErreurMoteur(
            f"le port {self.port} est deja occupe.{details} Change "
            f"moteur.port dans la configuration.")

    def demarrer(self) -> None:
        """Lance le moteur, en se repliant sur le processeur s'il le faut.

        Le repli n'est pas un mode d'usage : mesure sur le poste de
        developpement, huit secondes de parole demandent 250 ms avec la carte
        graphique et 9 400 ms sans. Mais une machine sans Vulkan exploitable
        doit dicter lentement plutot que ne pas demarrer du tout.
        """
        with self._demarrage:
            # Reteste a l'interieur du verrou : le fil qui attendait ici
            # pendant qu'un autre demarrait n'a plus rien a faire.
            if self.est_vivant():
                return

            try:
                self._demarrer_une_fois()
                return
            except ErreurMoteur:
                if self._sans_gpu or not self.conf["moteur.repli_processeur"]:
                    raise

            self._sans_gpu = True
            self._demarrer_une_fois()

    def _demarrer_une_fois(self) -> None:
        self._verifier_fichiers()

        self._liberer_le_port()

        # Le journal du moteur est indispensable au diagnostic : sans lui, un
        # echec de demarrage ne laisse aucune trace exploitable.
        chemin_journal = configuration.dossier_journaux() / "moteur.log"
        self._journal = chemin_journal.open("a", encoding="utf-8", errors="replace")
        self._journal.write(f"\n{'=' * 70}\ndemarrage {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        self._journal.flush()

        # On ne montre au moteur que la carte retenue : elle devient alors la
        # seule qu'il voit, et son numero interne n'a plus d'importance.
        env = os.environ.copy()
        numero = self._carte_a_utiliser()
        if numero is not None:
            env["GGML_VK_VISIBLE_DEVICES"] = str(numero)

        taire_les_boites_de_windows()

        try:
            self._processus = subprocess.Popen(
                self._arguments(sans_gpu=self._sans_gpu),
                stdout=self._journal, stderr=subprocess.STDOUT,
                cwd=str(configuration.MOTEUR), env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            self._fermer_journal()
            raise ErreurMoteur(f"impossible de lancer le serveur : {exc}") from exc

        # Rattache le moteur a un job suicidaire : il mourra avec nous, meme
        # si l'application est fermee par la croix ou tuee.
        self._job = creer_job_suicide()
        if self._job:
            poignee = int(self._processus._handle)
            if not kernel32.AssignProcessToJobObject(self._job, poignee):
                erreur = ctypes.get_last_error()
                # Sans job, on retombe sur l'arret explicite : moins robuste,
                # mais pas bloquant. tuer_orphelins() rattrapera au prochain
                # demarrage. L'echec est journalise : silencieux, il laisserait
                # croire la protection active alors qu'elle ne l'est pas.
                self._journal.write(
                    f"AVERTISSEMENT: rattachement au job impossible "
                    f"(code {erreur}) — le moteur peut survivre a un arret "
                    f"brutal\n")
                self._journal.flush()
                kernel32.CloseHandle(self._job)
                self._job = None
        else:
            self._journal.write("AVERTISSEMENT: creation du job impossible\n")
            self._journal.flush()

        self._attendre_disponibilite()

    def _attendre_disponibilite(self) -> None:
        """Attend que le serveur ecoute — il charge le modele avant cela."""
        limite = time.monotonic() + self.conf["moteur.demarrage_timeout_s"]
        while time.monotonic() < limite:
            if self._processus and self._processus.poll() is not None:
                code = self._processus.returncode
                self.arreter()
                raise ErreurMoteur(
                    f"le serveur s'est arrete au demarrage "
                    f"({_expliquer(code)}). "
                    f"Voir {configuration.dossier_journaux() / 'moteur.log'}."
                )
            if serveur_repond(self.hote, self.port):
                return
            time.sleep(0.15)

        self.arreter()
        raise ErreurMoteur(
            f"le serveur n'a pas repondu en "
            f"{self.conf['moteur.demarrage_timeout_s']:.0f} s. "
            f"Voir {configuration.dossier_journaux() / 'moteur.log'}."
        )

    def est_vivant(self) -> bool:
        return self._processus is not None and self._processus.poll() is None

    def _fermer_journal(self) -> None:
        if self._journal:
            try:
                self._journal.close()
            finally:
                self._journal = None

    def arreter(self, delai: float = 5.0) -> None:
        """Arrete le serveur, sans laisser de processus orphelin."""
        processus, self._processus = self._processus, None
        if processus is not None and processus.poll() is None:
            processus.terminate()
            try:
                processus.wait(timeout=delai)
            except subprocess.TimeoutExpired:
                processus.kill()
                processus.wait(timeout=delai)

        job, self._job = self._job, None
        if job:
            kernel32.CloseHandle(job)  # tue ce qui resterait du job
        self._fermer_journal()

    # -- resilience --------------------------------------------------------

    def _redemarrages_recents(self) -> int:
        fenetre = self.conf["moteur.fenetre_redemarrages_s"]
        maintenant = time.monotonic()
        self._redemarrages = [t for t in self._redemarrages
                              if maintenant - t < fenetre]
        return len(self._redemarrages)

    def assurer_disponibilite(self) -> bool:
        """Relance le moteur s'il est tombe. Vrai s'il est utilisable.

        Le plafond n'est pas une precaution de style : un moteur qui meurt en
        boucle signale une panne de fond — modele corrompu, pilote instable,
        memoire insuffisante. S'acharner la masquerait et consommerait la
        machine, alors qu'un message clair permet d'agir.
        """
        if self.est_vivant():
            return True

        with self._demarrage:
            # Un demarrage etait peut-etre en cours : on a attendu ici, il a
            # abouti, il n'y a plus rien a relancer. Sans ce controle, chaque
            # fil en attente comptait une relance de plus et repartait pour un
            # tour — c'est ainsi que naissaient les rafales.
            if self.est_vivant():
                return True

            maximum = self.conf["moteur.max_redemarrages"]
            if self._redemarrages_recents() >= maximum:
                return False

            self._redemarrages.append(time.monotonic())
            # Le processus precedent est mort, mais son port peut trainer.
            self._processus = None
            try:
                self.demarrer()
                return True
            except ErreurMoteur:
                return False

    @property
    def epuise(self) -> bool:
        """Le plafond de redemarrages est-il atteint ?"""
        return self._redemarrages_recents() >= self.conf["moteur.max_redemarrages"]

    def __enter__(self) -> Moteur:
        self.demarrer()
        return self

    def __exit__(self, *_) -> None:
        self.arreter()

    # -- transcription -----------------------------------------------------

    def transcrire(self, wav: bytes, prompt: str | None = None,
                   timeout: float = 60.0) -> str:
        """Transcrit un WAV 16 kHz mono et renvoie le texte, deja nettoye.

        Le prompt de conditionnement est accepte par requete : c'est ce qui
        permet un lexique different selon l'application active, sans jamais
        redemarrer le serveur.
        """
        if not self.est_vivant():
            # Une dictee ne doit pas etre perdue parce que le moteur est tombe
            # entre-temps : on le relance et on poursuit.
            if not self.assurer_disponibilite():
                raise ErreurMoteur(
                    "le moteur est indisponible et n'a pas pu etre relance "
                    f"({self._redemarrages_recents()} tentative(s) recente(s)). "
                    f"Voir {configuration.dossier_journaux() / 'moteur.log'}.")

        champs: dict[str, Any] = {
            "temperature": "0.0",
            "response_format": "json",
            "language": self.conf["langue"],
        }
        if prompt:
            champs["prompt"] = prompt

        try:
            reponse = requests.post(
                f"{self.conf.url_moteur}/inference",
                files={"file": ("dictee.wav", wav, "audio/wav")},
                data=champs, timeout=timeout,
            )
        except requests.RequestException as exc:
            raise ErreurMoteur(f"le moteur n'a pas repondu : {exc}") from exc

        if reponse.status_code != 200:
            raise ErreurMoteur(
                f"le moteur a renvoye {reponse.status_code} : "
                f"{reponse.text[:200]}")

        try:
            texte = reponse.json().get("text", "")
        except ValueError:
            texte = reponse.text

        return " ".join(texte.split())

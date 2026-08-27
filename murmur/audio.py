"""Capture micro et encodage WAV.

Le module est coupe en deux : des fonctions pures (encodage, mesure) qui se
testent sans materiel, et l'enregistreur qui parle au peripherique. Cette
separation compte — sans elle, la moindre verification demanderait un micro
branche et un humain pour parler dedans.

Format impose par whisper : 16 kHz, mono, PCM 16 bits.

QUELLE INTERFACE AUDIO, ET POURQUOI CELA COMPTE

Windows en expose quatre. PortAudio choisit MME par defaut, et MME accepte
n'importe quel taux — 16 kHz compris — ce qui evite un reechantillonnage.
C'est tentant, et c'est un piege : MME travaille sur une **table de
peripheriques figee au chargement**. Tout ce qui remanie les peripheriques
ensuite — un egaliseur comme FxSound qui interpose son peripherique virtuel,
un casque qui se reconnecte — la laisse perimee. Le flux s'ouvre alors sans
la moindre erreur sur une entree qui n'existe plus vraiment, et rend du
silence. C'est exactement ce qu'on lisait dans le journal : « rms 0.0000 »,
capture apres capture, sans qu'aucun garde-fou ne se declenche — il n'y avait
rien a rattraper, l'ouverture avait reussi.

On passe donc par WASAPI, qui suit le peripherique par defaut du systeme.
WASAPI, lui, impose le taux natif de la carte (48 kHz le plus souvent) et
refuse tout autre : « Invalid sample rate ». D'ou le reechantillonnage vers
16 kHz, fait ici. Il coute quelques millisecondes sur une dictee et rend le
micro fiable, ce qui n'est pas un echange discutable.

MME reste en secours : mieux vaut une entree figee qu'aucune entree.
"""

from __future__ import annotations

import io
import threading
import wave
from dataclasses import dataclass

import numpy as np

from . import config as configuration, journal

_log = journal.obtenir("audio")

TAUX = 16000
CANAUX = 1
LARGEUR_OCTETS = 2  # PCM 16 bits

#: Interfaces audio de Windows, dans l'ordre de preference. WASAPI d'abord :
#: c'est la seule qui suive le peripherique par defaut du systeme.
INTERFACES = ("Windows WASAPI", "Windows DirectSound", "MME")


class ErreurAudio(Exception):
    """Le peripherique de capture est indisponible ou a echoue."""


# --------------------------------------------------------------------------
# Fonctions pures
# --------------------------------------------------------------------------

def rms(echantillons: np.ndarray) -> float:
    """Energie efficace du signal, entre 0 et 1.

    Sert au garde anti-declenchement (T2.1) et a l'indicateur d'etat : un
    appui accidentel produit un RMS quasi nul, qu'on rejette avant meme
    d'envoyer quoi que ce soit au moteur.
    """
    if echantillons.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(echantillons, dtype=np.float64))))


def duree_ms(echantillons: np.ndarray, taux: int = TAUX) -> float:
    return len(echantillons) * 1000.0 / taux


def vers_pcm16(echantillons: np.ndarray) -> np.ndarray:
    """Convertit du flottant [-1, 1] en entiers 16 bits.

    L'ecretage est explicite : sans lui, un signal sature deborderait et
    produirait un bruit violent par repliement, au lieu d'une simple
    distorsion.
    """
    ecrete = np.clip(echantillons, -1.0, 1.0)
    return (ecrete * 32767.0).astype(np.int16)


def encoder_wav(echantillons: np.ndarray, taux: int = TAUX) -> bytes:
    """Produit un WAV complet en memoire, sans passer par un fichier."""
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as fichier:
        fichier.setnchannels(CANAUX)
        fichier.setsampwidth(LARGEUR_OCTETS)
        fichier.setframerate(taux)
        fichier.writeframes(vers_pcm16(echantillons).tobytes())
    return tampon.getvalue()


@dataclass(frozen=True)
class Capture:
    """Resultat d'un enregistrement."""

    echantillons: np.ndarray
    taux: int

    @property
    def duree_ms(self) -> float:
        return duree_ms(self.echantillons, self.taux)

    @property
    def rms(self) -> float:
        return rms(self.echantillons)

    @property
    def wav(self) -> bytes:
        return encoder_wav(self.echantillons, self.taux)

    @property
    def vide(self) -> bool:
        return self.echantillons.size == 0


def reechantillonner(x: np.ndarray, de: int, vers: int) -> np.ndarray:
    """Ramene un signal de `de` Hz a `vers` Hz.

    En deux temps, et le premier n'est pas facultatif : on coupe d'abord tout
    ce qui depasse la moitie du nouveau taux, sinon ces frequences ne
    disparaissent pas — elles se **replient** dans la bande utile et s'y
    ajoutent au signal sous forme de sifflements, que le modele entend comme
    des mots. On reechantillonne ensuite par interpolation lineaire, ce qui
    accepte les rapports non entiers (44 100 vers 16 000).

    La reduction seule, sans filtre, coute moins cher et s'entend tout de
    suite : c'est l'erreur classique.
    """
    if de == vers or x.size == 0:
        return x.astype(np.float32, copy=False)

    if vers < de:
        x = _passe_bas(x, de, vers / 2.0)

    duree = x.size / de
    cible = int(round(duree * vers))
    if cible <= 0:
        return np.zeros(0, dtype=np.float32)
    # Les deux grilles partent du meme instant zero : un decalage d'un demi
    # echantillon ne s'entend pas, mais fausserait les tests de duree.
    grille = np.linspace(0.0, x.size - 1, cible, dtype=np.float64)
    return np.interp(grille, np.arange(x.size), x).astype(np.float32)


#: Longueur du filtre anti-repliement, en echantillons. Un noyau plus court
#: laisse passer une partie de ce qu'il devait couper ; plus long, il coute
#: sans rien apporter d'audible sur de la parole.
NOYAU = 129


def _passe_bas(x: np.ndarray, taux: int, coupure: float) -> np.ndarray:
    """Sinus cardinal fenetre par Hamming, applique par convolution."""
    if coupure >= taux / 2.0:
        return x
    rangs = np.arange(NOYAU, dtype=np.float64) - (NOYAU - 1) / 2.0
    reduite = coupure / taux                      # frequence reduite
    noyau = 2.0 * reduite * np.sinc(2.0 * reduite * rangs)
    noyau *= np.hamming(NOYAU)
    noyau /= noyau.sum()
    # « same » garde la duree du signal : « valid » la raccourcirait du noyau.
    return np.convolve(x.astype(np.float64), noyau, mode="same")


def choisir_entree(sounddevice, demande=None) -> tuple:
    """(peripherique, taux de capture) a utiliser.

    Un peripherique explicitement choisi dans les reglages est respecte tel
    quel : c'est une decision de l'utilisateur, pas une valeur par defaut a
    optimiser. Sinon on prend l'entree par defaut de la premiere interface
    disponible, et son taux natif.
    """
    if demande is not None:
        return demande, TAUX

    try:
        interfaces = {api["name"]: api for api in sounddevice.query_hostapis()}
    except Exception:
        _log.debug("interfaces audio illisibles", exc_info=True)
        return None, TAUX

    for nom in INTERFACES:
        api = interfaces.get(nom)
        if api is None:
            continue
        index = api.get("default_input_device", -1)
        if index is None or index < 0:
            continue
        try:
            taux = int(round(sounddevice.query_devices(index)
                             ["default_samplerate"])) or TAUX
        except Exception:
            taux = TAUX
        return index, taux

    return None, TAUX


# --------------------------------------------------------------------------
# Enregistreur
# --------------------------------------------------------------------------

class Enregistreur:
    """Capture le micro entre un demarrage et un arret.

    Le rappel audio tourne sur un fil temps reel : il ne fait qu'empiler des
    blocs, sans allocation lourde ni calcul. Tout le traitement a lieu a
    l'arret.
    """

    def __init__(self, conf: configuration.Config):
        self.conf = conf
        self.taux: int = conf["audio.taux"]
        self._duree_max = conf["audio.duree_max_s"]

        self._flux = None
        #: Taux auquel la carte a reellement capture. WASAPI impose le sien,
        #: et il faudra en redescendre.
        self._taux_capture = self.taux
        self._blocs: list[np.ndarray] = []
        self._verrou = threading.Lock()
        self._rms_courant = 0.0
        self._sature = False
        self._debordement = False

    # -- etat --------------------------------------------------------------

    @property
    def peripherique(self):
        """Le micro choisi, relu a chaque acces.

        Relu et non retenu : le reglage peut changer pendant que
        l'application tourne, et un peripherique memorise a la construction
        survivrait au changement.
        """
        return self.conf["audio.peripherique"]

    @property
    def en_cours(self) -> bool:
        return self._flux is not None

    @property
    def rms_courant(self) -> float:
        """Niveau du dernier bloc : alimente l'indicateur et l'arret auto."""
        return self._rms_courant

    @property
    def echantillons_captures(self) -> int:
        with self._verrou:
            return sum(len(bloc) for bloc in self._blocs)

    # -- capture -----------------------------------------------------------

    def _rappel(self, donnees, _cadres, _horodatage, statut) -> None:
        if statut:
            # Un depassement signifie que des echantillons ont ete perdus.
            # On le retient pour le signaler a l'arret, sans rien afficher
            # depuis ce fil temps reel.
            self._debordement = True
        bloc = donnees[:, 0].copy()
        self._rms_courant = rms(bloc)
        if np.max(np.abs(bloc), initial=0.0) >= 0.999:
            self._sature = True
        with self._verrou:
            self._blocs.append(bloc)

    def demarrer(self) -> None:
        if self.en_cours:
            return

        import sounddevice  # importe tard : charge PortAudio

        with self._verrou:
            self._blocs = []
        self._rms_courant = 0.0
        self._sature = False
        self._debordement = False

        self._taux_capture = self.taux
        try:
            self._flux = self._ouvrir(sounddevice)
            self._flux.start()
        except Exception as exc:  # PortAudioError et consorts
            self._flux = None
            raise ErreurAudio(
                f"impossible d'ouvrir le micro : {exc}. Verifie qu'un "
                f"peripherique d'entree est branche et disponible."
            ) from exc

    def _ouvrir(self, sounddevice):
        """Ouvre le flux, en descendant les recours un par un.

        La liste des peripheriques est **refaite avant chaque capture**. Elle
        est dressee une fois pour toutes au chargement de PortAudio, et tout
        ce qui remanie les peripheriques ensuite — FxSound qui interpose son
        entree virtuelle, un casque qui se reconnecte — la laisse perimee. La
        refaire coute une soixantaine de millisecondes mesurees ; les payer a
        chaque dictee vaut mieux que d'enregistrer du silence sans le savoir.

        Ensuite, dans l'ordre : l'entree par defaut de la meilleure interface
        disponible, puis le defaut de PortAudio, puis — si un peripherique
        avait ete choisi dans les reglages et a disparu — le defaut tout
        court. Mieux vaut dicter dans un autre micro que ne pas dicter.
        """
        reenumerer(sounddevice)

        recours = []
        peripherique, taux = choisir_entree(sounddevice, self.peripherique)
        recours.append((peripherique, taux))
        if (peripherique, taux) != (None, self.taux):
            recours.append((None, self.taux))
        if self.peripherique is not None:
            recours.append((None, self.taux))

        derniere = None
        for peripherique, taux in recours:
            try:
                flux = self._flux_vers(sounddevice, peripherique, taux)
            except Exception as exc:
                derniere = exc
                _log.info("entree %r a %d Hz refusee : %s",
                          peripherique, taux, exc)
                continue
            self._taux_capture = taux
            return flux

        raise derniere if derniere is not None else ErreurAudio(
            "aucune entree audio disponible")

    def _flux_vers(self, sounddevice, peripherique, taux: int):
        return sounddevice.InputStream(
            samplerate=taux, channels=CANAUX, dtype="float32",
            device=peripherique, callback=self._rappel,
            blocksize=int(taux * 0.05),  # blocs de 50 ms
        )

    def arreter(self) -> Capture:
        """Arrete la capture et rend les echantillons accumules."""
        flux, self._flux = self._flux, None
        if flux is not None:
            try:
                flux.stop()
            finally:
                flux.close()

        with self._verrou:
            blocs, self._blocs = self._blocs, []

        echantillons = (np.concatenate(blocs) if blocs
                        else np.zeros(0, dtype=np.float32))

        # WASAPI n'accepte que le taux natif de la carte : on en redescend
        # ici, une fois, plutot qu'a chaque bloc dans le rappel temps reel.
        echantillons = reechantillonner(echantillons, self._taux_capture,
                                        self.taux)

        # Le mode bascule peut laisser tourner une capture oubliee : on borne
        # plutot que de rendre un enregistrement de plusieurs minutes.
        maximum = int(self._duree_max * self.taux)
        if len(echantillons) > maximum:
            echantillons = echantillons[:maximum]

        return Capture(echantillons=echantillons, taux=self.taux)

    @property
    def sature(self) -> bool:
        """Le signal a-t-il atteint la butee ? Utile pour conseiller un reglage."""
        return self._sature

    @property
    def debordement(self) -> bool:
        """Des echantillons ont-ils ete perdus faute d'etre consommes a temps ?"""
        return self._debordement

    def __enter__(self) -> Enregistreur:
        self.demarrer()
        return self

    def __exit__(self, *_) -> Capture | None:
        if self.en_cours:
            self.arreter()
        return None


def reenumerer(sounddevice=None) -> bool:
    """Refait la liste des peripheriques audio. Vrai si PortAudio a suivi.

    A appeler quand la liste est suspecte d'etre perimee — apres un echec
    d'ouverture, ou avant d'afficher les micros disponibles.
    """
    if sounddevice is None:
        import sounddevice
    try:
        sounddevice._terminate()
        sounddevice._initialize()
        return True
    except Exception:
        _log.debug("re-enumeration audio refusee", exc_info=True)
        return False


def peripheriques_entree(rafraichir: bool = True) -> list[dict]:
    """Liste les micros disponibles — pour la configuration et le diagnostic.

    La liste est refaite avant d'etre lue : sans cela, elle montrerait celle
    du chargement de PortAudio, d'ou l'absence d'un casque pourtant branche.
    """
    import sounddevice

    if rafraichir:
        reenumerer(sounddevice)
    try:
        return [
            {"index": index, "nom": info["name"],
             "canaux": info["max_input_channels"]}
            for index, info in enumerate(sounddevice.query_devices())
            if info["max_input_channels"] > 0
        ]
    except Exception as exc:
        raise ErreurAudio(f"impossible de lister les peripheriques : {exc}") from exc

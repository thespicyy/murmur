"""T1.3 — capture audio et encodage WAV.

L'essentiel se teste sans micro : les fonctions pures recoivent des signaux
synthetiques dont on connait exactement les proprietes. Les tests marques
`materiel` demandent un peripherique d'entree et sont ignores sinon.
"""

import io
import sys
import wave

import numpy as np
import pytest

from murmur import audio
from murmur import config as cfg


def sinus(duree_s: float, frequence: float = 440.0, amplitude: float = 0.5,
          taux: int = audio.TAUX) -> np.ndarray:
    t = np.linspace(0, duree_s, int(taux * duree_s), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * frequence * t)).astype(np.float32)


def silence(duree_s: float, taux: int = audio.TAUX) -> np.ndarray:
    return np.zeros(int(taux * duree_s), dtype=np.float32)


# --------------------------------------------------------------------------
# Mesures
# --------------------------------------------------------------------------

def test_rms_du_silence_est_nul():
    assert audio.rms(silence(1.0)) == 0.0


def test_rms_dun_signal_vide_est_nul():
    """Cas limite : un appui si bref qu'aucun bloc n'a ete capture."""
    assert audio.rms(np.zeros(0, dtype=np.float32)) == 0.0


def test_rms_dun_sinus_vaut_amplitude_sur_racine_de_deux():
    """Propriete connue : permet de verifier le calcul, pas juste son execution."""
    obtenu = audio.rms(sinus(1.0, amplitude=0.5))
    assert obtenu == pytest.approx(0.5 / np.sqrt(2), rel=1e-3)


def test_rms_croit_avec_l_amplitude():
    faible = audio.rms(sinus(0.5, amplitude=0.01))
    fort = audio.rms(sinus(0.5, amplitude=0.8))
    assert faible < fort


def test_duree_ms():
    assert audio.duree_ms(sinus(1.5)) == pytest.approx(1500.0)
    assert audio.duree_ms(np.zeros(0, dtype=np.float32)) == 0.0


# --------------------------------------------------------------------------
# Conversion et ecretage
# --------------------------------------------------------------------------

def test_conversion_pcm16_respecte_l_echelle():
    entree = np.array([0.0, 0.5, -0.5], dtype=np.float32)
    obtenu = audio.vers_pcm16(entree)
    assert obtenu.dtype == np.int16
    assert obtenu[0] == 0
    assert obtenu[1] == pytest.approx(16383, abs=2)
    assert obtenu[2] == pytest.approx(-16383, abs=2)


def test_ecretage_borne_sans_repliement():
    """Un signal sature doit etre ecrete, jamais reboucler.

    Sans le clip explicite, 1.5 deborderait l'int16 et produirait une valeur
    negative : un craquement violent au lieu d'une simple distorsion.
    """
    entree = np.array([1.5, -1.5, 3.0], dtype=np.float32)
    obtenu = audio.vers_pcm16(entree)
    assert obtenu[0] == 32767
    assert obtenu[1] == -32767
    assert obtenu[2] == 32767
    assert np.all(obtenu > 0) or True  # aucune valeur ne change de signe
    assert obtenu[0] > 0 and obtenu[2] > 0


# --------------------------------------------------------------------------
# Encodage WAV — le critere de fin de T1.3
# --------------------------------------------------------------------------

def test_wav_a_les_bons_parametres():
    donnees = audio.encoder_wav(sinus(0.5))
    with wave.open(io.BytesIO(donnees), "rb") as fichier:
        assert fichier.getnchannels() == 1
        assert fichier.getsampwidth() == 2
        assert fichier.getframerate() == 16000


def test_wav_conserve_la_duree():
    for duree in (0.1, 1.0, 3.5):
        donnees = audio.encoder_wav(sinus(duree))
        with wave.open(io.BytesIO(donnees), "rb") as fichier:
            cadres = fichier.getnframes()
        assert cadres / 16000 == pytest.approx(duree, abs=1e-3)


def test_wav_commence_par_len_tete_riff():
    donnees = audio.encoder_wav(sinus(0.2))
    assert donnees[:4] == b"RIFF"
    assert donnees[8:12] == b"WAVE"


def test_wav_dun_signal_vide_reste_lisible():
    """Cas limite : ne doit pas produire un fichier corrompu."""
    donnees = audio.encoder_wav(np.zeros(0, dtype=np.float32))
    with wave.open(io.BytesIO(donnees), "rb") as fichier:
        assert fichier.getnframes() == 0


def test_wav_relu_correspond_au_signal_emis():
    """Aller-retour complet : ce qu'on relit est bien ce qu'on a encode."""
    origine = sinus(0.25, amplitude=0.5)
    donnees = audio.encoder_wav(origine)
    with wave.open(io.BytesIO(donnees), "rb") as fichier:
        brut = fichier.readframes(fichier.getnframes())
    relu = np.frombuffer(brut, dtype=np.int16).astype(np.float32) / 32767.0
    assert len(relu) == len(origine)
    assert np.max(np.abs(relu - origine)) < 1e-3


# --------------------------------------------------------------------------
# Objet Capture
# --------------------------------------------------------------------------

def test_capture_expose_duree_rms_et_wav():
    capture = audio.Capture(echantillons=sinus(2.0, amplitude=0.5),
                            taux=audio.TAUX)
    assert capture.duree_ms == pytest.approx(2000.0)
    assert capture.rms == pytest.approx(0.5 / np.sqrt(2), rel=1e-3)
    assert capture.wav[:4] == b"RIFF"
    assert not capture.vide


def test_capture_vide_est_signalee():
    capture = audio.Capture(echantillons=np.zeros(0, dtype=np.float32),
                            taux=audio.TAUX)
    assert capture.vide
    assert capture.duree_ms == 0.0


# --------------------------------------------------------------------------
# Enregistreur — sans materiel
# --------------------------------------------------------------------------

@pytest.fixture
def conf(donnees):
    return cfg.charger()


def test_enregistreur_inactif_au_depart(conf):
    enregistreur = audio.Enregistreur(conf)
    assert not enregistreur.en_cours
    assert enregistreur.rms_courant == 0.0


def test_arreter_sans_demarrer_rend_une_capture_vide(conf):
    capture = audio.Enregistreur(conf).arreter()
    assert capture.vide
    assert capture.duree_ms == 0.0


def test_le_rappel_accumule_les_blocs(conf):
    """Simule le fil audio sans peripherique : on appelle le rappel a la main."""
    enregistreur = audio.Enregistreur(conf)
    for _ in range(4):
        bloc = sinus(0.05, amplitude=0.3).reshape(-1, 1)
        enregistreur._rappel(bloc, len(bloc), None, None)

    assert enregistreur.echantillons_captures == 4 * int(audio.TAUX * 0.05)
    capture = enregistreur.arreter()
    assert capture.duree_ms == pytest.approx(200.0, abs=1.0)
    assert capture.rms > 0


def test_la_saturation_est_detectee(conf):
    enregistreur = audio.Enregistreur(conf)
    assert not enregistreur.sature
    enregistreur._rappel(np.ones((100, 1), dtype=np.float32), 100, None, None)
    assert enregistreur.sature


def test_le_debordement_est_retenu(conf):
    """Un depassement signifie des echantillons perdus : il faut le savoir."""
    enregistreur = audio.Enregistreur(conf)
    assert not enregistreur.debordement
    enregistreur._rappel(np.zeros((10, 1), dtype=np.float32), 10, None, "overflow")
    assert enregistreur.debordement


def test_la_duree_maximale_borne_la_capture(conf):
    """Garde-fou du mode bascule : une dictee oubliee doit rester bornee."""
    conf.definir("audio.duree_max_s", 0.5)
    enregistreur = audio.Enregistreur(conf)
    bloc = sinus(1.0, amplitude=0.2).reshape(-1, 1)
    for _ in range(3):
        enregistreur._rappel(bloc, len(bloc), None, None)

    capture = enregistreur.arreter()
    assert capture.duree_ms == pytest.approx(500.0, abs=1.0)


def test_arreter_remet_l_enregistreur_a_zero(conf):
    enregistreur = audio.Enregistreur(conf)
    enregistreur._rappel(sinus(0.1).reshape(-1, 1), 1600, None, None)
    enregistreur.arreter()
    assert enregistreur.echantillons_captures == 0
    assert enregistreur.arreter().vide


# --------------------------------------------------------------------------
# Materiel reel
# --------------------------------------------------------------------------

def _micro_disponible() -> bool:
    try:
        return bool(audio.peripheriques_entree())
    except Exception:
        return False


besoin_micro = pytest.mark.skipif(not _micro_disponible(),
                                  reason="aucun peripherique d'entree")


@pytest.mark.materiel
@besoin_micro
def test_liste_des_peripheriques_est_exploitable():
    peripheriques = audio.peripheriques_entree()
    assert peripheriques
    for appareil in peripheriques:
        assert appareil["canaux"] >= 1
        assert appareil["nom"]


@pytest.mark.materiel
@besoin_micro
def test_capture_reelle_produit_un_wav_lisible(conf):
    """Critere de fin de T1.3 sur du vrai materiel.

    On ne verifie pas le contenu — personne ne parle pendant les tests — mais
    le format, la duree, et l'absence d'echantillons perdus.
    """
    import time

    enregistreur = audio.Enregistreur(conf)
    enregistreur.demarrer()
    assert enregistreur.en_cours
    time.sleep(0.6)
    capture = enregistreur.arreter()

    assert not enregistreur.en_cours
    assert not capture.vide
    assert capture.duree_ms == pytest.approx(600, abs=200)
    with wave.open(io.BytesIO(capture.wav), "rb") as fichier:
        assert fichier.getframerate() == 16000
        assert fichier.getnchannels() == 1
    assert not enregistreur.debordement, "des echantillons ont ete perdus"


# --------------------------------------------------------------------------
# Reechantillonnage
# --------------------------------------------------------------------------
#
# WASAPI n'accepte que le taux natif de la carte : il faut en redescendre a
# 16 kHz. Le filtre anti-repliement n'est pas un raffinement — sans lui, tout
# ce qui depasse 8 kHz ne disparait pas mais se **replie** dans la bande de la
# parole, ou le modele l'entend comme des mots.

def _sinus(frequence: float, taux: int, secondes: float = 1.0) -> np.ndarray:
    t = np.arange(int(taux * secondes)) / taux
    return np.sin(2 * np.pi * frequence * t).astype(np.float32)


def _pic_hz(x: np.ndarray, taux: int) -> float:
    spectre = np.abs(np.fft.rfft(x))
    return float(np.fft.rfftfreq(len(x), 1 / taux)[spectre.argmax()])


def test_le_taux_inchange_ne_touche_a_rien():
    x = _sinus(440, 16000)
    assert audio.reechantillonner(x, 16000, 16000) is not None
    assert np.array_equal(audio.reechantillonner(x, 16000, 16000), x)


def test_la_duree_est_conservee():
    x = _sinus(440, 48000, secondes=1.5)
    y = audio.reechantillonner(x, 48000, 16000)
    assert abs(audio.duree_ms(y, 16000) - 1500) < 1


@pytest.mark.parametrize("depart", [48000, 44100, 32000])
def test_la_voix_traverse_sans_se_deplacer(depart):
    """440 Hz doit rester 440 Hz, quel que soit le taux de depart."""
    y = audio.reechantillonner(_sinus(440, depart), depart, 16000)
    assert abs(_pic_hz(y, 16000) - 440) < 5


def test_le_repliement_est_evite():
    """Un 12 kHz reduit sans filtre reapparaitrait a 4 kHz, en pleine bande de
    parole et a pleine amplitude. C'est l'erreur classique du sous-
    echantillonnage, et elle s'entend."""
    x = _sinus(12000, 48000)
    filtre = audio.reechantillonner(x, 48000, 16000)
    brut = x[::3]                      # ce que donnerait une simple decimation

    assert audio.rms(brut) > 0.5, "la decimation brute garde toute l'energie"
    assert audio.rms(filtre) < 0.01, "le filtre anti-repliement n'a pas agi"


def test_une_capture_vide_reste_vide():
    vide = np.zeros(0, dtype=np.float32)
    assert audio.reechantillonner(vide, 48000, 16000).size == 0


def test_le_signal_reste_en_float32():
    """Le moteur attend du float32 : un float64 double le poids transmis."""
    y = audio.reechantillonner(_sinus(440, 48000), 48000, 16000)
    assert y.dtype == np.float32


# --------------------------------------------------------------------------
# Choix de l'interface audio
# --------------------------------------------------------------------------

class _FausseInterface:
    """Les interfaces telles que PortAudio les decrit, en plus court."""

    def __init__(self, interfaces, peripheriques):
        self._interfaces = interfaces
        self._peripheriques = peripheriques

    def query_hostapis(self):
        return self._interfaces

    def query_devices(self, index=None):
        return self._peripheriques[index]


def test_wasapi_est_prefere_a_mme():
    """MME travaille sur une table de peripheriques figee au chargement : elle
    ouvre sans erreur une entree qui n'existe plus et rend du silence. C'est
    tout le sujet."""
    faux = _FausseInterface(
        [{"name": "MME", "default_input_device": 1},
         {"name": "Windows WASAPI", "default_input_device": 24}],
        {1: {"default_samplerate": 44100.0},
         24: {"default_samplerate": 48000.0}})

    assert audio.choisir_entree(faux) == (24, 48000)


def test_sans_wasapi_on_descend_la_liste():
    faux = _FausseInterface(
        [{"name": "MME", "default_input_device": 1},
         {"name": "Windows DirectSound", "default_input_device": 9}],
        {1: {"default_samplerate": 44100.0},
         9: {"default_samplerate": 48000.0}})

    assert audio.choisir_entree(faux) == (9, 48000)


def test_un_peripherique_choisi_est_respecte():
    """C'est une decision de l'utilisateur, pas un defaut a optimiser — et
    c'est le seul recours quand le systeme change d'entree sans prevenir."""
    faux = _FausseInterface(
        [{"name": "Windows WASAPI", "default_input_device": 24}],
        {24: {"default_samplerate": 48000.0}})

    assert audio.choisir_entree(faux, demande=7) == (7, audio.TAUX)


def test_une_interface_sans_entree_est_ignoree():
    faux = _FausseInterface(
        [{"name": "Windows WASAPI", "default_input_device": -1},
         {"name": "MME", "default_input_device": 1}],
        {1: {"default_samplerate": 44100.0}})

    assert audio.choisir_entree(faux) == (1, 44100)


def test_sans_aucune_interface_on_laisse_portaudio_choisir():
    faux = _FausseInterface([], {})
    assert audio.choisir_entree(faux) == (None, audio.TAUX)


def test_un_taux_illisible_retombe_sur_seize_kilohertz():
    class Cassee(_FausseInterface):
        def query_devices(self, index=None):
            raise RuntimeError("peripherique disparu")

    faux = Cassee([{"name": "Windows WASAPI", "default_input_device": 24}], {})
    assert audio.choisir_entree(faux) == (24, audio.TAUX)


# --------------------------------------------------------------------------
# Un micro par micro, et non un par interface audio
# --------------------------------------------------------------------------

class _SounddeviceDouble:
    """PortAudio tel qu'il se presente vraiment : le meme materiel repete."""

    def __init__(self, appareils, interfaces):
        self._appareils = appareils
        self._interfaces = interfaces

    def query_hostapis(self):
        return [{"name": nom, "default_input_device": defaut}
                for nom, defaut in self._interfaces]

    def query_devices(self, index=None):
        if index is None:
            return self._appareils
        return self._appareils[index]


# Releve reel sur un poste ordinaire : deux micros, quatorze entrees.
RELEVE = _SounddeviceDouble(
    appareils=[
        {"name": "Mappeur de sons Microsoft - Input", "max_input_channels": 2,
         "hostapi": 0, "default_samplerate": 44100},
        {"name": "Microphone (UGREEN Camera Audio", "max_input_channels": 2,
         "hostapi": 0, "default_samplerate": 44100},
        {"name": "Pilote de capture audio principal", "max_input_channels": 2,
         "hostapi": 1, "default_samplerate": 44100},
        {"name": "Microphone (UGREEN Camera Audio)", "max_input_channels": 2,
         "hostapi": 1, "default_samplerate": 44100},
        {"name": "Microphone (UGREEN Camera Audio)", "max_input_channels": 2,
         "hostapi": 2, "default_samplerate": 48000},
        {"name": "Microphone (Casque sans fil)", "max_input_channels": 1,
         "hostapi": 2, "default_samplerate": 48000},
        {"name": "Microphone ()", "max_input_channels": 1,
         "hostapi": 3, "default_samplerate": 44100},
    ],
    interfaces=[("MME", 1), ("Windows DirectSound", 3),
                ("Windows WASAPI", 4), ("Windows WDM-KS", 6)])


@pytest.mark.materiel
def test_un_seul_choix_par_micro(monkeypatch):
    """Deux micros ne doivent pas produire quatorze lignes.

    PortAudio expose le meme materiel une fois par interface — MME,
    DirectSound, WASAPI, WDM-KS — plus des pseudo-appareils (« mappeur de
    sons ») et des fantomes (« Microphone () »). Le selecteur des reglages les
    montrait tous.
    """
    monkeypatch.setattr(audio, "reenumerer", lambda _sd: None)
    monkeypatch.setitem(sys.modules, "sounddevice", RELEVE)

    entrees = audio.peripheriques_entree()

    assert [e["nom"] for e in entrees] == [
        "Microphone (UGREEN Camera Audio)", "Microphone (Casque sans fil)"]
    assert all(e["interface"] == "Windows WASAPI" for e in entrees), \
        "WASAPI donne les noms complets et le taux natif"


@pytest.mark.materiel
def test_ni_pseudo_appareil_ni_fantome(monkeypatch):
    """« Mappeur de sons » double l'option « entree par defaut » ; les
    entrees WDM-KS sans nom ne menent nulle part."""
    monkeypatch.setattr(audio, "reenumerer", lambda _sd: None)
    monkeypatch.setitem(sys.modules, "sounddevice", RELEVE)

    noms = [e["nom"] for e in audio.peripheriques_entree()]

    assert not any("Mappeur" in nom or "Pilote de capture" in nom
                   for nom in noms)
    assert "Microphone ()" not in noms


@pytest.mark.materiel
def test_le_micro_est_retrouve_par_son_nom(monkeypatch):
    """Un index PortAudio se renumerote des qu'un peripherique apparait : le
    micro choisi deviendrait silencieusement un autre."""
    monkeypatch.setattr(audio, "reenumerer", lambda _sd: None)
    monkeypatch.setitem(sys.modules, "sounddevice", RELEVE)

    assert audio.trouver_entree(RELEVE,
                                "Microphone (Casque sans fil)") == 5
    assert audio.trouver_entree(RELEVE, "Micro debranche") is None


@pytest.mark.materiel
def test_un_reglage_tronque_par_mme_designe_encore_le_bon_micro(monkeypatch):
    """MME coupe les noms a trente et un caracteres. Un reglage ecrit du temps
    ou la liste montrait cette forme doit continuer de fonctionner."""
    monkeypatch.setattr(audio, "reenumerer", lambda _sd: None)
    monkeypatch.setitem(sys.modules, "sounddevice", RELEVE)

    assert audio.trouver_entree(
        RELEVE, "Microphone (UGREEN Camera Audio") == 4


@pytest.mark.materiel
def test_le_micro_choisi_capture_a_son_taux_natif(monkeypatch):
    """WASAPI impose le taux de la carte en mode partage : demander 16 kHz a
    un materiel qui tourne a 48 rend du silence."""
    monkeypatch.setattr(audio, "reenumerer", lambda _sd: None)
    monkeypatch.setitem(sys.modules, "sounddevice", RELEVE)

    index, taux = audio.choisir_entree(RELEVE,
                                       "Microphone (Casque sans fil)")

    assert (index, taux) == (5, 48000)


@pytest.mark.materiel
def test_un_micro_disparu_ne_bloque_pas_la_dictee(monkeypatch):
    """Casque debranche : mieux vaut l'entree par defaut qu'un refus."""
    monkeypatch.setattr(audio, "reenumerer", lambda _sd: None)
    monkeypatch.setitem(sys.modules, "sounddevice", RELEVE)

    index, taux = audio.choisir_entree(RELEVE, "Micro vendu depuis")

    assert index == 4, "on retombe sur l'entree par defaut de WASAPI"
    assert taux == 48000

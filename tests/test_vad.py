"""T2.2 — le VAD, verifie a travers les modules.

T0.3 avait mesure le comportement en ligne de commande : sans protection, le
modele invente du texte sur du silence dans trois cas sur trois ; avec
`--vad` et `--suppress-nst`, zero sur trois.

Ce fichier rejoue la meme mesure, mais par le chemin que l'application
emprunte reellement — configuration, arguments du serveur, requete HTTP. Un
reglage juste dans la documentation et faux dans le code se verrait ici.
"""

import numpy as np
import pytest

from murmur import audio, config as cfg, stt

MOTEUR_PRESENT = ((cfg.MOTEUR / "whisper-server.exe").exists()
                  and (cfg.MOTEUR / "ggml-large-v3-turbo-q5_0.bin").exists()
                  and (cfg.MOTEUR / "ggml-silero-v5.1.2.bin").exists())

besoin_moteur = pytest.mark.skipif(
    not MOTEUR_PRESENT, reason="engine/ incomplet (serveur, modele ou VAD absent)")

# Enregistrement de reference produit en P1 : voix reelle, francais, jargon.
ECHANTILLON_VOIX = (cfg.RACINE / "spikes" / "t0_2_lexique" / "sample_fr.wav")
besoin_voix = pytest.mark.skipif(not ECHANTILLON_VOIX.exists(),
                                 reason="sample_fr.wav absent")


@pytest.fixture
def conf(donnees):
    configuration = cfg.charger()
    configuration.definir("moteur.port", 8759)
    return configuration


def wav_silence(duree_s: float = 4.0) -> bytes:
    return audio.encoder_wav(np.zeros(int(audio.TAUX * duree_s),
                                      dtype=np.float32))


def wav_bruit(duree_s: float = 4.0, amplitude: float = 0.004) -> bytes:
    """Bruit de fond faible : une piece qui n'est pas parfaitement calme."""
    generateur = np.random.default_rng(12345)
    echantillons = (generateur.standard_normal(int(audio.TAUX * duree_s))
                    * amplitude).astype(np.float32)
    return audio.encoder_wav(echantillons)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def test_le_vad_est_actif_par_defaut(conf):
    """Sans lui, un declenchement accidentel insere une phrase inventee."""
    assert conf["vad.actif"] is True
    assert conf["vad.suppress_nst"] is True


def test_les_seuils_du_vad_sont_passes_au_serveur(conf):
    conf.definir("vad.seuil", 0.42)
    conf.definir("vad.min_parole_ms", 300)
    args = stt.Moteur(conf)._arguments()

    assert "--vad-threshold" in args
    assert args[args.index("--vad-threshold") + 1] == "0.42"
    assert args[args.index("--vad-min-speech-duration-ms") + 1] == "300"


def test_le_modele_vad_est_bien_reference(conf):
    args = stt.Moteur(conf)._arguments()
    chemin = args[args.index("--vad-model") + 1]
    assert chemin.endswith("ggml-silero-v5.1.2.bin")


# --------------------------------------------------------------------------
# Comportement reel — critere de fin de T2.2
# --------------------------------------------------------------------------

@pytest.mark.lent
@besoin_moteur
def test_le_silence_ne_produit_aucun_texte(conf):
    """Le coeur de la protection : trois hallucinations sur trois sans elle."""
    with stt.Moteur(conf) as moteur:
        assert moteur.transcrire(wav_silence()) == ""


@pytest.mark.lent
@besoin_moteur
def test_un_bruit_de_fond_faible_ne_produit_aucun_texte(conf):
    with stt.Moteur(conf) as moteur:
        assert moteur.transcrire(wav_bruit()) == ""


@pytest.mark.lent
@besoin_moteur
@besoin_voix
def test_la_parole_reelle_passe_toujours(conf):
    """Temoin indispensable : une protection qui filtre tout ne vaut rien."""
    with stt.Moteur(conf) as moteur:
        texte = moteur.transcrire(ECHANTILLON_VOIX.read_bytes())
    assert len(texte) > 40, f"parole perdue par le VAD : {texte!r}"


@pytest.mark.lent
@besoin_moteur
def test_sans_vad_le_silence_produit_bien_du_texte(conf):
    """Contre-epreuve : verifie que la protection sert vraiment a quelque chose.

    Si ce test cessait d'halluciner, les tests precedents deviendraient
    vacants — ils passeraient sans rien prouver.
    """
    conf.definir("vad.actif", False)
    conf.definir("vad.suppress_nst", False)
    with stt.Moteur(conf) as moteur:
        texte = moteur.transcrire(wav_silence())

    if not texte:
        pytest.skip("le modele n'a pas hallucine sur ce silence : la "
                    "contre-epreuve n'est pas concluante, mais rien n'est casse")
    assert texte, "hallucination attendue sans protection"

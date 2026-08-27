"""T4.1b — non-regression du lexique sur un enregistrement reel.

Le prompt de conditionnement **n'est pas monotone** : mesure en T0.2,
`Grafana` etait correctement transcrit SANS prompt et echouait AVEC. Ajouter
un terme au lexique peut donc en degrader un autre, sans que rien ne le
signale.

Ce fichier rejoue l'echantillon de reference — la voix de l'utilisateur, son
jargon — a travers la chaine complete, et exige que les termes attendus
passent. C'est le seul garde-fou contre une derive silencieuse du lexique.
"""

import json

import pytest

from murmur import config as cfg, lexicon, stt

SPIKE = cfg.RACINE / "spikes" / "t0_2_lexique"
ECHANTILLON = SPIKE / "sample_fr.wav"
REFERENCE = SPIKE / "reference.json"

MOTEUR_PRESENT = ((cfg.MOTEUR / "whisper-server.exe").exists()
                  and (cfg.MOTEUR / "ggml-large-v3-turbo-q5_0.bin").exists())

besoin_tout = pytest.mark.skipif(
    not (MOTEUR_PRESENT and ECHANTILLON.exists() and REFERENCE.exists()),
    reason="moteur ou echantillon de reference absent")

# Le vocabulaire et ses formes erronees vivent dans `reference.json`, a cote de
# l'enregistrement — et non ici.
#
# Ils ne valent que pour CET enregistrement : une voix, un jargon, des fautes
# de transcription relevees sur lui. Les ecrire dans le test donnait a croire
# qu'ils decrivaient le logiciel, alors qu'ils decrivent une personne. Ni le
# `.wav` ni son jeu de reference ne sont publies ; les tests qui en dependent
# se sautent d'eux-memes.


def _reference() -> dict:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def _termes_attendus() -> list[str]:
    return _reference()["termes_attendus"]


def _variantes_connues() -> dict:
    return _reference().get("variantes_connues", {})


@pytest.fixture
def conf(donnees):
    configuration = cfg.charger()
    configuration.definir("moteur.port", 8763)
    configuration.definir("langue", "fr")
    return configuration


@pytest.fixture
def lexique_garni(donnees):
    lexique = lexicon.Lexique()
    variantes = _variantes_connues()
    for terme in _termes_attendus():
        lexique.ajouter(terme, variantes.get(terme, []))
    return lexique


# --------------------------------------------------------------------------
# Sans moteur — coherence du jeu de reference
# --------------------------------------------------------------------------

def test_le_jeu_de_reference_est_coherent():
    if not REFERENCE.exists():
        pytest.skip("reference.json absent")
    termes = _termes_attendus()
    assert len(termes) == 10
    assert len(set(termes)) == len(termes), "doublon dans les termes attendus"


def test_toutes_les_variantes_connues_visent_un_terme_attendu():
    """Une variante orpheline ne corrigerait rien et fausserait la mesure."""
    if not REFERENCE.exists():
        pytest.skip("reference.json absent")
    attendus = set(_termes_attendus())
    inconnus = set(_variantes_connues()) - attendus
    assert not inconnus, f"variantes sans terme correspondant : {inconnus}"


def test_le_lexique_de_reference_tient_dans_le_prompt(lexique_garni):
    prompt = lexique_garni.prompt()
    assert len(prompt) <= lexicon.LIMITE_PROMPT
    assert not lexique_garni.termes_hors_prompt(), \
        "dix termes doivent tenir largement dans le prompt"


# --------------------------------------------------------------------------
# Avec moteur — la mesure qui compte
# --------------------------------------------------------------------------

@pytest.mark.lent
@besoin_tout
def test_la_chaine_complete_reconnait_le_jargon(conf, lexique_garni):
    """Critere de succes n.3 de la SPEC.

    Mesure de depart, sans aucune aide : 5 termes sur 10. Le prompt seul en
    portait 8. Avec la table de remplacement, on attend la totalite.
    """
    attendus = _termes_attendus()

    with stt.Moteur(conf) as moteur:
        texte = moteur.transcrire(ECHANTILLON.read_bytes(),
                                  prompt=lexique_garni.prompt())
    texte, _ = lexique_garni.corriger(texte)

    resultats = lexique_garni.verifier(texte, attendus)
    rates = [terme for terme, ok in resultats.items() if not ok]
    reussis = len(attendus) - len(rates)

    assert reussis >= 8, (
        f"regression : {reussis}/{len(attendus)} termes reconnus. "
        f"Rates : {rates}. Texte obtenu : {texte!r}")


@pytest.mark.lent
@besoin_tout
def test_le_lexique_ameliore_reellement_la_transcription(conf, lexique_garni,
                                                          donnees):
    """Contre-epreuve : sans lexique, le score doit etre nettement inferieur.

    Sans elle, le test precedent pourrait passer alors que le lexique ne sert
    a rien — il suffirait que le modele se soit ameliore par ailleurs.
    """
    attendus = _termes_attendus()
    audio = ECHANTILLON.read_bytes()
    vierge = lexicon.Lexique(chemin=donnees / "vide.json")

    with stt.Moteur(conf) as moteur:
        sans = moteur.transcrire(audio)
        avec = moteur.transcrire(audio, prompt=lexique_garni.prompt())

    avec, _ = lexique_garni.corriger(avec)

    score_sans = sum(vierge.verifier(sans, attendus).values())
    score_avec = sum(lexique_garni.verifier(avec, attendus).values())

    assert score_avec > score_sans, (
        f"le lexique n'apporte rien : {score_sans} sans, {score_avec} avec")

"""T2.1 — garde-fous contre les dictees fantomes."""

import numpy as np
import pytest

from murmur import audio, config as cfg, guard


@pytest.fixture
def conf(donnees):
    return cfg.charger()


@pytest.fixture
def garde(conf):
    return guard.Garde(conf)


def capture(duree_s: float, amplitude: float = 0.3) -> audio.Capture:
    n = int(audio.TAUX * duree_s)
    t = np.linspace(0, duree_s, n, endpoint=False)
    return audio.Capture((amplitude * np.sin(2 * np.pi * 440 * t)
                          ).astype(np.float32), audio.TAUX)


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def test_normalisation_ignore_casse_accents_et_ponctuation():
    assert guard.normaliser("Écoute, ça va !") == guard.normaliser("ecoute ca va")


def test_normalisation_reduit_les_espaces():
    assert guard.normaliser("  trop   d'espaces  ") == "trop d espaces"


def test_normalisation_dune_chaine_vide():
    assert guard.normaliser("   ...  ") == ""


# --------------------------------------------------------------------------
# En amont
# --------------------------------------------------------------------------

def test_capture_normale_est_acceptee(garde):
    assert garde.controler_capture(capture(1.0)).accepte


def test_capture_vide_est_rejetee(garde):
    verdict = garde.controler_capture(
        audio.Capture(np.zeros(0, dtype=np.float32), audio.TAUX))
    assert not verdict.accepte
    assert "aucun son" in verdict.motif


def test_capture_trop_courte_est_rejetee(garde):
    """Un appui accidentel ne doit meme pas atteindre le moteur."""
    verdict = garde.controler_capture(capture(0.1))
    assert not verdict.accepte
    assert "trop court" in verdict.motif
    assert "300" in verdict.motif, "le motif doit donner le seuil"


def test_un_micro_muet_est_distingue_dun_silence(garde):
    """Un micro coupe ne rend pas du silence mais du vide.

    Les confondre envoyait l'utilisateur parler plus fort dans un micro
    eteint — mesure en usage reel : 0.000015 contre 0.001 pour une piece
    calme.
    """
    verdict = garde.controler_capture(capture(2.0, amplitude=0.00002))
    assert not verdict.accepte
    assert "aucun signal" in verdict.motif
    assert "sourdine" in verdict.motif, "le motif doit dire quoi verifier"


def test_un_signal_trop_faible_invite_a_se_rapprocher(garde):
    """Micro actif mais voix trop lointaine : le remede n'est pas le meme."""
    verdict = garde.controler_capture(capture(2.0, amplitude=0.001))
    assert not verdict.accepte
    assert "trop faible" in verdict.motif
    assert "plus pres" in verdict.motif


def test_le_seuil_muet_est_bien_sous_le_seuil_de_voix(conf):
    """Sinon l'un des deux messages ne s'afficherait jamais."""
    from murmur import guard as module_guard
    assert module_guard.SEUIL_MICRO_MUET < conf["garde.rms_min"]


def test_les_seuils_sont_configurables(conf):
    conf.definir("garde.duree_min_ms", 50)
    assert guard.Garde(conf).controler_capture(capture(0.1)).accepte

    conf.definir("garde.duree_min_ms", 5000)
    assert not guard.Garde(conf).controler_capture(capture(1.0)).accepte


def test_une_dictee_chuchotee_passe_quand_meme(garde):
    """Le seuil doit ecarter le silence, pas une voix discrete."""
    assert garde.controler_capture(capture(1.0, amplitude=0.02)).accepte


# --------------------------------------------------------------------------
# En aval
# --------------------------------------------------------------------------

def test_texte_normal_est_accepte(garde):
    assert garde.controler_texte("bonjour, ceci est une dictee").accepte


def test_texte_vide_est_rejete(garde):
    assert not garde.controler_texte("   ").accepte


def test_texte_sans_contenu_est_rejete(garde):
    """« ... » est ce que le modele produit sur du bruit."""
    verdict = garde.controler_texte("...")
    assert not verdict.accepte


def test_liste_noire_vide_par_defaut_ne_filtre_rien(garde):
    """Pre-remplir la liste censurerait des phrases legitimes (cf. T0.3)."""
    assert garde.controler_texte(
        "Sous-titrage Societe Radio-Canada").accepte


def test_hallucination_listee_est_bloquee(conf):
    conf.definir("garde.liste_noire", ["Sous-titrage Societe Radio-Canada"])
    verdict = guard.Garde(conf).controler_texte("Sous-titrage Societe Radio-Canada")
    assert not verdict.accepte
    assert "hallucination" in verdict.motif


def test_le_blocage_tolere_les_variantes_de_forme(conf):
    """Le modele ne reproduit pas toujours la meme ponctuation."""
    conf.definir("garde.liste_noire", ["Sous-titrage Société Radio-Canada"])
    garde = guard.Garde(conf)
    for variante in ("sous-titrage societe radio-canada",
                     "Sous-titrage Société Radio-Canada.",
                     "  SOUS-TITRAGE SOCIETE RADIO-CANADA  "):
        assert not garde.controler_texte(variante).accepte, variante


def test_une_phrase_contenant_lexpression_nest_pas_censuree(conf):
    """Le point le plus important de ce module.

    La comparaison porte sur le texte ENTIER. Sans cela, une dictee legitime
    qui evoquerait l'expression serait effacee sans laisser de trace, et
    l'utilisateur ne comprendrait pas pourquoi sa phrase disparait.
    """
    conf.definir("garde.liste_noire", ["Merci d'avoir regarde cette video"])
    garde = guard.Garde(conf)
    phrase = ("je voulais te dire merci d'avoir regarde cette video "
              "que je t'ai envoyee hier")
    assert garde.controler_texte(phrase).accepte


def test_les_blocages_sont_journalises(conf, donnees):
    """Une liste noire non auditable finit par censurer sans qu'on sache quoi."""
    conf.definir("garde.liste_noire", ["phrase fantome"])
    guard.Garde(conf).controler_texte("phrase fantome")

    fichier = cfg.dossier_journaux() / "bloques.log"
    assert fichier.exists()
    assert "phrase fantome" in fichier.read_text(encoding="utf-8")


def test_journaliser_un_blocage_ne_peut_pas_casser_une_dictee(conf, monkeypatch):
    conf.definir("garde.liste_noire", ["fantome"])
    monkeypatch.setattr(
        cfg, "dossier_journaux",
        lambda: (_ for _ in ()).throw(OSError("disque plein")))
    # Ne doit pas lever.
    assert not guard.Garde(conf).controler_texte("fantome").accepte

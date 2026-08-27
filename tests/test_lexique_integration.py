"""T4 — le lexique dans la chaine complete, et l'apprentissage par correction."""

import numpy as np
import pytest

from murmur import audio, config as cfg, inject
from murmur.app import Application


def signal(duree_s: float = 0.6) -> audio.Capture:
    n = int(audio.TAUX * duree_s)
    return audio.Capture(np.full(n, 0.3, dtype=np.float32), audio.TAUX)


@pytest.fixture
def application(donnees, monkeypatch):
    conf = cfg.charger()
    conf.definir("moteur.port", 8761)
    app = Application(conf)
    app._transcription = "texte par defaut"
    monkeypatch.setattr(app.moteur, "transcrire",
                        lambda wav, prompt=None, timeout=60.0:
                        app._prompt_recu.append(prompt) or app._transcription)
    monkeypatch.setattr(app.injecteur, "injecter",
                        lambda t: inject.ResultatInjection(duree_pose_ms=1.0))
    app._prompt_recu = []
    try:
        yield app
    finally:
        app.historique.fermer()


# --------------------------------------------------------------------------
# Le lexique dans la chaine de dictee
# --------------------------------------------------------------------------

def test_le_prompt_est_transmis_au_moteur(application):
    application.lexique.ajouter("Cloudflare")
    application.lexique.ajouter("Supabase")

    application._traiter(signal(), "cible", 0.0)

    assert application._prompt_recu, "aucune transcription lancee"
    prompt = application._prompt_recu[0]
    assert prompt and "Cloudflare" in prompt and "Supabase" in prompt


def test_un_lexique_vide_nenvoie_pas_de_prompt_parasite(application):
    application._traiter(signal(), "cible", 0.0)
    assert application._prompt_recu[0] == ""


def test_le_lexique_desactive_nenvoie_aucun_prompt(application):
    application.conf.definir("lexique.actif", False)
    application.lexique.ajouter("Cloudflare")

    application._traiter(signal(), "cible", 0.0)
    assert application._prompt_recu[0] is None


def test_la_table_de_remplacement_corrige_le_texte(application):
    """Ce que le prompt ne rattrape pas doit l'etre apres coup."""
    application.lexique.ajouter("Cloudflare", ["cloudeflare"])
    application._transcription = "j'ai avance sur le bot cloudeflare"

    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    application._traiter(signal(), "cible", 0.0)

    assert resultats[0].texte == "j'ai avance sur le bot Cloudflare"
    assert resultats[0].termes_corriges == ("Cloudflare",)


def test_le_texte_archive_est_le_texte_corrige(application):
    """L'historique doit refleter ce qui a ete insere, pas la version brute."""
    application.lexique.ajouter("Vulkan", ["Vulcan"])
    application._transcription = "ca tourne sur Vulcan"

    application._traiter(signal(), "cible", 0.0)
    assert application.historique.recentes()[0].texte == "ca tourne sur Vulkan"


# --------------------------------------------------------------------------
# Apprentissage par correction
# --------------------------------------------------------------------------

def test_une_correction_est_detectee(application, monkeypatch):
    application.historique.ajouter("j'ai avance sur le bot cloudeflare")
    monkeypatch.setattr(inject, "lire_presse_papier",
                        lambda: "j'ai avance sur le bot Cloudflare")

    recues = []
    application.ecouteurs.correction.append(recues.append)
    analyse = application.apprendre_depuis_presse_papier()

    assert analyse is not None
    assert [s.apres for s in analyse.propositions] == ["Cloudflare"]
    assert recues == [analyse], "l'interface doit etre prevenue"


def test_un_presse_papier_sans_rapport_napprend_rien(application, monkeypatch):
    """Rien ne doit etre conserve quand le texte copie n'est pas une correction."""
    application.historique.ajouter("j'ai avance sur le bot Cloudflare")
    monkeypatch.setattr(inject, "lire_presse_papier",
                        lambda: "mot de passe : correct-horse-battery-staple")

    recues = []
    application.ecouteurs.correction.append(recues.append)
    assert application.apprendre_depuis_presse_papier() is None
    assert recues == [None]
    assert len(application.lexique) == 0


def test_un_presse_papier_vide_est_ignore(application, monkeypatch):
    monkeypatch.setattr(inject, "lire_presse_papier", lambda: None)
    assert application.apprendre_depuis_presse_papier() is None


def test_un_presse_papier_illisible_ne_leve_pas(application, monkeypatch):
    monkeypatch.setattr(
        inject, "lire_presse_papier",
        lambda: (_ for _ in ()).throw(inject.ErreurInjection("occupe")))
    assert application.apprendre_depuis_presse_papier() is None


def test_seules_les_substitutions_validees_entrent_au_lexique(application,
                                                              monkeypatch):
    """Le point central : rien n'est appris sans accord explicite."""
    application.historique.ajouter("du coup Olama tourne sur Vulcan")
    monkeypatch.setattr(inject, "lire_presse_papier",
                        lambda: "donc Ollama tourne sur Vulkan")

    analyse = application.apprendre_depuis_presse_papier()
    assert analyse is not None

    # L'utilisateur ne retient que les corrections de vocabulaire.
    retenues = [s for s in analyse.substitutions if s.est_vocabulaire]
    application.enregistrer_correction(analyse, retenues)

    assert application.lexique.contient("Ollama")
    assert application.lexique.contient("Vulkan")
    assert not application.lexique.contient("donc"), \
        "une tournure de style a ete apprise"


def test_le_terme_appris_corrige_les_dictees_suivantes(application, monkeypatch):
    """Boucle complete : corriger une fois doit suffire."""
    application.historique.ajouter("ca tourne sur Vulcan")
    monkeypatch.setattr(inject, "lire_presse_papier",
                        lambda: "ca tourne sur Vulkan")

    analyse = application.apprendre_depuis_presse_papier()
    application.enregistrer_correction(analyse, list(analyse.propositions))

    application._transcription = "et Vulcan encore une fois"
    resultats = []
    application.ecouteurs.resultat.append(resultats.append)
    application._traiter(signal(), "cible", 0.0)

    assert resultats[0].texte == "et Vulkan encore une fois"


def test_la_correction_est_conservee_dans_le_corpus(application, monkeypatch):
    """Meme les parties non retenues : c'est la matiere de l'apprentissage V2."""
    application.historique.ajouter("du coup Olama tourne")
    monkeypatch.setattr(inject, "lire_presse_papier",
                        lambda: "donc Ollama tourne")

    analyse = application.apprendre_depuis_presse_papier()
    application.enregistrer_correction(analyse, list(analyse.propositions))

    nombre = application.historique._connexion.execute(
        "SELECT COUNT(*) FROM corrections").fetchone()[0]
    assert nombre == 1


def test_enregistrer_sans_rien_retenir_ne_touche_pas_au_lexique(application,
                                                                monkeypatch):
    application.historique.ajouter("du coup ca marche")
    monkeypatch.setattr(inject, "lire_presse_papier",
                        lambda: "donc ca marche")

    analyse = application.apprendre_depuis_presse_papier()
    application.enregistrer_correction(analyse, [])
    assert len(application.lexique) == 0


def test_le_lexique_est_persiste_apres_apprentissage(application, monkeypatch):
    from murmur import lexicon

    application.historique.ajouter("ca tourne sur Vulcan")
    monkeypatch.setattr(inject, "lire_presse_papier",
                        lambda: "ca tourne sur Vulkan")

    analyse = application.apprendre_depuis_presse_papier()
    application.enregistrer_correction(analyse, list(analyse.propositions))

    assert lexicon.Lexique().contient("Vulkan"), \
        "le lexique n'a pas ete ecrit sur disque"

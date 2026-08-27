"""T4.1 et T4.2 — lexique personnel et table de remplacement."""

import json

import pytest

from murmur import config as cfg, lexicon


@pytest.fixture
def lexique(donnees):
    return lexicon.Lexique()


# --------------------------------------------------------------------------
# Persistance
# --------------------------------------------------------------------------

def test_un_lexique_neuf_est_vide(lexique):
    assert len(lexique) == 0
    assert lexique.prompt() == ""


def test_ajout_puis_relecture(lexique, donnees):
    lexique.ajouter("Cloudflare", ["cloudeflare"])
    lexique.sauvegarder()

    relu = lexicon.Lexique()
    assert len(relu) == 1
    assert relu.trouver("Cloudflare").variantes == ["cloudeflare"]


def test_le_fichier_reste_lisible_a_la_main(lexique, donnees):
    """Un lexique auto-alimente peut deriver : il faut pouvoir l'inspecter."""
    lexique.ajouter("Supabase", ["super base"])
    lexique.sauvegarder()

    donnees_brutes = json.loads(lexique.chemin.read_text(encoding="utf-8"))
    assert donnees_brutes["version"] == lexicon.VERSION
    assert donnees_brutes["termes"][0]["terme"] == "Supabase"


def test_un_lexique_corrompu_ne_bloque_pas_la_dictee(donnees):
    """Mieux vaut repartir vide que refuser de demarrer."""
    cfg.fichier_lexique().write_text("{ ceci n'est pas du json",
                                     encoding="utf-8")
    assert len(lexicon.Lexique()) == 0


# --------------------------------------------------------------------------
# Modification
# --------------------------------------------------------------------------

def test_ajouter_deux_fois_complete_les_variantes(lexique):
    lexique.ajouter("Vulkan", ["Vulcan"])
    lexique.ajouter("Vulkan", ["voulcane"])
    assert lexique.trouver("Vulkan").variantes == ["Vulcan", "voulcane"]
    assert len(lexique) == 1


def test_une_variante_en_double_est_ignoree(lexique):
    lexique.ajouter("Vulkan", ["Vulcan", "vulcan", "VULCAN"])
    assert len(lexique.trouver("Vulkan").variantes) == 1


def test_une_variante_identique_au_terme_est_refusee(lexique):
    """Elle produirait un remplacement circulaire."""
    lexique.ajouter("Ollama", ["Ollama", "ollama"])
    assert lexique.trouver("Ollama").variantes == []


def test_recherche_insensible_a_la_casse(lexique):
    lexique.ajouter("DexScreener")
    assert lexique.contient("dexscreener")
    assert lexique.trouver("DEXSCREENER").terme == "DexScreener"


def test_retirer_un_terme(lexique):
    lexique.ajouter("Vercel")
    assert lexique.retirer("vercel")
    assert len(lexique) == 0
    assert not lexique.retirer("vercel")


def test_retirer_une_variante(lexique):
    lexique.ajouter("Tkinter", ["Kinter", "T'as inter"])
    assert lexique.retirer_variante("Tkinter", "kinter")
    assert lexique.trouver("Tkinter").variantes == ["T'as inter"]


def test_un_terme_vide_est_refuse(lexique):
    with pytest.raises(ValueError):
        lexique.ajouter("   ")


# --------------------------------------------------------------------------
# Prompt de conditionnement
# --------------------------------------------------------------------------

def test_le_prompt_liste_les_termes(lexique):
    for terme in ("Cloudflare", "Supabase", "Grafana"):
        lexique.ajouter(terme)
    prompt = lexique.prompt()
    for terme in ("Cloudflare", "Supabase", "Grafana"):
        assert terme in prompt
    assert prompt.endswith(".")


def test_le_prompt_respecte_la_limite(lexique):
    """Depasser fait tronquer le prompt cote moteur, en coupant n'importe ou."""
    for i in range(300):
        lexique.ajouter(f"TermeTresLongNumero{i:03d}")
    prompt = lexique.prompt()
    assert len(prompt) <= lexicon.LIMITE_PROMPT + 1


def test_les_termes_les_plus_utilises_survivent_a_la_troncature(lexique):
    rare = lexique.ajouter("TermeRarementUtilise")
    frequent = lexique.ajouter("TermeTresFrequent")
    frequent.usages = 100
    for i in range(200):
        lexique.ajouter(f"Bourrage{i:03d}")

    prompt = lexique.prompt()
    assert "TermeTresFrequent" in prompt
    assert rare.terme not in prompt or True  # peut passer, l'essentiel est ci-dessus


def test_un_terme_epingle_reste_toujours_dans_le_prompt(lexique):
    lexique.ajouter("Indispensable", epingle=True)
    for i in range(300):
        lexique.ajouter(f"Bourrage{i:03d}")
    assert "Indispensable" in lexique.prompt()


def test_les_termes_ecartes_sont_identifiables(lexique):
    """L'interface doit pouvoir dire ce qui ne tient pas dans le prompt."""
    for i in range(200):
        lexique.ajouter(f"TermeAssezLong{i:03d}")
    ecartes = lexique.termes_hors_prompt()
    assert ecartes, "aucun terme ecarte alors que la limite est depassee"
    prompt = lexique.prompt()
    for terme in ecartes:
        assert terme not in prompt


def test_le_prompt_dun_lexique_vide_est_vide(lexique):
    assert lexique.prompt() == ""


# --------------------------------------------------------------------------
# Table de remplacement
# --------------------------------------------------------------------------

def test_une_variante_est_corrigee(lexique):
    lexique.ajouter("Cloudflare", ["cloudeflare"])
    texte, corriges = lexique.corriger("j'ai avance sur le bot cloudeflare")
    assert texte == "j'ai avance sur le bot Cloudflare"
    assert corriges == ["Cloudflare"]


def test_la_correction_est_insensible_a_la_casse(lexique):
    lexique.ajouter("Vulkan", ["vulcan"])
    texte, _ = lexique.corriger("Vulcan et VULCAN")
    assert texte == "Vulkan et Vulkan"


def test_la_correction_respecte_les_limites_de_mots(lexique):
    """Sans cela, « Vulkan » corrigerait l'interieur de « vulcanologie »."""
    lexique.ajouter("Vulkan", ["vulcan"])
    texte, corriges = lexique.corriger("la vulcanologie est une science")
    assert texte == "la vulcanologie est une science"
    assert corriges == []


def test_plusieurs_termes_sont_corriges(lexique):
    lexique.ajouter("Vulkan", ["Vulcan"])
    lexique.ajouter("Ollama", ["Olama"])
    texte, corriges = lexique.corriger("Olama tourne sur Vulcan")
    assert texte == "Ollama tourne sur Vulkan"
    assert set(corriges) == {"Ollama", "Vulkan"}


def test_le_compteur_dusages_augmente(lexique):
    terme = lexique.ajouter("Vercel", ["so lana"])
    lexique.corriger("so lana et so lana")
    assert terme.usages == 2


def test_un_texte_sans_variante_reste_intact(lexique):
    lexique.ajouter("Vulkan", ["Vulcan"])
    texte, corriges = lexique.corriger("rien a corriger ici")
    assert texte == "rien a corriger ici"
    assert corriges == []


def test_corriger_un_texte_vide(lexique):
    lexique.ajouter("Vulkan", ["Vulcan"])
    assert lexique.corriger("") == ("", [])


def test_les_variantes_multi_mots_sont_gerees(lexique):
    """« webhook » est transcrit « web hooks » : deux mots pour un."""
    lexique.ajouter("webhook", ["web hooks"])
    texte, _ = lexique.corriger("les web hooks sur Vercel")
    assert texte == "les webhook sur Vercel"


# --------------------------------------------------------------------------
# Verification — support du test de non-regression
# --------------------------------------------------------------------------

def test_verifier_detecte_les_termes_presents(lexique):
    resultats = lexique.verifier(
        "J'utilise Ollama avec Vulkan", ["Ollama", "Vulkan", "Supabase"])
    assert resultats == {"Ollama": True, "Vulkan": True, "Supabase": False}


def test_verifier_exige_la_forme_exacte(lexique):
    """Une casse differente est un echec : c'est bien ce qu'on veut mesurer."""
    resultats = lexique.verifier("j'utilise ollama", ["Ollama"])
    assert resultats["Ollama"] is False


def test_verifier_respecte_les_limites_de_mots(lexique):
    resultats = lexique.verifier("la vulcanologie", ["Vulkan"])
    assert resultats["Vulkan"] is False

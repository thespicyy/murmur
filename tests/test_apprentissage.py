"""T4.5 — apprentissage par correction."""

from dataclasses import dataclass

import pytest

from murmur import apprentissage


@dataclass
class DicteeFactice:
    identifiant: int
    texte: str


# --------------------------------------------------------------------------
# Similarite
# --------------------------------------------------------------------------

def test_deux_textes_identiques_sont_parfaitement_similaires():
    assert apprentissage.similarite("bonjour", "bonjour") == 1.0


def test_deux_textes_etrangers_sont_peu_similaires():
    assert apprentissage.similarite(
        "le chat dort sur le canape",
        "recette de tarte aux pommes pour six personnes") < 0.5


# --------------------------------------------------------------------------
# Comparaison
# --------------------------------------------------------------------------

def test_un_mot_corrige_est_isole():
    analyse = apprentissage.comparer(
        "j'ai avance sur le bot cloudeflare",
        "j'ai avance sur le bot Cloudflare")
    assert analyse.est_correction
    assert len(analyse.substitutions) == 1
    assert analyse.substitutions[0].avant == "cloudeflare"
    assert analyse.substitutions[0].apres == "Cloudflare"


def test_plusieurs_corrections_sont_isolees():
    analyse = apprentissage.comparer(
        "Olama tourne sur Vulcan",
        "Ollama tourne sur Vulkan")
    paires = {(s.avant, s.apres) for s in analyse.substitutions}
    assert paires == {("Olama", "Ollama"), ("Vulcan", "Vulkan")}


def test_un_texte_inchange_ne_produit_aucune_substitution():
    analyse = apprentissage.comparer("texte identique", "texte identique")
    assert analyse.substitutions == ()
    assert not analyse.est_correction, "rien a apprendre d'un texte identique"


def test_un_texte_etranger_nest_pas_une_correction():
    """Copier autre chose ne doit pas etre pris pour une correction."""
    analyse = apprentissage.comparer(
        "j'ai avance sur le bot Cloudflare",
        "rendez-vous chez le dentiste mardi a quatorze heures")
    assert not analyse.est_correction


def test_les_ajouts_purs_ne_sont_pas_des_substitutions():
    """Ajouter une phrase n'apprend aucune forme erronee au lexique."""
    analyse = apprentissage.comparer(
        "premiere phrase",
        "premiere phrase et une seconde ajoutee ensuite")
    assert analyse.substitutions == ()


def test_les_suppressions_pures_ne_sont_pas_des_substitutions():
    analyse = apprentissage.comparer(
        "une phrase avec des mots en trop dedans",
        "une phrase avec des mots dedans")
    assert all(s.avant and s.apres for s in analyse.substitutions)


# --------------------------------------------------------------------------
# Tri vocabulaire / style — le point sensible
# --------------------------------------------------------------------------

def test_une_correction_de_vocabulaire_est_proposee():
    analyse = apprentissage.comparer(
        "je regarde DexScreener", "je regarde DexScreener")
    analyse = apprentissage.comparer(
        "je regarde Deckscreener", "je regarde DexScreener")
    assert [s.apres for s in analyse.propositions] == ["DexScreener"]


def test_une_reformulation_de_style_nest_pas_proposee():
    """Corriger « du coup » en « donc » est une preference, pas du vocabulaire.

    L'inscrire au lexique reecrirait tous les « du coup » futurs sans que
    l'utilisateur l'ait demande.
    """
    analyse = apprentissage.comparer(
        "du coup j'ai fait le truc", "donc j'ai fait le truc")
    assert analyse.propositions == (), \
        f"propose a tort : {[(s.avant, s.apres) for s in analyse.propositions]}"


def test_une_difference_de_casse_seule_nest_pas_proposee():
    """La table de remplacement est deja insensible a la casse."""
    analyse = apprentissage.comparer("j'utilise ollama", "j'utilise Ollama")
    assert analyse.propositions == ()


def test_une_reecriture_sans_parente_nest_pas_proposee():
    analyse = apprentissage.comparer(
        "il faudrait peut etre envisager cette approche",
        "on pourrait tenter autre chose")
    assert analyse.propositions == (), \
        f"propose a tort : {[(s.avant, s.apres) for s in analyse.propositions]}"


def test_deux_mots_francais_proches_ne_sont_pas_proposes():
    """« faudrait »/« devrait » se ressemblent autant que « Olama »/« Ollama ».

    C'est l'absence de majuscule qui les separe : sans elle, on exige une
    ressemblance bien plus forte.
    """
    analyse = apprentissage.comparer("il faudrait le faire",
                                     "il devrait le faire")
    assert analyse.propositions == ()


@pytest.mark.parametrize("avant, apres, attendu", [
    # Termes techniques : la majuscule autorise un seuil plus permissif.
    ("obsidienne", "Obsidian", True),
    ("playrighteuse", "Playwright", True),
    ("ver cel", "Vercel", True),
    ("Grafanna", "Grafana", True),
    # Sans majuscule, il faut une ressemblance nettement plus forte.
    ("web hooks", "webhook", True),
    ("dire", "lire", False),
    ("etre", "autre", False),
    ("pense", "passe", False),
])
def test_le_seuil_depend_de_la_majuscule(avant, apres, attendu):
    assert apprentissage.Substitution(avant, apres).est_vocabulaire is attendu


def test_la_majuscule_est_detectee_ou_qu_elle_soit():
    assert apprentissage.Substitution("x", "Vulkan").porte_une_majuscule
    assert apprentissage.Substitution("x", "DexScreener").porte_une_majuscule
    assert not apprentissage.Substitution("x", "webhook").porte_une_majuscule


def test_un_bloc_remplace_est_decoupe_autour_des_mots_apparies():
    """difflib groupe les remplacements voisins : il faut les separer.

    Sans ce decoupage, « du coup Olama » -> « donc Ollama » entrerait au
    lexique comme un terme de trois mots, et reecrirait la phrase entiere a
    chaque occurrence.
    """
    analyse = apprentissage.comparer("du coup Olama tourne",
                                     "donc Ollama tourne")
    paires = [(s.avant, s.apres) for s in analyse.substitutions]
    assert ("Olama", "Ollama") in paires, "le terme n'a pas ete isole"
    assert ("du coup", "donc") in paires, "la tournure doit rester groupee"


def test_les_substitutions_restent_visibles_meme_non_proposees():
    """L'utilisateur doit pouvoir voir ce qui a change, meme ecarte."""
    analyse = apprentissage.comparer(
        "du coup j'ai fait le truc", "donc j'ai fait le truc")
    assert analyse.substitutions, "la substitution doit rester consultable"


@pytest.mark.parametrize("avant, apres, attendu", [
    ("cloudeflare", "Cloudflare", True),
    ("Vulcan", "Vulkan", True),
    ("Kinter", "Tkinter", True),
    ("web hooks", "webhook", True),
    ("du coup", "donc", False),
    ("", "quelque chose", False),
    ("truc", "", False),
])
def test_classement_vocabulaire_ou_style(avant, apres, attendu):
    assert apprentissage.Substitution(avant, apres).est_vocabulaire is attendu


# --------------------------------------------------------------------------
# Rapprochement avec une dictee
# --------------------------------------------------------------------------

def test_la_bonne_dictee_est_retrouvee():
    dictees = [
        DicteeFactice(1, "rendez-vous chez le dentiste mardi"),
        DicteeFactice(2, "j'ai avance sur le bot cloudeflare ce matin"),
        DicteeFactice(3, "il faut acheter du pain et du lait"),
    ]
    analyse = apprentissage.meilleure_correspondance(
        "j'ai avance sur le bot Cloudflare ce matin", dictees)

    assert analyse is not None
    assert analyse.dictee_id == 2
    assert [s.apres for s in analyse.propositions] == ["Cloudflare"]


def test_un_texte_sans_rapport_ne_correspond_a_rien():
    """Rien ne doit etre conserve quand le texte copie n'est pas une correction."""
    dictees = [DicteeFactice(1, "j'ai avance sur le bot Cloudflare")]
    assert apprentissage.meilleure_correspondance(
        "mot de passe : correct-horse-battery-staple", dictees) is None


def test_un_texte_identique_a_une_dictee_ne_correspond_pas():
    """Recopier sa dictee telle quelle n'apprend rien."""
    dictees = [DicteeFactice(1, "texte parfaitement transcrit")]
    assert apprentissage.meilleure_correspondance(
        "texte parfaitement transcrit", dictees) is None


def test_sans_dictee_aucune_correspondance():
    assert apprentissage.meilleure_correspondance("un texte", []) is None


# --------------------------------------------------------------------------
# Texte copie noye dans un document — le cas rencontre en usage reel
# --------------------------------------------------------------------------

DICTEE_REELLE = "Il se produit quand j'appuie sur le raccourci CTRL-HATS-N."
CORRIGEE_REELLE = "Il se produit quand j'appuie sur le raccourci CTRL-ALT-N."


def test_la_correction_est_trouvee_meme_avec_loriginal_conserve():
    """Garder l'original au-dessus de la correction est un usage naturel."""
    dictees = [DicteeFactice(1, DICTEE_REELLE)]
    copie = f"{DICTEE_REELLE}\ncorrection : {CORRIGEE_REELLE}"

    analyse = apprentissage.meilleure_correspondance(copie, dictees)
    assert analyse is not None
    # Le jeton entier est retenu, pas la syllabe : apprendre « HATS » -> « ALT »
    # reecrirait ces lettres partout ailleurs.
    assert ("CTRL-HATS-N", "CTRL-ALT-N") in [
        (s.avant, s.apres) for s in analyse.substitutions]


def test_la_correction_est_trouvee_dans_un_document_entier():
    """`Ctrl+A` copie tout le document, pas seulement la phrase corrigee.

    Comparee a l'ensemble, une dictee d'une ligne se noie : c'est ce qui
    produisait « aucune correspondance » alors que la correction etait la.
    """
    dictees = [DicteeFactice(1, DICTEE_REELLE)]
    copie = "\n".join([
        "Notes de la journee",
        "",
        "Rendez-vous chez le dentiste mardi a quatorze heures.",
        "Penser a racheter du cafe et des filtres.",
        CORRIGEE_REELLE,
        "Appeler la banque pour le virement.",
        "Liste de courses : pain, lait, oeufs, farine, beurre.",
    ])

    analyse = apprentissage.meilleure_correspondance(copie, dictees)
    assert analyse is not None, "la correction s'est noyee dans le document"
    assert analyse.dictee_id == 1
    # Le jeton entier est retenu, pas la syllabe : apprendre « HATS » -> « ALT »
    # reecrirait ces lettres partout ailleurs.
    assert ("CTRL-HATS-N", "CTRL-ALT-N") in [
        (s.avant, s.apres) for s in analyse.substitutions]


def test_un_document_sans_correction_ne_correspond_toujours_pas():
    """La decoupe en lignes ne doit pas rendre l'outil credule."""
    dictees = [DicteeFactice(1, DICTEE_REELLE)]
    copie = "\n".join([
        "Rendez-vous chez le dentiste mardi.",
        "Racheter du cafe.",
        "Appeler la banque.",
    ])
    assert apprentissage.meilleure_correspondance(copie, dictees) is None


def test_les_morceaux_incluent_le_texte_entier_en_premier():
    """Une correction portant sur tout le bloc doit rester prioritaire."""
    fragments = apprentissage.morceaux("premiere ligne\nseconde ligne")
    assert fragments[0] == "premiere ligne\nseconde ligne"
    assert "premiere ligne" in fragments
    assert "seconde ligne" in fragments


def test_les_morceaux_regroupent_les_paragraphes():
    """Une dictee longue peut avoir ete coupee en plusieurs lignes."""
    fragments = apprentissage.morceaux(
        "debut de phrase\nsuite de la phrase\n\nautre paragraphe")
    assert "debut de phrase suite de la phrase" in fragments


def test_les_morceaux_dun_texte_simple_restent_uniques():
    assert apprentissage.morceaux("une seule ligne") == ["une seule ligne"]


# --------------------------------------------------------------------------
# Diagnostic
# --------------------------------------------------------------------------

def test_le_diagnostic_signale_une_base_vide():
    assert "aucune dictee" in apprentissage.diagnostiquer("texte", [])


def test_le_diagnostic_chiffre_la_ressemblance_quand_elle_est_partielle():
    dictees = [DicteeFactice(1, "le chat dort sur le canape du salon")]
    message = apprentissage.diagnostiquer(
        "le chien aboie dans le jardin voisin", dictees)
    assert "%" in message


def test_le_diagnostic_signale_labsence_de_ressemblance():
    dictees = [DicteeFactice(1, DICTEE_REELLE)]
    message = apprentissage.diagnostiquer("azerty uiop qsdfgh", dictees)
    assert "ressemble" in message


def test_la_dictee_la_plus_proche_est_retenue():
    """Deux dictees voisines : c'est la plus ressemblante qui doit gagner."""
    dictees = [
        DicteeFactice(1, "le bot tourne sur Vulcan depuis hier soir"),
        DicteeFactice(2, "le bot tourne sur Vulcan depuis hier soir tres bien"),
    ]
    analyse = apprentissage.meilleure_correspondance(
        "le bot tourne sur Vulkan depuis hier soir", dictees)
    assert analyse is not None and analyse.dictee_id == 1


# --------------------------------------------------------------------------
# Le bruit de difflib
# --------------------------------------------------------------------------
#
# `SequenceMatcher` ecarte de son index, au-dela de 200 elements, tout element
# present dans plus d'un pour cent de la sequence. L'heuristique vise des
# LIGNES de code ; appliquee a des CARACTERES, elle ecarte l'espace, la
# virgule et la plupart des lettres, et l'algorithme ne peut plus amorcer ses
# correspondances que sur les caracteres rares. Selon l'endroit ou tombe la
# correction, il trouve un long bloc commun — ou se fragmente.
#
# Le defaut n'apparait donc PAS a partir d'une longueur donnee : il frappe par
# intermittence au-dela de deux cents caracteres. C'est ce qui l'a rendu si
# discret — les dictees courtes marchaient, et les longues une fois sur deux.

#: Un cas qui declenche le defaut : 0.060 au lieu de 0.968, alors que les deux
#: textes ne different que d'un mot sur deux cent trente-trois caracteres.
LONG_DICTE = (
    "Et pour le deploiement, tu peux aussi y avoir acces. Attends, j'ai "
    "l'impression que tu n'as pas cree de branche. pour que la prochaine fois "
    "que je te demande une revue, tu saches quoi faire. Parce qu'en fait, "
    "ca me sert de reference."
)
LONG_CORRIGE = LONG_DICTE.replace("le deploiement", "Cloudflare")


def test_une_faute_corrigee_dans_un_long_texte_reste_une_correction():
    """Le cas qui a fait echouer l'apprentissage en usage reel.

    Deux textes qui ne different que d'un mot doivent se ressembler. Sans
    precaution, difflib rendait 0.060 — dix fois moins que le seuil — et
    l'utilisateur lisait « aucune dictee ne ressemble au texte copie ».
    """
    assert len(LONG_DICTE) > 200, "en deca, le defaut ne se declenche pas"
    assert apprentissage.similarite(LONG_DICTE, LONG_CORRIGE) > 0.95


def test_la_correction_est_retrouvee_dans_un_long_texte():
    dictees = [DicteeFactice(1, LONG_DICTE)]
    analyse = apprentissage.meilleure_correspondance(LONG_CORRIGE, dictees)

    assert analyse is not None, "la dictee corrigee n'a pas ete reconnue"
    assert analyse.dictee_id == 1
    assert ("le deploiement", "Cloudflare") in [(s.avant, s.apres)
                                               for s in analyse.substitutions]


def test_la_ressemblance_ne_chute_pas_avec_la_longueur():
    """Le meme texte, rallonge, doit garder la meme ressemblance.

    C'est la propriete que le bruit de difflib brisait : la mesure devenait
    fonction de la longueur, alors que la correction, elle, ne changeait pas.
    """
    phrase = ("Concernant ta question, je veux bien que tu corriges en ligne, "
              "parce que ca me sert de reference pour la suite. ")
    ressemblances = []
    for repetitions in (1, 3, 6, 12):
        avant = (phrase * repetitions).strip()
        apres = avant.replace("corriges", "corrige", 1)
        ressemblances.append(apprentissage.similarite(avant, apres))

    assert min(ressemblances) > 0.98, ressemblances


def test_les_mots_outils_ne_sont_pas_ecartes_du_decoupage():
    """Meme precaution sur la comparaison MOT a mot.

    Au-dela de deux cents mots, « de », « que » et « le » seraient juges trop
    frequents et ecartes de l'index : le decoupage en substitutions partirait
    alors de travers, en plein milieu des phrases.
    """
    phrase = "je veux bien que tu corriges la ligne de ce fichier la "
    avant = (phrase * 25).strip()             # largement plus de 200 mots
    apres = avant.replace("fichier", "document", 1)

    assert len(avant.split()) > 200
    analyse = apprentissage.comparer(avant, apres)
    assert [(s.avant, s.apres) for s in analyse.substitutions] == \
        [("fichier", "document")]


# --------------------------------------------------------------------------
# Ce que le diagnostic laisse voir
# --------------------------------------------------------------------------
#
# « Aucune correspondance » sans plus laisse sans prise : l'utilisateur ne sait
# pas s'il a mal copie. Un cas reel est reste introuvable jusqu'a ce qu'on lise
# le presse-papier a la main — il contenait le texte NON corrige.

def test_le_diagnostic_montre_ce_qui_a_ete_lu():
    dictees = [DicteeFactice(1, "Je fais un test pour Cloudflare.")]
    raison = apprentissage.diagnostiquer("Rien a voir avec la dictee.", dictees)

    assert "Rien a voir avec la dictee." in raison


def test_le_diagnostic_tronque_un_texte_long():
    """La boite de dialogue ne doit pas se remplir du document entier."""
    dictees = [DicteeFactice(1, "court")]
    raison = apprentissage.diagnostiquer("mot " * 200, dictees)

    assert "…" in raison
    assert len(raison) < 300


def test_un_texte_identique_designe_la_cause_probable():
    """Le message le plus deroutant, et sa cause presque toujours la meme.

    On a corrige le texte dans l'application sans le recopier : Murmur ne lit
    que le presse-papier, jamais le champ de saisie, et y retrouve ce qu'il
    venait d'y ecrire pour le coller. Dire « texte identique » laissait
    l'utilisateur convaincu d'avoir corrige — ce qu'il avait fait.
    """
    dictee = "Je fais un test pour Cloudflare."
    raison = apprentissage.diagnostiquer(dictee, [DicteeFactice(1, dictee)])

    assert "Ctrl+C" in raison, "la cause probable n'est pas nommee"
    assert dictee in raison, "on ne voit pas ce qui a ete copie"


def test_un_presse_papier_vide_le_dit_franchement():
    """Et ne pretend pas qu'aucune dictee ne lui ressemble."""
    raison = apprentissage.diagnostiquer("   \n  ", [DicteeFactice(1, "abc")])

    assert "vide" in raison
    assert "ressemble" not in raison

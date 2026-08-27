"""Ce que le tableau de bord envoie a sa page.

Une couche a part, entre le stockage et l'affichage — et la premiere du
projet qui se teste sans ouvrir de fenetre. La version Tkinter melait calcul
et widgets : verifier une regle demandait de batir une interface.
"""

from datetime import date, datetime, timedelta

import pytest

from murmur import langue as module_langue, lexicon, store
from murmur.tableau import donnees


@pytest.fixture
def historique(donnees_dossier=None):
    with store.Historique() as base:
        yield base


@pytest.fixture(autouse=True)
def dossier(donnees):
    """Chaque test ecrit dans son propre dossier jetable."""
    return donnees


@pytest.fixture
def lexique():
    return lexicon.Lexique()


@pytest.fixture
def mot():
    return module_langue.Traducteur(langue="en")


@pytest.fixture
def mot_fr():
    return module_langue.Traducteur(langue="fr")


# --------------------------------------------------------------------------
# Vitesse et temps gagne
# --------------------------------------------------------------------------

def test_le_rapport_au_clavier(historique, lexique, mot):
    # Soixante mots en trente secondes : cent vingt mots par minute.
    historique.ajouter(" ".join(["mot"] * 60), duree_audio_ms=30_000)
    vue = donnees.insights(historique, lexique, mot)

    assert vue["vitesse"]["valeur"] == 120
    assert vue["vitesse"]["rapport"] == "3.0"


def test_la_jauge_plafonne(historique, lexique, mot):
    """Au-dela du plafond, l'aiguille reste au bout plutot que de sortir."""
    historique.ajouter(" ".join(["mot"] * 500), duree_audio_ms=10_000)
    assert donnees.insights(historique, lexique, mot)["vitesse"]["part"] == 1.0


def test_sans_dictee_il_n_y_a_pas_de_rapport(historique, lexique, mot):
    """Afficher « ×0,0 » serait un chiffre invente."""
    assert donnees.insights(historique, lexique,
                            mot)["vitesse"]["rapport"] is None


def test_le_temps_gagne_compare_a_la_frappe(historique, lexique, mot):
    historique.ajouter(" ".join(["mot"] * 400), duree_audio_ms=120_000)
    stats = historique.statistiques()

    # 400 mots : dix minutes au clavier, deux a la voix.
    assert donnees.temps_gagne(stats) == 8


def test_le_temps_gagne_ne_devient_jamais_negatif(historique, lexique, mot):
    """Une dictee plus lente que la frappe ne fait pas perdre du temps a
    l'affichage : elle en fait gagner zero."""
    historique.ajouter("un mot", duree_audio_ms=600_000)
    assert donnees.temps_gagne(historique.statistiques()) == 0


# --------------------------------------------------------------------------
# Tendance
# --------------------------------------------------------------------------

def test_la_tendance_est_muette_le_premier_mois(historique):
    """« +100 % » compare a rien ne veut rien dire."""
    historique.ajouter("des mots ce mois-ci")
    assert donnees.tendance(historique) is None


def test_la_tendance_compare_au_mois_precedent(historique):
    premier = date.today().replace(day=1)
    veille = datetime.combine(premier - timedelta(days=1),
                              datetime.min.time())
    historique.ajouter("un deux trois quatre", horodatage=veille)
    historique.ajouter("un deux")

    releve = donnees.tendance(historique)
    assert releve["hausse"] is False
    assert releve["texte"] == "50 %"


def test_une_hausse_est_marquee_comme_telle(historique):
    premier = date.today().replace(day=1)
    veille = datetime.combine(premier - timedelta(days=1),
                              datetime.min.time())
    historique.ajouter("un deux", horodatage=veille)
    historique.ajouter("un deux trois quatre")

    assert donnees.tendance(historique)["hausse"] is True


# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------

def test_les_parts_font_cent(historique, lexique, mot):
    historique.ajouter("un deux trois", cible="brave.exe — page")
    historique.ajouter("quatre", cible="Code.exe — projet")

    lignes = donnees.insights(historique, lexique,
                              mot)["applications"]["lignes"]
    assert sum(ligne["part"] for ligne in lignes) == pytest.approx(1.0)


def test_les_applications_portent_un_nom_lisible(historique, lexique, mot):
    historique.ajouter("un deux", cible="Code.exe — murmur")
    ligne = donnees.insights(historique, lexique,
                             mot)["applications"]["lignes"][0]

    assert ligne["nom"] == "VS Code"
    assert ligne["picto"] == "app_code"
    assert ligne["pourcentage"] == "100 %"


def test_sans_dictee_la_carte_dusage_est_vide(historique, lexique, mot):
    vue = donnees.insights(historique, lexique, mot)
    assert vue["applications"]["lignes"] == []


# --------------------------------------------------------------------------
# Calendrier
# --------------------------------------------------------------------------

def test_les_colonnes_commencent_un_lundi(historique):
    serie = historique.mots_par_jour(30)
    premiere = donnees.colonnes(serie)[0]

    # Les cases de remplissage precedent le premier vrai jour.
    vrais = [case for case in premiere if case]
    assert vrais[0][0].weekday() == premiere.index(vrais[0])


def test_chaque_colonne_compte_sept_jours(historique):
    for colonne in donnees.colonnes(historique.mots_par_jour(40)):
        assert len(colonne) == 7


def test_les_cases_de_remplissage_restent_vides(historique):
    """Les peindre au palier le plus pale inventerait des jours."""
    plates = donnees.cases(historique.mots_par_jour(30))
    assert None in plates


def test_une_journee_a_un_mot_se_distingue_dune_journee_vide(historique):
    """Le premier palier commence des le premier mot : un jour ou l'on a dicte
    ne doit jamais se confondre avec un jour vide."""
    historique.ajouter("mot")
    paliers = [c["niveau"] for c in donnees.cases(historique.mots_par_jour(20))
               if c is not None]

    assert 0 in paliers, "aucune journee vide"
    assert max(paliers) >= 1, "la journee dictee est restee au palier du vide"


@pytest.mark.parametrize("mots, maximum, attendu", [
    (0, 100, 0),        # rien de dicte
    (1, 100, 1),        # un seul mot compte deja
    (25, 100, 1),       # les paliers decoupent le maximum en quarts
    (50, 100, 2),
    (75, 100, 3),
    (100, 100, 4),      # le maximum tient le dernier palier
])
def test_les_paliers_se_repartissent_sur_le_maximum(mots, maximum, attendu):
    """Les paliers sont pris sur le maximum observe et non sur des seuils
    fixes : le calendrier doit rester lisible pour qui dicte cent mots par
    jour comme pour qui en dicte cinq mille."""
    assert donnees.niveau(mots, maximum) == attendu


def test_aucun_palier_ne_depasse_l_echelle():
    for maximum in (1, 7, 250, 100_000):
        for mots in (0, 1, maximum // 2, maximum):
            assert 0 <= donnees.niveau(mots, maximum) <= donnees.NIVEAUX


def test_une_case_porte_de_quoi_faire_une_infobulle(historique, mot):
    """La page ne recalcule ni la date ni le compte : ce serait redescendre
    les regles de l'application dans le HTML."""
    historique.ajouter("un deux trois")
    remplies = [c for c in donnees.cases(historique.mots_par_jour(7), mot)
                if c and c["niveau"]]

    assert remplies, "la dictee du jour n'apparait pas"
    assert remplies[-1]["jour"] == date.today().isoformat()
    assert "3" in remplies[-1]["titre"]


def test_le_calendrier_se_pagine_vers_le_passe(historique, mot):
    """Les fleches de la carte remontent le temps sans que la page connaisse
    la moindre date."""
    recente = donnees.calendrier(historique, mot, 0)
    ancienne = donnees.calendrier(historique, mot, 1)

    jours = lambda page: [c["jour"] for c in page["cases"] if c]  # noqa: E731
    assert max(jours(ancienne)) < min(jours(recente))
    assert len(recente["cases"]) == len(ancienne["cases"])


def test_les_mois_se_suivent_sans_doublon(historique, mot):
    releve = donnees.mois(historique.mots_par_jour(120), mot)
    noms = [m["nom"] for m in releve]

    assert noms == list(dict.fromkeys(noms)), "un mois apparait deux fois"
    assert sum(m["semaines"] for m in releve) == \
        len(donnees.colonnes(historique.mots_par_jour(120)))


def test_le_calendrier_survit_a_une_base_vide(historique, lexique, mot):
    vue = donnees.insights(historique, lexique, mot)
    assert vue["activite"]["cases"]
    assert len(vue["activite"]["jours"]) == 7


# --------------------------------------------------------------------------
# Dictees
# --------------------------------------------------------------------------

def test_les_dictees_sont_groupees_par_jour(historique, mot):
    hier = datetime.now() - timedelta(days=1)
    historique.ajouter("aujourd'hui")
    historique.ajouter("la veille", horodatage=hier)

    groupes = donnees.dictees(historique, mot, limite=10)["groupes"]
    assert [g["titre"] for g in groupes] == ["TODAY", "YESTERDAY"]


def test_la_limite_annonce_ce_qui_reste(historique, mot):
    for numero in range(6):
        historique.ajouter(f"dictee {numero}")

    vue = donnees.dictees(historique, mot, limite=3)
    assert vue["reste"] is True
    assert sum(len(g["lignes"]) for g in vue["groupes"]) == 3


def test_la_derniere_page_ne_promet_rien(historique, mot):
    historique.ajouter("une seule")
    assert donnees.dictees(historique, mot, limite=10)["reste"] is False


def test_la_recherche_filtre(historique, mot):
    historique.ajouter("le chat dort")
    historique.ajouter("le chien aboie")

    vue = donnees.dictees(historique, mot, limite=10, terme="chat")
    textes = [l["texte"] for g in vue["groupes"] for l in g["lignes"]]
    assert textes == ["le chat dort"]


def test_chaque_ligne_porte_son_identifiant(historique, mot):
    """La page doit pouvoir designer une dictee pour la supprimer."""
    identifiant = historique.ajouter("une dictee")
    ligne = donnees.dictees(historique, mot, limite=10)["groupes"][0]["lignes"][0]
    assert ligne["id"] == identifiant


# --------------------------------------------------------------------------
# Dictionnaire
# --------------------------------------------------------------------------

def test_les_termes_sont_ranges_par_ordre_alphabetique(lexique, mot):
    for terme in ("Vulkan", "Cloudflare", "supabase"):
        lexique.ajouter(terme)

    noms = [t["terme"] for t in donnees.dictionnaire(lexique, mot)["termes"]]
    assert noms == ["Cloudflare", "supabase", "Vulkan"]


def test_un_terme_porte_ses_variantes(lexique, mot):
    lexique.ajouter("Cloudflare", ["cloudeflare"])
    terme = donnees.dictionnaire(lexique, mot)["termes"][0]

    assert terme["variantes"] == ["cloudeflare"]
    assert terme["usages"] is None


def test_le_sous_titre_compte_les_termes(lexique, mot):
    lexique.ajouter("Vulkan")
    assert donnees.dictionnaire(lexique, mot)["sous_titre"].startswith("1 term")


def test_la_langue_suit_le_traducteur(historique, lexique, mot_fr):
    historique.ajouter("une dictee")
    vue = donnees.insights(historique, lexique, mot_fr)

    assert "dictée" in vue["volume"]["dictees"]
    assert vue["activite"]["jours"][0] == "Lu"


# --------------------------------------------------------------------------
# Reglages
# --------------------------------------------------------------------------
#
# Le formulaire est decrit en Python et non dans la page : c'est ce qui rend
# ces verifications possibles sans ouvrir de fenetre. La version Tkinter
# construisait chaque champ par un appel de widget, et rien de tout cela
# n'etait atteignable autrement qu'a l'oeil.

@pytest.fixture
def formulaire(mot):
    from murmur import config as configuration
    return donnees.reglages(configuration.charger(), mot, False, "C:/donnees")


def test_chaque_champ_appartient_a_une_section_connue():
    """Un champ range dans une section absente disparaitrait de la page sans
    que rien ne le signale."""
    for fiche in donnees.CHAMPS:
        assert fiche["section"] in donnees.SECTIONS, fiche["chemin"]


def test_aucune_section_n_est_vide(formulaire):
    for section in formulaire["sections"]:
        assert section["champs"], section["cle"]


def test_chaque_chemin_mene_vraiment_a_un_reglage():
    """Une faute de frappe dans un chemin passerait inapercue jusqu'a
    l'enregistrement : `definir` cree les chemins manquants sans se plaindre,
    et le reglage irait s'ecrire a cote de celui qu'il devait changer.

    `conf[...]` leve `KeyError` sur un chemin inconnu : c'est ce qui fait la
    verification, et non une comparaison de valeur — un reglage a le droit de
    valoir `None`.
    """
    from murmur import config as configuration
    conf = configuration.charger()
    for fiche in donnees.CHAMPS:
        if fiche["chemin"] == donnees.DEMARRAGE:
            continue
        conf[fiche["chemin"]]


def test_le_demarrage_n_est_pas_un_chemin_de_configuration():
    """S'il en devenait un, `enregistrer_reglages` l'ecrirait dans le fichier
    au lieu de le confier au systeme, et le raccourci de demarrage ne serait
    jamais depose."""
    from murmur import config as configuration
    with pytest.raises(KeyError):
        configuration.charger()[donnees.DEMARRAGE]


def test_tous_les_champs_sont_traduits(formulaire):
    """Un libelle non traduit s'afficherait comme sa cle, « reg.machin »."""
    for section in formulaire["sections"]:
        assert "." not in section["titre"]
        for champ in section["champs"]:
            assert not champ["libelle"].startswith("reg.")
            if champ["aide"]:
                assert not champ["aide"].startswith("reg.")


def test_les_valeurs_courantes_viennent_de_la_configuration():
    from murmur import config as configuration
    conf = configuration.charger()
    conf.definir("raccourcis.maintien", "ctrl+alt+k")
    mot = module_langue.Traducteur(langue="fr")

    formulaire = donnees.reglages(conf, mot, False, "C:/donnees")
    champs = {c["chemin"]: c
              for s in formulaire["sections"] for c in s["champs"]}
    assert champs["raccourcis.maintien"]["valeur"] == "ctrl+alt+k"


def test_le_demarrage_automatique_ne_vient_pas_de_la_configuration(mot):
    """C'est un etat du systeme — un raccourci depose dans un dossier — et non
    un reglage ecrit dans le fichier."""
    from murmur import config as configuration
    conf = configuration.charger()
    for actif in (True, False):
        formulaire = donnees.reglages(conf, mot, actif, "C:/donnees")
        champs = {c["chemin"]: c
                  for s in formulaire["sections"] for c in s["champs"]}
        assert champs[donnees.DEMARRAGE]["valeur"] is actif


def test_les_choix_portent_leur_libelle(formulaire):
    champs = {c["chemin"]: c
              for s in formulaire["sections"] for c in s["champs"]}
    theme = champs["interface.theme"]
    assert theme["type"] == "choix"
    assert [c["valeur"] for c in theme["choix"]] == ["auto", "clair", "sombre"]
    assert all(c["libelle"] for c in theme["choix"])


def test_la_valeur_courante_figure_parmi_les_choix(formulaire):
    """Sans cela, aucun segment ne serait marque actif et la page enverrait
    `undefined` a l'enregistrement."""
    for section in formulaire["sections"]:
        for champ in section["champs"]:
            if champ["type"] == "choix":
                valeurs = [c["valeur"] for c in champ["choix"]]
                assert champ["valeur"] in valeurs, champ["chemin"]


def test_le_chemin_des_donnees_figure_dans_la_note(mot):
    from murmur import config as configuration
    formulaire = donnees.reglages(configuration.charger(), mot, False,
                                  "C:/quelque/part")
    systeme = [s for s in formulaire["sections"]
               if s["cle"] == "systeme"][0]
    assert "C:/quelque/part" in systeme["note"]

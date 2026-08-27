"""T3.5 — historique des dictees et corpus de corrections."""

from datetime import date, datetime, timedelta

import pytest

from murmur import config as cfg, store


@pytest.fixture
def historique(donnees):
    with store.Historique() as base:
        yield base


def hier(jours: int = 1) -> datetime:
    return datetime.now() - timedelta(days=jours)


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def test_la_base_est_creee_avec_son_schema(historique):
    assert historique.chemin.exists()
    assert historique.version_schema == store.SCHEMA


def test_rouvrir_une_base_existante_ne_la_recree_pas(donnees):
    with store.Historique() as base:
        identifiant = base.ajouter("premiere dictee")
    with store.Historique() as base:
        assert base.version_schema == store.SCHEMA
        assert [d.identifiant for d in base.recentes()] == [identifiant]


# --------------------------------------------------------------------------
# Ecriture et lecture
# --------------------------------------------------------------------------

def test_une_dictee_est_enregistree_avec_ses_mesures(historique):
    historique.ajouter("bonjour le monde", duree_audio_ms=2000,
                       transcription_ms=250, latence_ms=380,
                       cible="notepad.exe")
    dictee = historique.recentes()[0]

    assert dictee.texte == "bonjour le monde"
    assert dictee.mots == 3
    assert dictee.latence_ms == 380
    assert dictee.cible == "notepad.exe"
    assert dictee.heure


def test_les_dictees_reviennent_de_la_plus_recente_a_la_plus_ancienne(historique):
    for i, moment in enumerate([hier(3), hier(1), datetime.now()]):
        historique.ajouter(f"dictee {i}", horodatage=moment)
    assert [d.texte for d in historique.recentes()] == \
        ["dictee 2", "dictee 1", "dictee 0"]


def test_la_limite_est_respectee(historique):
    for i in range(10):
        historique.ajouter(f"dictee {i}")
    assert len(historique.recentes(limite=4)) == 4


def test_filtrer_par_date(historique):
    historique.ajouter("ancienne", horodatage=hier(5))
    historique.ajouter("recente")
    resultats = historique.recentes(depuis=date.today())
    assert [d.texte for d in resultats] == ["recente"]


def test_recherche_par_contenu(historique):
    historique.ajouter("le chat dort sur le canape")
    historique.ajouter("le chien aboie")
    assert [d.texte for d in historique.chercher("chat")] == \
        ["le chat dort sur le canape"]


def test_recherche_sans_resultat(historique):
    historique.ajouter("bonjour")
    assert historique.chercher("introuvable") == []


def test_suppression(historique):
    identifiant = historique.ajouter("a supprimer")
    assert historique.supprimer(identifiant)
    assert historique.recentes() == []
    assert not historique.supprimer(identifiant), "deuxieme suppression"


def test_comptage_des_mots():
    assert store.compter_mots("un deux trois") == 3
    assert store.compter_mots("  espaces   multiples  ") == 2
    assert store.compter_mots("") == 0


def test_mots_par_minute_dune_dictee(historique):
    historique.ajouter("un deux trois quatre", duree_audio_ms=60_000)
    assert historique.recentes()[0].mots_par_minute == pytest.approx(4.0)


def test_mots_par_minute_sans_duree_ne_divise_pas_par_zero(historique):
    historique.ajouter("texte", duree_audio_ms=0)
    assert historique.recentes()[0].mots_par_minute == 0.0


# --------------------------------------------------------------------------
# Corpus de corrections
# --------------------------------------------------------------------------

def test_une_correction_est_enregistree(historique):
    identifiant = historique.ajouter("le bot cloudeflare")
    historique.ajouter_correction("cloudeflare", "Cloudflare",
                                  dictee_id=identifiant)
    # Pas d'API de lecture a ce stade : le corpus sert la V2. On verifie
    # seulement qu'il s'accumule sans erreur.
    historique.ajouter_correction("Vulcan", "Vulkan")


def test_vider_lhistorique_preserve_le_corpus(historique):
    """Le corpus est la matiere de l'apprentissage : il ne se jette pas.

    Un utilisateur qui efface son historique veut faire disparaitre ses
    textes, pas reduire a neant des mois d'apprentissage.
    """
    identifiant = historique.ajouter("une dictee")
    historique.ajouter_correction("avant", "apres", dictee_id=identifiant)

    historique.vider()

    assert historique.recentes() == []
    restant = historique._connexion.execute(
        "SELECT COUNT(*) FROM corrections").fetchone()[0]
    assert restant == 1, "le corpus a ete efface avec l'historique"


# --------------------------------------------------------------------------
# Statistiques
# --------------------------------------------------------------------------

def test_statistiques_dune_base_vide(historique):
    stats = historique.statistiques()
    assert stats.total_mots == 0
    assert stats.total_dictees == 0
    assert stats.mots_par_minute == 0.0
    assert stats.jours_consecutifs == 0


def test_statistiques_cumulees(historique):
    historique.ajouter("un deux trois", duree_audio_ms=30_000)
    historique.ajouter("quatre cinq", duree_audio_ms=30_000)
    stats = historique.statistiques()

    assert stats.total_dictees == 2
    assert stats.total_mots == 5
    assert stats.mots_par_minute == pytest.approx(5.0)  # 5 mots en 1 minute
    assert stats.mots_aujourdhui == 5


def test_les_mots_du_jour_excluent_les_jours_precedents(historique):
    historique.ajouter("hier hier hier", horodatage=hier(1))
    historique.ajouter("aujourd hui")
    stats = historique.statistiques()
    assert stats.total_mots == 5
    assert stats.mots_aujourdhui == 2


def test_serie_dun_seul_jour(historique):
    historique.ajouter("aujourd hui")
    assert historique.statistiques().jours_consecutifs == 1


def test_serie_de_jours_consecutifs(historique):
    for jours in (0, 1, 2, 3):
        historique.ajouter("dictee", horodatage=hier(jours))
    assert historique.statistiques().jours_consecutifs == 4


def test_une_interruption_casse_la_serie(historique):
    for jours in (0, 1, 3, 4):   # il manque le jour 2
        historique.ajouter("dictee", horodatage=hier(jours))
    assert historique.statistiques().jours_consecutifs == 2


def test_la_serie_tolere_de_navoir_pas_encore_dicte_aujourdhui(historique):
    """Consulter le matin avant d'avoir dicte ne doit pas remettre a zero."""
    historique.ajouter("dictee", horodatage=hier(1))
    historique.ajouter("dictee", horodatage=hier(2))
    assert historique.statistiques().jours_consecutifs == 2


def test_la_serie_est_nulle_apres_une_longue_absence(historique):
    historique.ajouter("dictee", horodatage=hier(5))
    assert historique.statistiques().jours_consecutifs == 0


# --------------------------------------------------------------------------
# Integration avec l'application
# --------------------------------------------------------------------------

def test_seules_les_dictees_reussies_sont_archivees(donnees, monkeypatch):
    """Un rejet n'a rien a retrouver plus tard et fausserait les statistiques."""
    import numpy as np
    from murmur import audio, config, inject
    from murmur.app import Application

    conf = config.charger()
    application = Application(conf)
    monkeypatch.setattr(application.injecteur, "injecter",
                        lambda t: inject.ResultatInjection(duree_pose_ms=1.0))

    try:
        # Une capture vide : rejetee par le garde.
        application._traiter(
            audio.Capture(np.zeros(0, dtype=np.float32), audio.TAUX),
            "cible", 0.0)
        assert application.historique.recentes() == []

        # Une dictee normale.
        monkeypatch.setattr(application.moteur, "transcrire",
                            lambda *a, **k: "bonjour")
        signal = np.full(int(audio.TAUX * 0.5), 0.3, dtype=np.float32)
        application._traiter(audio.Capture(signal, audio.TAUX), "cible", 0.0)
        assert [d.texte for d in application.historique.recentes()] == ["bonjour"]
    finally:
        application.historique.fermer()

# --------------------------------------------------------------------------
# Activite jour par jour
# --------------------------------------------------------------------------

def test_mots_par_jour_couvre_toute_la_periode(historique):
    """Les journees creuses restent dans la liste : les omettre tasserait
    l'histogramme et laisserait croire a une regularite inexistante."""
    historique.ajouter("un deux trois")
    serie = historique.mots_par_jour(7)

    assert len(serie) == 7
    assert serie[-1] == (date.today(), 3)
    assert all(mots == 0 for _, mots in serie[:-1])


def test_mots_par_jour_est_ordonne_du_plus_ancien_au_plus_recent(historique):
    serie = historique.mots_par_jour(5)
    jours = [jour for jour, _ in serie]
    assert jours == sorted(jours)
    assert jours[-1] == date.today()


def test_mots_par_jour_additionne_les_dictees_du_meme_jour(historique):
    historique.ajouter("un deux")
    historique.ajouter("trois quatre cinq")
    assert historique.mots_par_jour(3)[-1][1] == 5


def test_mots_par_jour_ignore_ce_qui_precede_la_periode(historique):
    ancien = datetime.now() - timedelta(days=40)
    historique.ajouter("tres vieille dictee", horodatage=ancien)
    historique.ajouter("recente")

    serie = historique.mots_par_jour(7)
    assert sum(mots for _, mots in serie) == 1

# --------------------------------------------------------------------------
# Indicateurs de la page Statistiques
# --------------------------------------------------------------------------

def test_usage_par_application(historique):
    historique.ajouter("un deux trois", cible="brave.exe")
    historique.ajouter("quatre cinq", cible="Code.exe")
    historique.ajouter("six", cible="brave.exe")

    usage = historique.usage_par_application()
    assert usage[0] == ("brave.exe", 2, 4)
    assert ("Code.exe", 1, 2) in usage


def test_les_dictees_sans_cible_ne_disparaissent_pas(historique):
    """Les dictees anterieures a l'enregistrement de la cible portent une
    chaine vide : les ecarter ferait mentir les pourcentages."""
    historique.ajouter("un deux", cible="")
    historique.ajouter("trois", cible="brave.exe")

    applications = {nom for nom, _, _ in historique.usage_par_application()}
    assert "inconnue" in applications
    assert "" not in applications


def test_usage_par_application_est_ordonne_par_volume(historique):
    historique.ajouter("un", cible="petit.exe")
    historique.ajouter("un deux trois quatre", cible="gros.exe")
    assert [nom for nom, _, _ in historique.usage_par_application()] ==         ["gros.exe", "petit.exe"]


def test_usage_par_application_respecte_la_limite(historique):
    for i in range(8):
        historique.ajouter("mot", cible=f"app{i}.exe")
    assert len(historique.usage_par_application(limite=3)) == 3


def test_total_corrections(historique):
    assert historique.total_corrections() == 0
    historique.ajouter_correction("cloudeflare", "Cloudflare")
    historique.ajouter_correction("vulcan", "Vulkan")
    assert historique.total_corrections() == 2


def test_mots_du_mois(historique):
    historique.ajouter("un deux trois")
    assert historique.mots_du_mois() == 3


def test_mots_du_mois_precedent(historique):
    """Decoupage calendaire et non glissant : « ce mois-ci » se compare a « le
    mois dernier », pas a une fenetre de trente jours."""
    premier = date.today().replace(day=1)
    veille = datetime.combine(premier - timedelta(days=1), datetime.min.time())
    historique.ajouter("un deux", horodatage=veille)
    historique.ajouter("trois")

    assert historique.mots_du_mois() == 1
    assert historique.mots_du_mois(1) == 2


def test_mots_du_mois_ignore_les_mois_lointains(historique):
    vieux = datetime.now() - timedelta(days=200)
    historique.ajouter("tres vieille dictee", horodatage=vieux)
    assert historique.mots_du_mois() == 0
    assert historique.mots_du_mois(1) == 0


def test_deux_dictees_de_la_meme_seconde_gardent_leur_ordre(historique):
    """L'horodatage est enregistre a la seconde : sans l'identifiant pour les
    departager, SQLite rendait les deux dans l'ordre qu'il voulait — souvent
    la plus ancienne en premier."""
    instant = datetime.now().replace(microsecond=0)
    premier = historique.ajouter("la premiere", horodatage=instant)
    second = historique.ajouter("la seconde", horodatage=instant)

    recentes = historique.recentes(limite=2)
    assert [d.identifiant for d in recentes] == [second, premier]
    assert recentes[0].texte == "la seconde"


def test_la_recherche_range_aussi_la_plus_recente_en_tete(historique):
    instant = datetime.now().replace(microsecond=0)
    historique.ajouter("terme cherche, premiere", horodatage=instant)
    second = historique.ajouter("terme cherche, seconde", horodatage=instant)

    assert historique.chercher("terme cherche")[0].identifiant == second

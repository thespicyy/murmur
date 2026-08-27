"""Noms lisibles et pictogrammes des applications ou l'on dicte."""

import pytest

from murmur import applications, icones


# --------------------------------------------------------------------------
# Noms
# --------------------------------------------------------------------------

@pytest.mark.parametrize("executable, attendu", [
    ("brave.exe", "Brave"),
    ("Brave.exe", "Brave"),
    ("msedge.exe", "Edge"),
    ("Code.exe", "VS Code"),
    ("powerpnt.exe", "PowerPoint"),
    ("explorer.exe", "Explorer"),
])
def test_noms_connus(executable, attendu):
    assert applications.nom(executable) == attendu


def test_un_programme_inconnu_garde_son_nom():
    """Mieux vaut « Obsidian » approximatif que « inconnu », qui perdrait
    l'information."""
    assert applications.nom("obsidian.exe") == "Obsidian"


def test_le_chemin_complet_est_ignore():
    assert applications.nom(r"C:\Program Files\Brave\brave.exe") == "Brave"


def test_lextension_disparait():
    """« .exe » n'apprend rien a personne."""
    assert ".exe" not in applications.nom("trucbidule.exe")


def test_une_cible_absente_a_un_nom():
    """Seul texte traduit de ce module : les noms de programmes s'ecrivent
    pareil dans toutes les langues."""
    assert applications.nom("", "en") == "Other"
    assert applications.nom("inconnue", "fr") == "Autre"


# --------------------------------------------------------------------------
# Pictogrammes
# --------------------------------------------------------------------------

def test_les_navigateurs_partagent_leur_pictogramme():
    navigateurs = {applications.pictogramme(nom) for nom in
                   ("chrome.exe", "brave.exe", "firefox.exe", "msedge.exe")}
    assert len(navigateurs) == 1


def test_les_usages_se_distinguent():
    """Deux familles differentes ne doivent pas se confondre a l'oeil."""
    usages = [applications.pictogramme(nom) for nom in
              ("brave.exe", "Code.exe", "Discord.exe", "olk.exe",
               "explorer.exe")]
    assert len(set(usages)) == len(usages)


def test_un_programme_inconnu_reste_aligne():
    """Une case vide desalignerait la colonne des libelles."""
    assert applications.pictogramme("trucbidule.exe") == applications.NEUTRE
    assert applications.pictogramme("") == applications.NEUTRE


def test_lia_prime_sur_le_navigateur():
    """L'ordre des familles compte : Claude est une application d'IA avant
    d'etre autre chose."""
    assert applications.pictogramme("claude.exe") != \
        applications.pictogramme("brave.exe")


def test_chaque_famille_a_son_trace():
    """Un nom sans trace correspondant laisserait une case vide a l'ecran."""
    for nom_trace, _marqueurs in applications.USAGES:
        assert nom_trace in icones.TRACES, nom_trace
    assert applications.NEUTRE in icones.TRACES


def test_les_pictogrammes_sont_au_trait():
    """Ni emoji ni couleur : l'interface n'en compte aucune autre."""
    for nom_trace, _marqueurs in applications.USAGES:
        image = icones.rendre(nom_trace, "#312d37", 18)
        assert image.size == (18, 18)
        assert image.mode == "RGBA"


def test_un_pictogramme_nest_jamais_vide():
    """Un trace mal transcrit donnerait un carre transparent, invisible mais
    occupant sa place."""
    for nom_trace, _marqueurs in applications.USAGES:
        image = icones.rendre(nom_trace, "#312d37", 18)
        opaques = sum(1 for _x in range(18) for _y in range(18)
                      if image.getpixel((_x, _y))[3] > 40)
        assert opaques > 12, nom_trace

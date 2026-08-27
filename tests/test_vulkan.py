"""Choix de la carte graphique, sur une machine qu'on ne connait pas.

Le moteur est compile pour Vulkan, une interface commune a tous les
fabricants : le meme binaire tourne sur AMD, Nvidia ou Intel. Ce qui ne se
transporte pas, c'est le NUMERO de la carte — et c'est ce qui etait fige dans
la configuration.
"""

from pathlib import Path

import pytest

from murmur import vulkan

RACINE_PROJET = Path(__file__).resolve().parents[1]

# Releve reel sur le poste de developpement, les deux ordres observes a
# quelques minutes d'intervalle. C'est cet ecart qui a motive le module.
ENUMERATION_A = """
ggml_vulkan: Found 2 Vulkan devices:
ggml_vulkan: 0 = AMD Radeon RX 9070 XT (AMD proprietary driver) | uma: 0 | fp16: 1 | bf16: 1 | fp4: 0 | warp size: 64 | shared memory: 32768 | int dot: 1 | matrix cores: KHR_coopmat
ggml_vulkan: 1 = AMD Radeon(TM) Graphics (AMD proprietary driver) | uma: 1 | fp16: 1 | bf16: 0 | fp4: 0 | warp size: 32 | shared memory: 32768 | int dot: 1 | matrix cores: none
"""

ENUMERATION_B = """
ggml_vulkan: Found 2 Vulkan devices:
ggml_vulkan: 0 = AMD Radeon(TM) Graphics (AMD proprietary driver) | uma: 1 | fp16: 1 | bf16: 0 | fp4: 0 | warp size: 32 | shared memory: 32768 | int dot: 1 | matrix cores: none
ggml_vulkan: 1 = AMD Radeon RX 9070 XT (AMD proprietary driver) | uma: 0 | fp16: 1 | bf16: 1 | fp4: 0 | warp size: 64 | shared memory: 32768 | int dot: 1 | matrix cores: KHR_coopmat
"""

# Une machine Nvidia : le meme binaire, un autre fabricant.
ENUMERATION_NVIDIA = """
ggml_vulkan: Found 2 Vulkan devices:
ggml_vulkan: 0 = Intel(R) UHD Graphics 630 (Intel open-source Mesa driver) | uma: 1 | fp16: 1 | bf16: 0 | warp size: 32 | shared memory: 32768 | int dot: 0 | matrix cores: none
ggml_vulkan: 1 = NVIDIA GeForce RTX 4070 (NVIDIA) | uma: 0 | fp16: 1 | bf16: 1 | warp size: 32 | shared memory: 49152 | int dot: 1 | matrix cores: NV_coopmat2
"""


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------

def test_les_peripheriques_sont_lus():
    cartes = vulkan.analyser(ENUMERATION_A)

    assert [c.nom for c in cartes] == [
        "AMD Radeon RX 9070 XT (AMD proprietary driver)",
        "AMD Radeon(TM) Graphics (AMD proprietary driver)"]
    assert not cartes[0].integre and cartes[0].matriciel
    assert cartes[1].integre and not cartes[1].matriciel


def test_une_machine_sans_vulkan_ne_rend_rien():
    """Aucune carte : l'appelant retombera sur le processeur."""
    assert vulkan.analyser("whisper-server : usage ...") == []


# --------------------------------------------------------------------------
# Choix
# --------------------------------------------------------------------------

def test_le_numero_zero_ne_veut_rien_dire():
    """Le defaut corrige : l'ordre d'enumeration n'est pas stable.

    Les deux relevés ci-dessus viennent de la MEME machine et du MEME binaire,
    a quelques minutes d'intervalle. Prendre le numero zero revenait a tirer au
    sort entre la carte dediee et le circuit integre au processeur.
    """
    a = vulkan.choisir(vulkan.analyser(ENUMERATION_A))
    b = vulkan.choisir(vulkan.analyser(ENUMERATION_B))

    assert a.nom == b.nom, "le choix depend encore de l'ordre"
    assert "9070 XT" in a.nom
    assert (a.numero, b.numero) == (0, 1), "les deux ordres sont bien couverts"


def test_une_carte_dediee_est_preferee_quel_que_soit_le_fabricant():
    """Vulkan est commun a tous : le meme binaire voit une Nvidia comme une
    AMD, et le meme critere s'y applique."""
    retenue = vulkan.choisir(vulkan.analyser(ENUMERATION_NVIDIA))

    assert "RTX 4070" in retenue.nom
    assert retenue.numero == 1


def test_sans_carte_dediee_on_prend_ce_qu_il_y_a():
    """Un portable sans carte dediee doit quand meme choisir quelque chose."""
    seul = """
ggml_vulkan: 0 = Intel(R) Iris(R) Xe Graphics (Intel) | uma: 1 | fp16: 1 | matrix cores: none
"""
    retenue = vulkan.choisir(vulkan.analyser(seul))

    assert retenue is not None and retenue.numero == 0


def test_le_calcul_matriciel_departage_deux_cartes_dediees():
    deux = """
ggml_vulkan: 0 = Vieille carte (X) | uma: 0 | fp16: 1 | matrix cores: none
ggml_vulkan: 1 = Carte recente (X) | uma: 0 | fp16: 1 | matrix cores: KHR_coopmat
"""
    assert vulkan.choisir(vulkan.analyser(deux)).numero == 1


# --------------------------------------------------------------------------
# Memoire du choix
# --------------------------------------------------------------------------

def test_la_carte_est_retrouvee_par_son_nom():
    """C'est le nom qui est retenu d'une session a l'autre : un numero ne veut
    rien dire une fois l'ordre change."""
    nom = "AMD Radeon RX 9070 XT (AMD proprietary driver)"

    dans_a = vulkan.retrouver(vulkan.analyser(ENUMERATION_A), nom)
    dans_b = vulkan.retrouver(vulkan.analyser(ENUMERATION_B), nom)

    assert (dans_a.numero, dans_b.numero) == (0, 1)


def test_une_carte_disparue_ne_bloque_rien():
    """Carte changee, pilote remplace : le choix est simplement refait."""
    absente = vulkan.retrouver(vulkan.analyser(ENUMERATION_A), "Carte vendue")

    assert absente is None


# --------------------------------------------------------------------------
# Sur cette machine
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_l_enumeration_reelle_repond():
    """Le moteur lui-meme sait lister ses peripheriques, en un quart de
    seconde — assez peu pour le demander a chaque demarrage."""
    serveur = RACINE_PROJET / "engine" / "whisper-server.exe"
    if not serveur.exists():
        pytest.skip("moteur absent de ce poste")

    cartes = vulkan.enumerer(serveur)

    assert cartes, "aucune carte Vulkan vue sur ce poste"
    assert vulkan.choisir(cartes) is not None

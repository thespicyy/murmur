"""Canal de commande entre le tableau de bord et l'application.

Deux processus qui se parlent sur la boucle locale : les tests montent un
vrai serveur sur un port libre et lui parlent avec le vrai client. Simuler la
prise ne prouverait rien de ce qui casse en pratique — une trame coupee, une
commande inconnue, une application absente.
"""

import json
import socket
import threading
import time

import pytest

from murmur import canal


@pytest.fixture
def prise():
    """Prise d'ecoute sur un port libre, comme celle du verrou d'instance."""
    p = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    p.bind(("127.0.0.1", 0))
    p.listen(1)
    yield p
    p.close()


@pytest.fixture
def serveur(prise):
    recu = []

    def noter(arguments):
        recu.append(arguments)
        return {"vu": True}

    s = canal.Serveur(prise, {"essai": noter, "vide": lambda _a: None})
    s.demarrer()
    s.recu = recu
    s.port = prise.getsockname()[1]
    yield s
    s.arreter()
    prise.close()
    # Laisse le fil sortir de son `accept` avant la fin du test : le
    # garde-fou du projet echoue si un fil survit.
    time.sleep(0.15)


# --------------------------------------------------------------------------
# Aller-retour
# --------------------------------------------------------------------------

def test_une_commande_atteint_son_rappel(serveur):
    reponse = canal.envoyer("essai", {"terme": "Vulkan"}, port=serveur.port)

    assert reponse["ok"] is True
    assert reponse["resultat"] == {"vu": True}
    assert serveur.recu == [{"terme": "Vulkan"}]


def test_une_commande_sans_arguments(serveur):
    assert canal.envoyer("essai", port=serveur.port)["ok"] is True
    assert serveur.recu == [{}]


def test_un_rappel_muet_repond_quand_meme(serveur):
    """Le tableau attend une reponse : sans elle, il patiente jusqu'au delai."""
    reponse = canal.envoyer("vide", port=serveur.port)
    assert reponse["ok"] is True
    assert reponse["resultat"] is None


def test_plusieurs_commandes_de_suite(serveur):
    for numero in range(4):
        canal.envoyer("essai", {"n": numero}, port=serveur.port)
    assert [a["n"] for a in serveur.recu] == [0, 1, 2, 3]


# --------------------------------------------------------------------------
# Ce qui tourne mal
# --------------------------------------------------------------------------

def test_une_commande_inconnue_est_refusee_sans_bruit(serveur):
    reponse = canal.envoyer("nexiste_pas", port=serveur.port)
    assert reponse["ok"] is False
    assert reponse["erreur"] == "inconnue"


def test_une_trame_illisible_ne_tue_pas_le_serveur(serveur):
    with socket.create_connection(("127.0.0.1", serveur.port)) as p:
        p.sendall(b"ceci n'est pas du JSON\n")
        p.recv(canal.TAILLE_MAX)

    # Le serveur doit continuer a servir apres l'incident.
    assert canal.envoyer("essai", port=serveur.port)["ok"] is True


def test_un_rappel_qui_leve_ne_tue_pas_le_serveur(prise):
    """Une erreur dans l'application ne doit pas emporter le canal avec elle."""
    def exploser(_arguments):
        raise RuntimeError("panne")

    s = canal.Serveur(prise, {"boum": exploser, "ok": lambda _a: "vivant"})
    s.demarrer()
    port = prise.getsockname()[1]
    try:
        canal.envoyer("boum", port=port)
        assert canal.envoyer("ok", port=port)["resultat"] == "vivant"
    finally:
        s.arreter()
        prise.close()
        time.sleep(0.15)


def test_une_application_absente_ne_leve_pas():
    """Le tableau peut survivre a l'application : on le signale, on ne
    l'interrompt pas."""
    libre = socket.socket()
    libre.bind(("127.0.0.1", 0))
    port = libre.getsockname()[1]
    libre.close()

    reponse = canal.envoyer("essai", port=port)
    assert reponse["ok"] is False
    assert "erreur" in reponse


def test_une_trame_demesuree_est_ecartee(serveur):
    """Le canal n'echange que des ordres courts."""
    with socket.create_connection(("127.0.0.1", serveur.port)) as p:
        p.sendall(b"{" + b"x" * (canal.TAILLE_MAX * 2) + b"}")
        try:
            p.recv(canal.TAILLE_MAX)
        except OSError:
            pass

    assert canal.envoyer("essai", port=serveur.port)["ok"] is True


# --------------------------------------------------------------------------
# Cycle de vie
# --------------------------------------------------------------------------

def test_le_fil_du_canal_est_un_demon(serveur):
    """Il ne doit jamais retenir l'application a l'arret."""
    fils = [f for f in threading.enumerate() if f.name == "canal"]
    assert fils and all(f.daemon for f in fils)


def test_demarrer_deux_fois_ne_cree_quun_fil(serveur):
    serveur.demarrer()
    assert len([f for f in threading.enumerate() if f.name == "canal"]) == 1


# --------------------------------------------------------------------------
# Le canal se greffe sur le verrou d'instance
# --------------------------------------------------------------------------
#
# Ce n'est pas un detail d'implementation : c'est ce qui garantit que le canal
# existe exactement quand l'application tourne. Un second port aurait pu rester
# ouvert apres son arret, ou manquer alors qu'elle est bien la.

def test_le_verrou_prete_sa_prise_au_canal():
    from murmur import systeme
    verrou = systeme.InstanceUnique(port=8699)
    assert verrou.prise is None, "une prise avant d'avoir pris le verrou"
    verrou.prendre()
    try:
        assert verrou.prise is not None
        recu = []
        serveur = canal.Serveur(verrou.prise, {"ping": recu.append})
        serveur.demarrer()
        assert canal.envoyer("ping", {}, port=8699)["ok"]
        assert recu == [{}]
    finally:
        verrou.liberer()


def test_la_configuration_se_relit_sur_place(donnees):
    """Sur place, et non en rendant un nouvel objet : la configuration est
    deja detenue par l'application, le theme, l'indicateur et l'icone. En
    remplacer un seul les laisserait tous les autres sur l'ancienne valeur."""
    from murmur import config as configuration
    tenue = configuration.charger()

    # Ce que fait le tableau de bord, dans son propre processus.
    autre = configuration.charger()
    autre.definir("raccourcis.maintien", "ctrl+alt+z")
    autre.sauvegarder()

    assert tenue["raccourcis.maintien"] != "ctrl+alt+z"
    tenue.recharger()
    assert tenue["raccourcis.maintien"] == "ctrl+alt+z"


# --------------------------------------------------------------------------
# Le prix d'une absence
# --------------------------------------------------------------------------
#
# Frapper a une porte fermee sur la boucle locale n'est pas refuse ici : les
# paquets sont avales — sans doute par le pare-feu — et la connexion EXPIRE.
# Chaque ouverture du tableau de bord commencait donc par le delai complet,
# deux secondes, pour constater une absence.

def test_le_delai_de_connexion_est_bien_plus_court_que_celui_de_reponse():
    """Deux questions differentes : « y a-t-il quelqu'un » se tranche en
    quelques millisecondes sur la boucle locale — six, mesurees —, tandis que
    « voici ta reponse » peut attendre une application occupee a transcrire."""
    assert canal.DELAI_CONNEXION < canal.DELAI / 4


def test_une_absence_se_constate_vite():
    """Le constat ne doit pas couter le delai de reponse."""
    libre = 8711
    debut = time.monotonic()
    reponse = canal.envoyer("montrer", {}, port=libre)
    ecoule = time.monotonic() - debut

    assert not reponse["ok"]
    assert ecoule < canal.DELAI, \
        f"{ecoule:.2f} s pour constater une absence, contre {canal.DELAI} s " \
        f"de delai de reponse : le mauvais delai est applique"


def test_une_reponse_lente_a_tout_de_meme_le_temps_d_arriver(prise):
    """Le delai de connexion, court, ne doit pas amputer celui de la reponse."""
    lent = canal.Serveur(prise, {"lent": lambda _a: time.sleep(
        canal.DELAI_CONNEXION * 2) or "arrive"})
    lent.demarrer()
    port = prise.getsockname()[1]

    reponse = canal.envoyer("lent", {}, port=port)
    assert reponse["ok"] and reponse["resultat"] == "arrive"

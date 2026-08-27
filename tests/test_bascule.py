"""La bascule vers le tableau de bord WebView2.

L'application n'a plus de fenetre principale : le tableau de bord vit dans son
propre processus, lance a la demande. Ce fichier verifie les trois coutures que
cela cree, et qu'aucun autre test ne couvre.

  - l'aiguillage du point d'entree : le meme executable ouvre l'application ou
    le tableau, selon l'argument ;
  - le lancement : un seul tableau a la fois, et celui qui tourne deja se
    montre au lieu qu'un double s'ouvre ;
  - les commandes venues du tableau : un reglage ou un terme modifie doit etre
    repris a l'instant, non au prochain lancement.

La fenetre WebView2 elle-meme n'est jamais ouverte ici : ce sont les decisions
qui la precedent qu'on eprouve.
"""

import sys

import pytest

from pathlib import Path

from murmur import canal, systeme, tableau
from murmur import lancement as point_entree

RACINE_PROJET = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def dossier(donnees):
    return donnees


@pytest.fixture(autouse=True)
def sans_tableau_retenu():
    """Chaque test part sans tableau connu, et n'en laisse pas derriere lui."""
    tableau._processus = None
    yield
    tableau._processus = None


# --------------------------------------------------------------------------
# Aiguillage du point d'entree
# --------------------------------------------------------------------------

def test_sans_argument_c_est_l_application_qui_demarre(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["murmur"])
    assert "--tableau" not in sys.argv


def test_la_page_demandee_suit_l_indicateur(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["murmur", "--tableau", "reglages"])
    assert point_entree._page_demandee() == "reglages"


def test_sans_page_on_ouvre_celle_par_defaut(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["murmur", "--tableau"])
    assert point_entree._page_demandee() == tableau.PAGE_PAR_DEFAUT


def test_un_autre_indicateur_n_est_pas_pris_pour_une_page(monkeypatch):
    """« --tableau --console » ne demande pas une page nommee « --console »."""
    monkeypatch.setattr(sys, "argv", ["murmur", "--tableau", "--console"])
    assert point_entree._page_demandee() == tableau.PAGE_PAR_DEFAUT


# --------------------------------------------------------------------------
# Commande de lancement
# --------------------------------------------------------------------------

def test_depuis_les_sources_on_vise_python_sans_console(monkeypatch):
    """`python.exe` ferait clignoter une console noire a chaque ouverture."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    commande = tableau.commande("dictees")
    assert commande[1:] == ["-m", "murmur", "--tableau", "dictees"]
    assert commande[0].endswith(("pythonw.exe", "python.exe"))


def test_empaquete_l_executable_est_murmur_lui_meme(monkeypatch, tmp_path):
    """Il n'y a pas d'autre programme a viser : l'exe porte les deux roles."""
    faux = tmp_path / "Murmur.exe"
    faux.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(faux))

    assert tableau.commande("reglages") == [str(faux), "--tableau", "reglages"]


def test_une_page_inconnue_retombe_sur_celle_par_defaut(monkeypatch):
    lances = []
    monkeypatch.setattr(canal, "envoyer", lambda *_a, **_k: {"ok": False})
    monkeypatch.setattr(tableau.subprocess, "Popen",
                        lambda commande, **_: lances.append(commande))

    tableau.ouvrir("page.qui.nexiste.pas")
    assert lances[0][-1] == tableau.PAGE_PAR_DEFAUT


def test_le_tableau_et_l_application_n_ont_pas_le_meme_verrou():
    """Un port commun ferait croire l'un present quand c'est l'autre."""
    assert systeme.PORT_TABLEAU != systeme.PORT_VERROU


# --------------------------------------------------------------------------
# Un seul tableau a la fois
# --------------------------------------------------------------------------

class _Processus:
    """Un `Popen` reduit a ce qui nous interesse : vit-il encore ?"""

    def __init__(self, vivant=True):
        self._vivant = vivant

    def poll(self):
        return None if self._vivant else 0



def test_un_tableau_deja_ouvert_est_ramene_au_lieu_d_etre_double(monkeypatch):
    """Deux clics sur l'icone ne doivent pas donner deux fenetres."""
    # Un tableau lance par nous et vivant : c'est la seule situation ou l'on
    # interroge le reseau, et donc celle qu'il faut poser pour l'eprouver.
    monkeypatch.setattr(tableau, "_processus", _Processus(vivant=True))
    demandes = []
    monkeypatch.setattr(canal, "envoyer",
                        lambda commande, args, port=None:
                        demandes.append((commande, args, port))
                        or {"ok": True})
    lances = []
    monkeypatch.setattr(tableau.subprocess, "Popen",
                        lambda *a, **k: lances.append(a))

    assert tableau.ouvrir("dictees")
    assert demandes == [("montrer", {"page": "dictees"},
                         systeme.PORT_TABLEAU)]
    assert lances == [], "un second tableau a ete lance"


def test_sans_tableau_ouvert_le_processus_est_lance(monkeypatch):
    monkeypatch.setattr(canal, "envoyer", lambda *_a, **_k: {"ok": False})
    lances = []
    monkeypatch.setattr(tableau.subprocess, "Popen",
                        lambda commande, **_: lances.append(commande))

    assert tableau.ouvrir("statistiques")
    assert lances and lances[0][-2:] == ["--tableau", "statistiques"]


def test_un_lancement_impossible_est_signale_sans_lever(monkeypatch):
    """L'icone pres de l'horloge ne doit pas tomber parce qu'un processus n'a
    pas pu demarrer."""
    monkeypatch.setattr(canal, "envoyer", lambda *_a, **_k: {"ok": False})

    def refuser(*_a, **_k):
        raise OSError("executable introuvable")

    monkeypatch.setattr(tableau.subprocess, "Popen", refuser)
    assert tableau.ouvrir("dictees") is False


def test_le_lancement_n_attend_pas_la_fenetre(monkeypatch):
    """WebView2 met une seconde a ouvrir : l'icone ne doit pas rester figee.

    On verifie qu'aucune attente n'est demandee au processus lance — ni
    `wait`, ni `communicate`, ni redirection a lire.
    """
    monkeypatch.setattr(canal, "envoyer", lambda *_a, **_k: {"ok": False})
    options = {}
    monkeypatch.setattr(tableau.subprocess, "Popen",
                        lambda _commande, **kw: options.update(kw))

    tableau.ouvrir()
    assert "stdout" not in options and "stderr" not in options
    assert options.get("creationflags") == tableau._SANS_CONSOLE


# --------------------------------------------------------------------------
# Ce que le tableau demande a l'application
# --------------------------------------------------------------------------

class _Application:
    def __init__(self):
        self.raccourcis_recharges = 0
        self.lexique_recharge = 0

    def recharger_raccourcis(self):
        self.raccourcis_recharges += 1

    def recharger_lexique(self):
        self.lexique_recharge += 1


class _Murmur:
    """Le strict necessaire : les rappels ne touchent a rien d'autre.

    La file de commandes est reprise telle quelle : c'est elle qu'on eprouve,
    puisque les rappels arrivent sur le fil du canal et n'ont pas le droit de
    toucher a Tk.
    """

    def __init__(self, conf, theme):
        self.conf = conf
        self.theme = theme
        self.application = _Application()
        self.log = __import__("logging").getLogger("essai")
        self._commandes = __import__("queue").Queue()

    @property
    def differes(self):
        """Les actions en attente, dans leur ordre de depot."""
        rendus = []
        while not self._commandes.empty():
            rendus.append(self._commandes.get_nowait())
        return rendus

    _demander = point_entree.Murmur._demander
    _sur_reglages_modifies = point_entree.Murmur._sur_reglages_modifies
    _reprendre_les_reglages = point_entree.Murmur._reprendre_les_reglages
    _sur_lexique_modifie = point_entree.Murmur._sur_lexique_modifie


@pytest.fixture
def murmur():
    from murmur import config as configuration, theme as module_theme
    conf = configuration.charger()
    return _Murmur(conf, module_theme.Theme(conf))


def test_un_reglage_modifie_est_repris_sans_redemarrer(murmur):
    """Le tableau ecrit le fichier ; l'application le relit et reprend ses
    raccourcis. Sans cela, un raccourci change n'aurait effet qu'au prochain
    lancement — alors que la page annonce le contraire."""
    from murmur import config as configuration
    autre = configuration.charger()
    autre.definir("raccourcis.maintien", "ctrl+alt+y")
    autre.sauvegarder()

    assert murmur._sur_reglages_modifies({}) == {"pris": True}

    # Le rappel arrive sur le fil du canal : il DEPOSE l'action dans la file
    # au lieu de la donner a Tk, seule la boucle principale ayant le droit d'y
    # toucher. Confiee a `after` depuis ce fil, la demande se perdait.
    en_attente = murmur.differes
    assert en_attente, "rien n'a ete renvoye vers le fil principal"
    for differe in en_attente:
        differe()

    assert murmur.conf["raccourcis.maintien"] == "ctrl+alt+y"
    assert murmur.application.raccourcis_recharges == 1


def test_le_lexique_modifie_est_repris(murmur):
    """Un terme ajoute change le prompt envoye au moteur."""
    assert murmur._sur_lexique_modifie({}) == {"pris": True}
    assert murmur.application.lexique_recharge == 1


def test_la_configuration_relue_reste_le_meme_objet(murmur):
    """Elle est deja detenue par le theme, l'indicateur et l'icone : en
    remplacer un seul les laisserait tous les autres sur l'ancienne valeur."""
    tenue = murmur.conf
    murmur._reprendre_les_reglages()
    assert murmur.conf is tenue


# --------------------------------------------------------------------------
# L'arret
# --------------------------------------------------------------------------
#
# « Quitter » ne quittait pas. Deux causes, cumulees, et toutes deux muettes :
# une demande d'arret adressee a Tk depuis le fil de l'icone — ou elle se
# perdait — et un tableau de bord laisse ouvert dans son propre processus,
# qui gardait une fenetre et un « Murmur.exe » apres coup.

def test_la_demande_d_arret_ne_touche_pas_tk_depuis_un_autre_fil():
    """`after` de Tk n'est pas sur entre fils : appele depuis le fil de
    l'icone, il ecrit dans les structures de l'interpreteur Tcl pendant que la
    boucle les lit. Le plus souvent la demande est simplement perdue — et
    l'application continuait de tourner, icone disparue."""
    source = (RACINE_PROJET / "murmur" / "lancement.py").read_text(
        encoding="utf-8")

    # Les seuls `after` admis sont ceux que la boucle principale se pose a
    # elle-meme : la file de commandes et le suivi du theme.
    appels = [ligne.strip() for ligne in source.splitlines()
              if "racine.after(" in ligne]
    assert appels, "plus aucun after : la file n'est plus relancee"
    for appel in appels:
        assert ("_traiter_commandes" in appel or "_suivre_theme" in appel), \
            f"appel a Tk depuis un fil inconnu : {appel}"


def test_les_reactions_d_autres_fils_passent_par_la_file():
    source = (RACINE_PROJET / "murmur" / "lancement.py").read_text(
        encoding="utf-8")
    for reaction in ("_sur_reglages_modifies", "_sur_correction", "_quitter"):
        corps = source.split(f"def {reaction}(")[1].split("\n    def ")[0]
        assert "_demander(" in corps, f"{reaction} ne passe pas par la file"


def test_l_icone_ne_se_joint_pas_elle_meme():
    """`_quitter` s'execute sur le fil de l'icone : l'y faire attendre la fin
    de ce meme fil leve une RuntimeError, perdue dans pystray."""
    source = (RACINE_PROJET / "murmur" / "tray.py").read_text(encoding="utf-8")
    corps = source.split("def _quitter(")[1].split("\n    def ")[0]
    assert "self.arreter()" not in corps
    assert "current_thread()" in source, "le garde-fou du join a disparu"


def test_quitter_ferme_aussi_le_tableau_de_bord():
    """Il vit dans un autre processus et ne meurt pas avec l'application."""
    source = (RACINE_PROJET / "murmur" / "lancement.py").read_text(
        encoding="utf-8")
    corps = source.split("    def arreter(")[1]
    assert "tableau.fermer()" in corps


def test_le_tableau_obeit_a_la_commande_de_fermeture(monkeypatch):
    envoyees = []
    monkeypatch.setattr(canal, "envoyer",
                        lambda commande, args, port=None:
                        envoyees.append((commande, port)) or {"ok": True})

    assert tableau.fermer() is True
    assert envoyees == [("fermer", systeme.PORT_TABLEAU)]


def test_un_tableau_absent_ne_gene_pas_l_arret(monkeypatch):
    """L'application doit pouvoir s'arreter sans lui."""
    monkeypatch.setattr(canal, "envoyer", lambda *_a, **_k: {"ok": False})
    assert tableau.fermer() is False


def test_le_tableau_declare_la_commande_de_fermeture():
    source = (RACINE_PROJET / "murmur" / "tableau" / "lancement.py").read_text(
        encoding="utf-8")
    assert '"fermer": fermer' in source, "le tableau n'ecoute pas « fermer »"
    assert "fenetre.destroy()" in source.split("def fermer(")[1][:400]


# --------------------------------------------------------------------------
# Ne pas demander ce qu'on sait deja
# --------------------------------------------------------------------------

def test_sans_tableau_connu_on_ne_frappe_pas(monkeypatch):
    """Frapper a une porte fermee coute un quart de seconde — les paquets sont
    avales plutot que refuses. C'est autant d'ajoute a chaque ouverture, pour
    apprendre une absence dont on est deja certain."""
    frappes = []
    monkeypatch.setattr(canal, "envoyer",
                        lambda *a, **k: frappes.append(a) or {"ok": False})
    monkeypatch.setattr(tableau.subprocess, "Popen",
                        lambda *a, **k: _Processus())

    assert tableau.ouvrir("dictees")
    assert frappes == [], "on a interroge le reseau pour rien"


def test_un_tableau_connu_vivant_est_interroge(monkeypatch):
    monkeypatch.setattr(tableau, "_processus", _Processus(vivant=True))
    frappes = []
    monkeypatch.setattr(canal, "envoyer",
                        lambda commande, args, port=None:
                        frappes.append(commande) or {"ok": True})
    lances = []
    monkeypatch.setattr(tableau.subprocess, "Popen",
                        lambda *a, **k: lances.append(a))

    assert tableau.ouvrir("dictees")
    assert frappes == ["montrer"]
    assert lances == [], "un second tableau a ete lance"


def test_un_tableau_connu_mort_est_relance(monkeypatch):
    monkeypatch.setattr(tableau, "_processus", _Processus(vivant=False))
    frappes = []
    monkeypatch.setattr(canal, "envoyer",
                        lambda *a, **k: frappes.append(a) or {"ok": False})
    lances = []
    monkeypatch.setattr(tableau.subprocess, "Popen",
                        lambda commande, **k: lances.append(commande)
                        or _Processus())

    assert tableau.ouvrir("dictees")
    assert frappes == []
    assert lances, "le tableau mort n'a pas ete relance"


def test_un_tableau_qui_repond_non_est_relance(monkeypatch):
    """Vivant mais muet — il se ferme peut-etre a l'instant. On en relance un
    plutot que de laisser le clic sans effet."""
    monkeypatch.setattr(tableau, "_processus", _Processus(vivant=True))
    monkeypatch.setattr(canal, "envoyer", lambda *a, **k: {"ok": False})
    lances = []
    monkeypatch.setattr(tableau.subprocess, "Popen",
                        lambda commande, **k: lances.append(commande)
                        or _Processus())

    assert tableau.ouvrir("dictees")
    assert lances


def test_fermer_oublie_le_tableau(monkeypatch):
    """Retenu apres sa fermeture, il ferait frapper a une porte fermee au
    prochain clic — la depense qu'on cherchait a eviter."""
    monkeypatch.setattr(tableau, "_processus", _Processus(vivant=True))
    monkeypatch.setattr(canal, "envoyer", lambda *a, **k: {"ok": True})

    assert tableau.fermer()
    assert tableau._processus is None


def test_fermer_un_tableau_deja_mort_n_interroge_personne(monkeypatch):
    monkeypatch.setattr(tableau, "_processus", _Processus(vivant=False))
    frappes = []
    monkeypatch.setattr(canal, "envoyer",
                        lambda *a, **k: frappes.append(a) or {"ok": True})

    assert tableau.fermer() is False
    assert frappes == []

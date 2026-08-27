"""Empaquetage — l'executable doit se reperer et parler.

Ces tests ne construisent pas l'executable (trop lent pour une suite) mais
verifient les deux mecanismes dont il depend : la resolution des chemins en
mode gele, et le fait qu'un echec de demarrage atteigne l'utilisateur alors
qu'aucune console n'existe.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from murmur import config as cfg


RACINE_PROJET = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Resolution des chemins
# --------------------------------------------------------------------------

def test_en_mode_source_la_racine_est_le_projet():
    assert not cfg.EMPAQUETE
    assert (cfg.RACINE / "murmur" / "config.py").exists()


def test_en_mode_gele_la_racine_suit_lexecutable(monkeypatch, tmp_path):
    """Le moteur reste a cote de l'executable, pas dans le dossier temporaire.

    PyInstaller extrait le code dans un repertoire temporaire ou les 600 Mo du
    moteur ne figurent pas : se reperer sur `__file__` y chercherait un moteur
    absent.
    """
    faux_exe = tmp_path / "Murmur.exe"
    faux_exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(faux_exe))

    assert cfg._racine() == tmp_path.resolve()


def test_le_moteur_est_cherche_a_cote_de_lexecutable(monkeypatch, tmp_path):
    faux_exe = tmp_path / "Murmur.exe"
    faux_exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(faux_exe))

    racine = cfg._racine()
    assert racine / "engine" == tmp_path.resolve() / "engine"


def test_les_donnees_utilisateur_ne_dependent_pas_du_mode(monkeypatch,
                                                          tmp_path):
    """Config, lexique et historique vivent dans %APPDATA% dans les deux cas.

    Ils doivent survivre au remplacement de l'executable.
    """
    monkeypatch.delenv(cfg.VAR_DONNEES, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    attendu = tmp_path / "Murmur"

    assert cfg.dossier_donnees() == attendu
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert cfg.dossier_donnees() == attendu


# --------------------------------------------------------------------------
# Ce que PyInstaller ne devine pas
# --------------------------------------------------------------------------
#
# Un fichier oublie ici ne se voit qu'a l'execution de l'executable construit,
# et se manifeste par une fenetre blanche ou une icone absente — jamais par une
# erreur explicite. Le fichier de construction est donc relu.

#: C'est le script de construction qui fait foi, non le fichier `.spec` :
#: celui-ci est REGENERE a chaque construction et perdrait toute retouche.
CONSTRUCTION = RACINE_PROJET / "outils" / "construire.py"


@pytest.fixture(scope="module")
def spec() -> str:
    return CONSTRUCTION.read_text(encoding="utf-8")


def test_la_page_du_tableau_de_bord_est_embarquee(spec):
    """HTML, CSS et JavaScript : PyInstaller n'analyse que les imports Python
    et ne les verrait pas. Sans eux, la fenetre s'ouvre sur du blanc."""
    assert "murmur/tableau/web" in spec


def test_la_destination_reprend_le_chemin_du_paquet(spec):
    """Le module cherche ses fichiers a cote de lui, par `__file__`. Les poser
    ailleurs dans le dossier d'extraction les rendrait introuvables."""
    assert "murmur/tableau/web" in spec.split("--add-data")[1][:120]


def test_tous_les_fichiers_de_la_page_sont_couverts():
    """Ils sont embarques par leur dossier : un fichier neuf y entre de
    lui-meme. On verifie qu'aucun n'a ete range ailleurs entre-temps."""
    web = RACINE_PROJET / "murmur" / "tableau" / "web"
    fichiers = {f.name for f in web.iterdir() if f.is_file()}
    assert {"index.html", "style.css", "app.js", "pictos.js"} <= fichiers


@pytest.mark.parametrize("greffon", [
    "pystray._win32",              # sans lui, l'icone disparait en silence
    "murmur.tableau.lancement",    # lance par « --tableau », jamais importe
    "webview.platforms.winforms",  # choisi a l'execution selon le systeme
])
def test_les_greffons_charges_par_leur_nom_sont_declares(spec, greffon):
    """Aucun `import` litteral ne les designe : PyInstaller ne peut pas les
    trouver seul, et leur absence ne se signale pas."""
    assert greffon in spec


def test_le_moteur_nest_pas_embarque(spec):
    """Ses 600 Mo restent a cote de l'executable, remplacables sans
    reconstruction : PyInstaller les reextrairait a chaque lancement."""
    assert "--add-data" in spec
    embarques = [bloc.split('"')[1] for bloc in spec.split('"--add-data",')[1:]]
    assert not any("engine" in chemin for chemin in embarques), embarques


# --------------------------------------------------------------------------
# Signalement des erreurs sans console
# --------------------------------------------------------------------------

def test_signaler_ecrit_toujours_sur_la_sortie_derreur(capsys, monkeypatch):
    from murmur import lancement as point_entree

    monkeypatch.setattr(cfg, "EMPAQUETE", False)
    point_entree.signaler("Panne", "quelque chose a casse")
    assert "quelque chose a casse" in capsys.readouterr().err


def test_signaler_ouvre_une_boite_si_empaquete(monkeypatch):
    """Sans console, un echec de demarrage se traduirait par « rien ne se passe »."""
    from murmur import lancement as point_entree

    vus = []
    monkeypatch.setattr(cfg, "EMPAQUETE", True)

    faux_tk = type("FauxTk", (), {
        "withdraw": lambda self: None, "destroy": lambda self: None})
    module_tk = type(sys)("tkinter")
    module_tk.Tk = lambda: faux_tk()
    module_boite = type(sys)("tkinter.messagebox")
    module_boite.showerror = lambda titre, message: vus.append((titre, message))
    module_tk.messagebox = module_boite
    monkeypatch.setitem(sys.modules, "tkinter", module_tk)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", module_boite)

    point_entree.signaler("Panne", "moteur introuvable")

    assert vus, "aucune boite affichee alors qu'aucune console n'existe"
    assert "moteur introuvable" in vus[0][1]


def test_signaler_ne_leve_jamais(monkeypatch):
    """Echouer a signaler une panne ne doit pas en provoquer une seconde."""
    from murmur import lancement as point_entree

    monkeypatch.setattr(cfg, "EMPAQUETE", True)
    monkeypatch.setitem(sys.modules, "tkinter", None)
    point_entree.signaler("Panne", "message")


# --------------------------------------------------------------------------
# Sorties standard absentes
# --------------------------------------------------------------------------

def test_les_sorties_absentes_sont_remplacees(monkeypatch):
    """Sans console, PyInstaller met stdout et stderr a None.

    Le moindre `print` leve alors une AttributeError — y compris celui charge
    de rapporter l'erreur, ce qui transforme un message clair en
    « Unhandled exception in script ».
    """
    from murmur import lancement as point_entree

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    point_entree.assurer_les_sorties()

    assert sys.stdout is not None
    assert sys.stderr is not None
    print("ceci ne doit pas lever")
    print("ni ceci", file=sys.stderr)


def test_les_sorties_existantes_ne_sont_pas_remplacees(capsys):
    from murmur import lancement as point_entree

    avant_out, avant_err = sys.stdout, sys.stderr
    point_entree.assurer_les_sorties()
    assert sys.stdout is avant_out
    assert sys.stderr is avant_err


def test_signaler_fonctionne_sans_sorties(monkeypatch):
    """Le cas exact rencontre : signaler plantait avant d'avoir rien affiche."""
    from murmur import lancement as point_entree

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(cfg, "EMPAQUETE", False)
    point_entree.signaler("Panne", "message sans console")   # ne doit pas lever


def test_la_sortie_muette_se_comporte_comme_un_flux():
    from murmur import lancement as point_entree

    muette = point_entree._SortieMuette()
    assert muette.write("texte") == 0
    muette.flush()
    assert muette.isatty() is False


# --------------------------------------------------------------------------
# Script de construction
# --------------------------------------------------------------------------

def test_le_script_de_construction_est_syntaxiquement_valide():
    script = RACINE_PROJET / "outils" / "construire.py"
    assert script.exists()
    compile(script.read_text(encoding="utf-8"), str(script), "exec")


def test_licone_couvre_les_tailles_attendues_par_windows():
    import importlib.util

    chemin = RACINE_PROJET / "outils" / "construire.py"
    spec = importlib.util.spec_from_file_location("construire", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert 16 in module.TAILLES_ICONE, "barre des taches"
    assert 256 in module.TAILLES_ICONE, "ecrans haute densite"
    assert module.TAILLES_ICONE == sorted(module.TAILLES_ICONE)


@pytest.mark.materiel
def test_licone_se_genere_reellement(tmp_path, monkeypatch):
    import importlib.util
    from PIL import Image

    chemin = RACINE_PROJET / "outils" / "construire.py"
    spec = importlib.util.spec_from_file_location("construire_icone", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ICONE", tmp_path / "essai.ico")

    produite = module.generer_icone()
    assert produite.exists()
    with Image.open(produite) as image:
        assert image.size[0] >= 256, "la plus grande taille doit etre presente"


# --------------------------------------------------------------------------
# Demarrage automatique
# --------------------------------------------------------------------------

def test_la_commande_de_demarrage_vise_linterpreteur_depuis_les_sources():
    from murmur import systeme

    commande = systeme.commande_de_lancement()
    assert commande.endswith("-m murmur")
    assert "python" in commande.lower()


def test_la_commande_de_demarrage_vise_lexe_une_fois_empaquete(monkeypatch):
    """`sys.executable` est alors l'application elle-meme : lui passer
    « -m murmur » reviendrait a lui donner un argument inconnu."""
    from murmur import systeme

    monkeypatch.setattr(systeme.sys, "frozen", True, raising=False)
    chemin = "D:" + chr(92) + "Murmur" + chr(92) + "Murmur.exe"
    monkeypatch.setattr(systeme.sys, "executable", chemin)

    commande = systeme.commande_de_lancement()
    assert commande == f'"{chemin}"'
    assert "-m murmur" not in commande


def test_la_commande_de_demarrage_est_toujours_entre_guillemets():
    """Un chemin contenant une espace serait sinon coupe en deux arguments."""
    from murmur import systeme

    assert systeme.commande_de_lancement().startswith('"')


def test_l_executable_nest_pas_un_fichier_unique(spec):
    """Un exécutable « un seul fichier » réextrait tout son contenu dans un
    dossier temporaire **a chaque lancement**.

    Le tableau de bord etant un second exemplaire du meme executable, il paie
    cette extraction une seconde fois. Mesure du clic a la fenetre repondante,
    sur trois tours : 2 200 a 2 370 ms en fichier unique, dont 1 400 a 1 560
    avant que Python ne demarre ; 1 130 a 1 760 ms en dossier, dont 310 a 450
    avant Python — soit la vitesse d'un lancement depuis les sources.
    """
    assert "--onefile" not in spec, "l'extraction coute une seconde par ouverture"
    assert "--onedir" in spec


def test_le_moteur_est_detache_avant_l_effacement(spec):
    """`rmtree` sur un dossier contenant une jonction pourrait la suivre et
    emporter les 600 Mo qu'elle designe, hors du dossier de construction."""
    debut = spec.index("def construire(")
    corps = spec[debut:spec.index("def rattacher_moteur(")]
    # Les commentaires sont ecartes : ils parlent des deux appels, et dans
    # l'ordre inverse de celui du code. C'est l'ordre du CODE qu'on verifie.
    code = "\n".join(ligne for ligne in corps.splitlines()
                     if not ligne.strip().startswith("#"))
    assert code.index("rmdir") < code.index("rmtree"), \
        "le moteur est encore rattache quand le dossier est efface"

"""T1.1 — configuration et resolution des chemins."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from murmur import config as cfg

RACINE = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# La regle du projet : aucun chemin absolu
# --------------------------------------------------------------------------

# Motifs revelateurs d'un chemin code en dur. On cherche une lettre de lecteur
# suivie d'un separateur, ou une racine POSIX d'utilisateur.
CHEMINS_ABSOLUS = re.compile(
    r"""(?x)
    (["'])              # ouverture de chaine
    (?:
        [A-Za-z]:[\\/]  # C:\ ou C:/
      | /(?:Users|home|mnt|opt)/
    )
    """,
)


def _sources():
    return sorted((RACINE / "murmur").rglob("*.py"))


def test_le_paquet_contient_des_sources():
    """Garde-fou : un test qui ne lit aucun fichier passerait a tort."""
    assert _sources(), "aucun fichier source trouve dans murmur/"


@pytest.mark.parametrize("source", _sources(), ids=lambda p: p.name)
def test_aucun_chemin_absolu_code_en_dur(source):
    """Regle 9 : le projet doit survivre a un changement de disque.

    Ce test echoue volontairement bruyamment : un chemin absolu introduit un
    jour dans le code rendrait l'application non portable sans qu'aucun autre
    test ne s'en apercoive.
    """
    contenu = source.read_text(encoding="utf-8")
    fautifs = []
    for numero, ligne in enumerate(contenu.splitlines(), 1):
        if CHEMINS_ABSOLUS.search(ligne):
            fautifs.append(f"    {source.name}:{numero}  {ligne.strip()}")
    assert not fautifs, "chemin(s) absolu(s) detecte(s) :\n" + "\n".join(fautifs)


# --------------------------------------------------------------------------
# Resolution des chemins
# --------------------------------------------------------------------------

def test_racine_pointe_sur_le_projet():
    assert (cfg.RACINE / "murmur" / "config.py").exists()
    assert cfg.MOTEUR == cfg.RACINE / "engine"


def test_chemins_independants_du_repertoire_courant(tmp_path, monkeypatch):
    """Le critere de fin de T1.1 : les chemins tiennent depuis n'importe ou."""
    avant = cfg.RACINE, cfg.MOTEUR
    monkeypatch.chdir(tmp_path)
    assert (cfg.RACINE, cfg.MOTEUR) == avant
    assert cfg.RACINE.is_absolute()


def test_resolution_depuis_un_autre_repertoire_dans_un_processus_neuf(tmp_path):
    """Verification reelle : un processus lance ailleurs resout les memes chemins.

    Le test precedent reutilise un module deja importe ; celui-ci repart de
    zero, ce qui est le seul moyen de prouver que l'import lui-meme ne depend
    pas du repertoire courant.
    """
    code = (
        "import sys, json;"
        f"sys.path.insert(0, {str(RACINE)!r});"
        "from murmur import config;"
        "print(json.dumps({'racine': str(config.RACINE),"
        " 'moteur': str(config.MOTEUR)}))"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=tmp_path,
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    obtenu = json.loads(proc.stdout)
    assert Path(obtenu["racine"]) == cfg.RACINE
    assert Path(obtenu["moteur"]) == cfg.MOTEUR


def test_dossier_donnees_redirige_et_cree(donnees):
    resolu = cfg.dossier_donnees()
    assert resolu == donnees
    assert resolu.is_dir(), "le dossier de donnees doit etre cree a la demande"


def test_dossier_journaux_cree(donnees):
    assert cfg.dossier_journaux().is_dir()


def test_sans_surcharge_les_donnees_vont_dans_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv(cfg.VAR_DONNEES, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert cfg.dossier_donnees() == tmp_path / "Murmur"


# --------------------------------------------------------------------------
# Chargement, defauts, validation
# --------------------------------------------------------------------------

def test_config_absente_est_creee_avec_les_defauts(donnees):
    assert not cfg.fichier_config().exists()
    conf = cfg.charger()
    assert cfg.fichier_config().exists()
    assert conf["langue"] == "fr"
    assert conf["moteur.port"] == 8642


def test_cle_manquante_reprend_le_defaut(donnees):
    """Ajouter une option plus tard ne doit pas casser les config existantes."""
    cfg.fichier_config().write_text(
        json.dumps({"langue": "en"}), encoding="utf-8")
    conf = cfg.charger()
    assert conf["langue"] == "en"                    # respecte le fichier
    assert conf["moteur.port"] == 8642               # complete par le defaut
    assert conf["injection.strategie"] == "presse_papier"


def test_fusion_recursive_preserve_les_voisins(donnees):
    cfg.fichier_config().write_text(
        json.dumps({"moteur": {"port": 9000}}), encoding="utf-8")
    conf = cfg.charger()
    assert conf["moteur.port"] == 9000
    assert conf["moteur.hote"] == "127.0.0.1"


def test_json_invalide_donne_une_erreur_explicite(donnees):
    cfg.fichier_config().write_text("{ ceci n'est pas du json", encoding="utf-8")
    with pytest.raises(cfg.ErreurConfig) as info:
        cfg.charger()
    message = str(info.value)
    assert "illisible" in message
    assert "supprime-le" in message, "l'erreur doit dire quoi faire"


@pytest.mark.parametrize("reglages, attendu", [
    ({"moteur": {"port": 0}}, "moteur.port"),
    ({"moteur": {"port": "8642"}}, "moteur.port"),
    ({"langue": "de"}, "langue"),
    ({"injection": {"strategie": "magie"}}, "injection.strategie"),
    ({"vad": {"seuil": 1.5}}, "vad.seuil"),
    ({"garde": {"duree_min_ms": -1}}, "garde.duree_min_ms"),
    ({"garde": {"liste_noire": "non"}}, "garde.liste_noire"),
])
def test_valeurs_invalides_sont_refusees(donnees, reglages, attendu):
    cfg.fichier_config().write_text(json.dumps(reglages), encoding="utf-8")
    with pytest.raises(cfg.ErreurConfig) as info:
        cfg.charger()
    assert attendu in str(info.value)


def test_config_par_defaut_est_valide(donnees):
    """Les defauts doivent passer leur propre validation."""
    cfg._valider(cfg.DEFAUTS)


# --------------------------------------------------------------------------
# Acces aux reglages
# --------------------------------------------------------------------------

def test_acces_par_chemin_pointe(donnees):
    conf = cfg.charger()
    assert conf["moteur.hote"] == "127.0.0.1"
    assert conf["vad.actif"] is True
    with pytest.raises(KeyError):
        conf["moteur.inexistant"]


def test_get_avec_defaut(donnees):
    conf = cfg.charger()
    assert conf.get("rien.du.tout", "repli") == "repli"


def test_definir_puis_sauvegarder_et_recharger(donnees):
    conf = cfg.charger()
    conf.definir("moteur.port", 9999)
    conf.sauvegarder()
    assert cfg.charger()["moteur.port"] == 9999


def test_valeurs_retourne_une_copie(donnees):
    """Modifier la copie ne doit pas alterer la configuration vivante."""
    conf = cfg.charger()
    copie = conf.valeurs
    copie["langue"] = "en"
    assert conf["langue"] == "fr"


def test_chemins_derives(donnees):
    conf = cfg.charger()
    assert conf.chemin_modele.parent == cfg.MOTEUR
    assert conf.chemin_modele.name.endswith(".bin")
    assert conf.chemin_serveur.name == "whisper-server.exe"
    assert conf.url_moteur == "http://127.0.0.1:8642"


def test_liste_noire_vide_par_defaut(donnees):
    """Pre-remplir cette liste censurerait des phrases legitimes (cf. T0.3)."""
    assert cfg.charger()["garde.liste_noire"] == []


# --------------------------------------------------------------------------
# Reprise du choix de carte graphique
# --------------------------------------------------------------------------

def test_l_ancien_numero_par_defaut_redevient_automatique(donnees):
    """`device_vulkan: 0` n'etait pas un choix, c'etait un defaut.

    Et ce zero designe une carte differente d'un demarrage a l'autre : le
    laisser en place garderait le tirage au sort qu'on vient de supprimer.
    """
    fichier = cfg.fichier_config()
    fichier.write_text(json.dumps({"moteur": {"device_vulkan": 0}}),
                       encoding="utf-8")

    config = cfg.charger()

    assert config["moteur.device_vulkan"] == "auto"


def test_un_numero_pose_a_la_main_est_respecte(donnees):
    """Qui a choisi sa carte explicitement doit la garder."""
    fichier = cfg.fichier_config()
    fichier.write_text(json.dumps({"moteur": {"device_vulkan": 2}}),
                       encoding="utf-8")

    assert cfg.charger()["moteur.device_vulkan"] == 2


def test_une_carte_deja_retenue_n_est_pas_reprise(donnees):
    """Si une carte a ete retenue par son nom, le zero qui l'accompagne a ete
    resolu : il n'y a plus rien a reprendre."""
    fichier = cfg.fichier_config()
    fichier.write_text(json.dumps({"moteur": {
        "device_vulkan": 0, "carte_vulkan": "Une carte"}}), encoding="utf-8")

    assert cfg.charger()["moteur.device_vulkan"] == 0

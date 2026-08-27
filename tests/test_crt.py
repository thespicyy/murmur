"""La bibliotheque C++ que le moteur reclame.

Trois fichiers que Visual Studio pose sur la machine qui compile, et que
Windows ne fournit pas. Rien ne les distingue, chez soi, d'une dependance du
systeme : c'est tout le probleme.
"""

from pathlib import Path

import pytest

from murmur import crt

RACINE_PROJET = Path(__file__).resolve().parents[1]


def test_rien_n_est_devine():
    """La liste ne doit pas etre ecrite a la main.

    Le premier essai sur machine vierge a bute sur `MSVCP140.dll`. Corrige, le
    deuxieme a bute sur `VCOMP140.DLL` — absente de la premiere liste, qui
    avait ete etablie en cherchant des noms plausibles. Une liste devinee se
    corrige a raison d'un demarrage par oubli.

    La regle appliquee ici ne devine rien : est a fournir ce que le moteur
    importe ET que Visual Studio range parmi ses redistribuables.
    """
    moteur = RACINE_PROJET / "engine"
    if not moteur.is_dir() or not crt.catalogue():
        pytest.skip("moteur ou Visual Studio absent de ce poste")

    calculee = set(crt.necessaires(moteur))
    assert "msvcp140.dll" in calculee
    assert "vcomp140.dll" in calculee, "la bibliotheque OpenMP a ete oubliee"


def test_la_chaine_des_dependances_est_suivie(tmp_path, monkeypatch):
    """Une bibliotheque posee peut en reclamer une autre.

    S'arreter au premier tour repousserait le probleme d'un cran : le moteur
    demarrerait, et tomberait sur la dependance de la dependance.
    """
    poses = []

    def catalogue_double():
        return {"a.dll": tmp_path / "_a", "b.dll": tmp_path / "_b"}

    def reclamees_double(_dossier):
        # `b` n'apparait qu'une fois `a` sur place : c'est tout le point.
        return {"a.dll", "b.dll"} if (tmp_path / "a.dll").exists() else {"a.dll"}

    (tmp_path / "_a").write_bytes(b"a")
    (tmp_path / "_b").write_bytes(b"b")
    monkeypatch.setattr(crt, "catalogue", catalogue_double)
    monkeypatch.setattr(crt, "reclamees", reclamees_double)

    poses = crt.fournir(tmp_path)

    assert poses == ["a.dll", "b.dll"], "la deuxieme n'a pas ete suivie"


def test_le_manifeste_permet_de_verifier_sans_visual_studio(tmp_path):
    """Sur la machine de l'utilisateur, le catalogue n'existe pas : seul le
    manifeste dit ce qui aurait du etre livre."""
    crt.ecrire_manifeste(tmp_path, ["msvcp140.dll", "vcomp140.dll"])

    declarees = crt.lire_manifeste(tmp_path)
    assert declarees == ("msvcp140.dll", "vcomp140.dll")
    assert crt.manquants(tmp_path, declarees) == list(declarees)

    (tmp_path / "msvcp140.dll").write_bytes(b"x")
    assert crt.manquants(tmp_path, declarees) == ["vcomp140.dll"]


def test_le_moteur_livre_emporte_la_bibliotheque():
    """Sans elle, l'application demarre et ne transcrit jamais.

    Mesure sur machine vierge : Windows ouvre « Impossible d'executer le code,
    car MSVCP140.dll est introuvable », le moteur ne demarre pas, et
    l'application echoue trente secondes plus tard sur « le serveur n'a pas
    repondu » — un message exact et sans rapport avec la cause.
    """
    moteur = RACINE_PROJET / "engine"
    if not moteur.is_dir():
        pytest.skip("moteur absent de ce poste")

    assert not crt.manquants(moteur), (
        "le dossier du moteur ne peut pas etre distribue tel quel : "
        f"{crt.manquants(moteur)} manque(nt). Relance construire.py.")


def test_fournir_ne_reecrit_pas_ce_qui_est_deja_la(tmp_path, monkeypatch):
    """Sur un poste de developpement, les fichiers en place peuvent etre plus
    recents que le redistribuable installe."""
    monkeypatch.setattr(crt, "catalogue", lambda: {"x.dll": tmp_path / "_x"})
    monkeypatch.setattr(crt, "reclamees", lambda _d: {"x.dll"})
    (tmp_path / "_x").write_bytes(b"neuf")
    (tmp_path / "x.dll").write_bytes(b"deja la")

    assert crt.fournir(tmp_path) == []
    assert (tmp_path / "x.dll").read_bytes() == b"deja la"


def test_l_absence_de_catalogue_est_dite_clairement(tmp_path, monkeypatch):
    """Construire sans Visual Studio doit expliquer quoi installer, pas
    echouer sur un chemin introuvable."""
    monkeypatch.setattr(crt, "catalogue", dict)
    monkeypatch.setattr(crt, "necessaires", lambda _d: ["msvcp140.dll"])

    with pytest.raises(FileNotFoundError) as erreur:
        crt.fournir(tmp_path)

    assert "Visual Studio" in str(erreur.value)
    assert "msvcp140.dll" in str(erreur.value)

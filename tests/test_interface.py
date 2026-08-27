"""T3.1, T3.2, T3.4, T3.6 — theme, indicateur, icone, integration systeme."""

import socket

import pytest

from murmur import config as cfg
from murmur import systeme, theme as module_theme, tray
from murmur.app import Etat


@pytest.fixture
def conf(donnees):
    return cfg.charger()


# --------------------------------------------------------------------------
# Theme
# --------------------------------------------------------------------------

def test_les_deux_palettes_definissent_les_memes_jetons():
    """Un jeton manquant d'un cote laisserait un trou visuel apres bascule."""
    clair = {c for c in vars(module_theme.CLAIR) if not c.startswith("_")}
    sombre = {c for c in vars(module_theme.SOMBRE) if not c.startswith("_")}
    assert clair == sombre


def test_les_palettes_sont_reellement_contrastees():
    """Garde-fou contre une palette sombre copiee de la claire par erreur."""
    assert module_theme.SOMBRE.fond != module_theme.CLAIR.fond
    assert module_theme.SOMBRE.texte != module_theme.CLAIR.texte


def test_les_couleurs_detat_sont_communes_aux_deux_themes():
    """Un vert qui change de teinte selon le fond se reconnait moins vite."""
    for etat in ("ecoute", "transcription", "insertion", "erreur"):
        assert getattr(module_theme.SOMBRE, etat) == \
            getattr(module_theme.CLAIR, etat)


def test_toutes_les_couleurs_sont_des_codes_hexadecimaux():
    for palette in (module_theme.CLAIR, module_theme.SOMBRE):
        for nom, valeur in vars(palette).items():
            if nom == "nom":
                continue
            assert isinstance(valeur, str) and valeur.startswith("#"), nom
            assert len(valeur) == 7, f"{nom} = {valeur}"


@pytest.mark.parametrize("preference, attendu", [
    ("clair", "clair"),
    ("sombre", "sombre"),
])
def test_une_preference_explicite_ignore_le_systeme(preference, attendu):
    assert module_theme.resoudre(preference).nom == attendu


def test_le_mode_auto_suit_windows(monkeypatch):
    monkeypatch.setattr(module_theme, "windows_en_clair", lambda: True)
    assert module_theme.resoudre("auto").nom == "clair"
    monkeypatch.setattr(module_theme, "windows_en_clair", lambda: False)
    assert module_theme.resoudre("auto").nom == "sombre"


def test_un_registre_illisible_retombe_sur_le_clair(monkeypatch):
    """Le clair est le defaut de Windows, et reste lisible en cas d'erreur."""
    monkeypatch.setattr(module_theme.winreg, "OpenKey",
                        lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert module_theme.windows_en_clair() is True


def test_rafraichir_signale_le_changement(conf, monkeypatch):
    monkeypatch.setattr(module_theme, "windows_en_clair", lambda: True)
    theme = module_theme.Theme(conf)
    assert theme.palette.nom == "clair"

    assert theme.rafraichir() is False, "aucun changement ne doit etre signale"

    monkeypatch.setattr(module_theme, "windows_en_clair", lambda: False)
    assert theme.rafraichir() is True
    assert theme.palette.nom == "sombre"


def test_acces_direct_aux_jetons(conf):
    theme = module_theme.Theme(conf)
    assert theme.fond == theme.palette.fond
    with pytest.raises(AttributeError, match="jeton de theme inconnu"):
        theme.couleur_imaginaire


def test_un_attribut_prive_absent_ne_boucle_pas(conf):
    """Sans garde, __getattr__ se rappellerait jusqu'au debordement de pile."""
    theme = module_theme.Theme(conf)
    with pytest.raises(AttributeError):
        theme._inexistant


# --------------------------------------------------------------------------
# Icone
# --------------------------------------------------------------------------

def test_licone_se_dessine_pour_chaque_etat():
    for couleur in ("#3fb950", "#d29922", "#4493f8", "#8a8a94"):
        image = tray.dessiner_icone(couleur, "#ffffff")
        assert image.size == (tray.TAILLE, tray.TAILLE)
        assert image.mode == "RGBA"


def test_licone_en_pause_differe_de_licone_au_repos():
    """L'etat suspendu doit se distinguer du repos, sinon on croit l'app active."""
    repos = tray.dessiner_icone("#8a8a94", "#ffffff", en_pause=False)
    pause = tray.dessiner_icone("#8a8a94", "#ffffff", en_pause=True)
    assert repos.tobytes() != pause.tobytes()


def test_chaque_etat_a_son_libelle():
    for etat in Etat:
        assert etat in tray.LIBELLES
        assert tray.LIBELLES[etat]


def test_licone_expose_letat_sans_pystray(conf, monkeypatch):
    """changer_etat doit rester sur avant que l'icone soit demarree."""
    theme = module_theme.Theme(conf)
    icone = tray.Icone(conf, theme, sur_pause=lambda a: None,
                       sur_quitter=lambda: None)
    icone.changer_etat(Etat.ECOUTE)   # aucune icone vivante : ne doit rien casser
    assert icone._etat is Etat.ECOUTE


def test_la_pause_appelle_le_rappel(conf):
    theme = module_theme.Theme(conf)
    recu = []
    icone = tray.Icone(conf, theme, sur_pause=recu.append,
                       sur_quitter=lambda: None)

    icone._basculer_pause()
    assert recu == [False], "suspendre doit desactiver la dictee"
    icone._basculer_pause()
    assert recu == [False, True]


def test_un_rappel_de_pause_defaillant_ne_casse_pas_licone(conf):
    theme = module_theme.Theme(conf)
    icone = tray.Icone(conf, theme,
                       sur_pause=lambda a: (_ for _ in ()).throw(
                           RuntimeError("casse")),
                       sur_quitter=lambda: None)
    icone._basculer_pause()          # ne doit pas lever
    assert icone._en_pause is True


# --------------------------------------------------------------------------
# Instance unique
# --------------------------------------------------------------------------

def test_le_verrou_se_prend_et_se_libere():
    verrou = systeme.InstanceUnique(port=8891)
    verrou.prendre()
    assert verrou.detenu
    verrou.liberer()
    assert not verrou.detenu

    # Reprenable une fois libere.
    with systeme.InstanceUnique(port=8891):
        pass


def test_un_second_lancement_est_refuse():
    """Critere de fin de T3.6 : deux instances ne doivent pas coexister."""
    with systeme.InstanceUnique(port=8892):
        with pytest.raises(systeme.DejaLance, match="deja lance"):
            systeme.InstanceUnique(port=8892).prendre()


def test_le_message_oriente_vers_licone():
    """Un refus sans explication laisserait croire a un plantage."""
    with systeme.InstanceUnique(port=8893):
        with pytest.raises(systeme.DejaLance) as info:
            systeme.InstanceUnique(port=8893).prendre()
        assert "horloge" in str(info.value)


def test_est_libre_repond_juste():
    verrou = systeme.InstanceUnique(port=8895)
    assert verrou.est_libre(), "aucune instance sur ce port"

    with systeme.InstanceUnique(port=8895):
        assert not systeme.InstanceUnique(port=8895).est_libre()

    assert verrou.est_libre(), "le verrou aurait du etre relache"


def test_est_libre_ne_conserve_pas_le_verrou():
    """Sonder ne doit pas bloquer : le verrou est relache aussitot."""
    verrou = systeme.InstanceUnique(port=8896)
    verrou.est_libre()
    assert not verrou.detenu
    with systeme.InstanceUnique(port=8896):
        pass   # doit rester prenable


def test_le_verrou_utilise_un_port_distinct_du_moteur(conf):
    """Confondre les deux rendrait un conflit incomprehensible."""
    assert systeme.PORT_VERROU != conf["moteur.port"]


def test_le_verrou_est_libere_a_la_mort_du_processus():
    """Un verrou par fichier survivrait a un plantage et bloquerait tout."""
    prise = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    prise.bind(("127.0.0.1", 8894))
    prise.listen(1)
    prise.close()   # equivaut a la disparition du processus
    with systeme.InstanceUnique(port=8894):
        pass


# --------------------------------------------------------------------------
# Demarrage automatique
# --------------------------------------------------------------------------

def test_la_commande_de_lancement_vise_le_bon_module():
    commande = systeme.commande_de_lancement()
    assert "-m murmur" in commande
    assert commande.startswith('"')


def test_la_commande_evite_la_console_si_possible():
    """Sans pythonw, une console noire s'ouvrirait a chaque demarrage."""
    commande = systeme.commande_de_lancement()
    import sys
    from pathlib import Path
    if Path(sys.executable).with_name("pythonw.exe").exists():
        assert "pythonw.exe" in commande


def test_la_commande_ne_contient_aucun_chemin_fige():
    """Deplacer le projet et reactiver doit suffire a corriger l'entree."""
    import sys
    assert str(sys.prefix) in systeme.commande_de_lancement()


# --------------------------------------------------------------------------
# Raccourci du menu Demarrer
# --------------------------------------------------------------------------

def test_le_raccourci_vise_le_menu_de_lutilisateur(monkeypatch, tmp_path):
    """Pas celui de la machine : y ecrire demanderait des droits admin."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    dossier = systeme.dossier_menu_demarrer()
    assert dossier == tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    assert systeme.chemin_raccourci().name == "Murmur.lnk"


def test_une_cible_absente_est_refusee(tmp_path):
    """Un raccourci vers rien laisserait un lanceur mort dans le menu."""
    with pytest.raises(FileNotFoundError):
        systeme.creer_raccourci(tmp_path / "inexistant.exe")


@pytest.mark.materiel
def test_creer_puis_supprimer_le_raccourci(tmp_path, monkeypatch):
    """Ecrit dans un faux menu Demarrer, jamais dans le vrai."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cible = tmp_path / "Murmur.exe"
    cible.write_bytes(b"MZ")   # suffit : on ne l'execute pas

    lien = systeme.creer_raccourci(cible)
    assert lien.exists()
    assert lien.suffix == ".lnk"
    assert lien.stat().st_size > 0, "raccourci vide"
    assert systeme.raccourci_existe()

    assert systeme.supprimer_raccourci()
    assert not systeme.raccourci_existe()
    assert not systeme.supprimer_raccourci(), "deuxieme suppression"


@pytest.mark.materiel
def test_le_raccourci_pointe_bien_sur_la_cible(tmp_path, monkeypatch):
    """Verification par relecture : un .lnk mal forme s'ouvrirait sur rien."""
    import subprocess

    monkeypatch.setenv("APPDATA", str(tmp_path))
    cible = tmp_path / "Murmur.exe"
    cible.write_bytes(b"MZ")
    lien = systeme.creer_raccourci(cible)

    lecture = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"$s = New-Object -ComObject WScript.Shell;"
         f"$s.CreateShortcut('{lien}').TargetPath"],
        capture_output=True, text=True)
    assert str(cible) in lecture.stdout.strip()
    systeme.supprimer_raccourci()


@pytest.mark.materiel
def test_activer_puis_desactiver_le_demarrage_auto():
    """Touche au registre de l'utilisateur : restaure l'etat initial."""
    etat_initial = systeme.demarrage_auto_actif()
    try:
        systeme.activer_demarrage_auto()
        assert systeme.demarrage_auto_actif()
        systeme.desactiver_demarrage_auto()
        assert not systeme.demarrage_auto_actif()
        # Desactiver deux fois ne doit pas lever.
        systeme.desactiver_demarrage_auto()
    finally:
        systeme.definir_demarrage_auto(etat_initial)
    assert systeme.demarrage_auto_actif() == etat_initial

"""T1.4 — raccourcis globaux.

L'analyse des combinaisons se teste entierement hors materiel. L'enregistrement
reel aupres de Windows est teste aussi : il ne demande aucune frappe humaine,
seulement que le systeme accepte ou refuse la reservation.
"""

import threading
import time

import pytest

from murmur import hotkeys


# --------------------------------------------------------------------------
# Analyse des combinaisons
# --------------------------------------------------------------------------

def test_combinaison_simple():
    mods, code = hotkeys.analyser("ctrl+alt+d")
    assert mods & hotkeys.MOD_CONTROL
    assert mods & hotkeys.MOD_ALT
    assert not mods & hotkeys.MOD_SHIFT
    assert code == ord("D")


def test_combinaison_avec_shift():
    mods, code = hotkeys.analyser("ctrl+alt+shift+d")
    assert mods & hotkeys.MOD_SHIFT
    assert code == ord("D")


def test_norepeat_est_toujours_pose():
    """Sans MOD_NOREPEAT, maintenir la touche declenche WM_HOTKEY en rafale."""
    for combinaison in ("ctrl+alt+d", "ctrl+f1", "alt+espace"):
        mods, _ = hotkeys.analyser(combinaison)
        assert mods & hotkeys.MOD_NOREPEAT, combinaison


def test_insensible_a_la_casse_et_aux_espaces():
    assert hotkeys.analyser("Ctrl + Alt + D") == hotkeys.analyser("ctrl+alt+d")


def test_synonymes_francais_et_anglais():
    assert hotkeys.analyser("ctrl+maj+a") == hotkeys.analyser("control+shift+a")


@pytest.mark.parametrize("combinaison, code", [
    ("ctrl+espace", 0x20),
    ("ctrl+alt+f5", 0x74),
    ("alt+suppr", 0x2E),
    ("ctrl+alt+haut", 0x26),
    ("ctrl+7", ord("7")),
])
def test_touches_nommees_et_alphanumeriques(combinaison, code):
    assert hotkeys.analyser(combinaison)[1] == code


def test_raccourci_sans_modificateur_est_refuse():
    """Reserver « d » seul volerait la touche dans toute application."""
    with pytest.raises(hotkeys.ErreurRaccourci, match="aucun modificateur"):
        hotkeys.analyser("d")


def test_modificateur_inconnu_est_signale_avec_les_valeurs_attendues():
    with pytest.raises(hotkeys.ErreurRaccourci) as info:
        hotkeys.analyser("hyper+d")
    message = str(info.value)
    assert "hyper" in message
    assert "ctrl" in message, "l'erreur doit lister ce qui est accepte"


def test_touche_inconnue_est_signalee():
    with pytest.raises(hotkeys.ErreurRaccourci, match="touche inconnue"):
        hotkeys.analyser("ctrl+alt+pizza")


def test_combinaison_vide_est_refusee():
    with pytest.raises(hotkeys.ErreurRaccourci, match="vide"):
        hotkeys.analyser("")


# --------------------------------------------------------------------------
# Declaration
# --------------------------------------------------------------------------

def test_maintien_sans_rappel_de_fin_est_refuse():
    """Un maintien sans rappel de fin ne detecterait jamais le relachement."""
    gestionnaire = hotkeys.Gestionnaire()
    with pytest.raises(hotkeys.ErreurRaccourci, match="rappel de fin"):
        gestionnaire.ajouter("dictee", "ctrl+alt+d", debut=lambda: None,
                             maintien=True)


def test_demarrer_sans_raccourci_est_refuse():
    with pytest.raises(hotkeys.ErreurRaccourci, match="aucun raccourci"):
        hotkeys.Gestionnaire().demarrer()


def test_ajouter_apres_demarrage_est_refuse():
    gestionnaire = hotkeys.Gestionnaire()
    gestionnaire.ajouter("a", "ctrl+alt+f13", debut=lambda: None)
    try:
        gestionnaire.demarrer()
        with pytest.raises(hotkeys.ErreurRaccourci, match="avant demarrer"):
            gestionnaire.ajouter("b", "ctrl+alt+f14", debut=lambda: None)
    finally:
        gestionnaire.arreter()


def test_combinaison_invalide_echoue_des_la_declaration():
    """Mieux vaut echouer a la declaration qu'au demarrage."""
    gestionnaire = hotkeys.Gestionnaire()
    with pytest.raises(hotkeys.ErreurRaccourci):
        gestionnaire.ajouter("mauvais", "ctrl+alt+pizza", debut=lambda: None)


# --------------------------------------------------------------------------
# Enregistrement reel aupres de Windows
# --------------------------------------------------------------------------

# F13 a F20 n'existent pas sur un clavier courant : on peut les reserver sans
# risquer de percuter un raccourci utilise, ni d'etre declenche par megarde.
LIBRE_1 = "ctrl+alt+shift+f13"
LIBRE_2 = "ctrl+alt+shift+f14"


@pytest.mark.materiel
def test_enregistrement_et_liberation():
    gestionnaire = hotkeys.Gestionnaire()
    gestionnaire.ajouter("essai", LIBRE_1, debut=lambda: None)
    gestionnaire.demarrer()
    assert gestionnaire.en_cours
    gestionnaire.arreter()
    assert not gestionnaire.en_cours

    # Le raccourci doit avoir ete rendu : un second gestionnaire le reprend.
    second = hotkeys.Gestionnaire()
    second.ajouter("essai", LIBRE_1, debut=lambda: None)
    second.demarrer()
    second.arreter()


@pytest.mark.materiel
def test_raccourci_deja_pris_leve_une_erreur_explicite():
    """Critere de fin de T1.4 : un conflit doit etre signale, pas subi."""
    premier = hotkeys.Gestionnaire()
    premier.ajouter("premier", LIBRE_2, debut=lambda: None)
    premier.demarrer()
    try:
        second = hotkeys.Gestionnaire()
        second.ajouter("second", LIBRE_2, debut=lambda: None)
        with pytest.raises(hotkeys.ErreurRaccourci) as info:
            second.demarrer()
        message = str(info.value)
        assert LIBRE_2 in message
        assert "second" in message, "l'erreur doit nommer le raccourci fautif"
        assert "deja pris" in message, "l'erreur doit expliquer la cause"
    finally:
        premier.arreter()


@pytest.mark.materiel
def test_un_conflit_ne_laisse_aucun_raccourci_a_moitie_enregistre():
    """Si le second raccourci echoue, le premier doit etre rendu.

    Sans ce retour arriere, une combinaison resterait reservee par un
    gestionnaire mort, et deviendrait impossible a reprendre.
    """
    occupant = hotkeys.Gestionnaire()
    occupant.ajouter("occupant", LIBRE_2, debut=lambda: None)
    occupant.demarrer()
    try:
        casse = hotkeys.Gestionnaire()
        casse.ajouter("libre", LIBRE_1, debut=lambda: None)   # celui-ci passe
        casse.ajouter("conflit", LIBRE_2, debut=lambda: None)  # celui-ci echoue
        with pytest.raises(hotkeys.ErreurRaccourci):
            casse.demarrer()
    finally:
        occupant.arreter()

    # LIBRE_1 doit etre reutilisable : il a ete rendu lors du retour arriere.
    verif = hotkeys.Gestionnaire()
    verif.ajouter("verif", LIBRE_1, debut=lambda: None)
    verif.demarrer()
    verif.arreter()


@pytest.mark.materiel
def test_le_maintien_declenche_debut_puis_fin():
    """Le critere central de T1.4, sans frappe humaine.

    On ne peut pas simuler un WM_HOTKEY credible depuis l'exterieur, mais on
    peut verifier la mecanique interne : `_traiter` doit appeler le debut,
    puis la fin des que la touche n'est plus enfoncee. Comme aucune touche
    n'est physiquement pressee, le relachement est immediat.
    """
    evenements = []
    fini = threading.Event()

    gestionnaire = hotkeys.Gestionnaire()
    gestionnaire.ajouter(
        "dictee", LIBRE_1, maintien=True,
        debut=lambda: evenements.append("debut"),
        fin=lambda: (evenements.append("fin"), fini.set()),
    )
    identifiant = next(iter(gestionnaire._raccourcis))

    gestionnaire._traiter(identifiant)
    assert fini.wait(2.0), "le relachement n'a jamais ete signale"
    assert evenements == ["debut", "fin"]


@pytest.mark.materiel
def test_une_repetition_pendant_le_maintien_est_ignoree():
    """Deux appuis rapproches ne doivent pas ouvrir deux dictees."""
    debuts = []
    gestionnaire = hotkeys.Gestionnaire()
    gestionnaire.ajouter(
        "dictee", LIBRE_1, maintien=True,
        debut=lambda: debuts.append(1),
        fin=lambda: None,
    )
    identifiant = next(iter(gestionnaire._raccourcis))
    raccourci = gestionnaire._raccourcis[identifiant]

    raccourci.actif = True          # simule une dictee deja en cours
    gestionnaire._traiter(identifiant)
    assert debuts == [], "une dictee etait deja en cours"


@pytest.mark.materiel
def test_mode_bascule_appelle_seulement_le_debut():
    appels = []
    gestionnaire = hotkeys.Gestionnaire()
    gestionnaire.ajouter("bascule", LIBRE_1, maintien=False,
                         debut=lambda: appels.append("debut"))
    identifiant = next(iter(gestionnaire._raccourcis))

    gestionnaire._traiter(identifiant)
    gestionnaire._traiter(identifiant)
    assert appels == ["debut", "debut"], "chaque appui doit compter"


def test_touche_enfoncee_repond_sans_intercepter():
    """La scrutation interroge l'etat, elle n'installe aucun hook."""
    assert hotkeys.touche_enfoncee(0x88) in (True, False)


# --------------------------------------------------------------------------
# Un rappel qui tombe ne doit pas rendre l'application sourde
# --------------------------------------------------------------------------

def _poster(gestionnaire, identifiant: int) -> None:
    """Depose un WM_HOTKEY dans la file du fil, comme le ferait Windows."""
    import ctypes
    ctypes.windll.user32.PostThreadMessageW(
        gestionnaire._id_fil, hotkeys.WM_HOTKEY, identifiant, 0)


@pytest.mark.materiel
def test_un_rappel_qui_leve_ne_tue_pas_la_boucle():
    """Le defaut le plus couteux de la journee, et le plus discret.

    Une exception dans un rappel remontait jusqu'a la boucle de messages, qui
    rendait TOUS les raccourcis en sortant. L'application continuait de
    tourner — icone, tableau de bord, tout marchait — et ne repondait plus
    jamais au clavier. Aucune trace : compilee sans console, elle n'a meme pas
    de sortie d'erreur ou deposer le traceback.
    """
    appels = []
    gestionnaire = hotkeys.Gestionnaire()
    gestionnaire.ajouter("fautif", LIBRE_1,
                         debut=lambda: (_ for _ in ()).throw(
                             RuntimeError("micro disparu")))
    gestionnaire.ajouter("sain", LIBRE_2, debut=lambda: appels.append("sain"))
    fautif, sain = list(gestionnaire._raccourcis)
    gestionnaire.demarrer()
    try:
        _poster(gestionnaire, fautif)
        _poster(gestionnaire, sain)
        for _ in range(50):
            if appels:
                break
            time.sleep(0.02)

        assert appels == ["sain"], "le second raccourci n'a pas ete traite"
        assert gestionnaire.en_cours, "la boucle est morte avec le rappel"
    finally:
        gestionnaire.arreter()


@pytest.mark.materiel
def test_la_boucle_morte_rend_bien_les_raccourcis():
    """Le corollaire : tant que la boucle vit, la combinaison reste prise.

    C'est ce qui rend la panne invisible — rien ne distingue de l'exterieur
    « personne n'ecoute » de « quelqu'un ecoute et ne fait rien ».
    """
    gestionnaire = hotkeys.Gestionnaire()
    gestionnaire.ajouter("essai", LIBRE_1, debut=lambda: None)
    gestionnaire.demarrer()

    concurrent = hotkeys.Gestionnaire()
    concurrent.ajouter("essai", LIBRE_1, debut=lambda: None)
    with pytest.raises(hotkeys.ErreurRaccourci):
        concurrent.demarrer()

    gestionnaire.arreter()
    concurrent = hotkeys.Gestionnaire()
    concurrent.ajouter("essai", LIBRE_1, debut=lambda: None)
    concurrent.demarrer()          # libere : la boucle etait bien la seule
    concurrent.arreter()

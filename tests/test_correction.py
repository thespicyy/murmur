"""Validation d'un apprentissage, en boite de dialogue.

La derniere fenetre de l'application encore dessinee par Tk, et la seule qui
doive le rester : elle apparait pendant qu'on travaille ailleurs, sur une
pression de raccourci. Lancer une douzaine de processus WebView2 pour trois
cases a cocher couterait plus cher que tout ce qu'elle affiche.

Ce qui compte ici tient en une regle : rien ne doit etre appris sans accord.
"""

import tkinter as tk

import pytest

from murmur import apprentissage, config as cfg
from murmur import correction as module_correction
from murmur import theme as module_theme


@pytest.fixture(autouse=True)
def dossier(donnees):
    return donnees


@pytest.fixture
def boite(racine_tk):
    conf = cfg.charger()
    yield module_correction.Boite(racine_tk, conf, module_theme.Theme(conf))
    # Une boite laissee ouverte fausserait le compte des fenetres du test
    # suivant, qui verifie justement qu'une boite se ferme.
    for fenetre in _fenetres(racine_tk):
        fenetre.destroy()
    racine_tk.update()


def _ouvrir(boite, racine, analyse, sur_validation=lambda *_: None):
    """Ouvre la boite et rend sa fenetre, **affichee**.

    L'affichage n'est pas un detail de confort : Tk ecarte purement et
    simplement un evenement de souris synthetise vers un widget qui n'est pas
    encore pose a l'ecran. Sans cette mise a jour, les clics du test ne
    partaient nulle part et la boite semblait ne pas repondre.
    """
    boite.montrer(analyse, sur_validation)
    fenetre = _fenetres(racine)[-1]
    fenetre.update()
    return fenetre


def _analyse(*paires) -> apprentissage.Analyse:
    substitutions = tuple(apprentissage.Substitution(avant, apres)
                          for avant, apres in paires)
    return apprentissage.Analyse(
        dictee_id=1, texte_origine="avant", texte_corrige="apres",
        similarite=0.9, substitutions=substitutions)


def _fenetres(racine) -> list:
    return [f for f in racine.winfo_children() if isinstance(f, tk.Toplevel)]


def _cases(fenetre) -> list:
    """Les cases a cocher de la boite, dans l'ordre d'affichage.

    Une case est une etiquette qui porte une image et aucun texte : elle est
    dessinee par Pillow, celle de Tk etant peinte par Windows et insensible a
    la palette.
    """
    trouvees = []

    def descendre(widget):
        for enfant in widget.winfo_children():
            if (isinstance(enfant, tk.Label) and enfant.cget("image")
                    and not enfant.cget("text")):
                trouvees.append(enfant)
            descendre(enfant)

    descendre(fenetre)
    return trouvees


def _etiquettes(widget) -> list[str]:
    textes = []

    def descendre(w):
        for enfant in w.winfo_children():
            if isinstance(enfant, tk.Label) and enfant.cget("text"):
                textes.append(enfant.cget("text"))
            descendre(enfant)

    descendre(widget)
    return textes


def _presser(fenetre, libelle: str) -> None:
    """Clique le bouton portant ce libelle."""
    def descendre(widget) -> bool:
        for enfant in widget.winfo_children():
            if isinstance(enfant, tk.Label) and enfant.cget("text") == libelle:
                enfant.event_generate("<Button-1>")
                return True
            if descendre(enfant):
                return True
        return False

    assert descendre(fenetre), f"bouton introuvable : {libelle}"


# --------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_les_substitutions_sont_affichees(boite, racine_tk):
    boite.montrer(_analyse(("web hooks", "webhook"),
                           ("olama", "Ollama")), lambda *_: None)
    fenetre = _fenetres(racine_tk)[-1]
    textes = _etiquettes(fenetre)

    assert "web hooks" in textes and "webhook" in textes
    assert "olama" in textes and "Ollama" in textes
    fenetre.destroy()


@pytest.mark.materiel
def test_la_boite_reste_au_premier_plan(boite, racine_tk):
    """Elle repond a un raccourci presse dans une autre application, qui garde
    le focus : sans cela, elle naitrait derriere elle."""
    boite.montrer(_analyse(("a", "b")), lambda *_: None)
    fenetre = _fenetres(racine_tk)[-1]
    assert fenetre.attributes("-topmost")
    fenetre.destroy()


@pytest.mark.materiel
def test_sans_substitution_aucune_boite_ne_s_ouvre(boite, racine_tk,
                                                   monkeypatch):
    """Deux textes identiques : ouvrir une boite vide serait une corvee, mais
    ne rien dire du tout laisserait croire a une panne."""
    dits = []
    monkeypatch.setattr(module_correction.messagebox, "showinfo",
                        lambda *args, **_: dits.append(args))
    avant = len(_fenetres(racine_tk))
    boite.montrer(_analyse(), lambda *_: None)

    assert len(_fenetres(racine_tk)) == avant
    assert dits, "l'utilisateur n'a rien su"


@pytest.mark.materiel
def test_sans_analyse_la_raison_est_donnee(boite, racine_tk, monkeypatch):
    """« Rien trouve » sans explication laisse sans prise."""
    dits = []
    monkeypatch.setattr(module_correction.messagebox, "showinfo",
                        lambda *args, **_: dits.append(args))
    boite.montrer(None, lambda *_: None, diagnostic="presse-papier vide")

    assert dits and "presse-papier vide" in dits[0][1]


# --------------------------------------------------------------------------
# Rien n'est appris sans accord
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_le_vocabulaire_est_coche_la_reformulation_non(boite, racine_tk):
    """Murmur propose, il ne decide pas : ce qu'il classe comme reformulation
    reste affiche, mais decoche."""
    analyse = _analyse(("olama", "Ollama"), ("du coup", "donc"))
    boite.montrer(analyse, lambda *_: None)
    fenetre = _fenetres(racine_tk)[-1]

    assert len(_cases(fenetre)) == 2
    assert analyse.substitutions[0].est_vocabulaire
    assert not analyse.substitutions[1].est_vocabulaire
    fenetre.destroy()


@pytest.mark.materiel
def test_seules_les_cases_cochees_sont_apprises(boite, racine_tk):
    analyse = _analyse(("olama", "Ollama"), ("du coup", "donc"))
    retenues = []
    fenetre = _ouvrir(boite, racine_tk, analyse,
                      lambda _a, r: retenues.extend(r))

    # On coche la reformulation : c'est l'utilisateur qui tranche.
    _cases(fenetre)[1].event_generate("<Button-1>")
    racine_tk.update()
    _presser(fenetre, boite.mot("corr.enregistrer"))

    assert [(s.avant, s.apres) for s in retenues] == [
        ("olama", "Ollama"), ("du coup", "donc")]


@pytest.mark.materiel
def test_decocher_retire_de_l_apprentissage(boite, racine_tk, monkeypatch):
    monkeypatch.setattr(boite, "_dire", lambda _m: None)
    analyse = _analyse(("olama", "Ollama"))
    retenues = []
    fenetre = _ouvrir(boite, racine_tk, analyse,
                      lambda _a, r: retenues.extend(r))

    _cases(fenetre)[0].event_generate("<Button-1>")
    racine_tk.update()
    _presser(fenetre, boite.mot("corr.enregistrer"))

    assert retenues == []


@pytest.mark.materiel
def test_enregistrer_sans_rien_cocher_le_dit(boite, racine_tk, monkeypatch):
    """Un bouton principal qui ne fait rien, sans le dire, est un piege.

    C'est arrive : aucune case n'etait cochee — Murmur avait classe la
    substitution en reformulation —, la boite s'est fermee sur « Enregistrer »,
    et le dictionnaire est reste vide. L'utilisateur a cherche ensuite ou etait
    passe son terme.
    """
    dits = []
    monkeypatch.setattr(boite, "_dire", dits.append)
    appels = []
    fenetre = _ouvrir(boite, racine_tk, _analyse(("du coup", "donc")),
                      lambda *_: appels.append(True))
    ouvertes = len(_fenetres(racine_tk))

    _presser(fenetre, boite.mot("corr.enregistrer"))
    racine_tk.update()

    assert appels == [], "rien ne devait etre appris"
    assert dits, "la boite s'est fermee sans rien dire"
    assert len(_fenetres(racine_tk)) == ouvertes,         "elle s'est fermee : la decision est perdue"


@pytest.mark.materiel
def test_ignorer_n_apprend_rien_et_ferme(boite, racine_tk):
    appels = []
    fenetre = _ouvrir(boite, racine_tk, _analyse(("olama", "Ollama")),
                      lambda *_: appels.append(True))
    avant = len(_fenetres(racine_tk))

    _presser(fenetre, boite.mot("corr.ignorer"))
    racine_tk.update()

    assert appels == []
    assert len(_fenetres(racine_tk)) == avant - 1


@pytest.mark.materiel
def test_valider_ferme_la_boite(boite, racine_tk):
    fenetre = _ouvrir(boite, racine_tk, _analyse(("olama", "Ollama")))
    avant = len(_fenetres(racine_tk))

    _presser(fenetre, boite.mot("corr.enregistrer"))
    racine_tk.update()

    assert len(_fenetres(racine_tk)) == avant - 1


# --------------------------------------------------------------------------
# Position
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_la_boite_s_ouvre_au_centre_de_l_ecran(boite, racine_tk):
    """Au centre de l'ecran, et non de la fenetre qui l'ouvre : celle-ci est
    desormais la racine invisible de Tk, un point sans dimensions en haut a
    gauche."""
    boite.montrer(_analyse(("a", "b")), lambda *_: None)
    fenetre = _fenetres(racine_tk)[-1]
    fenetre.update_idletasks()

    attendu = (fenetre.winfo_screenwidth() - module_correction.LARGEUR) // 2
    assert abs(fenetre.winfo_x() - attendu) <= 2
    fenetre.destroy()


# --------------------------------------------------------------------------
# Se faire voir
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_le_message_passe_devant_l_application(boite, racine_tk, monkeypatch):
    """Une boite sans parent nait DERRIERE la fenetre au premier plan.

    Le raccourci semble alors n'avoir rien fait : le journal montrait deux
    analyses menees a bien, et l'utilisateur n'avait rien vu passer. Windows
    refusant le premier plan a un processus qui ne l'a pas, la seule prise est
    le plan d'affichage — d'ou un parent « toujours au-dessus ».
    """
    vus = {}

    def capturer(_titre, _message, parent=None, **_):
        vus["parent"] = parent
        vus["au_dessus"] = bool(parent.attributes("-topmost")) if parent else None

    monkeypatch.setattr(module_correction.messagebox, "showinfo", capturer)
    boite._dire("un message")

    assert vus["parent"] is not None, "aucun parent : la boite passera dessous"
    assert vus["au_dessus"], "le parent n'est pas au-dessus"


@pytest.mark.materiel
def test_le_support_du_message_ne_survit_pas(boite, racine_tk, monkeypatch):
    """Une fenetre invisible laissee derriere s'accumulerait a chaque essai."""
    monkeypatch.setattr(module_correction.messagebox, "showinfo",
                        lambda *a, **k: None)
    avant = len(racine_tk.winfo_children())

    boite._dire("un message")
    racine_tk.update()

    assert len(racine_tk.winfo_children()) == avant


@pytest.mark.materiel
def test_les_deux_messages_sans_correction_passent_par_la(boite, monkeypatch):
    """Les deux chemins « rien a proposer » doivent se voir autant l'un que
    l'autre : c'est celui-la qu'on avait oublie."""
    dits = []
    monkeypatch.setattr(boite, "_dire", dits.append)

    boite.montrer(None, lambda *_: None, diagnostic="une raison")
    boite.montrer(_analyse(), lambda *_: None)

    assert len(dits) == 2

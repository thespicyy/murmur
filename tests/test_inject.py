"""T1.5 — insertion du texte.

La construction des evenements et le presse-papier se testent sans focus ni
fenetre. Seule l'insertion effective dans une application demande du materiel :
elle est verifiee contre une fenetre dont on relit le contenu exact.
"""

import threading
import time

import pytest

from murmur import config as cfg
from murmur import inject


@pytest.fixture
def conf(donnees):
    return cfg.charger()


@pytest.fixture
def presse_papier_preserve():
    """Rend son presse-papier a l'utilisateur, quoi qu'il arrive."""
    try:
        avant = inject.lire_presse_papier()
    except inject.ErreurInjection:
        avant = None
    yield
    if avant is not None:
        try:
            inject.ecrire_presse_papier(avant)
        except inject.ErreurInjection:
            pass


# --------------------------------------------------------------------------
# Construction des evenements
# --------------------------------------------------------------------------

def test_collage_envoie_ctrl_v_et_relache_tout():
    evenements = inject.evenements_collage()
    assert len(evenements) == 4
    codes = [e.ki.wVk for e in evenements]
    assert codes == [inject.VK_CONTROL, inject.VK_V,
                     inject.VK_V, inject.VK_CONTROL]

    montees = [bool(e.ki.dwFlags & inject.KEYEVENTF_KEYUP) for e in evenements]
    assert montees == [False, False, True, True], \
        "les touches doivent etre relachees, sinon Ctrl reste colle"


def test_frappe_produit_deux_evenements_par_caractere():
    evenements = inject.evenements_frappe("abc")
    assert len(evenements) == 6


def test_frappe_porte_le_codepoint_et_le_drapeau_unicode():
    evenements = inject.evenements_frappe("A")
    appui, relachement = evenements
    assert appui.ki.wScan == ord("A")
    assert appui.ki.wVk == 0, "en mode Unicode le code de touche doit etre nul"
    assert appui.ki.dwFlags & inject.KEYEVENTF_UNICODE
    assert relachement.ki.dwFlags & inject.KEYEVENTF_KEYUP


def test_frappe_gere_les_accents_et_la_typographie():
    for caractere in "àéèêëîïôùûüç«»—€":
        evenements = inject.evenements_frappe(caractere)
        assert len(evenements) == 2, caractere
        assert evenements[0].ki.wScan == ord(caractere), caractere


def test_frappe_decoupe_les_caracteres_hors_bmp_en_paire():
    """Sans paire de substitution, un emoji serait tronque."""
    evenements = inject.evenements_frappe("\U0001F600")
    assert len(evenements) == 4, "deux unites de code, donc quatre evenements"
    haute, basse = evenements[0].ki.wScan, evenements[2].ki.wScan
    assert 0xD800 <= haute <= 0xDBFF
    assert 0xDC00 <= basse <= 0xDFFF


def test_frappe_dun_texte_vide_ne_produit_rien():
    assert inject.evenements_frappe("") == []


def test_envoyer_sans_evenement_ne_fait_rien():
    inject._envoyer([])


# --------------------------------------------------------------------------
# Presse-papier
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_aller_retour_presse_papier(presse_papier_preserve):
    temoin = "Murmur test àéèç « » — 42 % 15 €"
    inject.ecrire_presse_papier(temoin)
    assert inject.lire_presse_papier() == temoin


@pytest.mark.materiel
def test_presse_papier_preserve_les_sauts_de_ligne(presse_papier_preserve):
    temoin = "premiere ligne\r\nseconde ligne"
    inject.ecrire_presse_papier(temoin)
    assert inject.lire_presse_papier() == temoin


@pytest.mark.materiel
def test_presse_papier_accepte_un_texte_vide(presse_papier_preserve):
    inject.ecrire_presse_papier("")
    assert inject.lire_presse_papier() in ("", None)


@pytest.mark.materiel
def test_presse_papier_accepte_un_texte_long(presse_papier_preserve):
    """Une dictee longue ne doit pas etre tronquee."""
    temoin = "phrase de dictee. " * 500
    inject.ecrire_presse_papier(temoin)
    assert inject.lire_presse_papier() == temoin


# --------------------------------------------------------------------------
# Fenetre active
# --------------------------------------------------------------------------

@pytest.mark.materiel
def test_fenetre_active_renvoie_un_couple_exploitable():
    """On ne presume pas de la forme du nom d'executable.

    Un premier jet exigeait une terminaison en « .exe » et a echoue sur
    « parsecd.exe.tmp2 » — un installeur en cours de mise a jour. Windows
    n'impose rien : le nom sert a identifier l'application, pas a etre valide.
    """
    titre, executable = inject.fenetre_active()
    assert isinstance(titre, str)
    assert isinstance(executable, str)
    assert "\\" not in executable, "le chemin doit avoir ete reduit au nom"


# --------------------------------------------------------------------------
# Injecteur
# --------------------------------------------------------------------------

def test_strategie_par_defaut_est_le_presse_papier(conf):
    """Tranchee en T0.1 : 5/5 applications, et insensible aux autocorrections."""
    assert inject.Injecteur(conf).strategie == "presse_papier"


def test_texte_vide_nest_pas_injecte(conf, monkeypatch):
    appels = []
    monkeypatch.setattr(inject, "injecter_par_presse_papier",
                        lambda *a, **k: appels.append(a))
    inject.Injecteur(conf).injecter("")
    assert appels == [], "rien ne doit etre envoye pour un texte vide"


def test_la_strategie_configuree_est_celle_appelee(conf, monkeypatch):
    appels = []
    monkeypatch.setattr(inject, "injecter_par_presse_papier",
                        lambda t, **k: appels.append(("presse_papier", t)))
    monkeypatch.setattr(inject, "injecter_par_frappe",
                        lambda t, p: appels.append(("frappe", t)))

    inject.Injecteur(conf).injecter("bonjour")
    conf.definir("injection.strategie", "frappe")
    inject.Injecteur(conf).injecter("bonjour")

    assert appels == [("presse_papier", "bonjour"), ("frappe", "bonjour")]


def test_la_frappe_respecte_la_pause_configuree(conf, monkeypatch):
    """Le rythme n'est pas cosmetique : en dessous de ~15 ms, le texte arrive
    tronque ou avec des caracteres repetes (mesure en T0.1)."""
    pauses = []
    monkeypatch.setattr(inject, "_envoyer", lambda e: None)
    monkeypatch.setattr(inject.time, "sleep", lambda d: pauses.append(d))

    conf.definir("injection.strategie", "frappe")
    conf.definir("injection.frappe_pause_ms", 20)
    inject.Injecteur(conf).injecter("abc")

    assert len(pauses) == 3, "une pause par caractere"
    assert all(p == pytest.approx(0.020) for p in pauses)


# --------------------------------------------------------------------------
# Insertion reelle — critere de fin de T1.5
# --------------------------------------------------------------------------

TEXTE_REFERENCE = ("Murmur : àéèêë îïô ùûü ç, « guillemets », "
                   "l'apostrophe, 42 % — 15 € (fin) !")


TITRE_FENETRE = "Murmur autotest injection"


@pytest.mark.materiel
def test_insertion_reelle_dans_une_fenetre_controlee(conf, racine_tk,
                                                     presse_papier_preserve):
    """Insere dans une fenetre dont on relit le contenu exact.

    Verifie la chaine complete — presse-papier, SendInput, reception — sans
    dependre d'une application tierce.

    Le test CONTROLE qu'il detient bien le focus avant d'injecter, et se
    declare non concluant sinon. Sans ce garde-fou il devient instable : une
    autre fenetre qui retient le focus produirait un echec rapporte comme un
    defaut d'injection, alors que rien n'a ete mesure.
    """
    import tkinter as tk

    # Toplevel sur la racine partagee : creer un second Tk() dans le meme
    # processus finit par echouer sur un « tk wasn't installed properly ».
    racine = tk.Toplevel(racine_tk)
    racine.title(TITRE_FENETRE)
    racine.geometry("560x160+150+150")
    racine.attributes("-topmost", True)
    zone = tk.Text(racine)
    zone.pack(fill="both", expand=True)

    resultat = {}

    def injecter():
        racine.lift()
        racine.focus_force()
        zone.focus_set()
        racine.update()

        titre_actif, _ = inject.fenetre_active()
        if TITRE_FENETRE not in titre_actif:
            resultat["sans_focus"] = titre_actif
            racine.quit()
            return

        # La fenetre peut etre au premier plan sans que la zone de saisie
        # detienne le focus clavier — le collage partirait alors dans le vide
        # et l'echec serait impute a l'injection. On exige les deux.
        if racine.focus_get() is not zone:
            resultat["sans_focus"] = f"{titre_actif} (zone de saisie non active)"
            racine.quit()
            return

        # SUR UN FIL A PART, et c'est la tout le point de ce test.
        #
        # `SendInput` ne fait que **deposer** la frappe dans la file de la
        # fenetre visee. Lancee depuis cette meme reaction Tk, l'injection
        # bloquerait la boucle de la fenetre jusqu'a son terme — donc jusqu'a
        # la restauration du presse-papier, 250 ms plus tard. Le Ctrl+V ne
        # serait traite qu'apres, et collerait l'ANCIEN contenu. C'est ce qui
        # arrivait, et l'echec se lisait comme un defaut d'injection.
        #
        # Rien de tel en usage reel : Murmur injecte depuis son fil de
        # traitement vers une application tierce, dont la boucle tourne. Le
        # fil separe retablit cette disposition.
        threading.Thread(
            target=lambda: inject.Injecteur(conf).injecter(TEXTE_REFERENCE),
            daemon=True).start()
        racine.after(60, guetter, time.monotonic())

    def guetter(depart: float):
        """Attend le texte en laissant la boucle tourner."""
        recu = zone.get("1.0", "end-1c")
        if recu or time.monotonic() - depart > 3.0:
            resultat["texte"] = recu
            racine.quit()
            return
        racine.after(40, guetter, depart)

    racine.after(600, injecter)
    racine.mainloop()
    racine.destroy()

    if "sans_focus" in resultat:
        pytest.skip(f"focus retenu par « {resultat['sans_focus']} » : "
                    f"rien n'a pu etre mesure")

    assert resultat.get("texte") == TEXTE_REFERENCE, (
        f"attendu {TEXTE_REFERENCE!r}, obtenu {resultat.get('texte')!r}")


# --------------------------------------------------------------------------
# Envoyer un raccourci depuis un raccourci
# --------------------------------------------------------------------------
#
# L'apprentissage est declenche par Ctrl+Alt+C et voudrait envoyer un Ctrl+C.
# Mais au moment ou il s'execute, l'utilisateur tient encore Ctrl et Alt : le
# systeme voit alors Ctrl+Alt+C — la combinaison de depart — et l'application
# ne copie rien. La selection etait bien a l'ecran, le presse-papier
# inchange. On ne peut pas relacher une touche que quelqu'un tient : on attend.

def test_on_attend_que_les_modificateurs_soient_laches(monkeypatch):
    """Trois relevés : Ctrl tenu, puis Alt seul, puis plus rien."""
    etats = [{inject.VK_CONTROL, inject.VK_MENU}, {inject.VK_MENU}, set()]
    releves = []

    def enfoncee(code):
        courant = etats[min(len(releves), len(etats) - 1)]
        return code in courant

    def dormir(_duree):
        releves.append(True)

    monkeypatch.setattr(inject, "touche_enfoncee", enfoncee)
    monkeypatch.setattr(inject.time, "sleep", dormir)

    assert inject.attendre_les_doigts(limite_s=5.0) is True
    assert releves, "on n'a pas attendu du tout"


def test_l_attente_ne_dure_pas_indefiniment(monkeypatch):
    """Une touche bloquee — clavier, machine virtuelle — ne doit pas figer
    l'apprentissage pour toujours."""
    monkeypatch.setattr(inject, "touche_enfoncee", lambda _c: True)
    monkeypatch.setattr(inject.time, "sleep", lambda _d: None)

    assert inject.attendre_les_doigts(limite_s=0.05) is False


def test_la_copie_attend_avant_de_frapper(monkeypatch):
    """L'ordre compte : frapper d'abord reviendrait a envoyer Ctrl+Alt+C."""
    ordre = []
    monkeypatch.setattr(inject, "attendre_les_doigts",
                        lambda *a, **k: ordre.append("attendu") or True)
    monkeypatch.setattr(inject, "_envoyer",
                        lambda evenements: ordre.append("frappe"))
    monkeypatch.setattr(inject.time, "sleep", lambda _d: None)

    inject.copier_la_selection()

    assert ordre == ["attendu", "frappe"]


def test_tous_les_modificateurs_sont_surveilles():
    """Shift et la touche Windows aussi : un raccourci d'apprentissage peut
    les porter."""
    assert set(inject.MODIFICATEURS) == {
        inject.VK_CONTROL, inject.VK_MENU, inject.VK_SHIFT,
        inject.VK_LWIN, inject.VK_RWIN}

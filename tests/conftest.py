"""Fixtures communes.

Les tests ne doivent jamais ecrire dans le vrai %APPDATA% : chaque test recoit
un dossier de donnees jetable via la variable d'environnement prevue a cet
effet.
"""

import importlib
import sys
import threading
import time
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from murmur import config as module_config  # noqa: E402
from murmur import ecran as module_ecran  # noqa: E402
from murmur import journal as module_journal  # noqa: E402

# Avant toute fenetre, et donc avant la racine Tk de la session.
#
# Sans cela le processus de test n'est pas conscient du DPI, et Windows lui
# ment : `GetWindowRect` rend des pixels virtualises tandis que le gestionnaire
# de bureau rend les pixels reels. A 125 %, les deux mesures d'une meme fenetre
# different d'un quart — et les tests du cadre mesuraient un ecart de 687 px
# la ou l'application, elle, n'en verra jamais aucun : elle declare sa
# conscience du DPI au demarrage.
module_ecran.declarer()


@pytest.fixture(autouse=True)
def journal_isole():
    """Detache le journal entre chaque test.

    Le journal est configure une fois pour toutes au premier appel : sans
    remise a zero, son fichier resterait ouvert sur le dossier temporaire du
    PREMIER test, supprime depuis. Ecrire dans un descripteur pointant sur un
    dossier disparu produit des defaillances erratiques, tres loin de leur
    cause.
    """
    module_journal.reinitialiser()
    yield
    module_journal.reinitialiser()


#: Fils lances par Murmur. Un test qui en laisse un derriere lui le fait
#: tourner pendant les tests suivants, puis pendant l'arret de l'interpreteur —
#: d'ou des defaillances erratiques, tres loin de leur cause.
FILS_MURMUR = ("traitement", "surveillance", "silence", "raccourcis",
               "relachement-", "icone", "apprentissage")


def _fils_murmur_vivants():
    return [f.name for f in threading.enumerate()
            if any(f.name.startswith(prefixe) for prefixe in FILS_MURMUR)]


@pytest.fixture(autouse=True)
def aucun_fil_fuyant():
    """Echoue si un test laisse un fil de Murmur en vie.

    Sans ce controle, le symptome n'apparait qu'a la fin de la session, sous
    forme d'un plantage sans message ni test coupable.
    """
    yield
    # Laisse une courte marge : un fil peut etre en train de se terminer.
    limite = time.monotonic() + 1.0
    while time.monotonic() < limite:
        restants = _fils_murmur_vivants()
        if not restants:
            return
        time.sleep(0.05)
    pytest.fail(f"fil(s) laisse(s) en vie par ce test : {sorted(set(restants))}")


@pytest.fixture(scope="session")
def racine_tk():
    """Unique instance Tk de la session.

    Tkinter tolere mal plusieurs `Tk()` successifs dans un meme processus :
    creer puis detruire des interpreteurs Tcl finit par echouer sur un
    « tk wasn't installed properly » trompeur. Les tests qui ont besoin d'une
    fenetre creent donc un `Toplevel` sur cette racine partagee.
    """
    import tkinter as tk

    racine = tk.Tk()
    racine.withdraw()
    yield racine
    try:
        racine.destroy()
    except tk.TclError:
        pass


@pytest.fixture(autouse=True)
def aucun_moteur_fuyant(request):
    """Echoue si un test marque « lent » laisse un moteur en vie.

    Le controle est reserve a ces tests : eux seuls demarrent un moteur, et
    l'enumeration des processus coute trop cher pour la passer sur les 250
    tests rapides.

    Sans ce garde-fou, le moteur orphelin n'apparait qu'a la fin de la
    session, sans indication du test coupable — et il bloque le port au
    lancement suivant de l'application.
    """
    lent = request.node.get_closest_marker("lent") is not None
    if not lent:
        yield
        return

    from murmur import stt, systeme

    # Une instance de Murmur en cours d'utilisation rend la detection
    # ininterpretable : son fil de surveillance peut relancer son propre
    # moteur pendant le test, faisant apparaitre un processus que le test n'a
    # pas cree. Mieux vaut renoncer au controle que produire une accusation
    # fausse — un test qui crie au loup finit par etre ignore.
    if not systeme.InstanceUnique().est_libre():
        yield
        return

    # On compte les moteurs plutot que d'en suivre les identifiants : un
    # redemarrage change le PID sans qu'aucune fuite n'ait eu lieu.
    avant = stt.orphelins_du_moteur()

    yield

    # Un processus termine met un instant a disparaitre de la table systeme :
    # verifier sans marge produirait de faux positifs a chaque arret propre.
    # La marge est large car l'arret ralentit sur une machine chargee.
    limite = time.monotonic() + 5.0
    while time.monotonic() < limite:
        apres = stt.orphelins_du_moteur()
        if len(apres) <= len(avant):
            return
        time.sleep(0.1)

    # Seulement le surplus : une instance de Murmur en cours d'utilisation ne
    # doit pas etre emportee par la suite de tests.
    surplus = [pid for pid in apres if pid not in avant][:len(apres) - len(avant)]
    stt.tuer_orphelins(surplus)
    pytest.fail(f"{len(apres) - len(avant)} moteur(s) laisse(s) en vie par "
                f"ce test : {surplus}")


@pytest.fixture
def donnees(tmp_path, monkeypatch):
    """Redirige les donnees utilisateur vers un dossier temporaire."""
    cible = tmp_path / "donnees"
    monkeypatch.setenv(module_config.VAR_DONNEES, str(cible))
    return cible


@pytest.fixture
def config(donnees):
    """Configuration fraiche, isolee, rechargee depuis zero."""
    importlib.reload(module_config)
    return module_config

"""Ouvre le tableau de bord dans sa propre fenetre.

Processus separe de l'application : voir la docstring du paquet. Il se lance
seul, lit la base, et meurt avec sa fenetre.

Comme pour `murmur.lancement`, le corps ne vit pas dans `__main__.py` :
PyInstaller ecarte de son analyse les modules ainsi nommes a l'interieur d'un
paquet.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .. import cadre, canal as module_canal, chrome, config as configuration
from .. import ecran, journal, sorties, systeme
from .. import theme as module_theme

# En tout premier : sans console, la moindre ecriture sur une sortie
# inexistante tue le fil qui ouvre la fenetre — sans un mot, et apres que
# WebView2 a demarre sa douzaine de processus.
sorties.assurer()

# Avant toute fenetre : declaree ensuite, la conscience du DPI laisse la
# fenetre deja nee dans l'ancien referentiel, et Windows continue d'etirer
# son image.
ECHELLE = ecran.declarer() and ecran.facteur() or 1.0

from . import PAGE_PAR_DEFAUT, PAGES     # noqa: E402
from . import api as module_api          # noqa: E402

RACINE = Path(__file__).resolve().parent
WEB = RACINE / "web"

LARGEUR = 1060
HAUTEUR = 700
MINIMUM = (860, 580)


def main(page: str = PAGE_PAR_DEFAUT) -> int:
    import webview

    log = journal.obtenir("tableau")
    page = page if page in PAGES else PAGE_PAR_DEFAUT

    # Une seule fenetre a la fois. Le verrou est pris ici et non par
    # l'application : le tableau nait et meurt sans elle, et c'est sa propre
    # presence qu'il faut savoir.
    verrou = systeme.InstanceUnique(port=systeme.PORT_TABLEAU)
    try:
        verrou.prendre()
    except systeme.DejaLance:
        # Deja ouvert : on lui passe la demande plutot que d'ouvrir un double.
        module_canal.envoyer("montrer", {"page": page},
                             port=systeme.PORT_TABLEAU)
        return 0

    # La fenetre est creee **avec** son cadre, puis on lui retire le seul
    # bandeau. Le mode « sans cadre » de pywebview aurait aussi emporte le
    # cadre epais, donc le redimensionnement par les bords et l'ancrage : voir
    # la docstring de `murmur.cadre`.
    gestion = cadre.Gestion(lambda: chrome.descripteur(fenetre))
    api = module_api.Api(gestion, page=page)

    # La page demande ses donnees au pont plutot que de les recevoir figees :
    # une dictee qui arrive pendant que la fenetre est ouverte doit pouvoir
    # s'afficher sans la reconstruire.
    fenetre = webview.create_window(
        "Murmur", str(WEB / "index.html"),
        width=round(LARGEUR * ECHELLE), height=round(HAUTEUR * ECHELLE),
        min_size=(round(MINIMUM[0] * ECHELLE), round(MINIMUM[1] * ECHELLE)),
        js_api=api, background_color="#f5f4f0")
    api.attacher(fenetre)

    def montrer(arguments: dict) -> dict:
        """L'application redemande le tableau alors qu'il est deja ouvert."""
        demandee = arguments.get("page") or PAGE_PAR_DEFAUT
        gestion.montrer()
        if demandee in PAGES:
            # `afficher` est la fonction de la page : on lui parle dans sa
            # langue plutot que de simuler un clic sur l'onglet.
            fenetre.evaluate_js(f"afficher({demandee!r})")
        return {"page": demandee}

    def fermer(_arguments: dict) -> dict:
        """L'application s'arrete : le tableau n'a pas a lui survivre."""
        log.info("fermeture demandee par l'application")
        fenetre.destroy()
        return {"ferme": True}

    serveur = module_canal.Serveur(verrou.prise,
                                   {"montrer": montrer, "fermer": fermer})

    def habiller() -> None:
        """Le bandeau ne peut etre retire qu'une fois la fenetre creee : avant,
        il n'y a pas de descripteur. `shown` est le premier moment ou il
        existe."""
        palette = module_theme.resoudre(
            configuration.charger()["interface.theme"])
        chrome.habiller(fenetre, palette)
        gestion.preparer()

    fenetre.events.shown += habiller
    fenetre.events.closing += gestion.fermer

    log.info("tableau de bord ouvert (echelle %.0f %%, page %s)",
             ECHELLE * 100, page)
    serveur.demarrer()
    try:
        # Mode prive, et c'est mesure : un profil persistant ne fait pas
        # demarrer WebView2 plus vite (776 a 1082 ms contre 830 en moyenne),
        # et deux processus qui partageraient le meme dossier de profil se
        # gêneraient. Rien a gagner, quelque chose a perdre.
        webview.start()
    finally:
        # Filet : `closing` ne se declenche pas sur toutes les fins de
        # processus.
        serveur.arreter()
        verrou.liberer()
        gestion.fermer()
        api.fermer_ressources()
        log.info("tableau de bord ferme")
    return 0


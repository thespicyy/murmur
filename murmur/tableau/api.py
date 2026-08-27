"""Ce que la page peut demander a Python.

pywebview expose les methodes publiques de cet objet sous
`window.pywebview.api`. Elles sont appelees depuis le fil du navigateur : tout
ce qu'elles touchent doit supporter d'etre lu et ecrit hors du fil principal.
La base l'accepte — ses ecritures sont deja serialisees par un verrou — et le
lexique est relu a chaque appel.

Les modifications ne s'arretent pas au disque : un terme ajoute change le
prompt du moteur, un raccourci modifie doit etre repris a l'instant. Le canal
previent l'application, qui vit dans l'autre processus. Si elle a ete fermee
entre-temps, l'echec est signale a la page sans interrompre l'utilisateur.
"""

from __future__ import annotations

from .. import canal, config as configuration, hotkeys, journal
from .. import langue as module_langue, lexicon, store, systeme
from .. import theme as module_theme
from . import donnees

_log = journal.obtenir("tableau")

#: Dictees chargees d'un coup, puis par tranches. Assez pour remplir l'ecran
#: et le defilement qui suit.
PAR_PAGE = 40


class Api:
    """Le pont. Une methode par chose que la page sait demander."""

    def __init__(self, gestion=None, fenetre=None, page: str = ""):
        # Tout ce qui n'est pas une commande porte un nom prive : pywebview
        # parcourt l'objet expose pour en dresser la liste des methodes, et
        # descend dans chaque attribut public. Une fenetre stockee en clair
        # l'entrainait jusque dans les objets .NET de WebView2, ou la
        # comparaison d'un rectangle levait une erreur de type.
        self._fenetre = fenetre
        self._gestion = gestion
        # La page d'ouverture est demandee par la page elle-meme, et non
        # imposee par un appel de script des l'affichage : le pont n'a pas
        # encore repondu a ce moment-la, et la page s'afficherait dans une
        # langue qu'elle n'a pas encore recue.
        self._page = page
        self._conf = configuration.charger()
        self._mot = module_langue.Traducteur(self._conf)
        self._base: store.Historique | None = None

    # -- ressources --------------------------------------------------------

    def attacher(self, fenetre) -> None:
        self._fenetre = fenetre

    def _historique(self) -> store.Historique:
        # Ouverte a la demande et gardee : rouvrir la base a chaque appel
        # couterait un acces disque par frappe au clavier dans la recherche.
        if self._base is None:
            self._base = store.Historique()
        return self._base

    def fermer_ressources(self) -> None:
        base, self._base = self._base, None
        if base is not None:
            base.fermer()

    # -- lecture -----------------------------------------------------------

    def insights(self) -> dict:
        return donnees.insights(self._historique(), lexicon.Lexique(), self._mot)

    def calendrier(self, decalage: int = 0) -> dict:
        """Une page du calendrier d'activite, sans tout recalculer.

        Redemander `insights` entier pour faire glisser la grille relirait
        l'usage par application et le lexique a chaque clic sur une fleche.
        """
        return donnees.calendrier(self._historique(), self._mot, int(decalage))

    def dictees(self, limite: int = PAR_PAGE, terme: str = "") -> dict:
        return donnees.dictees(self._historique(), self._mot, limite, terme)

    def dictionnaire(self) -> dict:
        return donnees.dictionnaire(lexicon.Lexique(), self._mot)

    def textes(self) -> dict:
        """Les libelles de l'interface, dans la langue choisie.

        La page ne porte aucune chaine en dur : elle demande ses mots, comme
        la version Tkinter les demandait au meme traducteur.
        """
        return {cle: self._mot(cle) for cle in module_langue.TEXTES}

    def etat(self) -> dict:
        return {
            "langue": self._mot.langue,
            # Le theme **resolu**, non la preference : « auto » ne dit rien a
            # la page, qui ne sait pas lire le reglage de Windows. Rendue
            # telle quelle, cette valeur retombait toujours sur le clair et
            # le mode sombre ne s'appliquait jamais.
            "theme": module_theme.resoudre(
                self._conf["interface.theme"]).nom,
            "repliee": bool(self._conf["interface.barre_repliee"]),
            "raccourci": self._conf["raccourcis.maintien"],
            "page": self._page,
        }

    # -- ecriture ----------------------------------------------------------

    def supprimer_dictee(self, identifiant: int) -> dict:
        supprimee = self._historique().supprimer(int(identifiant))
        return {"ok": supprimee}

    def ajouter_terme(self, terme: str, variante: str = "") -> dict:
        lexique = lexicon.Lexique()
        try:
            lexique.ajouter(terme.strip(),
                            [variante.strip()] if variante.strip() else None)
        except ValueError as exc:
            return {"ok": False, "erreur": str(exc)}
        lexique.sauvegarder()
        return {"ok": True, "prevenu": self._prevenir("lexique_modifie")}

    def retirer_terme(self, terme: str) -> dict:
        lexique = lexicon.Lexique()
        lexique.retirer(terme)
        lexique.sauvegarder()
        return {"ok": True, "prevenu": self._prevenir("lexique_modifie")}

    def replier(self, repliee: bool) -> dict:
        """Retient l'etat du volet : c'est une preference, pas un geste."""
        self._conf.definir("interface.barre_repliee", bool(repliee))
        self._conf.sauvegarder()
        return {"ok": True}

    def _prevenir(self, commande: str, **arguments) -> bool:
        reponse = canal.envoyer(commande, arguments)
        if not reponse.get("ok"):
            _log.warning("l'application n'a pas ete prevenue de « %s »",
                         commande)
        return bool(reponse.get("ok"))

    # -- reglages ----------------------------------------------------------

    def reglages(self) -> dict:
        # Relue plutot que reprise du cache : la configuration a pu changer
        # depuis l'ouverture de la fenetre, par l'application elle-meme.
        self._conf = configuration.charger()
        return donnees.reglages(self._conf, self._mot,
                                systeme.demarrage_auto_actif(),
                                str(configuration.dossier_donnees()))

    def enregistrer_reglages(self, valeurs: dict) -> dict:
        """Valide avant d'ecrire.

        Une configuration refusee au demarrage laisserait l'application
        inutilisable sans explication : on refuse ici, ou l'utilisateur peut
        encore corriger.
        """
        conf = configuration.charger()
        demarrage = None
        for chemin, valeur in valeurs.items():
            if chemin == donnees.DEMARRAGE:
                demarrage = bool(valeur)
            elif chemin == "audio.peripherique":
                # La page ne connait pas `None` : elle rend une chaine vide
                # pour « entree par defaut du systeme ».
                conf.definir(chemin,
                             None if valeur == donnees.MICRO_DEFAUT
                             else int(valeur))
            else:
                conf.definir(chemin, valeur)

        for chemin in ("raccourcis.maintien", "raccourcis.bascule",
                       "raccourcis.apprendre"):
            try:
                hotkeys.analyser(conf[chemin])
            except hotkeys.ErreurRaccourci as exc:
                return {"ok": False, "titre": self._mot("reg.raccourci_invalide"),
                        "erreur": str(exc)}
        try:
            configuration._valider(conf.valeurs)
        except configuration.ErreurConfig as exc:
            return {"ok": False, "titre": self._mot("reg.reglage_invalide"),
                    "erreur": str(exc)}

        avertissement = None
        if demarrage is not None:
            try:
                systeme.definir_demarrage_auto(demarrage)
            except OSError as exc:
                _log.exception("demarrage automatique")
                avertissement = self._mot("reg.demarrage.echec", erreur=exc)

        conf.sauvegarder()
        self._conf = conf
        self._mot = module_langue.Traducteur(conf)
        _log.info("reglages enregistres")
        return {"ok": True, "avertissement": avertissement,
                "prevenu": self._prevenir("reglages_modifies")}

    # -- commandes de fenetre ---------------------------------------------
    #
    # Reduction et agrandissement passent par `cadre`, non par pywebview :
    # `minimize()` s'appuie sur l'etat du systeme, que Windows calcule mal pour
    # une fenetre sans bandeau — la fenetre agrandie deborde alors de la
    # largeur du cadre et recouvre la barre des taches.

    def reduire(self) -> dict:
        return {"ok": bool(self._gestion and self._gestion.reduire())}

    def agrandir(self) -> dict:
        if not self._gestion:
            return {"agrandie": False}
        return self._gestion.basculer_agrandissement()

    def deplacer(self) -> dict:
        """Debut d'un glisser sur la barre de titre.

        La page ne peut pas mener le deplacement elle-meme : ses evenements de
        souris cessent d'arriver des que le curseur sort de la fenetre. Le
        suivi est donc pris en charge cote Python, curseur interroge
        directement.
        """
        return {"ok": bool(self._gestion
                           and self._gestion.commencer_deplacement())}

    def redimensionner_haut(self) -> dict:
        """Le bord haut appartient a la page : Windows n'y voit plus de poignee."""
        return {"ok": bool(self._gestion
                           and self._gestion.commencer_redimensionnement_haut())}

    def fermer(self) -> None:
        self._fenetre.destroy()

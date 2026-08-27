"""Textes de l'interface, en francais et en anglais.

Le vocabulaire anglais reprend celui de Wispr Flow — « Dictation »,
« Insights », « Dictionary », « fixes », « streak » — a la demande de
l'utilisateur, qui s'en sert comme reference. Ce n'est pas une traduction
mot a mot du francais : « Statistiques » devient « Insights », pas
« Statistics ».

Un module de textes plutot qu'un vrai gettext : deux langues, deux cents
chaines, aucun traducteur exterieur a servir. Un fichier `.po` et sa chaine
d'outils couteraient plus qu'ils ne rapporteraient, et la table se relit
d'un coup d'oeil.

Les accords sont traites ici aussi, les regles differant : « 0 dictée » au
singulier en francais, « 0 dictations » au pluriel en anglais.
"""

from __future__ import annotations

from datetime import date

LANGUES = ("fr", "en")

#: Langue par defaut. L'anglais, pour coller au vocabulaire de la reference ;
#: le francais reste a un clic dans les reglages.
DEFAUT = "en"

#: Chaines simples, indexees par cle puis par langue.
TEXTES: dict[str, dict[str, str]] = {
    # -- navigation --------------------------------------------------------
    "page.dictees": {"fr": "Dictées", "en": "Dictation"},
    "page.dictionnaire": {"fr": "Dictionnaire", "en": "Dictionary"},
    "page.statistiques": {"fr": "Statistiques", "en": "Insights"},
    "reglages": {"fr": "Réglages", "en": "Settings"},

    # -- page des dictees --------------------------------------------------
    "dictees.recherche": {"fr": "Rechercher dans tes dictées",
                          "en": "Search dictations"},
    "dictees.aujourdhui": {"fr": "aujourd'hui", "en": "today"},
    "dictees.vide": {"fr": "Aucune dictée pour l'instant.",
                     "en": "No dictations yet."},
    "dictees.vide.aide": {"fr": "Maintiens {raccourci} et parle.",
                          "en": "Hold {raccourci} and speak."},
    "dictees.sans_resultat": {"fr": "Aucun résultat.", "en": "No results."},
    "dictees.plus": {"fr": "Afficher plus", "en": "Show more"},
    "dictees.copier": {"fr": "Copier", "en": "Copy"},
    "dictees.supprimer": {"fr": "Supprimer", "en": "Delete"},
    "dictees.supprimer.confirmer": {"fr": "Supprimer cette dictée ?",
                                    "en": "Delete this dictation?"},
    "dictees.copie_impossible": {"fr": "Copie impossible : {erreur}",
                                 "en": "Could not copy: {erreur}"},
    "jour.aujourdhui": {"fr": "aujourd'hui", "en": "today"},
    "jour.hier": {"fr": "hier", "en": "yesterday"},

    # -- dictionnaire ------------------------------------------------------
    "dico.terme": {"fr": "Terme correct", "en": "Correct spelling"},
    "dico.variante": {"fr": "Ce que Murmur écrit à tort",
                      "en": "What Murmur gets wrong"},
    "dico.ajouter": {"fr": "Ajouter", "en": "Add"},
    "dico.retirer": {"fr": "Retirer", "en": "Remove"},
    "dico.retirer.confirmer": {"fr": "Retirer « {terme} » ?",
                               "en": "Remove “{terme}”?"},
    "dico.vide": {"fr": "Ton dictionnaire est vide.",
                  "en": "Your dictionary is empty."},
    "dico.vide.aide": {
        "fr": "Ajoute un terme ci-dessus, ou corrige une dictée :\n"
              "copie le texte corrigé puis appuie sur {raccourci}.",
        "en": "Add a term above, or fix a dictation:\n"
              "copy the corrected text, then press {raccourci}."},
    "dico.corrige": {"fr": "entendu comme", "en": "heard as"},
    "dico.hors_prompt": {"fr": "  hors prompt", "en": "  not in prompt"},
    "dico.hors_prompt.compte": {"fr": "{nombre} hors prompt",
                                "en": "{nombre} not in prompt"},
    "dico.indisponible": {"fr": "Indisponible.", "en": "Unavailable."},

    # -- statistiques ------------------------------------------------------
    "stats.sous_titre": {"fr": "ce que la dictée t'a fait gagner",
                         "en": "what dictation has saved you"},
    "stats.vitesse": {"fr": "MOTS PAR MINUTE", "en": "WORDS PER MINUTE"},
    "stats.clavier": {"fr": "le clavier", "en": "typing"},
    "stats.corrections": {"fr": "CORRECTIONS APPRISES", "en": "FIXES LEARNED"},
    "stats.termes": {"fr": "au dictionnaire", "en": "dictionary entries"},
    "stats.remplacements": {"fr": "remplacements appliqués",
                            "en": "dictionary fixes"},
    "stats.mots": {"fr": "MOTS DICTÉS", "en": "TOTAL WORDS DICTATED"},
    "stats.periode": {"fr": "comparé au mois dernier", "en": "vs last month"},
    "stats.applications": {"fr": "Applications", "en": "Desktop usage"},
    "stats.activite": {"fr": "Activité", "en": "Activity"},
    "stats.sans_dictee": {"fr": "Aucune dictée pour l'instant.",
                          "en": "No dictations yet."},

    # -- correction --------------------------------------------------------
    # -- premier lancement ------------------------------------------------
    "premier.titre": {"fr": "Preparation de Murmur",
                      "en": "Setting up Murmur"},
    "premier.explication": {
        "fr": "Murmur telecharge son modele de reconnaissance vocale : "
              "{taille} Mo, une seule fois. Il est choisi pour cette "
              "machine — {detail}.\n\nEnsuite, plus rien ne quitte "
              "l\'ordinateur.",
        "en": "Murmur is downloading its speech model: {taille} MB, "
              "once. It was chosen for this machine — {detail}.\n\n"
              "After this, nothing ever leaves your computer."},
    "modele.avec_carte": {
        "fr": "qualite maximale, environ 250 ms par phrase",
        "en": "best quality, around 250 ms per sentence"},
    "modele.sans_carte": {
        "fr": "adapte au processeur, environ 2 s par phrase",
        "en": "suited to the processor, around 2 s per sentence"},
    "premier.renoncer": {"fr": "Annuler", "en": "Cancel"},
    "premier.echec": {
        "fr": "Le modele n\'a pas pu etre telecharge.\n\n{raison}"
              "\n\nRelance Murmur pour reprendre la ou il s\'est "
              "arrete.",
        "en": "The model could not be downloaded.\n\n{raison}\n\n"
              "Start Murmur again to resume where it stopped."},

    "corr.titre": {"fr": "Corrections détectées", "en": "Fixes detected"},
    "corr.aide": {
        "fr": "Coche ce que Murmur doit retenir. Les tournures de style sont "
              "décochées : les retenir réécrirait toutes tes dictées futures.",
        "en": "Tick what Murmur should remember. Style rewrites are left "
              "unticked: keeping them would reword every future dictation."},
    "corr.aucune": {
        "fr": "Aucune correction n'a pu être déduite du presse-papier.",
        "en": "No fix could be derived from the clipboard."},
    "corr.aucune.aide": {
        "fr": "Copie la phrase corrigée — le texte autour ne gêne pas, "
              "Murmur cherche ligne par ligne.",
        "en": "Copy the corrected sentence — surrounding text is fine, "
              "Murmur searches line by line."},
    "corr.raison": {"fr": "Raison : {raison}.", "en": "Reason: {raison}."},
    "corr.identique": {"fr": "Aucune différence trouvée.",
                       "en": "No difference found."},
    "corr.rien_coche": {
        "fr": "Rien n'est coché : rien ne sera appris.\n\nCoche ce que "
              "Murmur doit retenir, ou clique sur Ignorer.",
        "en": "Nothing is ticked, so nothing will be learned.\n\nTick what "
              "Murmur should remember, or click Discard."},
    "corr.enregistrer": {"fr": "Enregistrer", "en": "Save"},
    "corr.ignorer": {"fr": "Ignorer", "en": "Discard"},

    "stats.applications.total": {"fr": "Applications utilisées",
                                "en": "Total apps used"},
    "stats.record": {"fr": "Record", "en": "Longest streak"},

    # -- reglages ----------------------------------------------------------
    "reg.sous_titre": {"fr": "Raccourcis, apparence et comportement",
                       "en": "Shortcuts, appearance and behaviour"},
    "reg.enregistre": {"fr": "Réglages enregistrés", "en": "Settings saved"},
    "reg.enregistrer": {"fr": "Enregistrer", "en": "Save"},
    "reg.fermer": {"fr": "Fermer", "en": "Close"},
    "reg.section.raccourcis": {"fr": "Raccourcis", "en": "Shortcuts"},
    "reg.section.apparence": {"fr": "Apparence", "en": "Appearance"},
    "reg.section.comportement": {"fr": "Comportement", "en": "Behaviour"},
    "reg.section.systeme": {"fr": "Système", "en": "System"},
    "reg.maintien": {"fr": "Maintien", "en": "Hold"},
    "reg.maintien.aide": {"fr": "Maintiens la touche pendant que tu parles",
                          "en": "Hold the key while you speak"},
    "reg.bascule": {"fr": "Bascule", "en": "Toggle"},
    "reg.bascule.aide": {"fr": "Un appui démarre, un second arrête",
                         "en": "One press starts, another stops"},
    "reg.apprendre": {"fr": "Apprendre", "en": "Learn"},
    "reg.apprendre.aide": {
        "fr": "Analyse le presse-papier pour en tirer une correction",
        "en": "Reads the clipboard to derive a fix"},
    "reg.raccourcis.note": {
        "fr": "Les raccourcis prennent effet dès l'enregistrement.",
        "en": "Shortcuts take effect as soon as you save."},
    "reg.theme": {"fr": "Thème", "en": "Theme"},
    "reg.theme.auto": {"fr": "auto", "en": "auto"},
    "reg.theme.clair": {"fr": "clair", "en": "light"},
    "reg.theme.sombre": {"fr": "sombre", "en": "dark"},
    "reg.langue": {"fr": "Langue", "en": "Language"},
    "reg.langue.fr": {"fr": "français", "en": "French"},
    "reg.langue.en": {"fr": "anglais", "en": "English"},
    "reg.position": {"fr": "Position de la barre", "en": "Bar position"},
    "reg.position.bas": {"fr": "bas", "en": "bottom"},
    "reg.position.haut": {"fr": "haut", "en": "top"},
    "reg.position.curseur": {"fr": "curseur", "en": "cursor"},
    "reg.indicateur": {"fr": "Afficher la barre pendant la dictée",
                       "en": "Show the bar while dictating"},
    "reg.copier": {"fr": "Copier le texte avant de l'analyser",
                   "en": "Copy the text before reading it"},
    "reg.copier.aide": {
        "fr": "Évite d'avoir à faire Ctrl+C avant le raccourci d'apprentissage",
        "en": "Saves pressing Ctrl+C before the learning shortcut"},
    "reg.micro": {"fr": "Microphone", "en": "Microphone"},
    "reg.micro.defaut": {"fr": "Entrée par défaut du système",
                         "en": "System default input"},
    "reg.micro.aide": {
        "fr": "Choisis-en un si le système en change sans prévenir",
        "en": "Pick one if the system switches inputs behind your back"},
    "reg.presse_papier": {"fr": "Restaurer le presse-papier après une dictée",
                          "en": "Restore the clipboard after a dictation"},
    "reg.vad": {"fr": "Filtrer les silences (évite les phrases inventées)",
                "en": "Filter silence (avoids invented sentences)"},
    "reg.lexique": {"fr": "Utiliser le dictionnaire personnel",
                    "en": "Use the personal dictionary"},
    "reg.nettoyage": {"fr": "Nettoyer le texte par IA locale (plus lent)",
                      "en": "Clean up text with local AI (slower)"},
    "reg.demarrage": {"fr": "Démarrer avec Windows", "en": "Start with Windows"},
    "reg.donnees": {"fr": "Données : {chemin}", "en": "Data: {chemin}"},
    "reg.raccourci_invalide": {"fr": "Raccourci invalide",
                               "en": "Invalid shortcut"},
    "reg.reglage_invalide": {"fr": "Réglage invalide", "en": "Invalid setting"},
    "reg.demarrage.echec": {
        "fr": "Réglages enregistrés, mais le démarrage automatique n'a pas pu "
              "être modifié : {erreur}",
        "en": "Settings saved, but startup could not be changed: {erreur}"},
    "reg.raccourcis.echec": {
        "fr": "Réglages enregistrés, mais les raccourcis n'ont pas pu être "
              "appliqués :\n\n{erreur}\n\nLes précédents restent actifs.",
        "en": "Settings saved, but the shortcuts could not be applied:"
              "\n\n{erreur}\n\nThe previous ones stay active."},

    # -- pied de page ------------------------------------------------------
    "pied.maintien": {"fr": "maintien {raccourci}", "en": "hold {raccourci}"},
}

#: Formes accordees, indexees par cle : (singulier, pluriel) par langue.
NOMBRES: dict[str, dict[str, tuple[str, str]]] = {
    "mot": {"fr": ("mot", "mots"), "en": ("word", "words")},
    "dictee": {"fr": ("dictée", "dictées"),
               "en": ("dictation", "dictations")},
    "terme": {"fr": ("terme", "termes"), "en": ("term", "terms")},
    "correction": {"fr": ("correction", "corrections"),
                   "en": ("fix", "fixes")},
    "minute": {"fr": ("minute", "minutes"), "en": ("minute", "minutes")},
    "minute_gagnee": {"fr": ("minute économisée", "minutes économisées"),
                      "en": ("minute saved", "minutes saved")},
    "jour_serie": {"fr": ("jour d'affilée", "jours d'affilée"),
                   "en": ("day streak", "day streak")},
    "application": {"fr": ("application", "applications"),
                    "en": ("app used", "apps used")},
    "jour": {"fr": ("jour", "jours"), "en": ("day", "days")},
}

JOURS = {
    "fr": ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi",
           "dimanche"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
           "Sunday"),
}

MOIS = {
    "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"),
}

#: Abreviations sur trois lettres, sauf la ou elles se confondraient : juin et
#: juillet donnent tous deux « jui », ce qui rend une frise illisible.
MOIS_COURTS = {
    "fr": ("janv", "févr", "mars", "avr", "mai", "juin", "juil", "août",
           "sept", "oct", "nov", "déc"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
           "Oct", "Nov", "Dec"),
}


def normaliser(langue: str | None) -> str:
    return langue if langue in LANGUES else DEFAUT


def au_pluriel(nombre: int, langue: str) -> bool:
    """Le francais garde le singulier a zero, l'anglais non.

    « 0 dictée » et « 0 dictations » : la meme donnee, deux regles.
    """
    if normaliser(langue) == "fr":
        return abs(nombre) >= 2
    return nombre != 1


class Traducteur:
    """Donne les textes dans la langue choisie, relue a chaque appel.

    Relue et non retenue : changer de langue dans les reglages redessine la
    fenetre, et une valeur figee a la construction survivrait au changement.
    """

    def __init__(self, conf=None, langue: str | None = None):
        self._conf = conf
        self._langue = langue

    @property
    def langue(self) -> str:
        if self._langue is not None:
            return normaliser(self._langue)
        if self._conf is not None:
            return normaliser(self._conf["interface.langue"])
        return DEFAUT

    def __call__(self, cle: str, **valeurs) -> str:
        formes = TEXTES.get(cle)
        if formes is None:
            # Une cle absente vaut mieux affichee que masquee : elle se
            # remarque a l'ecran, la ou une chaine vide passerait inapercue.
            return cle
        texte = formes.get(self.langue, formes[DEFAUT])
        return texte.format(**valeurs) if valeurs else texte

    def accord(self, nombre: int, cle: str) -> str:
        """Le seul mot accorde, sans son nombre."""
        formes = NOMBRES[cle][self.langue]
        return formes[1] if au_pluriel(nombre, self.langue) else formes[0]

    def nombre(self, nombre: int, cle: str) -> str:
        """« 3 dictations », « 3 dictées »."""
        return f"{self.milliers(nombre)} {self.accord(nombre, cle)}"

    def milliers(self, nombre: int) -> str:
        """Separateur de milliers selon l'usage : espace en francais, virgule
        en anglais."""
        if self.langue == "fr":
            return f"{nombre:,}".replace(",", " ")
        return f"{nombre:,}"

    def decimal(self, valeur: float, decimales: int = 1) -> str:
        texte = f"{valeur:.{decimales}f}"
        return texte.replace(".", ",") if self.langue == "fr" else texte

    # -- dates -------------------------------------------------------------

    def jour_long(self, jour: date) -> str:
        nom = JOURS[self.langue][jour.weekday()]
        mois = MOIS[self.langue][jour.month - 1]
        if self.langue == "fr":
            return f"{nom} {jour.day} {mois}"
        return f"{nom}, {mois} {jour.day}"

    def jour_relatif(self, jour: date, aujourdhui: date | None = None) -> str:
        """Nomme les deux jours qui comptent.

        L'immense majorite des dictees consultees datent du jour meme :
        « hier » se repere d'un coup d'oeil la ou une date demande un calcul.
        """
        aujourdhui = aujourdhui or date.today()
        ecart = (aujourdhui - jour).days
        if ecart == 0:
            return self("jour.aujourdhui")
        if ecart == 1:
            return self("jour.hier")
        return self.jour_long(jour)

    def heure(self, moment) -> str:
        """« 14:13 » en francais, « 2:13 pm » en anglais.

        Ecrite a la main plutot que par `strftime` : la mise en forme des
        heures depend de la locale du processus, que ce projet ne touche pas —
        `setlocale` agit sur tout le programme et modifie au passage
        l'interpretation des nombres a virgule.
        """
        if self.langue == "fr":
            return f"{moment.hour:02d}:{moment.minute:02d}"
        matin = moment.hour < 12
        heure = moment.hour % 12 or 12
        return f"{heure}:{moment.minute:02d} {'am' if matin else 'pm'}"

    def jour_court(self, jour: date) -> str:
        return JOURS[self.langue][jour.weekday()][:2].capitalize()

    def mois_court(self, mois: int) -> str:
        return MOIS_COURTS[self.langue][mois - 1]

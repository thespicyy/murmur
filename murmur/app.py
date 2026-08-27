"""Orchestration : machine a etats et assemblage des modules.



Une dictee suit toujours le meme chemin :



    REPOS --appui--> ECOUTE --relachement--> TRANSCRIPTION --> INSERTION --> REPOS



Le traitement se fait sur un fil dedie alimente par une file. Deux dictees

simultanees n'ont aucun sens : la seconde attend que la premiere soit posee,

plutot que de s'inserer au milieu.

"""



from __future__ import annotations



import queue

import threading

import time

from dataclasses import dataclass, field

from enum import Enum

from typing import Callable



from . import (apprentissage, audio, config as configuration, guard, hotkeys,

               inject, journal, lexicon, store, stt)





class Etat(Enum):

    REPOS = "repos"

    ECOUTE = "ecoute"

    TRANSCRIPTION = "transcription"

    INSERTION = "insertion"





@dataclass

class Resultat:

    """Trace d'une dictee, pour le journal et la mesure de latence."""



    texte: str = ""

    duree_audio_ms: float = 0.0

    latence_ms: float = 0.0          # fin de parole -> texte insere

    transcription_ms: float = 0.0

    rms: float = 0.0

    cible: str = ""

    erreur: str | None = None

    rejete: str | None = None        # motif du rejet, le cas echeant

    avertissement: str | None = None  # ce qui a ete perdu au passage

    termes_corriges: tuple[str, ...] = ()  # rattrapes par le lexique



    @property

    def reussi(self) -> bool:

        return self.erreur is None and self.rejete is None and bool(self.texte)





@dataclass

class Ecouteurs:

    """Points d'accroche pour l'interface (indicateur, icone, journal)."""



    etat: list[Callable[[Etat], None]] = field(default_factory=list)

    resultat: list[Callable[[Resultat], None]] = field(default_factory=list)

    #: Recoit une Analyse quand une correction est detectee, ou None si le

    #: presse-papier ne correspondait a aucune dictee recente.

    correction: list[Callable[[object], None]] = field(default_factory=list)





class Application:

    """Assemble raccourcis, capture, moteur et insertion."""



    def __init__(self, conf: configuration.Config):

        self.conf = conf

        self.moteur = stt.Moteur(conf)

        self.enregistreur = audio.Enregistreur(conf)

        self.injecteur = inject.Injecteur(conf)

        self.garde = guard.Garde(conf)

        self.raccourcis = hotkeys.Gestionnaire()

        #: Les raccourcis ont-ils ete enregistres au moins une fois ?
        self._poses = False

        #: Le veilleur peut reprendre les raccourcis pendant que le
        #: tableau de bord les recharge : un echange a moitie fait
        #: laisserait le clavier muet.
        self._verrou_raccourcis = threading.Lock()

        self.historique = store.Historique()

        self.lexique = lexicon.Lexique()

        self.ecouteurs = Ecouteurs()



        self._etat = Etat.REPOS

        self._file: queue.Queue = queue.Queue()

        self._ouvrier: threading.Thread | None = None

        self._veilleur: threading.Thread | None = None

        self._arret = threading.Event()

        self._bascule_active = False

        self._verrou = threading.Lock()

        self._log = journal.obtenir("app")

        #: Motif du dernier echec d'apprentissage, montre a l'utilisateur.

        self.dernier_diagnostic: str | None = None

        #: Mise en pause depuis l'icone : les raccourcis restent enregistres,

        #: mais ne declenchent rien. Preferable a les desenregistrer, ce qui

        #: laisserait une autre application s'en emparer entre-temps.

        self.actif = True



    # -- etat --------------------------------------------------------------



    @property

    def etat(self) -> Etat:

        return self._etat



    def _changer_etat(self, etat: Etat) -> None:

        self._etat = etat

        for ecouteur in self.ecouteurs.etat:

            try:

                ecouteur(etat)

            except Exception:

                # Une interface defaillante ne doit jamais casser une dictee.

                self._log.exception("un ecouteur d'etat a echoue")



    def _publier(self, resultat: Resultat) -> None:

        self._journaliser(resultat)

        self._archiver(resultat)

        for ecouteur in self.ecouteurs.resultat:

            try:

                ecouteur(resultat)

            except Exception:

                self._log.exception("un ecouteur de resultat a echoue")



    def _archiver(self, resultat: Resultat) -> None:

        """Enregistre la dictee dans l'historique.



        Seules les dictees reussies y entrent : un rejet ou une erreur n'a

        rien a retrouver plus tard, et polluerait les statistiques.

        """

        if not resultat.reussi:

            return

        try:

            self.historique.ajouter(

                texte=resultat.texte,

                duree_audio_ms=resultat.duree_audio_ms,

                transcription_ms=resultat.transcription_ms,

                latence_ms=resultat.latence_ms,

                cible=resultat.cible)

        except Exception:

            # Perdre une ligne d'historique est sans gravite ; perdre la

            # dictee elle-meme ne le serait pas.

            self._log.exception("echec de l'enregistrement dans l'historique")



    def _journaliser(self, resultat: Resultat) -> None:

        if resultat.erreur:

            self._log.error("echec : %s", resultat.erreur)

        elif resultat.rejete:

            self._log.info("rejete (%s) — %.0f ms, rms %.4f",

                           resultat.rejete, resultat.duree_audio_ms,

                           resultat.rms)

        elif resultat.texte:

            self._log.info("dictee %.1f s -> %d car. | transcription %.0f ms "

                           "| latence %.0f ms | cible %s",

                           resultat.duree_audio_ms / 1000, len(resultat.texte),

                           resultat.transcription_ms, resultat.latence_ms,

                           resultat.cible or "?")

        if resultat.avertissement:

            self._log.warning(resultat.avertissement)



    # -- capture -----------------------------------------------------------



    def commencer_ecoute(self) -> None:

        with self._verrou:

            if not self.actif:

                return  # mise en pause depuis l'icone

            if self._etat is not Etat.REPOS:

                return  # une dictee est deja en cours

            try:

                self.enregistreur.demarrer()

            except audio.ErreurAudio as exc:

                self._publier(Resultat(erreur=str(exc)))

                return

            self._changer_etat(Etat.ECOUTE)



    def terminer_ecoute(self) -> None:

        with self._verrou:

            if self._etat is not Etat.ECOUTE:

                return

            capture = self.enregistreur.arreter()

            # La cible est relevee maintenant : c'est la fenetre que

            # l'utilisateur regardait en parlant, pas celle qu'il aura

            # peut-etre activee entre-temps.

            titre, executable = inject.fenetre_active()

            self._changer_etat(Etat.TRANSCRIPTION)

        self._file.put((capture, f"{executable} — {titre}".strip(" —"),

                        time.perf_counter()))



    def annuler_ecoute(self) -> bool:

        """Abandonne la dictee en cours sans rien transcrire ni inserer.



        Se raviser doit rester possible : on a commence a parler, on change

        d'avis, et rien ne doit atteindre le document. La capture est jetee

        sans jamais passer par le moteur.

        """

        with self._verrou:

            if self._etat is not Etat.ECOUTE:

                return False

            self._bascule_active = False

            capture = self.enregistreur.arreter()

            self._changer_etat(Etat.REPOS)



        self._log.info("dictee annulee (%.1f s jetees)",

                       capture.duree_ms / 1000)

        self._publier(Resultat(duree_audio_ms=capture.duree_ms,

                               rms=capture.rms, rejete="annulee"))

        return True



    @property

    def niveau_sonore(self) -> float:

        """Energie du signal capte a l'instant, pour l'affichage."""

        return self.enregistreur.rms_courant if self._etat is Etat.ECOUTE else 0.0



    def basculer(self) -> None:

        """Mode bascule : un appui demarre, le suivant arrete."""

        if self._bascule_active:

            self._bascule_active = False

            self.terminer_ecoute()

            return



        self.commencer_ecoute()

        if self._etat is not Etat.ECOUTE:

            return  # refus (pause, dictee en cours) : ne pas armer la bascule

        self._bascule_active = True

        threading.Thread(target=self._surveiller_silence, daemon=True,

                         name="silence").start()



    def _surveiller_silence(self) -> None:

        """Ferme une dictee en bascule que l'utilisateur a oublie d'arreter.



        Sans ce garde-fou, un appui malencontreux laisserait le micro ouvert

        indefiniment — jusqu'a la duree maximale de capture, soit deux minutes

        d'audio a transcrire pour rien.

        """

        seuil = self.conf["garde.rms_min"]

        limite = self.conf["raccourcis.arret_auto_silence_s"]

        silence_depuis: float | None = None



        while self._bascule_active and self._etat is Etat.ECOUTE:

            if self._arret.wait(0.1):

                return

            if self.enregistreur.rms_courant >= seuil:

                silence_depuis = None

                continue

            maintenant = time.monotonic()

            if silence_depuis is None:

                silence_depuis = maintenant

            elif maintenant - silence_depuis >= limite:

                self._log.info("bascule fermee apres %.1f s de silence", limite)

                self._bascule_active = False

                self.terminer_ecoute()

                return



    # -- apprentissage -----------------------------------------------------



    #: Valeur ecrite dans le presse-papier pour savoir si la copie a pris.

    #: Comparer au contenu precedent ne suffirait pas : recopier le meme texte

    #: ne le changerait pas.

    #: Un texte que personne ne copierait. PAS d'octet nul : le presse-papier
    #: de Windows stocke des chaines terminees par zero, un nul en tete la
    #: rendrait vide — et la sentinelle passerait pour une copie reussie.
    _SENTINELLE = "⁣murmur-sentinelle⁣"



    def _copier_le_texte_corrige(self) -> None:

        """Copie ce qui est a l'ecran avant de le lire.



        Sans cela, l'utilisateur corrige son texte **dans l'application** puis

        appuie sur le raccourci — geste naturel — et Murmur ne trouve dans le

        presse-papier que ce qu'il venait d'y ecrire pour coller la dictee. Il

        compare alors la dictee a elle-meme.



        SEULEMENT la selection, jamais « tout selectionner ».

        La tentation est grande d'envoyer Ctrl+A quand rien n'est selectionne :
        l'utilisateur n'aurait alors plus rien a faire. C'est une mauvaise
        idee, et l'essai l'a montre sur des donnees reelles.

        `SendInput` ne vise pas une fenetre : il depose la frappe dans la file
        de **celle qui a le focus**. Or Windows refuse le passage au premier
        plan a un processus qui ne l'a pas — la frappe part donc parfois
        ailleurs. Au banc d'essai, le Ctrl+A a atterri dans un autre document
        et en a copie le contenu entier, qui n'avait rien a faire ici. Un
        Ctrl+A a l'aveugle, c'est aussi tout selectionner sous les yeux de
        l'utilisateur, dans un document qu'il n'avait pas designe.

        Ctrl+C sans selection, lui, ne fait rien du tout : c'est exactement la
        prudence qu'on veut. On garde alors ce que le presse-papier contenait
        deja, et le diagnostic dira quoi faire.

        Le presse-papier est rendu si rien n'a ete copie : ce raccourci sert a
        apprendre, pas a s'approprier ce que l'utilisateur y gardait.
        """
        try:
            avant = inject.contenu_presse_papier()
        except inject.ErreurInjection:
            avant = None

        try:
            inject.ecrire_presse_papier(self._SENTINELLE)
            inject.copier_la_selection()
            if inject.lire_presse_papier() == self._SENTINELLE:
                self._log.info("rien n'etait selectionne : on garde le "
                               "presse-papier tel quel")
                self._restaurer(avant)
        except inject.ErreurInjection as exc:
            self._log.warning("copie automatique impossible : %s", exc)
            self._restaurer(avant)


    def _restaurer(self, avant) -> None:

        if avant is None:

            return

        try:

            if avant.vide:

                inject.vider_presse_papier()

            elif avant.texte is not None:

                inject.ecrire_presse_papier(avant.texte)

        except inject.ErreurInjection:

            self._log.debug("presse-papier non restaure", exc_info=True)



    def apprendre_depuis_presse_papier(self) -> object | None:

        """Compare le presse-papier aux dictees recentes et en deduit les

        corrections.



        Declenche uniquement par le raccourci dedie : Murmur ne lit jamais le

        presse-papier de sa propre initiative. Si le texte copie ne correspond

        a aucune dictee, il est oublie sur-le-champ — rien n'est conserve, ni

        en memoire ni sur disque.

        """

        if self.conf["lexique.copier_avant_analyse"]:

            self._copier_le_texte_corrige()



        try:

            copie = inject.lire_presse_papier()

        except inject.ErreurInjection as exc:

            self._log.warning("presse-papier illisible : %s", exc)

            self._publier_correction(None)

            return None



        if not copie or not copie.strip():

            self._publier_correction(None)

            return None



        recentes = self.historique.recentes(

            limite=self.conf["lexique.dictees_comparees"])

        analyse = apprentissage.meilleure_correspondance(copie, recentes)



        if analyse is None:

            # Le motif exact est transmis a l'interface : « aucune

            # correspondance » sans explication laisse sans prise.

            self.dernier_diagnostic = apprentissage.diagnostiquer(

                copie, recentes)

            self._log.info("apprentissage : %s", self.dernier_diagnostic)

        else:

            self.dernier_diagnostic = None

            self._log.info("apprentissage : %d substitution(s), %d proposee(s)",

                           len(analyse.substitutions),

                           len(analyse.propositions))

        self._publier_correction(analyse)

        return analyse



    def _publier_correction(self, analyse) -> None:

        for ecouteur in self.ecouteurs.correction:

            try:

                ecouteur(analyse)

            except Exception:

                self._log.exception("un ecouteur de correction a echoue")



    def enregistrer_correction(self, analyse, retenues) -> None:

        """Applique les substitutions validees par l'utilisateur.



        `retenues` est la liste des Substitution que l'utilisateur a acceptees

        — jamais l'ensemble des differences : corriger une tournure releve du

        style et n'a rien a faire dans le lexique.

        """

        for substitution in retenues:

            self.lexique.ajouter(substitution.apres, [substitution.avant])

        if retenues:

            self.lexique.sauvegarder()



        # Le corpus garde la correction entiere, meme les parties non

        # retenues : c'est la matiere de l'apprentissage a venir.

        try:

            self.historique.ajouter_correction(

                analyse.texte_origine, analyse.texte_corrige,

                dictee_id=analyse.dictee_id)

        except Exception:

            self._log.exception("echec de l'enregistrement de la correction")



    # -- traitement --------------------------------------------------------



    def _travailler(self) -> None:

        while not self._arret.is_set():

            try:

                element = self._file.get(timeout=0.2)

            except queue.Empty:

                continue

            if element is None:

                break

            try:

                self._traiter(*element)

            except Exception:

                # _traiter capture deja tout ; ce filet couvre l'imprevu au

                # niveau de la boucle. L'ouvrier ne doit jamais mourir : s'il

                # s'arretait, l'application semblerait vivante mais aucune

                # dictee ne serait plus traitee.

                self._log.exception("erreur non geree dans l'ouvrier")

            finally:

                self._file.task_done()



    def _traiter(self, capture: audio.Capture, cible: str, depart: float) -> None:

        resultat = Resultat(duree_audio_ms=capture.duree_ms, rms=capture.rms,

                            cible=cible)

        try:

            # En amont : un appui accidentel ne doit meme pas atteindre le

            # moteur — c'est gratuit et cela evite un aller-retour inutile.

            amont = self.garde.controler_capture(capture)

            if not amont.accepte:

                resultat.rejete = amont.motif

                return



            # Le lexique agit en amont, sur le decodage lui-meme : 5/10 termes

            # de jargon corrects sans prompt, 8/10 avec (mesure T0.2).

            prompt = (self.lexique.prompt()

                      if self.conf["lexique.actif"] else None)



            debut = time.perf_counter()

            texte = self.moteur.transcrire(capture.wav, prompt=prompt)

            resultat.transcription_ms = (time.perf_counter() - debut) * 1000



            # En aval : dernier filet contre les hallucinations connues.

            aval = self.garde.controler_texte(texte)

            if not aval.accepte:

                resultat.rejete = aval.motif

                return



            # Puis la table de remplacement, qui rattrape ce que le prompt ne

            # corrige pas — et ce qu'il degrade, le conditionnement n'etant

            # pas monotone.

            if self.conf["lexique.actif"]:

                texte, corriges = self.lexique.corriger(texte)

                if corriges:

                    resultat.termes_corriges = tuple(corriges)



            resultat.texte = texte

            self._changer_etat(Etat.INSERTION)

            avant_injection = time.perf_counter()

            injection = self.injecteur.injecter(texte)

            resultat.avertissement = injection.avertissement

            # La latence s'arrete a l'arrivee du texte : la restauration du

            # presse-papier se produit apres, et n'est pas percue.

            resultat.latence_ms = ((avant_injection - depart) * 1000

                                   + injection.duree_pose_ms)



        except (stt.ErreurMoteur, inject.ErreurInjection) as exc:

            resultat.erreur = str(exc)

        except Exception as exc:  # un imprevu ne doit pas tuer l'ouvrier

            resultat.erreur = f"{type(exc).__name__} : {exc}"

        finally:

            self._changer_etat(Etat.REPOS)

            self._publier(resultat)



    # -- cycle de vie ------------------------------------------------------



    def _verifier_les_raccourcis(self) -> None:
        """Reprend les raccourcis si le fil qui les portait a disparu.

        Windows lie une combinaison au fil qui l'enregistre : quand ce fil
        s'arrete, elle est rendue au systeme. L'application continue alors de
        tourner, icone comprise, en ne repondant plus au clavier — panne
        silencieuse, et deroutante : tout a l'air normal.

        La cause premiere est traitee dans `hotkeys` (un rappel qui leve
        n'emporte plus la boucle). Ceci est le filet : quelle que soit la
        raison de la disparition, le clavier revient au tour suivant.
        """
        # `_poses` distingue « le fil est tombe » de « il n'a pas encore
        # demarre » : le veilleur est lance avant les raccourcis, et son
        # premier tour ne doit pas les reprendre a leur propre demarrage.
        if not self._poses or self.raccourcis.en_cours:
            return
        with self._verrou_raccourcis:
            if not self._poses or self.raccourcis.en_cours:
                return  # repris entre-temps par un autre fil
            self._reprendre_les_raccourcis()

    def _reprendre_les_raccourcis(self) -> None:
        self._log.error("les raccourcis ne sont plus ecoutes : reprise")
        repris = hotkeys.Gestionnaire()
        self._declarer_raccourcis(repris)
        try:
            repris.demarrer()
        except hotkeys.ErreurRaccourci:
            # Combinaison prise entre-temps par une autre application. On
            # reessaiera au tour suivant ; surtout, on ne remonte pas
            # l'exception : le veilleur a aussi un moteur a surveiller.
            self._log.warning("reprise des raccourcis impossible pour "
                              "l'instant")
            return
        self.raccourcis = repris
        self._log.info("raccourcis repris : %s",
                       ", ".join(f"{n} = {c}"
                                 for n, c in self._combinaisons().items()))

    def _surveiller(self) -> None:

        """Relance le moteur s'il tombe, sans attendre la prochaine dictee.



        Sans cette surveillance, la panne ne serait decouverte qu'au moment de

        dicter : l'utilisateur paierait le rechargement du modele en pleine

        latence, ou perdrait sa dictee si le plafond etait atteint.

        """

        periode = self.conf["moteur.surveillance_s"]

        prevenu = False

        panne_signalee = False

        while not self._arret.wait(periode):

            try:

                self._verifier_les_raccourcis()

                if self.moteur.est_vivant():

                    prevenu = False

                    panne_signalee = False

                    continue

                if self.moteur.assurer_disponibilite():

                    self._log.warning("moteur tombe, relance automatique")

                    self._publier(Resultat(

                        avertissement="le moteur est tombe et a ete relance"))

                    prevenu = False

                elif not prevenu:

                    prevenu = True  # ne pas repeter l'alerte a chaque tour

                    self._publier(Resultat(

                        erreur="le moteur est tombe et ne redemarre plus. "

                               "Consulte le journal moteur.log."))

            except Exception:

                # Le veilleur doit survivre a tout : c'est lui qui rattrape

                # les pannes, il ne peut pas en etre la premiere victime.

                #

                # Une seule trace complete par serie : une panne persistante

                # ferait sinon ecrire un traceback a chaque tour, inondant le

                # journal — et formater des tracebacks en boucle depuis un fil

                # secondaire suffit a faire tomber l'interpreteur.

                if not panne_signalee:

                    panne_signalee = True

                    self._log.exception("erreur dans la surveillance du moteur")



    def demarrer(self) -> None:

        self.moteur.demarrer()



        self._arret.clear()

        self._ouvrier = threading.Thread(target=self._travailler, daemon=True,

                                         name="traitement")

        self._ouvrier.start()

        self._veilleur = threading.Thread(target=self._surveiller, daemon=True,

                                          name="surveillance")

        self._veilleur.start()



        self._declarer_raccourcis(self.raccourcis)

        self.raccourcis.demarrer()

        self._poses = True



    def _combinaisons(self) -> dict[str, str]:

        """Combinaisons en vigueur, telles que la configuration les decrit."""

        combinaisons = {

            "dictee (maintien)": self.conf["raccourcis.maintien"],

            "dictee (bascule)": self.conf["raccourcis.bascule"],

        }

        if self.conf["lexique.actif"]:

            combinaisons["apprendre"] = self.conf["raccourcis.apprendre"]

        return combinaisons



    def _declarer_raccourcis(self, gestionnaire: hotkeys.Gestionnaire,

                             combinaisons: dict[str, str] | None = None) -> None:

        """Declare les raccourcis sur un gestionnaire neuf.



        Les combinaisons sont passees explicitement plutot que relues dans la

        configuration : lors d'un repli, celle-ci contient deja les valeurs

        fautives, et le gestionnaire de secours echouerait pour la meme raison

        que celui qu'il remplace.

        """

        combinaisons = combinaisons or self._combinaisons()

        rappels = {

            "dictee (maintien)": dict(maintien=True,

                                      debut=self.commencer_ecoute,

                                      fin=self.terminer_ecoute),

            "dictee (bascule)": dict(debut=self.basculer),

            "apprendre": dict(debut=self._apprendre_en_arriere_plan),

        }

        for nom, combinaison in combinaisons.items():

            gestionnaire.ajouter(nom, combinaison, **rappels[nom])



    def recharger_lexique(self) -> None:

        """Reprend le dictionnaire depuis le disque.



        Un terme ajoute depuis le tableau de bord change le prompt envoye au

        moteur : sans cette relecture, il ne servirait qu'au prochain

        lancement.

        """

        self.lexique = lexicon.Lexique()

        self._log.info("lexique recharge (%d termes)", len(self.lexique))



    def recharger_raccourcis(self) -> None:

        """Applique les raccourcis de la configuration sans redemarrer.



        Windows lie une combinaison au fil qui l'a enregistree : on ne peut

        pas la modifier, seulement rendre l'ancienne et en prendre une

        nouvelle. L'ordre compte — liberer d'abord, sinon reprendre une

        combinaison inchangee echouerait contre elle-meme.



        En cas d'echec (combinaison prise par une autre application), l'ancien

        jeu est remis en place : mieux vaut des raccourcis obsoletes que plus

        de raccourcis du tout.

        """

        anciennes = {nom: r.combinaison

                     for r in self.raccourcis._raccourcis.values()

                     for nom in [r.nom]}



        nouveau = hotkeys.Gestionnaire()

        self._declarer_raccourcis(nouveau)

        with self._verrou_raccourcis:
            self._echanger(nouveau, anciennes)

    def _echanger(self, nouveau, anciennes: dict[str, str]) -> None:

        self.raccourcis.arreter()

        try:

            nouveau.demarrer()

        except hotkeys.ErreurRaccourci:

            secours = hotkeys.Gestionnaire()

            self._declarer_raccourcis(secours, anciennes)

            try:

                secours.demarrer()

                self.raccourcis = secours

                self._log.warning("raccourcis precedents retablis")

            except hotkeys.ErreurRaccourci:

                self._log.exception("plus aucun raccourci actif")

            raise



        self.raccourcis = nouveau

        self._log.info("raccourcis recharges : %s",

                       ", ".join(f"{n} = {c}"

                                 for n, c in self._combinaisons().items()))



    def _apprendre_en_arriere_plan(self) -> None:

        """L'analyse ne doit pas bloquer la boucle de messages des raccourcis."""

        threading.Thread(target=self.apprendre_depuis_presse_papier,

                         daemon=True, name="apprentissage").start()



    def arreter(self) -> None:

        self._poses = False

        self.raccourcis.arreter()

        if self.enregistreur.en_cours:

            self.enregistreur.arreter()

        self._arret.set()

        self._file.put(None)

        for fil in ("_ouvrier", "_veilleur"):

            thread = getattr(self, fil)

            if thread is not None:

                thread.join(timeout=3.0)

                setattr(self, fil, None)

        self.moteur.arreter()

        try:

            self.historique.fermer()

        except Exception:

            self._log.exception("echec de la fermeture de l'historique")



    def __enter__(self) -> Application:

        self.demarrer()

        return self



    def __exit__(self, *_) -> None:

        self.arreter()


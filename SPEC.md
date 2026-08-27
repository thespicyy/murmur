# SPEC — Murmur

> Dictée vocale locale, instantanée et privée, partout dans Windows.
> Statut : **à valider**. « Murmur » est un nom de travail.
> Étape suivante une fois validée : PLAN (le comment technique), puis TÂCHES.

---

## 1. Le problème

Taper est plus lent que parler. On parle à environ 150 mots par minute, on tape à 40.
Pour tout ce qui relève de la prose — messages, notes, prompts, commentaires, mails —
la frappe est le goulot d'étranglement.

Les solutions existantes, Wispr Flow en tête, résolvent bien le problème mais posent
trois conditions : un abonnement mensuel, une connexion internet, et l'envoi de tout
ce qu'on dicte sur un serveur tiers. Ce dernier point disqualifie l'outil pour tout
contenu sensible — clés, notes personnelles, code client.

La dictée intégrée à Windows est gratuite, mais trop imprécise pour un usage soutenu
et incapable d'apprendre le moindre vocabulaire spécialisé.

## 2. L'objectif

Une application de dictée atteignant la qualité de Wispr Flow, fonctionnant
**entièrement en local**, sans abonnement ni réseau, et qui **s'améliore avec l'usage**
en apprenant le vocabulaire propre à son utilisateur.

Le bench préliminaire a validé la faisabilité : 11 secondes de parole transcrites en
environ 250 ms sur la machine cible, avec le modèle le plus précis disponible.
La performance n'est donc pas le risque de ce projet. L'intégration à l'OS l'est.

## 3. Utilisateur et usages

Un utilisateur unique, sur son poste personnel. Pas de multi-compte, pas de partage,
pas de synchronisation.

Situations visées :

- rédiger un message long dans Discord, Slack ou un mail ;
- écrire un prompt détaillé pour un agent IA ;
- prendre une note dans un bloc-notes ;
- dicter un commentaire ou un message de commit dans l'éditeur de code.

Ces contextes ont des vocabulaires distincts. C'est une donnée du problème, pas un détail.

## 4. Périmètre fonctionnel

### V1 — le socle indispensable

| # | Fonctionnalité | Pourquoi |
|---|---|---|
| F1 | Deux raccourcis globaux : un en maintien, un en bascule | Le maintien pour les dictées courtes sans risque d'oubli, la bascule pour les prompts longs |
| F2 | Insertion du texte là où se trouve le curseur, dans n'importe quelle application | C'est le geste complet : parler, puis voir le texte apparaître |
| F3 | Service résident, lancé avec Windows, discret en zone de notification | Le modèle doit rester chargé, sinon on paie 800 ms à chaque dictée |
| F4 | Retour visuel non intrusif de l'état : repos, écoute, transcription | Savoir si ça écoute, sans voler le focus |
| F5 | Transcription française, langue forcée, hors ligne, sur GPU | Le cœur. Forcer la langue supprime toute erreur de détection |
| F6 | Lexique personnel : liste de termes que le modèle doit reconnaître | Le jargon technique est massacré par défaut |
| F7 | Annulation en cours de dictée | Se raviser sans polluer le document |

### V2 — ce qui fait la différence

| # | Fonctionnalité | Pourquoi |
|---|---|---|
| F8 | Nettoyage optionnel par IA locale : hésitations, répétitions, ponctuation | Passer du verbatim à de l'écrit. **Désactivable**, car il coûte de la latence |
| F9 | Apprentissage par correction : corriger une dictée enrichit le lexique | L'outil progresse par l'usage plutôt que par configuration manuelle |
| F10 | Apprentissage passif : les termes récurrents absents du dictionnaire courant rejoignent le lexique | Zéro effort de l'utilisateur |
| F11 | Contexte applicatif : lexique et ton adaptés à l'application active | Le vocabulaire de l'éditeur de code n'est pas celui d'un mail |
| F12 | Apprentissage du style d'écriture à partir des corrections passées | La vraie personnalisation : pas la voix, la plume |
| F13 | Historique consultable des dictées | Récupérer un texte perdu, et alimenter l'apprentissage |

### Hors périmètre — décidé, pas oublié

- **Adaptation acoustique à la voix (fine-tuning).** Coût élevé, gain marginal pour une
  voix francophone standard sur un bon micro. Les corrections sont néanmoins journalisées
  dès le premier jour : si le besoin apparaît, le corpus existera. Décision réversible.
- **Commandes vocales** (« nouvelle ligne », « supprime ça », pilotage de l'OS à la voix).
  Un autre produit, un autre problème.
- **Transcription de fichiers audio ou de réunions.** L'outil sert la dictée temps réel,
  pas le traitement par lot.
- **Identification de locuteurs, gestion de plusieurs voix.**
- **Mobile, cloud, synchronisation, multi-utilisateur.**

## 5. Contraintes

**Absolues**

- Fonctionnement hors ligne intégral. Aucune donnée ne quitte la machine, jamais.
- Zéro coût récurrent : aucun abonnement, aucune clé d'API.
- Le service tourne en permanence ; son inactivité doit être invisible, sans
  consommation GPU ni ventilateur au repos.

**Techniques — issues du bench, déjà validées**

- Windows 11, GPU AMD piloté via Vulkan.
- Modèle résident en VRAM, budget cible sous 2 Go.
- Aucun chemin absolu codé en dur : l'application doit survivre à un changement de
  disque ou de machine.

**Expérience**

- Latence perçue sous 500 ms entre la fin de la parole et l'apparition du texte.
- Ne jamais voler le focus de la fenêtre active.
- Un conflit de raccourci clavier doit être détecté et signalé, pas subi.

## 6. Critères de succès

Le projet est réussi si, après une semaine d'usage réel :

1. La latence médiane reste sous 400 ms pour une dictée de 10 secondes, et sous
   800 ms dans 95 % des cas.
2. L'insertion de texte est fiable dans au moins cinq applications de familles
   différentes : un navigateur, un éditeur de code, une application Electron,
   un terminal, une application Win32 classique.
3. Après apprentissage, dix termes de jargon choisis à l'avance sont transcrits
   correctement alors qu'ils échouaient à l'état initial.
4. Aucun plantage ni fuite mémoire sur sept jours de service continu.
5. **Le test qui compte vraiment** : l'outil est utilisé spontanément à la place du
   clavier, pour au moins un message long par jour. Un outil de dictée qu'on oublie
   d'utiliser a échoué, quels que soient ses chiffres.

## 7. Risques identifiés

| Risque | Gravité | Nature |
|---|---|---|
| L'insertion de texte échoue dans certaines applications : terminaux, jeux, interfaces à rendu personnalisé | **Élevée** | Le risque principal du projet. La transcription est un problème résolu ; l'intégration à l'OS ne l'est pas |
| Whisper hallucine du texte sur du silence ou du bruit de fond | Élevée | Défaut documenté du modèle. Une dictée déclenchée par erreur doit ne rien produire, jamais une phrase inventée |
| La latence du nettoyage IA détruit la fluidité | Moyenne | D'où son caractère optionnel et désactivable |
| Le raccourci global entre en conflit avec une autre application | Moyenne | Fréquent sur un poste chargé |
| L'apprentissage automatique du lexique dérive et injecte du bruit | Moyenne | Un lexique auto-alimenté peut se dégrader ; il faudra pouvoir l'inspecter et le corriger à la main |

## 8. Décisions arrêtées

Les quatre questions ouvertes ont été tranchées. Elles sont désormais des contraintes
de conception, pas des options.

| Sujet | Décision | Conséquence |
|---|---|---|
| **Activation** | Deux raccourcis distincts : maintien et bascule | Couvre le message court et le prompt long. Le mode bascule impose un garde-fou : arrêt automatique après un silence prolongé, sinon le micro reste ouvert |
| **Langue** | Français uniquement, langue forcée | Supprime toute erreur de détection et simplifie le nettoyage IA. L'anglais reste au clavier ; un second raccourci pourra l'ajouter plus tard sans refonte |
| **Affichage** | Texte inséré d'un seul bloc à la fin | Le seul mode compatible avec le nettoyage IA, qui a besoin de la phrase entière. À 250 ms de latence, l'écart perçu avec le temps réel est négligeable |
| **Nom** | Murmur | Retenu |

### Ce qui reste à trancher au moment du PLAN

Ces points sont techniques et relèvent du **comment**. Ils n'appartiennent pas à la
spec, mais sont listés ici pour ne pas être perdus :

- Quel mécanisme d'insertion de texte, et quelle stratégie de repli quand
  l'application cible le refuse.
- Comment distinguer une vraie dictée d'un déclenchement accidentel, pour
  neutraliser les hallucinations sur silence.
- Où stocker lexique, historique et corrections, et sous quel format inspectable.

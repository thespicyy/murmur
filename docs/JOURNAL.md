# SUIVI — Murmur

Dictée vocale locale, instantanée et privée, partout dans Windows.
Alternative gratuite et hors ligne à Wispr Flow, qui apprend le vocabulaire de son
utilisateur avec l'usage.

- Spécification : [SPEC.md](SPEC.md)
- Journal d'incidents du bench : [../WhisperBench/logs/ERREURS.md](../WhisperBench/logs/ERREURS.md)

---

## Objectif

Remplacer le clavier par la voix pour tout ce qui relève de la prose — messages,
prompts, notes, commentaires — sans abonnement, sans réseau, et sans qu'aucune donnée
dictée ne quitte la machine.

## Stack technique

Validée par le bench :

| Brique | Choix | État |
|---|---|---|
| Transcription | whisper.cpp v1.9.2, modèle `large-v3-turbo-q5_0` (574 Mo) | ✅ compilé et mesuré |
| Accélération | Backend Vulkan sur Radeon RX 9070 XT | ✅ 10-15× plus rapide que le CPU |
| Toolchain de build | Vulkan SDK 1.4.357 + MSVC BuildTools 2022 + CMake 4.4.2 | ✅ installée |
| Nettoyage IA (optionnel, V2) | Ollama, déjà présent sur la machine | ⏳ non abordé |

Reste à décider au PLAN : langage et framework de l'application, mécanisme
d'injection de texte, format de stockage du lexique.

## Décisions de conception

| Sujet | Décision |
|---|---|
| Activation | Deux raccourcis globaux : un en maintien, un en bascule |
| Langue | Français uniquement, langue forcée |
| Affichage | Texte inséré d'un seul bloc en fin de dictée |
| Architecture | Service résident — le modèle reste chargé en VRAM |

## Performances mesurées

Bench du 19/08/2026, Ryzen 7 9700X + RX 9070 XT, modèle `large-v3-turbo-q5_0`.

| Échantillon | Vulkan | CPU | Gain |
|---|---|---|---|
| 11 s | 1 025 ms | 10 946 ms | 10,7× |
| 55 s | 1 495 ms | 22 690 ms | 15,2× |

Ces chiffres incluent 804 ms de chargement du modèle à chaque lancement.
**Modèle résident, la latence réelle par dictée tombe à environ 250 ms pour
11 secondes de parole** — c'est la métrique qui compte, et elle est meilleure que
celle de Wispr Flow (~1 s).

Enseignement principal : le CPU seul plafonne à 1,0-2,4× le temps réel, soit
11 secondes d'attente pour 11 secondes de dictée. Le GPU n'est pas un confort ici,
c'est la condition de viabilité du projet.

## État d'avancement

| Étape | État |
|---|---|
| Bench de faisabilité GPU | ✅ terminé le 19/08/2026 |
| Spécification | ✅ validée le 19/08/2026 |
| Plan technique | ✅ rédigé le 19/08/2026 — [PLAN.md](PLAN.md), à valider |
| Découpe en tâches | ✅ validée le 19/08/2026 — [TACHES.md](TACHES.md), 25 tâches V1 |
| **J0 · T0.1** injection de texte | ✅ 19/08/2026 — presse-papier **5/5 applications intactes**. Frappe Unicode viable mais à 16 ms/caractère : reléguée en dernier recours |
| **J0 · T0.2** lexique | ✅ 19/08/2026 — prompt validé : **5/10 → 8/10** termes corrects. Non monotone : `Grafana` dégradé par le prompt |
| **J0 · T0.3** VAD | ✅ 19/08/2026 — hallucinations confirmées **3/3** sans protection, **0/3** avec `--vad` + `--suppress-nst` |
| **J0 · T0.4** consolidation | ✅ 19/08/2026 — **J0 terminé, plan confirmé, aucune révision nécessaire** |
| **J1 · T1.1** squelette | ✅ 19/08/2026 — paquet, venv, `config.py`. **27 tests**, dont un qui interdit les chemins absolus dans tout le code |
| **J1 · T1.2** moteur | ✅ 19/08/2026 — `engine/` (603 Mo) + `stt.py`. **15 tests**, dont 5 démarrant le vrai moteur |
| **J1 · T1.3** capture audio | ✅ 19/08/2026 — `audio.py`, fonctions pures séparées du matériel. **24 tests** |
| **J1 · T1.4** raccourcis | ✅ 19/08/2026 — `hotkeys.py`, sans hook clavier. **21 tests** |
| **J1 · T1.5** injection | ✅ 19/08/2026 — `inject.py`, portage du spike validé. **22 tests** |
| **J1 · T1.6** assemblage | ✅ 19/08/2026 — `app.py` + `__main__.py`. **18 tests** |
| **J1 — jalon complet** | ✅ **dictée réelle validée le 19/08/2026, latence mesurée 380 ms** |
| **J2 · T2.3** presse-papier | ✅ 19/08/2026 — sauvegarde, restauration temporisée, avertissement sur contenu non restaurable. **16 tests** |
| **J2 · T2.1** garde | ✅ 19/08/2026 — `guard.py`, rejet en amont (durée, RMS) et liste noire en aval. **19 tests** |
| **J2 · T2.2** VAD | ✅ 19/08/2026 — seuils exposés, T0.3 rejoué à travers les modules. **7 tests**, contre-épreuve incluse |
| **J2 · T2.4** résilience moteur | ✅ 19/08/2026 — relance automatique plafonnée + fil de surveillance. **11 tests** |
| **J2 · T2.5** journalisation | ✅ 19/08/2026 — `journal.py` rotatif, survie à toute panne de composant. **9 tests** |
| **J2 — jalon complet** | ✅ 19/08/2026 — **194 tests** |
| **J3 · T3.1** indicateur | ✅ 19/08/2026 — pastille d'état non focusable, thème clair/sombre |
| **J3 · T3.2** icône | ✅ 19/08/2026 — `tray.py`, icône dessinée selon l'état, menu, mise en pause |
| **J3 · T3.4** arrêt auto | ✅ 19/08/2026 — le mode bascule se ferme seul après un silence prolongé |
| **J3 · T3.6** intégration | ✅ 19/08/2026 — instance unique par verrou de port, démarrage avec Windows |
| **J3 · T3.5** historique | ✅ 19/08/2026 — `store.py`, SQLite, statistiques, corpus de corrections. **23 tests** |
| **J3 · T3.3** fenêtre principale | ✅ 19/08/2026 — `fenetre.py` : dictées, statistiques, réglages. **15 tests** |
| **J3 — jalon complet** | ✅ 19/08/2026 — **264 tests** |
| **J4 · T4.1/T4.2** lexique | ✅ 20/08/2026 — `lexicon.py` : prompt priorisé + table de remplacement. **28 tests** |
| **J4 · T4.5** apprentissage | ✅ 20/08/2026 — `apprentissage.py`, déclenché par raccourci. **31 tests** |
| **J4 · T4.3** page Dictionnaire | ✅ 20/08/2026 — ajout, retrait, validation des corrections détectées |
| **J4 · T4.1b** non-régression | ✅ 20/08/2026 — l'échantillon réel est rejoué, contre-épreuve incluse |
| **J4 · T4.4** validation | ✅ 20/08/2026 — **10/10 termes reconnus** |
| **Identité visuelle** | ✅ 20/08/2026 — symbole Murmur intégré partout. **26 tests** |
| **Exécutable** | ✅ 20/08/2026 — `Murmur.exe` (34 Mo), sans console, icône intégrée |
| **V1 — COMPLÈTE** | ✅ 20/08/2026 — **396 tests** |
| **Raccourcis à chaud** | ✅ 21/08/2026 — un raccourci modifié prend effet à l'enregistrement, avec repli sur l'ancien jeu en cas de conflit. **7 tests** |
| **Refonte de l'interface** | ✅ 21/08/2026 — barre latérale à pictogrammes, réglages en fenêtre séparée, palette de Notes, histogramme d'activité. **496 tests** |
| **Interface arrondie** | ✅ 21/08/2026 — coins arrondis partout, barre de titre teintée par Windows, graphe redessiné, liste paginée. **527 tests** |
| **Panneau, volet, KPI** | ✅ 21/08/2026 — panneau central détouré, barre latérale repliable, cases à cocher dessinées, page Statistiques enrichie (applications, corrections, calendrier). **544 tests** |
| **Fenêtre sans bandeau** | ✅ 21/08/2026 — barre de titre dessinée par l'application, palette Wispr, emoji d'usage en couleur, affichage d'un bloc. **570 tests** |
| **Mise à l'échelle** | ✅ 21/08/2026 — proportions relevées sur Wispr Flow, jauge centrée, calendrier à sept jours, démarrage avec Windows. **573 tests** |
| **Anglais et finitions** | ✅ 21/08/2026 — interface traduite avec choix de la langue, pictogrammes au trait, quatre défauts reproduits puis corrigés. **574 tests** |
| **Repli animé** | ✅ 21/08/2026 — barre latérale qui glisse, symbole lissé, ordre des dictées d'une même seconde, cartes d'usage agrandies. **579 tests** |
| **Portage WebView2 — fondation** | 🚧 23/08/2026 — canal de commande, couche de données, processus séparé, page Insights. **623 tests** ; la fenêtre ne s'ouvre pas encore depuis mes lancements |

### Exécutable

`.venv\Scripts\python.exe construire.py` produit `dist/Murmur.exe`, crée la jonction
vers le moteur et pose le raccourci du menu Démarrer. Le moteur (600 Mo) **n'est pas
embarqué** : PyInstaller le réextrairait à chaque lancement, et le modèle se remplace
sans reconstruire l'application. `--copier` produit un dossier autonome, déplaçable sur
une autre machine ; `--sans-raccourci` saute l'entrée du menu.

Le raccourci vise le menu de **l'utilisateur courant**, jamais celui de la machine :
écrire dans `%ProgramData%` demanderait des droits administrateur pour une entrée qui
ne concerne qu'une personne. Windows 11 ne permettant plus d'épingler à la barre des
tâches par programme, l'épinglage reste une action volontaire depuis le menu.

**L'empaquetage a révélé un défaut de fond, invisible en mode source** :
`CreateJobObjectW` était appelé sans `restype`, donc ctypes tronquait le handle du job
à 32 bits. Le défaut ne se voit qu'une fois les handles au-delà de 2³¹ — ce qui arrive
dans un exécutable. On manipulait alors un handle qui ne désignait plus le job, et le
fermer **tuait le moteur au lieu de le protéger**. Trois autres suppositions sont
tombées au passage : `sys.stderr` vaut `None` sans console, les imports relatifs
exigent un point d'entrée dédié, et `__file__` ne désigne plus le projet. Détail dans
[logs/ERREURS.md](logs/ERREURS.md).

### Rendu de la barre — pourquoi elle ne passe pas par Tkinter

Signalé en usage réel : la barre paraissait pixelisée. Le logo n'était pas en cause —
**le canevas de Tk ne fait aucun anticrénelage**, et sortait chaque cercle, arc et
courbe en escalier. Aucun redessin du symbole n'y aurait changé quoi que ce soit.

[`rendu.py`](murmur/rendu.py) dessine désormais la barre avec Pillow, **à quatre fois
la taille finale puis réduite** : chaque pixel du résultat est la moyenne de seize.

L'affichage a suivi. L'attribut `-transparentcolor` de Tk fonctionne par couleur-clé,
sans demi-teinte : les bords adoucis se seraient mis à baver en halos colorés,
annulant le bénéfice. La barre est donc peinte par GDI en **fenêtre à couches**
(`UpdateLayeredWindow`), seule voie offrant une transparence par pixel. Les composantes
doivent y être **prémultipliées par l'alpha**, faute de quoi les bords se cernent d'un
halo clair.

### Barre de dictée

**130 × 28 px** : un disque portant le symbole, puis une pilule avec le bouton
**annuler**, le vumètre qui suit la voix, et le bouton **valider**. Les boutons
fonctionnent malgré `WS_EX_NOACTIVATE` — ce style empêche la prise de focus, pas les
clics.

La première version faisait 258 × 56, soit **quatre fois cette surface**. Le point
central du symbole porte l'état — vert à l'écoute, ambre en transcription — tandis que
le vumètre reste blanc pour ne rendre compte que du niveau sonore.

Pendant la transcription le micro est arrêté, donc sans niveau à suivre : le vumètre
s'anime alors à intensité fixe. Une barre figée juste au moment où l'utilisateur attend
son texte donnerait l'impression que rien ne se passe.

Toutes les proportions sont exprimées en fraction de la hauteur : changer la taille ne
demande de toucher qu'à une constante. Les exprimer en pixels obligeait à recalculer
une dizaine de valeurs à chaque essai, et laissait des glyphes disproportionnés dès
qu'on en oubliait une.

`annuler_ecoute()` jette la capture sans jamais la soumettre au moteur : se raviser
doit rester possible, et rien ne doit alors atteindre le document.

L'icône de la zone de notification est passée en **symbole blanc sur pastille noire**.
Un tracé transparent se perdait sur une barre des tâches sombre ; un fond constant
garde son contraste quel que soit le thème. L'état reste lisible par la couleur du
point central.

### Correction : recherche ligne par ligne

Signalé en usage réel : « le texte copié ne correspond à aucune dictée », alors que la
correction était bien présente. La cause n'était pas le seuil de similarité mais le
**périmètre de comparaison** — `Ctrl+A` copie tout le document, et une dictée d'une
ligne se noie dans l'ensemble.

`meilleure_correspondance()` confronte désormais chaque dictée au texte entier, à
chaque ligne, puis à chaque paragraphe. Le texte autour ne gêne plus. Et quand rien ne
correspond vraiment, `diagnostiquer()` en donne le motif — base vide, texte identique,
ou ressemblance chiffrée — plutôt qu'un refus sans explication.

### Identité visuelle

Le symbole — un point d'où rayonnent deux arcs — est **redessiné** par
[`murmur/marque.py`](murmur/marque.py) plutôt que chargé depuis une image : il doit
suivre la couleur de l'état (repos, écoute, transcription, insertion) **et** celle du
thème, ce qui exigerait autrement une image par combinaison. Les SVG d'origine sont
conservés dans [`assets/`](assets/) comme référence de géométrie.

Trois points appris en l'intégrant :

- **La déclinaison compacte du kit sert vraiment.** À 16 px, taille réelle dans la
  barre des tâches, les deux arcs fins se confondent en une tache. La variante à un
  seul arc, trait épais, reste lisible.
- **Le tracé demande un recentrage optique.** Les arcs occupent la gauche et rien à
  droite : le point est au centre géométrique, mais l'ensemble paraît décalé. Vérifié
  en mesurant l'étendue réelle sur l'image rendue, pas seulement la géométrie théorique.
- **Pillow épaissit les arcs vers l'intérieur du rayon**, pas de part et d'autre.
  Ajouter une demi-épaisseur au calcul surcorrigeait de plusieurs pixels — écart
  invisible en théorie, mesurable à l'image.

L'état suspendu retire les arcs et ne garde que le point : plus d'ondes, donc plus
d'écoute. Un symbole inchangé laisserait croire l'application active.

### Mesure finale du lexique

Sur l'enregistrement de référence (voix réelle, dix termes de jargon) :

| Étape | Termes reconnus |
|---|---|
| Sans aide | 6/10 |
| Prompt de conditionnement seul | 8/10 |
| Prompt + table de remplacement | **10/10** |

La table rattrape précisément les deux noms propres que le prompt seul
ne suffisait pas à faire écrire — ce qui confirme que les deux mécanismes sont complémentaires et non
redondants. Le critère de succès n°3 de la spec est atteint.

### Apprentissage par correction

Déclenché **uniquement** par `Ctrl+Alt+C` : Murmur ne lit jamais le presse-papier de
sa propre initiative. Écouter en continu reviendrait à lire tout ce que l'utilisateur
copie, mots de passe compris, dans un outil dont la confidentialité est l'argument
central.

Le tri entre correction de vocabulaire et reformulation de style repose sur **la
majuscule**, mesurée comme bien plus discriminante que la seule similarité : sur un
échantillon réel, dix des onze vrais termes en portent une, aucune des dix
reformulations. Sans majuscule, une ressemblance nettement plus forte est exigée — ce
qui laisse passer un mot composé recollé (0,84) tout en écartant
`dire`/`lire` (0,75).

Rien n'est jamais appris sans validation explicite, terme par terme.

**268 tests**, stables sur 4 exécutions consécutives.
Lancement : `lancer.bat` (sans console) ou `lancer_console.bat` (diagnostic).

**La fenêtre se rafraîchit en direct** (corrigé le 20/08/2026) : il fallait auparavant
la fermer et la rouvrir pour voir sa dernière dictée. Les pages Dictées et
Statistiques se redessinent à chaque dictée réussie ; la page Réglages en est
**volontairement exclue**, car la redessiner effacerait une saisie en cours.

### Deux garde-fous ajoutés aux tests

Un test qui laisse une ressource derrière lui produit une défaillance loin de sa
cause. Deux fixtures y remédient : l'une échoue si un fil de Murmur survit à un test,
l'autre si un moteur reste en vie après un test marqué « lent ». Toutes deux nomment
le test coupable, là où le symptôme n'apparaissait auparavant qu'en fin de session.

### Thème

Deux palettes complètes — claire inspirée de Wispr Flow, sombre alignée sur les autres
outils. Le mode `auto` suit le réglage de Windows, relu toutes les cinq secondes. Les
couleurs d'état (écoute, transcription, insertion, erreur) sont **communes aux deux
palettes** : un vert qui change de teinte selon le fond se reconnaît moins vite. Un
test vérifie que les deux palettes définissent exactement les mêmes jetons — un jeton
manquant d'un côté laisserait un trou visuel après bascule.

### Raccourcis appliqués à chaud

Modifier un raccourci n'obligeait à relancer l'application. Windows lie une
combinaison au **fil** qui l'a enregistrée : reprendre une combinaison inchangée
échouerait contre elle-même, il faut donc rendre l'ancien jeu **avant** de
demander le nouveau. Si la nouvelle combinaison est déjà prise par une autre
application, l'ancien jeu est rétabli et l'utilisateur en est informé — des
raccourcis obsolètes valent mieux que plus aucun raccourci, et surtout mieux
qu'un utilisateur qui croit que le nouveau fonctionne.

Le repli passe les combinaisons **explicitement** au gestionnaire de secours
plutôt que de les relire dans la configuration : celle-ci contient déjà les
valeurs fautives au moment du repli, et le secours échouerait pour la même
raison que la tentative.

### Refonte de l'interface

Organisation reprise de Wispr Flow, couleurs reprises de l'app Notes — dont la
signature est un texte secondaire **bleuté** plutôt que gris neutre.

- **Barre latérale** à pictogrammes tracés (`icones.py`), dessinés plutôt que
  chargés : ils doivent suivre la couleur du thème et l'état de sélection, ce
  qui demanderait autrement une image par combinaison. Supersampling ×4 comme
  pour la marque, le canevas de Tk n'anticrénelant pas.
- **Réglages en fenêtre séparée**, à quatre sous-sections. Mêlés au contenu,
  ils obligeaient à faire défiler une longue liste pour changer une valeur, et
  un rafraîchissement de page effaçait la saisie en cours.
- **Recherche au fil de la frappe**, avec un délai de 220 ms. Seule la liste
  est reconstruite : le champ garde le focus et le texte déjà saisi.
- **Histogramme de la quinzaine** sur la page Statistiques. Les compteurs
  disent le total, l'histogramme dit la régularité — c'est ce qu'on vient
  vérifier. Il disparaît faute de données : quatorze zéros n'apprennent rien.

Trois défauts de rendu trouvés à la relecture des captures, invisibles en
lecture de code :

| Défaut | Cause | Correctif |
|---|---|---|
| Cases cochées indiscernables des cases vides | Tk dessine la coche dans la couleur d'avant-plan, noir par défaut, sur le fond sombre du thème | `fg` et `activeforeground` explicites, via une fabrique unique |
| Les trois boutons radio paraissaient tous actifs | Le témoin est dessiné par Windows et ignore la palette | Remplacés par un sélecteur segmenté peint à la main |
| Ascenseur clair traversant le thème sombre | Idem : `tk.Scrollbar` est rendu par le système | `Ascenseur`, canevas de 10 px redessiné soi-même |

Ajouté aussi `francais.py` : noms de jours et de mois écrits en dur plutôt que
confiés à `locale`, dont `setlocale` agit sur tout le processus et modifie au
passage l'interprétation des nombres à virgule. Le module traite les accords —
« 1 dictées » trahissait un compteur brut là où l'utilisateur attend une
phrase. Deux fautes d'accord réelles ont été corrigées à cette occasion
(« 1 jours d'affilée », « 0 minute économisées »).

### Coins arrondis et barre de titre

Deuxième passe sur l'interface, après un retour sans détour : « tout est
carré », « la barre tout en haut n'est pas incluse dedans », « la partie
graphique est horrible ».

**La barre de titre n'appartient pas à Tk.** Elle est dessinée par le
gestionnaire de fenêtres, et aucun réglage de widget ne l'atteint : elle
restait un cadre clair et carré posé autour d'une application sombre. Deux
issues existaient. Passer en fenêtre sans cadre (`overrideredirect`) donne
tout le contrôle mais fait perdre le glisser-déposer, l'ancrage Windows, la
restauration et le menu système — tous à réimplémenter. Windows 11 accepte au
contraire qu'on lui **impose** la couleur du bandeau, du texte, du bord et la
forme des coins (`DwmSetWindowAttribute`) : c'est la voie retenue
(`chrome.py`), pour une trentaine de lignes et sans rien perdre. Sur une
version antérieure les appels échouent proprement et la fenêtre garde son
habillage — l'application reste utilisable, seulement moins jolie.

**Tk ne connaît que le rectangle.** `highlightthickness` trace un cadre à
angles droits, et les arcs de son canevas ne sont pas lissés : à dix pixels de
rayon, l'escalier se voit plus que l'arrondi. `arrondi.py` dessine donc les
**coins** par Pillow à quatre fois la taille puis les réduit — même remède que
pour la barre de dictée. Seuls les coins sont des images ; les bords et le
fond restent des rectangles du canevas, si bien qu'une carte redimensionnée ne
recalcule rien et que le cache ne dépend que du rayon et des couleurs, jamais
de la taille du widget.

Le point délicat de la `Carte` : un canevas seul ne sait pas se dimensionner
sur son contenu, Tk ne lui donnant jamais la taille de ce qu'il porte. La
carte est donc un cadre ordinaire — qui, lui, se dimensionne — avec le canevas
placé dessous et le contenu dans un cadre **retréci de la valeur du rayon**
sur les côtés : les quatre coins restent découverts, seuls endroits où
l'arrondi se voit.

**Le graphe** est passé en barres Pillow à sommets arrondis, avec une marge
haute réservée aux chiffres — sans elle, la valeur du jour le plus chargé
sortait du cadre, et c'est justement celle qu'on vient lire. La géométrie
passe par une fonction unique (`graphe.sommet`) appelée aussi bien pour
dessiner que pour poser les libellés : deux calculs parallèles auraient fini
par diverger, et un chiffre flottant à côté de sa barre se remarque.

**Alerte d'enregistrement supprimée.** La fenêtre qui se ferme dit déjà que
c'est fait. Seul l'échec interrompt encore — sinon l'utilisateur croirait son
nouveau raccourci en service alors qu'il est refusé.

### Deux régressions trouvées à la mesure, pas à la lecture

**Deux secondes et demie pour ouvrir l'onglet Dictées.** Deux cents lignes
font environ seize cents widgets, et le profilage montre que le coût n'est pas
dans le dessin arrondi (5 ms au total) mais dans la mise en page de Tk et la
destruction des lignes précédentes. La liste charge désormais quarante lignes,
avec un bouton pour la suite : **2 455 ms → 450 ms**. La leçon est que
l'intuition désignait le nouveau code, et qu'elle avait tort.

**`image "pyimage7" doesn't exist`.** Une `PhotoImage` appartient à
l'interpréteur Tcl qui l'a créée et devient inutilisable dès qu'il disparaît.
Le cache de coins, module et non instance, survivait à cet interpréteur. Il
est maintenant à deux niveaux : les images Pillow, qui n'appartiennent à
personne, sont conservées indéfiniment ; les `PhotoImage` sont refaites dès
que l'interpréteur change. L'application n'en crée qu'un, mais un cache global
d'objets liés à un contexte est un piège qui n'attend que la prochaine
occasion.

### Troisième passe : ce que la capture d'écran a montré

Retour de l'utilisateur, capture à l'appui. Chaque point a mené à un défaut
réel, pas à une affaire de goût.

**Des équerres flottantes autour des champs de saisie.** Le champ n'existait
que par son filet d'un pixel. Or les coins arrondis sont lissés — ils
s'étalent sur deux pixels à opacité réduite — alors que les bords droits sont
tracés nets par le canevas. À filet clair, les quatre coins paraissaient donc
détachés du reste. Le remède n'est pas de retoucher le lissage mais de retirer
le filet : le champ porte désormais un fond légèrement décalé vers la couleur
du texte (`_creux`), calculé depuis le fond réel de son parent — un champ se
pose aussi bien sur le panneau que dans une carte, dont les fonds diffèrent.

**Une ligne grise bizarre autour des encarts.** Même cause. Les cartes n'ont
plus de filet du tout : c'est le contraste des fonds qui les détache.

**Le symbole était pixelisé.** `dessiner_image` traçait directement à la
taille finale, sans suréchantillonnage — Pillow ne lisse ni ses arcs ni ses
ellipses. Trois candidats ont été comparés agrandis au voisin le plus proche :
×4 moyenne de zone, ×8 moyenne de zone, ×8 Lanczos. **×8 moyenne de zone** l'a
emporté ; Lanczos borde chaque trait fin d'un liseré clair, bien visible sur
un arc de deux pixels. Les pictogrammes sont passés au même réglage.

Un test a cédé au passage, et il avait tort : il échantillonnait le **centre
de l'image** pour vérifier la couleur du point, alors que le symbole est
recentré optiquement. Il ne passait que par l'effet du crénelage — le tracé
lissé est tombé pile sur le bord du disque.

**La barre de titre n'affichait pas mieux.** `iconphoto` recevait une seule
image de 64 pixels, que Windows réduisait sans soin pour le bandeau. Cinq
tailles lui sont maintenant fournies, chacune dessinée séparément.

**Les cases à cocher faisaient « Windows ».** Celle de Tk est rendue par le
système : bord gris, coins droits, coche anguleuse, insensible à la palette.
Redessinée dans `icones.case` — carré arrondi, rempli à l'accent, coche en
deux segments aux proportions des autres pictogrammes.

**Les encarts collaient aux parois.** Le contenu occupe désormais un panneau
arrondi posé sur le fond de la fenêtre, avec une bande tout autour — la
feuille sur le bureau plutôt que la zone collée au cadre. La palette a été
réorganisée en conséquence : `fond` pour la fenêtre, `surface` pour le
panneau, `carte` pour ce qui s'y pose, `pilule` pour l'onglet actif.

**Le logo était en double** — barre latérale et barre de titre. Retiré de la
barre, remplacé par un bouton de volet qui replie la latérale sur ses
pictogrammes ; le choix est retenu d'une session à l'autre. Le lien « Dossier
de données » est parti aussi : personne ne déplace ce dossier au quotidien.

**Les chiffres clignotaient à chaque dictée.** La page était détruite puis
rebâtie. Les étiquettes chiffrées sont maintenant conservées et seul leur
texte est réécrit (`_actualiser_statistiques`).

### Page Statistiques : les indicateurs

Aux quatre chiffres d'origine s'ajoutent, tous calculés sur des données déjà
présentes en base :

| Indicateur | Source |
|---|---|
| Rapport de vitesse et jauge | cadence mesurée contre 40 mots/minute au clavier |
| Corrections apprises | table `corrections`, alimentée depuis la V1 |
| Entrées au dictionnaire, remplacements appliqués | lexique |
| Tendance mensuelle | découpage **calendaire**, muette le premier mois — « +100 % » comparé à rien ne veut rien dire |
| Applications | colonne `cible` ; les dictées antérieures à son enregistrement sont regroupées sous « inconnue » plutôt qu'écartées, sans quoi les pourcentages ne feraient plus cent |
| Calendrier d'activité | `mots_par_jour`, une colonne par semaine |

Le calendrier n'affiche que les semaines **entières** qui tiennent dans la
largeur : une colonne coupée au bord droit se lit comme un défaut d'affichage.
Il remplace l'histogramme de quinzaine, qui disait la même chose sur une
période plus courte.

### Quatrième passe : la barre de titre, pour de bon

Teinter le bandeau du système ne suffisait pas — il restait un morceau
rapporté, d'un autre gris, aux boutons d'un autre style. Deux voies :

- `overrideredirect` détache la fenêtre du gestionnaire : plus de barre des
  tâches, plus d'Alt+Tab, plus d'ancrage, tout à réimplémenter ;
- retirer le seul style `WS_CAPTION` en gardant `WS_THICKFRAME` : le bandeau
  disparaît, le cadre redimensionnable reste, la fenêtre reste une fenêtre.

C'est la seconde. `BarreTitre` reprend ce que le bandeau assurait —
déplacement, agrandissement, réduction, fermeture — aux couleurs du thème.

**Deux pièges, tous deux trouvés par les tests plutôt qu'à l'œil :**

L'agrandissement par l'état `zoomed` de Tk vise l'écran entier pour une
fenêtre sans bandeau : elle recouvrait la barre des tâches. La zone utile est
donc demandée à Windows (`GetMonitorInfo`) et imposée directement.

Plus subtil : la fenêtre gagnait **deux pixels de large à chaque
agrandissement-restauration**. Tk ajoute à la taille demandée les marges du
cadre telles qu'il les a relevées au premier affichage — le bandeau ayant
disparu depuis, sa comptabilité est fausse. Position et taille passent
désormais par `SetWindowPos`, sans arithmétique de cadre. Un test enchaîne
trois allers-retours et compare le rectangle réel.

### Couleurs, textes, emoji

Palette relevée sur Wispr Flow à la demande : `#f5f4f0` pour la fenêtre,
`#fcfcfb` pour le panneau, `#312d37` pour le texte — un gris violacé, pas un
noir neutre. La palette sombre est bâtie sur la même teinte inversée : un
sombre neutre à côté d'un clair violacé donnerait deux applications
différentes selon le réglage de Windows.

La carte Applications affichait `navigateur.exe — Nouvel onglet`. Deux
défauts : la cible est enregistrée sous la forme « programme — titre de la
fenêtre », si bien que le regroupement produisait **une ligne par onglet** ;
et l'extension n'apprend rien à personne. Le regroupement se fait maintenant
sur le programme seul, et `applications.py` lui donne un nom d'usage et un
emoji de famille.

Ces emoji sortaient en noir et blanc : Tk dessine par GDI, qui ignore les
polices en couleur. Pillow, lui, sait lire les couches de « Segoe UI Emoji ».
Restait un dernier défaut — l'enveloppe se réduisait à un trait blanc sur le
bord du cadre. En cause, le **sélecteur de variante** U+FE0F : faute de moteur
de rendu de texte, il compte comme un second glyphe avec sa propre avance, et
centrer sur la paire poussait l'emoji hors du cadre. Il est retiré avant
rendu.

### Affichage d'un bloc

Une page bâtie directement dans le panneau se remplissait sous les yeux, carte
après carte : Tk affiche chaque widget dès qu'il est placé. Les pages sont
donc construites **hors écran** — un cadre non placé n'est pas dessiné — puis
posées d'un coup.

Le clignotement de la liste des dictées tenait à une autre cause : elle était
détruite puis reconstruite à chaque dictée. Seule la nouvelle ligne est
maintenant créée et insérée en tête, avec l'en-tête du jour si elle inaugure
une journée.

### Cinquième passe : comparaison côte à côte

Cette fois les deux fenêtres étaient sur la même capture, ce qui permet de
mesurer plutôt que d'estimer. Les écarts relevés, tous corrigés :

| Écart | Avant | Après |
|---|---|---|
| Barre de titre | 42 px, commandes serrées | 52 px, commandes espacées |
| Titre de page | 22 pt, marge 22 | 24 pt, marge 30 |
| Titres de section | petites capitales, 8 pt | 16 pt normal, appoint en capitales à droite |
| Cartes de chiffres | pas de séparation | filet entre le chiffre et son détail |
| Jauge | 86 px dans un coin | centrée sous son chiffre, rapport écrit dans le creux |
| Calendrier | 3 jours libellés, mois en bas | 7 jours libellés, mois au-dessus |
| Lignes de dictée | 15 px de marge, texte 10 pt | 19 px, texte 11 pt |

Trois défauts sont apparus à la relecture des captures :

**« −27 % ce mois-ci » se coupait au bord de sa carte** dès que le total
passait à quatre chiffres. Une carte dont le texte se tronque est pire qu'une
carte sans tendance : la mention est réduite à une flèche et un pourcentage,
et la période est dite dans le détail, où la place ne manque pas.

**« 6 APPLICATIONs »** — l'accord ajoutait son `s` en minuscule à un mot déjà
capitalisé. L'accord se fait maintenant sur le mot en minuscules, la
capitalisation vient après.

**« jui » deux fois de suite** sur la frise des mois : juin et juillet
partagent leurs trois premières lettres. Une table d'abréviations remplace la
troncature.

### Démarrage avec Windows

Demandé, et l'occasion de trouver un défaut : la commande inscrite dans la clé
`Run` visait toujours `pythonw.exe -m murmur`. Une fois l'application
empaquetée, `sys.executable` **est** l'exécutable — la commande lui passait un
argument qu'il ne comprend pas. Les deux cas sont désormais distingués, et
trois tests couvrent la commande produite, dont un qui simule l'état empaqueté.

### Sixième passe : quatre défauts reproduits avant d'être corrigés

Chacun a d'abord été mis en évidence par un script de diagnostic — un défaut
qu'on ne sait pas reproduire n'est pas corrigé, il est masqué.

**Une bande claire de six pixels au-dessus de la barre de titre.** Elle venait
de l'application elle-même : `habiller` imposait au gestionnaire de fenêtres la
couleur du **panneau** comme couleur de bandeau. Le bandeau retiré, Windows
garde six pixels de cadre et les peint de cette couleur. Elle prend désormais
celle du fond de la fenêtre, et la couture disparaît.

**Le calendrier d'activité n'affichait aucune case remplie.** Le nombre de
jours demandés valait `colonnes × 7`, mais la première semaine est complétée
jusqu'au lundi : la série produisait une colonne de plus que prévu, et le
tracé s'arrêtait au bord du cadre. La colonne perdue était la dernière —
celle d'aujourd'hui, la seule qu'on regarde. Le nombre de jours se déduit
maintenant du nombre de colonnes, jour de la semaine compris.

**Le pied de page restait figé** dès qu'on quittait l'historique : sa mise à
jour vivait dans la branche « page des dictées ». Le pied appartient à la
fenêtre, pas à la page ; il est rafraîchi hors de la condition.

**« Réglages » depuis le menu de l'icône ne faisait rien.** Le menu demandait
« reglages » comme une page ordinaire ; l'affichage levait une erreur de clé,
qui ne remonte nulle part depuis une réaction Tk. Les réglages ont leur propre
fenêtre — le cas est traité, et la fenêtre principale retombe sur sa première
page plutôt que de refuser de s'ouvrir.

### Anglais, et le choix de la langue

L'interface est en anglais par défaut, avec le vocabulaire de la référence —
« Dictation », « Insights », « Dictionary », « fixes », « streak » — et le
français reste à un clic dans les réglages. `langue.py` porte la table :
deux cents chaînes, deux langues, aucun traducteur extérieur à servir ; un
fichier `.po` et sa chaîne d'outils coûteraient plus qu'ils ne rapporteraient.

Les accords en font partie, les règles différant : « 0 dictée » au singulier
en français, « 0 dictations » au pluriel en anglais. Séparateurs de milliers et
de décimales suivent aussi la langue. Un test vérifie que les champs à
substituer se correspondent d'une langue à l'autre — un `{raccourci}` d'un côté
et un `{shortcut}` de l'autre lèveraient une erreur de formatage dans une seule
langue, donc chez un seul utilisateur.

### Pictogrammes au trait

Les emoji en couleur, introduits à la passe précédente, ont été retirés : ils
juraient à côté d'une interface qui ne compte aucune autre couleur. Douze
pictogrammes d'usage sont tracés comme le reste — navigateur, code, terminal,
messagerie, courriel, document, notes, dossier, IA, média, jeu, neutre.

Au passage : la jauge a maintenant des bouts arrondis (Pillow coupe ses arcs à
l'équerre, deux disques suffisent), les barres d'usage ont perdu leur piste
grise, qui donnait deux barres à lire au lieu d'une, et la marque est revenue
en haut de la barre latérale — retirée quand elle faisait double emploi avec le
bandeau du système, elle n'avait plus rien qui la porte une fois celui-ci ôté.

### Septième passe : l'ordre, le lissage, le glissement

**Deux dictées d'une même seconde sortaient dans le désordre.** L'horodatage
est enregistré à la seconde ; l'ordre `horodatage DESC` laissait les ex æquo au
bon vouloir de SQLite, qui rend souvent l'ordre d'insertion — donc la plus
ancienne en premier. L'identifiant les départage désormais, et deux tests
fixent le comportement.

**Le symbole de la barre latérale était crénelé** alors que celui de la barre
des tâches ne l'est plus : il passait par `dessiner_canvas`, qui trace sur un
canevas Tk, lequel ne lisse rien. Seul `dessiner_image` avait été corrigé.
La barre affiche maintenant une image, comme partout ailleurs.

**Le repli de la barre latérale glisse.** Cent cinquante millisecondes,
adoucies en cosinus. Le contenu est refait tout de suite et seule la largeur
s'anime : la barre découvre ou recouvre ses libellés comme un volet, là où les
rebâtir en fin de mouvement les faisait apparaître d'un coup. Deux clics
rapprochés renversent le mouvement au lieu d'être ignorés — refuser le second
laissait la barre à mi-chemin.

Les cartes d'usage et d'activité ont été agrandies (barres de 26 pixels,
calendrier de 196), et le pourcentage est centré dans sa barre plutôt que posé
à une ordonnée fixe, qui datait d'une hauteur précédente.

### Le dépôt « Wispr-Flow » de yatharthsameer

Examiné à la demande. Trois constats.

**Ce n'est pas Wispr Flow.** Le dépôt s'appelle ainsi sur GitHub mais le
projet se nomme **OpenWhispr** : une réimplémentation indépendante, cinq
étoiles, sous licence MIT. Son interface est un habillage shadcn/ui standard
à primaire indigo `#4f46e5` — rien à voir avec le beige et le gris violacé
que nous cherchons à approcher. Comme référence visuelle, c'est une impasse.

**Rien de son code ne se transpose.** Electron 36, React 19, Tailwind v4,
Vite. Notre interface est en Tkinter : il n'y a pas une ligne à reprendre.

**Une chose s'est révélée utile malgré tout**, et elle corrige une erreur que
j'avais commise. Leurs cartes portent :

```css
box-shadow: 0 4px 8px rgba(43,31,20,.08), 0 1px 0 rgba(255,255,255,.5) inset;
```

Le second terme est un **trait clair d'un pixel sous le bord haut**. C'est ce
qui donne l'impression de relief qu'on prenait pour un dégradé — et il ne
demande ni transparence ni fond dégradé. J'avais répondu que c'était
impossible : le dégradé l'est, cette arête ne l'était pas.

Elle est posée sur les cartes du tableau de bord, en tenant compte du thème :
une arête **claire en haut** sur fond sombre, une arête **sombre en bas** sur
fond clair. Sur une carte presque blanche, un trait clair ne se voit pas ; sur
une carte sombre, un trait sombre non plus. Les lignes de liste en sont
exclues : à cette échelle, le trait se remarquerait plus que la ligne.

### Portage sur WebView2 : la fondation

Décision d'architecture : le tableau de bord vit dans son **propre
processus**, lancé à l'ouverture de la fenêtre et arrêté avec elle. Deux
raisons, et la seconde compte autant que la première :

- Tk, qui porte la barre de dictée et l'icône, veut le fil principal ;
  pywebview aussi. Les faire cohabiter demanderait de reléguer l'un des deux
  sur un fil secondaire, ce qu'aucune des deux bibliothèques ne garantit.
- Les cinq processus de WebView2 pèsent plus lourd que tout le reste de
  l'application. Les laisser mourir avec la fenêtre ramène Murmur au repos à
  son empreinte d'origine — 213 Mo, contre les ~550 qu'aurait coûté une
  fenêtre permanente.

Trois modules sont en place :

| Module | Rôle | Tests |
|---|---|---|
| `canal.py` | commandes du tableau vers l'application, sur la prise déjà ouverte par le verrou d'instance | 11 |
| `tableau/donnees.py` | la base et le lexique vers du JSON ; **premier code d'affichage du projet testable sans ouvrir de fenêtre** | 26 |
| `tableau/api.py` | le pont Python↔page |  |
| `tableau/web/` | les trois pages : Insights, Dictation, Dictionary |  |
| `sorties.py` | garde-fou des sorties standard, extrait de `__main__` pour être partagé |  |
| `ecran.py` | conscience du DPI, prête mais pas encore branchée |  |

Le canal réutilise la prise du verrou d'instance, qui écoutait depuis toujours
sans jamais rien accepter. Cela évite un second port, et garantit que le canal
existe exactement quand l'application tourne.

**Piège pywebview** : il parcourt l'objet exposé au JavaScript pour en dresser
la liste des méthodes, et descend dans chaque attribut public. Une fenêtre
stockée en clair l'entraînait jusque dans les objets .NET de WebView2, où la
comparaison d'un rectangle levait une erreur de type — et la fenêtre ne
s'ouvrait pas. Tout ce qui n'est pas une commande porte donc un nom privé.

**Contrainte d'outillage établie** : la fenêtre s'ouvre normalement quand
l'utilisateur lance la commande lui-même, et jamais depuis mes lancements —
ni par un sous-processus Python, ni par `Start-Process`, ni avec `python.exe`,
ni avec `pythonw.exe`. Le processus atteint bien `webview.start()` et Chromium
enregistre sa classe de fenêtre, mais aucune fenêtre de premier niveau
n'apparaît. Les fenêtres Tk, elles, se créent sans difficulté depuis le même
contexte.

Conséquence pratique : **le tableau de bord ne peut pas être vérifié
visuellement de façon autonome**. Les captures d'écran passent par un
lancement manuel. La couche de données, elle, se teste sans fenêtre — c'était
justement la raison de la séparer.

**Piège rencontré une troisième fois** : `GetWindowThreadProcessId` appelée
sans `argtypes` reçoit un descripteur tronqué à 32 bits et répond zéro. Ma
sonde ne trouvait donc jamais la fenêtre — j'ai cherché le défaut dans
l'application avant de le trouver dans l'outil de mesure. Après
`SetWindowLongPtr` et `SetProcessDpiAwarenessContext`, c'est la même leçon :
en ctypes, **toute** fonction Win32 a besoin de `restype` et `argtypes`.

### Ce que Tk ne fera pas

Trois demandes sont restées sans réponse satisfaisante, et il vaut mieux le
dire que de faire semblant :

**Un dégradé sur les encarts.** Le contenu d'une carte est posé sur un cadre
Tk opaque, qui recouvre tout sauf les quatre coins. Un dégradé peint dessous
serait masqué par ce cadre, et Tk n'offre ni transparence ni fond dégradé pour
un conteneur. Seule une refonte complète — tout le contenu dessiné sur un
canevas unique, y compris le texte et les champs — le permettrait.

*Corrigé depuis* : le relief recherché ne venait pas d'un dégradé mais d'une
arête d'un pixel, qui elle est à notre portée — voir la section sur le dépôt
OpenWhispr.

**La finesse du texte.** Wispr Flow est une application Electron : son texte
est rendu par DirectWrite. Tk passe par GDI. Tailles, graisses et interlignes
s'ajustent, le moteur de rendu non.

**La bande claire au-dessus de la barre de titre** n'a pas pu être reproduite
après la correction de la couleur de bandeau, ni fenêtre au repos ni fenêtre
active, sur la fenêtre réelle comme sur un cas d'essai. L'habillage est
néanmoins redemandé à chaque activation et à chaque retour d'icône : Windows
repeint le cadre dans ces deux cas, et rien ne garantissait que la teinte
imposée y survive.

### Latence réelle

**380 ms** entre la fin de la parole et l'apparition du texte, mesurés en conditions
réelles sur une dictée en français. Le critère de succès n°1 de la spec (médiane sous
400 ms) est tenu dès le premier jalon fonctionnel, et l'outil est plus rapide que
Wispr Flow, qui tourne autour de la seconde.

Décomposition attendue : ~250 ms d'inférence GPU, le reste en capture, encodage WAV,
aller-retour HTTP local et collage.

**133 tests**, dont 8 démarrant le vrai moteur et 14 utilisant du matériel réel.
Lancement : `lancer.bat`, ou `.venv\Scripts\python.exe -m murmur`.

**Le moteur ne survit plus à l'application.** Le premier lancement réel a laissé un
`whisper-server` orphelin qui bloquait le port : sur Windows, un enfant ne meurt pas
avec son parent, et le nettoyage placé dans un `finally` ne s'exécute pas si la
console est fermée par la croix. Corrigé par un job object suicidaire, doublé d'une
récupération des orphelins au démarrage. Détail dans [logs/ERREURS.md](logs/ERREURS.md).

### Notes d'implémentation

**Deux questions distinctes sur un port.** `port_disponible()` tente un *bind*
(« puis-je démarrer ici ? »), `serveur_repond()` tente une *connexion* (« le moteur
est-il prêt ? »). Les confondre produisait un faux négatif quand le backlog du socket
était plein : l'application démarrait un serveur sur un port déjà pris.

**Le moteur reste chargé entre deux dictées** — vérifié par un test qui échoue si la
seconde transcription dépasse 900 ms, ce qui trahirait un rechargement du modèle.

**Reconstruire `engine/`** (exclu de git, 603 Mo) : compiler whisper.cpp v1.9.2 avec
`-DGGML_VULKAN=ON`, puis copier `whisper-server.exe`, `whisper-cli.exe`, `whisper.dll`
et les quatre `ggml*.dll`, plus les modèles `ggml-large-v3-turbo-q5_0.bin` et
`ggml-silero-v5.1.2.bin`.

**Un test qui dépend du focus doit vérifier qu'il l'a.** Le test d'insertion réelle
passait seul et échouait dans la suite complète : une autre fenêtre retenait le focus
et le collage partait ailleurs. Il contrôle désormais la fenêtre active avant
d'injecter et se déclare non concluant sinon, en nommant le coupable. Un test instable
qui rapporte de faux échecs coûte plus cher que pas de test du tout.

**Limite assumée de J1** : une nouvelle dictée est refusée tant que la précédente
n'est pas insérée (~250 ms). La fenêtre est courte, mais s'allongera si le nettoyage
par IA est activé. Sans retour visuel, l'utilisateur croirait avoir dicté dans le
vide : c'est à l'indicateur d'état (T3.1) de le signaler.

### Décisions issues de J0

| Sujet | Décision | Fondée sur |
|---|---|---|
| Injection par défaut | Presse-papier + `Ctrl+V` | 5/5 applications, ~3 ms, insensible aux autocorrections |
| Injection de repli | Frappe Unicode, dernier recours seulement | 16 ms/caractère, et vulnérable aux autocorrections |
| Anti-hallucination | `--vad` (Silero) + `--suppress-nst` en première ligne | 3/3 hallucinations sans, 0/3 avec |
| Lexique | Prompt de conditionnement + table de remplacement obligatoire | 5/10 → 8/10 termes, mais effet non monotone |

**Acquis anticipé** — `WS_EX_NOACTIVATE` a été posé et vérifié sur une fenêtre Tkinter
lors de l'outillage de T0.1 : le style tient. C'est la brique la plus délicate de la
décision D5 et de la tâche **T3.1** (indicateur d'état qui ne vole jamais le focus),
validée bien avant son jalon.

## Journal

**27/08/2026 (34) — Un dépôt public se lit d'abord par sa racine**
Dix-sept fichiers à la racine, dont 2 600 lignes de documents de travail, quatre
outils de captures d'écran, deux lanceurs `.bat` et une maquette morte. Ça se
lit comme un espace de travail, pas comme un projet publié.

Vérifié avant de tailler : **aucun module de `murmur/` n'est orphelin.** Chacun
des trente-quatre est importé par au moins un autre. Le problème n'était pas le
code, c'était sa disposition — et il valait pour le dossier local autant que
pour le dépôt.

```
avant                          après
  17 fichiers à la racine        5 fichiers à la racine
  PLAN, SPEC, TACHES, SUIVI      docs/    spécification, plan, journal
  construire, empaqueter,        outils/  construction, archive, captures,
  lanceur, 4 × outils_*,                  essai sur machine vierge
  2 × lancer.bat                 murmur/  l'application
  maquette/, bac/, logs/         tests/
```

Supprimés : les deux `.bat` (l'application se lance par `python -m murmur`, et
la version livrée est un exécutable) et la maquette — un prototype de
comparaison Tkinter contre moteur web, dont la décision est prise depuis
longtemps.

Deux pièges du déplacement, tous deux attrapés par les tests ou par un essai
réel. Les tests d'empaquetage lisaient `construire.py` à la racine. Et
`construire.py` importait `murmur` **avant** de poser la racine sur le chemin
de recherche : tant qu'il vivait à la racine, Python l'y ajoutait de lui-même ;
depuis `outils/`, il n'ajoute plus que `outils/`.

Vérifié de bout en bout après déplacement : construction, archive de 56 Mo,
planche de captures, et **781 tests**.


**27/08/2026 (33) — Le reste des relances : la suite de tests tuait le moteur**
Après le correctif de la course entre fils, les relances continuaient. Le
compteur passait de 237 à 239 **à chaque exécution de la suite de tests**, et
le moteur changeait de PID.

Libérer le port revenait à tuer **tous** les moteurs issus de notre dossier —
et deux tests faisaient le même ménage sans filtre. Or le dossier livré est une
jonction NTFS vers celui du projet, et Windows **résout la jonction** quand on
lui demande le chemin d'un processus :

```
lancé depuis  : ...\dist\Murmur\engine\whisper-server.exe
lu comme      : ...\Murmur\engine\whisper-server.exe
```

Deux chemins au lancement, un seul à la lecture. L'application et la suite de
tests se reconnaissaient donc mutuellement comme orphelines, et chaque
exécution des tests tuait le moteur de l'application en cours d'utilisation.
Cela n'atteint pas un utilisateur — la jonction n'existe que sur une machine de
développement — mais cela a pollué le diagnostic pendant des jours.

Le critère devient le bon : on ne tue que le processus qui **tient ce port-là**,
lu dans la table TCP du système (`GetExtendedTcpTable`), et seulement s'il est
des nôtres. Les deux ménages de test ne visent plus que ce qu'ils ont créé.

Mesuré avant / après, application en marche pendant l'exécution :

| | relances | PID du moteur |
|---|---|---|
| avant | 237 → 239 | changé |
| après, trois exécutions | 239 → 239 | inchangé |

Une leçon de méthode aussi : la première mesure du correctif donnait « zéro
relance » — mais l'application avait déjà atteint son plafond de trois
redémarrages et abandonné. Elle ne pouvait plus rien relancer. Un compteur
figé ne prouve pas qu'il ne se passe rien. **782 tests.**


**27/08/2026 (32) — Publication : dépôt public, licence MIT, version 0.1.0**
Le dépôt est ouvert sous licence MIT, l'archive de 56 Mo attachée à la
release. Deux choses ont demandé du soin.

**Le nettoyage.** Le journal, les tests et les données de démonstration
étaient truffés du vocabulaire de l'auteur — noms de services, corrections
tirées de dictées réelles, et un texte long de deux cent trente caractères
qui parlait de son travail. Rien de secret, mais rien qui décrive le
logiciel non plus.

La règle suivie : **ne jamais remplacer un mot dans une phrase qui cite une
mesure.** Une ressemblance de 0,600 a été relevée sur une paire précise ;
changer la paire rendrait le chiffre faux. Les phrases ont donc été
généralisées en gardant les chiffres, et là où un texte d'exemple devait
être remplacé, le remplaçant a été **choisi par mesure** : il fallait qu'il
reproduise le défaut. Le nouveau texte long obtient 0,060 contre 0,968 —
l'original donnait 0,052 contre 0,978.

Le vocabulaire des tests a été remplacé par du vocabulaire technique de même
difficulté, et la suite a servi de garde-fou : quatre tests ont échoué sur
des seuils de ressemblance, dont un remplaçant à 0,706 sous le seuil de 0,82.
Corrigé, mesuré, revert.

**L'enregistrement de référence.** Un test rejouait un fichier `.wav` — la
voix de l'auteur lisant son jargon — et portait son vocabulaire en dur. Le
`.wav` n'est pas publié ; les variantes attendues sont donc parties dans le
`reference.json` qui l'accompagne, et le test se saute de lui-même quand
l'enregistrement est absent. Ce qui décrit une personne ne doit pas vivre
dans ce qui décrit un logiciel.

Publié : dépôt `thespicyy/murmur`, release `v0.1.0`. **778 tests.**


**27/08/2026 (31) — L'archive : 56 Mo, et le modèle pris au premier lancement**
Le modèle pèse 574 Mo, tout le reste 82. Le livrer avec ferait une archive que
personne ne télécharge pour essayer — et la moitié de ceux qui la
téléchargeraient n'ont pas besoin de celui-là.

Il est donc pris au premier lancement, quand on sait sur quelle machine on est
tombé : `large-v3-turbo` (574 Mo) si une carte Vulkan répond, `small` (190 Mo)
sinon. Le choix est mesuré, pas supposé — sur une phrase de huit secondes,
250 ms avec la carte contre 9 400 ms sans. `base`, trois fois plus rapide que
`small`, a été écarté sur la qualité : là où `small` se trompait sur un
seul mot, `base` en inventait trois — dont un nom propre rendu en trois
morceaux sans rapport.

Le téléchargement reprend là où il s'est arrêté (en-tête `Range`), vérifie
l'empreinte SHA-256, et ne fait apparaître le fichier définitif qu'une fois
vérifié. Le modèle va dans les données de l'utilisateur, pas à côté de
l'exécutable : une mise à jour ne doit pas jeter 574 Mo.

**Archive : 56 Mo.**

Deux pièges rencontrés en la fabriquant.

*Le premier est le mien.* J'ai empaqueté un exécutable construit une
demi-heure avant la fonctionnalité qu'il était censé livrer. L'essai a échoué
sur un symptôme parfaitement trompeur — « modèle introuvable » — qui décrivait
l'ancienne version. `empaqueter.py` refuse désormais une archive dont
l'exécutable est plus ancien que les sources, et nomme les fichiers en cause.

*Le second est un vrai défaut.* Après le téléchargement, l'application
démarrait puis disparaissait avec le code **0x80000003**, sans une ligne de
journal. Deux racines Tk dans un même processus : la fenêtre de premier
lancement créait la sienne et la détruisait, celle de l'application tombait
dessus. Une seule racine désormais, créée dans `main` et prêtée aux deux — et
un test qui refuse qu'un module en crée une autre.

Vérifié de bout en bout depuis l'archive, données isolées : carte détectée,
modèle obtenu en 14 s, application en marche, Ctrl+Alt+D pris, transcription
correcte. **779 tests.**


**27/08/2026 (30) — Deux fils lançaient le moteur, le second tuait le premier**
Le journal comptait **211 « moteur tombe, relance automatique »**. Avant de
publier quoi que ce soit, il fallait savoir.

Premier tri, honnête : 45 de ces relances suivent de moins de trois minutes un
démarrage de l'application, et une bonne part du reste vient de mes propres
`Stop-Process` pendant les essais du jour. Le compteur brut ne prouvait rien.

Ce qui prouve, c'est la forme. Les écarts entre relances se groupent sur **3, 7,
9, 10 secondes** — des rafales de trois, puis 290 s d'attente : exactement le
plafond `max_redemarrages: 3` sur `fenetre_redemarrages_s: 300`. Et **aucune
corrélation avec les dictées** (14 sur 211 dans les deux minutes suivant une
transcription) : le moteur ne mourait pas en transcrivant, il mourait en
**démarrant**. Le journal du moteur le montre, coupé net sur
`Vulkan0 total size = 573.40 MB`, en plein chargement.

La cause est une course. `assurer_disponibilite` est appelée par deux fils —
le veilleur toutes les deux secondes, et le fil de traitement quand une dictée
arrive. Le démarrage dure plusieurs secondes et commence par **tuer les moteurs
orphelins** pour libérer le port. Pendant ce temps `self._processus` est nul :
le second fil voyait donc le moteur mort, entrait à son tour, et tuait celui
que le premier venait de lancer.

Par-dessus le marché, l'échec déclenchait le repli ajouté le matin même :
l'application basculait sur le processeur, **trente-sept fois plus lent**, pour
une panne qui n'existait pas.

Un verrou, et un contrôle refait à l'intérieur — le fil qui attendait n'a plus
rien à relancer. Vérifié : le test échoue sans le contrôle (deux relances au
lieu d'une), et l'application tourne depuis sans une seule relance.

Corrigé au passage : un test échouait une fois sur trois, dans la suite
complète seulement. Il exigeait qu'aucun moteur ne traîne, et un test précédent
lui en laissait un en train de s'éteindre. **765 tests, quatre exécutions
consécutives vertes.**


**27/08/2026 (29) — Le numéro de carte graphique ne se transporte pas**
Question posée : que se passe-t-il sur une Nvidia, ou sur une autre AMD ?

**Le moteur, lui, se transporte.** Vulkan est une interface commune à tous les
fabricants, et `ggml-vulkan.dll` n'importe rien d'autre que `vulkan-1.dll`, le
chargeur que tout pilote graphique installe. Les programmes sont compilés à
l'exécution pour le matériel présent : le même binaire tourne sur AMD, Nvidia
ou Intel. Le choix de Vulkan plutôt que CUDA ou ROCm, fait au bench initial
pour une raison de disponibilité, se révèle être ce qui rend l'application
distribuable.

**Le numéro de carte, non.** La configuration portait `device_vulkan: 0`, écrit
pour ce poste. Or l'ordre d'énumération n'est pas stable — relevé sur la même
machine, le même binaire, à quelques minutes d'intervalle :

```
0 = AMD Radeon RX 9070 XT       0 = AMD Radeon(TM) Graphics
1 = AMD Radeon(TM) Graphics     1 = AMD Radeon RX 9070 XT
```

Prendre le numéro zéro revenait donc à **tirer au sort** entre la carte dédiée
et le circuit intégré au processeur. Invisible sur une machine à une seule
carte ; sur un portable ou une tour à processeur graphique, c'est une dictée
plusieurs fois plus lente, sans rien dire.

Le moteur sait énumérer ses périphériques — `--help` les liste et rend la main
en 230 ms. On lui demande, on préfère une carte dédiée à un circuit intégré
puis le calcul matriciel, et **on retient le nom** plutôt que le numéro : un
numéro ne veut rien dire d'une session à l'autre. Les configurations existantes
qui portent l'ancien zéro par défaut repassent en automatique ; un numéro posé
à la main est respecté.

Vérifié sur ce poste : `carte graphique retenue : AMD Radeon RX 9070 XT (parmi
2)`, écrit dans la configuration. Les deux ordres d'énumération sont couverts
par un test, ainsi qu'une machine Intel + Nvidia. **764 tests.**


**27/08/2026 (28) — Le repli sur le processeur, mesuré**
Le tableau de bord s'ouvre bien sur machine vierge : WebView2 est là, ma sonde
le cherchait au mauvais endroit. Restait la carte graphique.

Mesuré sur le même fichier de huit secondes de parole, même modèle :

| | latence |
|---|---|
| Vulkan, RX 9070 XT | **250 ms** |
| processeur (`--no-gpu`) | **9 400 ms** |

Trente-sept fois plus lent, et au-delà du temps réel : ce n'est pas un mode
d'usage, c'est un secours. Mais une machine sans Vulkan exploitable doit
dicter lentement plutôt que ne pas démarrer du tout. Le moteur réessaie donc
une fois avec `--no-gpu` quand le démarrage échoue, le repli tient pour la
session — réessayer la carte à chaque fois ferait payer l'échec autant de
fois — et le réglage `moteur.repli_processeur` permet de le refuser, pour qui
préfère savoir que sa carte ne répond plus. **749 tests.**


**27/08/2026 (27) — Murmur tourne sur une machine qui n'est pas la mienne**
Premier essai hors du poste de developpement, dans Windows Sandbox : machine
vierge, aucun runtime, aucun SDK, aucun Python. Trois passages ont ete
necessaires.

**Passage 1.** Boite de Windows : « Impossible d'executer le code, car
MSVCP140.dll est introuvable ». Le moteur ne demarrait pas, et l'application
echouait trente secondes plus tard sur « le serveur n'a pas repondu » — exact,
et sans rapport avec la cause. Les binaires du moteur importent des
bibliotheques Visual C++ que Visual Studio installe sur la machine qui compile
et que Windows ne fournit pas.

**Passage 2.** Meme boite, autre nom : `VCOMP140.DLL`, la bibliotheque OpenMP.
Absente de la liste que j'avais ecrite, parce que je l'avais etablie en
cherchant des noms plausibles. Une liste devinee se corrige a raison d'un
demarrage par oubli.

D'ou la regle, qui ne devine plus rien : **est a livrer toute bibliotheque que
le moteur importe et que Visual Studio range parmi ses redistribuables** — ce
dossier est exactement la liste de ce que Microsoft ne garantit pas present.
La table des imports des fichiers PE est lue directement (`murmur/pe.py`), la
chaine des dependances est suivie jusqu'au bout, et un manifeste depose a cote
du moteur permet a l'application de verifier la livraison sur une machine qui
n'a jamais vu Visual Studio. Recompiler le moteur autrement amenera les bonnes
bibliotheques sans que personne y pense.

Deux corrections de diagnostic au passage. Le mode d'erreur du processus
empeche desormais Windows d'ouvrir sa propre boite modale au nom du moteur :
l'echec devient un code de sortie qu'on peut lire. Et ce code est traduit —
« code 3221225781 » devient « une bibliotheque manque a cote du moteur ».

**Passage 3.** Le moteur demarre, repond HTTP 200, trouve ses deux
peripheriques Vulkan, et **Ctrl+Alt+D est bien pris par Murmur**. **745 tests.**

Restent deux inconnues, non tranchees : le repli sur le processeur quand
Vulkan manque, et le tableau de bord quand WebView2 est absent — le bac a
sable a signale `webview2 : False`.


**27/08/2026 (26) — Une case de calendrier portait le nom d'un message**
La vue calendaire affichait trois colonnes de pavés géants au lieu de dix-neuf
rangées de carrés, et la page débordait dans les deux sens.

Même famille que la veille, autre nom. Les cases de remplissage — les jours qui
précèdent le début de la série — portaient la classe `vide`, qui est aussi
celle du message « rien à afficher » d'une liste : `padding: 72px 0`. Une case
héritait donc de **144 px de hauteur minimale** ; `aspect-ratio: 1` en tirait
la largeur, et toute la grille passait à 144 px par case au lieu de 15.

Mesuré, pas déduit : `.grille-jours` faisait 310 px de large pour dix-neuf
colonnes de 144 px. Renommée en `creuse`, elle retombe à 15 px et la page ne
déborde plus.

Deux enseignements consignés. Un test refuse désormais qu'un nom serve à la
fois de modificateur (`actif`, `creuse`) et de composant — vérifié en échec
avec l'ancien nom. Et l'outil de captures **mentait** : il rendait la page dans
un moteur qui, lui, résolvait la grille correctement, et son effacement de
profil échouait en milieu de planche, laissant en place les images de la
veille sans le dire. Corrigé aux deux endroits. **736 tests.**


**23/08/2026 (25) — Une fiche du dictionnaire portait le nom de l'ossature**
Le nom d'un terme et son descriptif rendus d'un seul tenant, sans espace,
dans une carte trois fois trop haute. La fiche d'un terme s'appelait `corps` — le nom que porte
aussi le squelette de la page, dont la règle vaut pour la fenêtre entière :
`display: flex` et une hauteur calculée sur la hauteur disponible. La fiche en
héritait sans que rien ne le signale ; ses deux lignes devenaient deux colonnes
collées. `.terme .corps` ne redéfinissait pas `display`, donc la règle générale
gagnait.

Renommée en `.texte`. Un test refuse désormais qu'une fiche reprenne un nom de
l'ossature — vérifié en échec avec l'ancien nom.

Présentation revue au passage : « corrections » désignait deux choses sur la
même fiche (le nombre d'applications, et la liste des graphies fautives). La
seconde devient **« entendu comme »**, suivie de pastilles plutôt que d'une
énumération à virgules. **735 tests.**


**23/08/2026 (24) — Construite avec le mauvais Python, l'app était sourde**
Le raccourci Ctrl+Alt+D ne faisait plus rien. L'application tournait pourtant :
icône, tableau de bord, moteur Whisper chargé. Mesuré depuis l'extérieur —
`RegisterHotKey` sur les trois combinaisons réussit, donc **personne ne les
écoutait** : Murmur les avait rendues au système.

Trois défauts en chaîne, chacun invisible seul.

**La cause.** J'avais reconstruit avec le Python du système, pas celui du
projet. PyInstaller n'embarque que ce que trouve l'interpréteur qui le lance :
`sounddevice` manquait, sans le moindre avertissement.

**Le propagateur.** Au premier appui, l'import échoue. L'exception remontait
jusqu'à la boucle de messages des raccourcis, qui rendait **toutes** les
combinaisons en sortant — Windows lie une combinaison au fil qui l'enregistre.
Un seul rappel fautif suffisait à rendre l'application définitivement sourde.

**Le silence.** Compilée sans console, elle n'a aucune sortie d'erreur où
déposer la trace. `hotkeys` était le seul module sans journal — précisément
celui dont la panne ne laisse rien.

Quatre garde-fous. Un rappel qui lève est attrapé et journalisé, les autres
raccourcis survivent. Le veilleur reprend les raccourcis si le fil qui les
portait a disparu, quelle qu'en soit la cause. La construction refuse un
interpréteur qui n'a pas les modules vitaux, et **demande à l'exécutable
lui-même** (`--verifier`) s'il peut dicter avant de déclarer la construction
réussie — les modules en pur Python vivent dans l'archive embarquée, illisible
de l'extérieur. **733 tests.**


**23/08/2026 (23) — Une construction ratée a cassé l'installation**
La construction efface `dist/` avant de le refaire. Lancée alors que Murmur
tournait, elle a emporté une partie du dossier puis buté sur un fichier
verrouillé — laissant un `_internal` amputé de la moitié de son contenu.
L'exécutable était toujours là, il ne démarrait plus. Le journal accusait
pythonnet de ne pas trouver de runtime .NET : ses fichiers avaient simplement
disparu avec le reste.

Deux garde-fous. La construction vérifie d'abord qu'aucun Murmur ne tourne — un
exécutable en cours d'exécution refuse de s'ouvrir en écriture, cela suffit à le
savoir — et s'arrête **avant de toucher à quoi que ce soit**. Et l'effacement
ne se fait plus `ignore_errors=True` : un fichier verrouillé arrête la
construction au lieu de la laisser continuer sur un dossier à moitié vide.


**23/08/2026 (22) — « Enregistrer » pouvait n'enregistrer rien du tout**
L'analyse avait trouvé la correction — le journal dit *1 substitution(s),
0 proposée(s)*. Mais aucune case n'était cochée : la correction
obtenait **0,600** de ressemblance avec la dictée, sous le seuil de **0,82**
exigé d'un terme sans majuscule. Murmur l'a donc classé en reformulation, affiché décoché.

L'utilisateur a cliqué **Enregistrer**, la boîte s'est fermée, et le
dictionnaire est resté vide. Il a cherché ensuite où était passé son terme.

Le défaut n'est pas dans le classement — Murmur propose, il ne décide pas —
mais dans le bouton : l'action principale ne faisait rien **sans le dire**. Elle
le dit désormais, et laisse la boîte ouverte pour que la décision ne soit pas
perdue. **729 tests.**


**23/08/2026 (21) — On n'envoie pas un raccourci les doigts encore posés**
La boîte passait bien devant, cette fois — et montrait que le presse-papier
n'avait pas bougé, alors que la phrase était sélectionnée à l'écran. Le Ctrl+C
automatique ne prenait pas.

La cause tient au geste lui-même : l'apprentissage est déclenché par
**Ctrl+Alt+C**, et au moment où il s'exécute l'utilisateur tient encore Ctrl et
Alt. Le Ctrl+C envoyé arrive donc sur un clavier où Alt est enfoncé : le
système lit **Ctrl+Alt+C**, la combinaison de départ, et l'application ne copie
rien.

On ne peut pas relâcher une touche que quelqu'un tient. On attend donc qu'il la
lâche — le temps d'un clignement — avant de frapper, avec une limite d'une
seconde pour qu'une touche bloquée ne fige pas l'apprentissage. Les cinq
modificateurs sont surveillés, Maj et la touche Windows comprises : un
raccourci d'apprentissage peut les porter. **728 tests.**


**23/08/2026 (20) — Le message naissait derrière la fenêtre**
« Le raccourci ne fait rien » — et le journal montrait deux analyses menées à
bien. La boîte d'information s'affichait bel et bien, mais **derrière** la
fenêtre au premier plan : elle n'avait pas de parent. Celle qui propose les
substitutions se posait déjà « toujours au-dessus » ; seul ce message-là avait
été oublié.

Première mesure fausse au passage : j'ai relevé `GetForegroundWindow`, qui
restait le navigateur — Windows refuse le premier plan à un processus qui ne
l'a pas. Ce n'était pas le bon critère. Ce qui compte est le **plan
d'affichage** : une fenêtre marquée au-dessus se voit sans avoir le focus. En
la cherchant parmi les fenêtres du processus plutôt qu'en interrogeant le
focus, la mesure a répondu.

Trouvé aussi dans le journal : le presse-papier de l'utilisateur contenait
« ancien » — une valeur laissée par ma propre suite de tests, dont la fixture
de préservation avait fini par la propager. **724 tests.**


**23/08/2026 (19) — Ctrl+Alt+C copie la sélection lui-même**
Le raccourci envoie désormais un Ctrl+C à l'application avant de lire le
presse-papier : plus besoin de copier à la main après avoir corrigé. Réglable,
et coupé rend le comportement d'avant.

**Ctrl+A écarté, et l'essai a montré pourquoi.** La tentation était de tout
sélectionner quand rien ne l'est, pour n'avoir plus rien à faire. Mais
`SendInput` ne vise pas une fenêtre : il dépose la frappe dans la file de
**celle qui a le focus**, et Windows refuse le passage au premier plan à un
processus qui ne l'a pas. Au banc d'essai, le Ctrl+A est parti dans un autre
document et en a copié le contenu entier — un document personnel qui n'avait
rien à faire dans l'analyse. Ctrl+C sans sélection, lui, ne fait rien : c'est
exactement la prudence voulue. Les fonctions de « tout sélectionner » ont été
retirées, un test vérifie qu'elles ne reviennent pas.

Deux fautes de ma part au passage. Un ` ` mal échappé a écrit un **vrai
octet nul** dans le source — et un octet nul dans le presse-papier de Windows
l'aurait de toute façon vidé, la sentinelle passant alors pour une copie
réussie. Et une doublure de presse-papier rendait « du texte sans format »,
état qui n'existe pas : `vide` se lit sur la liste des formats, pas sur la
chaîne, d'où un défaut de restauration imaginaire.

Non vérifiable de mon côté : je ne peux pas prendre le focus au premier plan,
donc pas éprouver le geste réel. Le banc d'essai le dit franchement — « non
concluant, focus retenu par… » — plutôt que de rapporter un échec. La logique,
elle, est couverte sans matériel. **721 tests.**


**23/08/2026 (18) — « Texte identique » : nommer la vraie cause**
Le message était exact et pourtant incompréhensible. Le journal a tranché :
cinq secondes entre la dictée et le raccourci, et le presse-papier contenait
la dictée telle quelle. L'utilisateur avait bien corrigé — **dans le champ du
navigateur**, sans faire Ctrl+C. Or Murmur ne lit que le presse-papier, jamais
le champ de saisie : il y retrouvait ce qu'il venait d'y écrire pour le coller,
et comparait la dictée à elle-même.

C'est de loin le cas le plus fréquent, et « texte identique » laissait
l'utilisateur convaincu d'avoir corrigé — ce qu'il avait fait. Le message
nomme désormais la cause probable et montre ce qui a été lu. Un ancien test
qui vérifiait le mot « identique » a été retiré : le nouveau couvre le même
cas en exigeant davantage.

⚠️ Trouvé dans le journal au passage, **non corrigé** : `descripteur de fenetre
indisponible` au lancement du tableau de bord, avec `'Window' object has no
attribute 'winfo_id'`. `chrome.descripteur` retombe sur la branche Tk quand le
descripteur .NET n'est pas encore prêt, et l'erreur qui en sort désigne donc la
mauvaise cause. **717 tests.**


**23/08/2026 (17) — Le diagnostic dit maintenant ce qu'il a lu**
« Le texte copié est identique à une dictée » était exact mais opaque :
l'utilisateur ne pouvait pas savoir que c'était le texte NON corrigé qui se
trouvait dans le presse-papier. Le message en montre désormais le début. Un
presse-papier vide le dit franchement, au lieu de prétendre qu'aucune dictée
ne lui ressemble. **718 tests.**


**23/08/2026 (16) — L'apprentissage ne trouvait plus les longues dictées**
Une correction copiée revenait avec « aucune des 20 dernières dictées ne
ressemble au texte copié », alors que la dictée était bien là et ne différait
que d'un mot. Similarité mesurée : **0,093** au lieu de 0,979.

`SequenceMatcher` de `difflib` écarte de son index, au-delà de 200 éléments,
tout élément présent dans plus d'un pour cent de la séquence — l'heuristique
`autojunk`. Elle vise des **lignes** de code, où un élément fréquent est une
ligne répétée. Appliquée à des **caractères**, elle écarte l'espace, la
virgule, le point et quinze lettres : dix-huit des trente-six caractères
distincts du texte. L'algorithme ne peut plus amorcer ses correspondances que
sur les caractères rares, et le résultat dépend de l'endroit où tombe la
correction. Relevé sur les deux versions du même texte : d'un côté **deux
blocs communs dont un de 183 caractères**, de l'autre **cinq blocs dont le
plus long en fait 26**.

D'où un défaut qui frappe **par intermittence** au-delà de deux cents
caractères, et jamais en deçà — les dictées courtes fonctionnaient, ce qui l'a
rendu invisible pendant des semaines. Recherche sur quatre mille tirages : il
se déclenche dans 2,5 % des cas, le pire à 0,052 contre 0,978.

La comparaison **mot à mot** souffrait du même mal, sans que cela se voie :
au-delà de deux cents mots, « de », « que », « le » étaient écartés et le
découpage partait de travers — 279 substitutions absurdes là où il en fallait
une. Les deux appels reçoivent désormais `autojunk=False`.

Trois des quatre tests ajoutés échouent si l'on remet le comportement par
défaut ; le quatrième fixe une propriété plus large. **714 tests.**

À savoir : le terme de l'essai reste **proposé décoché**, sa parenté avec
la dictée n'étant que de 0,60 contre 0,82 exigés sans majuscule. C'est
le compromis assumé — sans cette exigence, de simples reformulations
entreraient au lexique. Il suffit de cocher la case.


**23/08/2026 (15) — Données de démonstration et captures**
Deux outils, `outils_demo.py` et `outils_captures.py`. Le premier peuple un
dossier de données **à part** — jamais celles de l'utilisateur, qui contiennent
ses vraies dictées — avec 1 049 dictées sur 170 jours, onze termes et leurs
corrections. Le tirage part d'une graine fixe : deux exécutions donnent les
mêmes images, faute de quoi aucune capture ne se compare à la précédente. Les
données sont volontairement irrégulières — jours creux, week-ends calmes,
préférence marquée pour une application, pointe le dernier mois : une activité
uniforme donnerait un calendrier sans relief et des barres toutes égales, qui
ne montreraient rien de ce que la page sait faire.

Le second rend les pages **hors écran**, dans un navigateur sans fenêtre. La
voie évidente — poser la vraie fenêtre au premier plan et photographier le
rectangle qu'elle occupe — a été essayée et doit être proscrite : Windows
refuse le passage au premier plan à un processus qui n'a pas la main, si bien
que la photo garde ce qui se trouvait à l'écran. Elle a rendu ce que l'utilisateur
avait sous les yeux ; les images ont été effacées aussitôt. Ce
qu'on perd au rendu hors écran, ce sont les coins arrondis et l'ombre que
Windows compose autour de la fenêtre — la barre de titre, elle, appartient à
la page et figure bien.

Six captures produites (quatre pages en clair, deux en sombre) et l'entrée du
portfolio reprise autour d'elles.


**23/08/2026 (14) — Noir franc et rouge vif**
Les commandes de fenêtre passent du gris intermédiaire au noir du texte —
contraste mesuré de 12,2 contre 1 sur la barre. En demi-teinte, elles se
lisaient comme désactivées.

Le rouge de fermeture passe de `#e3453a`, une brique à 75 % de saturation, à
`#e81123` à 93 %. Il devient au passage un jeton nommé (`--rouge`) plutôt
qu'une valeur recopiée en trois endroits : la croix de fermeture, la
suppression d'une dictée et les messages d'erreur disaient la même chose et
pouvaient diverger. Éclairci en thème sombre, où le même rouge perdrait sa
vivacité. Blanc sur rouge : 4,6 contre 1. **710 tests.**


**23/08/2026 (13) — Les commandes de fenêtre, deuxième passe**
Comparaison côte à côte avec la référence : mon premier agrandissement ne
touchait qu'à la taille de la boîte, alors que trois choses les séparaient.
Le dessin passe de 9 à 14 px, le trait de 1,5 à 2 px, et la teinte du gris
pâle au gris du texte — en demi-teinte, les commandes se lisaient comme
désactivées. La surface visée ne bouge toujours pas : 46 × 52 px.

Mesures après un dernier cran en arrière, sur retour : barre de 13,5 px, carré
de 12,7, croix de 11,2, trait de 1,8 px exactement dans les trois.
**710 tests.**


**23/08/2026 (12) — Les commandes de fenêtre**
Glyphes portés de 12 à 16 px — le dessin utile passe de 7 à 9 px, la taille de
ceux que Windows dessine lui-même. La surface visée ne bouge pas : elle était
déjà bonne, à 46 × 52 px. L'épaisseur de trait descend de 1,8 à 1,5 pour que
l'agrandissement ne les rende pas gras. **710 tests.**


**23/08/2026 (11) — Ouverture du tableau : 4,3 s ramenées à 1,2 s**
Deux dépenses, dont la plus grosse ne se voyait pas.

**Deux secondes perdues à frapper à une porte fermée.** Avant de lancer le
tableau, l'application demandait au canal si un tableau tournait déjà. Or
frapper à une porte fermée sur la boucle locale n'est pas *refusé* ici : les
paquets sont avalés — sans doute par le pare-feu — et la connexion **expire**.
Chaque ouverture commençait donc par le délai complet, deux secondes, pour
constater une absence. Le délai de connexion est maintenant distinct de celui
de réponse : « y a-t-il quelqu'un » se tranche en quelques millisecondes sur
la boucle locale — six, mesurées —, tandis que « voici ta réponse » peut
attendre une application occupée à transcrire. Et l'on ne frappe plus du tout
quand on sait qu'aucun tableau ne tourne, ce que `Popen.poll` dit sans rien
demander au réseau.

**Une seconde d'extraction à chaque lancement.** L'exécutable « un seul
fichier » porte son contenu compressé et le réextrait dans un dossier
temporaire à chaque démarrage. Le tableau de bord étant un second exemplaire
du même exécutable, il payait cette extraction une seconde fois. Mesure sur
trois tours, du lancement à la fenêtre répondante :

    un fichier   2 200 à 2 370 ms   dont 1 400 à 1 560 avant Python
    un dossier   1 130 à 1 760 ms   dont   310 à  450 avant Python

Le dossier est exactement aussi rapide qu'un lancement depuis les sources.
L'application y gagne aussi de n'être plus qu'**un seul processus** au lieu de
deux, l'amorce du fichier unique disparaissant avec lui.

Total mesuré depuis l'application, trois fois de suite : **1 228 à 1 236 ms**,
contre 3 233 avant le premier correctif et environ 4 300 avant les deux. Un
tableau déjà ouvert se montre en 2 ms.

Ce qui reste — 310 ms de Python, 790 ms de WebView2 — est le plancher de
Chromium. Un profil persistant a été essayé et mesuré : aucun gain (776 à
1 082 ms contre 830 en moyenne), et deux processus partageant le même dossier
de profil se gêneraient. Écarté.

Le dossier de distribution passe de `dist/Murmur.exe` à `dist/Murmur/`. Le
raccourci du menu Démarrer est refait ; un éventuel épinglage à la barre des
tâches est à refaire une fois. **710 tests.**


**23/08/2026 (10) — Le survol : une seule forme, pas trois**
Le contour ajoute au survol etait pose a un pixel du bord de la case : on
lisait donc la case, un trou, puis un trait flottant autour. Trois formes la
ou il n'en fallait qu'une. Le contour est retire — la case grossit, et rien
d'autre. **699 tests** (le test d'injection s'est declare non concluant, le
focus etant retenu par une fenetre du systeme : c'est son garde-fou qui parle,
pas un echec).


**23/08/2026 (9) — La case survolée avait besoin d'air**
Elle grandit d'un tiers au survol, et la grille — qui masquait encore son
débordement — la tronquait : les cases de bord n'en montraient qu'une moitié.
Le masquage n'a plus lieu d'être depuis que la largeur commande la hauteur,
la grille ne pouvant plus déborder d'elle-même. La marge de la carte absorbe
largement les quelques pixels du survol.

Mesuré sur les quatre coins de la grille, là où le rognage se voyait : 19 px
au repos, 24 px au survol, entièrement dans la carte, avec 18 px de marge au
plus serré. La case survolée passe aussi au-dessus de ses voisines — agrandie,
elle glissait sous celles qui la suivent et son contour s'en trouvait mangé.
**700 tests.**


**23/08/2026 (8) — Le calendrier se rognait lui-même**
Les jours actifs avaient disparu, et pour une raison que la mesure seule
pouvait donner : la grille **débordait de sa carte par la droite**, où
`overflow: hidden` la rognait. Or elle se lit de gauche à droite — ce sont
précisément les jours les plus récents qui passaient à la trappe.

La cause tient à un ordre. J'avais étiré les cases sur la hauteur disponible,
puis demandé qu'elles soient carrées : elles tiraient donc leur **largeur** de
leur hauteur, sans égard pour la place réelle des colonnes. C'est l'inverse
qu'il faut — la largeur commande, la hauteur suit. Les cases font 19 px, la
grille s'arrête à un pixel de la marge, et les quatre jours actifs sont
visibles.

L'étendue passe de vingt-deux à dix-huit semaines : le nombre de colonnes et
la taille des cases sont le même réglage vu de deux côtés, et les flèches de
la carte donnent accès au reste de l'histoire. Paliers intermédiaires
assombris pour qu'un jour à un mot se distingue d'un jour vide.

Le liseré clair autour de la fenêtre était la bordure que Windows peint : la
teindre de la couleur du fond ne la fait pas disparaître, elle reste visible
contre le bureau et contre le rouge du bouton de fermeture. Seule la valeur
réservée « aucune couleur » la supprime. L'attribut étant en écriture seule —
le relire rend « paramètre incorrect » —, le test observe la demande faite à
Windows et non son résultat.

Le lien des réglages est aussi noir que les onglets. **700 tests.**


**23/08/2026 (7) — Le repli, le calendrier, deux pictogrammes**
Les pictogrammes bougeaient bel et bien au repli de la barre, et ma mesure
précédente ne le voyait pas : je relevais leur abscisse, or le déplacement
était **vertical**. Chaque onglet perdait 1,93 px quand son libellé
disparaissait — une ligne de texte de 13 px est plus haute qu'une icône de
20 px, et tout ce qui suit remontait d'autant, cumulativement. Les lignes ont
maintenant une hauteur fixe. Mesuré sur les cinq pictogrammes : déplacement
nul dans les deux axes.

Calendrier d'activité : cases carrées de 20 px au lieu de 12, écart ramené de
4 à 2 px, et la carte s'organise en colonne pour que la grille prenne ce qui
reste sous le titre. Le vide en bas de l'encart passe de la moitié de sa
hauteur aux 21 px de sa marge.

Pictogramme Insights complété de son axe des abscisses, et les trois curseurs
des réglages remplacés par une roue dentée. **698 tests.**


**23/08/2026 (6) — Le micro : ce n'était pas l'échec que je croyais**
Le journal a tranché : `rms 0.0000`, capture après capture. Le flux **s'ouvrait
sans la moindre erreur** et rendait du silence — ma correction précédente, qui
ré-énumérait les périphériques après un échec, ne se déclenchait donc jamais.
Il n'y avait rien à rattraper.

La cause est l'interface audio. Windows en expose quatre ; PortAudio choisit
**MME** par défaut, et MME travaille sur une table de périphériques figée au
chargement. FxSound qui interpose son entrée virtuelle laisse cette table
périmée : le flux s'ouvre sur une entrée qui n'existe plus vraiment et rend
des zéros. Mesuré sur la machine : MME et DirectSound acceptent 16 kHz,
**WASAPI les refuse** — « Invalid sample rate » — parce qu'il impose le taux
natif de la carte, 48 kHz.

On passe donc par WASAPI, qui suit le périphérique par défaut du système, et
l'on rééchantillonne vers 16 kHz. Le filtre anti-repliement n'est pas un
raffinement : sans lui, tout ce qui dépasse 8 kHz ne disparaît pas mais se
**replie** dans la bande de la parole. Mesuré : un 12 kHz réduit sans filtre
garde toute son énergie et réapparaît à 4 kHz ; avec le filtre, il est atténué
d'un facteur 300. Ouverture mesurée à 71 ms contre 163 ms en MME.

Ce que je n'ai pas pu prouver : que WASAPI capte bien la voix. Le micro était
muet pendant tous mes essais — WASAPI rend des zéros exacts là où MME rendait
un bit de bruit. La chaîne est vérifiée jusqu'au bout (durée exacte,
rééchantillonnage juste), la captation elle-même reste à confirmer à l'usage.
D'où l'ajout d'un **sélecteur de microphone** dans les réglages : onze entrées
listées, énumérées à chaque ouverture, et le choix l'emporte sur toute
heuristique.

Trois retouches d'affichage : pictogramme Insights repris une troisième fois
(un trait plein et deux barres évidées), ombre de la jauge retirée, légende du
calendrier retirée. Et les pictogrammes ne bougent plus d'un pixel au repli de
la barre — mesuré à 20 px du bord dans les deux états, déplacement nul.
**698 tests.**


**23/08/2026 (5) — « Quitter » ne quittait pas**
Deux causes cumulées, toutes deux muettes.

`after` de Tk n'est **pas sûr entre fils** : appelé depuis le fil de l'icône,
il écrit dans les structures de l'interpréteur Tcl pendant que la boucle les
lit, et le plus souvent la demande est simplement perdue. Le menu répondait,
l'icône disparaissait, l'application continuait de tourner. Tout ce qui vient
d'un autre fil — arrêt, réglages repris, boîte de correction — passe désormais
par une file que seule la boucle principale vide. Mesuré : 59 ms entre la
demande venue d'un autre fil et le retour de `mainloop`.

Ensuite, `_quitter` de l'icône appelait `arreter`, qui attend la fin du fil de
l'icône — c'est-à-dire le fil courant. Python refuse de joindre le fil courant
et lève ; l'exception se perdait dans pystray.

Et même arrêtée, l'application laissait le **tableau de bord** ouvert : il vit
dans son propre processus et ne meurt pas avec elle, gardant une fenêtre et un
« Murmur.exe » dans la liste des tâches après qu'on a demandé à quitter — ce
qui se lit, à juste titre, comme un refus de se fermer. L'arrêt lui envoie
maintenant une commande de fermeture. Vérifié sur l'exécutable : quatre
processus avant, deux après.

Les boucles de glisser sont bornées à soixante secondes. Elles repositionnent
la fenêtre cent quarante fois par seconde et gardent un aperçu au-dessus de
tout ; bloquées, elles rendraient le bureau inutilisable — ni Alt+Tab ni la
vue des tâches ne passent devant une fenêtre toujours au premier plan.

Pictogramme Insights repris : quatre barres pleines sans crochets. **684
tests.**

Non reproduit : le blocage d'Alt+Tab. Relevé pendant que l'application et le
tableau tournaient — aucune fenêtre de Murmur au premier plan, aucune qui ne
réponde plus, aucun modificateur resté enfoncé.


**23/08/2026 (4) — Insights refondu, deux pannes muettes, exécutable**
Quatre défauts trouvés, dont deux qui ne disaient rien.

Le premier expliquait à lui seul la double barre de titre, le glisser inerte
et l'ancrage absent : `native.Handle` de pywebview n'est pas un entier Python
mais un `IntPtr` .NET, et `int()` sur cet objet lève une `TypeError`. Chaque
appelant enveloppant la conversion dans un garde-fou, l'échec se lisait comme
« le système a refusé » — **toute la couche `cadre` était morte depuis la
bascule**. Le test qui prétendait la couvrir passait parce que sa doublure
exposait un entier ordinaire, plus accommodant que le vrai. La doublure refuse
désormais `int()`, comme l'original.

Le second : PyInstaller écarte de son analyse les modules nommés `__main__` à
l'intérieur d'un paquet, les confondant avec le script d'entrée. L'exécutable
se construisait sans une erreur et tombait au lancement sur « No module named
'murmur.__main__' » ; le déclarer en import caché n'y change rien. Le corps du
programme vit maintenant dans `lancement.py`, de part et d'autre, et
`__main__.py` n'est qu'une amorce de trois lignes.

Le mode sombre ne s'appliquait jamais : le pont envoyait la **préférence**
(« auto »), que la page ne sait pas résoudre — elle ne lit pas le réglage de
Windows. Il envoie désormais le thème résolu, et la page le réapplique après
un enregistrement. La barre latérale repliée ne montrait plus rien : les
libellés gardaient leur largeur sous une opacité nulle et, la ligne interdisant
le retour à la ligne, écrasaient le pictogramme jusqu'à le faire disparaître.

Micro : PortAudio dresse la liste des périphériques **une fois**, à son
chargement. Tout ce qui la remanie ensuite — un égaliseur comme FxSound et son
périphérique virtuel, un casque qui se reconnecte — la laisse périmée, et
l'ouverture échoue alors que le micro est disponible. La liste est refaite
après un échec, puis on retombe sur le micro par défaut si celui qui était
choisi a disparu.

Page Insights réorganisée d'après la référence : une seule grille de quatre
colonnes pour les deux rangées. Calendrier d'activité refait en cinq paliers
discrets avec légende et infobulle, et paginable vers le passé ; jauge de
vitesse dotée d'anneaux de halo épousant la portion remplie. L'heure des
dictées est centrée sur la hauteur de sa ligne.

Un test d'injection appelait l'injecteur **depuis** la boucle de messages de
la fenêtre cible : le Ctrl+V déposé par `SendInput` ne pouvait être traité
qu'après le retour de l'appel, donc après la restauration du presse-papier —
il collait l'ancien contenu. Il injecte maintenant depuis un fil séparé, comme
en usage réel. **678 tests.**

`dist/Murmur.exe` construit et vérifié : 37 Mo, la page embarquée, et la
fenêtre du tableau relevée sans bandeau mais avec cadre épais et bouton
d'agrandissement.


**23/08/2026 (3) — Bascule : la fenêtre Tk retirée**
Le tableau de bord Tkinter est supprimé (2 140 lignes) au profit de la fenêtre
WebView2, désormais atteinte par l'icône près de l'horloge comme par le menu
Réglages. Elle est lancée en processus séparé, avec son propre verrou : deux
clics ne donnent pas deux fenêtres — celle qui tourne déjà se montre sur la
page demandée. Le même exécutable porte les deux rôles, aiguillés par
`--tableau`, parce qu'empaqueté il n'y a pas d'autre programme à viser.

La boîte de validation d'un apprentissage est extraite dans son propre module
plutôt que supprimée avec le reste : elle apparaît pendant qu'on travaille
ailleurs, sur une pression de raccourci, et lancer une douzaine de processus
WebView2 pour trois cases à cocher coûterait plus cher que tout ce qu'elle
affiche. C'est la seule fenêtre encore dessinée par Tk.

La conscience du DPI est enfin déclarée dans l'application : à 125 %, Windows
ne dessine plus à 100 % pour étirer ensuite. Tk est mis à l'échelle, et la
barre de dictée — peinte pixel par pixel par Pillow — est redessinée à sa
taille réelle : 39 px de haut au lieu de 31, toute sa géométrie découlant
d'une seule constante. Le fichier de construction embarque les fichiers de la
page et déclare les greffons chargés par leur nom, deux oublis qui ne se
seraient vus qu'à l'exécution de l'exécutable.

Mesures : le tableau de bord ouvert pèse quinze processus et 374 Mo de mémoire
privée (995 Mo de working set brut, pages partagées comprises) — d'où la
décision de le faire mourir avec sa fenêtre. Le processus Python se dédouble,
mais c'est pywebview qui le fait : un pywebview nu, sans une ligne de Murmur,
donne les deux mêmes processus, dont un talon de 6 Mo.

Un test de glisser dépendait de la position **réelle** de la souris : posée
par hasard contre un bord de l'écran, elle armait une zone d'ancrage et la
fenêtre finissait ancrée au lieu d'être déplacée. Le test a d'abord semblé
dénoncer un défaut du code. **665 tests.**


**23/08/2026 (2) — Le cadre de la fenêtre, page Réglages, canal branché**
La fenêtre ne se redimensionnait ni ne s'ancrait aux bords. Cause : elle
naissait en mode « sans cadre » de pywebview, qui passe la fenêtre en
`FormBorderStyle.None` et emporte **aussi** le cadre épais — donc les poignées
de bord et l'agrandissement. Rendre `WS_THICKFRAME` après coup ne tient pas :
WinForms réimpose ses `CreateParams` au premier recalcul de cadre. La voie
inverse, déjà éprouvée dans une autre application maison, est reprise dans un module neuf
`cadre.py` : fenêtre **ordinaire**, puis retrait du seul `WS_CAPTION`, et
procédure de fenêtre dérivée pour récupérer les pixels de cadre restés en
haut. Le déplacement et l'ancrage (moitiés, quarts, plein écran, avec aperçu
translucide) sont menés côté Python, WebView2 ne relayant aucun message de
souris non client vers la fenêtre hôte.

Page **Réglages** portée : le formulaire est décrit en Python (`donnees.CHAMPS`)
et non dans la page, donc vérifiable sans ouvrir de fenêtre ; validation avant
écriture, sélecteurs segmentés et interrupteurs dessinés par la page. Le canal
est enfin branché des deux côtés : un raccourci ou un terme modifié depuis le
tableau de bord est repris à l'instant par l'application.

Quatre corrections d'affichage : nom d'application collé à sa barre, hauteur
des dictées rendue au texte (les boutons fixaient un plancher de 74 px pour
une ligne de 20), pictogramme Insights redessiné, plancher des petites barres
abaissé pour que 18 % ne se lise plus comme 1 %.

Deux défauts trouvés à la mesure, tous deux invisibles à l'œil : le processus
de test n'était pas conscient du DPI, si bien que Windows lui rendait des
pixels virtualisés d'un côté et réels de l'autre — un quart d'écart à 125 % ;
et `GetModuleHandleW`, déclarée sans `restype`, tronquait le descripteur de
module à 32 bits, ce qui faisait tomber `RegisterClassW` sur une violation
d'accès avalée par le garde-fou : l'aperçu d'ancrage ne s'affichait jamais,
sans un mot dans le journal. Le même défaut dort dans le module équivalent d'une autre application.
**685 tests.**


**23/08/2026 — Portage WebView2 : canal, données, processus séparé**
Décision : le tableau de bord devient un processus autonome, lancé à la
demande. Canal de commande sur la prise du verrou d'instance (11 tests),
couche de données testable sans fenêtre (26 tests), garde-fou des sorties
extrait pour être partagé, module de conscience du DPI prêt. La fenêtre
elle-même ne s'ouvre pas encore depuis mes lancements — la maquette non plus,
alors qu'elle fonctionnait le matin, ce qui écarte le nouveau code.
**623 tests.**


**21/08/2026 (7) — Ordre des dictées, symbole lissé, repli animé**
Deux dictées d'une même seconde sortaient dans le désordre : l'identifiant les
départage. Le symbole de la barre latérale passait par le canevas de Tk, qui
ne lisse rien — il est rendu en image comme partout ailleurs. Le repli de la
barre glisse sur cent cinquante millisecondes et se renverse à mi-course.
Cartes d'usage et d'activité agrandies, pourcentages centrés. Trois limites
consignées plutôt que contournées : dégradé impossible derrière des widgets
Tk, rendu de texte lié à GDI, bande claire non reproductible. **579 tests.**


**21/08/2026 (6) — Anglais, pictogrammes au trait, quatre défauts**
Interface traduite (anglais par défaut, vocabulaire de la référence, choix de
la langue dans les réglages), pictogrammes d'usage retracés au trait à la
place des emoji en couleur, marque rétablie en haut de la barre latérale,
jauge à bouts arrondis, barres d'usage sans piste. Quatre défauts reproduits
par un script de diagnostic puis corrigés : bande claire au-dessus de la barre
de titre, calendrier privé de sa colonne du jour, pied de page figé hors de
l'historique, menu de l'icône sans effet sur « Réglages ». **574 tests.**


**21/08/2026 (5) — Mise à l'échelle sur Wispr Flow**
Comparaison côte à côte des deux fenêtres : barre de titre, marges, tailles de
titres, hauteur des lignes et des cartes alignées sur la référence. Jauge
centrée sous son chiffre avec le rapport au clavier en son creux, calendrier à
sept jours libellés et mois au-dessus. Trois défauts de texte corrigés
(tendance tronquée, accord sur un mot capitalisé, abréviations de mois
ambiguës). Démarrage avec Windows activé, après correction de la commande
inscrite, qui visait l'interpréteur même une fois l'application empaquetée.
**573 tests.**


**21/08/2026 (4) — Fenêtre sans bandeau, palette Wispr, emoji en couleur**
La barre de titre du système est retirée (`WS_CAPTION`) et remplacée par celle
de l'application, cadre redimensionnable conservé. Palette reprise de Wispr
Flow. Carte Applications refaite : regroupement sur le programme et non sur le
titre de fenêtre, noms d'usage, emoji rendus en couleur par Pillow. Pages
construites hors écran puis posées d'un bloc ; liste des dictées mise à jour
par insertion. Deux dérives de géométrie trouvées par les tests, corrigées en
plaçant la fenêtre par `SetWindowPos`. **570 tests.**


**21/08/2026 (3) — Panneau central, volet et indicateurs**
Troisième passe sur l'interface, sur retour et captures : panneau arrondi
détouré du bord, barre latérale repliable, logo retiré de la barre (doublon
avec la barre de titre), cases à cocher redessinées, symbole et pictogrammes
suréchantillonnés ×8, champs sans filet. Page Statistiques enrichie
— applications, corrections, tendance mensuelle, calendrier d'activité — et
mise à jour sur place pour supprimer le clignotement. **544 tests.**


**21/08/2026 (2) — Interface arrondie et barre de titre intégrée**
Deuxième passe sur l'interface : coins arrondis partout via des coins dessinés
par Pillow, barre de titre teintée par Windows 11 plutôt que fenêtre sans
cadre, graphe d'activité redessiné en barres à sommets arrondis, alerte
d'enregistrement supprimée. Deux régressions trouvées à la mesure : ouverture
de l'onglet Dictées à 2,5 s (corrigée par pagination, 450 ms) et cache
d'images survivant à son interpréteur Tcl. **527 tests.**


**21/08/2026 — Raccourcis à chaud et refonte de l'interface**
Les raccourcis modifiés dans les réglages prennent désormais effet immédiatement,
avec rétablissement de l'ancien jeu si la nouvelle combinaison est déjà prise.
Interface refondue : barre latérale à pictogrammes, réglages sortis en fenêtre
propre, palette alignée sur l'app Notes, recherche instantanée, histogramme
d'activité. Trois défauts de rendu propres à Tk sur fond sombre corrigés
(cases à cocher, boutons radio, ascenseur), ainsi que deux fautes d'accord.
**496 tests.**


**19/08/2026 — Bench de faisabilité et spécification**
Validation que le backend Vulkan de whisper.cpp fonctionne sur Radeon RX 9070 XT,
alors qu'aucun binaire Vulkan précompilé n'est distribué par le projet — il a fallu
installer la toolchain complète et compiler. Trois incidents rencontrés et résolus,
consignés dans le journal du bench. Spécification rédigée et quatre décisions de
conception arrêtées.

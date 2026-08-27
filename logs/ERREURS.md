# Journal d'incidents — Murmur

Le journal du bench préalable est séparé :
[../../WhisperBench/logs/ERREURS.md](../../WhisperBench/logs/ERREURS.md)

---

## 1. Un tiret cadratin casse le parsing d'un script PowerShell

**Message exact**

```
Spécification de fichier manquante après l'opérateur de redirection.
L'opérateur « < » est réservé à une utilisation future.
Le terminateur ' est manquant dans la chaîne.
```

**Contexte** — validation syntaxique de `spikes/t0_2_lexique/enregistrer.ps1`.
Les erreurs pointaient la ligne 59, `Write-Host "  >>> PARLE MAINTENANT <<< "`,
alors que cette ligne est parfaitement valide.

**Diagnostic** — trois fausses pistes avant la bonne :

1. Le `` `r `` de la ligne 56 : testé isolément, parse sans erreur.
2. Les chevrons `>>>` de la ligne 59 : testés isolément, parsent sans erreur.
3. La regex ligne 16, seule ligne à nombre impair de guillemets : parse sans erreur.

Le signal décisif : `Parser::ParseInput` sur le contenu lu avec
`Get-Content -Encoding UTF8` **réussit**, alors que `Parser::ParseFile` sur le même
fichier **échoue**. La différence entre les deux n'est pas le contenu, c'est le
décodage. Le problème était donc l'encodage, pas la syntaxe.

**Cause** — le fichier était en UTF-8 **sans BOM**. PowerShell 5.1 lit alors le script
en Windows-1252. Le tiret cadratin `—` vaut `E2 80 94` en UTF-8 ; relu octet par octet
en CP1252, le dernier octet `0x94` devient `”` (U+201D). Or **PowerShell accepte les
guillemets typographiques comme délimiteurs de chaîne**. Le tiret, situé ligne 28 dans
un `Write-Host`, ouvrait donc une chaîne fantôme qui se refermait trente lignes plus
bas sur le guillemet des chevrons — d'où des erreurs signalées très loin de la cause.

**Remédiation** — suppression de tout caractère non-ASCII du script
(`sed 's/\xe2\x80\x94/-/g'`). Résolu, `ParseFile` passe.

**Règle retenue pour le projet** — tout fichier `.ps1` doit être **en ASCII pur**, ou
enregistré en UTF-8 **avec BOM**. Les caractères typographiques (`—`, `«` `»`, `’`)
n'ont rien à faire dans un script PowerShell : ils appartiennent aux données, pas au
code. Les textes accentués destinés à l'affichage sont donc stockés dans les fichiers
JSON, lus explicitement avec `-Encoding UTF8`.

`WhisperBench/record.ps1` a été vérifié : il ne contient aucun caractère non-ASCII et
n'est pas affecté.

**Vérification à intégrer** — avant d'exécuter tout `.ps1` produit :

```
LC_ALL=C grep -n '[^ -~]' script.ps1     # doit ne rien retourner
```

---

## 2. Test T0.3 biaisé : un « silence » qui contenait de la parole

**Symptôme** — premier passage de `tester_vad.py` : le segment censé être du silence
micro produisait une phrase entiere, plausible et inventee, y compris avec le VAD actif. Le
script en concluait automatiquement que **la protection native ne suffisait pas**, et
proposait d'inscrire cette phrase dans la liste noire des hallucinations.

**Contexte** — j'avais extrait le silence en supposant que la lecture du texte durait
~22 s sur un enregistrement de 30 s, et prélevé le segment 25-30 s.

**Cause** — supposition non vérifiée. `silencedetect` montre que la parole s'arrête à
**26,4 s**, pas 22 s. Le segment contenait donc 1,4 s de parole réelle : la
transcription était **correcte**, et le VAD faisait exactement son travail.

**Conséquences si l'erreur était passée** — trois décisions fausses en cascade :
la protection native jugée insuffisante, une phrase parfaitement légitime
(une transcription parfaitement correcte) inscrite en liste noire — donc censurée à jamais dans
les vraies dictées — et les couches maison requalifiées d'indispensables alors
qu'elles sont une défense en profondeur.

**Remédiation** — le script détecte désormais la fin de parole avec `silencedetect`
au lieu de la supposer, et n'utilise le cas « silence micro » que si une zone muette
terminale d'au moins 1 s existe réellement. Après correction : 3/3 hallucinations sans
protection, 0/3 avec. Résolu.

**Règle retenue** — un test dont le résultat contredit l'attendu doit d'abord être
soupçonné lui-même. Ici, le signal d'alarme était disponible : la phrase « inventée »
était trop cohérente avec le texte lu pour être une hallucination.

---

## 3. Le moteur survivait à l'application et bloquait le port

**Message exact**

```
Demarrage impossible : le port 8642 est deja occupe. Une autre instance de
Murmur tourne peut-etre, ou un autre programme utilise ce port.
```

**Contexte** — premier lancement réel de J1. La première session a fonctionné ; la
suivante a refusé de démarrer. Un `whisper-server.exe` du lancement précédent tenait
toujours le port.

**Cause** — sur Windows, un processus enfant ne meurt pas avec son parent. L'arrêt
propre du moteur vivait dans un `finally`, qui ne s'exécute pas quand la console est
fermée par la croix ou que le processus est tué. Le moteur restait donc vivant,
invisible, à occuper le port — et le message d'erreur accusait « une autre instance »
alors que le vrai coupable était notre propre négligence.

**Remédiation** — deux mécanismes complémentaires :

1. **Job object** (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`). Le moteur est rattaché à un
   job dont le handle se ferme automatiquement à la disparition du parent, quelle
   qu'en soit la cause. Le moteur meurt donc avec l'application, y compris sur un
   arrêt brutal. Vérifié par un test qui tue le parent au `kill()` et contrôle que
   l'enfant disparaît.
2. **Récupération au démarrage.** Si le port est pris, on identifie les
   `whisper-server` issus de notre propre dossier `engine/` et on les termine. Un
   binaire homonyme lancé par autre chose n'est jamais touché.

**Deux pièges rencontrés en corrigeant :**

- La première version énumérait les processus avec `wmic`, **absent des Windows 11
  récents**. La fonction renvoyait donc toujours une liste vide et le nettoyage ne
  faisait rien, *en silence*. Remplacé par `K32EnumProcesses` +
  `QueryFullProcessImageNameW`, et couvert par un test qui échoue si l'énumération ne
  voit même pas notre propre processus.
- Le port peut rester indisponible une seconde ou deux après la mort du serveur, des
  connexions HTTP restant en `TIME_WAIT`. Un redémarrage rapide échouait alors sans
  qu'aucun processus ne soit en cause. Ajout d'un réessai, et le message distingue
  désormais « des orphelins ont été terminés mais le port reste pris » de « aucun
  moteur à nous ne le détient : un autre programme l'utilise ».

**Règle retenue** — tout processus enfant lancé par l'application doit être rattaché à
un job suicidaire dès sa création. Compter sur un `finally` pour nettoyer, c'est
supposer une sortie propre — précisément ce qui n'arrive pas quand ça compte.

---

## 4. L'interpréteur tombe en journalisant des tracebacks en boucle

**Message exact**

```
Windows fatal exception: code 0x80000003
Current thread ... Garbage-collecting
  File "...tokenize.py", line 358 in detect_encoding
  File "...logging/__init__.py", line 670 in formatException
  File "...murmur/app.py", line 242 in _surveiller
```

**Contexte** — exécution de la suite complète après T2.4. pytest s'interrompt
(code 3, puis 255) sans qu'aucun test n'échoue. Le crash survient pendant
`test_la_surveillance_survit_a_une_exception`.

**Cause** — le fil de surveillance appelait `self._log.exception(...)` **à chaque tour
de boucle** tant que l'erreur persistait. Formater un traceback lit les fichiers
source via `linecache` et `tokenize` ; répété en boucle serrée depuis un fil
secondaire, pendant que le ramasse-miettes travaille, cela suffit à faire tomber
l'interpréteur.

Ce n'était donc pas un défaut de test mais un **défaut de conception** : en
production, une panne durable du moteur aurait écrit un traceback complet toutes les
deux secondes, gonflant le journal jusqu'à saturer sa rotation — et effaçant au
passage les traces utiles qui l'auraient précédée.

**Remédiation**

1. Une seule trace complète par série de pannes, remise à zéro dès que le moteur
   redevient sain — même logique que l'alerte utilisateur, déjà en place.
2. Fixture `journal_isole` (autouse) qui détache le journal entre chaque test. Sans
   elle, le gestionnaire de fichier restait ouvert sur le dossier temporaire du
   *premier* test, supprimé depuis : écrire dans un descripteur pointant sur un
   dossier disparu produit des défaillances erratiques, très loin de leur cause.

**Règle retenue** — dans une boucle de surveillance, journaliser une exception est un
événement, pas un état. Ce qui se répète à chaque tour doit être compté, pas réécrit.

---

## 5. « tk wasn't installed properly » — plusieurs interpréteurs Tcl

**Message exact**

```
ERROR tests/test_fenetre.py::test_une_liste_vide_affiche_une_invitation
E   This probably means that tk wasn't installed properly.
```

**Contexte** — apparu après l'ajout des tests de la fenêtre principale, alors que
`test_fenetre.py` passait seul et que Tk était évidemment bien installé.

**Cause** — deux fichiers de test créaient chacun leur `tk.Tk()`. Tkinter tolère mal
plusieurs interpréteurs Tcl successifs dans un même processus : après quelques
créations et destructions, la suivante échoue sur un message qui accuse
l'installation alors que le problème est le cycle de vie.

**Remédiation** — une fixture `racine_tk` de portée session fournit l'unique `Tk()`,
et les tests créent des `Toplevel` dessus. Le test d'injection utilise désormais
`quit()` puis `destroy()` au lieu de détruire la racine partagée.

**Règle retenue** — un seul `Tk()` par processus, y compris dans les tests.

---

## 6. Fausse piste — un résumé pytest « manquant »

Pendant l'investigation du crash n°4, j'ai cru à une perte du tampon de sortie parce
que le résumé final de pytest n'apparaissait jamais. J'ai comparé des exécutions,
capturé la sortie dans des fichiers, inspecté les octets bruts.

**La cause était triviale** : `pytest.ini` contient déjà `-q` dans `addopts`, et
j'ajoutais un second `-q` en ligne de commande. Deux `-q` suppriment le résumé — le
comportement documenté de pytest.

**Règle retenue** — avant de conclure qu'un outil se comporte anormalement, vérifier
les options qu'on lui passe réellement, en comptant celles qui viennent de sa
configuration. Le symptôme observé était réel ; l'anomalie n'existait pas.

---

## 7. Un handle Windows tronqué à 32 bits (défaut de fond)

**Symptôme** — dans l'exécutable, le moteur mourait puis était relancé en boucle,
jusqu'à `le moteur est tombe et ne redemarre plus`. En mode source, tout
fonctionnait, tests compris.

**Cause** — `kernel32.CreateJobObjectW` était appelé **sans déclarer son `restype`**.
ctypes suppose alors un entier 32 bits, alors qu'un handle Windows en fait 64 :
**le handle du job était tronqué**.

Le défaut restait invisible tant que les handles gardaient de petites valeurs, ce qui
est le cas au début d'un processus Python lancé depuis les sources. Dans un exécutable
empaqueté, davantage de handles sont ouverts, les valeurs dépassent 2³¹ — et on
manipulait alors un handle qui ne désignait plus le job. Le fermer tuait le moteur au
lieu de le protéger, produisant exactement l'inverse de l'effet recherché.

**Remédiation** — signatures explicites (`restype` et `argtypes`) pour
`CreateJobObjectW`, `SetInformationJobObject`, `AssignProcessToJobObject`. Deux tests
gardent la correction : l'un vérifie les signatures, l'autre qu'un handle rendu tient
sur 64 bits.

**Règle retenue** — toute fonction Win32 appelée par ctypes doit déclarer `restype` et
`argtypes`. Le défaut de ctypes est un entier signé 32 bits : correct par accident sur
les petites valeurs, silencieusement destructeur au-delà.

---

## 8. L'empaquetage révèle trois hypothèses implicites

Construire l'exécutable a mis au jour trois suppositions que le mode source rendait
invisibles. Aucune n'était détectable autrement.

**`sys.stdout` et `sys.stderr` valent `None`** avec `--windowed`. Le moindre `print`
lève une `AttributeError` — **y compris celui chargé de rapporter l'erreur**. Un
message clair se transformait ainsi en « Unhandled exception in script ». Corrigé par
un flux muet installé en toute première instruction.

**Les imports relatifs cassent.** PyInstaller exécute le script qu'on lui donne comme
programme principal, pas comme module d'un paquet : passer `murmur/__main__.py`
produisait `attempted relative import with no known parent package`. Un point d'entrée
dédié (`lanceur.py`) rétablit le contexte.

**`__file__` ne désigne plus le projet.** Le code est extrait dans un dossier
temporaire où les 600 Mo du moteur ne figurent pas. `config.RACINE` se repère
désormais sur `sys.executable` quand l'application est empaquetée.

**Piège annexe** — `mklink` résout un chemin relatif depuis le répertoire courant, pas
depuis l'emplacement du lien. Une jonction créée ainsi pointe dans le vide, et le
message d'erreur accuse alors un moteur manquant.

---

## 9. Le même défaut de typage, reproduit deux heures après l'avoir consigné

**Symptôme** — après le passage de la barre de dictée au rendu par GDI, plus aucun
indicateur ne s'affichait. La dictée fonctionnait, les raccourcis répondaient, mais
rien n'apparaissait à l'écran.

**Message exact**

```
ctypes.ArgumentError: argument 1: OverflowError: int too long to convert
  File "murmur/rendu.py", line 295, in peindre
    ancien = gdi32.SelectObject(hdc_memoire, bitmap)
```

**Cause** — exactement l'incident n°7 : `SelectObject`, `DeleteObject` et `DeleteDC`
n'avaient pas d'`argtypes`. J'avais déclaré les types de **retour** de plusieurs
fonctions GDI, en oubliant ceux des **arguments** — or c'est le passage d'un handle
64 bits en paramètre qui déborde.

**Ce que ça a coûté** — deux fausses pistes avant d'y revenir. Le symptôme visible
était « le raccourci ne marche plus », puis les mesures ont montré un micro à
0,000015 — vrai, mais sans rapport. La cause réelle n'a été trouvée qu'en exécutant
directement le chemin d'affichage.

**Deux défauts de fond en plus du typage :**

1. `peindre()` renvoyait `False` en cas d'échec, et l'appelant l'ignorait. L'indicateur
   restait invisible **sans une ligne de journal**. Un échec d'affichage est désormais
   journalisé — une fois par série, pas à chaque image.
2. L'exception remontait dans un rappel Tk, où elle pouvait interrompre la boucle.
   `peindre()` capture maintenant `ArgumentError` et `OSError`.

**Remédiation** — signatures complètes (`restype` **et** `argtypes`) pour les huit
fonctions GDI et user32 employées, plus deux tests : l'un vérifie que chacune déclare
ses types, l'autre peint réellement dans une fenêtre et exige un succès. Les tests
existants ne portaient que sur l'image produite — ils passaient tous alors que rien
ne s'affichait.

**Règle retenue, cette fois appliquée partout** — pour toute fonction Win32 appelée
par ctypes, déclarer `restype` **et** `argtypes`. Déclarer l'un sans l'autre laisse la
moitié du défaut en place, et cette moitié suffit à tout casser.

**Et une leçon sur les tests** — vérifier ce qu'une fonction *produit* ne dit rien de
ce qu'elle *affiche*. Un test de bout en bout, même coûteux, était le seul capable
d'attraper celui-ci.

---

## Méthode utile — isoler encodage et syntaxe

Comparer `ParseInput` (chaîne déjà décodée) et `ParseFile` (lecture disque) sépare en
une seule mesure un problème d'encodage d'un problème de syntaxe. À réutiliser : les
tests d'isolement ligne par ligne, eux, ont produit trois faux négatifs d'affilée
parce qu'ils supprimaient justement le décalage cumulatif qui causait l'erreur.

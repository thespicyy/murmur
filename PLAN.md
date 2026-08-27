# PLAN TECHNIQUE — Murmur

> Le **comment**. Fait suite à [SPEC.md](SPEC.md), validée.
> Statut : **à valider**. Étape suivante : découpe en TÂCHES.

---

## 1. Architecture d'ensemble

Deux processus, une seule application.

```
                    ┌─────────────────────────────────────────┐
                    │  murmur.exe  (Python, resident)         │
                    │                                         │
  Ctrl+Alt+D ──────►│  hotkeys ──► audio ──► guard ──┐        │
  (maintien)        │                                │        │
                    │  overlay ◄── etat              │        │
                    │  tray                          ▼        │
                    │                              stt ───────┼──► HTTP
                    │  lexicon ──────────────────────┘        │   127.0.0.1
                    │                                │        │      │
                    │  store (SQLite) ◄──────────────┤        │      │
                    │                                ▼        │      │
  texte au curseur ◄┼───────────────────────────── inject     │      │
                    └─────────────────────────────────────────┘      │
                                                                     ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  whisper-server.exe  (C++, Vulkan, modele resident) │
                    │  large-v3-turbo-q5_0 en VRAM · VAD Silero actif     │
                    └─────────────────────────────────────────────────────┘
```

Le serveur whisper est lancé comme processus enfant au démarrage et vit aussi
longtemps que l'application. Le modèle est chargé une seule fois : c'est ce qui
fait passer la latence de 1 025 ms à environ 250 ms.

**Flux d'une dictée :** appui sur le raccourci → capture micro → relâchement →
contrôle anti-déclenchement → envoi HTTP avec le lexique du contexte → texte reçu →
filtrage → insertion au curseur → journalisation.

## 2. Stack

| Couche | Choix | Justification |
|---|---|---|
| Langage | Python 3.13 | Terrain connu, et la TDL app prouve que le patron « service résident en zone de notification » y fonctionne. Python n'est **pas** dans le chemin critique : l'inférence tourne en C++ dans un autre processus. Il orchestre, il ne calcule pas |
| API Windows | `ctypes` sur user32/kernel32 | Appel **direct** aux fonctions Win32, sans surcouche — contrairement à ce que je supposais avant vérification, Python ne coûte rien ici |
| Capture audio | `sounddevice` (PortAudio) | Stream par callback, 16 kHz mono natif, exactement le format attendu par whisper |
| Transcription | `whisper-server.exe` + HTTP | Voir décision D2 |
| Interface | `pystray` + Tkinter | Déjà maîtrisés sur la TDL app |
| Stockage | SQLite + JSON | Voir décision D8 |
| Nettoyage IA (V2) | Ollama en HTTP local | Déjà installé |

**Écarté : C#/.NET.** Meilleures API natives sur le papier, mais introduit une stack
à maintenir pour un gain réel nul — `ctypes` donne accès aux mêmes fonctions Win32.

## 3. Décisions techniques

### D1 — Le moteur tourne dans un processus séparé, pas dans Python

Quatre options étaient possibles : relancer `whisper-cli` à chaque dictée (rejeté :
800 ms de rechargement à chaque fois, soit exactement le problème qu'on veut éviter),
lier `whisper.dll` en `ctypes` (le plus rapide, mais il faut mapper l'API C à la main
et un crash du moteur emporte toute l'application), utiliser `pywhispercpp` (compilé
sans Vulkan, il faudrait le recompiler), ou **piloter `whisper-server` en HTTP**.

**Retenu : `whisper-server` en HTTP local.** Le binaire est déjà compilé, le modèle
reste résident, et un plantage du moteur n'emporte pas l'application — elle le
relance. Le coût HTTP en boucle locale est de l'ordre de la milliseconde, négligeable
devant les 250 ms d'inférence.

Vérifié dans le source ([server.cpp:568](../WhisperBench/whisper.cpp/examples/server/server.cpp:568)) :
`prompt`, `language`, `temperature` et les seuils sont acceptés **par requête**. C'est
ce qui rend possible un lexique différent selon l'application active, sans jamais
redémarrer le serveur. Cette vérification conditionnait toute la conception du
lexique — elle est faite.

Si la latence HTTP devenait un jour gênante, seul le module `stt.py` serait à
réécrire en `ctypes`. L'architecture ne bouge pas.

### D2 — Raccourcis globaux sans hook clavier

Le maintien impose de détecter le **relâchement** de la touche, ce que `RegisterHotKey`
ne signale pas. La solution habituelle est un hook bas niveau `WH_KEYBOARD_LL`, mais
il intercepte **toutes** les frappes du système : c'est techniquement un enregistreur
de frappe, régulièrement signalé par les antivirus, et contraire à l'esprit d'un outil
qu'on choisit précisément pour sa confidentialité.

**Retenu : `RegisterHotKey` pour le déclenchement, puis `GetAsyncKeyState` en
scrutation à 20 Hz pour détecter le relâchement.** L'application ne voit jamais une
seule frappe qui ne la concerne pas. Coût processeur négligeable, et uniquement
pendant une dictée.

Le mode bascule utilise un second raccourci, avec arrêt automatique après silence
prolongé — sans ce garde-fou, un micro reste ouvert indéfiniment.

**Raccourcis par défaut :** maintien `Ctrl+Alt+D`, bascule `Ctrl+Alt+Shift+D`.
`Ctrl+Alt+N` est **déjà pris** par l'app Notes, à ne pas réutiliser. Les deux doivent
être reconfigurables, et un échec d'enregistrement doit être signalé explicitement
plutôt que produire un raccourci silencieusement inactif.

### D3 — Anti-hallucination en quatre couches

Whisper invente du texte sur du silence. En français il produit typiquement
« Sous-titres réalisés par la communauté d'Amara.org » ou « Merci d'avoir regardé
cette vidéo ». Un déclenchement accidentel ne doit **jamais** insérer une phrase
inventée dans un document.

La découverte du bench simplifie beaucoup : whisper.cpp embarque déjà l'essentiel.

| Couche | Moyen | Rôle |
|---|---|---|
| 1 | Durée minimale (300 ms) et énergie RMS du signal capturé | Rejette l'appui accidentel **avant** tout envoi — gratuit et très efficace |
| 2 | `--vad` avec le modèle Silero, natif whisper.cpp | Ne transcrit que les segments contenant réellement de la parole |
| 3 | `--suppress-nst` et `no_speech_thold` | Supprime les tokens non verbaux, seuil ajustable par requête |
| 4 | Liste noire de phrases d'hallucination connues | Dernier filet, avec journalisation de ce qui est bloqué pour enrichir la liste |

Le modèle VAD Silero (~1 Mo) est à télécharger séparément.

**Mesuré en T0.3** — le risque est réel et la parade fonctionne. Sur trois échantillons
muets (silence réel du micro, silence numérique, bruit de fond faible), le modèle
**invente du texte dans 3 cas sur 3** sans protection : le silence du micro produit
« Sous-titrage Société Radio-Canada ». Avec `--vad` et `--suppress-nst`, **0 cas sur 3**
produit quoi que ce soit, et la parole réelle reste transcrite normalement.

Les couches 2 et 3 suffisent donc sur ces cas. Les couches 1 et 4 restent au périmètre
comme défense en profondeur, mais **descendent en priorité** : la couche 1 garde sa
valeur propre — elle évite un aller-retour réseau inutile — tandis que la liste noire
ne doit surtout pas être pré-remplie à l'aveugle. Une phrase légitime inscrite en
liste noire serait censurée dans toutes les dictées futures ; elle ne se remplit que
sur hallucination réellement observée.

### D4 — Injection de texte : presse-papier d'abord, frappe simulée en repli

C'est le risque principal du projet, et aucune méthode ne marche partout.

> **Tranché en T0.1/T0.4 — le risque est levé.** Mesures sur quatre familles
> d'applications (Win32, Chromium, Electron ×2, console Windows) :
>
> | Stratégie | Résultat | Coût |
> |---|---|---|
> | **CLIP** (presse-papier + `Ctrl+V`) | **5/5 intactes**, accents et typographie compris | ~3 ms, indépendant de la longueur |
> | **UNIC** (frappe Unicode) | Utilisable seulement à 1 caractère par lot avec ≥15 ms de pause | **16 ms/caractère** — 3,2 s pour 200 caractères |
>
> **CLIP est la stratégie par défaut, sans réserve.** UNIC est conservé en repli
> mais dégradé au rang de dernier recours : au-delà d'une phrase courte, son coût
> devient perceptible et ruine la sensation d'immédiateté.
>
> **Découverte non anticipée, et c'est le point important** : à débit maîtrisé, UNIC
> délivre 115 caractères sur 115 dans le Bloc-notes — et pourtant le texte diffère
> d'un caractère, `a` transformé en `A`. La cause n'est pas la transmission mais
> **l'autocorrection de l'application cible**, qui s'applique à la frappe et **pas au
> collage**.
>
> Cela vaut bien au-delà du Bloc-notes : Word, les navigateurs avec correcteur, les
> champs de saisie mobiles-like appliquent tous des corrections automatiques à ce
> qui est tapé. Une dictée insérée par frappe simulée y serait silencieusement
> réécrite. **Le presse-papier contourne entièrement ce mécanisme**, ce qui en fait
> non seulement la stratégie la plus rapide, mais aussi la seule qui garantisse que
> le texte inséré est exactement celui qui a été transcrit.
>
> Conséquence pour T2.3 : quand le presse-papier contient une image et qu'on ne veut
> pas l'écraser, basculer sur UNIC n'est **pas** un repli équivalent — il est lent et
> vulnérable aux autocorrections. Mieux vaut alors prévenir l'utilisateur, ou
> accepter d'écraser le presse-papier après l'en avoir informé.

**Stratégie par défaut : presse-papier + `Ctrl+V` simulé via `SendInput`.** Rapide,
insensible à la longueur du texte, et fonctionne dans la grande majorité des
applications — navigateurs, Electron, Office, terminaux modernes.

Deux pièges à traiter explicitement :

- **Le presse-papier de l'utilisateur doit être restauré**, mais pas trop vite, sinon
  le collage récupère l'ancienne valeur. Il faut attendre la confirmation du collage
  (~200-300 ms). Le contenu non textuel — une image — ne survit pas à une
  sauvegarde naïve : dans ce cas, ne pas restaurer et le signaler, plutôt que
  détruire silencieusement le presse-papier.
- **Certaines applications refusent le collage synthétique.** D'où le repli.

**Repli : `SendInput` avec `KEYEVENTF_UNICODE`**, qui simule la frappe caractère par
caractère. Ne touche pas au presse-papier, mais plus lent et ignoré par certains
jeux et interfaces à rendu personnalisé.

Le choix se fait **par application**, identifiée via `GetForegroundWindow` puis
`GetWindowThreadProcessId`. La même détection sert au contexte applicatif de la V2
(F11) — un seul mécanisme, deux usages.

### D5 — Indicateur visuel qui ne vole jamais le focus

Fenêtre Tkinter sans bordure, toujours au-dessus, avec les styles étendus
`WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` posés en `ctypes`. Sans `WS_EX_NOACTIVATE`,
l'apparition de l'indicateur déplace le focus et le texte s'insère au mauvais endroit —
c'est le défaut qui rendrait l'outil inutilisable.

### D6 — Stockage inspectable et corrigible à la main

Dans `%APPDATA%/Murmur/`, résolu par `os.getenv('APPDATA')` — jamais de chemin en dur
(règle 9).

| Donnée | Format | Pourquoi |
|---|---|---|
| Configuration, raccourcis | JSON | Éditable dans un éditeur de texte |
| Lexique personnel | JSON | Doit rester inspectable : un lexique auto-alimenté peut dériver, il faut pouvoir le corriger |
| Historique, corrections | SQLite | Volume croissant, besoin de requêtes ; alimente l'apprentissage V2 |

Le corpus de corrections est journalisé **dès la V1**, même si l'apprentissage n'arrive
qu'en V2 : les données non collectées sont définitivement perdues.

### D7 — Concurrence

Un processus Python, quatre fils d'exécution : boucle de messages Win32 (raccourcis et
icône), capture audio, traitement (transcription, filtrage, insertion), surveillance du
serveur whisper. Le traitement est sérialisé par une file — deux dictées simultanées
n'ont pas de sens, la seconde attend.

## 4. Structure du projet

```
Murmur/
  murmur/
    app.py         orchestration, machine a etats
    config.py      configuration et resolution des chemins
    hotkeys.py     RegisterHotKey + scrutation du relachement
    audio.py       capture, RMS, encodage WAV
    guard.py       anti-hallucination (couches 1 et 4)
    stt.py         client HTTP + cycle de vie du serveur whisper
    lexicon.py     lexique et construction du prompt
    inject.py      presse-papier, SendInput, strategie par application
    overlay.py     indicateur d'etat
    tray.py        icone de zone de notification
    store.py       SQLite : historique et corrections
  engine/          whisper-server.exe, DLL, modeles (whisper + VAD)
  tests/
  SPEC.md  PLAN.md  SUIVI.md
```

Les binaires compilés dans `WhisperBench/` seront recopiés dans `engine/` : le bench
reste un dossier d'outillage indépendant, réutilisable pour mesurer les régressions.

## 5. Ordre de construction

Le principe : **attaquer le risque avant le confort**. Rien ne sert de soigner
l'interface si le texte ne s'insère pas dans un terminal.

| Jalon | Contenu | Sortie attendue |
|---|---|---|
| **J0 — Dé-risquage** | Deux essais jetables : injection de texte dans 5 familles d'applications, et lexique via `prompt` sur le serveur | Verdict sur le risque principal. Si l'injection échoue largement, le plan est revu **avant** d'avoir écrit l'application |
| **J1 — Chaîne complète** | Raccourci → audio → transcription → insertion. Aucune interface, aucun réglage | Une dictée fonctionne de bout en bout |
| **J2 — Robustesse** | Anti-hallucination, restauration du presse-papier, redémarrage du serveur, gestion des erreurs | Ne casse rien, jamais |
| **J3 — Intégration** | Indicateur, icône, configuration, lancement avec Windows, mode bascule | Utilisable au quotidien |
| **J4 — Lexique (F6)** | Lexique manuel et prompt contextuel | Le jargon passe |
| **V2** | F8 à F13 | Après une semaine d'usage réel de la V1 |

La V1 s'arrête à J4. Les fonctions d'apprentissage attendent délibérément un vrai
retour d'usage : construire un apprentissage automatique avant de savoir ce que le
modèle rate concrètement, c'est optimiser à l'aveugle.

## 6. Tests

Conformément à la règle 4, les tests tournent après chaque tâche.

- **Automatisés (`pytest`)** sur les modules déterministes : `guard` (rejet du silence,
  liste noire), `lexicon` (construction du prompt, limite de 224 tokens), `store`,
  `config`. Ce sont les parties où une régression passe inaperçue.
- **Matrice manuelle scriptée** pour l'injection : une liste d'applications à couvrir,
  un texte de référence, un résultat consigné. Non automatisable de façon fiable, mais
  reproductible.
- **Bench de latence** réutilisant [bench.py](../WhisperBench/bench.py), à relancer à
  chaque jalon pour détecter toute régression sur les 250 ms.

## 7. Ce qui reste incertain

Trois points que le plan ne peut pas trancher sur le papier :

1. ~~**Le taux de réussite réel de l'injection selon les applications.**~~
   **Levé en T0.1** : le presse-papier passe dans 5 applications sur 5, couvrant
   quatre familles (Win32, Chromium, Electron, console Windows). Le risque principal
   du projet n'en est plus un. Restent non testés : Firefox (moteur Gecko) et
   Windows Terminal (l'hôte moderne, distinct de la console classique éprouvée ici).
2. ~~**La limite pratique du prompt de conditionnement.**~~ **Mesuré en T0.2, avec un
   résultat inattendu.** Sur dix termes de jargon dictés naturellement : 5/10 corrects
   sans prompt, **8/10 avec**. Le prompt fonctionne donc, et le lexique par
   conditionnement est validé comme approche.

   Mais il **n'est pas monotone** : `Grafana`, correctement transcrit *sans* prompt,
   devient « Donchan » *avec*. Ajouter un terme au lexique peut donc en casser un
   autre. C'est une contrainte de conception qui n'était pas anticipée et qui impose
   deux choses :

   - un **test de non-régression du lexique** — la liste des termes attendus est
     rejouée à chaque modification, et une régression doit échouer bruyamment ;
   - la **table de remplacement (T4.2) n'est pas un complément optionnel** mais le
     traitement obligatoire des termes que le prompt ne corrige pas, voire dégrade.
     Deux termes y échappent encore : un nom propre de service, francisé a l'oreille, et
     `Grafana`.

   Le prompt utilisé ne fait que 100 caractères pour 10 termes ; la limite des
   224 tokens n'est donc pas contraignante à cette échelle. Elle le deviendra avec un
   lexique auto-alimenté, d'où la priorisation prévue en T4.1.

   Deux termes hors des dix suivis sont également ratés et méritent d'entrer au
   lexique : un mot composé recollé (transcrit en deux mots) et « IA locale » (« ialoka »).
3. **Le comportement du VAD sur un casque de jeu.** Le micro Logitech PRO X capte le
   souffle ; les seuils devront être calibrés sur des enregistrements réels.

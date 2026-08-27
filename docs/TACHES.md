# TÂCHES — Murmur

> Découpe opérationnelle. Fait suite à [SPEC.md](SPEC.md) et [PLAN.md](PLAN.md).
> Statut : **à valider**. Après validation, l'implémentation peut commencer.

Convention : chaque tâche est atomique, a un critère de fin **vérifiable** et un test
associé. Taille indicative — S : moins d'une heure · M : une demi-journée · L : une journée.

**Règle d'arrêt :** aucune tâche ne démarre tant que la précédente n'a pas son test au
vert (règles 4 et 5). Toute erreur rencontrée est consignée dans `logs/ERREURS.md`
avec message exact, contexte, cause probable et remédiation (règle 3).

---

## Prérequis — action utilisateur

| ID | Tâche | Bloque |
|---|---|---|
| **P1** | Enregistrer un échantillon de voix en français contenant du jargon, via [record.ps1](../WhisperBench/record.ps1) | T0.2, T0.3 |

Sans cet échantillon, la qualité française et l'effet du lexique ne peuvent pas être
mesurés — seulement supposés. C'est le seul point qui demande une action manuelle.

---

## J0 — Dé-risquage

Deux essais **jetables**. Le code produit ici n'ira pas dans l'application : il sert à
décider. C'est le jalon le plus important du projet.

| ID | Tâche | Dép. | Taille | Critère de fin | Test |
|---|---|---|---|---|---|
| **T0.1** | Essai d'injection de texte : script isolé implémentant les deux stratégies (presse-papier + `Ctrl+V`, et `SendInput` Unicode), déclenché après un délai laissant le temps de placer le focus | — | M | Une matrice de résultats remplie pour 5 familles : navigateur (Chrome), éditeur (VS Code), Electron (Discord), terminal (Windows Terminal), Win32 classique (Bloc-notes) | Le texte de référence, accents et ponctuation compris, arrive intact dans chaque cible. Résultat consigné par application et par stratégie |
| **T0.2** | Essai de lexique : transcrire l'échantillon P1 sans prompt, puis avec un prompt contenant le jargon, et comparer | P1 | S | Écart mesuré terme à terme | Le nombre de termes de jargon corrects augmente avec le prompt. Si l'écart est nul, l'approche par prompt est à revoir |
| **T0.3** | Récupérer le modèle VAD Silero et lancer `whisper-server` avec `--vad`, puis lui soumettre du silence, du bruit de fond et l'échantillon P1 | P1 | S | Comportement du VAD caractérisé sur le micro réel | Le silence et le bruit de clavier produisent une sortie **vide**, l'échantillon P1 est transcrit normalement |
| **T0.4** | Consolider J0 : décider la stratégie d'injection par défaut et son repli, fixer les seuils VAD | T0.1-T0.3 | S | Décisions écrites dans `PLAN.md` | Relecture — si l'injection échoue dans plus de deux familles, le plan est révisé avant J1 |

**Point de sortie :** si T0.1 échoue largement, on s'arrête et on reprend la
conception. C'est exactement le but de ce jalon.

---

## J1 — Chaîne complète

Objectif : une dictée qui fonctionne de bout en bout. Aucune interface, aucun réglage,
aucune robustesse. Juste la preuve que la chaîne tient.

| ID | Tâche | Dép. | Taille | Critère de fin | Test |
|---|---|---|---|---|---|
| **T1.1** | Squelette : arborescence `murmur/`, environnement virtuel, dépendances, `config.py` résolvant tous les chemins via `%APPDATA%` et `Path(__file__).parent` | T0.4 | S | Le paquet s'importe, aucun chemin absolu nulle part | `pytest` : les chemins se résolvent depuis un répertoire de travail arbitraire |
| **T1.2** | Recopier le moteur et les modèles dans `engine/`, écrire `stt.py` : démarrage du serveur en processus enfant, attente de disponibilité, client HTTP `/inference`, arrêt propre | T1.1 | M | Un fichier WAV envoyé revient en texte | `pytest` : transcription de `jfk.wav`, la sortie contient la phrase attendue. Le serveur s'arrête sans processus orphelin |
| **T1.3** | `audio.py` : capture `sounddevice` 16 kHz mono, démarrage/arrêt, encodage WAV en mémoire, calcul du RMS | T1.1 | M | Un enregistrement déclenché par code produit un WAV lisible | `pytest` sur l'encodage WAV (en-tête, débit, durée) à partir d'un signal synthétique — sans micro |
| **T1.4** | `hotkeys.py` : `RegisterHotKey` en `ctypes`, boucle de messages Win32, scrutation `GetAsyncKeyState` pour le relâchement, échec d'enregistrement remonté explicitement | T1.1 | M | Un appui maintenu déclenche deux rappels distincts : début et fin | Test manuel scripté : maintenir 2 s, vérifier la durée mesurée. Test auto : un raccourci déjà pris lève une erreur claire |
| **T1.5** | `inject.py` : implémentation de la stratégie retenue en T0.4, sans restauration du presse-papier à ce stade | T0.4, T1.1 | M | Le texte s'insère dans la fenêtre active | Rejouer la matrice T0.1, cette fois contre le vrai module |
| **T1.6** | `app.py` : machine à états (repos → écoute → transcription → insertion), file sérialisant les dictées, assemblage des modules | T1.2-T1.5 | M | **Une dictée réelle fonctionne de bout en bout** | Test manuel : dicter une phrase dans le Bloc-notes. Mesure de la latence de bout en bout, comparée aux 250 ms attendus |

**Point de sortie :** l'outil est utilisable, mais fragile. Ne pas s'en servir au
quotidien avant J2 — une hallucination sur silence peut polluer un vrai document.

---

## J2 — Robustesse

| ID | Tâche | Dép. | Taille | Critère de fin | Test |
|---|---|---|---|---|---|
| **T2.1** | `guard.py` : rejet en amont sur durée inférieure à 300 ms et sur RMS sous seuil ; liste noire de phrases d'hallucination en aval, avec journalisation de chaque blocage | T1.6 | M | Un déclenchement accidentel ne produit rien | `pytest` : silence → rejeté, signal trop court → rejeté, phrase de la liste noire → filtrée, phrase normale → laissée intacte |
| **T2.2** | Activer `--vad` et `--suppress-nst` côté serveur avec les seuils fixés en T0.3, exposés dans la configuration | T0.3, T2.1 | S | Le serveur démarre avec le VAD actif | Rejouer T0.3 via le module : silence et bruit de clavier donnent une sortie vide |
| **T2.3** | Restauration du presse-papier : sauvegarde avant, restauration temporisée après collage, détection du contenu non textuel (image) traité comme non restaurable et signalé | T1.5 | M | Le presse-papier retrouve son contenu après une dictée | `pytest` avec presse-papier simulé : texte restauré ; image → non écrasée ou avertissement. Test manuel : copier une image, dicter, vérifier |
| **T2.4** | Surveillance du serveur whisper : détection d'arrêt, redémarrage automatique, plafond de tentatives, message clair en cas d'échec répété | T1.2 | M | Tuer le serveur à la main n'empêche pas la dictée suivante | Test d'intégration : arrêt forcé du processus, la dictée suivante réussit après redémarrage automatique |
| **T2.5** | Gestion d'erreurs transversale et journalisation : aucune exception non capturée ne doit tuer le service ; journal rotatif dans `%APPDATA%/Murmur/logs/` | T1.6 | M | Le service survit à toute panne d'un composant | `pytest` : injection de pannes simulées sur micro absent, serveur injoignable, presse-papier verrouillé. Le service reste vivant dans les trois cas |

**Point de sortie :** utilisable au quotidien. C'est ici que commence le vrai retour
d'usage.

---

## J3 — Intégration

| ID | Tâche | Dép. | Taille | Critère de fin | Test |
|---|---|---|---|---|---|
| **T3.1** | `overlay.py` : indicateur sans bordure, toujours au-dessus, avec `WS_EX_NOACTIVATE` et `WS_EX_TOOLWINDOW` posés en `ctypes` ; trois états visuels | T2.5 | M | L'indicateur apparaît **sans jamais déplacer le focus** | Test critique : ouvrir le Bloc-notes, dicter, vérifier que le texte arrive bien dans le Bloc-notes et non ailleurs. Vérifier l'absence dans Alt+Tab |
| **T3.2** | `tray.py` : icône `pystray`, menu (activer/désactiver, ouvrir la configuration, historique, quitter), état reflété par l'icône | T3.1 | M | L'app se pilote sans console | Test manuel de chaque entrée du menu |
| **T3.3** | `config.py` complet : fichier JSON, valeurs par défaut, validation, rechargement à chaud, création au premier lancement | T3.2 | M | Modifier le JSON change le comportement sans redémarrage | `pytest` : config absente → défauts ; config invalide → erreur explicite, pas de plantage |
| **T3.4** | Mode bascule sur second raccourci, avec arrêt automatique après silence prolongé | T3.3 | M | Une dictée longue fonctionne sans maintenir la touche | Test manuel : bascule, parler 30 s, vérifier l'arrêt auto après le délai de silence configuré |
| **T3.5** | `store.py` : SQLite, historique des dictées, journalisation du corpus de corrections dès maintenant même si l'apprentissage n'arrive qu'en V2 | T3.3 | M | Chaque dictée est enregistrée et consultable | `pytest` : écriture, relecture, migration de schéma sur base existante |
| **T3.6** | Lancement avec Windows, instance unique (verrou par socket, comme la TDL app), et empaquetage en exécutable portable | T3.4, T3.5 | M | Double-clic → l'app tourne ; deuxième lancement → la première reprend la main | Test manuel : redémarrage de session, lancement en double |

---

## J4 — Lexique (F6)

| ID | Tâche | Dép. | Taille | Critère de fin | Test |
|---|---|---|---|---|---|
| **T4.1** | `lexicon.py` : lexique JSON, construction du prompt, **respect de la limite de 224 tokens** avec priorisation quand elle est dépassée | T0.2, T3.5 | M | Le prompt envoyé ne dépasse jamais la limite | `pytest` : lexique surdimensionné → tronqué par priorité, jamais d'erreur serveur |
| **T4.1b** | **Test de non-régression du lexique** : rejouer l'échantillon de référence et vérifier les termes attendus à chaque modification du lexique | T4.1 | S | Une régression échoue bruyamment | Mesuré en T0.2 : le prompt **n'est pas monotone** — `Grafana` passait sans prompt et échoue avec. Ajouter un terme peut donc en casser un autre : sans ce test, la dérive est invisible |
| **T4.2** | Table de remplacement appliquée après transcription, pour les termes que le prompt seul ne corrige pas ou dégrade | T4.1 | S | Les substitutions connues sont appliquées | `pytest` : casse, accents, limites de mots respectées — ne pas corriger à l'intérieur d'un autre mot. Cas réels à couvrir : `Cloudflare` (francisé en « cloudeflare »), `Grafana`, « webhook », « IA locale » |
| **T4.3** | Interface minimale d'édition du lexique, accessible depuis le menu de l'icône | T4.2 | M | Le lexique s'édite sans ouvrir un fichier à la main | Test manuel : ajout d'un terme, effet immédiat sur la dictée suivante |
| **T4.4** | Validation finale V1 sur les dix termes de jargon définis à l'avance | T4.3 | S | Les dix termes passent | Comparaison avec la mesure initiale de T0.2 — c'est le critère 3 de la spec |

---

## Clôture V1

| ID | Tâche | Dép. | Taille | Critère de fin |
|---|---|---|---|---|
| **T5.1** | Semaine d'usage réel, journal des manques et des irritants | T4.4 | — | Les cinq critères de succès de la spec sont évalués, chiffres à l'appui |
| **T5.2** | Mise à jour de `SUIVI.md` et ajout d'un bloc `⏳ à ajouter` en haut du `README.md` central (règle 8b), avec le stack et les compétences mises en œuvre | T5.1 | S | Entrée portfolio prête |
| **T5.3** | Arbitrage V2 : décider quelles fonctions parmi F8 à F13 méritent d'être construites, au vu de ce que l'usage réel a révélé | T5.1 | S | Périmètre V2 arrêté sur des faits, pas sur des suppositions |

---

## Récapitulatif

| Jalon | Tâches | Charge estimée |
|---|---|---|
| J0 — Dé-risquage | 4 | ~1 journée |
| J1 — Chaîne complète | 6 | ~2 journées |
| J2 — Robustesse | 5 | ~2 journées |
| J3 — Intégration | 6 | ~2 journées |
| J4 — Lexique | 4 | ~1 journée |
| **Total V1** | **25** | **~8 journées** |

Ces durées supposent un travail suivi et sans imprévu. Le risque principal reste
concentré sur T0.1 : si l'injection de texte se révèle capricieuse, J1 et J2
s'allongent nettement.

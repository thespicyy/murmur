# Essai sur machine vierge

Murmur tourne évidemment sur la machine qui l'a compilé : Python, les outils de
compilation Visual Studio et le modèle y sont déjà. Rien de tout cela n'est
présent chez la personne qui télécharge l'archive.

Ces deux fichiers rejouent son parcours dans **Windows Sandbox** — une machine
Windows neuve, jetée à la fermeture : décompresser l'archive, lancer
l'application, la laisser aller chercher son modèle, vérifier qu'elle
transcrit.

## Utilisation

1. Activez Windows Sandbox si ce n'est pas fait (Fonctionnalités Windows →
   *Bac à sable Windows*). Édition Pro ou Entreprise uniquement.
2. Dans `essai.wsb`, remplacez `CHEMIN\VERS\MURMUR` par le chemin réel du
   projet. Le format `.wsb` n'accepte que des chemins absolus, sans variable.
3. Construisez l'archive : `outils/construire.py` puis
   `outils/empaqueter.py`.
4. Double-cliquez sur `essai.wsb`.

Le rapport est écrit dans `resultat/rapport.txt`, sur la machine hôte, au fur
et à mesure. Les journaux de l'application y sont recopiés à la fin.

## Ce que l'essai a trouvé

Ce n'est pas une précaution de style — chaque passage a révélé un défaut que
rien, sur la machine de développement, ne pouvait montrer :

| passage | trouvé |
|---|---|
| 1 | `MSVCP140.dll` absente : le moteur ne démarrait pas |
| 2 | `VCOMP140.DLL` absente — la liste des bibliothèques avait été devinée |
| 3 | tout fonctionne : moteur, raccourcis, tableau de bord |

D'où la règle appliquée depuis dans `murmur/crt.py` : est à livrer toute
bibliothèque que le moteur **importe** et que Visual Studio range parmi ses
**redistribuables**. Plus rien n'y est écrit à la main.

## Deux pièges du bac à sable

Une seule instance peut tourner à la fois. Si vous arrêtez ses processus de
force, la session suivante échoue sur « le nombre maximal de sessions sur ce
serveur était déjà dépassé ». Le remède est de relancer le service, en
administrateur :

    Restart-Service CmService -Force

Et le bac à sable expose la carte graphique de l'hôte même avec
`<VGpu>Disable</VGpu>` : il ne permet donc pas de simuler une machine sans
carte. Cette mesure-là se fait autrement, en passant `--no-gpu` au moteur.

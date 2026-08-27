# Maquette — la page Insights rendue par un moteur web

Prototype de comparaison. **Rien n'est branché sur l'application** : la base
est lue en lecture seule, aucun fichier n'est écrit hors de ce dossier.

```bash
.venv\Scripts\python.exe maquette\lancer.py
.venv\Scripts\python.exe maquette\lancer.py --sombre
```

## Pourquoi

Sept passes sur l'interface Tkinter ont buté sur les mêmes limites, toutes
consignées dans le `SUIVI.md` : pas de dégradé derrière un widget, pas
d'ombre portée, pas de transition, rendu du texte par GDI. Cette maquette
montre ce que coûte — et ce que rapporte — le passage de la seule fenêtre du
tableau de bord à un moteur web.

## Ce qu'elle emploie

**WebView2**, déjà installé sur Windows 11 et partagé entre les applications
qui s'en servent. Contrairement à Electron, il n'y a pas de navigateur à
embarquer dans l'exécutable. Le pont Python↔page passe par `pywebview`.

Aucune bibliothèque d'interface : ni React, ni Tailwind. La maquette doit
montrer le coût réel du portage, pas celui d'un écosystème.

## Ce qui devient possible

Chaque règle marquée `Tk : impossible` dans `style.css` désigne un point qui a
fait l'objet d'un aller-retour dans les échanges :

| Effet | En Tkinter | Ici |
|---|---|---|
| Dégradé sur les cartes | impossible — un cadre Tk est opaque | `linear-gradient`, une ligne |
| Ombre portée | impossible — il faut peindre hors du widget | `box-shadow` |
| Repli de la barre | boucle d'images avec adoucissement à la main | `transition: width` |
| Jauge à bouts arrondis | deux disques posés aux extrémités | `stroke-linecap: round` |
| Barre de titre déplaçable | suivi de la souris réimplémenté | `-webkit-app-region: drag` |
| Chiffres à chasse fixe | inaccessible | `font-variant-numeric` |

## Ce qu'elle a fait découvrir

En la mesurant, un défaut de l'application **existante** est apparu : Murmur
n'est pas conscient du DPI. Sur un écran à 125 %, Windows le dessine à cent
pour cent puis étire l'image. C'est la cause du flou, indépendamment du choix
de moteur — et c'est corrigeable dans la version Tkinter.

Le piège au passage : `SetProcessDpiAwarenessContext(-4)` échoue **en
silence** si `argtypes` n'est pas déclaré, ctypes envoyant un entier de 32
bits là où Windows attend la taille d'un pointeur. Les scripts de capture
souffraient du même défaut et montraient donc une image plus nette que la
réalité.

# Assets — identité visuelle

Sources du symbole Murmur, copiées depuis
`_Done/Logo/Logo Murmur noir et blanc/`.

| Fichier | Usage |
|---|---|
| `murmur-mark.svg` | Symbole complet, deux arcs — grandes tailles |
| `murmur-mark-16.svg` | Déclinaison compacte, un seul arc — petites tailles |
| `murmur-lockup.svg` | Symbole + mot, en ligne |

**Ces fichiers ne sont pas lus par l'application.** Ils servent de référence :
le symbole est redessiné par [`murmur/marque.py`](../murmur/marque.py), qui
reprend leur géométrie exacte sur une base de 96 pixels.

Ce choix tient à une contrainte que des images figées ne satisfont pas : le
symbole doit changer de couleur selon l'état de la dictée (repos, écoute,
transcription, insertion) **et** selon le thème clair ou sombre. Il faudrait
autrement une image par combinaison, à régénérer à chaque ajustement.

Deux points repris du kit, à ne pas perdre en cas de retouche :

- **La déclinaison compacte n'est pas un caprice.** À 16 pixels — la taille
  réelle dans la barre des tâches — les deux arcs fins de la version complète
  se confondent en une tache. Le kit fournit donc une variante à un seul arc,
  trait épais et point plus gros.
- **Le tracé est recentré optiquement.** Les arcs occupent la gauche et rien à
  droite : le point a beau être au centre géométrique, l'ensemble paraît
  décalé. `marque.decalage_optique()` corrige, sans quoi l'icône semble mal
  alignée en permanence.

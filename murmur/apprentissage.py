"""Apprentissage par correction.

Le geste vise : tu dictes, tu corriges le texte dans l'application ou tu
travailles, tu selectionnes tout, tu copies, et tu appuies sur un raccourci.
Murmur compare ce que tu as copie a ce qu'il avait ecrit, et en deduit ce
qu'il a mal transcrit.

L'analyse ne se declenche QUE sur ce raccourci : Murmur ne lit jamais le
presse-papier de sa propre initiative. C'est un choix delibere — ecouter en
continu reviendrait a lire tout ce que l'utilisateur copie, mots de passe
compris, dans un outil dont la confidentialite est l'argument central.

Les mots differents sont **proposes**, jamais appris d'office : corriger
« du coup » en « donc » est une preference de style, pas du vocabulaire. Une
telle substitution appliquee a toutes les dictees futures serait une regression.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

#: En dessous, les deux textes n'ont plus de rapport : ce n'est pas une
#: correction mais un autre texte.
SIMILARITE_MINIMALE = 0.60

#: Au-dessus, les textes sont identiques : rien a apprendre.
SIMILARITE_MAXIMALE = 0.999

#: Seuils de parente orthographique, selon que le terme corrige porte ou non
#: une majuscule.
#:
#: Sur un echantillon elargi, la similarite seule ne suffit plus : les vrais
#: termes descendent a 0.78 (obsidienne/Obsidian) tandis que de simples mots
#: francais montent a 0.75 (dire/lire). Aucun seuil ne separe proprement.
#:
#: La majuscule, elle, discrimine nettement. Sur les memes donnees, dix des
#: onze corrections de vocabulaire en portent une — Vulkan, Ollama, Vercel,
#: DexScreener, Tkinter — et aucune des dix reformulations de style. C'est
#: coherent : un terme que le modele massacre et que l'utilisateur retablit
#: avec une majuscule est presque toujours un nom propre ou un mot technique.
#:
#: Sans cet indice, on exige une ressemblance bien plus forte pour compenser —
#: ce qui laisse passer « webhook » (0.84), le seul vrai terme tout en
#: minuscules, tout en ecartant « dire/lire » (0.75).
SIMILARITE_TERME_PROPRE = 0.65
SIMILARITE_SANS_MAJUSCULE = 0.82

#: Au-dela, ce n'est plus un terme mal transcrit mais une phrase reecrite.
MOTS_MAXIMUM = 3

MOT = re.compile(r"\w+(?:['’-]\w+)*|\S", re.UNICODE)


def decouper(texte: str) -> list[str]:
    return MOT.findall(texte)


#: `autojunk` DESACTIVE, et ce n'est pas un detail de reglage.
#:
#: Au-dela de 200 elements, `SequenceMatcher` ecarte de son index tout element
#: present dans plus d'un pour cent de la sequence. L'heuristique est faite
#: pour comparer des LIGNES de code, ou un element frequent est une ligne
#: repetee. Ici les elements sont des caracteres : sur un texte de 355
#: caracteres, elle ecarte l'espace, la virgule, le point et quinze lettres —
#: dix-huit des trente-six caracteres distincts. L'algorithme ne peut plus
#: amorcer ses correspondances que sur les caracteres rares, et selon l'endroit
#: ou tombe la correction, il trouve un long bloc commun ou se fragmente.
#:
#: Mesure sur un cas reel, deux textes qui ne different que d'un mot : 0.093
#: contre 0.979. Le premier passe sous le seuil, la correction reste
#: introuvable et l'utilisateur voit « aucune dictee ne ressemble au texte
#: copie ». Les dictees courtes, elles, fonctionnaient — d'ou un defaut qui
#: n'apparait qu'au-dela de deux cents caracteres.
SANS_BRUIT = {"autojunk": False}


def similarite(avant: str, apres: str) -> float:
    return difflib.SequenceMatcher(None, avant, apres, **SANS_BRUIT).ratio()


@dataclass(frozen=True)
class Substitution:
    """Un remplacement observe entre le texte dicte et le texte corrige."""

    avant: str
    apres: str

    @property
    def est_vocabulaire(self) -> bool:
        """Distingue un terme mal transcrit d'une reformulation de style.

        On ne compare PAS le nombre de mots de part et d'autre : le modele
        decoupe volontiers un terme inconnu en plusieurs mots familiers —
        « webhook » devient « web hooks ». Exiger l'egalite ferait rater
        exactement les cas qui interessent le lexique.

        Le critere est la parente orthographique : un terme mal entendu
        ressemble a ce qu'il aurait du etre, une reformulation non.
        """
        if not self.avant.strip() or not self.apres.strip():
            return False
        if (len(decouper(self.avant)) > MOTS_MAXIMUM
                or len(decouper(self.apres)) > MOTS_MAXIMUM):
            return False
        # Une simple difference de casse n'apprend rien d'utile : la table de
        # remplacement est deja insensible a la casse.
        if self.avant.casefold() == self.apres.casefold():
            return False

        seuil = (SIMILARITE_TERME_PROPRE if self.porte_une_majuscule
                 else SIMILARITE_SANS_MAJUSCULE)
        return (similarite(self.avant.casefold(), self.apres.casefold())
                >= seuil)

    @property
    def porte_une_majuscule(self) -> bool:
        """Le terme corrige contient-il une majuscule ?

        Indice le plus fiable dont on dispose pour reconnaitre un nom propre
        ou un terme technique, sans embarquer de dictionnaire francais.
        """
        return any(c.isupper() for c in self.apres)


@dataclass(frozen=True)
class Analyse:
    """Resultat d'une comparaison entre une dictee et sa correction."""

    dictee_id: int | None
    texte_origine: str
    texte_corrige: str
    similarite: float
    substitutions: tuple[Substitution, ...]

    @property
    def est_correction(self) -> bool:
        return SIMILARITE_MINIMALE <= self.similarite <= SIMILARITE_MAXIMALE

    @property
    def propositions(self) -> tuple[Substitution, ...]:
        """Substitutions qui meritent d'entrer au lexique."""
        return tuple(s for s in self.substitutions if s.est_vocabulaire)


def _affiner(mots_avant: list[str], mots_apres: list[str]) -> list[Substitution]:
    """Decoupe un bloc remplace en substitutions aussi fines que possible.

    difflib regroupe les remplacements voisins : « du coup Olama » ->
    « donc Ollama » ressort comme un seul bloc. Appris tel quel, ce bloc
    entrerait au lexique comme un « terme » de trois mots, ce qui n'a aucun
    sens et reecrirait la phrase entiere a chaque occurrence.

    On cherche donc les mots qui s'apparient nettement — « Olama » et
    « Ollama » — et on les isole. Ce qui les entoure reste groupe, et sera
    presente comme la reformulation qu'il est.
    """
    ancres: list[tuple[int, int]] = []
    depart = 0
    for i, mot in enumerate(mots_avant):
        meilleur, score = -1, 0.0
        for j in range(depart, len(mots_apres)):
            valeur = similarite(mot.casefold(), mots_apres[j].casefold())
            if valeur > score:
                meilleur, score = j, valeur
        if meilleur >= 0 and score >= SIMILARITE_TERME_PROPRE:
            ancres.append((i, meilleur))
            depart = meilleur + 1

    if not ancres:
        return [Substitution(" ".join(mots_avant), " ".join(mots_apres))]

    substitutions: list[Substitution] = []
    curseur_avant = curseur_apres = 0
    for i, j in ancres:
        if i > curseur_avant or j > curseur_apres:
            substitutions.append(Substitution(
                " ".join(mots_avant[curseur_avant:i]),
                " ".join(mots_apres[curseur_apres:j])))
        substitutions.append(Substitution(mots_avant[i], mots_apres[j]))
        curseur_avant, curseur_apres = i + 1, j + 1

    if curseur_avant < len(mots_avant) or curseur_apres < len(mots_apres):
        substitutions.append(Substitution(
            " ".join(mots_avant[curseur_avant:]),
            " ".join(mots_apres[curseur_apres:])))

    return [s for s in substitutions if s.avant or s.apres]


def comparer(origine: str, corrige: str,
             dictee_id: int | None = None) -> Analyse:
    """Compare deux textes et isole ce qui a change, mot a mot."""
    mots_origine = decouper(origine)
    mots_corrige = decouper(corrige)

    substitutions: list[Substitution] = []
    # Meme precaution : au-dela de deux cents mots, les mots-outils — « de »,
    # « que », « le » — seraient ecartes de l'index et le decoupage en
    # substitutions partirait de travers.
    comparateur = difflib.SequenceMatcher(None, mots_origine, mots_corrige,
                                          **SANS_BRUIT)
    for operation, debut1, fin1, debut2, fin2 in comparateur.get_opcodes():
        if operation != "replace":
            # Les insertions et suppressions pures n'apprennent rien au
            # lexique : elles n'ont pas de forme erronee a rattraper.
            continue
        substitutions.extend(_affiner(mots_origine[debut1:fin1],
                                      mots_corrige[debut2:fin2]))

    return Analyse(dictee_id=dictee_id, texte_origine=origine,
                   texte_corrige=corrige,
                   similarite=similarite(origine, corrige),
                   substitutions=tuple(substitutions))


def morceaux(texte: str) -> list[str]:
    """Fragments du texte copie a confronter aux dictees.

    Le texte entier d'abord, puis chaque ligne, puis chaque paragraphe.

    Cette decoupe est indispensable en pratique : `Ctrl+A` copie tout le
    document, pas seulement la phrase corrigee. Comparee a l'ensemble, une
    dictee d'une ligne se noie et la similarite s'effondre — l'utilisateur
    voit alors « aucune correspondance » alors que sa correction est bien la.
    """
    candidats = [texte]

    lignes = [ligne.strip() for ligne in texte.splitlines() if ligne.strip()]
    if len(lignes) > 1:
        candidats.extend(lignes)

        # Paragraphes : une dictee longue peut avoir ete repartie sur
        # plusieurs lignes par l'application ou par un retour manuel.
        paragraphe: list[str] = []
        for ligne in texte.splitlines():
            if ligne.strip():
                paragraphe.append(ligne.strip())
            elif paragraphe:
                candidats.append(" ".join(paragraphe))
                paragraphe = []
        if len(paragraphe) > 1:
            candidats.append(" ".join(paragraphe))

    # Doublons ecartes en conservant l'ordre : le texte entier reste prioritaire.
    vus, uniques = set(), []
    for candidat in candidats:
        if candidat and candidat not in vus:
            vus.add(candidat)
            uniques.append(candidat)
    return uniques


def meilleure_correspondance(texte: str, dictees) -> Analyse | None:
    """Trouve la dictee que ce texte corrige, s'il en corrige une.

    `dictees` est un iterable d'objets ayant `.texte` et `.identifiant`.
    Renvoie None si aucune ne correspond — auquel cas le texte copie est
    simplement oublie, jamais conserve.
    """
    fragments = morceaux(texte)
    meilleure: Analyse | None = None

    for dictee in dictees:
        for fragment in fragments:
            analyse = comparer(dictee.texte, fragment,
                               dictee_id=dictee.identifiant)
            if not analyse.est_correction:
                continue
            if meilleure is None or analyse.similarite > meilleure.similarite:
                meilleure = analyse
    return meilleure


def diagnostiquer(texte: str, dictees) -> str:
    """Explique pourquoi aucune correspondance n'a ete trouvee.

    « Aucune correspondance » sans plus de detail laisse l'utilisateur sans
    prise : il ne sait pas s'il a mal copie, si sa dictee est trop ancienne,
    ou si le texte a trop change.
    """
    dictees = list(dictees)
    if not dictees:
        return "aucune dictee enregistree pour l'instant"
    if not texte.strip():
        # Dit avant tout le reste : « aucune dictee ne ressemble au texte
        # copie » est trompeur quand il n'y a pas de texte copie du tout.
        return "le presse-papier est vide : il n'y a rien a comparer"

    meilleure = 0.0
    for dictee in dictees:
        for fragment in morceaux(texte):
            meilleure = max(meilleure, similarite(dictee.texte, fragment))

    if meilleure > SIMILARITE_MAXIMALE:
        # Le cas le plus frequent, et de loin : on a corrige le texte dans
        # l'application SANS le recopier. Murmur ne lit que le presse-papier,
        # jamais le champ de saisie — il y retrouve donc ce qu'il venait d'y
        # ecrire pour le coller, et compare la dictee a elle-meme. Le dire
        # ainsi vaut mieux qu'un « texte identique » que rien n'explique.
        return ("le presse-papier contient la dictee telle quelle, sans la "
                "correction — as-tu bien fait Ctrl+C apres avoir corrige ?"
                + _extrait(texte))
    if meilleure >= 0.35:
        return (f"la dictee la plus proche ne correspond qu'a "
                f"{meilleure * 100:.0f} % — trop de differences pour une "
                f"correction" + _extrait(texte))
    return (f"aucune des {len(dictees)} dernieres dictees ne ressemble au "
            f"texte copie" + _extrait(texte))


#: Longueur de l'extrait montre. Assez pour reconnaitre ce qu'on a copie, pas
#: assez pour remplir la boite de dialogue.
EXTRAIT = 70


def _extrait(texte: str) -> str:
    """Rappelle ce qui a ete lu dans le presse-papier.

    Sans cela, l'explication reste abstraite : l'utilisateur voit « identique
    a une dictee » sans savoir que c'est le texte NON corrige qu'il a copie.
    C'est arrive, et la cause est restee introuvable jusqu'a ce qu'on lise le
    presse-papier a la main.
    """
    lu = " ".join(texte.split())
    if not lu:
        return "\n\nLe presse-papier est vide."
    if len(lu) > EXTRAIT:
        lu = lu[:EXTRAIT] + "…"
    return f"\n\nLu dans le presse-papier : « {lu} »"

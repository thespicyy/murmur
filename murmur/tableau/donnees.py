"""Ce que le tableau de bord affiche, extrait de la base et du lexique.

Une couche a part, entre le stockage et la page. Elle existe pour deux
raisons : la page ne doit connaitre ni SQLite ni les objets du domaine — elle
recoit du JSON — et cette conversion se teste sans ouvrir de fenetre, ce que
la version Tkinter ne permettait pas.

Les calculs derives — rapport au clavier, temps gagne, tendance mensuelle —
vivent ici et non dans la page : ce sont des regles de l'application, pas de
l'affichage, et les changer ne doit pas demander de toucher au HTML.
"""

from __future__ import annotations

from datetime import date

from .. import applications, langue as module_langue, lexicon, store

#: Cadence de reference au clavier, en mots par minute.
CLAVIER_MPM = 40

#: Plafond de la jauge de vitesse. Au-dela, l'aiguille reste au bout.
JAUGE_MAX_MPM = 250

#: Etendue du calendrier d'activite, en jours. Dix-huit semaines.
#:
#: Le nombre de semaines et la taille des cases sont le meme reglage vu de
#: deux cotes : la carte a une largeur donnee, et plus on y met de colonnes,
#: plus les cases sont petites. A vingt-deux semaines elles tombaient a douze
#: pixels. Les fleches de la carte donnent acces au reste de l'histoire, ce
#: qui rend le compromis indolore.
JOURS_CALENDRIER = 126

#: Applications detaillees dans la carte d'usage.
APPLICATIONS_DETAILLEES = 5

#: Paliers d'intensite du calendrier, en plus du vide. Cinq niveaux en tout —
#: 0 pour un jour sans dictee, 1 a 4 par quarts du maximum observe. Des
#: paliers plutot qu'un degrade continu : l'oeil compare mal deux teintes
#: voisines, mais distingue sans effort quatre marches.
NIVEAUX = 4


def insights(historique: store.Historique, lexique: lexicon.Lexique,
             mot: module_langue.Traducteur) -> dict:
    """Tout ce que porte la page Insights."""
    stats = historique.statistiques()
    usage = historique.usage_par_application(limite=APPLICATIONS_DETAILLEES)

    return {
        "vitesse": {
            "valeur": round(stats.mots_par_minute),
            "part": min(1.0, stats.mots_par_minute / JAUGE_MAX_MPM),
            "rapport": (mot.decimal(stats.mots_par_minute / CLAVIER_MPM)
                        if stats.mots_par_minute else None),
        },
        "corrections": {
            "total": mot.milliers(historique.total_corrections()),
            "termes": mot.milliers(len(lexique)),
            "remplacements": mot.milliers(
                sum(terme.usages for terme in lexique.termes)),
        },
        "volume": {
            "mots": mot.milliers(stats.total_mots),
            "dictees": mot.nombre(stats.total_dictees, "dictee"),
            "gagne": mot.nombre(temps_gagne(stats), "minute_gagnee"),
            "tendance": tendance(historique),
        },
        "applications": {
            # Le nombre seul : le libelle qui l'accompagne est celui de la
            # carte, et la page le pose ou elle veut.
            "total": mot.milliers(
                len(historique.usage_par_application(limite=99))),
            "lignes": lignes_usage(usage, mot),
        },
        "activite": calendrier(historique, mot),
        "pied": pied(stats, mot),
    }


def temps_gagne(stats) -> int:
    """Minutes economisees contre la frappe, a cadence mesuree."""
    if not stats.total_mots or not stats.mots_par_minute:
        return 0
    clavier = stats.total_mots / CLAVIER_MPM
    voix = stats.total_mots / stats.mots_par_minute
    return round(max(0, clavier - voix))


def tendance(historique: store.Historique) -> dict | None:
    """Variation du mois en cours par rapport au precedent.

    Muette le premier mois : « +100 % » compare a rien ne veut rien dire.
    """
    precedent = historique.mots_du_mois(1)
    if not precedent:
        return None
    variation = (historique.mots_du_mois() - precedent) / precedent * 100
    return {"texte": f"{abs(variation):.0f} %", "hausse": variation >= 0}


def lignes_usage(usage: list, mot: module_langue.Traducteur) -> list[dict]:
    """Une ligne par application, avec sa part du total."""
    total = sum(mots for _cible, _n, mots in usage) or 1
    return [
        {
            "picto": applications.pictogramme(cible),
            "nom": applications.nom(cible, mot.langue),
            "mots": mot.nombre(mots, "mot"),
            "part": mots / total,
            "pourcentage": f"{mots / total * 100:.0f} %",
        }
        for cible, _n, mots in usage
    ]


def colonnes(serie: list) -> list[list]:
    """Repartit la serie en semaines, lundi en haut.

    Le debut est comble par des cases vides jusqu'au lundi : sans cela, les
    rangees ne correspondraient plus a des jours fixes et la grille perdrait
    son sens.
    """
    if not serie:
        return []
    cases = [None] * serie[0][0].weekday() + list(serie)
    while len(cases) % 7:
        cases.append(None)
    return [cases[i:i + 7] for i in range(0, len(cases), 7)]


def calendrier(historique: store.Historique, mot: module_langue.Traducteur,
               decalage: int = 0) -> dict:
    """Le calendrier d'activite, page par page.

    `decalage` recule d'autant de pages de `JOURS_CALENDRIER` jours : les
    fleches de la carte s'en servent pour remonter le temps sans que la page
    ait a connaitre la moindre date.
    """
    serie = historique.mots_par_jour(JOURS_CALENDRIER,
                                     recul=max(0, decalage) * JOURS_CALENDRIER)
    stats = historique.statistiques()
    return {
        "serie": mot.nombre(stats.jours_consecutifs, "jour_serie"),
        "record": mot.nombre(historique.plus_longue_serie(), "jour"),
        "jours": [module_langue.JOURS[mot.langue][rang][:2].capitalize()
                  for rang in range(7)],
        "mois": mois(serie, mot),
        "cases": cases(serie, mot),
    }


def niveau(mots: int, maximum: int) -> int:
    """Palier d'un jour, de 0 a NIVEAUX.

    Les paliers sont pris sur le maximum **observe** et non sur des seuils
    fixes : le meme calendrier doit rester lisible pour qui dicte cent mots
    par jour comme pour qui en dicte cinq mille.
    """
    if mots <= 0:
        return 0
    # Le premier palier commence des le premier mot : un jour ou l'on a dicte
    # ne doit jamais se confondre avec un jour vide.
    return min(NIVEAUX, 1 + int(mots * NIVEAUX / (maximum + 1)))


def cases(serie: list, mot: module_langue.Traducteur | None = None) -> list:
    """Une entree par case de la grille, dans l'ordre de lecture.

    Chaque case porte son palier, sa date et son compte : la page en a besoin
    pour l'infobulle, et calculer cela cote page reviendrait a y redescendre
    les regles de l'application.

    `None` marque les cases de remplissage — les jours qui precedent le debut
    de la serie. La page les laisse vides plutot que de les peindre au palier
    le plus pale, ce qui inventerait des jours.
    """
    maximum = max((valeur for _jour, valeur in serie), default=0)
    plates: list = []
    for colonne in colonnes(serie):
        for case in colonne:
            if case is None:
                plates.append(None)
                continue
            jour, mots = case
            plates.append({
                "niveau": niveau(mots, maximum),
                "jour": jour.isoformat(),
                "titre": (f"{mot.nombre(mots, 'mot')} · {mot.jour_long(jour)}"
                          if mot is not None else jour.isoformat()),
            })
    return plates


def mois(serie: list, mot: module_langue.Traducteur) -> list[dict]:
    """Largeur de chaque mois, en nombre de colonnes."""
    releve: list[dict] = []
    for colonne in colonnes(serie):
        jours = [case[0] for case in colonne if case]
        if not jours:
            continue
        nom = mot.mois_court(jours[0].month)
        if releve and releve[-1]["nom"] == nom:
            releve[-1]["semaines"] += 1
        else:
            releve.append({"nom": nom, "semaines": 1})
    return releve


def pied(stats, mot: module_langue.Traducteur) -> dict:
    return {
        "gauche": f"{mot.nombre(stats.total_dictees, 'dictee')}   ·   "
                  f"{mot.nombre(stats.total_mots, 'mot')}",
    }


def dictees(historique: store.Historique, mot: module_langue.Traducteur,
            limite: int, terme: str = "") -> dict:
    """Historique, groupe par jour, pour la page Dictation."""
    terme = terme.strip()
    # Une de plus que demande : c'est ce qui dit s'il en reste, sans second
    # passage en base pour les compter.
    trouvees = (historique.chercher(terme, limite=limite + 1) if terme
                else historique.recentes(limite=limite + 1))
    reste = len(trouvees) > limite

    groupes: list[dict] = []
    for dictee in trouvees[:limite]:
        jour = dictee.horodatage.date()
        if not groupes or groupes[-1]["jour"] != jour.isoformat():
            groupes.append({"jour": jour.isoformat(),
                            "titre": mot.jour_relatif(jour).upper(),
                            "lignes": []})
        groupes[-1]["lignes"].append({
            "id": dictee.identifiant,
            "heure": mot.heure(dictee.horodatage),
            "texte": dictee.texte,
        })

    stats = historique.statistiques()
    return {
        "groupes": groupes,
        "reste": reste,
        "sous_titre": f"{mot.nombre(stats.mots_aujourdhui, 'mot')} "
                      f"{mot('dictees.aujourdhui')}",
        "pied": pied(stats, mot),
    }


def dictionnaire(lexique: lexicon.Lexique,
                 mot: module_langue.Traducteur) -> dict:
    """Termes du lexique, pour la page Dictionary."""
    hors_prompt = set(lexique.termes_hors_prompt())
    sous_titre = mot.nombre(len(lexique), "terme")
    if hors_prompt:
        sous_titre += " · " + mot("dico.hors_prompt.compte",
                                  nombre=len(hors_prompt))

    return {
        "sous_titre": sous_titre,
        "termes": [
            {
                "terme": terme.terme,
                "variantes": terme.variantes,
                "usages": (mot.nombre(terme.usages, "correction")
                           if terme.usages else None),
                "hors_prompt": terme.terme in hors_prompt,
            }
            for terme in sorted(lexique.termes,
                                key=lambda t: t.terme.lower())
        ],
    }


# --------------------------------------------------------------------------
# Reglages
# --------------------------------------------------------------------------
#
# Le formulaire est **decrit ici**, pas dans la page : sa structure est une
# regle de l'application — quels reglages existent, de quel type, dans quelle
# section — et non un choix de mise en page. Elle se verifie donc sans ouvrir
# de fenetre, ce qui etait impossible tant que chaque champ etait un appel
# Tkinter noye dans le code de construction.

#: Sections, dans l'ordre d'affichage.
SECTIONS = ("raccourcis", "apparence", "comportement", "systeme")

#: Valeur du micro « par defaut ». Une chaine vide plutot que `None` : la page
#: renvoie ce qu'elle a recu, et JSON ne distingue pas `None` de « rien ».
MICRO_DEFAUT = ""

#: Chemin qui ne mene pas a la configuration : le demarrage automatique est un
#: etat du systeme (un raccourci depose dans le dossier de demarrage), lu et
#: ecrit ailleurs. Il figure dans le formulaire comme les autres.
DEMARRAGE = "systeme.demarrage_auto"

#: Un champ par reglage : (section, chemin, type, libelle, aide, choix).
#: Les libelles sont des cles de la table des textes, resolues plus bas.
CHAMPS: tuple[dict, ...] = (
    {"section": "raccourcis", "chemin": "raccourcis.maintien",
     "type": "texte", "libelle": "reg.maintien", "aide": "reg.maintien.aide"},
    {"section": "raccourcis", "chemin": "raccourcis.bascule",
     "type": "texte", "libelle": "reg.bascule", "aide": "reg.bascule.aide"},
    {"section": "raccourcis", "chemin": "raccourcis.apprendre",
     "type": "texte", "libelle": "reg.apprendre",
     "aide": "reg.apprendre.aide"},

    {"section": "comportement", "chemin": "audio.peripherique",
     "type": "liste", "libelle": "reg.micro", "aide": "reg.micro.aide"},

    {"section": "apparence", "chemin": "interface.langue", "type": "choix",
     "libelle": "reg.langue",
     "choix": (("fr", "reg.langue.fr"), ("en", "reg.langue.en"))},
    {"section": "apparence", "chemin": "interface.theme", "type": "choix",
     "libelle": "reg.theme",
     "choix": (("auto", "reg.theme.auto"), ("clair", "reg.theme.clair"),
               ("sombre", "reg.theme.sombre"))},
    {"section": "apparence", "chemin": "interface.indicateur_position",
     "type": "choix", "libelle": "reg.position",
     "choix": (("bas", "reg.position.bas"), ("haut", "reg.position.haut"),
               ("curseur", "reg.position.curseur"))},
    {"section": "apparence", "chemin": "interface.indicateur_actif",
     "type": "case", "libelle": "reg.indicateur"},

    {"section": "comportement",
     "chemin": "injection.restaurer_presse_papier", "type": "case",
     "libelle": "reg.presse_papier"},
    {"section": "comportement", "chemin": "vad.actif", "type": "case",
     "libelle": "reg.vad"},
    {"section": "comportement", "chemin": "lexique.actif", "type": "case",
     "libelle": "reg.lexique"},
    {"section": "comportement", "chemin": "lexique.copier_avant_analyse",
     "type": "case", "libelle": "reg.copier", "aide": "reg.copier.aide"},
    {"section": "comportement", "chemin": "nettoyage_ia.actif",
     "type": "case", "libelle": "reg.nettoyage"},

    {"section": "systeme", "chemin": DEMARRAGE, "type": "case",
     "libelle": "reg.demarrage"},
)

#: Note en pied de section. Le chemin des donnees s'y substitue.
NOTES = {"raccourcis": "reg.raccourcis.note", "systeme": "reg.donnees"}


def micros(mot: module_langue.Traducteur) -> list[dict]:
    """Les entrees audio de la machine, pour le selecteur des reglages.

    Enumerees a chaque ouverture des reglages, jamais mises en cache : c'est
    precisement quand la liste a change qu'on vient ici.
    """
    from .. import audio

    choix = [{"valeur": MICRO_DEFAUT, "libelle": mot("reg.micro.defaut")}]
    try:
        choix += [{"valeur": entree["index"], "libelle": entree["nom"]}
                  for entree in audio.peripheriques_entree()]
    except Exception:                      # aucune interface audio disponible
        pass
    return choix


def reglages(conf, mot: module_langue.Traducteur, demarrage: bool,
             dossier: str) -> dict:
    """Le formulaire des reglages : sections, champs, valeurs courantes."""
    listes = {"audio.peripherique": micros(mot)}
    return {
        "sections": [
            {
                "cle": section,
                "titre": mot(f"reg.section.{section}"),
                "champs": [_champ(fiche, conf, mot, demarrage, listes)
                           for fiche in CHAMPS
                           if fiche["section"] == section],
                "note": (mot(NOTES[section], chemin=dossier)
                         if section in NOTES else None),
            }
            for section in SECTIONS
        ],
        "enregistrer": mot("reg.enregistrer"),
    }


def _champ(fiche: dict, conf, mot: module_langue.Traducteur,
           demarrage: bool, listes: dict | None = None) -> dict:
    valeur = demarrage if fiche["chemin"] == DEMARRAGE else conf[fiche["chemin"]]
    if valeur is None:
        valeur = MICRO_DEFAUT
    resolu = {
        "chemin": fiche["chemin"],
        "type": fiche["type"],
        "libelle": mot(fiche["libelle"]),
        "aide": mot(fiche["aide"]) if fiche.get("aide") else None,
        "valeur": valeur,
    }
    if fiche["type"] == "choix":
        resolu["choix"] = [{"valeur": v, "libelle": mot(cle)}
                           for v, cle in fiche["choix"]]
    elif fiche["type"] == "liste":
        resolu["choix"] = (listes or {}).get(fiche["chemin"], [])
        # Un peripherique disparu depuis le dernier enregistrement ne doit pas
        # laisser le selecteur sans reponse : on retombe sur « par defaut ».
        if valeur not in [c["valeur"] for c in resolu["choix"]]:
            resolu["valeur"] = MICRO_DEFAUT
    return resolu

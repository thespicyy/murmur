"""Ouvre la maquette de la page Insights dans une fenetre WebView2.

But : comparer, sur les memes donnees, ce que rend Tkinter et ce que rend un
moteur web. Rien ici n'est branche sur l'application ; la base est lue en
lecture seule.

    .venv\\Scripts\\python.exe maquette\\lancer.py [--sombre]

WebView2 est deja installe sur Windows 11 et partage entre les applications
qui l'utilisent : contrairement a Electron, il n'y a pas de navigateur a
embarquer dans l'executable.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE.parent))


def _declarer_conscience_dpi() -> float:
    """Se declare conscient du DPI, et renvoie l'echelle du systeme.

    A faire **avant** toute fenetre : declaree ensuite, la taille demandee
    reste interpretee dans l'ancien referentiel. Sans cette declaration,
    Windows dessine a cent pour cent puis etire l'image — c'est ce qui rend
    floue une application qui ne la fait pas.
    """
    import ctypes

    from ctypes import wintypes

    try:
        user32 = ctypes.WinDLL("user32")
        # `argtypes` est indispensable : sans lui, ctypes envoie -4 en entier
        # signe de 32 bits la ou Windows attend la taille d'un pointeur, et
        # l'appel echoue sans rien dire.
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return user32.GetDpiForSystem() / 96
    except Exception:
        return 1.0


ECHELLE = _declarer_conscience_dpi()

from murmur import applications, langue as module_langue  # noqa: E402
from murmur import lexicon, store  # noqa: E402

#: Reprises des constantes de la vue Tk, pour que les deux disent la meme
#: chose des memes donnees.
CLAVIER_MPM = 40
JAUGE_MAX_MPM = 250
JOURS_CALENDRIER = 154

#: Traces SVG des pictogrammes d'usage, repris de `icones.TRACES`. Le trait
#: est decrit une fois et le navigateur le lisse — c'est tout le sujet.
PICTOS = {
    "app_navigateur": '<circle cx="12" cy="12" r="8"/><line x1="4" y1="12" '
                      'x2="20" y2="12"/><ellipse cx="12" cy="12" rx="4" ry="8"/>',
    "app_code": '<path d="M9 8 4.5 12 9 16M15 8l4.5 4L15 16"/>',
    "app_terminal": '<rect x="3.5" y="5" width="17" height="14" rx="2.5"/>'
                    '<path d="M7 10l3 2.5L7 15M12.5 15.5h4.5"/>',
    "app_message": '<path d="M5 17V7.5h14v8H9.5L5 19z"/>',
    "app_courriel": '<rect x="3.5" y="6" width="17" height="12" rx="2"/>'
                    '<path d="M3.5 7.5 12 13.5 20.5 7.5"/>',
    "app_document": '<path d="M6 20V4h9l3 3v13H6z"/><path d="M9 11h6M9 15h6"/>',
    "app_note": '<rect x="5.5" y="5.5" width="13" height="13" rx="1"/>'
                '<path d="M9 10h6M9 14h4"/>',
    "app_media": '<circle cx="8" cy="17" r="3"/><circle cx="15" cy="15" r="3"/>'
                 '<path d="M11 17V5l7 2v8"/>',
    "app_jeu": '<rect x="3" y="8" width="18" height="9" rx="4"/>'
               '<path d="M7.5 10.5v4M5.5 12.5h4"/>'
               '<circle cx="16" cy="11.5" r="1.3" fill="currentColor"/>'
               '<circle cx="18.5" cy="14" r="1.3" fill="currentColor"/>',
    "app_ia": '<path d="M12 3.5 13.6 9.4 19.5 11 13.6 12.6 12 18.5 10.4 12.6'
              ' 4.5 11 10.4 9.4Z"/>',
    "app_dossier": '<path d="M3.5 8v10.5h17V8M3.5 8V5.5h6l2 2.5h9"/>',
    "app_autre": '<rect x="3.5" y="5" width="17" height="11" rx="2"/>'
                 '<path d="M9 20h6M12 16v4"/>',
}


def svg(nom: str) -> str:
    trace = PICTOS.get(nom, PICTOS["app_autre"])
    return (f'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.7" '
            f'stroke-linecap="round" stroke-linejoin="round">{trace}</svg>')


def rassembler() -> dict:
    """Lit la vraie base et compose ce que la page doit afficher."""
    mot = module_langue.Traducteur(langue="en")
    historique = store.Historique()
    try:
        stats = historique.statistiques()
        usage = historique.usage_par_application(limite=5)
        total_apps = len(historique.usage_par_application(limite=99))
        corrections = historique.total_corrections()
        courant = historique.mots_du_mois()
        precedent = historique.mots_du_mois(1)
        serie = historique.mots_par_jour(JOURS_CALENDRIER)
    finally:
        historique.fermer()

    lexique = lexicon.Lexique()
    usages = sum(t.usages for t in lexique.termes)

    rapport = stats.mots_par_minute / CLAVIER_MPM if stats.mots_par_minute else 0
    minutes = (round(max(0, stats.total_mots / CLAVIER_MPM
                         - (stats.total_mots / stats.mots_par_minute
                            if stats.mots_par_minute else 0)))
               if stats.total_mots and stats.mots_par_minute else 0)

    tendance, hausse = "", True
    if precedent:
        variation = (courant - precedent) / precedent * 100
        hausse = variation >= 0
        tendance = f"{'↗' if hausse else '↘'} {abs(variation):.0f} %"

    total_mots_usage = sum(mots for _, _, mots in usage) or 1
    maximum = max((valeur for _, valeur in serie), default=0) or 1

    return {
        "vitesse": f"{stats.mots_par_minute:.0f}",
        "part_vitesse": min(1.0, stats.mots_par_minute / JAUGE_MAX_MPM),
        "rapport": f"×{rapport:.1f}" if rapport else "—",
        "corrections": mot.milliers(corrections),
        "termes": mot.milliers(len(lexique)),
        "remplacements": mot.milliers(usages),
        "mots": mot.milliers(stats.total_mots),
        "dictees": mot.nombre(stats.total_dictees, "dictee"),
        "gagne": mot.nombre(minutes, "minute_gagnee"),
        "tendance": tendance,
        "hausse": hausse,
        "nb_apps": mot.nombre(total_apps, "application").upper(),
        "serie": mot.nombre(stats.jours_consecutifs, "jour_serie"),
        "pied_gauche": f"{mot.nombre(stats.total_dictees, 'dictee')}   ·   "
                       f"{mot.nombre(stats.total_mots, 'mot')}",
        "pied_droite": "hold ctrl+alt+d",
        "applications": [
            {"picto": svg(applications.pictogramme(cible)),
             "nom": applications.nom(cible, "en"),
             "mots": f" {mot.milliers(mots)} words",
             "part": mots / total_mots_usage}
            for cible, _n, mots in usage
        ],
        "jours": [module_langue.JOURS["en"][rang][:2] for rang in range(7)],
        "mois": mois_visibles(serie),
        # `None` marque les cases ajoutees pour aligner la premiere colonne
        # sur un lundi : elles restent vides.
        "cases": cases(serie, maximum),
    }


def colonnes(serie: list) -> list[list]:
    """Repartit la serie en semaines, lundi en haut — comme `graphe`."""
    if not serie:
        return []
    cases = [None] * serie[0][0].weekday() + list(serie)
    while len(cases) % 7:
        cases.append(None)
    return [cases[i:i + 7] for i in range(0, len(cases), 7)]


def cases(serie: list, maximum: int) -> list:
    """Intensite de chaque case, de 0 a 1, dans l'ordre de la grille."""
    plates = []
    for colonne in colonnes(serie):
        for case in colonne:
            if case is None:
                plates.append(None)
            elif not case[1]:
                plates.append(0.0)
            else:
                plates.append(round(0.18 + 0.82 * case[1] / maximum, 3))
    return plates


def mois_visibles(serie: list) -> list[dict]:
    """Largeur de chaque mois, en nombre de colonnes."""
    releve: list[dict] = []
    for colonne in colonnes(serie):
        jours = [case[0] for case in colonne if case]
        if not jours:
            continue
        nom = module_langue.MOIS_COURTS["en"][jours[0].month - 1]
        if releve and releve[-1]["nom"] == nom:
            releve[-1]["semaines"] += 1
        else:
            releve.append({"nom": nom, "semaines": 1})
    return releve


class Pont:
    """Ce que la page peut demander a Python — l'equivalent du `BarreTitre`."""

    def __init__(self):
        self.fenetre = None

    def reduire(self):
        self.fenetre.minimize()

    def agrandir(self):
        self.fenetre.toggle_fullscreen()

    def fermer(self):
        self.fenetre.destroy()


def main() -> None:
    import webview

    sombre = "--sombre" in sys.argv
    gabarit = (RACINE / "page.html").read_text(encoding="utf-8")
    page = gabarit.replace("/*{{DONNEES}}*/ {}",
                           json.dumps(rassembler(), ensure_ascii=False))
    if sombre:
        page = page.replace("<meta charset=\"utf-8\">",
                            "<meta charset=\"utf-8\">"
                            "<script>document.documentElement"
                            ".dataset.theme='sombre'</script>")

    # Ecrit a cote des feuilles de style : le navigateur doit pouvoir les
    # charger par chemin relatif.
    rendu = RACINE / "_rendu.html"
    rendu.write_text(page, encoding="utf-8")

    pont = Pont()
    # WebView2 est conscient du DPI et rend a l'echelle du systeme. Sur un
    # ecran a 125 %, il faut donc un quart de pixels en plus pour offrir la
    # meme largeur utile que la fenetre Tk, qui, elle, ne l'est pas.
    pont.fenetre = webview.create_window(
        "Murmur — maquette", str(rendu),
        width=round(1060 * ECHELLE), height=round(700 * ECHELLE),
        frameless=True, easy_drag=False, js_api=pont,
        background_color="#f5f4f0" if not sombre else "#15131a")
    webview.start()


if __name__ == "__main__":
    main()

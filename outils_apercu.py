r"""Prepare un apercu de la page hors de WebView2, en un seul fichier.

Raison d'etre : la fenetre du tableau de bord ne s'ouvre pas depuis un
lancement automatise — seul un lancement manuel y parvient. Sans cet apercu,
toute verification visuelle du rendu devrait passer par l'utilisateur.

Le pont vers Python est simule avec de vraies donnees, prises dans la base.
Tout est inline — feuille de style, scripts, donnees — parce que le volet de
previsualisation sert la page en `data:`, ou les chemins relatifs ne menent
nulle part.

    .venv\Scripts\python.exe outils_apercu.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from murmur import config as configuration, langue as module_langue  # noqa: E402
from murmur import lexicon, store, systeme  # noqa: E402
from murmur.tableau import donnees  # noqa: E402

WEB = RACINE / "murmur" / "tableau" / "web"
SORTIE = RACINE / "maquette" / "apercu"

PONT = """<script>
/* Pont simule : les memes methodes que `tableau.api`, servies figees. */
const CHARGE = __DONNEES__;
window.pywebview = { api: {
  insights: async () => CHARGE.insights,
  dictees: async () => CHARGE.dictees,
  dictionnaire: async () => CHARGE.dictionnaire,
  reglages: async () => CHARGE.reglages,
  calendrier: async () => CHARGE.insights.activite,
  enregistrer_reglages: async () => ({ ok: true }),
  textes: async () => CHARGE.textes,
  etat: async () => CHARGE.etat,
  replier: async () => ({ ok: true }),
  supprimer_dictee: async () => ({ ok: true }),
  ajouter_terme: async () => ({ ok: true }),
  retirer_terme: async () => ({ ok: true }),
  reduire: () => {}, agrandir: () => {}, fermer: () => {},
  deplacer: () => {}, redimensionner_haut: () => {},
} };
</script>"""


def charger(langue: str = "en", theme: str = "clair",
            page: str = "") -> dict:
    mot = module_langue.Traducteur(langue=langue)
    historique = store.Historique()
    lexique = lexicon.Lexique()
    try:
        return {
            "insights": donnees.insights(historique, lexique, mot),
            "dictees": donnees.dictees(historique, mot, 40),
            "dictionnaire": donnees.dictionnaire(lexique, mot),
            "calendrier": donnees.calendrier(historique, mot),
            "reglages": donnees.reglages(
                configuration.charger(), mot, systeme.demarrage_auto_actif(),
                str(configuration.dossier_donnees())),
            "textes": {cle: mot(cle) for cle in module_langue.TEXTES},
            "etat": {"langue": langue, "theme": theme, "repliee": False,
                     "raccourci": "ctrl+alt+d", "page": page},
        }
    finally:
        historique.fermer()


def batir(langue: str = "en", theme: str = "clair", ouvrir_sur: str = "",
          sortie: Path | None = None) -> Path:
    """Ecrit une page autonome. `ouvrir_sur` choisit l'onglet affiche."""
    dossier = sortie or SORTIE
    dossier.mkdir(parents=True, exist_ok=True)
    page = (WEB / "index.html").read_text(encoding="utf-8")
    page = page.replace(
        '<link rel="stylesheet" href="style.css">',
        "<style>" + (WEB / "style.css").read_text(encoding="utf-8") + "</style>")
    page = page.replace(
        '<script src="pictos.js"></script>\n<script src="app.js"></script>',
        PONT.replace("__DONNEES__",
                     json.dumps(charger(langue, theme, ouvrir_sur),
                                ensure_ascii=False))
        + "<script>" + (WEB / "pictos.js").read_text(encoding="utf-8") + "</script>"
        + "<script>" + (WEB / "app.js").read_text(encoding="utf-8")
        + "\ndemarrer();</script>")

    suffixe = f"_{ouvrir_sur}" if ouvrir_sur else ""
    chemin = dossier / f"apercu_{langue}_{theme}{suffixe}.html"
    chemin.write_text(page, encoding="utf-8")
    return chemin


if __name__ == "__main__":
    for langue in ("en", "fr"):
        for theme in ("clair", "sombre"):
            print("  ", batir(langue, theme))

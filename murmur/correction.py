"""Validation des corrections apprises, en boite de dialogue.

Extrait du tableau de bord Tkinter quand celui-ci est passe au moteur web.
C'est la seule fenetre de l'application qui reste dessinee par Tk, et elle a
de bonnes raisons d'y rester : elle apparait **pendant** qu'on travaille
ailleurs, sur une pression de raccourci, et doit s'afficher en une fraction de
seconde. Lancer une douzaine de processus WebView2 pour trois cases a cocher
couterait plus cher que tout ce qu'elle affiche.

Rien n'est appris sans accord : les differences que Murmur classe comme
reformulation restent affichees mais decochees, et l'inverse. C'est
l'utilisateur qui tranche.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from . import arrondi, chrome, graphe, icones, journal
from . import langue as module_langue, theme as module_theme

_log = journal.obtenir("correction")

LARGEUR = 580
HAUTEUR = 480
RAYON_CARTE = 10
RAYON_BOUTON = 9
TAILLE_CASE = 18


def centrer(fenetre, largeur: int, hauteur: int) -> None:
    """Pose la fenetre au centre de l'ecran.

    Au centre de l'ecran et non de celle qui l'ouvre : depuis que le tableau
    de bord vit dans un autre processus, la fenetre qui ouvre celle-ci est la
    racine invisible de Tk — un point sans dimensions, en haut a gauche.
    """
    x = (fenetre.winfo_screenwidth() - largeur) // 2
    y = (fenetre.winfo_screenheight() - hauteur) // 2
    fenetre.geometry(f"{largeur}x{hauteur}+{max(0, x)}+{max(0, y)}")


class Boite:
    """Boite de validation d'un apprentissage.

    Construite a chaque apprentissage puis detruite : elle ne vit que le temps
    d'une decision, et rien n'a besoin de lui survivre.
    """

    def __init__(self, racine, conf, theme):
        self.racine = racine
        self.conf = conf
        self.theme = theme
        self.mot = module_langue.Traducteur(conf)
        self.police = module_theme.police_disponible(racine)
        # Tk ne retient pas les PhotoImage : sans cette reserve, les cases a
        # cocher disparaitraient des le ramassage des miettes.
        self._images: dict[str, object] = {}

    # -- entree ------------------------------------------------------------

    def montrer(self, analyse, sur_validation,
                diagnostic: str | None = None) -> None:
        """Propose les substitutions detectees, ou explique qu'il n'y en a pas."""
        if analyse is None:
            detail = ("\n\n" + self.mot("corr.raison", raison=diagnostic)
                      if diagnostic else "")
            self._dire(self.mot("corr.aucune") + detail + "\n\n"
                       + self.mot("corr.aucune.aide"))
            return

        if not analyse.substitutions:
            self._dire(self.mot("corr.identique"))
            return

        self._batir(analyse, sur_validation)

    def _dire(self, message: str) -> None:
        """Montre un message, PAR-DESSUS l'application ou l'on travaille.

        Une boite de dialogue sans parent nait derriere la fenetre au premier
        plan : le raccourci semble alors n'avoir rien fait. C'est exactement ce
        qui s'est produit — le journal montrait deux analyses menees a bien, et
        l'utilisateur n'avait rien vu passer.

        On lui donne donc un parent invisible mais toujours au-dessus. La
        fenetre des substitutions se posait deja ainsi ; seul ce message-ci
        avait ete oublie.
        """
        support = tk.Toplevel(self.racine)
        support.withdraw()
        support.attributes("-topmost", True)
        try:
            messagebox.showinfo("Murmur", message, parent=support)
        finally:
            support.destroy()

    # -- construction ------------------------------------------------------

    def _batir(self, analyse, sur_validation) -> None:
        palette = self.theme.palette
        boite = tk.Toplevel(self.racine)
        boite.title(self.mot("corr.titre"))
        boite.configure(bg=palette.surface)
        # Au premier plan : elle repond a un raccourci presse dans une autre
        # application, qui garde le focus.
        boite.attributes("-topmost", True)
        centrer(boite, LARGEUR, HAUTEUR)
        boite.update_idletasks()
        chrome.habiller(boite, palette)

        tk.Label(boite, text=self.mot("corr.titre"), bg=palette.surface,
                 fg=palette.texte, font=(self.police, 16, "bold"),
                 anchor="w").pack(fill="x", padx=26, pady=(24, 4))
        tk.Label(boite, text=self.mot("corr.aide"), bg=palette.surface,
                 fg=palette.texte_doux, font=(self.police, 9), anchor="w",
                 wraplength=LARGEUR - 70, justify="left").pack(
                     fill="x", padx=26, pady=(0, 16))

        zone = tk.Frame(boite, bg=palette.surface)
        zone.pack(fill="both", expand=True, padx=26)

        choix: list[tuple[tk.BooleanVar, object]] = []
        for substitution in analyse.substitutions:
            variable = tk.BooleanVar(value=substitution.est_vocabulaire)
            choix.append((variable, substitution))
            self._ligne(zone, variable, substitution)

        boutons = tk.Frame(boite, bg=palette.surface)
        boutons.pack(fill="x", padx=26, pady=20)

        def valider():
            retenues = [s for variable, s in choix if variable.get()]
            if not retenues:
                # Enregistrer sans rien avoir coche n'apprend rien. Fermer en
                # silence laisserait croire le contraire — c'est arrive, et
                # l'utilisateur a cherche ensuite ou etait passe son terme.
                self._dire(self.mot("corr.rien_coche"))
                return
            sur_validation(analyse, retenues)
            boite.destroy()

        self._bouton(boutons, self.mot("corr.enregistrer"), valider,
                     principal=True).pack(side="left")
        self._bouton(boutons, self.mot("corr.ignorer"),
                     boite.destroy).pack(side="left", padx=10)

    def _ligne(self, zone, variable, substitution) -> None:
        palette = self.theme.palette
        carte = arrondi.Carte(zone, palette.carte, rayon=RAYON_CARTE)
        carte.pack(fill="x", pady=3)
        ligne = carte.interieur

        self._case(ligne, variable).pack(side="left", padx=(4, 8))
        texte = tk.Frame(ligne, bg=palette.carte)
        texte.pack(side="left", fill="x", expand=True, pady=10)
        tk.Label(texte, text=substitution.avant, bg=palette.carte,
                 fg=palette.erreur, font=(self.police, 10),
                 anchor="w").pack(side="left")
        tk.Label(texte, text="   →   ", bg=palette.carte,
                 fg=palette.texte_faible,
                 font=(self.police, 10)).pack(side="left")
        tk.Label(texte, text=substitution.apres, bg=palette.carte,
                 fg=palette.ecoute, font=(self.police, 10, "bold"),
                 anchor="w").pack(side="left")

    # -- elements dessines -------------------------------------------------

    def _image(self, cle: str, fabrique):
        if cle not in self._images:
            from PIL import ImageTk
            self._images[cle] = ImageTk.PhotoImage(fabrique())
        return self._images[cle]

    def _case(self, parent, variable) -> tk.Label:
        """Case a cocher dessinee.

        Celle de Tk est rendue par Windows : bord gris, coins droits, coche
        anguleuse. Elle ne se laisse pas recolorier et se reconnait au premier
        coup d'oeil comme un element etranger au reste.
        """
        palette = self.theme.palette
        fond = parent.cget("bg")
        etiquette = tk.Label(parent, bg=fond, cursor="hand2", bd=0,
                             highlightthickness=0)

        def peindre(*_):
            cochee = bool(variable.get())
            etiquette.configure(image=self._image(
                f"case:{cochee}:{fond}",
                lambda: icones.case(cochee, TAILLE_CASE, fond,
                                    palette.bordure, palette.accent,
                                    palette.accent_texte)))

        variable.trace_add("write", peindre)
        etiquette.bind("<Button-1>",
                       lambda _e: variable.set(not variable.get()))
        peindre()
        return etiquette

    def _bouton(self, parent, texte: str, commande, principal: bool = False):
        palette = self.theme.palette
        fond = (palette.accent if principal
                else graphe.melange(parent.cget("bg"), palette.texte, 0.10))
        couleur = palette.accent_texte if principal else palette.texte
        carte = arrondi.Carte(parent, fond, rayon=RAYON_BOUTON)
        etiquette = tk.Label(carte.interieur, text=texte, cursor="hand2",
                             font=(self.police, 10), bg=fond, fg=couleur,
                             padx=8, pady=7)
        etiquette.pack(fill="both", expand=True)
        etiquette.bind("<Button-1>", lambda _e: commande())

        survol = (palette.texte_doux if principal
                  else graphe.melange(fond, palette.texte, 0.10))

        def peindre(couleur_fond):
            carte.repeindre(fond=couleur_fond)
            etiquette.configure(bg=couleur_fond)

        etiquette.bind("<Enter>", lambda _e: peindre(survol))
        etiquette.bind("<Leave>", lambda _e: peindre(fond))
        return carte

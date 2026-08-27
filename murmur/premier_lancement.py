"""Le premier lancement : obtenir le modele, en le disant.

C'est le seul moment ou Murmur touche au reseau, et le seul ou il fait
attendre. Les deux mefaits classiques sont donc a eviter ensemble : partir
telecharger 574 Mo sans prevenir, et faire attendre sans montrer que quelque
chose avance.

La fenetre est dessinee par Tk et non par le tableau de bord : a ce stade
l'application n'est pas encore demarree, et lancer douze processus WebView2
pour une barre de progression couterait plus cher que ce qu'elle affiche.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from . import arrondi, chrome, graphe, journal, modeles, vulkan
from . import langue as module_langue, theme as module_theme

_log = journal.obtenir("premier")

LARGEUR = 520
HAUTEUR = 250
RAYON_CARTE = 10
RAYON_BOUTON = 9
HAUTEUR_BARRE = 6

#: La progression est rafraichie au plus souvent tous les deux dixiemes de
#: seconde. Redessiner a chaque bloc recu occuperait plus de temps que le
#: telechargement lui-meme.
PAS_MS = 200


class Accueil:
    """Fenetre de premier lancement : annonce, telecharge, rend la main."""

    def __init__(self, conf, theme, racine):
        self.conf = conf
        self.theme = theme
        self.mot = module_langue.Traducteur(conf)
        # La racine est PRETEE, pas creee ici : deux racines Tk dans un meme
        # processus font planter la seconde des que la premiere est detruite.
        # Mesure : code de sortie 0x80000003, sans une ligne de journal — le
        # telechargement reussissait, et l'application disparaissait juste
        # apres.
        self.racine = racine
        self.racine.withdraw()
        self.police = module_theme.police_disponible(self.racine)

        self.modele = modeles.choisir(self._carte_presente())
        self._abandon = threading.Event()
        self._echec: str | None = None
        self._fini = False
        #: Ecrit par le fil de telechargement, lu par celui de l'interface.
        #: Un entier n'a pas besoin de verrou ; l'affichage, si.
        self._recus = 0
        self._total = self.modele.octets

    # -- decision ----------------------------------------------------------

    def _carte_presente(self) -> bool:
        """Cette machine a-t-elle une carte graphique exploitable ?

        La reponse decide du modele, et l'ecart est considerable : mesure sur
        une phrase de huit secondes, 250 ms avec la carte contre 9 400 ms sans.
        Un grand modele sur un processeur seul ne se dicte pas, il se subit.
        """
        try:
            cartes = vulkan.enumerer(self.conf.chemin_serveur)
        except Exception:
            _log.exception("enumeration des cartes impossible")
            return False
        if cartes:
            _log.info("carte trouvee : %s", vulkan.choisir(cartes))
        else:
            _log.info("aucune carte Vulkan : modele adapte au processeur")
        return bool(cartes)

    # -- deroulement -------------------------------------------------------

    def executer(self) -> bool:
        """Montre la fenetre et telecharge. Vrai si le modele est en place.

        Rend `False` quand l'utilisateur renonce ou que le telechargement
        echoue : l'appelant s'arrete alors, plutot que de demarrer une
        application qui ne saura pas transcrire.
        """
        self._batir()
        self.racine.deiconify()
        threading.Thread(target=self._travailler, daemon=True,
                         name="telechargement").start()
        self.racine.after(PAS_MS, self._rafraichir)
        self.racine.mainloop()
        # Rendue dans l'etat ou on l'a trouvee : videe de nos widgets, cachee,
        # et surtout vivante — c'est la racine de toute l'application.
        for widget in self.racine.winfo_children():
            widget.destroy()
        self.racine.withdraw()
        self.racine.protocol("WM_DELETE_WINDOW", lambda: None)

        if self._echec:
            return False
        return self._fini

    def _travailler(self) -> None:
        try:
            modeles.telecharger(
                self.modele,
                progression=self._avancer,
                arret=self._abandon.is_set)
            self.conf.definir("moteur.modele", self.modele.fichier)
            self.conf.sauvegarder()
            self._fini = True
        except modeles.ErreurTelechargement as exc:
            if not self._abandon.is_set():
                self._echec = str(exc)
                _log.error("modele non obtenu : %s", exc)

    def _avancer(self, recus: int, total: int) -> None:
        self._recus, self._total = recus, max(total, 1)

    def _rafraichir(self) -> None:
        """Redessine la progression, depuis le fil de l'interface.

        Tk n'accepte ses widgets que du fil qui les a crees : le fil de
        telechargement se contente de poser deux entiers, et c'est ici qu'on
        les lit.
        """
        if self._fini or self._echec or self._abandon.is_set():
            self.racine.quit()
            return

        part = min(1.0, self._recus / self._total)
        self._barre.configure(width=max(1, int(self._largeur_barre * part)))
        faits = self._recus / 1_000_000
        self._compte.configure(
            text=f"{faits:.0f} / {self.modele.megaoctets} Mo")
        self.racine.after(PAS_MS, self._rafraichir)

    def _renoncer(self) -> None:
        self._abandon.set()
        self.racine.quit()

    # -- fenetre -----------------------------------------------------------

    def _batir(self) -> None:
        palette = self.theme.palette
        self.racine.title(self.mot("premier.titre"))
        self.racine.configure(bg=palette.surface)
        self.racine.resizable(False, False)
        self.racine.protocol("WM_DELETE_WINDOW", self._renoncer)
        self._centrer()
        self.racine.update_idletasks()
        chrome.habiller(self.racine, palette)

        tk.Label(self.racine, text=self.mot("premier.titre"),
                 bg=palette.surface, fg=palette.texte,
                 font=(self.police, 16, "bold"), anchor="w").pack(
                     fill="x", padx=26, pady=(24, 6))
        tk.Label(self.racine,
                 text=self.mot("premier.explication",
                               taille=self.modele.megaoctets,
                               detail=self.mot(self.modele.resume)),
                 bg=palette.surface, fg=palette.texte_doux,
                 font=(self.police, 9), anchor="w", justify="left",
                 wraplength=LARGEUR - 60).pack(fill="x", padx=26, pady=(0, 18))

        piste = tk.Frame(self.racine, bg=palette.carte, height=HAUTEUR_BARRE)
        piste.pack(fill="x", padx=26)
        piste.pack_propagate(False)
        self._largeur_barre = LARGEUR - 52
        self._barre = tk.Frame(piste, bg=palette.accent, width=1,
                               height=HAUTEUR_BARRE)
        self._barre.place(x=0, y=0)

        self._compte = tk.Label(self.racine,
                                text=f"0 / {self.modele.megaoctets} Mo",
                                bg=palette.surface, fg=palette.texte_faible,
                                font=(self.police, 9), anchor="w")
        self._compte.pack(fill="x", padx=26, pady=(8, 0))

        boutons = tk.Frame(self.racine, bg=palette.surface)
        boutons.pack(fill="x", padx=26, pady=18)
        self._bouton(boutons, self.mot("premier.renoncer"),
                     self._renoncer).pack(side="right")

    def _centrer(self) -> None:
        x = (self.racine.winfo_screenwidth() - LARGEUR) // 2
        y = (self.racine.winfo_screenheight() - HAUTEUR) // 2
        self.racine.geometry(f"{LARGEUR}x{HAUTEUR}+{max(0, x)}+{max(0, y)}")

    def _bouton(self, parent, texte: str, commande):
        palette = self.theme.palette
        fond = graphe.melange(parent.cget("bg"), palette.texte, 0.10)
        carte = arrondi.Carte(parent, fond, rayon=RAYON_BOUTON)
        etiquette = tk.Label(carte.interieur, text=texte, cursor="hand2",
                             font=(self.police, 10), bg=fond, fg=palette.texte,
                             padx=10, pady=7)
        etiquette.pack(fill="both", expand=True)
        etiquette.bind("<Button-1>", lambda _e: commande())
        return carte


def assurer_le_modele(conf, theme, racine) -> bool:
    """Verifie que le modele est la, le telecharge sinon.

    `racine` est la racine Tk de l'application : elle sert de support a la
    fenetre et lui survit. Rend `False` si l'application ne doit pas demarrer
    — modele absent et utilisateur ayant renonce, ou telechargement impossible.
    """
    if conf.chemin_modele.exists():
        return True

    accueil = Accueil(conf, theme, racine)
    if accueil.executer():
        return True

    if accueil._echec:
        messagebox.showerror("Murmur",
                             accueil.mot("premier.echec",
                                         raison=accueil._echec))
    return False

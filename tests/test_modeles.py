"""Le modele de transcription : lequel, ou, et comment l'obtenir.

Le modele n'est pas dans l'archive — 574 Mo pour une application qui en pese
138, dont la moitie des utilisateurs n'ont pas besoin de celui-la. Il est pris
au premier lancement, quand on sait sur quelle machine on est tombe.
"""

import hashlib

import pytest

from murmur import modeles


@pytest.fixture(autouse=True)
def dossier(donnees):
    return donnees


class _Reponse:
    """Doublure de reponse HTTP en flux."""

    def __init__(self, contenu: bytes, code: int = 200):
        self.contenu = contenu
        self.status_code = code

    def raise_for_status(self):
        pass

    def iter_content(self, taille):
        for debut in range(0, len(self.contenu), taille):
            yield self.contenu[debut:debut + taille]

    def close(self):
        pass


def _modele(contenu: bytes) -> modeles.Modele:
    return modeles.Modele(
        fichier="essai.bin", octets=len(contenu),
        empreinte=hashlib.sha256(contenu).hexdigest(), resume="essai")


# --------------------------------------------------------------------------
# Le choix
# --------------------------------------------------------------------------

def test_le_modele_suit_la_machine():
    """L'ecart mesure ne laisse pas le choix : sur une phrase de huit
    secondes, 250 ms avec la carte contre 9 400 ms sans."""
    assert modeles.choisir(True) is modeles.AVEC_CARTE
    assert modeles.choisir(False) is modeles.SANS_CARTE
    assert modeles.SANS_CARTE.octets < modeles.AVEC_CARTE.octets


# --------------------------------------------------------------------------
# La verification
# --------------------------------------------------------------------------

def test_un_fichier_tronque_est_refuse_sans_le_relire():
    """La taille ecarte le cas le plus frequent en une lecture de rien."""
    modele = _modele(b"x" * 5000)
    chemin = modeles.dossier() / modele.fichier
    chemin.write_bytes(b"x" * 400)

    assert not modeles.verifier(chemin, modele)


def test_un_fichier_corrompu_a_la_bonne_taille_est_refuse():
    """Taille juste, contenu faux : seule l'empreinte le dit."""
    modele = _modele(b"le vrai contenu")
    chemin = modeles.dossier() / modele.fichier
    chemin.write_bytes(b"le faux contenu")

    assert not modeles.verifier(chemin, modele)


# --------------------------------------------------------------------------
# Le telechargement
# --------------------------------------------------------------------------

def test_le_modele_est_ecrit_et_verifie(monkeypatch):
    contenu = b"modele" * 5000
    modele = _modele(contenu)
    monkeypatch.setattr("requests.get",
                        lambda *a, **k: _Reponse(contenu))

    chemin = modeles.telecharger(modele)

    assert chemin.read_bytes() == contenu
    assert not list(modeles.dossier().glob("*" + modeles.EN_COURS)), \
        "le fichier de travail n'a pas ete range"


def test_un_telechargement_deja_fait_n_est_pas_refait(monkeypatch):
    contenu = b"deja la" * 1000
    modele = _modele(contenu)
    (modeles.dossier() / modele.fichier).write_bytes(contenu)
    monkeypatch.setattr("requests.get", lambda *a, **k: pytest.fail(
        "le reseau a ete sollicite pour rien"))

    assert modeles.telecharger(modele).read_bytes() == contenu


def test_une_coupure_est_reprise_ou_elle_s_est_arretee(monkeypatch):
    """574 Mo sur une connexion ordinaire, c'est plusieurs minutes : une
    coupure est un evenement normal, pas un incident."""
    contenu = b"abcdefgh" * 4000
    modele = _modele(contenu)
    coupure = len(contenu) // 2
    (modeles.dossier() / (modele.fichier + modeles.EN_COURS)).write_bytes(
        contenu[:coupure])

    demandes = {}

    def get_double(url, headers=None, **_):
        demandes["entetes"] = headers or {}
        return _Reponse(contenu[coupure:], code=206)

    monkeypatch.setattr("requests.get", get_double)
    chemin = modeles.telecharger(modele)

    assert demandes["entetes"].get("Range") == f"bytes={coupure}-"
    assert chemin.read_bytes() == contenu


def test_un_serveur_qui_ignore_la_reprise_repart_de_zero(monkeypatch):
    """Repondre 200 a une demande de reprise, c'est renvoyer le fichier
    entier : le coller a la suite le doublerait."""
    contenu = b"0123456789" * 3000
    modele = _modele(contenu)
    (modeles.dossier() / (modele.fichier + modeles.EN_COURS)).write_bytes(
        contenu[:1000])
    monkeypatch.setattr("requests.get",
                        lambda *a, **k: _Reponse(contenu, code=200))

    assert modeles.telecharger(modele).read_bytes() == contenu


def test_un_contenu_faux_ne_devient_jamais_le_modele(monkeypatch):
    """Le fichier definitif n'apparait qu'une fois verifie : l'application
    doit pouvoir s'y fier sans le relire a chaque demarrage."""
    modele = _modele(b"ce qui etait attendu")
    monkeypatch.setattr("requests.get",
                        lambda *a, **k: _Reponse(b"tout autre chose......"))

    with pytest.raises(modeles.ErreurTelechargement):
        modeles.telecharger(modele)

    assert not (modeles.dossier() / modele.fichier).exists()


def test_l_abandon_conserve_ce_qui_est_deja_recu(monkeypatch):
    """L'utilisateur ferme la fenetre : le telechargement suivant doit
    reprendre, pas recommencer."""
    # Trois blocs : l'abandon se decide entre deux ecritures, et il
    # faut donc qu'il y en ait plusieurs.
    contenu = b"z" * (3 * modeles.BLOC)
    modele = _modele(contenu)
    monkeypatch.setattr("requests.get", lambda *a, **k: _Reponse(contenu))
    recus = []

    with pytest.raises(modeles.ErreurTelechargement):
        modeles.telecharger(modele,
                            progression=lambda r, _t: recus.append(r),
                            arret=lambda: len(recus) >= 1)

    partiel = modeles.dossier() / (modele.fichier + modeles.EN_COURS)
    assert partiel.exists() and partiel.stat().st_size > 0


def test_le_descriptif_du_modele_est_traduit():
    """Il est insere dans une phrase traduite : un texte francais fige y
    donnait « chosen for this machine — qualite maximale »."""
    from murmur import langue as module_langue

    for modele in (modeles.AVEC_CARTE, modeles.SANS_CARTE):
        formes = module_langue.TEXTES.get(modele.resume)
        assert formes is not None, f"{modele.resume} n'est pas une cle connue"
        assert set(formes) >= {"fr", "en"}
        assert formes["fr"] != formes["en"]


def test_une_seule_racine_tk_dans_le_processus():
    """Deux racines Tk font planter la seconde, sans une ligne de journal.

    Mesure : le telechargement reussissait, l'application demarrait, puis
    disparaissait avec le code 0x80000003. La fenetre de premier lancement
    creait sa propre racine et la detruisait ; celle de l'application, creee
    ensuite, tombait dessus.

    La racine est donc creee une fois dans `main` et pretee aux deux.
    """
    import inspect

    from murmur import lancement, premier_lancement

    for fabrique in (premier_lancement.Accueil.__init__,
                     premier_lancement.assurer_le_modele):
        parametres = inspect.signature(fabrique).parameters
        assert "racine" in parametres, \
            f"{fabrique.__qualname__} doit recevoir la racine, pas la creer"

    source = inspect.getsource(premier_lancement)
    assert "tk.Tk()" not in source, \
        "la fenetre de premier lancement ne doit pas creer de racine"

    assert "racine" in inspect.signature(lancement.Murmur.__init__).parameters

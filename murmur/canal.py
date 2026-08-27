"""Canal de commande entre le tableau de bord et l'application.

Le tableau de bord vit dans son **propre processus** : Tk et le moteur web
veulent tous deux le fil principal, et les processus de WebView2 pesent plus
lourd que le reste de l'application reunie — quinze processus et 374 Mo de
memoire privee, mesures fenetre ouverte. Les lancer a la demande, puis les
laisser mourir avec la fenetre, ramene Murmur au repos a son empreinte
d'origine.

Restait a relier les deux. Le tableau lit la base directement — SQLite accepte
plusieurs lecteurs — mais quand il **modifie** quelque chose, l'application
doit le savoir : un terme ajoute au dictionnaire change le prompt du moteur,
un raccourci modifie doit etre repris a l'instant.

Le canal reprend la prise deja ouverte par le verrou d'instance. Elle ecoute
depuis toujours sans jamais rien accepter ; lui faire porter les commandes
evite un second port, et garantit que le canal existe exactement quand
l'application tourne — ni avant, ni apres.

Le protocole tient en une ligne de JSON par echange : la demande, la reponse.
Rien de plus n'est necessaire entre deux processus qui se parlent sur la
boucle locale.
"""

from __future__ import annotations

import json
import socket
import threading

from . import journal

_log = journal.obtenir("canal")

#: Au-dela, la demande est jugee malformee et la connexion fermee. Le canal
#: n'echange que des ordres courts ; une trame plus longue signale une erreur,
#: pas un usage legitime.
TAILLE_MAX = 8192

#: Une commande qui n'arrive pas en deux secondes n'arrivera pas. Ce delai
#: couvre le TRAITEMENT : l'application peut etre occupee a transcrire.
DELAI = 2.0

#: Delai pour ETABLIR la connexion, qui est une tout autre question.
#:
#: A l'autre bout il y a un processus local : soit il ecoute et repond en
#: quelques millisecondes — six, mesurees —, soit il n'existe pas. Rien entre
#: les deux. Or frapper a une porte fermee sur la boucle locale n'est pas
#: refuse ici mais **expire** : les paquets sont avales, sans doute par le
#: pare-feu. Chaque ouverture du tableau de bord commencait donc par deux
#: secondes d'attente pour constater une absence.
#:
#: Se tromper ne coute rien : l'application conclut que le tableau n'est pas
#: la et en lance un, qui trouve le verrou pris et transmet la demande.
DELAI_CONNEXION = 0.25


class Serveur:
    """Ecoute les commandes du tableau de bord, sur la prise du verrou.

    Le fil est demon : il ne doit jamais retenir l'application a l'arret. Une
    connexion en cours au moment de la fermeture est perdue, ce qui est sans
    consequence — le tableau reessaiera ou n'existera plus.
    """

    def __init__(self, prise: socket.socket, rappels: dict):
        self._prise = prise
        self._rappels = rappels
        self._fil: threading.Thread | None = None
        self._arret = threading.Event()

    def demarrer(self) -> None:
        if self._fil is not None:
            return
        self._fil = threading.Thread(target=self._boucler, name="canal",
                                     daemon=True)
        self._fil.start()

    def arreter(self) -> None:
        self._arret.set()
        # La prise appartient au verrou d'instance : c'est lui qui la ferme,
        # et sa fermeture debloque l'`accept` en cours.

    def _boucler(self) -> None:
        while not self._arret.is_set():
            try:
                connexion, _adresse = self._prise.accept()
            except OSError:
                return          # prise fermee : l'application s'arrete
            with connexion:
                try:
                    self._servir(connexion)
                except Exception:
                    _log.exception("commande non traitee")

    def _servir(self, connexion: socket.socket) -> None:
        connexion.settimeout(DELAI)
        brut = connexion.recv(TAILLE_MAX).decode("utf-8", "replace").strip()
        if not brut:
            return

        try:
            demande = json.loads(brut)
            nom = demande["commande"]
        except (ValueError, KeyError, TypeError):
            _log.warning("commande illisible : %.80s", brut)
            connexion.sendall(b'{"ok": false, "erreur": "illisible"}\n')
            return

        rappel = self._rappels.get(nom)
        if rappel is None:
            _log.warning("commande inconnue : %s", nom)
            connexion.sendall(b'{"ok": false, "erreur": "inconnue"}\n')
            return

        # Le rappel s'execute sur le fil du canal : c'est a l'application de
        # renvoyer vers son fil principal ce qui touche a ses fenetres.
        resultat = rappel(demande.get("arguments") or {})
        reponse = {"ok": True, "resultat": resultat}
        connexion.sendall((json.dumps(reponse) + "\n").encode("utf-8"))


def envoyer(commande: str, arguments: dict | None = None,
            port: int | None = None) -> dict:
    """Envoie une commande a l'application. Renvoie sa reponse.

    Un echec n'est pas une erreur fatale : l'application peut avoir ete
    fermee pendant que le tableau de bord restait ouvert. On le signale sans
    interrompre ce que l'utilisateur etait en train de faire.
    """
    from . import systeme

    port = systeme.PORT_VERROU if port is None else port
    trame = json.dumps({"commande": commande,
                        "arguments": arguments or {}}) + "\n"
    try:
        with socket.create_connection(("127.0.0.1", port),
                                      timeout=DELAI_CONNEXION) as prise:
            # La connexion etablie, on redonne au dialogue le temps qu'il
            # merite : c'est la reponse qu'on attend maintenant, pas une
            # presence.
            prise.settimeout(DELAI)
            prise.sendall(trame.encode("utf-8"))
            reponse = prise.recv(TAILLE_MAX).decode("utf-8", "replace")
        return json.loads(reponse) if reponse.strip() else {"ok": False}
    except (OSError, ValueError) as exc:
        _log.debug("commande « %s » non delivree : %s", commande, exc)
        return {"ok": False, "erreur": str(exc)}

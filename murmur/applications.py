"""Noms lisibles et pictogrammes pour les applications ou l'on dicte.

La base retient le nom du programme tel que Windows le donne : `msedge.exe`,
`powerpnt.exe`, `devenv.exe`. Affiches tels quels, ces noms disent surtout que
personne ne les a regardes — et l'extension `.exe` n'apprend rien a personne.

Le pictogramme dit l'usage plutot que le programme : on retient plus vite
« du navigateur » que « brave.exe ». Les programmes inconnus tombent sur un
symbole neutre, jamais sur une case vide qui ferait sauter l'alignement.

Les pictogrammes sont traces par `icones`, au trait et d'une seule couleur.
Des emoji en couleur ont ete essayes d'abord : ils demandaient un rendu par
Pillow — Tk dessine par GDI, qui aplatit les polices en couleur — et surtout
ils juraient a cote d'une interface qui ne compte aucune autre couleur.
"""

from __future__ import annotations

#: Programmes dont le nom de fichier ne ressemble pas a leur nom d'usage.
NOMS = {
    "msedge": "Edge",
    "chrome": "Chrome",
    "brave": "Brave",
    "firefox": "Firefox",
    "code": "VS Code",
    "devenv": "Visual Studio",
    "idea64": "IntelliJ",
    "pycharm64": "PyCharm",
    "explorer": "Explorer",
    "winword": "Word",
    "excel": "Excel",
    "powerpnt": "PowerPoint",
    "outlook": "Outlook",
    "wt": "Terminal",
    "windowsterminal": "Terminal",
    "powershell": "PowerShell",
    "cmd": "Command Prompt",
    "notepad": "Notepad",
    "notepad++": "Notepad++",
    "vlc": "VLC",
    "olk": "Outlook",
}

#: Usage par programme, du plus specifique au plus general. L'ordre compte :
#: « code » apparait dans « vscode » comme dans « qtcreator ».
#:
#: Chaque famille designe un pictogramme de `icones`, trace au trait et d'une
#: seule couleur. Les emoji en couleur, essayes d'abord, juraient a cote d'une
#: interface qui n'en compte aucune.
USAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("app_ia", ("claude", "chatgpt", "copilot", "perplexity", "gemini",
                "cursor", "windsurf")),
    ("app_code", ("code", "devenv", "idea", "pycharm", "webstorm", "sublime",
                  "notepad++", "rider", "clion", "goland", "android studio")),
    ("app_terminal", ("wt", "windowsterminal", "powershell", "cmd", "conhost",
                      "alacritty", "wezterm")),
    ("app_message", ("discord", "slack", "teams", "telegram", "whatsapp",
                     "signal", "messenger")),
    ("app_courriel", ("outlook", "thunderbird", "mailbird", "olk")),
    ("app_document", ("winword", "excel", "powerpnt", "onenote", "notion",
                      "obsidian", "acrobat", "libreoffice", "wps")),
    ("app_navigateur", ("chrome", "brave", "firefox", "msedge", "opera",
                        "vivaldi", "arc", "safari", "zen")),
    ("app_note", ("notepad", "typora", "logseq", "joplin")),
    ("app_dossier", ("explorer",)),
    ("app_media", ("spotify", "vlc", "musicbee", "foobar")),
    ("app_jeu", ("steam", "epicgameslauncher", "battle.net")),
)

#: Programme inconnu, ou dictee anterieure a l'enregistrement de la cible.
NEUTRE = "app_autre"


def _racine(executable: str) -> str:
    """« C:/x/Brave.exe » vers « brave ». Insensible a la casse et au chemin."""
    nom = executable.strip().replace("\\", "/").rsplit("/", 1)[-1]
    if nom.lower().endswith(".exe"):
        nom = nom[:-4]
    return nom.lower()


#: Repli quand la cible n'a pas ete relevee. Seul texte de ce module qui se
#: traduise : les noms de programmes s'ecrivent pareil dans toutes les langues.
AUTRE = {"fr": "Autre", "en": "Other"}


def nom(executable: str, langue: str = "en") -> str:
    """Nom d'usage du programme, sans extension.

    Un programme inconnu garde son nom de fichier, capitalise : mieux vaut
    « Obsidian » approximatif que « inconnu », qui perdrait l'information.
    """
    if not executable or executable == "inconnue":
        return AUTRE.get(langue, AUTRE["en"])

    racine = _racine(executable)
    if racine in NOMS:
        return NOMS[racine]
    return racine[:1].upper() + racine[1:]


def pictogramme(executable: str) -> str:
    """Nom du trace d'usage. Jamais vide : une case manquante desalignerait."""
    if not executable or executable == "inconnue":
        return NEUTRE

    racine = _racine(executable)
    for nom_trace, marqueurs in USAGES:
        if any(marqueur in racine for marqueur in marqueurs):
            return nom_trace
    return NEUTRE

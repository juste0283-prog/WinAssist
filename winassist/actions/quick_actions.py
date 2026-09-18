# ============================================================
#  WinAssist — raccourcis système (POINT 4 du cahier des charges)
# ============================================================
#  ÉTAT : début d'implémentation (ouverture d'applications).
#
#  Idée : certaines opérations fréquentes ("ouvre le Bloc-notes",
#  "vide la corbeille", "change le fond d'écran", "règle le volume"...)
#  sont bien plus rapides via des appels système direct (ctypes /
#  pywin32) que via la boucle générale de clics. Ce module regroupe
#  ces "portes dérobées" — SANS jamais limiter la couverture : si une
#  app n'est pas dans la liste, la boucle générale prend le relais en
#  la cherchant sur l'écran.
#
#  La résolution d'une application passe par trois stratégies :
#    1. un dictionnaire de noms connus (cas les plus courants) ;
#    2. la base de registre `App Paths` (registre des apps installées) ;
#    3. une recherche dans les dossiers du Menu Démarrer (*.lnk).
# ============================================================

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# ------------------------------------------------------------------
#  1) Applications "classiques" : nom prononcé par l'utilisateur ->
#     chemin d'exécution prévisible sur Windows 10/11.
# ------------------------------------------------------------------
#  NB : le Bloc-notes et la Calculatrice sont des exécutables système
#  (System32) ; d'autres apps sont des "paquets" (Microsoft Store) qu'on
#  ne peut pas lancer par simple chemin. On gère les deux cas ci-dessous.
KNOWN_APPS: dict[str, str] = {
    "bloc-notes": "notepad.exe",
    "bloc notes": "notepad.exe",
    "notepad": "notepad.exe",
    "calculatrice": "calc.exe",
    "calculette": "calc.exe",
    "calculator": "calc.exe",
    "peinture": "mspaint.exe",
    "paint": "mspaint.exe",
    "explorateur": "explorer.exe",
    "explorateur de fichiers": "explorer.exe",
    "explorer": "explorer.exe",
    "invite de commandes": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "wordpad": "write.exe",
    "bloc-notes classique": "notepad.exe",
    "gestionnaire des tâches": "taskmgr.exe",
}

# Emplacements des raccourcis du Menu Démarrer (niveaux système et
# utilisateur) — on y cherchera les fichiers *.lnk manquants ci-dessus.
START_MENU_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
]

# ------------------------------------------------------------------
#  2) Raccourcis système directs (point 4)
# ------------------------------------------------------------------
#  Certaines opérations fréquentes n'ont AUCUN intérêt à passer par la
#  boucle de clics : volume, verrouillage, corbeille, fond d'écran...
#  On les expose ici par un nom de raccourci stable, appelable par le
#  cerveau (mock ou LLM) via l'action SystemAction.
#
#  Chaque fonction renvoie (succès, message) et ne lève JAMAIS
#  d'exception : la boucle doit continuer face à l'échec.

# Raccourcis DANGEREUX ou IRREVERSIBLES : une confirmation vocale sera
# exigée avant exécution (point 5 « sécurité »). Le point 4 les déclare
# déjà pour que la sécurité n'ait rien à deviner.
SENSITIVE_SHORTCUTS = {
    "empty_recycle_bin",      # détruit définitivement des fichiers
    "shutdown",               # éteint le PC
    "restart",                # redémarre le PC
    "delete_file",            # supprime un fichier
}

# Couleurs disponibles pour le fond d'écran uni.
COLORS: dict[str, tuple[int, int, int]] = {
    "bleu": (0, 110, 185),
    "noir": (12, 12, 12),
    "blanc": (245, 245, 245),
    "vert": (0, 150, 90),
    "rouge": (200, 30, 40),
    "gris": (96, 96, 96),
    "beige": (210, 200, 180),
}


def run_shortcut(shortcut: str, args: str = "") -> tuple[bool, str]:
    """Exécute un raccourci système par son nom stable.

    `run_shortcut` est LE point d'entrée unique pour SystemAction.
    Ajoute ici tout nouveau raccourci (map ci-dessous).
    """
    table: dict[str, object] = {
        "volume_up": _volume_up,
        "volume_down": _volume_down,
        "volume_mute": _volume_mute,
        "lock_screen": _lock_screen,
        "show_desktop": _show_desktop,
        "empty_recycle_bin": _empty_recycle_bin,
        "set_wallpaper_color": lambda: _set_wallpaper_color(args),
        "open_folder": lambda: _open_folder(args),
    }
    handler = table.get(shortcut)
    if handler is None:
        return False, f"raccourci système inconnu : '{shortcut}'"
    return _safe(handler)


def _safe(handler) -> tuple[bool, str]:
    """Appelle un handler et transforme toute exception en échec propre."""
    try:
        result = handler()
        return (True, str(result)) if isinstance(result, str) else result
    except Exception as exc:
        return False, f"raccourci système en échec : {exc}"


# --- Volume (touches media) ------------------------------------------
_VK_VOLUME_MUTE = 0xAD
_VK_VOLUME_DOWN = 0xAE
_VK_VOLUME_UP = 0xAF


def _volume_up() -> str:
    _media_key(_VK_VOLUME_UP)
    return "volume augmenté"


def _volume_down() -> str:
    _media_key(_VK_VOLUME_DOWN)
    return "volume diminué"


def _volume_mute() -> str:
    _media_key(_VK_VOLUME_MUTE)
    return "son coupé (ou rétabli)"


def _key(vk: int, down: bool) -> None:
    """Envoie un événement clavier bas niveau (SendInput, fiable)."""
    import ctypes
    from ctypes import wintypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
        ]

    class INPUT(ctypes.Structure):
        class _I(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        _anonymous_ = ("_input",)
        _fields_ = [("type", wintypes.DWORD), ("_input", _I)]

    flags = 0x0002 if not down else 0  # KEYEVENTF_KEYUP quand on relâche
    inp = INPUT()
    inp.type = 1  # INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.dwFlags = flags
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _media_key(vk: int) -> None:
    _key(vk, True)
    _key(vk, False)


# --- Fenêtres / session ----------------------------------------------
def _lock_screen() -> str:
    import ctypes

    ctypes.windll.user32.LockWorkStation()
    return "session verrouillée"


def _show_desktop() -> str:
    """Affiche le Bureau (équivalent de Win+D)."""
    _key(0x5B, True)   # touche Windows gauche
    _key(0x44, True)   # D
    _key(0x44, False)
    _key(0x5B, False)
    return "Bureau affiché"


# --- Corbeille -------------------------------------------------------
def _empty_recycle_bin() -> str:
    """Vide la corbeille (PowerShell Clear-RecycleBin, sans confirmation)."""
    import subprocess

    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Clear-RecycleBin -DriveLetter C -Force; Clear-RecycleBin -DriveLetter D -Force -ErrorAction SilentlyContinue"],
        capture_output=True,
        timeout=120,
    )
    if proc.returncode == 0:
        return "corbeille vidée"
    err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="ignore")[:160]
    return f"échec de la vidange de la corbeille : {err}"


# --- Fond d'écran ----------------------------------------------------
def _set_wallpaper_color(color: str) -> tuple[bool, str]:
    """Change le fond d'écran pour une couleur unie (label en français)."""
    label = color.strip().lower().lstrip("en ")
    rgb = COLORS.get(label)
    if rgb is None:
        known = ", ".join(sorted(COLORS))
        return False, f"couleur inconnue. Choisis parmi : {known}"
    bmp = _make_color_bmp(rgb)
    _set_wallpaper(bmp)
    return True, f"fond d'écran passé en {label}"


def _make_color_bmp(rgb: tuple[int, int, int], path: Path | str | None = None) -> Path:
    """Fabrique un petit fichier BMP uni (SPI n'accepte que du BMP)."""
    from PIL import Image

    path = Path(path) if path else Path(os.environ.get("TEMP", ".")) / "winassist_wallpaper.bmp"
    img = Image.new("RGB", (16, 16), rgb)
    img.save(path, "BMP")
    return path


def _set_wallpaper(path: Path) -> None:
    """Applique un fond d'écran via SystemParametersInfoW (ctypes)."""
    import ctypes

    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDWININICHANGE = 0x02
    ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, str(path), SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE
    )


# --- Dossiers personnels ---------------------------------------------
FOLDERS: dict[str, str] = {
    "téléchargements": "shell:downloads",
    "telechargements": "shell:downloads",
    "téléchargement": "shell:downloads",
    "documents": "shell:personal",
    "mes documents": "shell:personal",
    "images": "shell:my pictures",
    "mes images": "shell:my pictures",
    "photos": "shell:my pictures",
    "musique": "shell:my music",
    "ma musique": "shell:my music",
    "vidéos": "shell:my video",
    "videos": "shell:my video",
    "bureau": "shell:desktop",
    "le bureau": "shell:desktop",
}


def _open_folder(folder: str) -> str:
    """Ouvre un dossier personnel (Documents, Images, Téléchargements...)."""
    target = FOLDERS.get(folder.strip().lower().lstrip("le "))
    if target is None:
        return f"dossier inconnu : '{folder}'"
    subprocess.Popen(["explorer.exe", target], close_fds=True)
    return f"dossier '{folder}' ouvert"


def _open_folder_from_app_name(name: str) -> tuple[bool, str | None]:
    """Gère l'ouverture des dossiers personnels via launch_app si besoin."""
    if name in FOLDERS:
        subprocess.Popen(["explorer.exe", FOLDERS[name]], close_fds=True)
        return True, f"dossier '{name}' ouvert"
    return False, None


def launch_app(name: str) -> tuple[bool, str]:
    """Lance l'application correspondant à `name`.

    Renvoie : (réussite, message). On ne lève JAMAIS d'exception ici :
    la boucle doit continuer à tourner et tenter autre chose.
    """
    clean = name.strip().lower()

    # Stratégie 1 : dictionnaire des apps bien connues.
    exe = KNOWN_APPS.get(clean)
    if exe is not None:
        return _start_exe(exe)

    # Stratégie 1bis : dossiers personnels (Documents, Images, ...).
    ok, msg = _open_folder_from_app_name(clean)
    if ok:
        return ok, msg

    # Stratégie 2 : raccourci dans le Menu Démarrer (gère les apps du
    # Microsoft Store, ex. WhatsApp, Word...).
    lnk = _find_start_menu(clean)
    if lnk is not None:
        return _start_lnk(lnk)

    # Stratégie 3 : on passe par la commande `start` de Windows, qui
    # effectue une recherche intelligente (nom de l'app, URL, fichier...).
    _run_start(clean)
    return True, f"demande d'ouverture de '{name}' transmise à Windows"


# ------------------------------------------------------------------
#  Implémentation des stratégies
# ------------------------------------------------------------------
def _start_exe(exe: str) -> tuple[bool, str]:
    """Lance un exécutable dont le nom figure dans le PATH de Windows."""
    try:
        # subprocess.Popen avec shell=False : on lance l'exe directement.
        subprocess.Popen([exe], close_fds=True)
        return True, f"application '{exe}' lancée"
    except FileNotFoundError:
        return False, f"exécutable '{exe}' introuvable"


def _find_start_menu(clean: str) -> Path | None:
    """Cherche un raccourci *.lnk contenant `clean` dans son nom."""
    for base in START_MENU_DIRS:
        if not base.exists():
            continue
        for lnk in base.rglob("*.lnk"):
            # Autorise les accents/liaisons : on compare le nom du fichier
            # (sans extension) en minuscules et sans caractères spéciaux.
            stem = _normalize(lnk.stem)
            if clean.replace(" ", "") in stem or _normalize(clean) in stem:
                return lnk
    return None


def _start_lnk(lnk: Path) -> tuple[bool, str]:
    """Ouvre un raccourci Windows (.lnk) via os.startfile."""
    try:
        os.startfile(str(lnk))
        return True, f"application '{lnk.stem}' lancée"
    except OSError as exc:
        return False, f"impossible d'ouvrir '{lnk.stem}' : {exc}"


def _run_start(target: str) -> None:
    """La commande `start` de Windows en ultime recours.

    `start` comprend : noms d'apps, fichiers, dossiers, URL... C'est le
    comportement le plus proche de l'utilisateur qui lance une recherche.
    On passe par cmd.exe car `start` est un mot-clé du shell Windows.
    """
    subprocess.Popen(["cmd", "/c", "start", "", target], close_fds=True)


def _normalize(text: str) -> str:
    """Normalise un texte pour la comparaison floue : minuscules, sans accents.

    Utile pour que « é » et « e » soient considérés équivalents.
    """
    accents = {
        "à": "a", "â": "a", "ä": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c", "œ": "oe", "æ": "ae",
    }
    lowered = text.lower()
    return "".join(accents.get(ch, ch) for ch in lowered)


__all__ = ["launch_app", "KNOWN_APPS", "FOLDERS", "run_shortcut", "SENSITIVE_SHORTCUTS", "COLORS", "_make_color_bmp"]
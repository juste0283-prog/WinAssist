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


__all__ = ["launch_app", "KNOWN_APPS"]
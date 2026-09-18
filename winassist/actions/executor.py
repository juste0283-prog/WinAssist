# ============================================================
#  WinAssist — exécution physique des actions
# ============================================================
#  Traduit les objets Action (modèles) en effets réels sur la
#  machine : mouvements de souris, frappe clavier, etc.
#
#  Choix d'implémentation :
#   - pyautogui pour les actions "souris/clavier" (simple, multiplateforme,
#     avec failsafe anticatastrophe : souris dans un coin d'écran = stop).
#   - presse-papiers (pyperclip) + Ctrl+V pour la SAIE DE TEXTE :
#     pyautogui.write() ne gère pas correctement les caractères non-ASCII
#     (les accents français !) ; la technique du collage est universelle.
#
#  IMPORTANT (sécurité) : le failsafe de pyautogui est activé par défaut.
#  On peut le désactiver via WINASSIST_FAILSAFE=0, déconseillé.
# ============================================================

from __future__ import annotations

import ctypes
import time

import pyautogui
import pyperclip

from winassist.config import get_config
from winassist.core.models import (
    Action,
    Click,
    DoubleClick,
    Drag,
    OpenApp,
    PressEnter,
    PressKeys,
    RightClick,
    Scroll,
    TypeText,
)

# Fonctions Win32 conservées pour les futures touches spéciales
# (point 4) — utilisées via ctypes si nécessaire.
_user32 = ctypes.windll.user32


class ActionExecutor:
    """Exécute un objet Action et renvoie (réussite, feedback)."""

    def __init__(self) -> None:
        config = get_config()
        # Activation/désactivation du failsafe (déplacement souris dans
        # le coin en haut à gauche de l'écran = arrêt d'urgence).
        pyautogui.FAILSAFE = config.pyautogui_failsafe
        # Petite pause après chaque appel pyautogui : laisse à Windows
        # le temps d'anticiper les mouvements.
        pyautogui.PAUSE = 0.1

    # ------------------------------------------------------------------
    #  Point d'entrée : dispatch selon le type d'action
    # ------------------------------------------------------------------
    def execute(self, action: Action) -> tuple[bool, str]:
        """Exécute l'action. Renvoie (succès, message de feedback)."""
        kind = action.type

        if kind == "click":
            return self._click(action.x, action.y)
        if kind == "double_click":
            return self._double_click(action.x, action.y)
        if kind == "right_click":
            return self._right_click(action.x, action.y)
        if kind == "type_text":
            return self._type_text(action.text)
        if kind == "press_keys":
            return self._press_keys(action.keys)
        if kind == "press_enter":
            return self._press_enter()
        if kind == "scroll":
            return self._scroll(action.direction)
        if kind == "drag":
            return self._drag(action.x1, action.y1, action.x2, action.y2)
        if kind == "open_app":
            return open_app_resolver(action.app_name)

        return False, f"Action inconnue : {kind}"

    # ------------------------------------------------------------------
    #  Souris
    # ------------------------------------------------------------------
    def _click(self, x: int, y: int) -> tuple[bool, str]:
        pyautogui.click(x, y)
        return True, ""

    def _double_click(self, x: int, y: int) -> tuple[bool, str]:
        pyautogui.doubleClick(x, y)
        return True, "double-clic effectué"

    def _right_click(self, x: int, y: int) -> tuple[bool, str]:
        pyautogui.rightClick(x, y)
        return True, "clic droit effectué"

    def _drag(self, x1: int, y1: int, x2: int, y2: int) -> tuple[bool, str]:
        pyautogui.moveTo(x1, y1)
        time.sleep(0.2)
        pyautogui.drag(x2 - x1, y2 - y1, duration=0.5, button="left")
        return True, "glisser-déposer effectué"

    def _scroll(self, direction: str) -> tuple[bool, str]:
        # pyautogui.scroll(coef) : coef > 0 = vers le haut, < 0 vers le bas.
        step = 3
        if direction == "up":
            pyautogui.scroll(step)
        elif direction == "down":
            pyautogui.scroll(-step)
        elif direction == "left":
            pyautogui.hscroll(-step)
        elif direction == "right":
            pyautogui.hscroll(step)
        return True, f"défilement {direction}"

    # ------------------------------------------------------------------
    #  Clavier
    # ------------------------------------------------------------------
    def _press_keys(self, keys: list[str]) -> tuple[bool, str]:
        # pyautogui.hotkey appuie sur toutes les touches "en même temps"
        # dans l'ordre : hotkey("ctrl", "s") = Ctrl+S.
        pyautogui.hotkey(*[k.lower() for k in keys])
        return True, "raccourci clavier envoyé"

    def _press_enter(self) -> tuple[bool, str]:
        pyautogui.press("enter")
        return True, "Entrée envoyée"

    def _type_text(self, text: str) -> tuple[bool, str]:
        # Technique du collage pour supporter tous les accents.
        # ON SAUVEGARDE le presse-papiers AVANT et on le restaure APRÈS
        # pour ne pas perturber l'utilisateur.
        previous = None
        try:
            previous = pyperclip.paste()  # peut échouer si pas de texte
        except Exception:
            previous = None

        pyperclip.copy(text)
        # Coller (Ctrl+V) dans le champ qui a le focus.
        pyautogui.hotkey("ctrl", "v")

        if previous is not None:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass
        return True, f"texte saisi ({len(text)} caractères)"


# ------------------------------------------------------------------
#  Raccourcis système / ouverture d'application (début du point 4)
# ------------------------------------------------------------------
def open_app_resolver(app_name: str) -> tuple[bool, str]:
    """Essaie d'ouvrir une application par son nom (retour pour l'executor).

    Priorité de résolution :
      1. dictionnaire des applications Windows "classiques" ;
      2. recherche dans les dossiers du Menu Démarrer (raccourcis .lnk) ;
      3. échec propre (on n'essaie jamais de deviner des chemins).
    """
    from winassist.actions.quick_actions import launch_app

    success, message = launch_app(app_name)
    return success, message


__all__ = ["ActionExecutor"]
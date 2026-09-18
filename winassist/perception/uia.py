# ============================================================
#  WinAssist — perception de l'écran via UI Automation (UIA)
# ============================================================
#  UIA est la brique "officielle" d'accessibilité de Windows :
#  elle expose une arborescence d'éléments (boutons, champs de
#  texte, menus...) avec leur position, leur type et leur libellé
#  accessible. C'est LE point de départ pour voir l'écran sans
#  capture d'image : les coordonnées sont déjà structurées.
#
#  Quand l'arbre UIA est vide ou insuffisant (jeux, canvas, vieilles
#  apps), on basculera vers le repli VISION (analyse d'image par un
#  modèle multimodal) — c'est le point 3 du cahier des charges.
#  L'interface `PerceptionProvider` de core/loop.py est prévue pour
#  qu'on puisse brancher ce repli sans toucher à la boucle.
#
#  Note multi-écran : les coordonnées UIA et pyautogui s'expriment
#  en pixels, origine = coin haut-gauche de l'écran PRINCIPAL.
#  En mono-écran (le cas le plus courant), tout concorde.
# ============================================================

from __future__ import annotations

import ctypes
from typing import Optional

from pywinauto import Desktop
from pywinauto.uia_element_info import UIAElementInfo

from winassist.config import Config, get_config
from winassist.core.models import IGNORED_TYPES, INTERACTIVE_TYPES, ScreenState, UIElement

# On récupère les fonctions Win32 nécessaires pour lire la fenêtre au
# premier plan (celle que voit l'utilisateur et sur laquelle on agit).
_user32 = ctypes.windll.user32

# Types de contrôle "porteurs de texte" qui valent la peine d'être vus
# même s'ils ne sont pas manipulables : ils décrivent le contenu.
INFORMATIVE_TYPES = {"Text", "Document", "Image", "Menu", "ToolTip"}


def _foreground_hwnd() -> int:
    """Renvoie le handle (hwnd) de la fenêtre active."""
    return _user32.GetForegroundWindow()


class UIA_Perception:
    """Capture l'écran en extrayant l'arbre UIA de la fenêtre active."""

    def __init__(self, config: Optional[Config] = None):
        # On garde une référence au Desktop pour ne le recréer qu'une fois.
        self.config = config or get_config()
        self._desktop = Desktop(backend="uia")

    # ------------------------------------------------------------------
    #  Méthode principale, appelée par la boucle à chaque itération
    # ------------------------------------------------------------------
    def capture(self) -> ScreenState:
        """Construit un ScreenState à partir de la fenêtre au premier plan."""
        hwnd = _foreground_hwnd()
        window_text = _window_text(hwnd)
        elements = self._extract_elements(hwnd)
        return ScreenState(foreground_window=window_text, elements=elements)

    # ------------------------------------------------------------------
    #  Extraction : descendre dans l'arbre et filtrer ce qui est utile
    # ------------------------------------------------------------------
    def _extract_elements(self, hwnd: int) -> list[UIElement]:
        """Extrait tous les éléments pertinents de la fenêtre `hwnd`.

        Stratégie pour garder le contexte compact et exploitable :
          1. On ne garde que les éléments AYANT un nom ou de type
             manipulable (un bouton sans nom ne sert à rien).
          2. On ignore les types purement décoratifs (Panes, Groupes...).
          3. On trie par position écran (haut -> bas, gauche -> droite).
          4. On limite la taille (element_limit) pour ne pas noyer l'IA.
        """
        spec = self._desktop.window(handle=hwnd)
        try:
            descendants = spec.descendants()
        except Exception:
            # Fenêtre fermée entre-temps ou arbre inaccessible :
            # on renvoie une vue vide plutôt que de faire échouer la boucle.
            return []

        raw: list[tuple[float, float, UIAElementInfo]] = []
        for wrapper in descendants:
            info = wrapper.element_info
            if not self._kept(info):
                continue
            rect = info.rectangle
            raw.append((rect.top, rect.left, info))

        # Tri "lecture naturelle" : par position verticale puis horizontale.
        raw.sort(key=lambda t: (t[0], t[1]))

        elements: list[UIElement] = []
        for idx, (_, _, info) in enumerate(raw):
            if idx >= self.config.element_limit:
                break
            el = _to_uielement(idx, info)
            if el.is_visible:  # on élimine les éléments hors-écran ou vides
                elements.append(el)
        return elements

    # ------------------------------------------------------------------
    #  Filtres : quels éléments garder ?
    # ------------------------------------------------------------------
    def _kept(self, info: UIAElementInfo) -> bool:
        """Décide si un élément vaut la peine d'être envoyé à l'agent."""
        control_type = getattr(info, "control_type", "") or ""
        name = (info.name or "").strip()

        if control_type in IGNORED_TYPES:
            return False  # décoratif : inutile pour l'agent

        # On garde tout élément manipulable (même sans nom : un champ
        # vide est parfois le champ à remplir).
        if control_type in INTERACTIVE_TYPES:
            return True

        # Pour le reste, seuls les éléments nommés apportent du contexte.
        return bool(name) and control_type in INFORMATIVE_TYPES


# ------------------------------------------------------------------
#  Conversion UIA -> modèle interne
# ------------------------------------------------------------------
def _to_uielement(id_: int, info: UIAElementInfo) -> UIElement:
    rect = info.rectangle
    return UIElement(
        id=id_,
        control_type=(getattr(info, "control_type", "") or "Unknown"),
        name=(info.name or "").strip(),
        automation_id=str(getattr(info, "automation_id", "") or "") or None,
        x=rect.left,
        y=rect.top,
        w=max(0, rect.right - rect.left),
        h=max(0, rect.bottom - rect.top),
        enabled=_is_enabled(info),
    )


def _is_enabled(info: UIAElementInfo) -> bool:
    """L'élément est-il interactif ? On lit la propriété UIA `IsEnabled`."""
    try:
        return bool(info.is_enabled) if hasattr(info, "is_enabled") else True
    except Exception:
        return True  # en cas de doute, on le laisse cliquable


def _window_text(hwnd: int) -> str:
    """Lit le titre de la fenêtre (boucle jusqu'à 260 caractères max)."""
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return "(fenêtre sans titre)"
    buffer = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value or "(fenêtre sans titre)"


# Compatibilité : même fonction que le Provider Protocol, utilisée par
# la boucle. On crée un alias `UIA_Perception.capture` déjà présent.
__all__ = ["UIA_Perception"]
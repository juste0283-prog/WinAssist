# ============================================================
#  WinAssist — repli VISION pour la perception de l'écran
# ============================================================
#  Quand l'arbre UIA est vide ou insuffisant (jeux, canvas, vieilles
#  apps, éléments sans nom accessible), on ne peut plus "voir" via
#  les structures. On bascule alors sur l'analyse d'IMAGE :
#   1. capture d'écran (mss, rapide) ;
#   2. un modèle multimodal (OpenAI-compatible) décrit les éléments
#      interactifs sous forme de JSON structuré, comme UIA ;
#   3. on reconstruit un ScreenState identique à celui de UIA,
#      donc utilisable tel quel par la boucle agentique.
#
#  La prose naturelle de la vue est aussi utilisée par la voix pour
#  décrire l'écran aux personnes aveugles (« il y a une barre de
#  recherche en haut... »).
# ============================================================

from __future__ import annotations

import base64
import io
import json
import re
from typing import Optional, Protocol

from winassist.config import Config, get_config
from winassist.core.models import INTERACTIVE_TYPES, ScreenState, UIElement

# Système d'exploitation multi-écran : mss capture TOUTE la virtuale.
# On limite la précision initiale aux rectangles écran — UIA filtre déjà.
_MSS = None


def capture_screen(config: Optional[Config] = None) -> bytes:
    """Capture l'écran principal et renvoie une image PNG compressée.

    Renvoie des octets PNG. Redimensionne / re-encode au besoin pour
    tenir sous config.vision_max_bytes (les modèles limitent la taille
    d'entrée et le coût).
    """
    config = config or get_config()
    global _MSS
    try:
        if _MSS is None:
            import mss

            _MSS = mss.mss()
        monitor = _MSS.monitors[1]  # écran principal
        raw = _MSS.grab(monitor)
        import numpy as np

        img_bytes = _encode(np.array(raw), config.vision_max_bytes)
        return img_bytes
    except Exception:
        # Repli Pillow si mss est indisponible.
        from PIL import ImageGrab

        img = ImageGrab.grab()
        return _encode_pillow(img, config.vision_max_bytes)


def _encode(arr, max_bytes: int) -> bytes:
    """Compresse un numpy array (BGRA) en PNG sous `max_bytes` octets."""
    from PIL import Image

    img = Image.fromarray(arr[:, :, :3][:, :, ::-1], mode="RGB")  # BGR->RGB
    return _encode_pillow(img, max_bytes)


def _encode_pillow(img, max_bytes: int) -> bytes:
    """Compresse une image PIL en PNG, en réduisant la taille au besoin."""
    from PIL import Image

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    # Trop gros ? on réduit progressivement jusqu'à tenir (ou min 400px).
    scale = 0.9
    while len(data) > max_bytes and min(img.size) > 400:
        w, h = img.size
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
    return data


# ------------------------------------------------------------------
#  Fournisseur multimodal (OpenAI-compatible), injectable pour les tests
# ------------------------------------------------------------------
class VisionProvider(Protocol):
    """Qui répond à une question « par l'image » et renvoie du texte."""

    def ask(self, prompt: str, image_bytes: bytes) -> str:
        ...


class OpenAIVisionProvider:
    """Appelle un modèle multimodal compatible OpenAI avec l'image encodée.

    L'image est passée en data-URL base64 (aucun fichier temporaire).
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        if not self.config.api_key:
            raise RuntimeError(
                "Vision indisponible : aucune cle API. "
                "Renseigne WINASSIST_API_KEY (ou un serveur OpenAI compatible)."
            )
        from openai import OpenAI

        self._client = OpenAI(api_key=self.config.api_key or None, base_url=self.config.api_base_url or None)
        self.model = self.config.vision_model or self.config.model

    def ask(self, prompt: str, image_bytes: bytes) -> str:
        data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        try:
            resp = self._client.chat.completions.create(model=self.model, messages=messages, temperature=0.0)
        except Exception as exc:
            raise RuntimeError(f"Vision refuse l'appel (modèle non multimodal ?) : {exc}") from exc
        return (resp.choices[0].message.content or "").strip()


# ------------------------------------------------------------------
#  Prompts (en français : le modèle doit répondre en français)
# ------------------------------------------------------------------
_ELEMENTS_PROMPT = """Tu analyses une capture d'écran de Windows.
Décris les éléments INTERACTIFS (boutons, champs de texte, menus, listes, onglets, cases à cocher...) que l'on voit à l'écran.
Réponds UNIQUEMENT par un tableau JSON, sans autre texte, de la forme :
[{"control_type": "Button|Edit|List|CheckBox|TabItem|ComboBox|Unknown", "name": "libellé visible", "x": entier, "y": entier, "w": entier, "h": entier}]
- x,y = coin haut-gauche de l'élément, w,h = sa largeur/hauteur, en pixels sur l'image.
- En plus des éléments interactifs, ajoute les TITRES/TEXTES importants avec control_type "Text".
- bornes pour les nombres : écris des entiers positifs, max 10 éléments essentiels.
- Si l'écran est vide ou illisible, renvoie []."""

_DESCRIBE_PROMPT = """Tu analyses une capture d'écran de Windows pour une personne aveugle.
Décris EN FRANÇAIS, en 3 à 6 phrases claires, ce qu'il y a à l'écran :
le nom de la fenêtre, la zone principale, les boutons/champs importants et
leur position approximative (en haut, à gauche, au centre...)."""


# ------------------------------------------------------------------
#  Perception vision : même contrat que UIA_Perception
# ------------------------------------------------------------------
class VisionUnavailable(Exception):
    """Vision impossible (pas de clé, modèle non multimodal, image illisible)."""


class VisionPerception:
    """Perception par analyse d'image : remplace la vue UIA quand nécessaire."""

    def __init__(self, config: Optional[Config] = None, provider: Optional[VisionProvider] = None):
        self.config = config or get_config()
        # Provider créé PAresseusement : aucune clé API n'est requise tant
        # que la vision n'est pas réellement sollicitée (mode mock de démo).
        self.provider = provider
        self._client_provider = None

    # ------------------------------------------------------------------
    #  Méthode principale, même signature que UIA_Perception.capture
    # ------------------------------------------------------------------
    def capture(self) -> ScreenState:
        """Capture l'écran, le fait décrire et renvoie des éléments structurés."""
        image = capture_screen(self.config)
        elements = parse_elements(self._ask_elements(image), self.config.element_limit)
        return ScreenState(foreground_window="(vision : analyse d'image)", elements=elements)

    # ------------------------------------------------------------------
    #  Description en prose pour la voix (personnes aveugles)
    # ------------------------------------------------------------------
    def describe(self) -> str:
        """Décrit l'écran en langage naturel (français), pour le TTS."""
        image = capture_screen(self.config)
        if self.provider is None:
            if self._client_provider is None:
                self._client_provider = OpenAIVisionProvider(self.config)
            self.provider = self._client_provider
        text = self.provider.ask(_DESCRIBE_PROMPT, image).strip()
        return text or "(écran indescriptible)"

    # ------------------------------------------------------------------
    def _ask_elements(self, image: bytes) -> str:
        if self.provider is None:
            if self._client_provider is None:
                self._client_provider = OpenAIVisionProvider(self.config)
            self.provider = self._client_provider
        try:
            return self.provider.ask(_ELEMENTS_PROMPT, image)
        except RuntimeError:
            raise
        except Exception as exc:  # erreurs réseau, JSON, etc.
            raise VisionUnavailable(str(exc)) from exc


# ------------------------------------------------------------------
#  Parser du JSON renvoyé par le modèle
# ------------------------------------------------------------------
def parse_elements(raw: str, limit: int = 80) -> list[UIElement]:
    """Transforme la réponse du modèle en liste d'éléments fiables.

    Tolérant : retire les blocs de code, ignore les champs inconnus,
    déduplique, borne les coordonnées, tronque à `limit`.
    """
    if not raw or not raw.strip():
        return []
    text = raw.strip()
    # On ne garde que le contenu entre [ ] éventuellement entouré de ```json
    m = re.search(r"(\[[\s\S]*\])", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    seen: set[tuple] = set()
    elements: list[UIElement] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        try:
            x, y, w, h = (int(item.get(k) or 0) for k in ("x", "y", "w", "h"))
        except (TypeError, ValueError):
            continue
        w = max(1, w)
        h = max(1, h)
        key = (x, y, w, h, name)
        if key in seen:
            continue  # double détection par le modèle : on garde un seul
        seen.add(key)
        ctype = str(item.get("control_type") or "Unknown").strip()
        ctype = ctype if ctype in INTERACTIVE_TYPES | {"Text"} else "Unknown"
        elements.append(
            UIElement(
                id=i,
                control_type=ctype,
                name=name,
                automation_id=None,
                x=x,
                y=y,
                w=w,
                h=h,
                enabled=True,
            )
        )
        if len(elements) >= limit:
            break
    return elements


# ------------------------------------------------------------------
#  Perception hybride : UIA d'abord, vision en secours
# ------------------------------------------------------------------
class HybridPerception:
    """Utilise UIA ; bascule sur la vision quand UIA n'apporte rien.

    Règle : si le nombre d'éléments interactifs NOMÉS détectés par UIA
    est inférieur à `vision_min_named_elements`, on considère que la vue
    UIA est aveugle et on tente le repli vision. En cas d'échec de la
    vision (pas de clé, modèle non multimodal), on garde la vue UIA.
    """

    def __init__(self, uia, vision: Optional[VisionPerception] = None, config: Optional[Config] = None, verbose: bool = True):
        self.config = config or get_config()
        self.uia = uia
        self.vision = vision
        self.verbose = verbose
        self.last_used: str = "uia"

    def capture(self) -> ScreenState:
        state = self.uia.capture()
        self.last_used = "uia"
        if self._sufficient(state):
            return state
        if not self.config.vision_enabled or self.vision is None:
            return state
        try:
            if self.verbose:
                print("[perception] Vue UIA insuffisante : repli vision d'image.")
            self.last_used = "vision"
            return self.vision.capture()
        except Exception:
            # La vision a échoué (pas de clé, modèle non multimodal) :
            # on ne fait pas échouer la boucle, on garde la vue UIA.
            self.last_used = "uia"
            return state

    def describe_for_voice(self) -> str:
        """Description naturelle de l'écran pour la voix."""
        if self.config.vision_enabled and self.vision is not None:
            try:
                return self.vision.describe()
            except Exception:
                pass
        # Sans vision : on décrit avec ce que UIA voit.
        state = self.uia.capture()
        lines = [f"Fenêtre {state.foreground_window}. "]
        for el in state.elements[:10]:
            if el.name:
                lines.append(f"{el.control_type} {el.name}.")
        return " ".join(lines) or "(écran vide)"

    # ------------------------------------------------------------------
    def _sufficient(self, state: ScreenState) -> bool:
        named = [
            e
            for e in state.elements
            if e.control_type in INTERACTIVE_TYPES and e.name and e.enabled
        ]
        return len(named) >= self.config.vision_min_named_elements


__all__ = [
    "VisionPerception",
    "HybridPerception",
    "OpenAIVisionProvider",
    "VisionUnavailable",
    "capture_screen",
    "parse_elements",
]
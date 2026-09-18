"""Paquet `core` : les éléments transverses du système (modèles, boucle, historique)."""

from winassist.core.loop import AgenticLoop, RunResult
from winassist.core.models import ScreenState, UIElement

__all__ = ["AgenticLoop", "RunResult", "ScreenState", "UIElement"]
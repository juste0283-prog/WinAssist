"""Paquet `perception` : comment l'assistant "voit" l'écran.

- uia.py    : extraction de l'arbre UI Automation (implémenté).
- vision.py : repli vision par capture d'écran + modèle multimodal
              (point 3 du cahier des charges) : utilisé quand UIA
              ne voit aucun élément interactif nommé.
"""

from winassist.perception.uia import UIA_Perception
from winassist.perception.vision import HybridPerception, VisionPerception

__all__ = ["UIA_Perception", "VisionPerception", "HybridPerception"]
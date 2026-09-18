"""Paquet `perception` : comment l'assistant "voit" l'écran.

- uia.py             : extraction de l'arbre UI Automation (implémenté).
- vision_perception  : repli vision par capture + modèle multimodal,
                       prévu pour le point 3 du cahier des charges.
"""

from winassist.perception.uia import UIA_Perception

__all__ = ["UIA_Perception"]
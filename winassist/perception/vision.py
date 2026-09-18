# ============================================================
#  WinAssist — repli VISION (POINT 3 du cahier des charges)
# ============================================================
#  ÉTAT : non implémenté pour l'instant (prototype = UIA seul).
#
#  Objectif : quand l'arbre UIA est vide, incomplet ou trompeur
#  (applications graphiques, jeux, canvas HTML, vieilles apps Win32
#  mal accessibles), l'assistant devra :
#    1. capture une image de l'écran (Pillow / mss) ;
#    2. envoyer cette image à un modèle multimodal (vision) avec un
#       résumé de la tâche ;
#    3. en recevoir soit des coordonnées x/y d'action, soit une
#       description texte du contenu (pour le retour vocal).
#
#  L'interface `PerceptionProvider` de core/loop.py permet de brancher
#  ce module plus tard SANS modifier la boucle : un PerceptionProvider
#  composé choisira UIA ou vision selon la richesse de l'arbre.
# ============================================================

from __future__ import annotations

from typing import Any


class VisionPerception:
    """Placeholder : sera le repli vision (point 3)."""

    def capture(self) -> Any:
        raise NotImplementedError(
            "Le repli vision n'est pas encore implémenté (point 3 du développement)."
        )
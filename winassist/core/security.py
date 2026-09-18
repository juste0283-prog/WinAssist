# ============================================================
#  WinAssist — garde-fous de sécurité (POINT 5 du cahier des charges)
# ============================================================
#  Tout n'est pas innocent : vider la corbeille, éteindre le PC,
#  supprimer un fichier... sont IRRÉVERSIBLES. Avant d'exécuter une
#  telle action, la boucle demande une CONFIRMATION à l'utilisateur.
#
#  Règle par défaut (défensive) : sans aucun "confirmer" branché, une
#  action sensible n'est JAMAIS exécutée — elle est refusée et
#  journalisée. On préfère bloquer tout, plutôt que de risquer la
#  moindre perte pour un utilisateur à handicap.
# ============================================================

from __future__ import annotations

from typing import Optional, Protocol

from winassist.actions.quick_actions import SENSITIVE_SHORTCUTS
from winassist.core.models import Action

# Libellés compréhensibles par l'utilisateur (et lus par la synthèse
# vocale) pour chaque raccourci sensible.
SENSITIVE_DESCRIPTIONS: dict[str, str] = {
    "empty_recycle_bin": "vider la corbeille. Les fichiers seront supprimés définitivement",
    "shutdown": "éteindre complètement le PC",
    "restart": "redémarrer le PC",
    "delete_file": "supprimer un fichier définitivement",
}


class ConfirmationProvider(Protocol):
    """Qui demande à l'utilisateur d'accepter (ou non) une action sensible.

    Implémenté côté console (input) et côté voix (TTS + micro). La boucle
    n'exécute l'action que si `confirm` renvoie True.
    """

    def confirm(self, description: str) -> bool:
        ...


def sensitive_description(action: Action) -> Optional[str]:
    """Renvoie la description de danger si l'action est SENSIBLE, sinon None.

    Seules les actions DESTRUCTRICES ou IRRÉVERSIBLES sont concernées ;
    les actions ordinaires (clic, texte, volume...) passent sans contrôle.
    """
    if action.type == "system" and action.shortcut in SENSITIVE_SHORTCUTS:
        return SENSITIVE_DESCRIPTIONS.get(action.shortcut, f"l'action sensible « {action.shortcut} »")
    return None


__all__ = ["sensitive_description", "ConfirmationProvider", "SENSITIVE_SHORTCUTS"]
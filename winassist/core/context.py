# ============================================================
#  WinAssist — contexte d'une itération de décision
# ============================================================
#  Petit module volontairement "pauvre" : il ne contient QUE
#  DecisionContext, afin d'éviter tout import circulaire.
#
#  Qui importe quoi (dépendances) :
#     core.models  <- core.history  <- core.context
#                                                  ^
#     core.loop    <- core.context -----------------+
#     core.loop   (n'importe PLUS decision : plus de cycle)
#     decision.*  <- core.context (pour recevoir le contexte)
#
#  Contrat : {commande utilisateur, écran actuel, historique}
#  -> renvoyé par la boucle au moteur de décision à chaque itération.
# ============================================================

from __future__ import annotations

from dataclasses import dataclass

from winassist.core.history import ActionHistory
from winassist.core.models import ScreenState


@dataclass
class DecisionContext:
    """Tout ce dont le cerveau a besoin pour choisir la prochaine action."""

    command: str                 # la demande de l'utilisateur
    state: ScreenState           # l'écran tel qu'on vient de le voir
    history: ActionHistory       # les actions déjà tentées (ne pas répéter)
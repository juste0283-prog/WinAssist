# ============================================================
#  WinAssist — interfaces du moteur de décision
# ============================================================
#  Le moteur de décision est le cerveau de la boucle : il reçoit
#  {commande utilisateur, état courant de l'écran, historique} et
#  renvoie UNE action unique (ou "done" / "ask").
#
#  Deux implémentations (voir mock.py et llm_client.py) :
#   - MockDecisionProvider : règles locales, zéro réseau, pour tester
#     la boucle sans clé API. C'est le défaut.
#   - LLMDecisionProvider  : appelle un serveur compatible OpenAI
#     (OpenAI ou Ollama/LM Studio en local) avec function calling.
#
#  L'interface est volontairement minimale : cela permet de brancher
#  n'importe quel futur cerveau (prompt différent, techno différente)
#  sans toucher à la boucle.
# ============================================================

from __future__ import annotations

from winassist.core.context import DecisionContext  # noqa: F401  (réexporté)
from winassist.core.history import ActionHistory
from winassist.core.models import Action, ScreenState


class DecisionProvider:
    """Classe de base abstraite des moteurs de décision."""

    def decide(self, ctx: DecisionContext) -> Action:
        """Renvoie l'action à exécuter (aucune exécution de plan complet).

        Lève en cas d'erreur : la boucle transformera l'exception en échec
        propre (jamais de crash de l'assistant).
        """
        raise NotImplementedError
"""Paquet `decision` : moteurs de décision de la boucle agentique.

- base.py      : interfaces communes (DecisionProvider, DecisionContext).
- mock.py      : cerveau local à règles, SANS réseau (tests + démo).
- compound.py  : enchaînement d'étapes dans une phrase (« ouvre X puis tape Y »).
- llm_client.py: cerveau LLM compatible OpenAI (function calling).
"""

from winassist.config import Config, get_config
from winassist.decision.base import DecisionContext, DecisionProvider
from winassist.decision.compound import CompoundDecisionProvider
from winassist.decision.mock import MockDecisionProvider


def make_decision_provider(config: Config | None = None) -> DecisionProvider:
    """Fabrique le bon moteur de décision selon la configuration.

    Règle de choix :
      - WINASSIST_LLM_MODE=mock  -> CompoundDecisionProvider (mock capable
        d'enchaîner plusieurs étapes : « ouvre X puis tape Y »).
      - WINASSIST_LLM_MODE=openai -> LLMDecisionProvider (clé ou serveur local).
    Si le mode demandé est "openai" mais que la clé est absente et qu'aucun
    serveur local n'est visé, on bascule automatiquement sur le mock avec
    un avertissement — le prototype reste utilisable en toutes circonstances.
    """
    config = config or get_config()
    requested = config.llm_mode

    if requested == "llm" or requested == "openai":
        if not config.api_key and "localhost" not in config.api_base_url:
            # Aucune clé ni serveur local : sécurité de repli.
            print("[decision] Mode 'openai' demandé sans clé : bascule sur le mock local.")
            return CompoundDecisionProvider()
        from winassist.decision.llm_client import LLMDecisionProvider

        return LLMDecisionProvider(config)

    return CompoundDecisionProvider()


__all__ = [
    "DecisionContext",
    "DecisionProvider",
    "MockDecisionProvider",
    "CompoundDecisionProvider",
    "make_decision_provider",
]
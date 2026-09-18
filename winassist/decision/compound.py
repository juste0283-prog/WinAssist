# ============================================================
#  WinAssist — commandes composées multi-étapes (POINT 6)
# ============================================================
#  « Ouvre le bloc-notes puis tape bonjour » = DEUX étapes réelles
#  dans une seule phrase. Le LLM réel gère naturellement ce cas
#  (une action par itération, guidée par l'observation). En mode
#  MOCK (sans clé API), on simule le même raisonnement avec une
#  file de sous-commandes :
#
#      plan[0] -> exécutée -> plan[1] -> exécutée -> Done final
#
#  Chaque étape dispose de SON PROPRE MockDecisionProvider (état
#  d'avancement indépendant), mais partage la perception et
#  l'historique de la boucle. Une commande n'est découpée que si
#  CHAQUE morceau est une commande réellement exécutable : sinon,
#  on laisse le mock simple traiter la phrase entière (« tape
#  bonjour et merci » ne doit PAS être découpé, « et merci »
#  n'est pas une commande).
# ============================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field

from winassist.core.models import Action, Ask, Done
from winassist.decision.base import DecisionContext, DecisionProvider
from winassist.decision.mock import (
    MockDecisionProvider,
    OPEN_VERBS,
    SCROLL_WORDS,
    SYSTEM_RULES,
    TYPE_VERBS,
)

# Séparateurs entre étapes dans une phrase composée.
_SEPARATOR = re.compile(r"\s+(?:puis|ensuite|et ensuite|alors|et)\s+")

# Toutes les familles de commandes reconnues (pour décider si une
# phrase est découpable en étapes exécutables).
_ACTIONABLE = (
    set(OPEN_VERBS)
    | set(TYPE_VERBS)
    | {"valide", "entrée", "enter", "envoie", "clique", "appuie", "touche"}
    | {"fond", "écran", "ecran"}
    | {w for w, _, _ in SYSTEM_RULES}
)


def split_compound(command: str) -> list[str]:
    """Découpe `command` en étapes, ou renvoie [command] entière.

    Ne découpe QUE si chaque morceau est une commande reconnue.
    """
    parts = [p.strip() for p in _SEPARATOR.split(command)]
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return [command]
    if any(not _is_actionable(p) for p in parts):
        return [command]
    return parts


def _is_actionable(fragment: str) -> bool:
    """Un morceau est-il une commande que le mock sait exécuter ?"""
    f = fragment.lower()
    return any(v in f for v in _ACTIONABLE)


@dataclass
class _Plan:
    """Plan d'exécution d'une commande composée."""

    fragments: list[str]
    providers: list[MockDecisionProvider] = field(default_factory=list)
    index: int = 0

    def __post_init__(self) -> None:
        # Chaque étape a SON avancement, pour ne pas se marcher dessus.
        self.providers = [MockDecisionProvider() for _ in self.fragments]


class CompoundDecisionProvider(DecisionProvider):
    """Décideur mock capable d'enchaîner les étapes d'une phrase.

    - commande simple  -> délégué au MockDecisionProvider habituel ;
    - commande composée -> séquence d'étapes, une action à la fois.
    """

    def __init__(self) -> None:
        self._simple = MockDecisionProvider()
        self._plans: dict[str, _Plan | None] = {}  # cmd -> plan (ou None)

    def decide(self, ctx: DecisionContext) -> Action:
        # On construit le plan UNE fois par commande (état persistant).
        if ctx.command not in self._plans:
            fragments = split_compound(ctx.command)
            self._plans[ctx.command] = _Plan(fragments) if len(fragments) > 1 else None

        plan = self._plans[ctx.command]
        if plan is None:
            return self._simple.decide(ctx)

        # On avance d'étape en étape tant que les précédentes sont "fini".
        while plan.index < len(plan.fragments):
            provider = plan.providers[plan.index]
            fragment_ctx = DecisionContext(
                command=plan.fragments[plan.index],
                state=ctx.state,
                history=ctx.history,
            )
            action = provider.decide(fragment_ctx)
            if isinstance(action, Done):
                plan.index += 1
                continue  # étape terminée -> suivante
            if isinstance(action, Ask):
                return action  # on laisse l'utilisateur préciser
            return action  # une action à exécuter par la boucle

        # Toutes les étapes sont exécutées : fin de la tâche.
        return Done(summary="Toutes les étapes demandées sont terminées.")

    def reset(self) -> None:
        """Oublie tous les plans (pratique pour une nouvelle session)."""
        self._plans.clear()


__all__ = ["CompoundDecisionProvider", "split_compound"]
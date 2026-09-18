# ============================================================
#  WinAssist — la boucle agentique (le cœur du prototype)
# ============================================================
#  Boucle perception -> décision -> action -> observation :
#
#    1. Capter l'état de l'écran (ScreenState, via la perception).
#    2. Demander AU MODÈLE une action unique pour progresser.
#    3. Résoudre les références (element_id -> coordonnées écran).
#    4. Exécuter l'action (executor), enregistrer dans l'historique.
#    5. Recapter l'écran et recommencer, jusqu'à :
#         - le modèle répond "done" (tâche réussie) ;
#         - la limite d'itérations est atteinte ;
#         - une boucle bloquée est détectée (écran figé).
#
#  Règles d'or implémentées ici :
#    - JAMAIS d'exécution de plan complet : une action à la fois.
#    - Chaque itération est observée et journalisée.
#    - L'exécution est interrompable (voir le drapeau cancel_requested,
#      relié plus tard à l'interruption vocale, section 6 du cahier).
# ============================================================

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from winassist.core.context import DecisionContext
from winassist.core.history import ActionHistory, untouched_iteration
from winassist.core.models import (
    PROGRESSIVE_ACTIONS,
    Action,
    Done,
    Ask,
    ScreenState,
    describe_action,
)
from winassist.core.security import ConfirmationProvider, sensitive_description

# Un "pipeline" est l'ensemble des composants branchables de la boucle.
# On utilise des interfaces minimales (Protocol) pour pouvoir injecter
# des faux dans les tests unitaires sans toucher à l'écran ni au réseau.
from typing import Protocol


class PerceptionProvider(Protocol):
    """Qui fournit l'état courant de l'écran."""

    def capture(self) -> ScreenState: ...


class DecisionProvider(Protocol):
    """Qui choisit l'action suivante (LLM réel ou mock local)."""

    def decide(self, ctx: DecisionContext) -> Action: ...


class Executor(Protocol):
    """Qui exécute physiquement une action."""

    def execute(self, action: Action) -> tuple[bool, str]:
        """Renvoie (réussite, message de feedback)."""
        ...


# ------------------------------------------------------------------
#  Structure de sortie de la boucle
# ------------------------------------------------------------------
@dataclass
class RunResult:
    """Ce que la boucle renvoie quand elle s'arrête."""

    success: bool                        # True si la tâche est terminée ("done")
    reason: str                          # pourquoi la boucle s'est arrêtée
    iterations: int = 0                  # nombre d'actions exécutées
    history: ActionHistory = field(default_factory=ActionHistory)
    final_state: Optional[ScreenState] = None

    def summary(self) -> str:
        """Courte phrase de restitution (utile pour le TTS)."""
        return f"{'Réussi' if self.success else 'Échec'} après {self.iterations} action(s) : {self.reason}"


class StagnationError(Exception):
    """Levée quand l'agent tourne en rond (écran figé)."""


class MaxIterationsError(Exception):
    """Levée quand la limite d'itérations est atteinte.

    (Déclarée pour la complétude — la boucle renvoie aujourd'hui un
    RunResult plutôt que de lever, ce qui est plus propre pour le
    retour vocal : pas d'exception à attraper dans la couche d'entrée.)
    """


# ------------------------------------------------------------------
#  La boucle elle-même
# ------------------------------------------------------------------
class AgenticLoop:
    """Orchestre l'alternance perception / décision / action.

    Tous les composants sont injectés au constructeur : cela rend la
    boucle testable avec des faux (pas d'écran, pas de réseau) et
    remplaçable composant par composant (mock -> LLM réel -> vision).
    """

    def __init__(
        self,
        perception: PerceptionProvider,
        decider: DecisionProvider,
        executor: Executor,
        *,
        max_iterations: int = 12,
        stagnation_limit: int = 3,
        action_delay: float = 0.4,     # pause après chaque action (laisser l'UI réagir)
        on_event: Optional[Callable[[str], None]] = None,
        confirmer: Optional[ConfirmationProvider] = None,  # point 5
    ):
        self.perception = perception
        self.decider = decider
        self.executor = executor
        self.max_iterations = max_iterations
        self.stagnation_limit = stagnation_limit
        self.action_delay = action_delay
        # Rappel pour streamer les événements vers la console / la voix.
        self.on_event = on_event or (lambda msg: None)
        # Confirmation des actions sensibles (point 5) : si absent,
        # toute action sensible est REFUSÉE d'office (règle défensive).
        self.confirmer = confirmer
        # Drapeau d'interruption : posé par un thread externe (voix,
        # clavier) pour arrêter la boucle entre deux actions.
        self.cancel_requested = False
        self.cancel_reason = "Interruption demandée par l'utilisateur."

    def cancel(self, reason: str = "Interruption demandée par l'utilisateur.") -> None:
        """Demande l'arrêt de la boucle (thread-safe, appelable d'ailleurs)."""
        self.cancel_requested = True
        self.cancel_reason = reason

    # -- petit utilitaire interne de journalisation -------------
    def _log(self, msg: str) -> None:
        self.on_event(msg)

    def run(self, user_command: str) -> RunResult:
        """Exécute la commande utilisateur et renvoie le résultat."""
        self._log(f"Commande reçue : \"{user_command}\"")
        history = ActionHistory()

        # -- itération 0 : état initial (avant toute action) ---------
        try:
            state = self.perception.capture()
        except Exception as exc:  # la perception peut échouer (pas de fenêtre...)
            return RunResult(False, f"Perception impossible : {exc}", history=history)
        self._log(f"État initial : {len(state.elements)} élément(s).")

        previous_action: Optional[Action] = None

        # Arrêt demandé avant même de commencer ?
        if self.cancel_requested:
            return RunResult(False, self.cancel_reason, history=history, final_state=state)

        for i in range(1, self.max_iterations + 1):
            # -- interruption : on vérifie le drapeau à CHAQUE itération --
            if self.cancel_requested:
                self._log(f"Interruption demandée : {self.cancel_reason}")
                return RunResult(False, self.cancel_reason,
                                 iterations=i - 1, history=history, final_state=state)

            # -- (a) DÉCISION ----------------------------------------
            try:
                action = self.decider.decide(DecisionContext(user_command, state, history))
            except Exception as exc:
                self._log(f"Erreur de décision : {exc}")
                return RunResult(False, f"Le moteur de décision a échoué : {exc}",
                                 iterations=i - 1, history=history, final_state=state)

            # -- (b) FIN DE TÂCHE : le modèle déclare avoir terminé ---
            if isinstance(action, Done):
                self._log(f"L'agent estime la tâche terminée : {action.summary}")
                return RunResult(True, action.summary or "tâche terminée",
                                 iterations=i - 1, history=history, final_state=state)

            # -- (b') CLARIFICATION : le modèle a besoin de l'humain --
            if isinstance(action, Ask):
                self._log(f"L'agent demande : {action.question}")
                return RunResult(False, f"Clarification demandée : {action.question}",
                                 iterations=i - 1, history=history, final_state=state)

            # -- blocage anticipé : action strictement répétée --------
            if untouched_iteration(action, previous_action):
                self._log("Action identique à la précédente : arrêt anti-boucle.")
                return RunResult(False, "L'agent répète la même action sans progresser.",
                                 iterations=i - 1, history=history, final_state=state)

            # -- (c) RÉSOLUTION : element_id -> coordonnées écran -----
            before_sig = state.signature()
            try:
                resolved = self._resolve(action, state)
            except Exception as exc:
                self._log(f"Résolution impossible : {exc}")
                history.record(i, action, before_sig, before_sig, ok=False, error=str(exc))
                return RunResult(False, str(exc), iterations=i, history=history, final_state=state)

            # -- (d) CONFIRMATION DES ACTIONS SENSIBLES (point 5) ---------
            #  Avant toute exécution : si l'action est dangereuse (corbeille,
            #  extinction, suppression...), on exige l'accord explicite de
            #  l'utilisateur. Sans confirmer, on REFUSE — jamais d'exécution
            #  silencieuse d'une action irréversible.
            warning = sensitive_description(resolved)
            if warning is not None:
                confirmer = self.confirmer
                # Accepte objet à .confirm(desc) OU simple callable(desc).
                ask = confirmer.confirm if confirmer is not None and hasattr(confirmer, "confirm") else confirmer
                allowed = ask(warning) if ask is not None else False
                if not allowed:
                    refusal = (
                        "Action sensible refusée : aucune confirmation disponible."
                        if self.confirmer is None else
                        f"Action sensible refusée par l'utilisateur."
                    )
                    self._log(f"  -> {refusal} : {describe_action(resolved)}")
                    history.record(i, resolved, before_sig, before_sig, ok=False, error=refusal)
                    # Un refus arrête la tâche : déclarer "réussi" juste
                    # après serait mensonger pour l'utilisateur.
                    return RunResult(False, refusal,
                                     iterations=i, history=history, final_state=state)
                self._log(f"  -> Confirmé par l'utilisateur : {warning}")

            # -- (d') EXÉCUTION ----------------------------------------
            self._log(f"[{i}] {describe_action(resolved)}")
            try:
                ok, feedback = self.executor.execute(resolved)
            except Exception as exc:
                ok, feedback = False, str(exc)
            if not ok:
                self._log(f"  -> Échec : {feedback}")
            else:
                self._log(f"  -> {feedback or 'exécuté'}")

            # -- (e) OBSERVATION : re-capturer l'écran ----------------
            time.sleep(self.action_delay)
            try:
                next_state = self.perception.capture()
            except Exception as exc:
                next_state = state  # si la capture échoue, on conserve le dernier état

            history.record(i, resolved, before_sig, next_state.signature(), ok=ok, error=feedback if not ok else "")

            # -- (f) VÉRIFICATIONS ANTIBLOCAGE --------------------------
            if history.is_stalled(self.stagnation_limit):
                self._log(f"Aucun changement d'écran après {self.stagnation_limit} actions.")
                return RunResult(False, "L'écran ne change plus : boucle bloquée.",
                                 iterations=i, history=history, final_state=next_state)

            state = next_state
            previous_action = action

        # -- (g) LIMITE D'ITÉRATIONS ------------------------------------
        self._log(f"Limite de {self.max_iterations} itérations atteinte.")
        return RunResult(False, f"Limite de {self.max_iterations} itérations atteinte sans terminer la tâche.",
                         iterations=self.max_iterations, history=history, final_state=state)

    # -- résolution des coordonnées ------------------------------------
    @staticmethod
    def _resolve(action: Action, state: ScreenState) -> Action:
        """Traduit les `element_id` en coordonnées écran concrètes.

        Le modèle préfère dire « clique sur l'élément #12 » (plus fiable
        que de deviner des pixels). C'est la boucle qui fait la traduction
        à partir de l'état courant — une seule source de vérité.
        """
        if action.type not in PROGRESSIVE_ACTIONS:
            return action  # type_text, press_keys... n'ont pas besoin de résolution

        target = None
        if hasattr(action, "element_id") and action.element_id is not None:
            for el in state.elements:
                if el.id == action.element_id:
                    target = el
                    break
            if target is None:
                raise ValueError(
                    f"L'élément #{action.element_id} n'existe plus dans l'écran courant."
                )
            # On copie l'action avec les coordonnées du centre de l'élément.
            cx, cy = target.center
            action = action.model_copy(update={"x": cx, "y": cy, "element_id": None})

        # Un clic SANS élément et SANS coordonnées est une erreur de l'agent.
        if hasattr(action, "x") and action.x is None:
            kind = action.type
            raise ValueError(
                f"Action '{kind}' sans élément ni coordonnées : l'agent doit"
                " cibler un element_id de l'écran courant."
            )
        return action
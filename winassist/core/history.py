# ============================================================
#  WinAssist — historique des actions et détection de blocage
# ============================================================
#  L'historique sert à deux choses :
#   1. Donner le contexte au modèle (il doit connaître les actions déjà
#      tentées pour ne pas refaire la même chose indéfiniment).
#   2. Détecter les boucles bloquées : si l'écran ne change plus après
#      plusieurs actions, le plan est probablement mauvais — on arrête.
#
#  Point 1 : faire un journal "listenable" de toutes les actions est
#  prévu (sécurité, section 6 du cahier des charges). On pose ici la
#  structure, le module de retour vocal viendra lire ce journal.
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field

from winassist.core.models import Action, describe_action


@dataclass
class HistoryEntry:
    """Une ligne du journal : une action tentée + son résultat."""

    iteration: int          # numéro d'itération de la boucle
    description: str        # texte lisible de l'action (pour le journal vocal)
    screen_before: str      # empreinte de l'écran avant l'action
    screen_after: str       # empreinte de l'écran après l'action
    ok: bool = True         # l'exécution a-t-elle réussi (pas d'exception) ?
    error: str = ""         # message d'erreur si échec

    def changed_anything(self) -> bool:
        """Vrai si l'écran a changé suite à l'action."""
        return self.screen_before != self.screen_after

    def to_llm_line(self) -> str:
        """Représentation d'une ligne pour le prompt du modèle."""
        verdict = "ok" if self.ok else f"ERREUR: {self.error}"
        state = "écran inchangé" if self.changed_anything() else "écran CHANGÉ"
        return f"[{self.iteration}] {self.description} -> {verdict} ({state})"


@dataclass
class ActionHistory:
    """Le journal complet de la session, + la logique anti-blocage."""

    entries: list[HistoryEntry] = field(default_factory=list)

    # ------------------------------------------------------------------
    #  Ajout d'entrées
    # ------------------------------------------------------------------
    def record(
        self,
        iteration: int,
        action: Action | None,
        screen_before: str,
        screen_after: str,
        ok: bool = True,
        error: str = "",
    ) -> None:
        """Enregistre une action exécutée (avec son impact sur l'écran)."""
        self.entries.append(
            HistoryEntry(
                iteration=iteration,
                description=describe_action(action) if action else "—",
                screen_before=screen_before,
                screen_after=screen_after,
                ok=ok,
                error=error,
            )
        )

    def last(self, n: int = 5) -> list[HistoryEntry]:
        """Les `n` dernières entrées, à injecter dans le contexte du modèle."""
        return self.entries[-n:]

    def to_llm_context(self, n: int = 5) -> str:
        """Bloc texte lisible résumé de l'historique, pour le prompt."""
        if not self.entries:
            return "(aucune action effectuée pour l'instant)"
        return "\n".join(e.to_llm_line() for e in self.last(n))

    # ------------------------------------------------------------------
    #  Détection de blocage (anti-boucle infinie)
    # ------------------------------------------------------------------
    def is_stalled(self, limit: int) -> bool:
        """L'agent tourne-t-il en rond ?

        On considère que l'on est bloqué dès que les `limit` dernières
        actions successives n'ont produit AUCUN changement visible de
        l'écran. Le seuil est configurable (config.stagnation_limit).
        """
        recent = self.entries[-limit:]
        if len(recent) < limit:
            return False  # pas encore assez de recul pour juger
        return all(not e.changed_anything() for e in recent)

    # ------------------------------------------------------------------
    #  Journal à destination de l'utilisateur
    # ------------------------------------------------------------------
    def human_readable(self) -> str:
        """Le journal complet, tel qu'on le lirait à voix haute."""
        if not self.entries:
            return "Aucune action effectuée."
        lines = []
        for e in self.entries:
            state = "progression" if e.changed_anything() else "aucun changement"
            status = "réussi" if e.ok else f"échec ({e.error})"
            lines.append(f"{e.iteration}. {e.description} — {status}, {state}")
        return "\n".join(lines)


# ------------------------------------------------------------------
#  Détection des actions répétées à l'identique
# ------------------------------------------------------------------
def untouched_iteration(action: Action, previous: Action | None) -> bool:
    """Vrai si `action` est identique à la précédente.

    Si l'agent redemande plusieurs fois le même clic au même endroit
    sans que l'écran change, inutile d'insister : on coupe.
    """
    if previous is None:
        return False
    return action.model_dump(exclude_none=True) == previous.model_dump(exclude_none=True)
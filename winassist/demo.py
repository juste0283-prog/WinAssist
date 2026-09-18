# ============================================================
#  WinAssist — démo console du prototype (POINT 1)
# ============================================================
#  Lancement :
#      python -m winassist.demo
#  ou avec une commande directe :
#      python -m winassist.demo "ouvre le bloc-notes"
#
#  Ce script assemble les 4 briques (perception / décision / action /
#  retour) et affiche en temps réel ce que fait l'agent. Le retour vocal
#  est activé si WINASSIST_TTS=1 (défaut).
#
#  Astuces pour tester sans risque :
#      ouvre le bloc-notes
#      tape bonjour
#      clique sur le bouton <libellé>    (le bloc-notes en a peu)
#      valide
#      écran                              (affiche la perception brute)
#      quitter / exit / quit
# ============================================================

from __future__ import annotations

import sys

from winassist.config import get_config
from winassist.core.journal import Journal
from winassist.core.loop import AgenticLoop, RunResult
from winassist.decision import make_decision_provider
from winassist.perception import HybridPerception, VisionPerception, UIA_Perception
from winassist.actions import ActionExecutor

QUIT_COMMANDS = {"quitter", "exit", "quit", "stop", "arrête"}


def make_console_confirmer(tts):
    """Confirmation console pour les actions sensibles (point 5).

    La question est posée à l'écran ET à voix haute ; uniquement une
    réponse positive explicite laisse passer l'action. Sinon : refus.
    """

    def confirm(description: str) -> bool:
        print(f"\n[CONFIRMATION] {description}")
        if tts:
            tts.speak(f"Attention : {description}. Confirme avec oui, ou annule avec non.")
        try:
            reply = input("  Confirmer ? (oui/non) > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return reply in {"o", "oui", "y", "yes", "ok", "confirme", "valide", "go"}

    return confirm


def build_session():
    """Assemble la session complète et renvoie (loop, tts)."""
    config = get_config()

    # Banque de perception : UIA d'abord, repli vision si UIA est aveugle.
    perception = HybridPerception(
        uia=UIA_Perception(config),
        vision=VisionPerception(config) if config.vision_enabled else None,
        config=config,
    )
    # Cerveau : mock (défaut) ou LLM réel selon WINASSIST_LLM_MODE.
    decider = make_decision_provider(config)
    # Mains : exécution souris/clavier + raccourcis système.
    executor = ActionExecutor()

    loop = AgenticLoop(
        perception=perception,
        decider=decider,
        executor=executor,
        max_iterations=config.max_iterations,
        stagnation_limit=config.stagnation_limit,
    )
    return loop, config


def run_command(loop: AgenticLoop, config, command: str, tts) -> RunResult:
    """Exécute une commande texte à travers la boucle complète."""
    events: list[str] = []
    journal: Journal = getattr(loop, "_journal", None)

    def on_event(msg: str) -> None:
        events.append(msg)
        print(f"  {msg}")
        if journal:
            journal.record("etape", msg)
        if tts and config.enable_tts:
            tts.speak(msg)  # chaque étape est annoncée à voix haute

    # On remplace le gestionnaire d'événements de la boucle.
    loop.on_event = on_event
    if journal:
        journal.record("commande", command)
    result = loop.run(command)

    # Restitution finale (à voix haute et à l'écran).
    print(f"\n>>> RESULTAT : {result.summary()}")
    if journal:
        journal.record("resultat", result.summary())
    if tts and config.enable_tts:
        tts.speak(result.summary())

    # Affiche une description de l'écran final : utile pour un
    # utilisateur qui ne voit pas l'écran (le TTS suivra dans l'étape 2).
    if result.final_state:
        print(result.final_state.describe_visible())
    return result


def main() -> None:
    config = get_config()
    loop, _ = build_session()

    # Confirmation des actions sensibles (point 5) : mode console.
    loop.confirmer = make_console_confirmer(None)

    # Journal de session (point 5) : fichier JSONL, réécoutable.
    journal = None
    if config.journal_enabled:
        try:
            journal = Journal(enabled=True)
        except Exception:
            journal = None
    loop._journal = journal  # utilisé par run_command/on_event

    # TTS optionnel (désactivable par WINASSIST_TTS=0).
    tts = None
    if config.enable_tts:
        try:
            from winassist.io import get_tts
            tts = get_tts()
        except Exception:
            tts = None  # pas de voix sur ce poste : on reste en console
    # On rebranche le confirmer avec la voix une fois le TTS prêt.
    loop.confirmer = make_console_confirmer(tts)

    print("=" * 62)
    print("  WinAssist — prototype de la boucle agentique")
    print(f"  Mode décision : {config.llm_mode}   TTS : {'oui' if tts else 'non'}")
    print("  Failsafe : souris dans le coin haut-gauche = STOP")
    print("  Sensible : toute action dangereuse demande confirmation")
    print("=" * 62)

    # Commande passée directement en argument -> un seul passage.
    if len(sys.argv) > 1:
        try:
            run_command(loop, config, " ".join(sys.argv[1:]), tts)
        finally:
            if journal:
                journal.close()
        return

    # Mode interactif (REPL) : on pose une question, on agit, on recommence.
    while True:
        try:
            command = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break
        if not command:
            continue
        if command.lower() in QUIT_COMMANDS:
            print("Au revoir.")
            break
        if command.lower() == "écran":
            state = loop.perception.capture()
            print(state.describe_visible())
            if tts:
                tts.speak(state.describe_visible())
            continue
        if command.lower() == "décris":
            try:
                desc = loop.perception.describe_for_voice()
            except Exception as exc:
                desc = f"Description impossible : {exc}"
            print(desc)
            if tts:
                tts.speak(desc)
            continue
        if command.lower() in ("journal", "lit le journal"):
            if journal and journal.path:
                Journal.replay(journal.path, lambda line: (print(line), tts.speak(line) if tts else None), limit=20)
            else:
                print("Journal désactivé.")
            continue
        run_command(loop, config, command, tts)

    if journal:
        journal.close()


if __name__ == "__main__":
    main()
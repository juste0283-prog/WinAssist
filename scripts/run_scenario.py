# ============================================================
#  WinAssist — exécution de SCÉNARIOS MULTI-ÉTAPES réels (point 6)
# ============================================================
#  Usage :
#      python scripts/run_scenario.py            # liste les scénarios
#      python scripts/run_scenario.py notepad    # joue le scénario
#      python scripts/run_scenario.py notepad,explorateur
#
#  Chaque scénario est une suite de commandes vocales réelles,
#  passées à la boucle agentique COMPLÈTE (perception UIA réelle +
#  décision composée + exécution réelle). Après chaque étape, on
#  vérifie des prédicats simples sur l'état de l'écran et on
#  affiche PASS / FAIL — c'est la démonstration de bout en bout :
#  « ouvre le bloc-notes puis tape bonjour » fonctionne vraiment.
#
#  Aucune action destructive : uniquement des applications innocentes
#  (Bloc-notes, Calculatrice, dossiers, volume, Bureau).
# ============================================================

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

# Rendre winassist importable quand on lance scripts/run_scenario.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from winassist.config import get_config
from winassist.core.loop import AgenticLoop, RunResult
from winassist.decision import make_decision_provider
from winassist.perception import HybridPerception, UIA_Perception, VisionPerception
from winassist.actions import ActionExecutor

# ------------------------------------------------------------------
#  Définition des scénarios (nom -> suite de commandes + vérifications)
# ------------------------------------------------------------------
SCENARIOS: dict[str, dict] = {
    "notepad": {
        "nom": "Bloc-notes : ouverture puis saisie",
        "commandes": [
            "ouvre le bloc-notes et tape bonjour",
        ],
        "verif": [lambda s: _fg(s, "bloc")],
    },
    "calculatrice": {
        "nom": "Calculatrice : ouverture",
        "commandes": ["ouvre la calculatrice"],
        "verif": [lambda s: _fg(s, "calcul")],
    },
    "explorateur": {
        "nom": "Documents : dossier personnel",
        "commandes": ["ouvre mes documents"],
        "verif": [lambda s: _fg(s, "document")],
    },
    "bureau": {
        "nom": "Volume puis Bureau (raccourcis système)",
        "commandes": ["monte le volume puis affiche le bureau"],
        "verif": [],
    },
}


def _fg(state, word: str) -> bool:
    return word.lower() in (state.foreground_window or "").lower()


def build_session() -> AgenticLoop:
    config = get_config()
    return AgenticLoop(
        perception=HybridPerception(
            uia=UIA_Perception(config),
            vision=VisionPerception(config) if config.vision_enabled else None,
            config=config,
        ),
        decider=make_decision_provider(config),
        executor=ActionExecutor(),
        max_iterations=config.max_iterations,
        stagnation_limit=config.stagnation_limit,
        action_delay=0.5,
    )


def run_scenario(name: str) -> bool:
    scenario = SCENARIOS.get(name)
    if scenario is None:
        print(f"[scenario] Inconnu : {name}")
        return False

    print("=" * 64)
    print(f"[scenario] {scenario['nom']}")
    print("=" * 64)
    all_ok = True
    for command in scenario["commandes"]:
        loop = build_session()
        result: RunResult = loop.run(command)
        print(f"  « {command} » -> {result.summary()}")
        all_ok = all_ok and result.success
        for i, check in enumerate(scenario["verif"], 1):
            state = result.final_state or loop.perception.capture()
            ok = bool(check(state))
            all_ok = all_ok and ok
            print(f"    [{'PASS' if ok else 'FAIL'}] vérification {i}")
    return all_ok


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print("Scénarios disponibles :")
        for name, sc in SCENARIOS.items():
            print(f"  - {name:<14} {sc['nom']}")
        return 0
    ok = all(run_scenario(name) for name in args[0].split(","))
    print("\n[scenario] " + ("TOUS LES SCÉNARIOS ONT RÉUSSI." if ok else "ÉCHEC partiel — voir ci-dessus."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
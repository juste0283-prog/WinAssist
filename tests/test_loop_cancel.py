# ============================================================
#  Tests du mécanisme d'interruption de la boucle agentique
#  (core/loop.py) — compose fakes + un vrai thread.
# ============================================================

import threading
import unittest

from winassist.core.loop import AgenticLoop
from winassist.core.models import Done, ScreenState, TypeText


class InstantPerception:
    def capture(self):
        return ScreenState(foreground_window="F")


class StepDecider:
    """Renvoie une action ; bloque au 2e appel jusqu'à libération."""

    def __init__(self):
        self.reached_step2 = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def decide(self, ctx):
        self.calls += 1
        if self.calls == 2:
            self.reached_step2.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("timeout en attente de libération")
        return TypeText(text=f"étape {self.calls}")


class RecordingExecutor:
    def __init__(self):
        self.executed = []

    def execute(self, action):
        self.executed.append(action)
        return True, ""


class TestLoopCancel(unittest.TestCase):
    def test_cancel_before_run(self):
        loop = AgenticLoop(
            InstantPerception(), StepDecider(), RecordingExecutor(),
            max_iterations=10, action_delay=0,
        )
        loop.cancel("arrêt avant départ")
        result = loop.run("xyz")
        self.assertFalse(result.success)
        self.assertIn("arrêt", result.reason)

    def test_cancel_during_run(self):
        decider = StepDecider()
        executor = RecordingExecutor()
        loop = AgenticLoop(
            InstantPerception(), decider, executor,
            max_iterations=10, action_delay=0,
        )

        worker = threading.Thread(target=lambda: loop.run("xyz"))
        worker.start()

        # On attend que l'agent soit engagé dans la 2e décision.
        self.assertTrue(decider.reached_step2.wait(timeout=5))
        loop.cancel("j'ai changé d'avis")
        decider.release.set()
        worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertTrue(loop.cancel_requested)
        # La boucle s'est arrêtée en peu d'itérations (pas jusqu'à la limite).
        self.assertLessEqual(len(executor.executed), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
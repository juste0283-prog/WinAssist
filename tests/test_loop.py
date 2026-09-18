# ============================================================
#  Tests de la boucle agentique (core/loop.py)
#  On injecte des "faux" composants (pas d'écran, pas de réseau).
# ============================================================

import unittest

from winassist.core.loop import AgenticLoop
from winassist.core.models import (
    Ask,
    Click,
    Done,
    OpenApp,
    ScreenState,
    UIElement,
    TypeText,
)


def make_element(id_: int, name: str, control_type: str = "Button",
                 x: int = 100, y: int = 100, w: int = 50, h: int = 20) -> UIElement:
    return UIElement(id=id_, control_type=control_type, name=name,
                     x=x, y=y, w=w, h=h)


class FakePerception:
    """Simule l'écran : renvoie une suite d'états prédéfinis."""

    def __init__(self, states):
        self.states = list(states)
        self.calls = 0

    def capture(self) -> ScreenState:
        idx = min(self.calls, len(self.states) - 1)
        self.calls += 1
        return self.states[idx]


class ScriptedDecider:
    """Simule le cerveau : renvoie les actions d'un script, les unes après les autres."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.asked = 0

    def decide(self, ctx):
        if self.asked < len(self.actions):
            action = self.actions[self.asked]
            self.asked += 1
            return action
        return Done(summary="fin de script")


class RecordingExecutor:
    """Simule les mains : enregistre ce qu'on lui demande d'exécuter."""

    def __init__(self, ok: bool = True, feedback: str = ""):
        self.executed = []
        self.ok = ok
        self.feedback = feedback

    def execute(self, action):
        self.executed.append(action)
        return self.ok, self.feedback


class TestLoopBasics(unittest.TestCase):
    def test_open_app_then_done(self):
        # Perception : d'abord le bureau (sans éléments) puis la fenêtre du Bloc-notes.
        desk = ScreenState(foreground_window="Bureau")
        note = ScreenState(foreground_window="Bloc-notes")
        perception = FakePerception([desk, note])
        decider = ScriptedDecider([OpenApp(app_name="bloc-notes"), Done(summary="ok")])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)

        result = loop.run("ouvre le bloc-notes")
        self.assertTrue(result.success)
        self.assertEqual(len(executor.executed), 1)
        self.assertEqual(executor.executed[0].type, "open_app")
        self.assertEqual(result.iterations, 1)

    def test_click_resolves_element_to_coordinates(self):
        # Un bouton "Envoyer" à x=100 y=100 w=50 h=20 -> centre (125, 110).
        screen = ScreenState(foreground_window="Messagerie", elements=[
            make_element(3, "Envoyer"),
        ])
        perception = FakePerception([screen])
        decider = ScriptedDecider([Click(element_id=3), Done(summary="ok")])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)

        result = loop.run("clique sur Envoyer")
        self.assertTrue(result.success)
        click = executor.executed[0]
        self.assertEqual((click.x, click.y), (125, 110))

    def test_click_on_unknown_element_is_reported(self):
        screen = ScreenState(foreground_window="F", elements=[])
        perception = FakePerception([screen])
        decider = ScriptedDecider([Click(element_id=99)])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)

        result = loop.run("clique sur X")
        self.assertFalse(result.success)
        self.assertIn("n'existe plus", result.reason)


class TestLoopGuards(unittest.TestCase):
    def test_stagnation_detected(self):
        # Écran figé : l'état ne change JAMAIS.
        frozen = ScreenState(foreground_window="F", elements=[
            make_element(0, "A"), make_element(1, "B"), make_element(2, "C")])
        perception = FakePerception([frozen])
        decider = ScriptedDecider([
            Click(element_id=0), Click(element_id=1), Click(element_id=2),
        ])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor,
                           max_iterations=10, stagnation_limit=3, action_delay=0)

        result = loop.run("fais le tour")
        self.assertFalse(result.success)
        self.assertIn("ne change plus", result.reason)

    def test_repeated_identical_action_aborts(self):
        frozen = ScreenState(foreground_window="F", elements=[make_element(0, "A")])
        perception = FakePerception([frozen])
        decider = ScriptedDecider([Click(element_id=0), Click(element_id=0)])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)

        result = loop.run("clique")
        self.assertFalse(result.success)
        self.assertIn("répète la même action", result.reason)
        # La première occurrence a bien eu lieu, la deuxième copie non.
        self.assertEqual(len(executor.executed), 1)

    def test_second_identical_action_not_executed(self):
        # L'alerte "répète la même action" doit arriver AVANT l'exécution
        # de la copie, et non après (sinon on cliquerait deux fois).
        frozen = ScreenState(foreground_window="F", elements=[make_element(0, "A")])
        perception = FakePerception([frozen])
        decider = ScriptedDecider([Click(element_id=0), Click(element_id=0)])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)
        loop.run("clique")
        self.assertEqual(len(executor.executed), 1)

    def test_max_iterations_reached(self):
        # L'écran change à chaque fois (aucune stagnation) mais l'agent ne
        # termine jamais : on doit s'arrêter par la limite d'itérations.
        changing = [ScreenState(foreground_window=f"État {i}") for i in range(6)]
        perception = FakePerception(changing)
        decider = ScriptedDecider([
            TypeText(text="a"),
            TypeText(text="b"),
            TypeText(text="c"),
            TypeText(text="d"),
        ])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=3, action_delay=0)
        result = loop.run("fais des saisies")
        self.assertFalse(result.success)
        self.assertIn("limite", result.reason.lower())
        self.assertEqual(loop.max_iterations, 3)


class TestLoopEdgeCases(unittest.TestCase):
    def test_ask_stops_loop(self):
        screen = ScreenState(foreground_window="F")
        perception = FakePerception([screen])
        decider = ScriptedDecider([Ask(question="Que veux-tu ?")])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)

        result = loop.run("je ne sais pas")
        self.assertFalse(result.success)
        self.assertIn("Clarification", result.reason)
        self.assertEqual(len(executor.executed), 0)

    def test_type_text_no_resolution_needed(self):
        screen = ScreenState(foreground_window="Notepad", elements=[])
        perception = FakePerception([screen])
        decider = ScriptedDecider([TypeText(text="bonjour"), Done(summary="ok")])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)

        result = loop.run("tape bonjour")
        self.assertTrue(result.success)
        self.assertEqual(executor.executed[0].text, "bonjour")

    def test_perception_failure_returns_clean_result(self):
        class BrokenPerception:
            def capture(self):
                raise RuntimeError("aucune fenêtre")

        decider = ScriptedDecider([Done(summary="ok")])
        loop = AgenticLoop(BrokenPerception(), decider, RecordingExecutor(), max_iterations=5, action_delay=0)
        result = loop.run("test")
        self.assertFalse(result.success)
        self.assertIn("Perception", result.reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
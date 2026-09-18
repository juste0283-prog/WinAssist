# ============================================================
#  Tests de la sécurité (point 5) : portail de confirmation
#  devant les actions sensibles (corbeille, extinction...).
# ============================================================

import unittest

from winassist.core.loop import AgenticLoop
from winassist.core.models import Done, ScreenState, SystemAction, TypeText
from winassist.core.security import sensitive_description

from test_loop import FakePerception, RecordingExecutor, ScriptedDecider


class TestSensitiveDescription(unittest.TestCase):
    def test_corbeille_sensible(self):
        action = SystemAction(shortcut="empty_recycle_bin")
        self.assertIsNotNone(sensitive_description(action))

    def test_extinction_sensible(self):
        action = SystemAction(shortcut="shutdown")
        self.assertIn("éteindre", sensitive_description(action))

    def test_volume_pas_sensible(self):
        action = SystemAction(shortcut="volume_up")
        self.assertIsNone(sensitive_description(action))

    def test_action_ordinaire_pas_sensible(self):
        self.assertIsNone(sensitive_description(TypeText(text="bonjour")))


class TestConfirmationGate(unittest.TestCase):
    def _screen(self):
        return ScreenState(foreground_window="Bureau")

    def test_sans_confirmer_la_sensible_est_refusee(self):
        # Règle défensive : pas de confirmer -> REFUS, jamais exécuté.
        perception = FakePerception([self._screen()])
        decider = ScriptedDecider([SystemAction(shortcut="empty_recycle_bin"), Done(summary="ok")])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)

        result = loop.run("vide la corbeille")
        # La corbeille n'est JAMAIS vidée sans confirmation.
        self.assertEqual(executor.executed, [])
        self.assertFalse(result.success)
        # Le refus est journalisé dans l'historique.
        refusals = [h for h in result.history.entries if not h.ok]
        self.assertTrue(any("refus" in (h.error or "") for h in refusals))

    def test_confirmation_oui_execute(self):
        perception = FakePerception([self._screen()])
        decider = ScriptedDecider([SystemAction(shortcut="empty_recycle_bin"), Done(summary="ok")])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)
        loop.confirmer = lambda description: True

        result = loop.run("vide la corbeille")
        self.assertTrue(result.success)
        self.assertEqual(len(executor.executed), 1)
        self.assertEqual(executor.executed[0].shortcut, "empty_recycle_bin")

    def test_confirmation_non_refuse(self):
        perception = FakePerception([self._screen()])
        decider = ScriptedDecider([SystemAction(shortcut="empty_recycle_bin"), Done(summary="ok")])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)
        loop.confirmer = lambda description: False

        result = loop.run("vide la corbeille")
        self.assertEqual(executor.executed, [])
        self.assertFalse(result.success)

    def test_action_ordinaire_sans_confirm_call(self):
        # Aucune confirmation ne doit être demandée pour une saisie de texte.
        calls = []

        def spy(description):
            calls.append(description)
            return True

        perception = FakePerception([self._screen()])
        decider = ScriptedDecider([TypeText(text="bonjour"), Done(summary="ok")])
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)
        loop.confirmer = spy

        result = loop.run("tape bonjour")
        self.assertTrue(result.success)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
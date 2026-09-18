# ============================================================
#  Tests du découpage multi-étapes (point 6, decision/compound.py)
#  « ouvre le bloc-notes et tape bonjour » = 2 actions réelles.
# ============================================================

import unittest

from winassist.core.loop import AgenticLoop
from winassist.core.models import Done, OpenApp, ScreenState, SystemAction, TypeText
from winassist.decision.compound import CompoundDecisionProvider, split_compound

from test_loop import FakePerception, RecordingExecutor, ScriptedDecider


class TestSplitCompound(unittest.TestCase):
    def test_deux_etapes(self):
        parts = split_compound("ouvre le bloc-notes et tape bonjour")
        self.assertEqual(parts, ["ouvre le bloc-notes", "tape bonjour"])

    def test_separateur_puis(self):
        parts = split_compound("monte le volume puis ouvre la calculatrice")
        self.assertEqual(parts, ["monte le volume", "ouvre la calculatrice"])

    def test_phrase_simple_inchangee(self):
        self.assertEqual(split_compound("ouvre le bloc-notes"), ["ouvre le bloc-notes"])

    def test_et_du_texte_non_decoupe(self):
        # « et merci » n'est pas une commande : on garde la phrase entière.
        self.assertEqual(split_compound("tape bonjour et merci"), ["tape bonjour et merci"])

    def test_morceau_inconnu_non_decoupe(self):
        self.assertEqual(
            split_compound("ouvre le bloc-notes puis fais un gâteau"),
            ["ouvre le bloc-notes puis fais un gâteau"],
        )


class TestCompoundLoop(unittest.TestCase):
    """Intégration : la boucle exécute réellement les étapes, dans l'ordre."""

    def test_ouvre_puis_tape(self):
        # État initial : Bureau vide. Après ouverture : Notepad au premier plan.
        desk = ScreenState(foreground_window="Bureau")
        note = ScreenState(foreground_window="Sans titre - Bloc-notes")
        perception = FakePerception([desk, note])
        decider = CompoundDecisionProvider()
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)

        result = loop.run("ouvre le bloc-notes et tape bonjour")
        self.assertTrue(result.success)
        types = [a.type for a in executor.executed]
        self.assertEqual(types, ["open_app", "type_text"])
        self.assertEqual(executor.executed[1].text, "bonjour")

    def test_etape_systeme_puis_ouverture(self):
        # Bureau, toujours Bureau après l'étape "volume", puis Calculatrice
        # une fois l'application réellement ouverte.
        desk = ScreenState(foreground_window="Bureau")
        calc = ScreenState(foreground_window="Calculatrice")
        perception = FakePerception([desk, desk, calc])
        decider = CompoundDecisionProvider()
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)

        result = loop.run("monte le volume et ouvre la calculatrice")
        self.assertTrue(result.success)
        self.assertIsInstance(executor.executed[0], SystemAction)
        self.assertEqual(executor.executed[0].shortcut, "volume_up")
        self.assertIsInstance(executor.executed[1], OpenApp)
        self.assertEqual(executor.executed[1].app_name, "calculatrice")

    def test_premiere_etape_inconnue_propage_demande(self):
        desk = ScreenState(foreground_window="Bureau")
        perception = FakePerception([desk, desk])
        decider = CompoundDecisionProvider()
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=10, action_delay=0)

        result = loop.run("ouvre zzzinconnu puis tape bonjour")
        self.assertFalse(result.success)
        self.assertIn("Clarification", result.reason)
        self.assertEqual(executor.executed, [])

    def test_commande_simple_identique_mock(self):
        desk = ScreenState(foreground_window="Bureau")
        perception = FakePerception([desk])
        decider = CompoundDecisionProvider()
        executor = RecordingExecutor()
        loop = AgenticLoop(perception, decider, executor, max_iterations=5, action_delay=0)
        result = loop.run("ouvre la calculatrice")
        self.assertIsInstance(executor.executed[0], OpenApp)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
# ============================================================
#  Tests du moteur de décision mock (decision/mock.py)
#  Aucun accès au réseau ni à l'écran requis.
# ============================================================

import unittest

from winassist.core.history import ActionHistory
from winassist.core.models import Click, Done, OpenApp, ScreenState, TypeText, UIElement
from winassist.decision import MockDecisionProvider
from winassist.decision.base import DecisionContext


def context(command: str, foreground: str = "Bureau", elements: list = None) -> DecisionContext:
    return DecisionContext(
        command=command,
        state=ScreenState(foreground_window=foreground, elements=elements or []),
        history=ActionHistory(),
    )


class TestMockOpen(unittest.TestCase):
    def setUp(self):
        self.mock = MockDecisionProvider()

    def test_ouvre_bloc_notes(self):
        action = self.mock.decide(context("ouvre le bloc-notes"))
        self.assertIsInstance(action, OpenApp)
        self.assertEqual(action.app_name, "bloc-notes")

    def test_ouvre_whatsapp_unknown_app_asks(self):
        action = self.mock.decide(context("ouvre zigouionium"))
        # pas de nom d'app connu -> on demande une précision
        self.assertEqual(action.type, "ask")

    def test_open_then_done_when_window_matches(self):
        # Premier passage : on ouvre.
        first = self.mock.decide(context("ouvre le bloc-notes"))
        self.assertIsInstance(first, OpenApp)
        # Passage suivant : la fenêtre est maintenant le Bloc-notes -> terminé.
        second = self.mock.decide(context(
            "ouvre le bloc-notes",
            foreground="Sans titre - Bloc-notes",
        ))
        self.assertIsInstance(second, Done)


class TestMockTyping(unittest.TestCase):
    def setUp(self):
        self.mock = MockDecisionProvider()

    def test_tape_texte(self):
        action = self.mock.decide(context("tape bonjour"))
        self.assertIsInstance(action, TypeText)
        self.assertEqual(action.text, "bonjour")

    def test_ecris_dans_champ(self):
        action = self.mock.decide(context("écris dans le le champ nom"))
        self.assertIsInstance(action, TypeText)

    def test_tape_sans_contenu_asks(self):
        action = self.mock.decide(context("tape"))
        self.assertEqual(action.type, "ask")

    def test_typing_then_done(self):
        self.mock.decide(context("tape bonjour"))
        again = self.mock.decide(context("tape bonjour"))
        self.assertIsInstance(again, Done)


class TestMockClick(unittest.TestCase):
    def setUp(self):
        self.mock = MockDecisionProvider()

    @staticmethod
    def _screen_with_button():
        return [
            UIElement(id=0, control_type="List", name="Liste de messages", x=0, y=0, w=200, h=100),
            UIElement(id=1, control_type="Button", name="Envoyer", x=0, y=100, w=80, h=24),
        ]

    def test_click_on_button(self):
        action = self.mock.decide(context(
            "clique sur Envoyer",
            elements=self._screen_with_button(),
        ))
        self.assertIsInstance(action, Click)
        self.assertEqual(action.element_id, 1)  # le bouton, pas la liste

    def test_click_unknown_asks(self):
        action = self.mock.decide(context("clique sur Réservé-aucun", elements=self._screen_with_button()))
        self.assertEqual(action.type, "ask")


class TestMockFallback(unittest.TestCase):
    def test_unknown_command_asks(self):
        mock = MockDecisionProvider()
        action = mock.decide(context("fais un gâteau au chocolat"))
        self.assertEqual(action.type, "ask")


if __name__ == "__main__":
    unittest.main(verbosity=2)
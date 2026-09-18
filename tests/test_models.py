# ============================================================
#  Tests des modèles de données (core/models.py)
#  Aucun accès au réseau ni à l'écran requis.
# ============================================================

import unittest

from winassist.core.models import (
    Action,
    Ask,
    Click,
    Done,
    OpenApp,
    ScreenState,
    SystemAction,
    TypeText,
    UIElement,
    describe_action,
    parse_action,
)


def make_element(id_: int, name: str, control_type: str = "Button",
                 x: int = 100, y: int = 100, w: int = 50, h: int = 20,
                 enabled: bool = True) -> UIElement:
    return UIElement(
        id=id_, control_type=control_type, name=name,
        x=x, y=y, w=w, h=h, enabled=enabled,
    )


class TestUIElement(unittest.TestCase):
    def test_center(self):
        el = make_element(0, "Bouton", x=100, y=200, w=50, h=20)
        self.assertEqual(el.center, (125, 210))

    def test_is_visible_false_when_zero_size(self):
        el = make_element(0, "x", w=0, h=0)
        self.assertFalse(el.is_visible)

    def test_summary_format(self):
        el = make_element(12, "Envoyer")
        self.assertEqual(el.summary(), "#12 Button 'Envoyer' @(125,110)")


class TestScreenState(unittest.TestCase):
    def test_signature_ignores_coordinates(self):
        a = ScreenState(foreground_window="W", elements=[
            make_element(0, "A", x=0, y=0), make_element(1, "B", x=50, y=50)])
        b = ScreenState(foreground_window="W", elements=[
            make_element(0, "A", x=999, y=999), make_element(1, "B", x=10, y=20)])
        # Un déplacement de fenêtre ne doit pas être vu comme du progrès.
        self.assertEqual(a.signature(), b.signature())

    def test_signature_differs_on_name_change(self):
        a = ScreenState(foreground_window="W", elements=[make_element(0, "A")])
        b = ScreenState(foreground_window="W", elements=[make_element(0, "B")])
        self.assertNotEqual(a.signature(), b.signature())


class TestActionParsing(unittest.TestCase):
    """L'union discriminée `Action` doit choisir la bonne classe."""

    def test_click(self):
        action = parse_action({"type": "click", "element_id": 3})
        self.assertIsInstance(action, Click)
        self.assertEqual(action.type, "click")
        self.assertEqual(action.element_id, 3)

    def test_type_text(self):
        action = parse_action({"type": "type_text", "text": "bonjour"})
        self.assertIsInstance(action, TypeText)
        self.assertEqual(action.text, "bonjour")

    def test_done(self):
        action = parse_action({"type": "done", "summary": "ok"})
        self.assertIsInstance(action, Done)

    def test_system_action_roundtrip(self):
        action = parse_action({"type": "system", "shortcut": "volume_up"})
        self.assertIsInstance(action, SystemAction)
        self.assertEqual(action.shortcut, "volume_up")
        with_args = parse_action({"type": "system", "shortcut": "set_wallpaper_color", "args": "bleu"})
        self.assertEqual(with_args.args, "bleu")

    def test_ask(self):
        action = parse_action({"type": "ask", "question": "quoi ?"})
        self.assertIsInstance(action, Ask)

    def test_invalid_type_rejected(self):
        with self.assertRaises(Exception):
            parse_action({"type": "nimporte_quoi"})

    def test_invalid_click_without_geometry_accepted_as_model(self):
        # La validation de contenu (au moins element_id OU x,y) est faite
        # par la boucle (résolution), pas par Pydantic.
        action = parse_action({"type": "click"})
        self.assertIsInstance(action, Click)


class TestDescribeAction(unittest.TestCase):
    def test_descriptions(self):
        self.assertIn("clic", describe_action(Click(x=1, y=2)))
        self.assertIn("bonjour", describe_action(TypeText(text="bonjour")))
        self.assertIn("bloc-notes", describe_action(
            parse_action({"type": "open_app", "app_name": "bloc-notes"})))


if __name__ == "__main__":
    unittest.main(verbosity=2)
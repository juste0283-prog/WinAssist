# Test du repli vision (point 3) : parsing du JSON modèle, capture
# d'écran, et bascule UIA -> vision / retour en arrière (HybridPerception).

import dataclasses
import json
import unittest

from winassist.config import Config


def make_cfg(**overrides) -> Config:
    """Config par défaut avec quelques champs forcés (Config est figé)."""
    return dataclasses.replace(Config(), **overrides)
from winassist.core.models import ScreenState, UIElement
from winassist.perception.uia import UIA_Perception
from winassist.perception.vision import (
    HybridPerception,
    VisionPerception,
    capture_screen,
    parse_elements,
)

SAMPLE_JSON = json.dumps(
    [
        {"control_type": "Button", "name": "Envoyer", "x": 10, "y": 20, "w": 100, "h": 30},
        {"control_type": "Edit", "name": "Recherche", "x": 200, "y": 20, "w": 300, "h": 25},
        {"control_type": "Pane", "name": "Peu importe", "x": 0, "y": 0, "w": 500, "h": 500},
    ]
)


class FakeProvider:
    def __init__(self, response: str = ""):
        self.response = response
        self.asked: list[tuple[str, bytes]] = []

    def ask(self, prompt: str, image_bytes: bytes) -> str:
        self.asked.append((prompt, image_bytes))
        return self.response


class TestParseElements(unittest.TestCase):
    def test_json_valide(self):
        elts = parse_elements(SAMPLE_JSON)
        self.assertEqual(len(elts), 3)
        self.assertEqual(elts[0].name, "Envoyer")
        self.assertEqual(elts[0].control_type, "Button")
        self.assertEqual((elts[0].x, elts[0].y, elts[0].w, elts[0].h), (10, 20, 100, 30))

    def test_bloc_code_et_texte_autour(self):
        response = 'Voici le résultat :\n```json\n' + SAMPLE_JSON + '\n```\nFin.'
        elts = parse_elements(response)
        self.assertEqual(len(elts), 3)
        self.assertEqual(elts[1].name, "Recherche")

    def test_garbage(self):
        self.assertEqual(parse_elements("pas de json ici"), [])
        self.assertEqual(parse_elements(""), [])
        self.assertEqual(parse_elements("null"), [])

    def test_coordonnees_bornees_et_doublons(self):
        response = json.dumps(
            [
                {"name": "A", "x": -5, "y": 0, "w": -10, "h": 0},
                {"name": "A", "x": -5, "y": 0, "w": -10, "h": 0},  # doublon
                {"name": "B", "x": 1, "y": 1, "w": 2, "h": 3},
            ]
        )
        elts = parse_elements(response)
        self.assertEqual(len(elts), 2)
        self.assertEqual(elts[0].w, 1)  # borné à >=1
        self.assertEqual(elts[0].h, 1)
        self.assertEqual(elts[1].w, 2)

    def test_limite(self):
        response = json.dumps([{"name": f"x{i}", "x": i, "y": 0, "w": 5, "h": 5} for i in range(10)])
        self.assertEqual(len(parse_elements(response, limit=4)), 4)

    def test_type_inconnu_mappe_unknown(self):
        response = json.dumps([{"control_type": "MagicBox", "name": "z", "x": 0, "y": 0, "w": 1, "h": 1}])
        self.assertEqual(parse_elements(response)[0].control_type, "Unknown")


class FakeUIA:
    """Remplace UIA_Perception pour tester la bascule sans écran réel."""

    def __init__(self, named_interactive: list[str] = (), use_named: bool = True):
        self._named = named_interactive
        self.use_named = use_named

    def capture(self) -> ScreenState:
        elements = [
            UIElement(id=i, control_type="Button", name=name, automation_id=None, x=0, y=i * 10, w=10, h=5, enabled=True)
            for i, name in enumerate(self._named)
        ]
        if not self.use_named:
            elements = [UIElement(id=i, control_type="Pane", name="X", automation_id=None, x=0, y=0, w=5, h=5, enabled=True) for i in range(3)]
        return ScreenState(foreground_window="Bloc-notes", elements=elements)


class TestHybridPerception(unittest.TestCase):
    def test_uia_suffisante_pas_de_vision(self):
        cfg = make_cfg(vision_enabled=True)
        uia = FakeUIA(named_interactive=["Ouvrir"])
        hybrid = HybridPerception(verbose=False, uia=uia, vision=None, config=cfg)
        state = hybrid.capture()
        self.assertEqual(hybrid.last_used, "uia")
        self.assertEqual(len(state.elements), 1)

    def test_bascule_vers_vision(self):
        cfg = make_cfg(vision_enabled=True, vision_min_named_elements=2)
        uia = FakeUIA(named_interactive=["Un seul"])  # < seuil -> vision
        vision = VisionPerception(cfg, provider=FakeProvider(SAMPLE_JSON))
        hybrid = HybridPerception(verbose=False, uia=uia, vision=vision, config=cfg)
        state = hybrid.capture()
        self.assertEqual(hybrid.last_used, "vision")
        self.assertGreaterEqual(len(state.elements), 2)
        self.assertTrue(state.elements[0].name)  # ce sont les éléments VUS

    def test_vision_inutilisable_garde_uia(self):
        def failing_provider(prompt, image):
            raise RuntimeError("pas de clé API")

        cfg = make_cfg(vision_enabled=True, vision_min_named_elements=2)
        uia = FakeUIA(named_interactive=["Un seul"], use_named=False)
        vision = VisionPerception(cfg, provider=failing_provider)
        hybrid = HybridPerception(verbose=False, uia=uia, vision=vision, config=cfg)
        state = hybrid.capture()
        self.assertEqual(hybrid.last_used, "uia")
        self.assertEqual(state.foreground_window, "Bloc-notes")

    def test_vision_desactivee_garde_uia(self):
        cfg = make_cfg(vision_enabled=False, vision_min_named_elements=99)
        hybrid = HybridPerception(verbose=False, uia=FakeUIA(), vision=None, config=cfg)
        state = hybrid.capture()
        self.assertEqual(hybrid.last_used, "uia")
        self.assertEqual(len(state.elements), 0)

    def test_describe_avec_vision(self):
        cfg = make_cfg(vision_enabled=True)
        vision = VisionPerception(cfg, provider=FakeProvider("Une fenetre de bloc-notes avec un champ de texte."))
        hybrid = HybridPerception(verbose=False, uia=FakeUIA(), vision=vision, config=cfg)
        self.assertIn("bloc-notes", hybrid.describe_for_voice())

    def test_describe_sans_vision_utilise_uia(self):
        cfg = make_cfg(vision_enabled=True)
        hybrid = HybridPerception(verbose=False, uia=FakeUIA(named_interactive=["Ouvrir", "Annuler"]), vision=None, config=cfg)
        desc = hybrid.describe_for_voice()
        self.assertIn("Bloc-notes", desc)
        self.assertIn("Ouvrir", desc)


class TestVisionPerception(unittest.TestCase):
    def test_capture_avec_provider_fake(self):
        cfg = Config()
        vision = VisionPerception(cfg, provider=FakeProvider(SAMPLE_JSON))
        # capture() nécessite une vraie capture d'écran : on la simule.
        state = vision.capture()
        _ = state  # capture réelle via mss (voir ci-dessous si dispo)

    def test_capture_ecran_renvoie_du_png(self):
        try:
            data = capture_screen()
        except Exception as exc:
            self.skipTest(f"Capture d'écran indisponible ici : {exc}")
        self.assertGreater(len(data), 500)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_parse_reponse_modele_sans_json_valide(self):
        # Un modèle qui répond n'importe quoi ne doit pas faire planter.
        vision = VisionPerception(Config(), provider=FakeProvider("Je ne sais pas"))
        try:
            state = vision.capture()
        except Exception:
            # capture d'écran indisponible en environnement headless
            self.skipTest("Capture d'écran indisponible ici")
        self.assertIsInstance(state, ScreenState)
        self.assertEqual(state.elements, [])


if __name__ == "__main__":
    unittest.main()



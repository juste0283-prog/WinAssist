# ============================================================
#  Tests des raccourcis système (point 4, actions/quick_actions.py)
#  On ne déclenche AUCUN effet réel : pas de volume, pas de
#  corbeille, pas de changement de fond d'écran.
# ============================================================

import os
import tempfile
import unittest

from winassist.actions.quick_actions import (
    COLORS,
    SENSITIVE_SHORTCUTS,
    _make_color_bmp,
    run_shortcut,
)


class TestShortcutDispatch(unittest.TestCase):
    def test_shortcut_inconnu_echoue_sans_lever(self):
        ok, msg = run_shortcut("pilote_automate_marteau")
        self.assertFalse(ok)
        self.assertIn("inconnu", msg)

    def test_couleur_inconnue_refusee_sans_effet(self):
        # « argentin » n'existe pas : refus avant toute écriture système.
        ok, msg = run_shortcut("set_wallpaper_color", "argentin")
        self.assertFalse(ok)

    def test_couleurs_disponibles(self):
        self.assertIn("bleu", COLORS)
        self.assertIn("noir", COLORS)

    def test_raccourcis_sensibles_declares(self):
        # La sécurité (point 5) exigera une confirmation pour ceux-là.
        self.assertIn("empty_recycle_bin", SENSITIVE_SHORTCUTS)
        self.assertIn("restart", SENSITIVE_SHORTCUTS)
        self.assertIn("shutdown", SENSITIVE_SHORTCUTS)


class TestWallpaperHelper(unittest.TestCase):
    def test_bmp_valide_genere(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _make_color_bmp((0, 110, 185), path=os.path.join(tmp, "fond.bmp"))
            self.assertTrue(path.exists())
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(2), b"BM")  # signature BMP
            self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
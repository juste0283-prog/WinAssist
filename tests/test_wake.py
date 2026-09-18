# ============================================================
#  Tests du mot d'activation (io/wake.py) — pur texte.
# ============================================================

import unittest

from winassist.io import wake


class TestNormalize(unittest.TestCase):
    def test_accent_and_case(self):
        self.assertEqual(wake.normalize("OK WinAssist !"), "ok winassist")

    def test_empty(self):
        self.assertEqual(wake.normalize(""), "")


class TestDetectWake(unittest.TestCase):
    def setUp(self):
        self.phrases = wake.parse_phrases("OK WinAssist,Hey WinAssist,bonjour winassist,winassist")

    def test_parsing(self):
        self.assertEqual(self.phrases, ["ok winassist", "hey winassist", "bonjour winassist", "winassist"])

    def test_detect_at_start(self):
        self.assertTrue(wake.detect_wake("OK WinAssist ouvre le bloc-notes", self.phrases))

    def test_detect_with_accents(self):
        self.assertTrue(wake.detect_wake("Bonjoùr winassist ouvre", self.phrases))

    def test_wake_alone_is_not_a_command(self):
        self.assertFalse(wake.detect_wake("OK WinAssist", self.phrases))

    def test_no_wake(self):
        self.assertFalse(wake.detect_wake("ouvre le bloc-notes", self.phrases))

    def test_wake_in_middle_not_detected(self):
        self.assertFalse(wake.detect_wake("ouvre le bloc-notes ok winassist", self.phrases))

    def test_tolerant_missing_last_letter(self):
        # « winassist » transcrit « winassis » (une lettre perdue) : toléré.
        self.assertTrue(wake.detect_wake("Bonjour winassis ouvre la calculatrice", self.phrases))

    def test_tolerant_step_one_extra_word(self):
        self.assertTrue(wake.detect_wake("ok winassist s'il ouvre le bloc-notes", self.phrases))

    def test_tolerant_wake_alone_still_rejected(self):
        # Un wake déformé mais SANS commande ne déclenche rien.
        self.assertFalse(wake.detect_wake("bonjour winassis", self.phrases))

    def test_tolerant_different_first_word_rejected(self):
        self.assertFalse(wake.detect_wake("allez winassist ouvre", self.phrases))


class TestStripWake(unittest.TestCase):
    def setUp(self):
        self.phrases = wake.parse_phrases("OK WinAssist,Hey WinAssist")

    def test_strip(self):
        self.assertEqual(
            wake.strip_wake("OK WinAssist ouvre le bloc-notes", self.phrases),
            "ouvre le bloc-notes",
        )

    def test_strip_nothing_when_no_wake(self):
        self.assertEqual(wake.strip_wake("ouvre", self.phrases), "ouvre")

    def test_strip_only_wake(self):
        self.assertEqual(wake.strip_wake("OK WinAssist", self.phrases), "")

    def test_strip_tolerant(self):
        self.assertEqual(
            wake.strip_wake("Hey winassis ouvre le bloc-notes", self.phrases),
            "ouvre le bloc-notes",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
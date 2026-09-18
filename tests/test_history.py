# ============================================================
#  Tests de l'historique et de la détection de blocage
#  (core/history.py) — pur Python, aucun périphérique requis.
# ============================================================

import unittest

from winassist.core.history import ActionHistory, untouched_iteration
from winassist.core.models import Click


class TestHistoryStagnation(unittest.TestCase):
    def test_empty_history_not_stalled(self):
        self.assertFalse(ActionHistory().is_stalled(limit=3))

    def test_stalled_when_screen_never_changes(self):
        h = ActionHistory()
        for i in range(3):
            h.record(i, Click(x=1, y=1), "sig-before", "sig-AFTER-CHANGED")
        # Après 3 actions qui ont CHANGÉ l'écran : pas de blocage.
        self.assertFalse(h.is_stalled(limit=3))

    def test_stalled_when_screen_frozen(self):
        h = ActionHistory()
        for i in range(3):
            h.record(i, Click(x=1, y=1), "sig-before", "sig-before", ok=True)
        self.assertTrue(h.is_stalled(limit=3))

    def test_not_enough_entries(self):
        h = ActionHistory()
        h.record(0, Click(x=1, y=1), "a", "a")
        h.record(1, Click(x=2, y=2), "a", "a")
        # 2 entrées seulement, seuil à 3 -> pas encore concluant.
        self.assertFalse(h.is_stalled(limit=3))

    def test_progress_resets_stagnation(self):
        h = ActionHistory()
        # 2 fois sans changement, puis 1 fois avec changement.
        h.record(0, Click(x=1, y=1), "a", "a")
        h.record(1, Click(x=2, y=2), "a", "a")
        h.record(2, Click(x=3, y=3), "a", "b")
        self.assertFalse(h.is_stalled(limit=3))


class TestUntouchedIteration(unittest.TestCase):
    def test_same_action_detected(self):
        a = Click(element_id=3)
        self.assertTrue(untouched_iteration(a, a))

    def test_different_action_not_detected(self):
        a = Click(element_id=3)
        b = Click(element_id=4)
        self.assertFalse(untouched_iteration(a, b))
        self.assertFalse(untouched_iteration(a, None))


class TestHistoryContext(unittest.TestCase):
    def test_llm_context_lines(self):
        h = ActionHistory()
        h.record(1, Click(x=5, y=5), "before", "after", ok=True)
        self.assertIn("clic", h.to_llm_context())

    def test_human_readable(self):
        h = ActionHistory()
        h.record(1, Click(x=5, y=5), "a", "a", ok=False, error="échec")
        text = h.human_readable()
        self.assertIn("échec", text)
        self.assertIn("aucun changement", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
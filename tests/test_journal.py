# ============================================================
#  Tests du journal de session (point 5, core/journal.py)
#  Écriture JSON Lines + relecture "écoutable".
# ============================================================

import tempfile
import unittest
from pathlib import Path

from winassist.core.journal import Journal


class TestJournal(unittest.TestCase):
    def test_ecrit_et_relit_sans_perte(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.log"
            journal = Journal(path=path, enabled=True)
            journal.record("commande", "vide la corbeille")
            journal.record("etape", "Décision : ouvrir Notepad", agent="mock")
            journal.record("resultat", "Échec : action refusée")
            journal.close()

            heard: list[str] = []
            Journal.replay(path, heard.append)
            self.assertEqual(len(heard), 3)
            self.assertTrue(any("vide la corbeille" in line for line in heard))
            self.assertTrue(any("action refusée" in line.lower() for line in heard))

    def test_desactive_n_ecrit_pas(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Journal(enabled=False)
            journal.record("commande", "x")
            self.assertIsNone(journal.path)

    def test_replay_dossier_introuvable(self):
        heard: list[str] = []
        Journal.replay(Path("aucun/journal.log"), heard.append)
        self.assertTrue(heard and "introuvable" in heard[0])

    def test_json_invalide_ignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.log"
            path.write_text("pas du json\n", encoding="utf-8")
            heard: list[str] = []
            Journal.replay(path, heard.append)
            self.assertEqual(heard, [])

    def test_limit_dernieres_lignes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.log"
            journal = Journal(path=path, enabled=True)
            for i in range(10):
                journal.record("etape", f"ligne {i}")
            journal.close()
            heard: list[str] = []
            lines = Journal.replay(path, heard.append, limit=3)
            self.assertEqual(len(lines), 3)
            self.assertIn("ligne 9", lines[-1])


if __name__ == "__main__":
    unittest.main()
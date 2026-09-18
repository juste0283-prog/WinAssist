# ============================================================
#  Tests de la session vocale et de l'interruption
#  (io/voice_loop.py, io/listener.py) — tout simulé, pas de micro.
# ============================================================

import contextlib
import io
import queue
import threading
import unittest

from winassist.io.listener import InterruptMonitor, is_interrupt
from winassist.io.tts import SilentTTS
from winassist.io.voice_loop import VoiceSession
from winassist.core.loop import RunResult


class TestIsInterrupt(unittest.TestCase):
    def test_detects_french_stop(self):
        self.assertTrue(is_interrupt("arrête s'il te plaît"))

    def test_detects_stop(self):
        self.assertTrue(is_interrupt("stop ça"))

    def test_ignores_normal_speech(self):
        self.assertFalse(is_interrupt("ouvre le bloc-notes"))
        self.assertFalse(is_interrupt("je vais me garer dans le parking"))

    def test_ignores_iteration(self):
        self.assertFalse(is_interrupt("défile vers le bas"))


class FakeLoop:
    """Fausse boucle : n'exécute rien, renvoie un résultat, accepte on_event."""

    def __init__(self, result=None):
        self.on_event = lambda msg: None
        self.result = result or RunResult(True, "fini")
        self.cancelled = []

    def run(self, command):
        return self.result

    def cancel(self, reason=""):
        self.cancelled.append(reason)


class TestInterruptMonitor(unittest.TestCase):
    def test_start_monitor_ignores_exit_flow(self):
        q = queue.Queue()
        q.put("ouvre le bloc-notes")
        loop = FakeLoop()
        monitor = InterruptMonitor(q, loop)
        monitor.start()
        monitor.stop()
        monitor.join(timeout=2)
        # Une phrase normale ne doit pas interrompre.
        self.assertEqual(loop.cancelled, [])


class FakeListener:
    """Simule l'écouteur : une file remplie à l'avance."""

    def __init__(self, commands):
        self.commands = queue.Queue()
        for c in commands:
            self.commands.put(c)

    def start(self):
        pass

    def stop(self):
        pass


class TestVoiceSession(unittest.TestCase):
    def test_session_executes_then_exits(self):
        tts = SilentTTS()
        # D'abord une commande, ensuite la sortie.
        listener = FakeListener(["ouvre le bloc-notes", "au revoir"])
        session = VoiceSession(
            stt=None,
            tts=tts,
            make_loop=lambda: FakeLoop(),
            listener=listener,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            session.run()

        # La TTS a annoncé l'exécution et l'adieu.
        spoken = " ".join(tts.spoken)
        self.assertIn("J'exécute", spoken)
        self.assertIn("Au revoir", spoken)

    def test_exit_on_au_revoir(self):
        tts = SilentTTS()
        listener = FakeListener(["au revoir"])
        session = VoiceSession(stt=None, tts=tts, make_loop=lambda: FakeLoop(), listener=listener)
        with contextlib.redirect_stdout(io.StringIO()):
            session.run()
        self.assertIn("Au revoir", " ".join(tts.spoken))


if __name__ == "__main__":
    unittest.main(verbosity=2)
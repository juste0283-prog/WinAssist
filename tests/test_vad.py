# ============================================================
#  Tests du VAD (io/audio.py) — signaux synthétiques, pas de micro.
# ============================================================

import unittest

import numpy as np

from winassist.io.audio import find_phrase_end


def sine_chunk(seconds: float, freq: float = 440.0, amp: float = 5000.0) -> np.ndarray:
    """Sinusoïde 'voix' : énergie forte, au-dessus du seuil (300)."""
    t = np.arange(int(seconds * 16000)) / 16000
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.int16)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * 16000), dtype=np.int16)


def frame(samples) -> float:
    """Helper : extrait l'index de fin présumé (en échantillon)."""
    return samples


class TestFindPhraseEnd(unittest.TestCase):
    def test_phrase_detected_after_trailing_silence(self):
        # 1s silence, 0.5s voix, 1s silence.
        signal = np.concatenate([silence(1.0), sine_chunk(0.5), silence(1.0)])
        end = find_phrase_end(signal, 16000, threshold=300.0,
                              trailing_silence_seconds=0.7, min_speech_seconds=0.25)
        self.assertIsNotNone(end)
        # La fin doit tomber après la voix (fin voix = 1.5s -> 24000).
        self.assertGreaterEqual(end, 24000 - 480)
        self.assertLessEqual(end, 24000 + 480)

    def test_silence_only_returns_none(self):
        self.assertIsNone(find_phrase_end(silence(2.0), 16000, 300.0))

    def test_tone_continuing_returns_none(self):
        # La personne parle encore (pas de silence de traîne).
        signal = np.concatenate([silence(0.2), sine_chunk(1.5)])
        self.assertIsNone(find_phrase_end(signal, 16000, 300.0, trailing_silence_seconds=0.7))

    def test_short_click_ignored(self):
        # Un bruit bref (< 0.25s) ne doit pas devenir une commande.
        signal = np.concatenate([silence(0.2), sine_chunk(0.05), silence(1.0)])
        self.assertIsNone(find_phrase_end(signal, 16000, 300.0, min_speech_seconds=0.25))

    def test_long_quiet_gap_is_end(self):
        signal = np.concatenate([sine_chunk(0.4), silence(2.0)])
        end = find_phrase_end(signal, 16000, 300.0,
                              trailing_silence_seconds=0.7, min_speech_seconds=0.25)
        self.assertIsNotNone(end)
        # Doit s'arrêter là où la voix s'arrête (0.4s -> 6400).
        self.assertLessEqual(end, 6400 + 480)


if __name__ == "__main__":
    unittest.main(verbosity=2)
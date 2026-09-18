# ============================================================
#  WinAssist — écouteur audio continu (point 2)
# ============================================================
#  `AudioCommandListener` : un thread qui enregistre les phrases,
#  les transcrit, applique le mot d'activation, et dépose les
#  COMMANDES (sans le wake) dans une file partagée.
#
#  `InterruptMonitor` : pendant qu'une tâche s'exécute, il surveille
#  la MÊME file pour capter les mots d'interruption (« arrête »...)
#  et demande l'arrêt à la boucle agentique (cancel).
#
#  Conséquence de design : on n'ouvre JAMAIS deux flux micro simultanés ;
#  l'écoute est un seul thread, utilisé soit pour les commandes (repos),
#  soit pour l'interruption (exécution). C'est simple et fiable.
# ============================================================

from __future__ import annotations

import queue
import threading

import numpy as np

from winassist.io import audio, wake as wake_module
from winassist.io.stt import SpeechRecognizer


class AudioCommandListener(threading.Thread):
    """Thread unique d'écoute : produit des commandes dans `commands`."""

    def __init__(
        self,
        stt: SpeechRecognizer,
        *,
        sample_rate: int = 16000,
        threshold: float = 300.0,
        max_duration: float = 10.0,
        wake_enabled: bool = True,
        wake_phrases: list[str] | None = None,
    ):
        super().__init__(daemon=True, name="audio-listener")
        self.stt = stt
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.max_duration = max_duration
        self.wake_enabled = wake_enabled
        self.wake_phrases = wake_phrases or []
        # File des commandes reconnues (consommée par la session vocale
        # ou par l'InterruptMonitor pendant une exécution).
        self.commands: queue.Queue = queue.Queue()
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            audio.reset_capture()  # réarme la capture pour la phrase suivante
            samples: np.ndarray | None = None
            try:
                samples = audio.record_phrase(
                    sample_rate=self.sample_rate,
                    threshold=self.threshold,
                    max_duration=self.max_duration,
                )
            except Exception:
                continue  # pas de micro dispo : on retente doucement
            if samples is None or samples.size == 0:
                continue

            text = self.stt.transcribe_phrase(samples, self.sample_rate)
            if not text:
                continue

            # Filtre du mot d'activation.
            if self.wake_enabled:
                if not wake_module.detect_wake(text, self.wake_phrases):
                    continue
                command = wake_module.strip_wake(text, self.wake_phrases)
            else:
                command = text

            if command.strip():
                self.commands.put(command.strip())

    def stop(self) -> None:
        """Arrête l'écoute (débloque aussi la capture en cours)."""
        self._stop.set()
        audio.stop_capture()

    def stop_after_natural(self, n: int) -> list[str]:
        """Petit utilitaire de TEST : écoute (bloquant) et collecte n phrases."""
        got: list[str] = []
        while len(got) < n:
            got.append(self.commands.get())
        return got


# ------------------------------------------------------------------
#  Mots d'interruption (reconnaissance vocale pendant l'exécution)
# ------------------------------------------------------------------
DEFAULT_INTERRUPT_WORDS = ("stop", "arrête", "arrete", "annule", "retire", "laisse")

# Extraire les mots clés d'une phrase, avec gestion des accents.


def is_interrupt(text: str, words: tuple[str, ...] = DEFAULT_INTERRUPT_WORDS) -> bool:
    """La phrase entendue contient-elle un mot d'interruption ?"""
    n = wake_module.normalize(text)
    for word in words:
        if word in n.split():
            return True
    return False


class InterruptMonitor(threading.Thread):
    """Draine `commands` et interrompt la boucle si la voix le demande."""

    def __init__(self, commands: queue.Queue, loop, interrupt_words=DEFAULT_INTERRUPT_WORDS):
        super().__init__(daemon=True, name="interrupt-monitor")
        self.commands = commands
        self.loop = loop
        self.interrupt_words = interrupt_words
        self._done = threading.Event()

    def run(self) -> None:
        while not self._done.is_set():
            try:
                text = self.commands.get(timeout=0.2)
            except queue.Empty:
                continue
            if is_interrupt(text, self.interrupt_words):
                self.loop.cancel(reason=f"Interrompu à la voix : « {text} »")
            else:
                # Phrase non liée à l'interruption : on la REMET dans la
                # file pour que la session la traite comme prochaine commande
                # (ex. « au revoir » prononcé pendant une tâche rapide).
                self.commands.put(text)
                threading.Event().wait(0.05)  # éviter de monopoliser la file

    def stop(self) -> None:
        self._done.set()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
# ============================================================
#  WinAssist — session vocale (orchestration point 2)
# ============================================================
#  Boucle de vie "grand public" de l'assistant :
#
#     1. L'utilisateur prononce « OK WinAssist <commande> ».
#     2. Le listener transcrit, détecte le wake, et dépose la commande.
#     3. On exécute la commande dans la boucle agentique, TOUT en
#        écoutant encore (mots d'interruption : stopper la tâche).
#     4. On annonce le résultat à voix haute, et on réécoute.
#
#  L'utilisateur NE VOIT PAS l'écran : à chaque étape, on lui décrit
#  l'écran et les actions effectuées (retour vocal, cf. TTS).
# ============================================================

from __future__ import annotations

import queue
import threading

from winassist.config import Config, get_config
from winassist.core.loop import AgenticLoop
from winassist.io.listener import AudioCommandListener, InterruptMonitor
from winassist.io.stt import SpeechRecognizer
from winassist.io import wake as wake_module

# Phrases qui QUITTENT la session vocale (dites sans wake, en français).
EXIT_WORDS = ("au revoir", "quitte", "termine", "arrête-toi", "bonne nuit")


class VoiceSession:
    """Assemble le tout : écoute + exécution + retour vocal."""

    def __init__(
        self,
        stt: SpeechRecognizer,
        tts,
        make_loop,
        config: Config | None = None,
        current_loop_holder: dict | None = None,
        listener=None,
    ):
        self.stt = stt
        self.tts = tts
        self.make_loop = make_loop          # fonction() -> AgenticLoop
        self.config = config or get_config()
        # Listener injectable (tests) ou construit dans run().
        self._injected_listener = listener
        # Un dict partagé pour que le clavier de secours (ESC) trouve la
        # boucle en cours d'exécution (voir io/interrupt.py).
        self.current_loop_holder = current_loop_holder if current_loop_holder is not None else {"loop": None}

    # ------------------------------------------------------------------
    #  La session principale
    # ------------------------------------------------------------------
    def run(self) -> None:
        phrases = wake_module.parse_phrases(self.config.wake_phrases)

        if self._injected_listener is not None:
            listener = self._injected_listener
        else:
            listener = AudioCommandListener(
                self.stt,
                sample_rate=self.config.audio_sample_rate,
                threshold=float(self.config.vad_threshold),
                max_duration=float(self.config.max_phrase_seconds),
                wake_enabled=self.config.wake_word_enabled,
                wake_phrases=phrases,
            )
            listener.start()
        self.tts.speak("Bonjour, je t'écoute.")
        print("[Voice] Écoute active. Dis « OK WinAssist » suivi de ta commande.")
        if self.config.wake_word_enabled:
            print(f"[Voice] Phrases d'activation : {', '.join(phrases)}")

        try:
            while True:
                try:
                    command = listener.commands.get(timeout=1.0)
                except queue.Empty:
                    continue

                # -- quitter la session ? ------------------------------
                if self._is_exit(command):
                    self.tts.speak("Au revoir.")
                    break

                print(f"[Voice] Commande reçue : « {command} »")
                self._announce_command(command)

                result, track = self._execute_and_announce(command, listener)
                # On le laisse terminer sa phrase avant de redonner la main.
                self._describe_final_state(result)

        except KeyboardInterrupt:
            pass
        finally:
            listener.stop()

    # ------------------------------------------------------------------
    #  Exécution avec possibilité d'interruption vocale
    # ------------------------------------------------------------------
    def _execute_and_announce(self, command: str, listener: AudioCommandListener):
        """Lance la boucle agentique, avec moniteur d'interruption vocale.

        La boucle tourne dans CE thread (elle est bloquante) ; l'écouteur
        continue de tourner en parallèle et l'InterruptMonitor draine la
        file pour attraper « arrête » / « stop » au vol.
        """
        loop: AgenticLoop = self.make_loop()

        # Stream des étapes vers la voix (et la console pour le dev).
        events: list[str] = []

        def _on_event(msg: str) -> None:
            events.append(msg)
            self.tts.speak(msg)
            print(f"  {msg}")

        loop.on_event = _on_event
        self.current_loop_holder["loop"] = loop
        try:
            with InterruptMonitor(listener.commands, loop):
                result = loop.run(command)
        finally:
            self.current_loop_holder["loop"] = None
        return result, events

    def _announce_command(self, command: str) -> None:
        self.tts.speak(f"J'exécute : {command}")

    def _is_exit(self, command: str) -> bool:
        n = wake_module.normalize(command)
        if not n:
            return False
        return any(word in n for word in EXIT_WORDS)

    def _describe_final_state(self, result) -> None:
        """Annonce le résumé de la tâche et, si utile, décrit l'écran."""
        if result is None:
            return
        self.tts.speak(result.summary())
        if getattr(result, "final_state", None) is not None:
            # Trop verbeux à tout lire : on lit l'essentiel de la fenêtre.
            desc = result.final_state.describe_visible()
            # On limite à la description des éléments nommés.
            brief = desc.split("\n- ")[0]
            self.tts.speak(brief)
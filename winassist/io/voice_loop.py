# ============================================================
#  WinAssist — session vocale (orchestration point 2 + point 5)
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
#
#  Point 5 (sécurité) au cœur de la session :
#   - CONFIRMATIONS vocales avant toute action sensible (corbeille,
#     extinction, suppression...) : « Attention, vider la corbeille.
#     Confirme avec oui, ou dis non » ;
#   - JOURNAL de session réécoutable via « lit le journal » ;
#   - interruption vocale (« arrête ») et touche ÉCHAP pendant une tâche.
# ============================================================

from __future__ import annotations

import queue
import threading
import time

from winassist.config import Config, get_config
from winassist.core.journal import Journal
from winassist.core.loop import AgenticLoop
from winassist.io.listener import AudioCommandListener, InterruptMonitor, is_interrupt
from winassist.io.stt import SpeechRecognizer
from winassist.io import wake as wake_module

# Phrases qui QUITTENT la session vocale (dites sans wake, en français).
EXIT_WORDS = ("au revoir", "quitte", "termine", "arrête-toi", "bonne nuit")
# Phrases qui déclenchent la relecture du journal.
JOURNAL_WORDS = ("lit le journal", "écoute le journal", "lis le journal", "relis le journal", "journal")
# Oui / Non de confirmation (mots simples, sans wake).
YES_WORDS = ("oui", "yes", "confirme", "confirmé", "ok", "okay", "vas-y", "fais-le", "valide", "d'accord", "go")
NO_WORDS = ("non", "nope", "annule", "laisse tomber", "ne le fais pas", "stop")


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
        journal: Journal | None = None,
    ):
        self.stt = stt
        self.tts = tts
        self.make_loop = make_loop          # fonction() -> AgenticLoop
        self.config = config or get_config()
        # Listener injectable (tests) ou construit dans run().
        self._injected_listener = listener
        # Journal de session (point 5), créé dans run() si besoin.
        self.journal = journal
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
        self.listener = listener

        if self.journal is None and self.config.journal_enabled:
            try:
                self.journal = Journal(enabled=True)
            except Exception:
                self.journal = None

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
                    if self.journal:
                        self.journal.close()
                    break

                # -- réécouter le journal ? ---------------------------
                if self._journal_requested(command):
                    self._replay_journal()
                    continue

                print(f"[Voice] Commande reçue : « {command} »")
                if self.journal:
                    self.journal.record("commande", command)
                self._announce_command(command)

                result, track = self._execute_and_announce(command, listener)
                # On le laisse terminer sa phrase avant de redonner la main.
                self._describe_final_state(result)

        except KeyboardInterrupt:
            pass
        finally:
            listener.stop()
            if self.journal:
                self.journal.close()

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

        # Confirmation des actions sensibles (point 5) ET journal :
        # on branche le confirmer vocal directement sur la boucle.
        loop.confirmer = self._confirm

        # Stream des étapes vers la voix (et la console pour le dev).
        events: list[str] = []

        def _on_event(msg: str) -> None:
            events.append(msg)
            if self.journal:
                self.journal.record("etape", msg)
            self.tts.speak(msg)
            print(f"  {msg}")

        loop.on_event = _on_event
        self.current_loop_holder["loop"] = loop
        try:
            with InterruptMonitor(listener.commands, loop):
                result = loop.run(command)
        finally:
            self.current_loop_holder["loop"] = None
        if self.journal:
            self.journal.record("resultat", result.summary())
        return result, events

    # ------------------------------------------------------------------
    #  Confirmation vocale des actions sensibles (point 5)
    # ------------------------------------------------------------------
    def _confirm(self, description: str) -> bool:
        """Demande un « oui / non » vocal avant une action dangereuse."""
        if not self.config.confirm_sensitive:
            return True  # l'utilisateur a explicitement désactivé la confirmation
        question = f"Attention : {description}. Confirme avec oui, ou dis non pour annuler."
        print("[Voice] " + question)
        self.tts.speak(question)

        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                answer = self.listener.commands.get(timeout=0.5)
            except queue.Empty:
                continue
            norm = wake_module.normalize(answer)
            if not norm:
                continue
            if any(w in norm for w in YES_WORDS):
                self.tts.speak("Confirmé.")
                return True
            if any(w in norm for w in NO_WORDS) or is_interrupt(answer):
                self.tts.speak("Action annulée.")
                return False
            # Phrase hors sujet pendant la confirmation : on la remet dans
            # la file pour l'exécuter juste après (ou la rejoindre).
            self.listener.commands.put(answer)
        self.tts.speak("Pas de confirmation reçue. Action annulée.")
        return False

    # ------------------------------------------------------------------
    #  Journal écoutable (point 5)
    # ------------------------------------------------------------------
    def _replay_journal(self) -> None:
        if self.journal is None or self.journal.path is None:
            self.tts.speak("Le journal est désactivé.")
            return
        print(f"[Voice] Relecture du journal : {self.journal.path}")
        Journal.replay(self.journal.path, self.tts.speak, limit=20)

    def _announce_command(self, command: str) -> None:
        self.tts.speak(f"J'exécute : {command}")

    def _is_exit(self, command: str) -> bool:
        n = wake_module.normalize(command)
        if not n:
            return False
        return any(word in n for word in EXIT_WORDS)

    def _journal_requested(self, command: str) -> bool:
        n = wake_module.normalize(command)
        if not n:
            return False
        return any(word in n for word in JOURNAL_WORDS)

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
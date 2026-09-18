# ============================================================
#  WinAssist — retour vocal (TTS)
# ============================================================
#  Deux moteurs derrière LA MÊME interface ``speak(text)`` :
#    - Pyttsx3TTS : synthèse locale Windows (SAPI 5), aucun réseau.
#                  Retard de démarrage faible, voix robotique acceptable.
#    - EdgeTTS    : voix Edge (Microsoft), très naturelle, mais réseau.
#  Choix via WINASSIST_TTS_ENGINE=pyttsx3|edge.
#
#  L'API (speak) ne bloque jamais l'appelant : la lecture se fait en
#  arrière-plan. En cas de moteur indisponible, on dégrade en silence
#  (console) plutôt que de crasher la boucle agentique.
# ============================================================

from __future__ import annotations

import os
import queue
import tempfile
import threading

from winassist.config import Config, get_config

# ------------------------------------------------------------------
#  Moteur 1 : pyttsx3 (local Windows)
# ------------------------------------------------------------------
def _make_pyttsx3_engine():
    try:
        import pyttsx3

        engine = pyttsx3.init()
        try:
            rate = engine.getProperty("rate")
            engine.setProperty("rate", max(120, int(rate * 0.9)))
        except Exception:
            pass
        try:
            voices = engine.getProperty("voices")
            for v in voices:
                if "fr" in (v.id or "").lower() or "french" in (v.name or "").lower():
                    engine.setProperty("voice", v.id)
                    break
        except Exception:
            pass
        return engine
    except Exception:
        return None


class Pyttsx3TTS:
    """Synthèse vocale locale, non bloquante (file + thread)."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._engine = _make_pyttsx3_engine() if enabled else None
        self._queue: queue.Queue = queue.Queue()
        if self._engine is not None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def _run(self) -> None:
        while True:
            text = self._queue.get()
            if text is None:
                break
            self._speak_sync(text)

    def _speak_sync(self, text: str) -> None:
        if self._engine is None:
            return
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception:
            try:
                self._engine._inLoop = False
            except Exception:
                pass
            self._engine = None  # on abandonne la voix sans crash

    def speak(self, text: str) -> None:
        if self.enabled and self._engine is not None:
            self._queue.put(text)

    def close(self) -> None:
        if self._engine is not None:
            self._queue.put(None)


# ------------------------------------------------------------------
#  Moteur 2 : edge-tts (voix Microsoft, réseau)
# ------------------------------------------------------------------
def _mci_play_mp3(path: str, wait: bool = True) -> None:
    """Joue un fichier mp3 via winmm (MCI) — aucun lecteur externe requis."""
    import ctypes

    winmm = ctypes.windll.winmm
    command = f'open "{path}" type mpegvideo alias winassist_voice'
    winmm.mciSendStringW(command, None, 0, None)
    winmm.mciSendStringW("play winassist_voice" + (" wait" if wait else ""), None, 0, None)
    winmm.mciSendStringW("close winassist_voice", None, 0, None)


class EdgeTTS:
    """Voix Edge, générée via le réseau sur un thread dédié (async)."""

    def __init__(self, voice: str = "fr-FR-EloiseNeural"):
        self.voice = voice
        self.enabled = True

    def _generate_and_play(self, text: str) -> None:
        import asyncio

        import edge_tts

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, self.voice)
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            try:
                await communicate.save(tmp.name)
                _mci_play_mp3(tmp.name, wait=True)
            finally:
                try:
                    os.remove(tmp.name)
                except OSError:
                    pass

        asyncio.run(_run())

    def speak(self, text: str) -> None:
        if not self.enabled:
            return
        # Un thread par énoncé : simple, et l'appelant n'est jamais bloqué.
        threading.Thread(target=self._generate_and_play, args=(text,), daemon=True).start()

    def close(self) -> None:
        pass  # les threads sont daemon : rien à fermer proprement


# ------------------------------------------------------------------
#  Fabrique
# ------------------------------------------------------------------
def make_tts(config: Config | None = None):
    """Construit la TTS choisie. En cas d'échec, renvoie un « faux » muet."""
    config = config or get_config()
    engine = config.tts_engine
    if engine == "edge":
        return EdgeTTS(voice=config.edge_voice)
    return Pyttsx3TTS(enabled=config.enable_tts)


# ------------------------------------------------------------------
#  Un "faux" silencieux (tests), même interface speak()
# ------------------------------------------------------------------
class SilentTTS:
    def __init__(self):
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def close(self) -> None:
        pass


# Instance globale : toute l'app partage la voix.
_default = None


def get_tts() -> object:
    """Accès à la TTS globale (créée à la première demande)."""
    global _default
    if _default is None:
        _default = make_tts()
    return _default
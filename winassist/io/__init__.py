"""Paquet `io` : entrées/sorties audio de l'assistant.

- tts.py        : synthèse vocale (pyttsx3 local ou edge-tts) — opérationnelle.
- stt.py        : reconnaissance vocale (Whisper API/local, Vosk).
- wake.py       : mot d'activation — logique pure, testable.
- audio.py      : capture micro + détection de voix (VAD).
- listener.py   : thread d'écoute continue + moniteur d'interruption.
- voice_loop.py : session vocale complète (de bout en bout).
- interrupt.py  : arrêt d'urgence clavier (ESC).
"""

from winassist.io.tts import Pyttsx3TTS, EdgeTTS, SilentTTS, get_tts, make_tts
from winassist.io.stt import SpeechRecognizer, make_stt
from winassist.io import wake

__all__ = [
    "Pyttsx3TTS", "EdgeTTS", "SilentTTS", "get_tts", "make_tts",
    "SpeechRecognizer", "make_stt",
    "wake",
]
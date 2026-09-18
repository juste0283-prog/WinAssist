"""Paquet `io` : entrées/sorties audio de l'assistant.

- tts.py : synthèse vocale (pyttsx3), opérationnelle dès maintenant.
- stt.py : reconnaissance vocale, POINT 2 du plan (placeholder).
"""

from winassist.io.tts import TTS, get_tts

__all__ = ["TTS", "get_tts"]
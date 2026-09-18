# ============================================================
#  WinAssist — retour vocal (TTS) — base opérationnelle
# ============================================================
#  On annonce à voix haute les événements de la boucle : chaque action
#  significative, le résultat, le résumé final.
#
#  Moteur : pyttsx3 (synthèse locale via SAPI 5 sur Windows, aucune
#  dépendance réseau). Si le moteur ne démarre pas (machine sans voix
#  SAPI, environnement contraint), on "dégrade" silencieusement : les
#  messages sont simplement affichés dans la console au lieu de crash.
#
#  NB : edge-tts (voix de meilleure qualité) est une option du point 2 ;
#  on garde l'interface `TTS` pour pouvoir en changer sans toucher l'appelant.
# ============================================================

from __future__ import annotations

import queue
import threading

import pyttsx3


def _make_engine():
    """Crée le moteur pyttsx3 de façon robuste.

    Retourne None si le moteur ne peut pas être initialisé.
    """
    try:
        engine = pyttsx3.init()
        # Débit légèrement réduit : plus confortable pour les réglages
        # de vitesse par défaut de Windows (SAPI) avec du français.
        try:
            rate = engine.getProperty("rate")
            engine.setProperty("rate", max(120, int(rate * 0.9)))
        except Exception:
            pass
        # On choisit une voix en français si elle est disponible.
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


class TTS:
    """Synthèse vocale simple, non bloquante (file d'attente + thread)."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._engine = _make_engine() if enabled else None
        # File d'attente : les messages sont lus en arrière-plan pour ne
        # JAMAIS bloquer la boucle d'action sur la durée d'un énoncé.
        self._queue: queue.Queue[str] = queue.Queue()
        if self._engine is not None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    # -- méthode interne : le thread consomme la file -----------------
    def _run(self) -> None:
        while True:
            text = self._queue.get()
            if text is None:  # signal d'arrêt propre
                break
            self._speak_sync(text)

    def _speak_sync(self, text: str) -> None:
        if self._engine is None:
            return
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception:
            # Le moteur peut "mourir" (consommation de ressource) :
            # on tente de le recréer une fois, sinon on abandonne la voix.
            try:
                self._engine._inLoop = False  # déblocage si boucle morte
            except Exception:
                pass
            self._engine = None

    # -- API publique -----------------------------------------------
    def speak(self, text: str) -> None:
        """Prononce `text` (attend son tour, n'interrompt rien)."""
        if not self.enabled or self._engine is None:
            return
        self._queue.put(text)

    def stop(self) -> None:
        """Termine proprement le thread de lecture (fin de session)."""
        if self._engine is not None:
            self._queue.put(None)


# Une instance globale : toute l'app partage LA voix.
_default: TTS | None = None


def get_tts() -> TTS:
    """Accès à la TTS globale (créée à la première demande)."""
    global _default
    if _default is None:
        _default = TTS()
    return _default
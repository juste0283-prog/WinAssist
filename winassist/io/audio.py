# ============================================================
#  WinAssist — capture audio et détection de voix (point 2)
# ============================================================
#  Deux responsabilités :
#   1. Capturer le micro en continu (sounddevice, stéréo/16kHz) ;
#   2. Découper le flux en "phrases" grâce à un détecteur d'activité
#      vocale (VAD) à base d'énergie — simple, léger, sans modèle.
#
#  Le VAD est une FONCTION PURE (aucune entrée/sortie) : on peut donc
#  la tester avec des signaux synthétiques, sans micro (voir tests).
#
#  Format interne : tableau NumPy `int16` mono, 16 kHz — le format
#  natif des moteurs de reconnaissance (Whisper/Vosk).
# ============================================================

from __future__ import annotations

import time

import numpy as np

# sounddevice est importé paresseusement : la partie logique (VAD) reste
# testable même si le paquet audio n'est pas installé.
try:
    import sounddevice as sd
    _AUDIO_AVAILABLE = True
except ImportError:
    sd = None
    _AUDIO_AVAILABLE = False

# Durée d'une "frame" d'analyse en secondes (30 ms est un bon compromis
# précision / coût pour l'activité vocale).
FRAME_SECONDS = 0.03


# ------------------------------------------------------------------
#  VAD : purement mathématique, testable
# ------------------------------------------------------------------
def frame_rms(samples: np.ndarray) -> float:
    """RMS (root mean square) d'un signal : mesure son énergie moyenne.

    Pour du PCM int16, un silence vaut ~0, une voix normale frisera le
    millier d'unités. Le seuil (config.vad_threshold, défaut 300) sépare
    le "bruit de fond" de la "voix".
    """
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


def find_phrase_end(
    samples: np.ndarray,
    sample_rate: int,
    threshold: float = 300.0,
    trailing_silence_seconds: float = 0.7,
    min_speech_seconds: float = 0.25,
) -> int | None:
    """En détection au fil de l'eau : la phrase est-elle finie ?

    Analyse le signal accumulé jusqu'ici et renvoie, si une phrase s'est
    terminée, l'index du dernier échantillon de celle-ci. Renvoie None
    si la personne parle encore (pas assez de silence de traîne) ou si
    le début n'est même pas assez long pour être de la voix.

    Cette fonction est appelée à chaque bloc enregistré ; dès qu'elle
    renvoie un index, on coupe l'enregistrement (voir `record_phrase`).
    """
    n = samples.size
    if n == 0:
        return None

    frame_size = max(1, int(sample_rate * FRAME_SECONDS))
    n_frames = n // frame_size

    # Pour chaque frame, on calcule son énergie.
    energies = np.empty(n_frames, dtype=np.float64)
    for i in range(n_frames):
        energies[i] = frame_rms(samples[i * frame_size:(i + 1) * frame_size])

    speech = energies > threshold
    if not speech.any():
        return None  # personne ne parle : on continue d'écouter

    # ~ début de la voix : première frame au-dessus du seuil.
    first_speech = int(np.argmax(speech))

    # ~ fin présumée : dernière frame considérée comme de la voix.
    #   (np.flatnonzero renvoie les indices des frames "voix").
    speech_indices = np.flatnonzero(speech)
    last_speech = int(speech_indices[-1])

    # Le début est trop court pour être une vraie phrase ? (click, bruit)
    if (last_speech - first_speech + 1) * frame_size < int(sample_rate * min_speech_seconds):
        return None

    # Y a-t-il assez de silence APRÈS la dernière frame de voix ?
    trailing_frames_needed = int(trailing_silence_seconds / FRAME_SECONDS)
    frames_after = n_frames - last_speech - 1
    if frames_after >= trailing_frames_needed:
        return (last_speech + 1) * frame_size

    return None  # la personne parle encore


# ------------------------------------------------------------------
#  Enregistrement d'une phrase (micro)
# ------------------------------------------------------------------
def record_phrase(
    sample_rate: int = 16000,
    threshold: float = 300.0,
    max_duration: float = 10.0,
    trailing_silence_seconds: float = 0.7,
    device: int | None = None,
) -> np.ndarray | None:
    """BLOQUANT : enregistre jusqu'à ce qu'une phrase soit détectée.

    Renvoie la phrase en int16 mono, ou None si rien n'a été dit dans
    `max_duration` secondes. C'est la fonction utilisée par la boucle
    vocale pour écouter chaque commande.

    Exigence technique : sounddevice (pip install sounddevice). Signalé
    clairement si la bibliothèque manque.
    """
    if sd is None:
        raise RuntimeError(
            "Le paquet 'sounddevice' est requis pour le micro : python -m pip install sounddevice"
        )

    chunks: list[np.ndarray] = []
    started = time.time()

    # Stream mono, PCM int16 — le plus universel pour STT.
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16", device=device) as stream:
        while (time.time() - started) < max_duration and not _STOP_CAPTURE:
            # On lit un gros bloc (0.5 s) : ça suffit pour réagir vite.
            data, overflowed = stream.read(sample_rate // 2)
            if overflowed:
                pass  # pas grave en prototype : on ignore les dépassements
            chunks.append(data.copy())

            signal = np.concatenate(chunks)
            end = find_phrase_end(signal, sample_rate, threshold, trailing_silence_seconds)
            if end is not None:
                return signal[:end]

            # Sécurité supplémentaire : trop de parole continue ?
            if (time.time() - started) > max_duration:
                break

    # On n'a rien entendu de concluant : on rend l'enregistrement quand
    # même (le STT jugera) ou None s'il est vide.
    if chunks and np.concatenate(chunks).size > sample_rate // 2:
        return np.concatenate(chunks)
    return None


# Utilisé par la boucle vocale pour interrompre l'écoute (fin de session).
_STOP_CAPTURE = False


def stop_capture() -> None:
    """Demande à la capture en cours de s'arrêter au prochain bloc."""
    global _STOP_CAPTURE
    _STOP_CAPTURE = True


def reset_capture() -> None:
    """Réarme la capture pour la phrase suivante."""
    global _STOP_CAPTURE
    _STOP_CAPTURE = False
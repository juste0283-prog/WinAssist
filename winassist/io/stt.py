# ============================================================
#  WinAssist — reconnaissance vocale (STT) — POINT 2
# ============================================================
#  Trois moteurs interchangeables derrière UNE interface :
#    - WhisperAPI_STT  : API compatible OpenAI (clé requise, réseau).
#    - FasterWhisperSTT: Whisper LOCAL (faster-whisper, modèle téléchargé
#                        une seule fois, fonctionne hors-ligne).
#    - VoskSTT         : Vosk local (modèle français, très léger).
#
#  L'interface commune est `transcribe_audio(samples, sample_rate) -> str`.
#  La boucle vocale ne connaît PAS le moteur : on peut en changer sans
#  toucher au reste (comme pour la TTS).
#
#  IMPORTANT : chaque moteur est importé LAZILY (à l'intérieur de sa
#  classe). Ainsi, si faster-whisper ou vosk ne sont pas installés sur
#  la machine, le programme démarre quand même et indique quoi installer.
# ============================================================

from __future__ import annotations

import io
import wave

import numpy as np

from winassist.config import Config, get_config


def samples_to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """Convertit un tableau int16 en fichier WAV en mémoire (bytes).

    Nécessaire pour l'API Whisper (qui attend un fichier audio).
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16 bits = 2 octets
        wav.setframerate(sample_rate)
        wav.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()


def audio_to_float32(samples: np.ndarray) -> np.ndarray:
    """Convertit l'int16 micro en flottants [-1, 1] (format Whisper)."""
    return samples.astype(np.float32) / 32768.0


class SpeechRecognizer:
    """Interface commune : les moteurs l'implémentent."""

    def transcribe_audio(self, samples: np.ndarray, sample_rate: int) -> str:
        raise NotImplementedError

    # -- confort : toute la session vocale passe par cette méthode ---
    def transcribe_phrase(self, samples: np.ndarray, sample_rate: int) -> str:
        """Enveloppe sûre : ne lève jamais, renvoie une chaîne vide si vide."""
        if samples is None or samples.size == 0:
            return ""
        try:
            return (self.transcribe_audio(samples, sample_rate) or "").strip()
        except Exception as exc:
            return f"(erreur de transcription : {exc})"


# ------------------------------------------------------------------
#  Moteur 1 : Whisper via API (OpenAI ou compatible)
# ------------------------------------------------------------------
class WhisperAPI_STT(SpeechRecognizer):
    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        from openai import OpenAI

        self._client = OpenAI(
            api_key=self.config.api_key or "local",
            base_url=self.config.api_base_url,
        )

    def transcribe_audio(self, samples: np.ndarray, sample_rate: int) -> str:
        response = self._client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.wav", samples_to_wav_bytes(samples, sample_rate), "audio/wav"),
            language=self.config.stt_language,
        )
        return response.text


# ------------------------------------------------------------------
#  Moteur 2 : Whisper local (faster-whisper)
# ------------------------------------------------------------------
class FasterWhisperSTT(SpeechRecognizer):
    def __init__(self, config: Config | None = None, device: str = "cpu"):
        self.config = config or get_config()
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Le moteur FasterWhisperSTT nécessite : python -m pip install faster-whisper"
            ) from exc
        # Le modèle est téléchargé au premier appel (mise en cache par
        # faster-whisper dans ~/.cache/huggingface). device="cpu" est le
        # plus sûr ; sur GPU on peut passer "cuda".
        self._model = WhisperModel(self.config.stt_model_size, device=device, compute_type="int8")

    def transcribe_audio(self, samples: np.ndarray, sample_rate: int) -> str:
        segments, _ = self._model.transcribe(
            audio_to_float32(samples),
            language=self.config.stt_language or None,
            beam_size=5,
        )
        return " ".join(seg.text for seg in segments).strip()


# ------------------------------------------------------------------
#  Moteur 3 : Vosk local (modèle français, téléchargement manuel)
# ------------------------------------------------------------------
class VoskSTT(SpeechRecognizer):
    def __init__(self, model_path: str, sample_rate: int = 16000, config: Config | None = None):
        self.config = config or get_config()
        try:
            from vosk import KaldiRecognizer, Model
        except ImportError as exc:
            raise RuntimeError(
                "Le moteur VoskSTT nécessite : python -m pip install vosk"
            ) from exc
        self._model = Model(model_path)
        self._recognizer = KaldiRecognizer(self._model, sample_rate)

    def transcribe_audio(self, samples: np.ndarray, sample_rate: int) -> str:
        # Vosk consomme le flux par blocs ; AcceptWaveform retourne True
        # quand un résultat partiel est prêt.
        self._recognizer.AcceptWaveform(samples.tobytes())
        import json

        result = json.loads(self._recognizer.FinalResult())
        return result.get("text", "")


# ------------------------------------------------------------------
#  Fabrique : choisir le moteur selon la configuration
# ------------------------------------------------------------------
def make_stt(config: Config | None = None) -> SpeechRecognizer:
    """Construit le moteur STT adapté à la configuration.

    Règles (WINASSIST_STT_ENGINE) :
      - "auto"        : Whisper API si clé disponible, sinon whisper local,
                        sinon vosk, sinon erreur explicative.
      - "whisper_api" : force l'API.
      - "whisper_local": force faster-whisper.
      - "vosk"        : force vosk (WINASSIST_VOSK_MODEL_PATH requis).
      - "none"        : renvoie None (mode silencieux / texte uniquement).
    """
    config = config or get_config()
    engine = config.stt_engine

    if engine == "none":
        return None

    if engine in ("auto", "whisper_api") and config.api_key:
        return WhisperAPI_STT(config)

    if engine in ("auto", "whisper_local"):
        try:
            return FasterWhisperSTT(config)
        except RuntimeError:
            if engine == "whisper_local":
                raise
            # repli : on tente vosk si disponible

    if engine in ("auto", "vosk"):
        if not config.vosk_model_path:
            if engine == "vosk":
                raise RuntimeError(
                    "WINASSIST_VOSK_MODEL_PATH doit pointer vers le modèle Vosk."
                    " Utilise scripts/download_models.py pour le télécharger."
                )
        else:
            return VoskSTT(config.vosk_model_path, config.audio_sample_rate, config)

    raise RuntimeError(
        "Aucun moteur STT disponible. Installer un modèle puis relancer :\n"
        "  - 'python -m pip install faster-whisper' puis 'python scripts/download_models.py'\n"
        "  - ou fournir WINASSIST_API_KEY pour le Whisper API."
    )
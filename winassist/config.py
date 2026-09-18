# ============================================================
#  WinAssist — configuration centrale
# ============================================================
#  Toute la configuration est lue depuis les variables
#  d'environnement (ou un fichier `.env` placé à la racine).
#
#  Pourquoi des variables d'environnement plutôt que des
#  constantes en dur dans le code ?
#    - changer de mode (mock <-> LLM réel) sans toucher au code ;
#    - ne JAMAIS committer de clé API dans le dépôt (risque de
#      vol si le dépôt est public) ;
#    - permettre des réglages différents selon la machine
#      (ordinateur de dev vs poste de l'utilisateur).
#
#  Le chargement du fichier `.env` se fait manuellement ci-dessous
#  pour ne pas ajouter de dépendance python-dotenv.
# ============================================================

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- Chargement optionnel d'un fichier `.env` -----------------
def _load_dotenv() -> None:
    """Charge les variables de `WINASSIST_DIR/.env` si le fichier existe.

    Format attendu : des lignes `CLE=VALEUR` (une par ligne).
    On ne surcharge jamais une variable déjà définie dans l'environnement
    réel — l'environnement a toujours priorité sur le fichier `.env`.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        # On ignore les lignes vides et les commentaires (# ou ;).
        if not line or line.startswith(("#", ";")):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("\"'")
        os.environ.setdefault(key, value)


_load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    """Lit une variable d'environnement en l'interprétant comme un booléen."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "oui"}


@dataclass(frozen=True)
class Config:
    """Réglages du prototype, tous dérivés de l'environnement.

    Les valeurs par défaut sont choisies pour que le prototype
    fonctionne immédiatement après installation, SANS clé API :
    le mode par défaut est donc "mock" (un moteur de décision local
    à base de règles, voir decision/mock.py).
    """

    # --- Moteur de décision -----------------------------------
    #  "mock"   : règles locales, aucun réseau, pour les tests/démo.
    #  "openai" : API compatible OpenAI (OpenAI, Ollama, LM Studio...).
    llm_mode: str = field(default_factory=lambda: os.environ.get("WINASSIST_LLM_MODE", "mock").strip().lower())
    #  Clé API. Peut rester vide en mode "mock".
    api_key: str = field(default_factory=lambda: os.environ.get("WINASSIST_API_KEY", ""))
    #  URL de base de l'API. Compatible avec tout serveur OpenAI-like.
    api_base_url: str = field(default_factory=lambda: os.environ.get("WINASSIST_API_BASE_URL", "https://api.openai.com/v1"))
    #  Nom du modèle utilisé. En local (Ollama/LM Studio) : ex. "llama3.2".
    model: str = field(default_factory=lambda: os.environ.get("WINASSIST_MODEL", "gpt-4o-mini"))

    # --- Boucle agentique --------------------------------------
    #  Nombre maximal d'itérations avant d'abandonner (anti-boucle infinie).
    max_iterations: int = field(default_factory=lambda: int(os.environ.get("WINASSIST_MAX_ITERATIONS", "12")))
    #  Nombre d'itérations consécutives SANS changement d'écran
    #  autorisé avant de déclarer la boucle "bloquée".
    stagnation_limit: int = field(default_factory=lambda: int(os.environ.get("WINASSIST_STAGNATION_LIMIT", "3")))

    # --- Perception --------------------------------------------
    #  Nombre maximal d'éléments UIA envoyés à l'IA (limite de tokens).
    element_limit: int = field(default_factory=lambda: int(os.environ.get("WINASSIST_ELEMENT_LIMIT", "80")))
    #  Repli vision (point 3) : si l'écran contient moins d'éléments
    #  interactifs NOMÉS que ce seuil, on bascule sur l'analyse d'image
    #  par un modèle multimodal.
    vision_enabled: bool = field(default_factory=lambda: _env_bool("WINASSIST_VISION_FALLBACK", True))
    vision_min_named_elements: int = field(default_factory=lambda: int(os.environ.get("WINASSIST_VISION_MIN_ELEMENTS", "1")))
    #  Modèle utilisé pour la vision (doit être multimodal ; par défaut,
    #  on réutilise le modèle de décision).
    vision_model: str = field(default_factory=lambda: os.environ.get("WINASSIST_VISION_MODEL", ""))
    #  Taille maximale d'image côté vision (en octets) pour limiter le coût.
    vision_max_bytes: int = field(default_factory=lambda: int(os.environ.get("WINASSIST_VISION_MAX_BYTES", "1500000")))

    # --- Sécurité -----------------------------------------------
    #  Sécurité anti-folie de pyautogui : déplacer la souris dans un
    #  coin de l'écran interrompt immédiatement le programme (failsafe).
    pyautogui_failsafe: bool = field(default_factory=lambda: _env_bool("WINASSIST_FAILSAFE", True))
    #  Exiger une confirmation avant une action SENSIBLE (corbeille,
    #  extinction/redémarrage...). Sans confirmer branché, ces actions
    #  sont refusées d'office (règle défensive).
    confirm_sensitive: bool = field(default_factory=lambda: _env_bool("WINASSIST_CONFIRM_SENSITIVE", True))

    # --- Journal (point 5) -----------------------------------------
    #  Écrire le journal JSON Lines de la session (réécoutable à voix haute).
    journal_enabled: bool = field(default_factory=lambda: _env_bool("WINASSIST_JOURNAL", True))
    #  Dossier de stockage des journaux.
    journal_dir: Path = field(default_factory=lambda: Path(os.environ.get("WINASSIST_JOURNAL_DIR", "logs")))

    # --- Retour vocal --------------------------------------------
    #  Active le TTS (pyttsx3). On peut le désactiver pour ne tester
    #  que la partie logique, sans bruit.
    enable_tts: bool = field(default_factory=lambda: _env_bool("WINASSIST_TTS", True))
    #  Moteur TTS : "pyttsx3" (local, défaut) ou "edge" (voix Edge, réseau).
    tts_engine: str = field(default_factory=lambda: os.environ.get("WINASSIST_TTS_ENGINE", "pyttsx3").strip().lower())
    #  Voix utilisée par edge-tts (si tts_engine=edge).
    edge_voice: str = field(default_factory=lambda: os.environ.get("WINASSIST_EDGE_VOICE", "fr-FR-EloiseNeural"))

    # --- Reconnaissance vocale (point 2) ---------------------------
    #  Moteur STT : "auto" (détection), "whisper_api", "whisper_local",
    #  "vosk", "none". En "auto" : API (si clé) -> whisper local -> vosk.
    stt_engine: str = field(default_factory=lambda: os.environ.get("WINASSIST_STT_ENGINE", "auto").strip().lower())
    #  Taille du modèle whisper local (tiny/base/small/medium).
    stt_model_size: str = field(default_factory=lambda: os.environ.get("WINASSIST_STT_MODEL_SIZE", "base"))
    #  Modèle vocale cible (whisper) : fr pour le français.
    stt_language: str = field(default_factory=lambda: os.environ.get("WINASSIST_STT_LANGUAGE", "fr"))
    #  Chemin du modèle Vosk (dossier contenant amodel français).
    vosk_model_path: str = field(default_factory=lambda: os.environ.get("WINASSIST_VOSK_MODEL_PATH", ""))
    #  Format audio commun (Hz). Whisper est entraîné sur du 16 kHz.
    audio_sample_rate: int = field(default_factory=lambda: int(os.environ.get("WINASSIST_AUDIO_SAMPLE_RATE", "16000")))
    #  Seuil RMS de détection de voix (échelle int16, 0-32768).
    vad_threshold: int = field(default_factory=lambda: int(os.environ.get("WINASSIST_VAD_THRESHOLD", "300")))
    #  Durée maximale d'une phrase (sécurité si VAD trop permissif).
    max_phrase_seconds: float = field(default_factory=lambda: float(os.environ.get("WINASSIST_MAX_PHRASE_SECONDS", "10")))

    # --- Mot d'activation (wake word) ------------------------------
    #  "1" : l'assistant n'agit que si on l'appelle d'abord.
    wake_word_enabled: bool = field(default_factory=lambda: _env_bool("WINASSIST_WAKE_WORD", True))
    #  Phrases d'activation (séparées par des virgules).
    wake_phrases: str = field(default_factory=lambda: os.environ.get(
        "WINASSIST_WAKE_PHRASES",
        "ok winassist,hey winassist,bonjour winassist,winassist",
    ))

    @classmethod
    def from_env(cls) -> "Config":
        """Construit la configuration depuis l'environnement (méthode usuelle)."""
        return cls()


# Une instance globale "paresseuse" : elle n'est construite qu'au
# premier accès, et reste ensuite figée pour toute l'exécution.
_config: Config | None = None


def get_config() -> Config:
    """Cache global de la configuration (même config partout dans le code)."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
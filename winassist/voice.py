# ============================================================
#  WinAssist — DÉMARRAGE EN MODE VOCAL (point 2)
# ============================================================
#  Lancement :   python -m winassist.voice
#
#  Ce que ça fait :
#    1. Initialise la TTS (voix locale pyttsx3 ou edge-tts).
#    2. Initialise le STT selon la config (Whisper API / local / Vosk).
#    3. Demarre la session vocale : « OK WinAssist, ouvre le bloc-notes ».
#    4. Répète l'opération jusqu'à « au revoir ».
#
#  Touche de secours en cours d'exécution : ÉCHAP (ESC).
#
#  Exigences :
#    - WINASSIST_STT_ENGINE=auto  + une clé API (Whisper API) ;
#    - OU  pip install faster-whisper (local) ;
#    - OU  un modèle Vosk téléchargé + WINASSIST_VOSK_MODEL_PATH.
#    - Le micro : pip install sounddevice (déjà fait sur ce poste).
# ============================================================

from __future__ import annotations

import sys

from winassist.config import get_config
from winassist.core.loop import AgenticLoop
from winassist.decision import make_decision_provider
from winassist.perception import UIA_Perception
from winassist.actions import ActionExecutor
from winassist.io import make_stt, get_tts
from winassist.io.voice_loop import VoiceSession
from winassist.io.interrupt import KeyboardStopMonitor

# Conteneur partagé : la session vocale y pose la boucle courante,
# et le moniteur clavier (ESC) peut l'arrêter à tout moment.
LOOP_HOLDER: dict = {"loop": None}


def make_loop_factory(config=None):
    """Construit la fabrique de boucle pour la session vocale.

    Chaque commande aura SA boucle fraîche (passe 1 perception/action).
    """

    def factory() -> AgenticLoop:
        config_ = config or get_config()
        return AgenticLoop(
            perception=UIA_Perception(config_),
            decider=make_decision_provider(config_),
            executor=ActionExecutor(),
            max_iterations=config_.max_iterations,
            stagnation_limit=config_.stagnation_limit,
        )

    return factory


def main() -> int:
    config = get_config()

    # -- 1. Init STT -------------------------------------------------
    print("[voice] Initialisation de la reconnaissance vocale...")
    try:
        stt = make_stt(config)
    except RuntimeError as exc:
        print(f"[voice] STT indisponible : {exc}", file=sys.stderr)
        print("[voice] Redémarre en mode CONSOLE (texte) : python -m winassist.demo", file=sys.stderr)
        return 1
    if stt is None:
        print("[voice] STT désactivé (WINASSIST_STT_ENGINE=none). Utilise winassist.demo en mode texte.")
        return 1

    # -- 2. Init TTS -------------------------------------------------
    print("[voice] Initialisation de la voix...")
    tts = get_tts()

    # -- 3. Session vocale -------------------------------------------
    session = VoiceSession(stt, tts, make_loop_factory(config), config=config,
                           current_loop_holder=LOOP_HOLDER)
    # Arrêt d'urgence clavier (ESC) en fond.
    KeyboardStopMonitor(LOOP_HOLDER).start()

    print("[voice] Lancement de la session. TTS :", type(tts).__name__)
    session.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
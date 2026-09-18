# ============================================================
#  WinAssist — téléchargement des modèles locaux (hors-ligne)
# ============================================================
#  Usage :
#    python scripts/download_models.py              # tout (whisper + vosk)
#    python scripts/download_models.py --whisper base
#    python scripts/download_models.py --vosk
#
#  - Whisper : via faster-whisper (le modèle part dans le cache
#    HuggingFace standard de la machine). Nécessite d'abord :
#        python -m pip install faster-whisper
#  - Vosk    : téléchargement du modèle français SMALL (≈42 Mo) depuis
#    le site officiel, extraction dans ./models/vosk-small-fr.
#    Évite ensuite dans le .env :
#        WINASSIST_VOSK_MODEL_PATH=models/vosk-small-fr
# ============================================================

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

# Modèle Vosk français officiel (léger, idéal comme repli hors-ligne).
VOSK_FR_SMALL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip"


def download_vosk(target: Path = MODELS_DIR / "vosk-small-fr") -> Path:
    """Télécharge et décompresse le modèle Vosk français (42 Mo env.)."""
    if target.exists() and any(target.iterdir()):
        print(f"[vosk] Modèle déjà présent : {target}")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    zip_path = target.parent / "vosk-small-fr.zip"
    print(f"[vosk] Téléchargement de {VOSK_FR_SMALL_URL} ...")

    def _progress(block_num: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            done = block_num * block_size * 100 // total_size
            sys.stdout.write(f"\r  {done:3d}%")
            sys.stdout.flush()

    urllib.request.urlretrieve(VOSK_FR_SMALL_URL, zip_path, reporthook=_progress)
    print()

    print(f"[vosk] Extraction vers {target} ...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target.parent)
    zip_path.unlink(missing_ok=True)

    # Le zip contient un dossier avec un nom de version ; on le normalise.
    for child in target.parent.iterdir():
        if child.is_dir() and child.name.startswith("vosk-model-small-fr"):
            if child != target:
                if target.exists():
                    target.rmdir()
                child.rename(target)
    print(f"[vosk] Terminé. Modèle : {target}")
    return target


def download_whisper(size: str = "base") -> None:
    """Lance le téléchargement du modèle Whisper via faster-whisper."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "Impossible d'utiliser faster-whisper. Lance d'abord :\n"
            "  python -m pip install faster-whisper"
        ) from exc

    print(f"[whisper] Téléchargement du modèle '{size}' (cache HuggingFace)...")
    WhisperModel(size, device="cpu", compute_type="int8")
    print(f"[whisper] Modèle '{size}' prêt à l'emploi.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Télécharge les modèles STT locaux.")
    parser.add_argument("--whisper", nargs="?", const="base", metavar="SIZE",
                        help="Télécharge Whisper (tiny/base/small/medium).")
    parser.add_argument("--vosk", action="store_true", help="Télécharge le modèle Vosk français.")
    args = parser.parse_args()

    if not (args.whisper or args.vosk):
        args.vosk = True
        args.whisper = args.whisper or "base"
        print("[main] Aucune option : téléchargement de Vosk + Whisper.")

    if args.whisper:
        download_whisper(args.whisper)
    if args.vosk:
        path = download_vosk()
        print(f"\n[main] Pour l'utiliser, ajoute dans .env :\n  WINASSIST_VOSK_MODEL_PATH={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
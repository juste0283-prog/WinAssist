# ============================================================
#  WinAssist — journal de session (POINT 5)
# ============================================================
#  Chaque session écrit un journal horodaté (JSON Lines) de tout ce que
#  l'assistant a vu, décidé et fait. Deux usages :
#   1. traces de diagnostic (un bug se rejoue au coup par coup) ;
#   2. journal "écoutable" : relecture de la session à voix haute pour
#      un utilisateur aveugle (« lit le journal »).
#
#  Format : une ligne JSON par événement, encodée en UTF-8.
# ============================================================

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional

from winassist.config import get_config


class Journal:
    """Journalise une session dans un fichier JSON Lines append-only."""

    def __init__(self, path: Optional[Path] = None, enabled: bool = True) -> None:
        self.enabled = enabled
        self.path: Optional[Path] = None
        self._fh = None
        if enabled:
            config = get_config()
            path = path or (config.journal_dir / f"session_{time.strftime('%Y%m%d_%H%M%S')}.log")
            path.parent.mkdir(parents=True, exist_ok=True)
            self.path = path
            self._fh = open(path, "a", encoding="utf-8")

    def record(self, kind: str, message: str, **extra) -> None:
        """Écrit un événement : kind (commande, etape, resultat...), message."""
        if not self.enabled or self._fh is None:
            return
        entry: dict = {
            "time": time.strftime("%H:%M:%S"),
            "kind": kind,
            "message": message,
        }
        entry.update(extra)
        self._fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    # ------------------------------------------------------------------
    #  Relecture ("journal écoutable")
    # ------------------------------------------------------------------
    @staticmethod
    def replay(path: Path, say: Callable[[str], None], limit: Optional[int] = None) -> list[str]:
        """Lit le journal et fait « dire » chaque ligne (TTS / console).

        Renvoie les lignes lues (les `limit` dernières si précisées).
        """
        lines: list[str] = []
        if not path.exists():
            say("Journal introuvable.")
            return []
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                lines.append(f"{entry.get('time', '??')} — {entry.get('message', '')}")
        if limit is not None:
            lines = lines[-limit:]
        for line in lines:
            say(line)
        return lines


__all__ = ["Journal"]
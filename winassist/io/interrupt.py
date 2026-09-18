# ============================================================
#  WinAssist — interruption matérielle de secours
# ============================================================
#  Même si la reconnaissance vocale fonctionne, l'utilisateur doit
#  pouvoir arrêter une tâche en un geste fiable : ici, la touche
#  ÉCHAP (ESC) du clavier, captée via msvcrt (console Windows).
#
#  Le thread surveille la console ; s'il voit ESC, il demande l'arrêt
#  à la BOUCLE COURANTE (visible via un simple dict partagé, rempli
#  par la session vocale / la démo).
# ============================================================

from __future__ import annotations

import threading


class KeyboardStopMonitor(threading.Thread):
    """Arrête la boucle courante quand l'utilisateur appuie sur ESC."""

    def __init__(self, loop_holder: dict, key: str = "\x1b"):
        super().__init__(daemon=True, name="keyboard-stop")
        self.loop_holder = loop_holder  # {"loop": AgenticLoop | None}
        self.key = key

    def run(self) -> None:
        import msvcrt  # accès clavier console, Windows seulement

        while True:
            if msvcrt.kbhit():
                if msvcrt.getch() in (self.key.encode(), b"\x00" + self.key.encode()):
                    loop = self.loop_holder.get("loop")
                    if loop is not None:
                        loop.cancel(reason="Interrompu par la touche Échap.")
            threading.Event().wait(0.05)  # petite pause pour ne pas surcharger le CPU
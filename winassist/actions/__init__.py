"""Paquet `actions` : exécution physique des actions décidées par l'IA.

- executor.py    : déplace la souris, tape au clavier, etc. (pyautogui).
- quick_actions.py : raccourcis système directs (ouvrir une app...).
"""

from winassist.actions.executor import ActionExecutor

__all__ = ["ActionExecutor"]
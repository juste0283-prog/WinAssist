"""WinAssist — assistant vocal agentique pour Windows.

Ce paquet implémente un prototype du cœur du système :

    perception (UIA)  ->  décision (IA/mock)  ->  action (pyautogui)

La boucle est la suivante (voir `core/loop.py`) :
  1. On "regarde" l'écran : on extrait l'arbre UI Automation de la fenêtre active.
  2. On demande au modèle de choisir UNE seule action à exécuter,
     en lui fournissant l'état de l'écran et l'historique des actions.
  3. On exécute l'action, puis on recommence, jusqu'à ce que le modèle
     décide que la tâche est terminée.

Le module est volontairement découpé en 4 paquets à responsabilité unique :
  - winassist.perception : "voir" l'écran (UIA, puis vision en point 3).
  - winassist.decision    : "réfléchir" (choisir l'action suivante).
  - winassist.actions     : "agir" (exécuter physiquement l'action).
  - winassist.core        : "orchestrer" (la boucle, l'historique, la sécurité).
"""

__version__ = "0.1.0"
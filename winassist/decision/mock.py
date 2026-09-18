# ============================================================
#  WinAssist — moteur de décision MOCK (testable localement)
# ============================================================
#  Un "faux cerveau" à base de règles simples. Il ne comprend qu'un
#  petit vocabulaire français, mais il suffit à :
#    - démontrer la boucle perception -> décision -> action de bout
#      en bout, sans clé API, sans réseau ;
#    - fournir une base de tests déterministes (les règles ne changent
#      jamais) ;
#    - vérifier que toute la tuyauterie (résolution, exécution, journal)
#      fonctionne avant de brancher le vrai LLM.
#
#  Règles implémentées (dans l'ordre de priorité) :
#    1. "ouvre X"  -> OpenApp(X), puis Done dès que la fenêtre convient.
#    2. "tape T"   -> TypeText(T) une fois, puis Done.
#    3. "valide"   -> PressEnter une fois, puis Done.
#    4. "clique sur <libellé>" -> Click sur l'élément correspondant
#        (repli sur Ask si introuvable ; Done après un clic réussi).
#    5. "défile"   -> Scroll une fois, puis Done.
#    6. sinon      -> Ask (demande de précision), repli sûr.
#
#  Remarque : un vrai LLM déciderait de "terminer" naturellement (action
#  `done`) à chaque étape. Ici on simule ce raisonnement grâce à des
#  repères simples (la fenêtre a changé, l'action a déjà été envoyée...).
# ============================================================

from __future__ import annotations

import re

from winassist.actions.quick_actions import KNOWN_APPS
from winassist.core.models import Action, Ask, Click, Done, OpenApp, PressEnter, Scroll, TypeText
from winassist.decision.base import DecisionContext, DecisionProvider

# ------------------------------------------------------------------
#  Vocabulaire de commandes (entrées multiples = variations naturelles)
# ------------------------------------------------------------------
OPEN_VERBS = ["ouvre", "ouvrir", "ouvre-moi", "lance", "lancer", "démarre", "démarrer", "launch", "open"]
TYPE_VERBS = ["tape", "écris", "type", "saisis", "écrire", "taper"]
SCROLL_WORDS = {
    "défile": "down", "déroule": "down", "descend": "down", "vers le bas": "down",
    "remonte": "up", "vers le haut": "up", "monte": "up",
}


class MockDecisionProvider(DecisionProvider):
    """Cerveau de démonstration : règles locales, déterministes."""

    def __init__(self) -> None:
        # Noms d'apps connus triés par longueur décroissante : le plus
        # spécifique l'emporte lors de la recherche dans la commande.
        self._known_keys = sorted(KNOWN_APPS.keys(), key=len, reverse=True)
        # État interne de la session : on évite de rejouer une action déjà
        # envoyée pour la même commande (sinon la boucle "répète sans
        # progression" et s'arrête sèchement).
        self._sent: set[tuple[str, str]] = set()   # (commande, type d'action)
        self._last_click_element: int | None = None

    def decide(self, ctx: DecisionContext) -> Action:
        cmd = ctx.command.strip().lower()

        # -- 1) ouverture d'application --------------------------------
        for verb in OPEN_VERBS:
            if verb in cmd:
                app = self._find_app_name(cmd)
                if app:
                    # Déjà lancée ET la fenêtre correspond ? -> terminé.
                    if self._foreground_matches(ctx.state, app):
                        return Done(summary=f"L'application '{app}' est ouverte.")
                    if (cmd, "open_app") in self._sent:
                        return Done(summary=f"L'application '{app}' a été lancée.")
                    self._sent.add((cmd, "open_app"))
                    return OpenApp(app_name=app)
                return Ask(question=f"Quelle application veux-tu que je lance ? (exemple : {self._suggest_apps()})")

        # -- 2) saisie de texte ----------------------------------------
        for verb in TYPE_VERBS:
            if verb in cmd:
                text = self._extract_text(cmd, verb)
                if not text:
                    return Ask(question="Que dois-je écrire ?")
                if (cmd, "type_text") in self._sent:
                    return Done(summary="Texte saisi.")
                self._sent.add((cmd, "type_text"))
                return TypeText(text=text)

        # -- 3) touche Entrée / validation ------------------------------
        if any(w in cmd for w in ["valide", "entrée", "enter", "envoie le message"]):
            if (cmd, "press_enter") in self._sent:
                return Done(summary="Validation envoyée.")
            self._sent.add((cmd, "press_enter"))
            return PressEnter()

        # -- 4) clic sur un élément -------------------------------------
        if "clique" in cmd or "appuie" in cmd or "touche sur" in cmd:
            target = self._find_target_label(cmd)
            if not target:
                return Ask(question="Sur quoi dois-je cliquer ?")
            el = self._find_element(ctx.state, target)
            if el is None:
                return Ask(question=f"Je ne vois pas d'élément « {target} » à l'écran.")
            if el.id == self._last_click_element:
                return Done(summary=f"Clic effectué sur « {el.name} ».")
            self._last_click_element = el.id
            return Click(element_id=el.id)

        # -- 5) défilement ----------------------------------------------
        for word, direction in SCROLL_WORDS.items():
            if word in cmd:
                if (cmd, "scroll") in self._sent:
                    return Done(summary="Défilement effectué.")
                self._sent.add((cmd, "scroll"))
                return Scroll(direction=direction)

        # -- 6) commande non reconnue -> demande de précision -----------
        return Ask(question="Je n'ai pas compris la commande. Essaie par exemple « ouvre le bloc-notes ».")

    # ------------------------------------------------------------------
    #  Helpers de reconnaissance
    # ------------------------------------------------------------------
    def _find_app_name(self, cmd: str) -> str | None:
        """Trouve quelle app est mentionnée dans la commande.

        On cherche la plus longue clé connue présente dans le texte
        (ex. « ouvre le gestionnaire des tâches » -> "gestionnaire des tâches").
        """
        compact = cmd.replace(" ", "")
        for key in self._known_keys:
            if key.replace(" ", "") and key.replace(" ", "") in compact:
                return key
        return None

    def _extract_text(self, cmd: str, verb: str) -> str:
        """Récupère ce qui doit être saisi après le verbe."""
        _, _, text = cmd.partition(verb)
        text = re.sub(r"^(dans|du|de la|le|la)\s+", "", text.strip())
        return text

    def _find_target_label(self, cmd: str) -> str | None:
        """Extrait le libellé sur lequel cliquer (ex. « clique sur Envoyer »)."""
        match = re.search(r"(?:sur|sur le bouton|le bouton)\s+(.+)", cmd)
        if not match:
            return None
        label = match.group(1).strip().strip("?.")
        label = re.sub(r"^(bouton\s+|le\s+|la\s+|les\s+)+", "", label).strip()
        return label.lower()

    @staticmethod
    def _find_element(state, label: str):
        """Retrouve l'élément dont le nom correspond à `label`.

        Scoring simple : correspondance exacte > correspondance partielle,
        bonus pour les types maniables (bouton > champ de texte > menu),
        pénalité si l'élément est désactivé.
        """
        label = label.lower()
        best, best_score = None, -1
        for el in state.elements:
            name = el.name.lower()
            if label in name or name in label:
                score = 10 if name == label else 0
                score += {"Button": 5, "Edit": 4, "MenuItem": 3, "ListItem": 3,
                          "Hyperlink": 3}.get(el.control_type, 0)
                if not el.enabled:
                    score -= 20
                if score > best_score:
                    best, best_score = el, score
        return best

    @staticmethod
    def _foreground_matches(state, app: str) -> bool:
        """La fenêtre au premier plan correspond-elle à l'app demandée ?

        On vérifie que des mots-clés du nom de l'app (ou de son exécutable)
        apparaissent dans le titre de la fenêtre, avec normalisation des
        accents : « Bloc-notes » contient bien « bloc-notes ».
        """
        title = _normalize(state.foreground_window)
        words = set(_normalize(app).split())
        exe = _normalize(KNOWN_APPS.get(app, "")).replace(".exe", "")
        if exe:
            words.add(exe)
            words.update(exe.split())
        return any(len(w) >= 4 and w in title for w in words)

    def _suggest_apps(self) -> str:
        """Liste les apps connues pour aider l'utilisateur dans la question."""
        return ", ".join(sorted(set(k for k in KNOWN_APPS)))


# ------------------------------------------------------------------
#  Normalisation de texte (minuscules + sans accents)
# ------------------------------------------------------------------
def _normalize(text: str) -> str:
    accents = {
        "à": "a", "â": "a", "ä": "a", "ã": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o", "õ": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c", "œ": "oe", "æ": "ae",
    }
    return "".join(accents.get(ch, ch) for ch in text.lower())
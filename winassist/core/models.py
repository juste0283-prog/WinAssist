# ============================================================
#  WinAssist — modèles de données du cœur du système
# ============================================================
#  Trois familles de modèles (Pydantic, pour une validation stricte
#  et une sérialisation JSON fiable) :
#
#   1. UIElement / ScreenState  : ce que l'assistant "voit".
#   2. Action et ses variantes  : ce que l'assistant décide de faire.
#   3. Helpers de sérialisation : le format texte compact envoyé à l'IA.
#
#  Ces modèles sont le contrat entre les 4 paquets. Tous les messages
#  qui transitent (perception -> décision -> action) passent par ces
#  structures, ce qui rend le prototypage et les tests très simples :
#  on peut construire un ScreenState à la main dans un test sans
#  toucher à l'écran.
# ============================================================

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter


# ------------------------------------------------------------
#  1) Perception : description d'un élément d'interface
# ------------------------------------------------------------

# Types de contrôles "manipulables" : ce sont les éléments sur lesquels
# l'utilisateur peut cliquer/taper. On les priorise lors de l'extraction.
INTERACTIVE_TYPES = {
    "Button", "Edit", "CheckBox", "RadioButton", "ComboBox",
    "Hyperlink", "ListItem", "TabItem", "MenuItem", "TreeItem",
    "Slider", "Spinner", "DataItem",
}

# Types "décoratifs" sans intérêt pour l'agent (jamais envoyés).
IGNORED_TYPES = {"Pane", "Group", "ScrollBar", "Separator", "ToolBar", "StatusBar"}


class UIElement(BaseModel):
    """Une abstraction portable d'un élément UI extrait via UIA.

    On ne garde que ce qui est utile à la décision, pas tout ce que
    Windows expose : le but est de fabriquer un JSON compact et lisible
    pour le modèle de langage, sans noyer l'IA dans le bruit.
    """

    # index stable dans la liste d'une capture (les coordonnées données
    # au modèle se réfèrent à cet index — voir le champ `element_id` des actions).
    id: int
    # type de contrôle Windows (Button, Edit, CheckBox...).
    control_type: str
    # libellé accessible (le texte que voit un lecteur d'écran).
    name: str
    # identifiant technique (parfois vide). Utile pour les tests.
    automation_id: Optional[str] = None
    # rectangle de l'élément EN COORDONNÉES ÉCRAN (origine = coin haut-gauche
    # de l'écran principal, comme pyautogui).
    x: int
    y: int
    w: int
    h: int
    # un élément grisé n'est pas cliquable : le modèle ne doit pas essayer.
    enabled: bool = True

    @property
    def center(self) -> tuple[int, int]:
        """Centre du rectangle — c'est là que l'on va cliquer."""
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def is_visible(self) -> bool:
        """Un élément hors écran ou de taille nulle ne sert à rien."""
        return self.w > 0 and self.h > 0

    def summary(self) -> str:
        """Représentation sur une ligne, pour le prompt envoyé à l'IA.

        Exemple :  `#12 Button 'Envoyer' @ (720,430)`
        """
        coord = self.center
        vis = "" if self.enabled else " (désactivé)"
        return f"#{self.id} {self.control_type} '{self.name}' @({coord[0]},{coord[1]}){vis}"


class ScreenState(BaseModel):
    """Une "photo" instantanée de l'interface, à un instant T.

    C'est le contexte principal donné au modèle : chaque itération de la
    boucle produit un nouvel objet ScreenState avant la décision.
    """

    # titre de la fenêtre au premier plan (aucune: fenêtre système).
    foreground_window: str = ""
    # éléments extraits, triés de haut en bas puis de gauche à droite
    # (ordre de lecture naturel pour l'IA et pour un utilisateur).
    elements: list[UIElement] = Field(default_factory=list)

    def summary_lines(self) -> list[str]:
        """Lignes compactes décrivant les éléments (pour le prompt)."""
        return [el.summary() for el in self.elements]

    def signature(self) -> str:
        """Empreinte de l'état, sert à détecter les boucles sans progression.

        On ignore les coordonnées (un déplacement de 1px ne doit pas
        être considéré comme un "changement"). On compare le titre de
        la fenêtre ainsi que types, noms et états des éléments.
        """
        return self.foreground_window + " || " + repr([
            (el.control_type, el.name, el.enabled, str(el.automation_id))
            for el in self.elements
        ])

    def describe_visible(self) -> str:
        """Texte lisible pour un utilisateur qui ne voit pas l'écran
        (utilisé par le retour vocal et les journaux)."""
        if not self.elements:
            return f"Fenêtre '{self.foreground_window}' : aucun élément exploitable."
        parts = [f"Fenêtre '{self.foreground_window}'. "+ "Sur l'écran :"]
        for el in self.elements:
            parts.append(f"- {el.control_type} '{el.name}'")
        return "\n".join(parts)


# ------------------------------------------------------------
#  2) Décision : les actions possibles
# ------------------------------------------------------------
#  Chaque action est un modèle distinct, tous regroupés dans une
#  "union discriminée" (`type` est le champ discriminant). Pydantic
#  choisit automatiquement la bonne classe selon la valeur de `type`.
#
#  Deux conventions importantes :
#   - les actions "espace" (clic, glisser...) référencent un élément
#     de l'écran par son `element_id`, OU des coordonnées brutes x/y.
#     L'opérateur `|` (None) entre les deux : soit un élément est
#     fourni, soit des coordonnées. C'est la résolution de la boucle
#     (core/loop.py) qui tranche.
#   - la boucle n'exécute JAMAIS un plan complet : elle attend UNE
#     action à la fois, observe le résultat, puis redemande une action.


class Click(BaseModel):
    type: Literal["click"] = "click"
    element_id: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None


class DoubleClick(BaseModel):
    type: Literal["double_click"] = "double_click"
    element_id: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None


class RightClick(BaseModel):
    type: Literal["right_click"] = "right_click"
    element_id: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None


class TypeText(BaseModel):
    """Tape du texte dans le champ qui a le focus.

    Remarque : on passe par le presse-papiers (clavier + Ctrl+V) pour
    supporter les accents français — pyautogui.write() échoue sur les
    caractères non-ASCII comme 'é' ou 'à'.
    """
    type: Literal["type_text"] = "type_text"
    text: str


class PressKeys(BaseModel):
    """Envoie des raccourcis clavier, ex. keys=["ctrl", "s"].

    On fournit le raccourci comme UNE action même s'il contient
    plusieurs touches : bien plus fiable que de demander à l'IA de
    composer le raccourci touche par touche.
    """
    type: Literal["press_keys"] = "press_keys"
    keys: list[str] = Field(default_factory=list)


class Scroll(BaseModel):
    type: Literal["scroll"] = "scroll"
    direction: Literal["up", "down", "left", "right"]


class Drag(BaseModel):
    type: Literal["drag"] = "drag"
    x1: int
    y1: int
    x2: int
    y2: int


class OpenApp(BaseModel):
    """Raccourci système : lance une application par son nom.

    Ce n'est PAS une action sur l'écran (il n'y a pas forcément de
    menu à ouvrir) : on délègue à actions/quick_actions.py qui connaît
    les applications courantes de Windows.
    """
    type: Literal["open_app"] = "open_app"
    app_name: str


class SystemAction(BaseModel):
    """Raccourci système direct, sans passer par les clics (point 4).

    Exemples : monter le volume, verrouiller la session, vider la
    corbeille, changer le fond d'écran, afficher le bureau...
    Le dispatcher actions/quick_actions.py connaît chaque `shortcut` et
    renvoie (succès, message) ; `args` est un paramètre optionnel propre
    au raccourci (ex. la couleur du fond d'écran).
    """
    type: Literal["system"] = "system"
    shortcut: str
    args: str = ""


class PressEnter(BaseModel):
    type: Literal["press_enter"] = "press_enter"


class Done(BaseModel):
    """Signale que la tâche est terminée (avec un petit résumé)."""
    type: Literal["done"] = "done"
    summary: str = ""


class Ask(BaseModel):
    """Demande une clarification : l'IA ne sait pas faire / n'est pas sûre."""
    type: Literal["ask"] = "ask"
    question: str


# Union discriminée : c'est le type unique manipulé par la boucle.
Action = Annotated[
    Union[
        Click, DoubleClick, RightClick,
        TypeText, PressKeys, PressEnter, Scroll, Drag, OpenApp, SystemAction,
        Done, Ask,
    ],
    Field(discriminator="type"),
]

# Pydantic ne permet pas d'appeler `.model_validate()` directement sur un
# type `Annotated[Union[...]]` : il faut passer par un TypeAdapter.
# `parse_action()` est donc LE point d'entrée unique pour construire une
# Action à partir d'un dictionnaire (résolution d'un appel de fonction du
# LLM, ou d'un JSON utilisateur).
ActionAdapter: TypeAdapter = TypeAdapter(Action)


def parse_action(data: dict) -> Action:
    """Construit une Action depuis un dict JSON (ex. arguments du LLM).

    Lève une ValidationError si le dict ne correspond à aucune action.
    """
    return ActionAdapter.validate_python(data)

# Actions qui produisent un effet visible / qui "comptent" pour la
# progression de la boucle (une action qui ne change pas l'écran est
# un signe de blocage potentiel).
PROGRESSIVE_ACTIONS = {
    "click", "double_click", "right_click", "type_text",
    "press_keys", "scroll", "drag", "open_app", "system",
}


def describe_action(action: Action) -> str:
    """Description lisible d'une action, pour le journal / le retour vocal."""
    kind = action.type
    if kind == "click":
        return f"clic à ({action.x}, {action.y})"
    if kind == "double_click":
        return f"double-clic à ({action.x}, {action.y})"
    if kind == "right_click":
        return f"clic droit à ({action.x}, {action.y})"
    if kind == "type_text":
        return f"saisie du texte \"{action.text}\""
    if kind == "press_keys":
        return f"touches : {' + '.join(action.keys)}"
    if kind == "press_enter":
        return "touche Entrée"
    if kind == "scroll":
        return f"défilement vers le {action.direction}"
    if kind == "drag":
        return f"glisser de ({action.x1},{action.y1}) vers ({action.x2},{action.y2})"
    if kind == "open_app":
        return f"ouverture de l'application '{action.app_name}'"
    if kind == "system":
        args = f" ({action.args})" if action.args else ""
        return f"raccourci système '{action.shortcut}'{args}"
    if kind == "done":
        return f"tâche terminée : {action.summary}"
    if kind == "ask":
        return f"demande de clarification : {action.question}"
    return kind
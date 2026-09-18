# ============================================================
#  WinAssist — moteur de décision par LLM (compatible OpenAI)
# ============================================================
#  Ce moteur appelle un serveur d'API "compatible OpenAI" avec
#  FUNCTION CALLING. Fonctionne indifféremment avec :
#    - l'API officielle OpenAI (base_url par défaut) ;
#    - un modèle local via Ollama ("http://localhost:11434/v1") ;
#    - LM Studio / vLLM / toute API compatible.
#
#  Principe du function calling :
#    - on décrit à l'API les fonctions disponibles (clic, taper...)
#      au format JSON Schema ;
#    - l'API répond par UNE fonction à appeler avec ses arguments ;
#    - on traduit cet appel en modèle Action (core/models.py) que la
#      boucle exécute.
#
#  L'état de l'écran et l'historique sont injectés dans le prompt :
#    le modèle doit donc "raisonner" sur des données fraîches à chaque
#    itération — c'est exactement la boucle agentique voulue.
# ============================================================

from __future__ import annotations

from openai import OpenAI

from winassist.config import Config, get_config
from winassist.core.models import Action, Ask, Done, parse_action
from winassist.decision.base import DecisionContext, DecisionProvider

# ------------------------------------------------------------------
#  Jeu d'outils déclaré à l'API (équivalent exact des modèles Action)
# ------------------------------------------------------------------
#  Chaque entrée = JSON Schema automatisé par Pydantic via model_json_schema.
#  On les écrit "à la main" pour rester lisibles et pédagogiques.
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Clique une fois à une position donnée. "
                           "Passe element_id pour viser un élément de l'écran, "
                           "ou x et y (pixels écran) si tu préfères une position précise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer", "description": "numéro # de l'élément dans la liste de l'écran"},
                    "x": {"type": "integer", "description": "abscisse en pixels"},
                    "y": {"type": "integer", "description": "ordonnée en pixels"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "double_click",
            "description": "Double-clic sur un élément ou à une position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "right_click",
            "description": "Clic droit (ouvre le menu contextuel).",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Saisit du texte dans le champ qui a le focus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "le texte exact à saisir"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_keys",
            "description": "Envoie un raccourci clavier. Exemple : [\"ctrl\", \"s\"] pour sauvegarder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_enter",
            "description": "Appuie sur la touche Entrée (valider un formulaire, envoyer un message...).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Fait défiler le contenu dans une direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drag",
            "description": "Glisser-déposer d'une position à une autre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x1": {"type": "integer"}, "y1": {"type": "integer"},
                    "x2": {"type": "integer"}, "y2": {"type": "integer"},
                },
                "required": ["x1", "y1", "x2", "y2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Lance une application de Windows par son nom (ex. \"bloc-notes\", \"whatsapp\").",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string"},
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "À appeler quand la tâche demandée est COMPLÈTE. Résume ce qui a été fait.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "résumé des actions effectuées"},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask",
            "description": "À appeler si tu es bloqué ou si la commande est ambiguë : pose une question à l'utilisateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                },
                "required": ["question"],
            },
        },
    },
]

# Prompt système : le "personnage" de l'assistant.
_SYSTEM_PROMPT = """Tu es WinAssist, le cerveau d'un assistant qui pilote un PC Windows \
par la voix au profit surtout d'utilisateurs en situation de handicap.

RÈGLES ABSOLUES :
1. Tu ne reçois que l'écran courant (liste d'éléments UIA) + l'historique.
2. Tu DOIS renvoyer EXACTEMENT UNE action à la fois pour progresser vers le but.
3. Privilégie element_id pour viser un élément ; sinon fournis x et y.
4. Ne répète jamais une action identique qui n'a rien changé.
5. Quand le but demandé par l'utilisateur est atteint, appelle `done`.
6. Si tu es bloqué après plusieurs essais ou si la demande est ambiguë,
   appelle `ask` avec une question claire en français.
7. Ne fais JAMAIS de supposition destructrice : en cas de doute, `ask`.
"""

# Noms d'action attendus côté modèle de données (1:1 avec TOOLS).
_TOOL_TO_TYPE = {
    "double_click": "double_click",
    "right_click": "right_click",
    "type_text": "type_text",
    "press_keys": "press_keys",
    "press_enter": "press_enter",
    "scroll": "scroll",
    "drag": "drag",
    "open_app": "open_app",
    "done": "done",
    "ask": "ask",
    "click": "click",
}


def _build_user_prompt(ctx: DecisionContext) -> str:
    """Compose le prompt utilisateur : commande + écran + historique.

    Le format est volontairement compact (~1 ligne par élément) pour
    limiter les tokens : un écran de bureau peut contenir des centaines
    d'éléments, la liste est tronquée côté perception.
    """
    lines = [f"# Commande de l'utilisateur :\n{ctx.command}", ""]
    lines.append("# État courant de l'écran (numérote tes cibles comme #N) :")
    lines.append(f"Fenêtre au premier plan : {ctx.state.foreground_window}")
    if ctx.state.elements:
        lines.extend(f"- {el.summary()}" for el in ctx.state.elements)
    else:
        lines.append("(aucun élément exploitable via UIA)")
    lines.append("")
    lines.append("# Actions déjà exécutées (ne pas refaire à l'identique) :")
    lines.append(ctx.history.to_llm_context(n=6))
    return "\n".join(lines)


class LLMDecisionProvider(DecisionProvider):
    """Moteur de décision basé sur un LLM compatible OpenAI."""

    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        if not self.config.api_key and "localhost" not in self.config.api_base_url:
            raise ValueError(
                "WINASSIST_API_KEY est vide. Fournis une clé, ou pointe "
                "WINASSIST_API_BASE_URL vers un serveur local (Ollama/LM Studio)."
            )
        self._client = OpenAI(api_key=self.config.api_key or "local", base_url=self.config.api_base_url)

    # ------------------------------------------------------------------
    def decide(self, ctx: DecisionContext) -> Action:
        """Appelle le LLM et traduit sa réponse en une Action."""
        try:
            completion = self._client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_prompt(ctx)},
                ],
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.0,
            )
        except Exception as exc:
            raise RuntimeError(f"Appel LLM impossible : {exc}") from exc

        message = completion.choices[0].message

        # -- Cas 1 : l'API demande un appel de fonction ----------------
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            tool_name = tool_call.function.name
            try:
                raw_args = _parse_arguments(tool_call.function.arguments)
            except Exception:
                raw_args = {}
            return self._build_action(tool_name, raw_args)

        # -- Cas 2 : l'API répond sans appel de fonction (texte seul) --
        # On considère qu'il s'agit d'une terminaison de la tâche.
        return Done(summary=message.content or "La tâche demandée est terminée.")

    # ------------------------------------------------------------------
    def _build_action(self, tool_name: str, args: dict) -> Action:
        """Construit l'objet Action depuis un appel de fonction du LLM."""
        action_type = _TOOL_TO_TYPE.get(tool_name)
        if action_type is None:
            return Ask(question=f"Le modèle a demandé un outil inconnu : « {tool_name} ».")

        # La validation Pydantic fera le tri : si les arguments sont
        # mal formés, on renvoie une demande de correction plutôt que
        # d'écraser le programme.
        try:
            return parse_action({"type": action_type, **args})
        except Exception as exc:
            return Ask(question=f"Arguments d'action invalides ({action_type}) : {exc}. Recommence proprement.")


def _parse_arguments(raw: str) -> dict:
    """Parse le JSON d'arguments renvoyé par l'API (avec filet de sécurité)."""
    import json

    if not raw or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Certaines implémentations locales renvoient du texte brut
        # (vision) : on ignore et on laissera l'action être incomplète.
        return {}
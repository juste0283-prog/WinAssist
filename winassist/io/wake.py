# ============================================================
#  WinAssist — mot d'activation ("wake word")
# ============================================================
#  L'assistant n'écoute PAS en permanence : il attend qu'on l'appelle
#  par une phrase ("OK WinAssist", "Hey WinAssist"...), ce qui évite :
#    - de transcrire et d'analyser toute la vie de la pièce (coût) ;
#    - d'exécuter une commande entendue "par hasard" (sécurité).
#
#  Tout est ici des FONCTIONS PURES sur du texte : le STT fait le plus
#  dur (transforme le son en texte), puis `detect_wake` décide. Aucune
#  dépendance matérielle : pleinement testable sans micro.
# ============================================================

from __future__ import annotations

import re
from difflib import SequenceMatcher

# Accents -> lettres simples (pour comparer "Bonià" et "bonjour").
# NB : maketrans mappe 1 caractère -> 1 caractère : œ et æ sont donc
# traités séparément en remplacement (chaînes multi-caractères).
_SINGLE = str.maketrans(
    "àâäéèêëîïôöùûüç",
    "aaaeeeeiioouuuc",
)


def normalize(text: str) -> str:
    """Minuscules, sans accents, sans ponctuation ni espaces doubles."""
    if not text:
        return ""
    low = text.lower()
    low = low.translate(_SINGLE)
    low = low.replace("œ", "oe").replace("æ", "ae")
    low = re.sub(r"[^a-z0-9 ]+", " ", low)
    return re.sub(r"\s+", " ", low).strip()


def parse_phrases(raw: str) -> list[str]:
    """Transforme une config de phrases (séparées par des virgules) en liste."""
    return [normalize(p) for p in raw.split(",") if normalize(p)]


# ------------------------------------------------------------------
#  Correspondance tolérante du wake (STT bruité)
# ------------------------------------------------------------------
def _tolerant_wake_len(n: str, phrase: str) -> int | None:
    """Taille (en mots) du wake en tête de phrase, malgré des coquilles STT.

    Critères :
      - le PREMIER mot transcrit doit être le premier mot du wake
        (l'assistant doit être appelé en tête, pas au milieu d'une phrase) ;
      - on tolère jusqu'à 2 mots parasites entre les mots du wake ;
      - la tête candidate doit ressembler à la phrase d'activation
        (ratio difflib >= 0.62). On garde la fenêtre MINIMALE qui matche,
        afin de préserver le plus de commande possible.

    Renvoie le nombre de mots du wake (à retirer), ou None. Ne couvre PAS
    les déformations sévères (marque inventée inconnue du modèle STT) :
    pour le modèle Vosk français, on ajoute des variantes connues
    (« assistant »…) aux phrases d'activation, voir config.py.
    """
    p = phrase.split()
    t = n.split()
    if not p or not t or t[0] != p[0]:
        return None
    max_k = min(len(t), len(p) + 2)
    for k in range(len(p), max_k + 1):
        candidate = " ".join(t[:k])
        if SequenceMatcher(None, phrase, candidate).ratio() >= 0.62:
            return k
    return None


def detect_wake(text: str, phrases: list[str]) -> bool:
    """La phrase entendue commence-t-elle par un mot d'activation ?

    On exige le wake en DÉBUT de phrase ("ok winassist ouvre le bloc-notes")
    plutôt qu'à la fin : c'est LE format naturel d'une commande. Une
    commande DOIT suivre le wake (un wake seul ne déclenche rien).
    """
    n = normalize(text)
    for phrase in phrases:
        if n == phrase:  # uniquement le mot d'activation -> pas de commande
            return False
        if n.startswith(phrase + " "):
            return True
        head = _tolerant_wake_len(n, phrase)
        if head is not None and head < len(n.split()):
            return True
    return False


def strip_wake(text: str, phrases: list[str]) -> str:
    """Retire le mot d'activation du début, rend la commande restante.

    Ex. : "OK WinAssist ouvre le bloc-notes" -> "ouvre le bloc-notes"
    Gère aussi la correspondance tolérante (coquilles STT).
    """
    n = normalize(text)
    for phrase in phrases:
        if n == phrase:
            return ""
        if n.startswith(phrase + " "):
            stem_len = len(phrase) + 1  # le wake + l'espace qui le suit
            return _recover_original(text, stem_len)
        head = _tolerant_wake_len(n, phrase)
        if head is not None and head < len(n.split()):
            # On retire les `head` premiers mots de la phrase ORIGINALE.
            return _drop_first_words(text, head)
    return text


def _drop_first_words(original: str, n_words: int) -> str:
    words = original.split()
    return " ".join(words[n_words:])


def _recover_original(original: str, stem_norm_len: int) -> str:
    """Renvoie la fin ORIGINALE (casse/accents conservés) d'un texte dont la
    tête normalisée mesure `stem_norm_len` caractères.

    On découpe le texte d'origine mot à mot en vérifiant la longueur
    normalisée cumulée : dès qu'un mot dépasse la limite du "stem", c'est
    que la commande commence à ce mot.
    """
    words = original.split()
    acc = ""
    for i, w in enumerate(words):
        candidate = f"{acc} {w}" if acc else w
        if len(normalize(candidate)) > stem_norm_len:
            return " ".join(words[i:])
        acc = candidate
    return ""
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


def detect_wake(text: str, phrases: list[str]) -> bool:
    """La phrase entendue commence-t-elle par un mot d'activation ?

    On exige le wake en DÉBUT de phrase ("ok winassist ouvre le bloc-notes")
    plutôt qu'à la fin : c'est LE format naturel d'une commande.
    """
    n = normalize(text)
    for phrase in phrases:
        if n == phrase:  # uniquement le mot d'activation -> pas de commande
            return False
        if n.startswith(phrase + " "):
            return True
    return False


def strip_wake(text: str, phrases: list[str]) -> str:
    """Retire le mot d'activation du début, rend la commande restante.

    Ex. : "OK WinAssist ouvre le bloc-notes" -> "ouvre le bloc-notes"
    """
    n = normalize(text)
    for phrase in phrases:
        if n == phrase:
            return ""
        if n.startswith(phrase + " "):
            stem_len = len(phrase) + 1  # le wake + l'espace qui le suit
            return _recover_original(text, stem_len)
    return text


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
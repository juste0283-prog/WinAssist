# ============================================================
#  WinAssist — reconnaissance vocale (STT) — POINT 2
# ============================================================
#  ÉTAT : placeholder. La boucle texte->action fonctionne déjà
#  (démo console) ; le branchement de la voix est le point 2.
#
#  Architecture prévue :
#    - transcription continue dans un thread dédié ;
#    - MOTEUR principal : Whisper (API ou local via faster-whisper) ;
#    - REPLI hors-ligne : Vosk (transcription rapide, vocabulaire
#      léger, idéal pour des commandes courtes et un mot d'activation).
#    - mot d'activation ("OK WinAssist"...) pour éviter de tout
#      transcrire en permanence et économiser la batterie.
# ============================================================

from __future__ import annotations


class SpeechRecognizer:
    """Interface STT : sera implémentée au point 2 du développement.

    Le contrat public est volontairement minimal pour que la boucle ne
    dépende pas du moteur choisi (Whisper ou Vosk).
    """

    def listen_for_command(self) -> str:
        """Écoute en continu et renvoie le texte de la commande entendue.

        Cette méthode est bloquante : elle attend l'activation vocale
        (ou la fin d'une phrase) puis renvoie la transcription.
        """
        raise NotImplementedError(
            "La reconnaissance vocale est prévue au point 2 ; "
            "utilisez la démo console (texte) pour le prototype actuel."
        )
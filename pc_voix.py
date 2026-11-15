"""pc_voix.py - Voix de JARVIS, 100 % locale.

- Whisper (faster-whisper) : après que Vosk a repéré « JARVIS », la phrase est retranscrite par Whisper,
  bien meilleur pour les noms étrangers (Godot, Steam, Discord...) et les nombres.
- Piper : voix naturelle à la place de la voix Windows (modèle .onnx dans le dossier « voix »).
Tout est facultatif : sans ces paquets, JARVIS garde Vosk et la voix Windows.
"""
import os
import re
import tempfile
import wave


class Whisper:
    def __init__(self, taille="base"):
        self.taille = taille
        self.modele = None
        self.pret = False
        self.erreur = ""

    def charger(self):
        try:
            from faster_whisper import WhisperModel
            self.modele = WhisperModel(self.taille, device="cpu", compute_type="int8", cpu_threads=2)
            self.pret = True
        except Exception as exc:  # paquet absent, pas de réseau au premier téléchargement...
            self.erreur = str(exc)

    def transcrire(self, pcm16):
        """Texte français d'un enregistrement 16 kHz mono 16 bits (octets)."""
        import numpy as np
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self.modele.transcribe(audio, language="fr", beam_size=1, vad_filter=False,
                                             condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()


def nettoyer_pour_voix(texte, maximum=500):
    """Retire adresses, symboles et émojis qu'une voix lirait mal ; coupe à la fin d'une phrase."""
    texte = re.sub(r"https?://\S+", " ", texte)
    texte = re.sub(r"[*#_`~>|]+", " ", texte)
    texte = re.sub("[\U0001F300-\U0001FAFF\u2600-\u27BF]", " ", texte)
    texte = " ".join(texte.split())
    if len(texte) > maximum:
        coupe = texte[:maximum]
        fin = max(coupe.rfind(". "), coupe.rfind("! "), coupe.rfind("? "))
        texte = coupe[:fin + 1] if fin > 100 else coupe
    return texte


class Piper:
    def __init__(self, fichier_modele):
        self.fichier = fichier_modele
        self.voix = None
        self.pret = False

    def charger(self):
        if not os.path.exists(self.fichier):
            return
        try:
            from piper import PiperVoice
            self.voix = PiperVoice.load(self.fichier)
            self.pret = True
        except Exception:
            self.pret = False

    def dire(self, texte):
        import winsound
        if not texte:
            return
        chemin = os.path.join(tempfile.gettempdir(), "jarvis_voix.wav")
        with wave.open(chemin, "wb") as wav:
            if hasattr(self.voix, "synthesize_wav"):   # piper-tts récent
                self.voix.synthesize_wav(texte, wav)
            else:                                       # piper-tts plus ancien
                self.voix.synthesize(texte, wav)
        winsound.PlaySound(chemin, winsound.SND_FILENAME)

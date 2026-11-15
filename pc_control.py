"""pc_control.py - JARVIS contrôle ton PC Windows : volume, média, capture, verrouillage,
luminosité, dossiers, mode jeu, redémarrage, veille.

traiter(c) renvoie :
  - une phrase à dire (str) quand l'action est faite ou impossible,
  - ("confirm", clé) quand l'action demande une autorisation (voir ACTIONS_CONFIRM),
  - None si la commande ne concerne pas ce module.
"""
import ctypes
import os
import re
import subprocess
from datetime import datetime

import pyautogui

SANS_FENETRE = 0x08000000

# Applications fermées par le « mode jeu » (modifiez cette liste à votre goût).
APPS_MODE_JEU = ["OneDrive.exe", "Teams.exe", "ms-teams.exe", "Skype.exe"]

NOMBRES = {
    "zéro": 0, "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
    "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "vingts": 20,
    "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
}

DOSSIERS = {
    "téléchargements": "Downloads", "telechargements": "Downloads", "downloads": "Downloads",
    "documents": "Documents", "bureau": "Desktop", "images": "Pictures", "photos": "Pictures",
    "musique": "Music", "vidéos": "Videos", "videos": "Videos",
}
MOTIF_DOSSIER = re.compile(r"^ouvre(?: moi)? (?:le dossier |mon dossier |mes |le |la )?([\wéèê]+)$")


def nombre_dans(texte):
    """Extrait un nombre (chiffres ou mots français, ex. « soixante dix ») ; None s'il n'y en a pas."""
    m = re.search(r"\d+", texte)
    if m:
        return int(m.group())
    t = re.sub(r"\b(pour cents?|pourcents?|pourcentage)\b", " ", texte.replace("-", " "))
    jetons = [j for j in t.split() if j != "et"]
    total, trouve, i = 0, False, 0
    while i < len(jetons):
        j = jetons[i]
        if j == "quatre" and i + 1 < len(jetons) and jetons[i + 1] in ("vingt", "vingts"):
            total, trouve, i = total + 80, True, i + 2
            continue
        if j in ("cent", "cents"):
            total, trouve = (100 if not total else total * 100), True
        elif j in NOMBRES:
            total, trouve = total + NOMBRES[j], True
        i += 1
    return min(total, 100) if trouve else None


def _dossier(nom):
    base = DOSSIERS[nom]
    home = os.path.expanduser("~")
    for racine in (home, os.path.join(home, "OneDrive")):
        chemin = os.path.join(racine, base)
        if os.path.isdir(chemin):
            return chemin
    return None


def regler_volume(n):
    n = max(0, min(100, n))
    pyautogui.press("volumedown", presses=50, interval=0)
    pyautogui.press("volumeup", presses=round(n / 2), interval=0)


def regler_luminosite(n):
    n = max(0, min(100, n))
    cmd = ("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
           f".WmiSetBrightness(1,{n})")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                       text=True, timeout=15, creationflags=SANS_FENETRE)
    return r.returncode == 0


def capture_ecran():
    dossier = os.path.join(os.path.expanduser("~"), "Pictures", "JARVIS")
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, datetime.now().strftime("capture_%Y%m%d_%H%M%S.png"))
    pyautogui.screenshot(chemin)
    return chemin


def activer_mode_jeu():
    subprocess.run(["powercfg", "/setactive", "SCHEME_MIN"], capture_output=True,
                   creationflags=SANS_FENETRE)
    for app in APPS_MODE_JEU:
        subprocess.run(["taskkill", "/IM", app, "/F"], capture_output=True,
                       creationflags=SANS_FENETRE)


def desactiver_mode_jeu():
    subprocess.run(["powercfg", "/setactive", "SCHEME_BALANCED"], capture_output=True,
                   creationflags=SANS_FENETRE)


ACTIONS_CONFIRM = {
    "mode_jeu": ("activer le mode jeu (performances maximales, fermeture de OneDrive et Teams)",
                 activer_mode_jeu),
    "redemarrage": ("redémarrer le PC dans 30 secondes",
                    lambda: subprocess.Popen(["shutdown", "/r", "/t", "30"])),
    "veille_pc": ("mettre le PC en veille",
                  lambda: subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])),
}


def _volume(c):
    reste = c.split("volume", 1)[1]
    if any(k in c for k in ("maximum", "à fond", "a fond")):
        regler_volume(100)
        return "Volume au maximum."
    if "minimum" in c:
        regler_volume(0)
        return "Volume au minimum."
    n = nombre_dans(reste)
    absolu = re.search(r"\b(à|a|au)\b", reste) is not None
    monte = any(k in c for k in ("monte", "augmente", "plus fort", "plus haut"))
    baisse = any(k in c for k in ("baisse", "diminue", "moins fort", "plus bas"))
    if n is not None and (absolu or not (monte or baisse)):
        regler_volume(n)
        return f"Volume réglé à {max(0, min(100, n))} pour cent."
    if monte or baisse:
        pas = round((n if n is not None else 10) / 2)
        pyautogui.press("volumeup" if monte else "volumedown", presses=max(1, pas), interval=0)
        return "Volume augmenté." if monte else "Volume baissé."
    return None


def traiter(c):
    c = c.lower().strip()

    # Dossiers : « ouvre mes téléchargements », « ouvre le dossier bureau »...
    m = MOTIF_DOSSIER.match(c)
    if m and m.group(1) in DOSSIERS:
        chemin = _dossier(m.group(1))
        if not chemin:
            return "Je ne trouve pas ce dossier, Salim."
        os.startfile(chemin)
        return "J'ouvre " + m.group(1) + ", Salim."

    # Mode jeu
    if "mode jeu" in c:
        if any(k in c for k in ("fin du", "désactive", "desactive", "arrête", "arrete", "quitte")):
            desactiver_mode_jeu()
            return "Mode jeu désactivé, retour au mode équilibré."
        return ("confirm", "mode_jeu")
    if "mode normal" in c:
        desactiver_mode_jeu()
        return "Retour au mode équilibré."

    # Extinction annulée / redémarrage / veille du PC
    if any(k in c for k in ("annule l'extinction", "annule l'arrêt", "annule l'arret",
                            "annule le redémarrage", "annule le redemarrage")):
        r = subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=SANS_FENETRE)
        return "Extinction annulée, Salim." if r.returncode == 0 else "Il n'y avait rien à annuler."
    if any(k in c for k in ("redémarre le pc", "redémarre l'ordinateur", "redémarre mon pc",
                            "redemarre le pc", "relance le pc")):
        return ("confirm", "redemarrage")
    if any(k in c for k in ("mets le pc en veille", "mets l'ordinateur en veille",
                            "mets mon pc en veille")):
        return ("confirm", "veille_pc")

    # Volume et son
    if "volume" in c:
        rep = _volume(c)
        if rep:
            return rep
    if any(k in c for k in ("coupe le son", "remets le son", "rétablis le son", "rends le son",
                            "mets le son en sourdine", "mute")):
        pyautogui.press("volumemute")
        return "J'ai basculé le son, Salim."

    # Musique et vidéos (touches multimédia)
    if any(k in c for k in ("pause la musique", "mets pause", "reprends la musique",
                            "mets la musique", "pause la vidéo")):
        pyautogui.press("playpause")
        return "C'est fait."
    if any(k in c for k in ("musique suivante", "morceau suivant", "chanson suivante", "piste suivante")):
        pyautogui.press("nexttrack")
        return "Morceau suivant."
    if any(k in c for k in ("musique précédente", "morceau précédent", "chanson précédente",
                            "piste précédente")):
        pyautogui.press("prevtrack")
        return "Morceau précédent."

    # Écran
    if any(k in c for k in ("capture d'écran", "capture d'ecran", "screenshot", "prends une capture")):
        try:
            chemin = capture_ecran()
        except Exception as exc:
            return "La capture a échoué : " + str(exc)
        return "Capture enregistrée dans le dossier Images, sous JARVIS. " + os.path.basename(chemin)
    if any(k in c for k in ("affiche le bureau", "montre le bureau", "réduis toutes les fenêtres")):
        pyautogui.hotkey("win", "d")
        return "Voici le bureau."
    if "luminosité" in c or "luminosite" in c:
        n = nombre_dans(c.split("luminosit", 1)[1])
        if n is None:
            return "Dites par exemple : luminosité à cinquante."
        try:
            ok = regler_luminosite(n)
        except Exception:
            ok = False
        return (f"Luminosité réglée à {n} pour cent." if ok
                else "Je ne peux pas régler la luminosité de cet écran (fréquent sur un PC fixe).")

    # Verrouillage
    if any(k in c for k in ("verrouille le pc", "verrouille l'ordinateur", "verrouille mon pc",
                            "verrouille la session", "verrouille l'écran")):
        ctypes.windll.user32.LockWorkStation()
        return "Session verrouillée, Salim."

    return None

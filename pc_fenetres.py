"""pc_fenetres.py - JARVIS envoie du code directement dans la fenêtre d'un logiciel (Godot, VS Code,
Bloc-notes...).

Principe : trouver la fenêtre, la mettre au premier plan, puis coller (Ctrl+V) à l'endroit du curseur.
JARVIS ne voit pas l'écran : le logiciel doit être ouvert avec le fichier ou le script voulu.
Sécurité : jamais dans un terminal (un collage y exécuterait le code aussitôt).
"""
import time

import pyautogui
import pyperclip

from pc_docs import normaliser

TERMINAUX = ("powershell", "cmd.exe", "invite de commandes", "command prompt", "windows terminal",
             "terminal", "git bash", "wsl")


def _gw():
    try:
        import pygetwindow as gw
        return gw
    except Exception:
        return None


def est_terminal(titre):
    t = normaliser(titre)
    return any(k in t for k in TERMINAUX)


def trouver(noms):
    """Première fenêtre dont le titre contient l'un des noms (le plus précis d'abord)."""
    gw = _gw()
    if gw is None:
        return None
    variantes = []
    for nom in noms:
        n = normaliser(nom).strip()
        # un nom très court (« code ») est trop ambigu : il faut le nom complet du logiciel
        if n and (len(n) >= 4 or len(noms) == 1) and n not in variantes:
            variantes.append(n)
    for n in variantes:
        for fenetre in gw.getAllWindows():
            titre = (fenetre.title or "").strip()
            if titre and "jarvis" not in normaliser(titre) and n in normaliser(titre):
                return fenetre
    return None


def _actif(titre):
    gw = _gw()
    try:
        courante = gw.getActiveWindow()
        return bool(courante) and courante.title == titre
    except Exception:
        return False


def activer(fenetre):
    titre = fenetre.title
    try:
        if fenetre.isMinimized:
            fenetre.restore()
    except Exception:
        pass
    for _ in range(3):
        try:
            fenetre.activate()
        except Exception:
            pass  # pygetwindow signale parfois une erreur alors que la fenêtre est bien active
        time.sleep(0.4)
        if _actif(titre):
            return True
        pyautogui.press("alt")  # contourne le blocage du premier plan par Windows
    return False


def coller(titre, code, remplacer=False):
    """Colle le code dans la fenêtre au titre donné. Lève RuntimeError avec un message clair."""
    if est_terminal(titre):
        raise RuntimeError("je refuse de coller dans un terminal, le code s'y exécuterait tout de suite")
    fenetre = trouver([titre])
    if fenetre is None:
        raise RuntimeError("la fenêtre « " + titre[:40] + " » n'est plus ouverte")
    if not activer(fenetre):
        raise RuntimeError("je n'arrive pas à mettre cette fenêtre au premier plan")
    time.sleep(0.5)
    pyperclip.copy(code)
    if remplacer:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.15)
    pyautogui.hotkey("ctrl", "v")

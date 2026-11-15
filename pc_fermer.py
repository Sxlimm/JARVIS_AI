"""pc_fermer.py - JARVIS ferme un logiciel : « ferme Chrome », « quitte Word ».

Fermeture POLIE par défaut : JARVIS envoie à chaque fenêtre la demande de fermeture normale (comme un clic
sur la croix), donc le logiciel peut te demander d'enregistrer. « De force » termine le processus sans
prévenir (documents non enregistrés perdus) et exige « JARVIS oui ». Les processus système sont protégés.
"""
import difflib
import re
import subprocess

import psutil

from pc_docs import normaliser

SANS_FENETRE = 0x08000000
WM_CLOSE = 0x0010
PROTEGES = {"explorer.exe", "winlogon.exe", "csrss.exe", "svchost.exe", "services.exe", "lsass.exe", "system",
            "dwm.exe", "wininit.exe", "smss.exe", "searchhost.exe", "startmenuexperiencehost.exe",
            "shellexperiencehost.exe", "textinputhost.exe", "securityhealthsystray.exe", "msmpeng.exe",
            "taskmgr.exe", "ctfmon.exe", "fontdrvhost.exe", "sihost.exe", "registry"}
TITRES_IGNORES = ("program manager", "windows input experience", "msctfime ui", "default ime", "jarvis")


def _n(texte):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normaliser(texte)).split())


def fenetres_visibles():
    """[{hwnd, titre, pid, processus}] des fenêtres visibles ayant un titre (Windows)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    sortie = []
    proc_enum = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def rappel(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                tampon = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, tampon, n + 1)
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                sortie.append({"hwnd": hwnd, "titre": tampon.value, "pid": pid.value})
        return True

    user32.EnumWindows(proc_enum(rappel), 0)
    for f in sortie:
        try:
            f["processus"] = psutil.Process(f["pid"]).name()
        except Exception:
            f["processus"] = ""
    return [f for f in sortie if not any(t in f["titre"].lower() for t in TITRES_IGNORES)]


def _score(q, f):
    proc = _n(f["processus"].rsplit(".", 1)[0])
    titre = _n(f["titre"])
    if not q:
        return 0.0
    if q == proc:
        return 1.0
    if len(q) >= 3 and (q in proc.split() or proc.startswith(q) or q in proc):
        return 0.95
    if len(q) >= 3 and (" " + q + " ") in (" " + titre + " "):
        return 0.9
    if len(q) >= 3 and q in titre:
        return 0.85
    return max(difflib.SequenceMatcher(None, q, proc).ratio(), 0.0)


def trouver(noms, fenetres):
    """Meilleur logiciel ouvert correspondant à l'un des noms : (fenêtres du même processus, score) ou None."""
    meilleur_pid, meilleur_score = None, 0.0
    for nom in noms:
        q = _n(nom)
        for f in fenetres:
            s = _score(q, f)
            if s > meilleur_score:
                meilleur_pid, meilleur_score = f["pid"], s
    if meilleur_pid is None or meilleur_score < 0.75:
        return None
    return [f for f in fenetres if f["pid"] == meilleur_pid], meilleur_score


def fermer_doucement(fenetres):
    import ctypes
    n = 0
    for f in fenetres:
        ctypes.windll.user32.PostMessageW(f["hwnd"], WM_CLOSE, 0, 0)
        n += 1
    return n


def est_protege(processus):
    return processus.lower() in PROTEGES


def forcer(pid, processus):
    if est_protege(processus):
        raise PermissionError("« %s » est un processus système : je n'y touche pas" % processus)
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=SANS_FENETRE)

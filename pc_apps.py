"""pc_apps.py - JARVIS connaît tous les logiciels de ton PC et les ouvre par leur nom.

Sources lues (100 % local) :
  1. la liste du menu Démarrer de Windows (applications classiques ET applications du Microsoft Store),
  2. les raccourcis du menu Démarrer et du Bureau (.lnk, .url : les jeux Steam y sont souvent),
  3. les dossiers supplémentaires que tu indiques (logiciels portables, jeux), 2 niveaux de profondeur.
"""
import difflib
import json
import os
import re
import subprocess
import threading

from pc_docs import normaliser

SANS_FENETRE = 0x08000000

IGNORES = ("uninstall", "desinstall", "readme", "lisez moi", "license", "licence", "documentation",
           "manual", "site web", "website", "release notes", "notes de version", "changelog")
EXE_IGNORES = ("unins", "setup", "install", "crash", "update", "updater", "helper", "redist",
               "vc_redist", "dxsetup", "launcher_helper", "notification")
FILLERS = re.compile(r"^(?:(?:moi|le|la|les|mon|ma|mes|un|une|ce|cette|logiciel|application|appli|"
                     r"programme|jeu)\s+|l')+")
POLITESSE = re.compile(r"\s+(?:s'il te plaît|s'il te plait|s'il vous plaît|s'il vous plait|stp|svp)\s*$")


def _n(texte):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normaliser(texte)).split())


def nettoyer_nom(demande):
    d = POLITESSE.sub("", demande.lower().strip(" .,!?"))
    return FILLERS.sub("", d).strip()


def _ignore(nom_normalise):
    return any(mot in nom_normalise for mot in IGNORES)


def _depuis_get_startapps():
    cmd = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
           "Get-StartApps | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                       timeout=60, creationflags=SANS_FENETRE)
    texte = r.stdout.decode("utf-8", errors="replace").strip()
    if not texte:
        return []
    donnees = json.loads(texte)
    if isinstance(donnees, dict):
        donnees = [donnees]
    return [{"nom": d["Name"], "cible": "shell:AppsFolder\\" + d["AppID"]}
            for d in donnees if d.get("Name") and d.get("AppID")]


def _raccourcis(dossiers):
    entrees = []
    for dossier in dossiers:
        if not dossier or not os.path.isdir(dossier):
            continue
        for racine, _, fichiers in os.walk(dossier):
            for f in fichiers:
                nom, ext = os.path.splitext(f)
                if ext.lower() in (".lnk", ".url"):
                    entrees.append({"nom": nom, "cible": os.path.join(racine, f)})
    return entrees


def _executables(dossiers, profondeur=2):
    entrees = []
    for dossier in dossiers:
        if not dossier or not os.path.isdir(dossier):
            continue
        base = dossier.rstrip("\\/").count(os.sep)
        for racine, sous, fichiers in os.walk(dossier):
            if racine.count(os.sep) - base >= profondeur:
                sous[:] = []
            for f in fichiers:
                nom, ext = os.path.splitext(f)
                if ext.lower() == ".exe" and not any(m in nom.lower() for m in EXE_IGNORES):
                    entrees.append({"nom": nom, "cible": os.path.join(racine, f)})
    return entrees


def lancer(entree):
    os.startfile(entree["cible"])


class Logiciels:
    def __init__(self, dossiers_supplementaires=()):
        self.supplementaires = list(dossiers_supplementaires)
        self.entrees = []
        self.pret = False
        self.verrou = threading.Lock()

    def scanner(self):
        home = os.path.expanduser("~")
        demarrer = [os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
                    os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]
        bureaux = [os.path.join(home, "Desktop"), os.path.join(home, "OneDrive", "Desktop"),
                   os.path.join(os.environ.get("PUBLIC", ""), "Desktop")]
        brut = []
        try:
            brut += _depuis_get_startapps()
        except Exception:
            pass  # PowerShell indisponible : on se contente des raccourcis
        brut += _raccourcis(demarrer + bureaux) + _executables(self.supplementaires)
        vus, entrees = set(), []
        for e in brut:
            n = _n(e["nom"])
            if not n or n in vus or _ignore(n):
                continue
            vus.add(n)
            entrees.append({"nom": e["nom"], "cible": e["cible"], "n": n})
        with self.verrou:
            self.entrees = entrees
            self.pret = True
        return len(entrees)

    def noms(self):
        with self.verrou:
            return sorted((e["nom"] for e in self.entrees), key=str.lower)

    def chercher(self, demande):
        """Renvoie (entrée, score) ou None. 1.0 = nom exact ; en dessous de 0.85, à confirmer."""
        q = _n(nettoyer_nom(demande))
        if len(q) < 2:
            return None
        with self.verrou:
            entrees = list(self.entrees)
        meilleur, score_max = None, 0.0
        for e in entrees:
            n = e["n"]
            if n == q:
                s = 1.0
            elif len(q) >= 3 and (" " + q + " ") in (" " + n + " "):
                s = 0.93 - 0.002 * len(n)
            elif len(q) >= 3 and q in n.replace(" ", ""):
                s = 0.88 - 0.002 * len(n)
            elif len(n) >= 4 and (" " + n + " ") in (" " + q + " "):
                s = 0.86 - 0.002 * len(n)
            else:
                s = difflib.SequenceMatcher(None, q, n).ratio()
                for mot in n.split():
                    s = max(s, 0.9 * difflib.SequenceMatcher(None, q, mot).ratio())
            if s > score_max:
                meilleur, score_max = e, s
        return (meilleur, score_max) if meilleur and score_max >= 0.6 else None

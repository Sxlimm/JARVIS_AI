"""pc_optim.py - Optimisation prudente de Windows par JARVIS.

Ce que fait ce module (rien d'irréversible sans accord explicite) :
  - analyser le PC et donner des conseils chiffrés (mémoire, disque, démarrage, ancienneté du démarrage) ;
  - supprimer les fichiers temporaires de plus d'un jour (dossiers TEMP uniquement) ;
  - vider la corbeille ;
  - lister et désactiver (réversible) les programmes qui démarrent avec Windows.
Ce qu'il ne fait volontairement PAS : « nettoyeur de registre », désactivation de services Windows,
suppression de fichiers système. Ces « boosters » font gagner très peu et peuvent casser Windows.
"""
import ctypes
import difflib
import os
import re
import shutil
import subprocess
import time

import psutil

from pc_docs import normaliser

SANS_FENETRE = 0x08000000
CLE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
CLE_APPROUVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
CLE_APPROUVE_DOSSIER = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"
PROTEGES = ("jarvis", "defender", "securityhealth", "antivirus", "antimalware", "bitdefender", "kaspersky",
            "norton", "mcafee", "avast", "avg", "eset", "malwarebytes")


def _go(valeur):
    return ("%.1f" % valeur).replace(".", ",")


def formater_taille(octets):
    if octets >= 1024 ** 3:
        return ("%.1f Go" % (octets / 1024 ** 3)).replace(".", ",")
    return "%d Mo" % round(octets / 1024 ** 2)


# ---------------------------------------------------------------- fichiers temporaires

def dossiers_temp():
    candidats = [os.environ.get("TEMP"), os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")]
    vus, sortie = set(), []
    for d in candidats:
        if d and os.path.isdir(d) and os.path.realpath(d) not in vus:
            vus.add(os.path.realpath(d))
            sortie.append(d)
    return sortie


def parcourir_temp(racines=None, age_jours=1, delai=25):
    """(taille totale, [(chemin, taille)]) des fichiers temporaires de plus de `age_jours` jours."""
    racines = dossiers_temp() if racines is None else racines
    limite, fin = time.time() - age_jours * 86400, time.time() + delai
    total, fichiers = 0, []
    for racine in racines:
        for dossier, _, noms in os.walk(racine):
            if time.time() > fin:
                return total, fichiers
            for nom in noms:
                chemin = os.path.join(dossier, nom)
                try:
                    if os.path.islink(chemin):
                        continue
                    st = os.stat(chemin)
                except OSError:
                    continue
                if st.st_mtime < limite:
                    fichiers.append((chemin, st.st_size))
                    total += st.st_size
    return total, fichiers


def supprimer_temp(racines=None, age_jours=1):
    """Supprime les fichiers temporaires anciens. Renvoie (octets libérés, supprimés, ignorés)."""
    racines = dossiers_temp() if racines is None else racines
    reels = [os.path.realpath(r) for r in racines]
    _, fichiers = parcourir_temp(racines, age_jours)
    liberes = supprimes = ignores = 0
    for chemin, taille in fichiers:
        reel = os.path.realpath(chemin)
        if not any(reel.startswith(r + os.sep) for r in reels):   # garde-fou : jamais hors des dossiers TEMP
            ignores += 1
            continue
        try:
            os.remove(chemin)
            liberes, supprimes = liberes + taille, supprimes + 1
        except OSError:
            ignores += 1  # fichier en cours d'utilisation ou droits insuffisants
    for racine in racines:  # dossiers devenus vides
        for dossier, _, _ in os.walk(racine, topdown=False):
            if dossier != racine:
                try:
                    os.rmdir(dossier)
                except OSError:
                    pass
    return liberes, supprimes, ignores


def vider_corbeille():
    """Renvoie « ok » ou « vide »."""
    code = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)  # sans confirmation, sans bruit
    if code in (0, 0x8000FFFF):  # 0x8000FFFF : la corbeille était déjà vide
        return "ok" if code == 0 else "vide"
    raise OSError("Windows a refusé (code %d)" % code)


# ---------------------------------------------------------------- programmes de démarrage

def _approuve_desactive(nom, racine, cle_approuve):
    import winreg
    try:
        with winreg.OpenKey(racine, cle_approuve) as cle:
            donnees, _ = winreg.QueryValueEx(cle, nom)
        return bool(donnees) and donnees[0] % 2 == 1   # 03 = désactivé, 02 ou 06 = activé
    except OSError:
        return False


def lister_demarrage():
    """[{nom, commande, portee, type, actif, modifiable}] : entrées Run (utilisateur et machine) et dossier Démarrage."""
    import winreg
    sortie = []
    for racine, portee in ((winreg.HKEY_CURRENT_USER, "utilisateur"), (winreg.HKEY_LOCAL_MACHINE, "machine")):
        try:
            with winreg.OpenKey(racine, CLE_RUN) as cle:
                i = 0
                while True:
                    try:
                        nom, valeur, _ = winreg.EnumValue(cle, i)
                    except OSError:
                        break
                    i += 1
                    sortie.append({"nom": nom, "commande": str(valeur), "portee": portee, "type": "run",
                                   "actif": not _approuve_desactive(nom, racine, CLE_APPROUVE_RUN),
                                   "modifiable": portee == "utilisateur"})
        except OSError:
            continue
    dossier = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    if os.path.isdir(dossier):
        for f in os.listdir(dossier):
            if f.lower().endswith((".lnk", ".url", ".bat", ".cmd", ".vbs", ".exe")):
                sortie.append({"nom": f, "commande": os.path.join(dossier, f), "portee": "utilisateur",
                               "type": "dossier", "modifiable": True,
                               "actif": not _approuve_desactive(f, winreg.HKEY_CURRENT_USER, CLE_APPROUVE_DOSSIER)})
    return sortie


def est_protege(entree):
    n = normaliser(entree["nom"] + " " + entree["commande"])
    return any(p in n for p in PROTEGES)


def trouver_demarrage(entrees, nom):
    q = normaliser(nom).strip()
    meilleur, score_max = None, 0.0
    for e in entrees:
        n = normaliser(e["nom"])
        s = 1.0 if q == n else (0.9 if q and (q in n or n in q) else difflib.SequenceMatcher(None, q, n).ratio())
        if s > score_max:
            meilleur, score_max = e, s
    return meilleur if score_max >= 0.6 else None


def definir_demarrage(entree, actif):
    """Active ou désactive (réversible) une entrée de démarrage de l'utilisateur."""
    import winreg
    if not entree["modifiable"]:
        raise PermissionError("entrée « machine » : à modifier dans le Gestionnaire des tâches, onglet Démarrage")
    if not actif and est_protege(entree):
        raise PermissionError("programme de sécurité ou JARVIS lui-même : je n'y touche pas")
    cle_approuve = CLE_APPROUVE_RUN if entree["type"] == "run" else CLE_APPROUVE_DOSSIER
    valeur = bytes([2 if actif else 3]) + bytes(11)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cle_approuve) as cle:
        winreg.SetValueEx(cle, entree["nom"], 0, winreg.REG_BINARY, valeur)


# ---------------------------------------------------------------- analyse

def plan_alimentation():
    try:
        r = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=8,
                           creationflags=SANS_FENETRE)
        return r.stdout.strip()
    except Exception:
        return ""


def analyser(lecteur=None):
    """Liste de conseils [(importance 1-3, phrase)], du plus important au moins important."""
    conseils = []
    ram = psutil.virtual_memory()
    total_go = ram.total / 1024 ** 3
    if ram.percent >= 80:
        conseils.append((3, "La mémoire est utilisée à %d %% (%s Go sur %s Go). Ferme les programmes que tu "
                            "n'utilises pas, surtout le navigateur et ses onglets." % (ram.percent, _go(ram.used / 1024 ** 3), _go(total_go))))
    lecteur = lecteur or os.environ.get("SystemDrive", "C:") + "\\"
    try:
        d = shutil.disk_usage(lecteur)
        libre_pct = d.free / d.total * 100
        if libre_pct < 15:
            conseils.append((3, "Le disque système est presque plein : %s libres, soit %d %%. Au-dessous de 15 %%, Windows "
                                "ralentit nettement." % (formater_taille(d.free), libre_pct)))
        elif libre_pct < 25:
            conseils.append((2, "Il reste %s sur le disque système (%d %%). Pense à faire de la place." % (
                formater_taille(d.free), libre_pct)))
    except OSError:
        pass
    try:
        taille, _ = parcourir_temp(delai=15)
        if taille > 300 * 1024 ** 2:
            conseils.append((2, "Il y a %s de fichiers temporaires à supprimer sans risque : dis « nettoie le PC »." %
                             formater_taille(taille)))
    except Exception:
        pass
    try:
        actifs = [e for e in lister_demarrage() if e["actif"]]
        if len(actifs) >= 8:
            conseils.append((3, "%d programmes démarrent avec Windows. C'est la première cause de lenteur au démarrage : "
                                "dis « quels programmes démarrent » pour les voir et en désactiver." % len(actifs)))
        elif len(actifs) >= 5:
            conseils.append((2, "%d programmes démarrent avec Windows, tu peux en désactiver quelques-uns." % len(actifs)))
    except Exception:
        pass
    jours = (time.time() - psutil.boot_time()) / 86400
    if jours >= 7:
        conseils.append((2, "Le PC n'a pas redémarré depuis %d jours. Un redémarrage libère la mémoire et applique les mises "
                            "à jour." % jours))
    plan = normaliser(plan_alimentation())
    if "economie" in plan or "saver" in plan:
        conseils.append((1, "Le mode d'alimentation est « économie d'énergie » : il bride le processeur. Dis « mode jeu » "
                            "pour passer en performances maximales."))
    if total_go < 7:
        conseils.append((2, "Avec %s Go de mémoire, la meilleure amélioration est matérielle : passer à 16 Go de RAM "
                            "(et à un disque SSD s'il n'y en a pas) aide plus que tous les logiciels d'optimisation." % _go(total_go)))
    conseils.sort(key=lambda c: -c[0])
    return conseils

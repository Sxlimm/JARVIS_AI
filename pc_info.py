"""pc_info.py - JARVIS lit les données de ton PC (100 % local, lecture seule).
Dépendance : pip install psutil
"""
import platform
import re
import socket
import subprocess
from collections import defaultdict
from datetime import datetime

import psutil

GO = 1024 ** 3


def cpu():
    pct = psutil.cpu_percent(interval=0.5)
    coeurs = psutil.cpu_count(logical=False) or "?"
    threads = psutil.cpu_count(logical=True) or "?"
    freq = psutil.cpu_freq()
    ghz = f", à {freq.current / 1000:.1f} gigahertz" if freq else ""
    return f"Processeur utilisé à {pct:.0f} %, {coeurs} cœurs et {threads} threads{ghz}."


def ram():
    m = psutil.virtual_memory()
    return (f"Mémoire vive : {m.used / GO:.1f} Go utilisés sur {m.total / GO:.1f} Go, "
            f"soit {m.percent:.0f} %.")


def disques():
    morceaux = []
    for p in psutil.disk_partitions(all=False):
        if "cdrom" in p.opts or not p.fstype:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        morceaux.append(f"{p.device.rstrip(chr(92))} {u.free / GO:.0f} Go libres sur "
                        f"{u.total / GO:.0f} Go ({u.percent:.0f} % utilisé)")
    return "Disques : " + " ; ".join(morceaux) + "." if morceaux else "Aucun disque lisible."


def batterie():
    b = psutil.sensors_battery()
    if b is None:
        return "Pas de batterie détectée, c'est probablement un PC fixe."
    etat = "en charge" if b.power_plugged else "sur batterie"
    reste = ""
    if not b.power_plugged and b.secsleft and b.secsleft > 0:
        reste = f", environ {b.secsleft // 3600} h {(b.secsleft % 3600) // 60} min restantes"
    return f"Batterie à {b.percent:.0f} %, {etat}{reste}."


def reseau():
    nom = socket.gethostname()
    try:
        ip = socket.gethostbyname(nom)
    except OSError:
        ip = "inconnue"
    io = psutil.net_io_counters()
    return (f"Réseau : PC « {nom} », adresse locale {ip}. "
            f"Depuis le démarrage : {io.bytes_recv / GO:.2f} Go reçus, {io.bytes_sent / GO:.2f} Go envoyés.")


def processus(n=5):
    par_nom = defaultdict(int)
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            par_nom[p.info["name"]] += p.info["memory_info"].rss
        except (psutil.Error, TypeError, AttributeError):
            continue
    top = sorted(par_nom.items(), key=lambda x: x[1], reverse=True)[:n]
    liste = ", ".join(f"{nom} ({taille / GO * 1024:.0f} Mo)" for nom, taille in top)
    return f"Programmes les plus gourmands en mémoire : {liste}."


def allume_depuis():
    delta = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
    h, reste = divmod(int(delta.total_seconds()), 3600)
    return f"Le PC est allumé depuis {h} heures et {reste // 60} minutes."


def gpu():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, creationflags=0x08000000).stdout.strip()
        nom, util, used, total, temp = [x.strip() for x in out.splitlines()[0].split(",")]
        return f"Carte graphique {nom} : {util} % utilisée, {used}/{total} Mo de mémoire, {temp} °C."
    except Exception:
        return "Je ne peux pas lire la carte graphique (seules les cartes NVIDIA sont gérées)."


def systeme():
    nom, release = platform.system(), platform.release()
    if nom == "Windows":
        # Windows 11 se déclare encore « 10 » : seul le numéro de build les distingue.
        try:
            build = int(platform.version().split(".")[-1])
            if release == "10" and build >= 22000:
                release = "11"
        except ValueError:
            pass
    return f"Système : {nom} {release}, version {platform.version()}."


def resume():
    return " ".join([cpu(), ram(), disques(), batterie(), allume_depuis()])


def rapport_complet():
    return "\n".join([systeme(), cpu(), ram(), disques(), batterie(), reseau(),
                      processus(), allume_depuis()])


def repondre(c):
    """Renvoie une réponse si la commande parle du PC, sinon None."""
    c = c.lower()
    mots = set(re.findall(r"[\w'-]+", c))

    if any(k in c for k in ("état du pc", "etat du pc", "infos du pc", "informations du pc",
                            "données du pc", "donnees du pc", "diagnostic", "état du système")):
        return rapport_complet()
    if "cpu" in mots or "processeur" in mots:
        return cpu()
    if "ram" in mots or "mémoire vive" in c or "memoire vive" in c:
        return ram()
    if any(k in c for k in ("disque", "stockage", "espace libre")):
        return disques()
    if "batterie" in mots:
        return batterie()
    if any(k in mots for k in ("réseau", "reseau", "wifi", "ip")):
        return reseau()
    if any(k in c for k in ("gourmand", "quels programmes", "quels processus", "processus")):
        return processus()
    if "allumé depuis" in c or "allume depuis" in c:
        return allume_depuis()
    if "gpu" in mots or "carte graphique" in c:
        return gpu()
    return None


if __name__ == "__main__":
    print(rapport_complet())

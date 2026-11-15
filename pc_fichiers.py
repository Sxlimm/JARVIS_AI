"""pc_fichiers.py - JARVIS retrouve un fichier par son nom : « cherche mon CV », « où est ma facture EDF ».

La recherche se fait dans tes dossiers personnels (Bureau, Documents, Téléchargements, Images, Vidéos,
Musique, OneDrive) et dans les dossiers que tu ajoutes. Elle ne lit jamais le contenu des fichiers.
"""
import difflib
import os
import re
import subprocess
import time
from datetime import datetime

from pc_docs import normaliser

DOSSIERS_PERSO = ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "OneDrive"]
IGNORES = {"appdata", "node_modules", ".git", "__pycache__", "$recycle.bin", "windows", "program files",
           "program files (x86)", "programdata", "venv", ".venv", "site-packages", ".cache"}
TYPES = {"pdf": {".pdf"}, "word": {".doc", ".docx", ".odt"}, "excel": {".xls", ".xlsx", ".csv", ".ods"},
         "powerpoint": {".ppt", ".pptx", ".odp"}, "diaporama": {".ppt", ".pptx", ".odp"},
         "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"},
         "photo": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"},
         "video": {".mp4", ".mkv", ".avi", ".mov", ".wmv"}, "musique": {".mp3", ".wav", ".flac", ".m4a"},
         "texte": {".txt", ".md"}}
for _singulier, _pluriel in (("image", "images"), ("photo", "photos"), ("video", "videos"), ("pdf", "pdfs"),
                             ("musique", "musiques")):
    TYPES[_pluriel] = TYPES[_singulier]
EXTENSIONS_RISQUE = {".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".ps1", ".vbs", ".js", ".jse", ".wsf",
                     ".lnk", ".jar", ".reg", ".dll", ".hta", ".pif"}
MOTS_VIDES = {"mon", "ma", "mes", "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "fichier",
              "fichiers", "document", "documents", "dossier", "dossiers", "sur", "pc", "ordinateur", "recent",
              "recents", "derniers", "dernier", "derniere", "dernieres", "mon", "moi", "il", "elle", "se", "trouve",
              "ou", "est", "sont", "cherche", "trouve", "retrouve", "localise", "avec", "pour", "dans", "mes", "word",
              "pdf", "pdfs", "excel", "powerpoint", "image", "images", "photo", "photos", "video", "videos", "musique", "musiques", "texte"}


def racines(supplementaires=()):
    home = os.path.expanduser("~")
    sortie = [os.path.join(home, d) for d in DOSSIERS_PERSO] + list(supplementaires)
    vus, uniques = set(), []
    for d in sortie:
        if os.path.isdir(d) and os.path.realpath(d) not in vus:
            vus.add(os.path.realpath(d))
            uniques.append(d)
    return uniques


def analyser_requete(texte):
    """{"mots": [...], "types": {extensions}|None, "recent": bool}"""
    n = normaliser(texte)
    mots_bruts = re.findall(r"[a-z0-9]+", n)
    types = None
    for m in mots_bruts:
        if m in TYPES:
            types = (types or set()) | TYPES[m]
    recent = any(m in ("recent", "recents", "dernier", "derniers", "derniere", "dernieres") for m in mots_bruts)
    mots = [m for m in mots_bruts if m not in MOTS_VIDES and len(m) >= 2]
    return {"mots": mots, "types": types, "recent": recent}


def _score(mots, nom_sans_ext, parents):
    if not mots:
        return 1.0
    jetons = re.findall(r"[a-z0-9]+", normaliser(nom_sans_ext))
    jetons_parents = re.findall(r"[a-z0-9]+", normaliser(parents))
    total = 0.0
    for m in mots:
        meilleur = 0.0
        for j in jetons:
            s = 1.0 if j == m else (0.9 if len(m) >= 3 and (j.startswith(m) or m in j) else
                                    difflib.SequenceMatcher(None, m, j).ratio())
            meilleur = max(meilleur, s)
        if meilleur < 0.8:  # le mot n'est pas dans le nom : un dossier parent qui le contient compte à moitié
            if any(m == p or (len(m) >= 4 and m in p) for p in jetons_parents):
                meilleur = 0.5
            else:
                return 0.0
        total += meilleur
    return total / len(mots)


def chercher(requete, dossiers, delai=25, maximum=8):
    """Fichiers dont le nom correspond : [{chemin, nom, taille, date, score}], meilleurs d'abord."""
    fin = time.time() + delai
    trouves = []
    for racine in dossiers:
        for dossier, sous, noms in os.walk(racine):
            sous[:] = [d for d in sous if d.lower() not in IGNORES and not d.startswith(".")]
            if time.time() > fin:
                break
            parents = os.path.relpath(dossier, racine) if dossier != racine else ""
            for nom in noms:
                stem, ext = os.path.splitext(nom)
                if requete["types"] and ext.lower() not in requete["types"]:
                    continue
                s = _score(requete["mots"], stem, parents + " " + os.path.basename(racine))
                if s <= 0:
                    continue
                chemin = os.path.join(dossier, nom)
                try:
                    st = os.stat(chemin)
                except OSError:
                    continue
                trouves.append({"chemin": chemin, "nom": nom, "taille": st.st_size, "date": st.st_mtime,
                                "score": s})
    if requete["recent"] or not requete["mots"]:
        trouves.sort(key=lambda f: -f["date"])
    else:
        trouves.sort(key=lambda f: (-round(f["score"], 2), -f["date"]))
    return trouves[:maximum]


def est_risque(chemin):
    return os.path.splitext(chemin)[1].lower() in EXTENSIONS_RISQUE


def ouvrir(chemin):
    """Ouvre un fichier sûr ; pour un exécutable ou un script, montre seulement son dossier."""
    if est_risque(chemin):
        reveler(chemin)
        return False
    os.startfile(chemin)
    return True


def reveler(chemin):
    subprocess.Popen(["explorer", "/select,", os.path.normpath(chemin)])


def taille_lisible(octets):
    if octets >= 1024 ** 3:
        return ("%.1f Go" % (octets / 1024 ** 3)).replace(".", ",")
    if octets >= 1024 ** 2:
        return "%d Mo" % round(octets / 1024 ** 2)
    return "%d Ko" % max(1, round(octets / 1024))


def date_lisible(horodatage):
    return datetime.fromtimestamp(horodatage).strftime("%d/%m/%Y")

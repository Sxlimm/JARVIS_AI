
import os
import re
import json
import subprocess

GODOT_EXE = r"C:\Users\farah\OneDrive\Desktop\Godot_v4.7.2-stable_win64.exe"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(APP_DIR, "projets_godot")
LAST_PROJECT_FILE = os.path.join(PROJECTS_DIR, "dernier_projet.json")

ALLOWED_FILES = (
    "project.godot",
    ".gd",
    ".tscn",
    ".tres",
    ".godot"
)


def est_demande_projet(c):
    c = c.lower()
    mots = ("crée", "cree", "créer", "creer", "fabrique", "construis")
    godot = "godot" in c
    jeu = any(x in c for x in ("jeu", "projet", "game"))
    return godot and jeu and any(x in c for x in mots)


def est_ouvrir_projet(c):
    c = c.lower().strip()
    expressions = (
        "fais-le sur godot",
        "fait-le sur godot",
        "ouvre le projet godot",
        "ouvre le dernier projet",
        "ouvre mon projet godot",
        "ouvre le jeu dans godot",
        "lance le projet godot"
    )
    return any(x in c for x in expressions)


def lire_dernier_projet():
    try:
        with open(LAST_PROJECT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        chemin = data.get("chemin", "")
        if os.path.isfile(os.path.join(chemin, "project.godot")):
            return chemin
    except Exception:
        pass
    return None


def enregistrer_dernier_projet(chemin):
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    with open(LAST_PROJECT_FILE, "w", encoding="utf-8") as f:
        json.dump({"chemin": chemin}, f, ensure_ascii=False, indent=2)


def nettoyer_nom(nom):
    nom = re.sub(r'[<>:"/\\|?*]', "", nom)
    nom = re.sub(r"\s+", "_", nom.strip())
    return nom[:50] or "Mon_jeu_Godot"


def creer_structure(nom):
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    dossier = os.path.join(PROJECTS_DIR, nettoyer_nom(nom))
    os.makedirs(os.path.join(dossier, "scenes"), exist_ok=True)
    os.makedirs(os.path.join(dossier, "scripts"), exist_ok=True)

    return dossier


def creer_projet_base(nom="Mon_jeu_Godot"):
    dossier = creer_structure(nom)

    project = """config_version=5

[application]
config/name="Mon jeu Godot"
run/main_scene="res://scenes/main.tscn"

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
"""

    scene = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scripts/main.gd" id="1"]

[node name="Main" type="Node2D"]
script = ExtResource("1")
"""

    script = """extends Node2D

func _ready():
    print("Bienvenue dans mon jeu Godot !")
"""

    with open(os.path.join(dossier, "project.godot"), "w", encoding="utf-8") as f:
        f.write(project)

    with open(os.path.join(dossier, "scenes", "main.tscn"), "w", encoding="utf-8") as f:
        f.write(scene)

    with open(os.path.join(dossier, "scripts", "main.gd"), "w", encoding="utf-8") as f:
        f.write(script)

    enregistrer_dernier_projet(dossier)
    return dossier


def ouvrir_projet(chemin=None):
    if chemin is None:
        chemin = lire_dernier_projet()

    if not chemin or not os.path.isfile(os.path.join(chemin, "project.godot")):
        return False, "Aucun projet Godot valide n'a été trouvé."

    if not os.path.isfile(GODOT_EXE):
        return False, "Je ne trouve pas Godot à son emplacement habituel."

    try:
        subprocess.Popen([
            GODOT_EXE,
            "--editor",
            "--path",
            chemin
        ])
        return True, "Projet ouvert dans Godot."
    except Exception as e:
        return False, str(e)

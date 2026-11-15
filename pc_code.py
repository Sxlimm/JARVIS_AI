"""pc_code.py - JARVIS écrit du code : détection des demandes, extraction du code, nom de fichier.

La génération elle-même est faite par jarvis.py avec un modèle Ollama spécialisé (qwen2.5-coder).
Le code n'est jamais exécuté automatiquement.
"""
import re
from datetime import datetime

from pc_docs import normaliser

LANGAGES = {
    "python": "python", "javascript": "javascript", "js": "javascript", "html": "html", "css": "css",
    "java": "java", "c++": "cpp", "cpp": "cpp", "c#": "csharp", "powershell": "powershell",
    "bash": "bash", "sql": "sql", "batch": "bat", "lua": "lua", "gdscript": "gdscript",
    "godot": "gdscript", "godo": "gdscript", "godeau": "gdscript",
}
NORMALISATION = {"py": "python", "js": "javascript", "node": "javascript", "c++": "cpp", "c#": "csharp",
                 "cs": "csharp", "sh": "bash", "shell": "bash", "ps1": "powershell", "gd": "gdscript",
                 "batch": "bat", "cmd": "bat", "htm": "html"}
EXTENSIONS = {"python": ".py", "javascript": ".js", "html": ".html", "css": ".css", "java": ".java",
              "cpp": ".cpp", "c": ".c", "csharp": ".cs", "powershell": ".ps1", "bash": ".sh",
              "sql": ".sql", "lua": ".lua", "gdscript": ".gd", "bat": ".bat"}

VERBES = {"écris", "ecris", "écrire", "ecrire", "crée", "cree", "créer", "creer", "fais", "fabrique",
          "génère", "genere", "développe", "developpe", "coder", "programmer", "réalise", "realise"}
OBJETS = ("script", "programme", "fonction", "application", "logiciel", "code", "classe", "bot", "jeu",
          "site", "page web", "outil", "calculatrice", "algorithme", "boucle", "macro", "module")
QUESTIONS = ("quel ", "quelle ", "quels ", "qui ", "qu'est", "c'est ", "combien", "pourquoi", "quand ", "où ")
MODIFS = ("modifie", "corrige", "ajoute", "change", "améliore", "ameliore", "simplifie", "optimise",
          "répare", "repare", "rends le code", "rajoute", "enlève", "enleve", "supprime la partie")
CAPACITE = ("tu peux coder", "tu peut coder", "peux-tu coder", "peux tu coder", "tu sais coder",
            "sais-tu coder", "sais tu coder", "tu sais programmer", "tu peux programmer",
            "tu codes", "tu peux faire du code", "tu sais écrire du code", "tu peux écrire du code")
MOTS_VIDES = set("""ecris ecrire cree creer fais fabrique genere developpe coder programmer realise
un une des moi toi script programme code fonction pour qui avec dans sur les the python en le la
de du et peux peut veux voudrais besoin que gdscript godot gd""".split())


def detecter_langage(c):
    c = re.sub(r"\bg\.?\s?d\.?\s?script\b", "gdscript", c.lower())  # « gd script » dit à voix haute
    for mot in re.findall(r"[\w+#]+", c):
        if mot in LANGAGES:
            return LANGAGES[mot]
    if "page web" in c or "site web" in c:
        return "html"
    return None


def est_capacite(c):
    return any(k in c.lower() for k in CAPACITE)


def est_modification(c):
    return c.lower().strip().startswith(MODIFS)


def est_demande_code(c):
    c = c.lower().strip(" ?!.")
    if c.startswith(QUESTIONS):
        return False
    mots = set(re.findall(r"[\w+#'-]+", c))
    langage = detecter_langage(c)
    verbe = bool(mots & VERBES)
    objet = any(o in c for o in OBJETS)
    if verbe and (objet or langage):
        return True
    if c.startswith(("code ", "codes ", "coder ", "programme-moi", "programme moi")):
        return True
    return bool(langage and mots & {"comment", "exemple", "explique", "montre"})


def normaliser_langage(nom):
    nom = (nom or "").strip().lower()
    return NORMALISATION.get(nom, nom)


def extraire_code(reponse):
    """Renvoie (langage, code, explication) ; code vide si la réponse n'en contient pas."""
    m = re.search(r"```([\w+#-]*)[ \t]*\n(.*?)```", reponse, re.S)
    if not m:  # bloc non refermé (réponse coupée)
        m = re.search(r"```([\w+#-]*)[ \t]*\n(.*)$", reponse, re.S)
    if not m:
        return "", "", reponse.strip()
    explication = (reponse[:m.start()] + " " + reponse[m.end():]).strip()
    return normaliser_langage(m.group(1)), m.group(2).strip("\n"), " ".join(explication.split())


def nom_fichier(langage, demande):
    mots = [m for m in re.findall(r"[a-z0-9]{3,}", normaliser(demande)) if m not in MOTS_VIDES][:3]
    base = "_".join(mots) or "code"
    return base + "_" + datetime.now().strftime("%H%M%S") + EXTENSIONS.get(langage, ".txt")


CONSIGNES_GODOT = (
    "\nLe langage est GDScript pour Godot 4 (GDScript 2.0). Utilise STRICTEMENT la syntaxe de Godot 4, "
    "jamais celle de Godot 3 :\n"
    "- @export var vitesse: float = 300.0 (pas « export var »), @onready var noeud = $Noeud (pas « onready »).\n"
    "- Mouvement : extends CharacterBody2D ou CharacterBody3D, modifier la propriété velocity puis appeler "
    "move_and_slide() sans argument (pas KinematicBody).\n"
    "- Fonctions : func _physics_process(delta: float) -> void:\n"
    "- Signaux : signal touche, touche.emit(), bouton.pressed.connect(_on_pressed) "
    "(pas emit_signal ni connect avec une chaîne).\n"
    "- Entrées : Input.get_vector(\"gauche\", \"droite\", \"haut\", \"bas\"), "
    "Input.is_action_just_pressed(\"saut\").\n"
    "- Nœuds : Node2D, Node3D, Area2D, Area3D, RigidBody3D, StaticBody3D, CollisionShape3D, MeshInstance3D, "
    "Camera3D, Timer.\n"
    "- Indente avec des tabulations. Donne des types aux variables.\n"
    "- Écris en première ligne un commentaire indiquant le type de nœud auquel attacher le script, "
    "et les actions à créer dans Projet > Paramètres du projet > Contrôles."
)


def consignes_langage(langage):
    return CONSIGNES_GODOT if langage == "gdscript" else ""


POLITESSE = re.compile(r"\s+(?:s'il te pla[iî]t|s'il vous pla[iî]t|stp|svp)\s*$")
VERBES_COLLAGE = r"\b(?:colle|écris|ecris|mets|met|tape|envoie|insère|insere|transfère|transfere|copie|remplace|écrase|ecrase)\b"
OBJET_DEFINI = r"\b(?:le|ce|mon|ton|ce dernier|le dernier)\s+(?:code|script)\b"
ARTICLES = r"(?:le |la |l'|les |mon |ma )?(?:logiciel |application |appli |éditeur |editeur |fenêtre |fenetre )?"
CIBLE = r"(?P<cible>[\w .+#'-]{2,40}?)"


def _nettoyer_cible(texte):
    texte = POLITESSE.sub("", texte.strip(" ,;.!?")).strip()
    return texte if len(texte) >= 2 and "presse" not in texte else None


def cible_collage(c):
    """« colle le code dans godot » -> {"cible": "godot", "remplacer": False} ; sinon None."""
    c = POLITESSE.sub("", c.lower().strip(" ?!."))
    if not re.search(VERBES_COLLAGE, c) or not re.search(OBJET_DEFINI, c):
        return None
    remplacer = bool(re.search(r"\b(?:remplace|écrase|ecrase)\b", c))
    m = re.search(r"\b(?:de|dans|sur)\s+" + ARTICLES + CIBLE + r"\s+par\s+(?:le|ce)\s+(?:code|script)\b", c)
    if not m:
        m = re.search(r"\b(?:dans|sur|vers|à)\s+" + ARTICLES + CIBLE + r"$", c)
    cible = _nettoyer_cible(m.group("cible")) if m else None
    return {"cible": cible, "remplacer": remplacer} if cible else None


def cible_fin(c):
    """« écris un script gdscript pour sauter dans godot » -> « godot » (à valider par l'appelant)."""
    c = POLITESSE.sub("", c.lower().strip(" ?!."))
    m = re.search(r"\b(?:directement\s+)?(?:dans|sur)\s+" + ARTICLES + CIBLE + r"$", c)
    return _nettoyer_cible(m.group("cible")) if m else None

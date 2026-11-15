"""pc_agent.py - Logique de l'agent qui utilise l'écran : consignes données à l'IA, lecture de l'action
qu'elle choisit, contrôles de sécurité. Rien n'est exécuté ici.
"""
import json
import re

from pc_docs import normaliser

# Un clic sur un élément contenant l'un de ces mots exige « JARVIS oui », même en mode automatique.
BLOQUES = ("supprimer", "effacer", "desinstaller", "formater", "payer", "paiement", "acheter", "commander",
           "envoyer", "publier", "virement", "reinitialiser", "quitter sans enregistrer",
           "ne pas enregistrer", "vider", "detruire", "definitivement", "confirmer l'achat",
           "valider la commande", "delete", "remove", "uninstall", "pay", "buy", "send", "erase")
TOUCHES_RISQUE = {"alt+f4", "ctrl+w", "ctrl+shift+delete", "win+l", "shift+delete"}
ACTIONS_VALIDES = {"cliquer", "double_cliquer", "ecrire", "touche", "defiler", "attendre", "fini"}

SYSTEME = (
    "Tu pilotes un ordinateur Windows pour Salim, une action à la fois. Tu reçois l'objectif, le titre de "
    "la fenêtre active, la liste numérotée des éléments visibles et les étapes déjà faites. Réponds "
    "UNIQUEMENT par un objet JSON, sans aucun texte autour, sous l'une de ces formes :\n"
    '{"action":"cliquer","id":3,"raison":"..."}\n'
    '{"action":"double_cliquer","id":3,"raison":"..."}\n'
    '{"action":"ecrire","id":4,"texte":"...","raison":"..."}  (id = zone de texte à cliquer avant, facultatif)\n'
    '{"action":"touche","touche":"ctrl+s","raison":"..."}\n'
    '{"action":"defiler","sens":"bas","raison":"..."}\n'
    '{"action":"attendre","raison":"..."}\n'
    '{"action":"fini","raison":"ce qui a été fait, ou pourquoi c\'est impossible"}\n'
    "N'invente jamais d'id : utilise seulement ceux de la liste. Fais la plus petite action utile. "
    "Si l'objectif est atteint ou impossible, réponds fini."
)


def est_bloque(nom):
    n = " ".join(re.sub(r"[^a-z0-9']+", " ", normaliser(nom)).split())
    return any(re.search(r"\b" + re.escape(m) + r"\b", n) for m in BLOQUES)


def decrire_elements(elements, maximum=60):
    """Renvoie (texte numéroté pour l'IA, liste d'éléments dans le même ordre)."""
    retenus = elements[:maximum]
    lignes = ["%d. [%s] %s" % (i, e["type"], (e["nom"] or "(sans nom)")[:60]) for i, e in enumerate(retenus, 1)]
    return "\n".join(lignes) or "(aucun élément lisible)", retenus


def construire_messages(objectif, titre, liste_texte, historique):
    fait = "\n".join(historique[-8:]) or "(rien encore)"
    utilisateur = ("Objectif : " + objectif + "\nFenêtre active : " + (titre or "(inconnue)")
                   + "\n\nÉléments visibles :\n" + liste_texte + "\n\nÉtapes déjà faites :\n" + fait
                   + "\n\nProchaine action (JSON) :")
    return [{"role": "system", "content": SYSTEME}, {"role": "user", "content": utilisateur}]


def lire_action(texte, nb_elements):
    """Action validée sous forme de dict, ou None si la réponse de l'IA est inutilisable."""
    m = re.search(r"\{.*\}", texte or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group())
    except ValueError:
        return None
    if not isinstance(d, dict) or d.get("action") not in ACTIONS_VALIDES:
        return None
    action = {"action": d["action"], "id": None, "texte": "", "touche": "", "sens": "bas",
              "raison": str(d.get("raison", ""))[:120]}

    def identifiant(valeur):
        try:
            i = int(valeur)
        except (TypeError, ValueError):
            return None
        return i if 1 <= i <= nb_elements else None

    if d["action"] in ("cliquer", "double_cliquer"):
        action["id"] = identifiant(d.get("id"))
        if action["id"] is None:
            return None
    elif d["action"] == "ecrire":
        action["texte"] = str(d.get("texte", ""))
        action["id"] = identifiant(d.get("id"))
        if not action["texte"]:
            return None
    elif d["action"] == "touche":
        action["touche"] = str(d.get("touche", "")).strip().lower()
        if not action["touche"]:
            return None
    elif d["action"] == "defiler":
        action["sens"] = "haut" if d.get("sens") == "haut" else "bas"
    return action


def evaluer(action, element):
    """("ok" | "danger" | "interdit", motif)."""
    genre = action["action"]
    if genre == "ecrire" and element is not None:
        n = normaliser(element.get("nom", ""))
        if element.get("mdp") or "mot de passe" in n or "password" in n:
            return "interdit", "je n'écris jamais dans un champ de mot de passe"
    if genre in ("cliquer", "double_cliquer") and element is not None and est_bloque(element.get("nom", "")):
        return "danger", "ce bouton peut supprimer, envoyer ou payer"
    if genre == "touche" and action["touche"].replace(" ", "") in TOUCHES_RISQUE:
        return "danger", "ce raccourci peut fermer ou supprimer"
    return "ok", ""


def description(action, element):
    nom = (element or {}).get("nom") or (element or {}).get("type") or "sans nom"
    genre = action["action"]
    if genre == "cliquer":
        return "cliquer sur « %s »" % nom
    if genre == "double_cliquer":
        return "double-cliquer sur « %s »" % nom
    if genre == "ecrire":
        cible = " dans « %s »" % nom if element else ""
        return "écrire « %s »%s" % (action["texte"][:40], cible)
    if genre == "touche":
        return "appuyer sur " + action["touche"]
    if genre == "defiler":
        return "faire défiler vers le " + action["sens"]
    return "attendre un instant"

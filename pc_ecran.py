"""pc_ecran.py - JARVIS « voit » l'écran et agit de façon visible (souris et clavier).

Voir l'écran, sans modèle d'image lourd :
  1. UI Automation de Windows : liste des boutons, menus, zones de texte... de la fenêtre active ;
  2. OCR de Windows (paquet winocr) : le texte affiché à l'écran, avec sa position.
Agir : la souris glisse lentement vers la cible et le texte est tapé caractère par caractère,
pour que tu puisses suivre. Arrêt d'urgence : souris dans le coin haut gauche de l'écran.
"""
import base64
import difflib
import io
import re
import time

import pyautogui
import pyperclip

from pc_docs import normaliser

TYPES_UTILES = {
    "ButtonControl": "bouton", "SplitButtonControl": "bouton", "MenuItemControl": "menu",
    "TabItemControl": "onglet", "EditControl": "zone de texte", "CheckBoxControl": "case à cocher",
    "RadioButtonControl": "bouton radio", "ComboBoxControl": "liste déroulante",
    "ListItemControl": "élément de liste", "HyperlinkControl": "lien",
    "TreeItemControl": "élément d'arbre", "DocumentControl": "document", "TextControl": "texte",
}
TOUCHES = {"contrôle": "ctrl", "controle": "ctrl", "control": "ctrl", "entrée": "enter", "entree": "enter",
           "échap": "esc", "echap": "esc", "espace": "space", "tabulation": "tab", "supprimer": "delete",
           "suppr": "delete", "retour": "backspace", "majuscule": "shift", "fenêtre": "win",
           "fenetre": "win", "windows": "win", "flèche bas": "down", "flèche haut": "up"}


def _n(texte):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normaliser(texte)).split())


# ---------------------------------------------------------------- voir l'écran

def capturer():
    return pyautogui.screenshot()


def png_base64(image, cote=1024):
    image = image.copy()
    image.thumbnail((cote, cote))
    tampon = io.BytesIO()
    image.save(tampon, format="PNG")
    return base64.b64encode(tampon.getvalue()).decode("ascii")


def titre_actif():
    try:
        import uiautomation as auto
        return (auto.GetForegroundControl().Name or "").strip()
    except Exception:
        return ""


def elements_actifs(max_elements=60, delai=6.0):
    """Éléments utiles de la fenêtre active : [{nom, type, rect, mdp, source}]."""
    import uiautomation as auto
    racine = auto.GetForegroundControl()
    titre = (racine.Name or "").strip()
    fin = time.time() + delai
    sortie = []
    for ctrl, _profondeur in auto.WalkControl(racine, includeTop=False, maxDepth=12):
        if time.time() > fin or len(sortie) >= max_elements:
            break
        try:
            genre = ctrl.ControlTypeName
            if genre not in TYPES_UTILES or ctrl.IsOffscreen:
                continue
            nom = (ctrl.Name or "").strip()
            r = ctrl.BoundingRectangle
            if r.width() < 4 or r.height() < 4 or (not nom and genre != "EditControl"):
                continue
            sortie.append({"nom": nom, "type": TYPES_UTILES[genre],
                           "rect": (r.left, r.top, r.right, r.bottom),
                           "mdp": bool(getattr(ctrl, "IsPassword", False)), "source": "uia"})
        except Exception:
            continue
    return titre, sortie


def mots_ocr(image, langue="fr"):
    """Lignes de texte lues à l'écran : [{nom, type, rect, mdp, source}] ; None si winocr est absent."""
    try:
        import winocr
    except ImportError:
        return None
    try:
        res = winocr.recognize_pil_sync(image, langue)
    except Exception:
        res = winocr.recognize_pil_sync(image, "en")
    lignes = []
    for ligne in res.get("lines", []):
        mots = [m for m in ligne.get("words", []) if m.get("bounding_rect")]
        texte = (ligne.get("text") or " ".join(m.get("text", "") for m in mots)).strip()
        if not mots or len(texte) < 2:
            continue
        gauche = min(m["bounding_rect"]["x"] for m in mots)
        haut = min(m["bounding_rect"]["y"] for m in mots)
        droite = max(m["bounding_rect"]["x"] + m["bounding_rect"]["width"] for m in mots)
        bas = max(m["bounding_rect"]["y"] + m["bounding_rect"]["height"] for m in mots)
        lignes.append({"nom": texte, "type": "texte vu", "rect": (int(gauche), int(haut), int(droite), int(bas)),
                       "mdp": False, "source": "ocr"})
    return lignes


def fusionner(elements, lignes_ocr, ignorer=("jarvis", "arreter")):
    """Éléments UI Automation + lignes OCR sans doublon ; ignore le bandeau de JARVIS lui-même."""
    connus = {_n(e["nom"]) for e in elements if e["nom"]}
    sortie = list(elements)
    for ligne in lignes_ocr or []:
        n = _n(ligne["nom"])
        if n and n not in connus and not any(m in n for m in ignorer):
            sortie.append(ligne)
            connus.add(n)
    return sortie


# ---------------------------------------------------------------- trouver une cible

def _score(q, n):
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    if len(q) >= 3 and (" " + q + " ") in (" " + n + " "):
        return 0.93 - 0.002 * len(n)
    if len(q) >= 3 and q in n:
        return 0.88 - 0.002 * len(n)
    s = difflib.SequenceMatcher(None, q, n).ratio()
    for mot in n.split():
        s = max(s, 0.9 * difflib.SequenceMatcher(None, q, mot).ratio())
    return s


def trouver_cible(nom, elements):
    """(élément, score) le plus proche du nom demandé, ou None."""
    q = _n(nom)
    meilleur, score_max = None, 0.0
    for e in elements:
        s = _score(q, _n(e["nom"]))
        if e.get("source") == "ocr":
            s *= 0.97  # à égalité, l'élément « vrai » de la fenêtre passe avant le texte lu
        if s > score_max:
            meilleur, score_max = e, s
    return (meilleur, score_max) if meilleur and score_max >= 0.7 else None


def centre(rect):
    return (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2


# ---------------------------------------------------------------- agir, de façon visible

def aller_vers(x, y, duree=0.9):
    pyautogui.moveTo(x, y, duration=duree, tween=pyautogui.easeInOutQuad)


def cliquer_visible(x, y, bouton="left", double=False):
    aller_vers(x, y)
    time.sleep(0.3)
    if double:
        pyautogui.doubleClick()
    else:
        pyautogui.click(button=bouton)


def ecrire_visible(texte, pause=0.04):
    """Tape le texte lettre par lettre (les accents passent par le presse-papiers)."""
    for ch in texte:
        if ch == "\n":
            pyautogui.press("enter")
        elif ch.isascii() and ch.isprintable():
            pyautogui.write(ch)
        else:
            pyperclip.copy(ch)
            pyautogui.hotkey("ctrl", "v")
        time.sleep(pause)


def convertir_touche(texte):
    """« contrôle s » ou « ctrl+s » -> ["ctrl", "s"]. Lève ValueError si une touche est inconnue."""
    t = texte.lower().replace(" plus ", "+").strip()
    morceaux = [p.strip() for p in (t.split("+") if "+" in t else re.split(r"\s+", t)) if p.strip()]
    touches = [TOUCHES.get(p, p) for p in morceaux]
    valides = getattr(pyautogui, "KEYBOARD_KEYS", None)
    if not touches or (valides and any(k not in valides for k in touches)):
        raise ValueError("touche inconnue : " + texte)
    return touches


def appuyer(texte):
    touches = convertir_touche(texte)
    if len(touches) == 1:
        pyautogui.press(touches[0])
    else:
        pyautogui.hotkey(*touches)


def defiler(sens="bas", crans=5):
    pyautogui.scroll(-crans if sens == "bas" else crans)

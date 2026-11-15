"""pc_outils.py - Outils exacts pour JARVIS : calculs, pourcentages, conversions d'unités, dates.

Un petit modèle d'IA se trompe souvent en calculant. Ici les réponses sont calculées par le programme
(jamais devinées) : « combien font quinze fois vingt-trois », « 20 % de 150 », « 10 miles en km »,
« dans combien de jours est Noël ». Tout est local, sans modèle.
"""
import ast
import math
import operator
import re
from datetime import date, datetime, timedelta

from pc_docs import normaliser

# ---------------------------------------------------------------- nombres écrits en lettres

UNITES_NB = {"zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
             "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
             "quinze": 15, "seize": 16}
DIZAINES = {"vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}
OPERATEURS_MOTS = {"plus", "moins", "fois", "par", "divise", "divisee", "multiplie", "multiplies", "puissance",
                   "x", "+", "-", "*", "/", "au", "pourcent", "egal", "egale"}
VOCAB = set(UNITES_NB) | set(DIZAINES) | {"cent", "cents", "mille", "million", "millions"}


def _nombre_a(jetons, i):
    total = courant = 0
    j, vu = i, False
    while j < len(jetons):
        t = jetons[j]
        if t == "et" and vu and j + 1 < len(jetons) and jetons[j + 1] in VOCAB:
            j += 1
            continue
        if t == "quatre" and j + 1 < len(jetons) and jetons[j + 1] in ("vingt", "vingts"):
            courant, j, vu = courant + 80, j + 2, True
            continue
        if t in UNITES_NB:
            courant += UNITES_NB[t]
        elif t in DIZAINES:
            courant += DIZAINES[t]
        elif t in ("cent", "cents"):
            courant = (courant or 1) * 100
        elif t == "mille":
            total, courant = total + (courant or 1) * 1000, 0
        elif t in ("million", "millions"):
            total, courant = total + (courant or 1) * 1_000_000, 0
        else:
            break
        vu = True
        j += 1
    return (total + courant, j) if vu else None


def mots_vers_chiffres(texte):
    """« quinze fois vingt trois » -> « 15 fois 23 » (texte déjà normalisé)."""
    texte = re.sub(r"\bpour cents?\b", "pourcent", texte)
    jetons = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", texte).split()
    sortie, i = [], 0
    while i < len(jetons):
        r = _nombre_a(jetons, i) if jetons[i] in VOCAB else None
        if r and r[1] == i + 1 and jetons[i] in ("un", "une"):
            # « un » / « une » seul : article ou nombre ? Nombre seulement à côté d'un opérateur ou d'un chiffre.
            voisins = jetons[max(0, i - 1):i] + jetons[i + 1:i + 2]
            if not any(v in OPERATEURS_MOTS or v.replace(".", "").isdigit() for v in voisins):
                r = None
        if r:
            sortie.append(str(r[0]))
            i = r[1]
        else:
            sortie.append(jetons[i])
            i += 1
    return " ".join(sortie)


# ---------------------------------------------------------------- calcul sûr

OPERATEURS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
              ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
FONCTIONS = {"sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max}
CONSTANTES = {"pi": math.pi}


def _evaluer(n):
    if isinstance(n, ast.Expression):
        return _evaluer(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
        return n.value
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
        v = _evaluer(n.operand)
        return v if isinstance(n.op, ast.UAdd) else -v
    if isinstance(n, ast.BinOp) and type(n.op) in OPERATEURS:
        a, b = _evaluer(n.left), _evaluer(n.right)
        if isinstance(n.op, ast.Pow) and (abs(b) > 1000 or (abs(a) > 1e6 and b > 10)):
            raise ValueError("nombre trop grand")
        return OPERATEURS[type(n.op)](a, b)
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FONCTIONS and not n.keywords:
        return FONCTIONS[n.func.id](*[_evaluer(a) for a in n.args])
    if isinstance(n, ast.Name) and n.id in CONSTANTES:
        return CONSTANTES[n.id]
    raise ValueError("expression non autorisée")


def formater(v):
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        v = int(v)
    if isinstance(v, int):
        return str(v)
    return ("%.10g" % v).replace(".", ",")


DEBUTS_CALCUL = ("calcule", "calcul ", "combien font", "combien fait", "combien ca fait", "combien ça fait",
                 "c'est combien", "combien vaut", "combien valent", "resous", "résous", "donne moi le resultat de")


def _vers_expression(texte):
    """Texte français -> expression arithmétique, ou None si ce n'est pas un calcul."""
    t = normaliser(texte).replace("×", "*").replace("÷", "/").replace("^", "**")
    for debut in sorted(DEBUTS_CALCUL, key=len, reverse=True):
        d = normaliser(debut)
        if t.startswith(d):
            t = t[len(d):]
            break
    t = re.sub(r"\b(?:s'il te plait|s'il vous plait|stp|svp|egal|egale|egalent)\b|[?!=]", " ", t)
    t = mots_vers_chiffres(t)
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)
    t = re.sub(r"(?<=\d) (?=\d{3}\b)", "", t)                       # 1 000 -> 1000
    t = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|pour cent|pourcent)\s*de\s+", r"(\1/100)*", t)
    t = re.sub(r"racine carree de\s+(\d+(?:\.\d+)?)", r"sqrt(\1)", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s+au carre\b", r"(\1)**2", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s+au cube\b", r"(\1)**3", t)
    t = re.sub(r"\bmultipli\w*\s+par\b|\bfois\b|(?<=\d)\s*x\s*(?=\d)", "*", t)
    t = re.sub(r"\bdivis\w*\s+par\b", "/", t)
    t = re.sub(r"\b(?:puissance|exposant)\b", "**", t)
    t = re.sub(r"\bplus\b", "+", t)
    t = re.sub(r"\bmoins\b", "-", t)
    t = t.strip(" .,")
    if not t or len(t) > 200 or not re.search(r"\d", t) or not re.search(r"[-+*/%]|sqrt|pi\b", t):
        return None
    if re.search(r"[a-z]", re.sub(r"sqrt|\bpi\b", "", t)):
        return None  # il reste des mots : ce n'est pas un calcul pur
    return t


def calcul(texte):
    expression = _vers_expression(texte)
    if expression is None:
        return None
    try:
        v = _evaluer(ast.parse(expression, mode="eval"))
    except ZeroDivisionError:
        return "La division par zéro est impossible, Salim."
    except ValueError as exc:
        return "Ce nombre est trop grand pour moi, Salim." if "trop grand" in str(exc) else None
    except (SyntaxError, TypeError, OverflowError):
        return None
    return "Le résultat est " + formater(v) + "."


def remise(texte):
    """« 80 euros avec 15 % de remise » -> prix final."""
    t = mots_vers_chiffres(normaliser(texte))
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:euros?|€)?\s*(?:avec|apres|moins|et)?\s*(?:une? )?(?:remise|reduction|solde)s?\s+de\s+"
                  r"(\d+(?:\.\d+)?)\s*(?:%|pourcent)", t)
    if m:
        prix, pct = float(m.group(1)), float(m.group(2))
    else:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:euros?|€)?\s*(?:avec|apres|moins)?\s*(?:une? )?(\d+(?:\.\d+)?)\s*(?:%|pourcent)\s*"
                      r"de\s+(?:remise|reduction|solde)", t)
        if not m:
            return None
        prix, pct = float(m.group(1)), float(m.group(2))
    final = prix * (1 - pct / 100)
    return "Après %s %% de remise sur %s, le prix est de %s, soit %s d'économie." % (
        formater(pct), formater(prix), formater(round(final, 2)), formater(round(prix - final, 2)))


# ---------------------------------------------------------------- conversions d'unités

LONGUEURS = {"mm": 0.001, "millimetre": 0.001, "cm": 0.01, "centimetre": 0.01, "m": 1, "metre": 1, "km": 1000,
             "kilometre": 1000, "pouce": 0.0254, "inch": 0.0254, "pied": 0.3048, "foot": 0.3048, "feet": 0.3048,
             "yard": 0.9144, "mile": 1609.344}
MASSES = {"g": 0.001, "gramme": 0.001, "kg": 1, "kilo": 1, "kilogramme": 1, "tonne": 1000, "livre": 0.45359237,
          "lb": 0.45359237, "once": 0.028349523125}
VOLUMES = {"ml": 0.001, "millilitre": 0.001, "cl": 0.01, "centilitre": 0.01, "l": 1, "litre": 1, "gallon": 3.785411784}
VITESSES = {"km/h": 1 / 3.6, "kmh": 1 / 3.6, "m/s": 1.0, "mph": 0.44704, "noeud": 0.514444}
DUREES = {"seconde": 1, "s": 1, "minute": 60, "min": 60, "heure": 3600, "h": 3600, "jour": 86400, "semaine": 604800}
TEMPERATURES = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}
FAMILLES = [LONGUEURS, MASSES, VOLUMES, VITESSES, DUREES]


def _unite(brut):
    u = normaliser(brut).strip(" .")
    u = re.sub(r"\bdegres?\b", "", u).replace("°", "").strip()
    if u in ("km/h", "m/s"):
        return u
    if u in ("celsius", "fahrenheit", "kelvin"):
        return {"celsius": "c", "fahrenheit": "f", "kelvin": "k"}[u]
    return re.sub(r"(?<=[a-z]{3})[sx]$", "", u)  # pluriels : miles, pieds, kilometres


def _temperature(v, de, vers):
    kelvin = v if de == "k" else (v + 273.15 if de == "c" else (v - 32) * 5 / 9 + 273.15)
    return kelvin if vers == "k" else (kelvin - 273.15 if vers == "c" else (kelvin - 273.15) * 9 / 5 + 32)


ACCENTS = {"kilometre": "kilomètre", "kilometres": "kilomètres", "metre": "mètre", "metres": "mètres",
           "millimetre": "millimètre", "millimetres": "millimètres", "centimetre": "centimètre",
           "centimetres": "centimètres", "degres": "degrés", "millilitre": "millilitre", "noeud": "nœud"}


def _accents(texte):
    return re.sub(r"[a-z]+", lambda m: ACCENTS.get(m.group(), m.group()), texte)


def conversion(texte):
    t = mots_vers_chiffres(normaliser(texte))
    t = re.sub(r"\b(?:un|une)\s+(?=[a-z/°]+(?: [a-z]+)?\s+(?:en|vers)\b)", "1 ", t)   # « un kilomètre en mètres »
    t = re.sub(r"(?<=\bfont )(?:un|une)\b|(?<=\bfait )(?:un|une)\b", "1", t)       # « combien de mètres font un kilomètre »
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)
    m = re.search(r"(?P<val>-?\d+(?:\.\d+)?)\s*(?P<u1>[a-z/°]+(?: [a-z]+)?)\s+(?:en|vers)\s+(?P<u2>[a-z/°]+)", t)
    if m:
        v, u1, u2 = float(m.group("val")), m.group("u1"), m.group("u2")
    else:
        m = re.search(r"combien (?:de |d')?(?P<u2>[a-z/°]+) (?:font|fait|y a t il dans|dans) (?P<val>-?\d+(?:\.\d+)?)\s*"
                      r"(?P<u1>[a-z/°]+(?: [a-z]+)?)", t)
        if not m:
            return None
        v, u1, u2 = float(m.group("val")), m.group("u1"), m.group("u2")
    u1, u2 = _unite(u1), _unite(u2)
    if u1 in TEMPERATURES and u2 in TEMPERATURES:
        r = _temperature(v, u1, u2)
    else:
        famille = next((f for f in FAMILLES if u1 in f and u2 in f), None)
        if famille is None:
            return None
        r = v * famille[u1] / famille[u2]
    return _accents("%s %s font %s %s." % (formater(v), m.group("u1").strip(), formater(round(r, 6)), m.group("u2").strip()))


# ---------------------------------------------------------------- dates

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
MOIS_N = {normaliser(m): i + 1 for i, m in enumerate(MOIS)}
FETES = {"noel": (12, 25), "nouvel an": (1, 1), "jour de l'an": (1, 1), "saint valentin": (2, 14),
         "halloween": (10, 31), "la fete nationale": (7, 14)}
RE_DATE = re.compile(r"(?:le )?(\d{1,2})(?:er)?\s+(" + "|".join(MOIS_N) + r")(?:\s+(\d{4}))?")
RE_NUM = re.compile(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?")


def joli(d):
    return "%s %s %s %d" % (JOURS[d.weekday()], "1er" if d.day == 1 else d.day, MOIS[d.month - 1], d.year)


def _prochaine(mois, jour, aujourdhui):
    for annee in (aujourdhui.year, aujourdhui.year + 1, aujourdhui.year + 2, aujourdhui.year + 4):
        try:
            d = date(annee, mois, jour)
        except ValueError:
            continue
        if d >= aujourdhui:
            return d
    return None


def lire_date(t, aujourdhui, futur=True):
    """Première date trouvée dans le texte normalisé, ou None."""
    for mot, delta in (("apres demain", 2), ("demain", 1), ("aujourd'hui", 0), ("hier", -1)):
        if mot in t:
            return aujourdhui + timedelta(days=delta)
    for nom, (mois, jour) in FETES.items():
        if nom in t:
            return _prochaine(mois, jour, aujourdhui) if futur else date(aujourdhui.year, mois, jour)
    m = RE_DATE.search(t)
    if m:
        jour, mois = int(m.group(1)), MOIS_N[m.group(2)]
        try:
            return date(int(m.group(3)), mois, jour) if m.group(3) else (
                _prochaine(mois, jour, aujourdhui) if futur else date(aujourdhui.year, mois, jour))
        except ValueError:
            return None
    m = RE_NUM.search(t)
    if m:
        jour, mois = int(m.group(1)), int(m.group(2))
        try:
            return date(int(m.group(3)), mois, jour) if m.group(3) else _prochaine(mois, jour, aujourdhui)
        except ValueError:
            return None
    return None


def _ajouter_mois(d, n):
    mois = d.month - 1 + n
    annee, mois = d.year + mois // 12, mois % 12 + 1
    dernier = (date(annee + (mois == 12), mois % 12 + 1, 1) - timedelta(days=1)).day
    return date(annee, mois, min(d.day, dernier))


def calcul_date(texte, aujourdhui=None):
    aujourdhui = aujourdhui or date.today()
    t = mots_vers_chiffres(normaliser(texte)).strip(" ?!.")
    m = re.search(r"dans (\d+) (jours?|semaines?|mois|ans?|annees?)", t)
    if m and ("quel jour" in t or "quelle date" in t or "serons nous" in t or "sera t on" in t):
        n, unite = int(m.group(1)), m.group(2)
        d = (aujourdhui + timedelta(days=n) if unite.startswith("jour") else
             aujourdhui + timedelta(weeks=n) if unite.startswith("semaine") else
             _ajouter_mois(aujourdhui, n) if unite == "mois" else _ajouter_mois(aujourdhui, 12 * n))
        return "Dans %d %s, nous serons le %s." % (n, m.group(2), joli(d))
    m = re.search(r"combien de (jours|semaines|mois) (?:y a t il |separent |reste t il )?entre (.+?) et (.+)$", t)
    if m:
        d1, d2 = lire_date(m.group(2), aujourdhui), lire_date(m.group(3), aujourdhui)
        if d1 and d2:
            jours = abs((d2 - d1).days)
            return "Il y a %d jours entre le %s et le %s." % (jours, joli(d1), joli(d2))
    if "dans combien de" in t:
        d = lire_date(t, aujourdhui)
        if d:
            jours = (d - aujourdhui).days
            if jours == 0:
                return "C'est aujourd'hui, Salim."
            return "Il reste %d jour%s avant le %s." % (jours, "s" if jours > 1 else "", joli(d))
    if t.startswith(("quel jour", "quelle jour")) and any(k in t for k in ("sera", "etait", "tombe", "est le", "etait le")):
        d = lire_date(t, aujourdhui, futur="etait" not in t)
        if d:
            verbe = "sera" if d > aujourdhui else ("est" if d == aujourdhui else "était")
            return "Le %d %s %d %s un %s." % (d.day, MOIS[d.month - 1], d.year, verbe, JOURS[d.weekday()])
    if "quel age" in t and ("ne" in t.split() or " ne " in " " + t + " "):
        d = lire_date(t, aujourdhui, futur=False)
        if d and d < aujourdhui and RE_DATE.search(t) and RE_DATE.search(t).group(3):
            ans = aujourdhui.year - d.year - ((aujourdhui.month, aujourdhui.day) < (d.month, d.day))
            return "Cela fait %d ans." % ans
    return None


# ---------------------------------------------------------------- point d'entrée

def repondre(commande, aujourdhui=None):
    """Réponse exacte si la commande est un calcul, une conversion ou une question de date ; sinon None."""
    for outil in (lambda c: calcul_date(c, aujourdhui), remise, conversion, calcul):
        try:
            r = outil(commande)
        except Exception:
            r = None
        if r:
            return r
    return None

"""pc_rappels.py - Rappels et minuteurs vocaux de JARVIS.

« mets un minuteur de 10 minutes pour les pâtes », « rappelle-moi dans une heure et demie d'appeler Karim »,
« rappelle-moi demain à 8h de prendre mon médicament », « réveille-moi à 7h30 ».
Les rappels sont sauvegardés dans rappels.json : ils survivent à un redémarrage de JARVIS.
"""
import json
import os
import re
import uuid
from datetime import datetime, timedelta

from pc_docs import normaliser
from pc_outils import _nombre_a, VOCAB, JOURS

DECLENCHEURS = ("rappelle", "un rappel", "minuteur", "chrono", "compte a rebours", "previens moi",
                "previens-moi", "reveille moi", "reveille-moi", "n'oublie pas", "alarme")
DEBUT_LABEL = {"rappelle", "rappelle-moi", "moi", "mets", "met", "mettre", "ajoute", "lance", "programme", "regle",
               "un", "une", "le", "minuteur", "rappel", "chrono", "previens", "previens-moi", "reveille", "reveille-moi",
               "n'oublie", "n'oublie-pas", "pas", "de", "me", "d'", "du", "pour", "que", "qu'", "a", "au", "afin",
               "et", "s'il", "te", "plait", "alarme", "encore"}
PERIODES = {"matin": "matin", "soir": "soir", "apres-midi": "soir", "apres midi": "soir", "midi": "midi"}


# ---------------------------------------------------------------- découpage en unités alignées

ELISIONS = ("d'", "l'", "qu'", "n'", "j'", "m'", "t'", "s'", "c'")
UNITES_TEMPS = re.compile(r"(?:heures?|minutes?|secondes?|jours?|semaines?)")


def decouper(commande):
    """Unités {n: forme normalisée, o: forme originale, colle: sans espace avant} ; les nombres en lettres
    sont fusionnés en un chiffre et les élisions (d'une, l'heure) séparées."""
    morceaux = []
    for o in commande.strip(" .!?").split():
        bas = o.lower()
        el = next((e for e in ELISIONS if bas.startswith(e) and len(o) > len(e)), None)
        if el:
            morceaux.append((o[:len(el)], False))
            morceaux.append((o[len(el):], True))
        else:
            morceaux.append((o, False))
    originaux = [m[0] for m in morceaux]
    colles = [m[1] for m in morceaux]
    normes = [re.sub(r"[.,!?;]+$", "", normaliser(o)) for o in originaux]
    unites, i = [], 0
    while i < len(normes):
        r = _nombre_a(normes, i) if normes[i] in VOCAB else None
        if r:
            valeur, j = r
            if j == i + 1 and normes[i] in ("un", "une") and not (j < len(normes) and UNITES_TEMPS.fullmatch(normes[j])):
                r = None  # article : « un minuteur », « une demi-heure »
        if r:
            unites.append({"n": str(valeur), "o": " ".join(originaux[i:j]), "colle": colles[i]})
            i = j
        else:
            unites.append({"n": normes[i], "o": originaux[i], "colle": colles[i]})
            i += 1
    return unites


def assembler(unites):
    texte = ""
    for u in unites:
        texte += ("" if (u["colle"] or not texte) else " ") + u["o"]
    return texte


# ---------------------------------------------------------------- expressions de temps

RE_COURT = re.compile(r"(?:(?:dans|de|d'|pendant)\s+)?(?P<q>un quart d'?\s?heure|une demi[- ]?heure|trois quarts d'?\s?heure)")
RE_HEURES_DUREE = re.compile(r"dans\s+(?P<h>\d+)\s*(?:heures?|h)(?:\s+et\s+(?P<f>demie?|quart)|\s+(?P<m>\d{1,2})(?:\s*min(?:utes?)?)?)?(?!\d)")
RE_DUREE_PREF = re.compile(r"(?:dans|de|d'|pendant)\s+(?P<v>\d+(?:[.,]\d+)?)\s*(?P<u>secondes?|sec|minutes?|min|heures?|jours?|semaines?)\b")
RE_DUREE_NU = re.compile(r"(?P<v>\d+(?:[.,]\d+)?)\s*(?P<u>secondes?|sec|minutes?|min|jours?|semaines?)\b")
RE_DUREE_H_MINUTEUR = re.compile(r"(?:de|d')\s*(?P<h>\d+)\s*(?:heures?|h)(?:\s+et\s+(?P<f>demie?|quart)|\s+(?P<m>\d{1,2})(?:\s*min(?:utes?)?)?)?(?!\d)")
RE_HORLOGE = re.compile(r"(?:a|vers)\s+(?P<h>\d{1,2})\s*(?:heures?|h|:)(?:\s?(?P<m>\d{2})(?!\d))?"
                        r"(?:\s+et\s+(?P<f>demie?|quart)|\s+moins\s+(?:le\s+)?(?P<mo>quart|\d{1,2}))?"
                        r"(?:\s+du\s+(?P<p>matin|soir|apres[- ]midi))?")
RE_MIDI = re.compile(r"\ba\s+(?P<mm>midi|minuit)\b")
RE_JOUR = re.compile(r"\b(?P<j>apres demain|demain|aujourd'hui|ce soir|ce matin|cet apres[- ]midi|" + "|".join(JOURS) + r")\b")


def _duree(m):
    """Durée (timedelta) d'une correspondance de RE_COURT / RE_HEURES_DUREE / RE_DUREE ; None sinon."""
    g = m.groupdict()
    if g.get("q"):
        q = g["q"]
        return timedelta(minutes=45 if "trois" in q else (30 if "demi" in q else 15))
    if g.get("h") is not None and "u" not in g:
        d = timedelta(hours=int(g["h"]))
        if g.get("f"):
            d += timedelta(minutes=30 if g["f"].startswith("demi") else 15)
        elif g.get("m"):
            d += timedelta(minutes=int(g["m"]))
        return d
    v = float(g["v"].replace(",", "."))
    u = g["u"]
    if u.startswith("sec"):
        return timedelta(seconds=v)
    if u.startswith("min"):
        return timedelta(minutes=v)
    if u.startswith("heure"):
        return timedelta(hours=v)
    if u.startswith("jour"):
        return timedelta(days=v)
    return timedelta(weeks=v)


def duree_lisible(delta):
    s = int(round(delta.total_seconds()))
    if s < 60:
        return "%d seconde%s" % (s, "s" if s > 1 else "")
    if s < 3600:
        m = round(s / 60)
        return "%d minute%s" % (m, "s" if m > 1 else "")
    if s < 86400:
        h, m = divmod(s // 60, 60)
        return "%d heure%s%s" % (h, "s" if h > 1 else "", (" %d" % m) if m else "")
    j = s // 86400
    return "%d jour%s" % (j, "s" if j > 1 else "")


def heure_lisible(dt, maintenant):
    jour = ("aujourd'hui" if dt.date() == maintenant.date() else
            "demain" if dt.date() == (maintenant + timedelta(days=1)).date() else
            "%s %d" % (JOURS[dt.weekday()], dt.day))
    return "%s à %d h %02d" % (jour, dt.hour, dt.minute)


def _horloge(m, mm):
    """(heure, minute, période) d'une correspondance de RE_HORLOGE ou RE_MIDI."""
    if mm:
        return (12 if mm.group("mm") == "midi" else 0), 0, "midi"
    h, minute = int(m.group("h")), int(m.group("m") or 0)
    f, mo = m.group("f"), m.group("mo")
    if f:
        minute = 30 if f.startswith("demi") else 15
    if mo:
        retrait = 15 if mo == "quart" else int(mo)
        h, minute = (h - 1) % 24, 60 - retrait
    periode = PERIODES.get((m.group("p") or "").replace("-", " ") if m.group("p") else "", None)
    if m.group("p") and m.group("p").startswith("apres"):
        periode = "soir"
    return h, minute, periode


def _echeance_horloge(h, minute, periode, jour, maintenant, matin=False):
    if h > 23 or minute > 59:
        return None
    base = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    if jour == "apres demain":
        base += timedelta(days=2)
    elif jour == "demain":
        base += timedelta(days=1)
    elif jour in JOURS:
        base += timedelta(days=(JOURS.index(jour) - maintenant.weekday()) % 7)
    if periode == "soir" and h < 12:
        h += 12
    candidat = base.replace(hour=h, minute=minute)
    if candidat <= maintenant:
        if jour is None and not matin and periode is None and 0 < h < 12:
            soir = base.replace(hour=h + 12, minute=minute)   # « à 6h » à 17h : on comprend 18h
            if soir > maintenant:
                return soir
        if jour in JOURS:
            candidat += timedelta(days=7)
        elif jour is None:
            candidat += timedelta(days=1)
        else:
            return None
    return candidat


# ---------------------------------------------------------------- analyse complète

def analyser(commande, maintenant=None):
    """None si la phrase n'est pas un rappel ; sinon {"echeance", "texte", "genre", "duree"} ou {"erreur"}."""
    maintenant = maintenant or datetime.now()
    brut = normaliser(commande)
    if not any(d in brut for d in DECLENCHEURS):
        return None
    unites = decouper(commande.strip())
    textes = [u["n"].replace("-", " ") for u in unites]   # « après-demain » = « apres demain »
    joint = " ".join(textes)
    debuts, pos = [], 0
    for t in textes:
        debuts.append(pos)
        pos += len(t) + 1
    minuteur = bool(re.search(r"minuteur|chrono|compte a rebours", joint))
    reveil = bool(re.search(r"\breveille moi\b", joint))

    consommes, echeance, duree, span = set(), None, None, None
    for motif in (RE_COURT, RE_HEURES_DUREE, RE_DUREE_PREF):          # 1) « dans 20 minutes », « de 10 minutes »
        m = motif.search(joint)
        if m:
            duree, span = _duree(m), m.span()
            break
    if duree is None and minuteur:                                      # 2) « minuteur d'1 heure »
        m = RE_DUREE_H_MINUTEUR.search(joint)
        if m:
            duree, span = _duree(m), m.span()
    if duree is None:                                                   # 3) « à 18h30 », « à midi »
        m, mm = RE_HORLOGE.search(joint), RE_MIDI.search(joint)
        if m or mm:
            h, minute, periode = _horloge(m, mm)
            jm = RE_JOUR.search(joint)
            jour = jm.group("j") if jm else None
            if jour == "ce soir":
                jour, periode = None, periode or "soir"
            elif jour in ("ce matin", "aujourd'hui", "cet apres midi", "cet apres-midi"):
                jour = None
            echeance = _echeance_horloge(h, minute, periode, jour, maintenant, matin=reveil)
            span = (m or mm).span()
            if echeance is None:
                return {"erreur": "Cette heure est déjà passée ou je ne l'ai pas comprise, Salim."}
    if duree is None and echeance is None:                              # 4) « 90 secondes », « 5 minutes »
        m = RE_DUREE_NU.search(joint)
        if m:
            duree, span = _duree(m), m.span()
    if duree is not None:
        echeance = maintenant + duree
    if echeance is None:
        return {"erreur": "Je n'ai pas compris quand, Salim. Dis par exemple « dans dix minutes » ou « à 18 heures »."}

    # les mots du jour (« demain », « lundi »...) et de l'heure ne font pas partie du texte à rappeler
    a_retirer = [span] if span else []
    for jm in RE_JOUR.finditer(joint):
        a_retirer.append(jm.span())
    for i, t in enumerate(textes):
        debut, fin = debuts[i], debuts[i] + len(t)
        if any(debut < s[1] and fin > s[0] for s in a_retirer):
            consommes.add(i)
    restant = [u for i, u in enumerate(unites) if i not in consommes]
    while restant and (restant[0]["n"] in DEBUT_LABEL or restant[0]["n"].rstrip("'") in DEBUT_LABEL):
        restant.pop(0)
    while restant and restant[-1]["n"] in ("dans", "a", "de", "d'", "pour", "et"):
        restant.pop()
    texte = assembler(restant).strip(" ,.")
    if minuteur:
        genre = "minuteur"
    elif reveil:
        genre, texte = "reveil", texte or "Réveil"
    else:
        genre, texte = "rappel", texte or "Rappel"
    return {"echeance": echeance, "texte": texte, "genre": genre, "duree": duree}


# ---------------------------------------------------------------- stockage

class Rappels:
    def __init__(self, chemin):
        self.chemin = chemin
        self.liste = []
        if os.path.exists(chemin):
            try:
                with open(chemin, encoding="utf-8") as f:
                    for r in json.load(f):
                        r["echeance"] = datetime.fromisoformat(r["echeance"])
                        self.liste.append(r)
            except (OSError, ValueError, KeyError):
                self.liste = []

    def _sauver(self):
        with open(self.chemin, "w", encoding="utf-8") as f:
            json.dump([dict(r, echeance=r["echeance"].isoformat()) for r in self.liste], f, ensure_ascii=False, indent=1)

    def ajouter(self, echeance, texte, genre="rappel", duree_texte=""):
        r = {"id": uuid.uuid4().hex[:8], "echeance": echeance, "texte": texte, "genre": genre, "duree": duree_texte}
        self.liste.append(r)
        self.liste.sort(key=lambda x: x["echeance"])
        self._sauver()
        return r

    def dus(self, maintenant=None):
        maintenant = maintenant or datetime.now()
        dus = [r for r in self.liste if r["echeance"] <= maintenant]
        if dus:
            self.liste = [r for r in self.liste if r not in dus]
            self._sauver()
        return dus

    def supprimer(self, numero=None, genre=None):
        """Supprime le rappel n° `numero` (1 = le plus proche), ou tous (numero=None) ; renvoie ceux supprimés."""
        cibles = [r for r in self.liste if genre is None or (r["genre"] == "minuteur") == (genre == "minuteur")]
        if numero is not None:
            cibles = cibles[numero - 1:numero] if 1 <= numero <= len(cibles) else []
        self.liste = [r for r in self.liste if r not in cibles]
        self._sauver()
        return cibles

    def description(self, r, maintenant=None):
        maintenant = maintenant or datetime.now()
        reste = duree_lisible(max(r["echeance"] - maintenant, timedelta(seconds=1)))
        nom = ("Minuteur" + (" « %s »" % r["texte"] if r["texte"] else "")) if r["genre"] == "minuteur" else r["texte"]
        return "%s, dans %s (%s)" % (nom, reste, heure_lisible(r["echeance"], maintenant))

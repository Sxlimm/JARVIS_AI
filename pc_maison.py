"""pc_maison.py - JARVIS commande la maison connectée via Home Assistant (lumières, volets, prises...).

Il faut un Home Assistant installé sur ton réseau, son adresse et un « jeton d'accès longue durée »
(profil Home Assistant > Sécurité). Renseigne HA_URL et HA_JETON en haut de jarvis.py.
Sans configuration, ce module reste inactif.
"""
import difflib
import json
import re
import time
import urllib.request

from pc_docs import normaliser

DOMAINES = {
    "lumiere": ("light",), "lampe": ("light",), "ampoule": ("light",),
    "volet": ("cover",), "store": ("cover",), "rideau": ("cover",), "garage": ("cover",), "portail": ("cover",),
    "prise": ("switch",), "ventilateur": ("fan", "switch"), "chauffage": ("climate", "switch"),
    "radiateur": ("climate", "switch"), "climatisation": ("climate",), "television": ("media_player",),
    "tele": ("media_player",), "scene": ("scene",), "ambiance": ("scene",),
}
ARTICLES = r"^(?:le |la |les |l'|du |de la |des |de l'|mon |ma |mes |un |une )+"
GENERIQUES = {"lumiere", "lumieres", "lampe", "lampes", "ampoule", "volet", "volets", "store", "stores", "rideau",
              "rideaux", "prise", "prises", "ventilateur", "chauffage", "radiateur", "climatisation", "television",
              "tele", "scene", "ambiance", "dans", "pour", "avec", "sur", "etat"}


def _n(texte):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normaliser(texte)).split())


class Maison:
    def __init__(self, url, jeton):
        self.url = (url or "").rstrip("/")
        self.jeton = jeton or ""
        self._cache, self._cache_heure = [], 0.0
        self.ambigus = []

    @property
    def configuree(self):
        return bool(self.url and self.jeton)

    def _requete(self, chemin, donnees=None):
        req = urllib.request.Request(
            self.url + chemin, data=None if donnees is None else json.dumps(donnees).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.jeton, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8") or "null")

    def entites(self):
        if time.time() - self._cache_heure > 60:
            self._cache = self._requete("/api/states")
            self._cache_heure = time.time()
        return self._cache

    def trouver(self, nom, domaines=None):
        """Entité dont le nom ressemble le plus à `nom` : (entité, score) ou None."""
        q = _n(re.sub(ARTICLES, "", nom.lower().strip()))
        # mots qui distinguent l'appareil voulu (« salon », « chambre »...) : ils doivent figurer dans son nom
        precis = [t for t in q.split() if t not in GENERIQUES and t not in ("de", "du", "la", "le", "les", "des", "l") and len(t) > 2]
        self.ambigus = []
        meilleur, score_max = None, 0.0
        du_domaine = []
        for e in self.entites():
            if domaines and e["entity_id"].split(".")[0] not in domaines:
                continue
            n = _n(e.get("attributes", {}).get("friendly_name", e["entity_id"]))
            if not n:
                continue
            du_domaine.append(e.get("attributes", {}).get("friendly_name", e["entity_id"]))
            mots = n.split()
            if precis and not all(any(difflib.SequenceMatcher(None, t, m).ratio() >= 0.8 for m in mots) for t in precis):
                continue
            if q == n:
                s = 1.0
            elif q and (q in n or n in q):
                s = 0.9
            else:
                s = difflib.SequenceMatcher(None, q, n).ratio()
            if s > score_max:
                meilleur, score_max = e, s
        if not precis and len(du_domaine) > 1:  # « la lumière » sans précision : on ne devine pas
            self.ambigus = du_domaine
            return None
        return (meilleur, score_max) if meilleur and score_max >= 0.6 else None

    def appeler(self, entite, service, donnees=None):
        domaine = entite["entity_id"].split(".")[0]
        corps = {"entity_id": entite["entity_id"]}
        corps.update(donnees or {})
        self._requete("/api/services/%s/%s" % (domaine, service), corps)


def analyser(c):
    """« allume la lumière du salon » -> {"verbe": "allumer", "cible": "lumière du salon", "domaines": (...)}"""
    c = c.lower().strip(" ?!.")
    m = re.match(r"^(?:est-ce que |est ce que )?(?:(?P<v>allume|éteins|eteins|ouvre|ferme|monte|baisse)|"
                 r"(?:mets|règle|regle)|(?:quel est l'état de|quel est l'etat de|où en est|ou en est))\s+(?P<reste>.+)$", c)
    if not m:
        return None
    reste = m.group("reste")
    mot = _n(reste)
    domaines = next((d for k, d in DOMAINES.items() if k in mot.split() or k + "s" in mot.split()), None)
    if domaines is None:
        return None  # pas une commande de maison (« ouvre godot », « éteins le pc »...)
    pourcent = re.search(r"(\d{1,3})\s*(?:%|pour cent|pourcent)", reste)
    verbe = m.group("v")
    if pourcent and verbe not in ("allume", "éteins", "eteins"):
        action = "regler"
    elif verbe == "allume":
        action = "allumer"
    elif verbe in ("éteins", "eteins"):
        action = "eteindre"
    elif verbe in ("ouvre", "monte"):
        action = "ouvrir"
    elif verbe in ("ferme", "baisse"):
        action = "fermer"
    elif verbe is None and not pourcent:
        action = "etat"
    else:
        return None
    cible = re.sub(r"\s*(?:à|a)?\s*\d{1,3}\s*(?:%|pour cent|pourcent)$", "", reste).strip()
    return {"action": action, "cible": cible, "domaines": domaines,
            "pourcent": int(pourcent.group(1)) if pourcent else None}


def executer(maison, demande):
    """Exécute la demande ; renvoie la phrase à dire."""
    trouve = maison.trouver(demande["cible"], demande["domaines"]) or maison.trouver(demande["cible"])
    if not trouve and maison.ambigus:
        return "Lequel, Salim ? " + ", ".join(maison.ambigus[:6]) + "."
    if not trouve:
        return "Je ne trouve aucun appareil nommé « " + demande["cible"] + " » dans Home Assistant."
    entite, _ = trouve
    nom = entite.get("attributes", {}).get("friendly_name", entite["entity_id"])
    domaine = entite["entity_id"].split(".")[0]
    action, pct = demande["action"], demande["pourcent"]
    if action == "etat":
        return "%s : %s." % (nom, entite.get("state", "inconnu"))
    if action == "allumer":
        maison.appeler(entite, "turn_on")
        return "J'allume " + nom + "."
    if action == "eteindre":
        maison.appeler(entite, "turn_off")
        return "J'éteins " + nom + "."
    if action == "ouvrir" and domaine == "cover":
        maison.appeler(entite, "open_cover")
        return "J'ouvre " + nom + "."
    if action == "fermer" and domaine == "cover":
        maison.appeler(entite, "close_cover")
        return "Je ferme " + nom + "."
    if action == "ouvrir":
        maison.appeler(entite, "turn_on")
        return "J'active " + nom + "."
    if action == "fermer":
        maison.appeler(entite, "turn_off")
        return "Je désactive " + nom + "."
    if action == "regler" and pct is not None:
        pct = max(0, min(100, pct))
        if domaine == "light":
            maison.appeler(entite, "turn_on", {"brightness_pct": pct})
        elif domaine == "cover":
            maison.appeler(entite, "set_cover_position", {"position": pct})
        elif domaine == "climate":
            maison.appeler(entite, "set_temperature", {"temperature": pct})
        else:
            return "Je ne sais pas régler " + nom + " à une valeur."
        return "%s réglé à %d." % (nom, pct)
    return "Je ne sais pas faire cela avec " + nom + "."

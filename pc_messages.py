"""pc_messages.py - JARVIS prépare des messages (WhatsApp, e-mail) pour tes contacts.

Principe de sécurité : JARVIS rédige, te montre le brouillon, puis ouvre WhatsApp ou ton logiciel de
messagerie avec le texte déjà écrit. Par défaut, c'est TOI qui appuies sur Entrée ou sur Envoyer.
Les contacts sont dans le fichier local contacts.json (rien n'est envoyé nulle part).
"""
import difflib
import json
import os
import re
import urllib.parse

from pc_docs import normaliser

CANAUX = {"whatsapp": "whatsapp", "watsap": "whatsapp", "whatsap": "whatsapp", "watsapp": "whatsapp",
          "sms": "sms", "texto": "sms", "mail": "email", "email": "email", "e-mail": "email", "courriel": "email"}
NOMS_CANAUX = "whatsapp|watsap|whatsap|watsapp|sms|texto|mail|email|e-mail|courriel"

RE_DEBUT = re.compile(
    r"^(?:envoie|écris|ecris|rédige|redige|fais|prépare|prepare)(?:-moi)?\s+(?:un |une |le )?"
    r"(?P<type>message|" + NOMS_CANAUX + r")\s+(?:(?:sur|par|via|en)\s+)?(?:(?P<canal>" + NOMS_CANAUX + r")\s+)?"
    r"(?:à|a|pour)\s+(?P<reste>.+)$")
RE_DIS = re.compile(r"^(?:dis à|dis a|préviens|previens)\s+(?P<reste>.+)$")
SEPARATEURS = [(":", True), (",", True), (" pour lui dire que ", False), (" pour lui dire ", False),
               (" pour dire que ", False), (" pour lui demander ", False), (" pour lui annoncer ", False),
               (" en disant que ", False), (" en disant ", False), (" disant que ", False), (" que ", False),
               (" pour ", False)]
RE_CANAL_FIN = re.compile(r"\s+(?:sur|par|via|en)\s+(" + NOMS_CANAUX + r")$")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_TEL = re.compile(r"\+?\d(?:[\d .-]{6,}\d)")
DETERMINANTS = re.compile(r"^(?:mon |ma |mes |le |la |les |l')+")


def analyser_message(c):
    """« envoie un message à Karim que j'arrive » ->
    {"canal": None|"whatsapp"|"email"|"sms", "nom": "karim", "texte": "j'arrive", "litteral": False} ou None."""
    original = c.strip()
    c = c.lower().strip(" .!?")
    canal = None
    m = RE_DEBUT.match(c)
    if m:
        brut = m.group("canal") or (m.group("type") if m.group("type") in CANAUX else None)
        canal = CANAUX.get(brut) if brut else None
        reste = m.group("reste")
    else:
        m = RE_DIS.match(c)
        if not m:
            return None
        reste = m.group("reste")
    debut, litteral, sep_len = None, False, 0
    for sep, lit in SEPARATEURS:
        i = reste.find(sep)
        if i > 0 and (debut is None or i < debut):
            debut, litteral, sep_len = i, lit, len(sep)
    if debut is None:
        nom, texte = reste, ""
    else:
        nom, texte = reste[:debut], reste[debut + sep_len:]
    m = RE_CANAL_FIN.search(nom.strip())
    if m:
        canal = canal or CANAUX[m.group(1)]
        nom = nom.strip()[:m.start()]
    texte = re.sub(r"^que\s+", "", texte.strip(" ,:"))
    if litteral and texte and original[-1:] in ("?", "!"):
        texte += original[-1]  # garde le point d'interrogation ou d'exclamation d'un texte dicté tel quel
    return {"canal": canal, "nom": DETERMINANTS.sub("", nom.strip()), "texte": texte, "litteral": litteral}


def nettoyer_brouillon(texte):
    """Retire guillemets, « Message : » et explications ajoutées par l'IA."""
    t = texte.strip()
    t = re.sub(r"^(?:voici (?:le|ton) message\s*:?|message\s*:)\s*", "", t, flags=re.I)
    t = t.strip().strip('"«»“”').strip()
    return " ".join(t.split())[:600]


def normaliser_numero(brut, code_pays="33"):
    """« 06 12 34 56 78 » -> « 33612345678 » (format international sans +) ; None si invalide."""
    chiffres = re.sub(r"\D", "", brut)
    if brut.strip().startswith("+"):
        pass
    elif chiffres.startswith("00"):
        chiffres = chiffres[2:]
    elif chiffres.startswith("0") and len(chiffres) == 10:
        chiffres = code_pays + chiffres[1:]
    return chiffres if 8 <= len(chiffres) <= 15 else None


def url_whatsapp(numero, texte):
    return "whatsapp://send?phone=%s&text=%s" % (numero, urllib.parse.quote(texte, safe=""))


def url_whatsapp_web(numero, texte):
    return "https://wa.me/%s?text=%s" % (numero, urllib.parse.quote(texte, safe=""))


def url_mailto(adresse, objet, corps):
    return "mailto:%s?subject=%s&body=%s" % (adresse, urllib.parse.quote(objet, safe=""),
                                             urllib.parse.quote(corps[:1500], safe=""))


class Contacts:
    def __init__(self, chemin):
        self.chemin = chemin
        self.donnees = {}
        if os.path.exists(chemin):
            try:
                with open(chemin, encoding="utf-8") as f:
                    self.donnees = json.load(f)
            except (OSError, ValueError):
                self.donnees = {}

    def _sauver(self):
        with open(self.chemin, "w", encoding="utf-8") as f:
            json.dump(self.donnees, f, ensure_ascii=False, indent=2)

    def ajouter(self, nom, telephone=None, email=None):
        cle = normaliser(nom).strip()
        fiche = self.donnees.setdefault(cle, {"nom": nom.strip().capitalize()})
        if telephone:
            fiche["telephone"] = telephone
        if email:
            fiche["email"] = email
        self._sauver()
        return fiche

    def supprimer(self, nom):
        trouve = self.trouver(nom)
        if trouve:
            self.donnees.pop(normaliser(trouve["nom"]).strip(), None)
            self._sauver()
        return trouve

    def noms(self):
        return sorted(f["nom"] for f in self.donnees.values())

    def trouver(self, nom):
        q = normaliser(DETERMINANTS.sub("", nom.lower())).strip()
        meilleur, score_max = None, 0.0
        for cle, fiche in self.donnees.items():
            s = 1.0 if q == cle else (0.9 if q and (q in cle or cle in q) else difflib.SequenceMatcher(None, q, cle).ratio())
            if s > score_max:
                meilleur, score_max = fiche, s
        return meilleur if score_max >= 0.75 else None


def analyser_contact(c):
    """« ajoute le contact maman numéro 06 12 34 56 78 » -> (nom, telephone|None, email|None) ou None."""
    c = c.lower().strip(" .!?")
    m = re.match(r"^(?:ajoute|enregistre|crée|cree|note)\s+(?:le |un |une )?(?:nouveau )?contact\s+(?P<reste>.+)$", c)
    if not m:
        return None
    reste = m.group("reste")
    email = RE_EMAIL.search(reste)
    tel = RE_TEL.search(reste)
    coupe = min([x.start() for x in (email, tel) if x] or [len(reste)])
    nom = re.sub(r"\b(?:numéro|numero|téléphone|telephone|email|e-mail|mail|adresse|avec|le|son|de)\b", " ", reste[:coupe])
    nom = " ".join(nom.strip(" ,:").split())
    return (nom, tel.group().strip() if tel else None, email.group() if email else None) if nom else None

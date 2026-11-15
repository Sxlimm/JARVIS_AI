"""pc_web.py - JARVIS cherche des informations sur Internet, puis l'IA locale rédige la réponse.

Seul le texte de la recherche quitte le PC (vers DuckDuckGo, Wikipédia, wttr.in et les sites lus).
La réponse est écrite en local par Ollama. Les pages web sont traitées comme des données,
jamais comme des instructions : le modèle ne peut rien exécuter.
Dépendance conseillée : pip install ddgs (sinon un mode de secours sans bibliothèque est utilisé).
"""
import html
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html.parser import HTMLParser

from pc_docs import jetons

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"
TIMEOUT = 8

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


def date_du_jour():
    d = datetime.now()
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


def domaine(url):
    return urllib.parse.urlparse(url).netloc.replace("www.", "")


def _get(url, data=None, max_octets=400_000, entetes=None):
    req = urllib.request.Request(
        url, data=data,
        headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9", **(entetes or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        brut = r.read(max_octets)
        type_contenu = r.headers.get("Content-Type", "")
        charset = r.headers.get_content_charset() or "utf-8"
    return brut.decode(charset, errors="replace"), type_contenu


def _nettoyer(texte):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", texte)).split())


# ---------------------------------------------------------------- recherche

def _ddgs(question, n):
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return []
    res = DDGS().text(question, region="fr-fr", max_results=n)
    return [{"titre": r.get("title", ""), "url": r.get("href", ""), "extrait": r.get("body", "")}
            for r in res if r.get("href")]


def _url_reelle(href):
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" in href:
        cible = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [""])[0]
        return cible or href
    return href


def _ddg_html(question, n):
    donnees = urllib.parse.urlencode({"q": question, "kl": "fr-fr"}).encode()
    texte, _ = _get("https://html.duckduckgo.com/html/", data=donnees)
    liens = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', texte, re.S)
    extraits = re.findall(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', texte, re.S)
    resultats = []
    for i, (href, titre) in enumerate(liens[:n]):
        resultats.append({"titre": _nettoyer(titre), "url": _url_reelle(href),
                          "extrait": _nettoyer(extraits[i]) if i < len(extraits) else ""})
    return resultats


def _wikipedia(question, n):
    url = ("https://fr.wikipedia.org/w/api.php?action=query&generator=search&gsrlimit=%d"
           "&prop=extracts&exintro=1&explaintext=1&exlimit=%d&format=json&gsrsearch=%s"
           % (n, n, urllib.parse.quote(question)))
    texte, _ = _get(url)
    pages = json.loads(texte).get("query", {}).get("pages", {})
    resultats = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        resultats.append({"titre": page.get("title", ""),
                          "url": "https://fr.wikipedia.org/?curid=" + str(page.get("pageid", "")),
                          "extrait": (page.get("extract") or "")[:1200]})
    return resultats


def rechercher(question, n=5):
    """Essaie DuckDuckGo (bibliothèque), puis DuckDuckGo (HTML), puis Wikipédia."""
    for moteur in (_ddgs, _ddg_html, _wikipedia):
        try:
            res = moteur(question, n)
        except Exception:
            continue
        if res:
            return res
    return []


# ---------------------------------------------------------------- lecture des pages

class _Texte(HTMLParser):
    IGNORE = {"script", "style", "nav", "header", "footer", "aside", "noscript", "svg",
              "form", "button", "iframe"}
    BLOCS = {"p", "li", "h1", "h2", "h3", "h4", "td"}

    def __init__(self):
        super().__init__()
        self.ignore = 0
        self.courant = []
        self.paragraphes = []

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORE:
            self.ignore += 1
        elif tag in self.BLOCS:
            self._fin()

    def handle_endtag(self, tag):
        if tag in self.IGNORE:
            self.ignore = max(0, self.ignore - 1)
        elif tag in self.BLOCS:
            self._fin()

    def handle_data(self, data):
        if not self.ignore:
            self.courant.append(data)

    def _fin(self):
        texte = " ".join("".join(self.courant).split())
        self.courant = []
        if len(texte) >= 50:
            self.paragraphes.append(texte)


def extraire_paragraphes(page_html):
    p = _Texte()
    p.feed(page_html)
    p._fin()
    return p.paragraphes[:200]


def meilleurs_passages(paragraphes, question, max_chars):
    """Garde les paragraphes qui parlent le plus de la question, dans l'ordre de la page."""
    mots = set(jetons(question))
    notes = []
    for i, para in enumerate(paragraphes):
        notes.append((len(mots & set(jetons(para))), -i, i))
    notes.sort(reverse=True)
    choisis, total = [], 0
    for note, _, i in notes:
        if choisis and note == 0:
            break
        if total + len(paragraphes[i]) > max_chars and choisis:
            continue
        choisis.append(i)
        total += len(paragraphes[i])
        if total >= max_chars:
            break
    return " ".join(paragraphes[i] for i in sorted(choisis))[:max_chars]


def lire_page(url, question, max_chars=900):
    if not url.lower().startswith(("http://", "https://")):
        return ""
    texte, type_contenu = _get(url)
    if "html" not in type_contenu.lower():
        return ""
    return meilleurs_passages(extraire_paragraphes(texte), question, max_chars)


def sources_web(question, nb=3, max_chars=900):
    resultats = rechercher(question, n=5)[:nb]

    def charger(r):
        texte = ""
        try:
            texte = lire_page(r["url"], question, max_chars)
        except Exception:
            pass
        if len(texte) < 200 and r.get("extrait"):
            texte = (r["extrait"] + " " + texte).strip()
        return {"titre": r["titre"], "url": r["url"], "texte": texte[:max_chars]}

    if not resultats:
        return []
    with ThreadPoolExecutor(max_workers=3) as pool:
        return [s for s in pool.map(charger, resultats) if s["texte"]]


# ---------------------------------------------------------------- quand chercher ?

DEBUTS = ("qui ", "qu'est-ce", "qu'est ce", "qu'est", "quel ", "quelle ", "quels ", "quelles ",
          "quand ", "où ", "ou est", "ou se trouve", "combien", "comment ", "pourquoi ",
          "c'est quoi", "c'est qui", "que signifie", "que veut dire", "définition", "definition",
          "explique", "dis-moi", "dis moi", "parle-moi de", "parle moi de",
          "y a-t-il", "est-ce que", "est ce que", "à quoi sert", "a quoi sert")
INDICES = ("sur internet", "sur le web", "sur le net", "en ligne", "actualité", "actualite",
           "dernières nouvelles", "dernieres nouvelles", "cours du ", "prix du ", "prix de ",
           "résultat du", "resultat du", "score du", "qui a gagné", "qui a gagne")
EXCLUS = (" tu ", " toi", " ton ", " ta ", " tes ", " t'", " vous ", " jarvis", "sais-tu",
          "peux-tu", "comment ça va", "comment ca va", "quelle heure", "quel jour", "quelle date")


def est_question_web(c):
    c = c.lower().strip(" ?!.")
    avec_espaces = " " + c + " "
    if any(k in avec_espaces for k in EXCLUS):
        return any(k in c for k in ("sur internet", "sur le web", "sur le net"))
    return c.startswith(DEBUTS) or any(k in c for k in INDICES)


# ---------------------------------------------------------------- météo

def _ville(commande):
    ignores = {"demain", "aujourd'hui", "ce", "cette", "la", "le", "semaine", "soir", "matin", "heure"}
    for m in re.finditer(r"\b(?:à|a|de|pour|sur|dans|en)\s+([a-zàâçéèêëîïôûùüÿœ' -]+)", commande):
        ville = re.split(r"\b(?:demain|aujourd'hui|ce soir|ce matin|cette semaine)\b",
                         m.group(1))[0].strip(" ?!.,'-")
        if len(ville) >= 2 and ville not in ignores:
            return ville
    return None


def meteo(commande):
    ville = _ville(commande.lower())
    url = "https://wttr.in/" + urllib.parse.quote(ville or "") + "?format=j1&lang=fr"
    texte, _ = _get(url)
    d = json.loads(texte)
    cur = d["current_condition"][0]
    desc = (cur.get("lang_fr") or cur.get("weatherDesc") or [{"value": ""}])[0]["value"].lower()
    lieu = ville or d["nearest_area"][0]["areaName"][0]["value"]
    aujourdhui, demain = d["weather"][0], d["weather"][1]
    return (f"Météo à {lieu} : {desc}, {cur['temp_C']} degrés, ressenti {cur['FeelsLikeC']}, "
            f"humidité {cur['humidity']} pour cent, vent {cur['windspeedKmph']} kilomètres par heure. "
            f"Aujourd'hui entre {aujourdhui['mintempC']} et {aujourdhui['maxtempC']} degrés, "
            f"demain entre {demain['mintempC']} et {demain['maxtempC']}.")

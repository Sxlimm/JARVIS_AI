"""pc_video.py - JARVIS cherche des vidéos (tutoriels YouTube) pour un problème, puis les ouvre.

Recherche : DuckDuckGo (vidéos), puis la page de résultats YouTube en secours. Rien n'est lu ni
téléchargé : JARVIS ne fait qu'ouvrir le lien dans ton navigateur quand tu le demandes.
"""
import json
import re
import urllib.parse

from pc_web import _get

MOTS_VIDEO = ("vidéo", "video", "vidéos", "videos", "tuto", "tutos", "tutoriel", "tutoriels")
VERBES_CHERCHE = ("cherche", "recherche", "trouve", "propose", "montre", "donne", "regarde")
VERBES_OUVRE = ("ouvre", "lance", "mets", "joue")
PRONOMS = {"ça", "ca", "cela", "ce problème", "ce probleme", "mon problème", "mon probleme",
           "le problème", "le probleme", "là-dessus", "la-dessus", "là dessus", "la dessus",
           "dessus", "ce sujet", "ce que je viens de dire", "mon souci", "ce souci"}
ORDRES = {"premier": 1, "première": 1, "premiere": 1, "1ère": 1, "1ere": 1, "un": 1, "une": 1, "1": 1,
          "deuxième": 2, "deuxieme": 2, "seconde": 2, "second": 2, "deux": 2, "2": 2,
          "troisième": 3, "troisieme": 3, "trois": 3, "3": 3,
          "quatrième": 4, "quatrieme": 4, "quatre": 4, "4": 4,
          "cinquième": 5, "cinquieme": 5, "cinq": 5, "5": 5}
CHOIX = re.compile(r"^(?:ouvre|lance|mets|joue|regarde)(?:-moi| moi)?\s+(?:la |le |l')?"
                   r"(?P<mot>vidéo|video|résultat|resultat|lien)?\s*(?:numéro |numero |n° )?"
                   r"(?P<ordre>[\wèéê]+)?\s*$")


def _contient(c, mots):
    return any(re.search(r"\b" + re.escape(m) + r"\b", c) for m in mots)


def choix_video(c):
    """« ouvre la deuxième », « ouvre la vidéo trois »... Renvoie le numéro (1 à 5) ou None."""
    m = CHOIX.match(c.lower().strip(" ?!."))
    if not m:
        return None
    if m.group("ordre"):
        return ORDRES.get(m.group("ordre"))
    return 1 if m.group("mot") else None


def _nettoyer_sujet(texte):
    texte = re.sub(r"\b(?:s'il te pla[iî]t|s'il vous pla[iî]t|stp|svp)\b", " ", texte)
    texte = re.sub(r"\b(?:sur|dans|de)\s+youtube\b|\byoutube\b", " ", texte)
    return " ".join(texte.strip(" ,;.:-").split())


def analyser(c):
    """Renvoie {"sujet": str|None, "ouvrir": bool} si c'est une demande de vidéo, sinon None."""
    c = c.lower().strip(" ?!.")
    video = _contient(c, MOTS_VIDEO)
    youtube = "youtube" in c and _contient(c, VERBES_CHERCHE)
    if not (video or youtube):
        return None
    if not (_contient(c, VERBES_CHERCHE) or _contient(c, VERBES_OUVRE)):
        return None
    ouvrir = _contient(c, VERBES_OUVRE) and not _contient(c, ("cherche", "recherche", "trouve", "propose"))

    sujet = None
    m = re.search(r"\b(?:vidéos?|videos?|tutoriels?|tutos?)\s+(?:youtube\s+)?(?:sur|pour|à propos de|"
                  r"qui explique|qui montre|qui parle de|de|d'|afin de)\s*(.+)$", c)
    if m:
        sujet = _nettoyer_sujet(m.group(1))
    if not sujet:
        m = re.search(r"\b(?:problème|probleme|souci|bug|panne)\s+(?:avec|de|d'|sur|pour)\s*(.+?)"
                      r"(?:\s*[,;.]\s*|\s+(?:trouve|cherche|montre|propose)|$)", c)
        if m:
            sujet = _nettoyer_sujet(m.group(1))
    if not sujet and youtube:
        m = re.search(r"\b(?:cherche|recherche|trouve)(?:-moi)?\s+(.+)$", c)
        if m:
            sujet = _nettoyer_sujet(m.group(1))
    if sujet in PRONOMS or (sujet and len(sujet) < 3):
        sujet = None
    return {"sujet": sujet, "ouvrir": ouvrir}


def requete(sujet):
    sujet = sujet.strip()
    if not re.search(r"tuto|comment|solution|résoudre|resoudre|réparer|reparer", sujet):
        sujet += " tutoriel"
    return sujet


def duree_parlee(duree):
    """« 12:34 » -> « 12 minutes » ; « 1:02:10 » -> « 1 heure »."""
    parties = [p for p in re.findall(r"\d+", duree or "")]
    if len(parties) == 3:
        return parties[0] + " heure" + ("s" if int(parties[0]) > 1 else "")
    if len(parties) == 2:
        minutes = int(parties[0])
        return "moins d'une minute" if minutes == 0 else "%d minute%s" % (minutes, "s" if minutes > 1 else "")
    return ""


# ---------------------------------------------------------------- recherche

def _youtube_seulement(videos):
    yt = [v for v in videos if re.match(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/", v["url"])]
    return yt or [v for v in videos if v["url"].startswith("https://")]


def _ddgs_videos(q, n):
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return []
    res = DDGS().videos(q, region="fr-fr", max_results=n * 3)
    return [{"titre": r.get("title", ""), "url": r.get("content") or r.get("embed_url") or "",
             "duree": r.get("duration", "") or "", "chaine": r.get("uploader") or r.get("publisher") or ""}
            for r in res]


def _trouver_videos(noeud, sortie):
    if isinstance(noeud, dict):
        if "videoRenderer" in noeud:
            v = noeud["videoRenderer"]
            try:
                titre = v["title"]["runs"][0]["text"]
                sortie.append({
                    "titre": titre, "url": "https://www.youtube.com/watch?v=" + v["videoId"],
                    "duree": v.get("lengthText", {}).get("simpleText", ""),
                    "chaine": (v.get("ownerText", {}).get("runs") or [{}])[0].get("text", "")})
            except (KeyError, IndexError, TypeError):
                pass
        for valeur in noeud.values():
            _trouver_videos(valeur, sortie)
    elif isinstance(noeud, list):
        for element in noeud:
            _trouver_videos(element, sortie)


def analyser_page_youtube(page_html):
    m = re.search(r"var ytInitialData = (\{.*?\});\s*</script>", page_html, re.S)
    if not m:
        return []
    sortie = []
    _trouver_videos(json.loads(m.group(1)), sortie)
    return sortie


def _youtube_html(q, n):
    url = "https://www.youtube.com/results?hl=fr&search_query=" + urllib.parse.quote_plus(q)
    texte, _ = _get(url, max_octets=3_000_000, entetes={"Cookie": "SOCS=CAI; CONSENT=YES+1"})
    return analyser_page_youtube(texte)


def rechercher_videos(q, n=5):
    for moteur in (_ddgs_videos, _youtube_html):
        try:
            videos = _youtube_seulement([v for v in moteur(q, n) if v.get("url") and v.get("titre")])
        except Exception:
            continue
        vus, uniques = set(), []
        for v in videos:
            if v["url"] not in vus:
                vus.add(v["url"])
                uniques.append(v)
        if uniques:
            return uniques[:n]
    return []

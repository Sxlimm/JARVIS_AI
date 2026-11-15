"""pc_docs.py - JARVIS lit tes documents (txt, md, csv, pdf, docx) et retrouve les passages utiles.
100 % local, sans modèle supplémentaire : recherche par mots-clés (BM25), légère pour 8 Go de RAM.
Dépendances optionnelles : pypdf (pour les PDF), python-docx (pour les Word).
"""
import math
import os
import re
import threading
import unicodedata
from collections import Counter

EXTENSIONS = {".txt", ".md", ".csv", ".pdf", ".docx"}
TAILLE_MAX = 30 * 1024 * 1024  # fichiers plus gros ignorés
TAILLE_EXTRAIT = 600

MOTS_VIDES = set("""
alors aussi avec avez avoir cela celle celui ces cette chez comme dans des donc dont elle elles
est les leur leurs mais meme mes mon nous ont par pas pour que quel quelle quels quelles qui
sans ses son sont sur tes ton tous tout tres une vos votre vous etre fait faire peux peut
quand comment combien pourquoi parle parler disent dit dis document documents
""".split())


def normaliser(texte):
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(ch for ch in texte if unicodedata.category(ch) != "Mn")


def jetons(texte):
    mots = re.findall(r"[a-z0-9]{3,}", normaliser(texte))
    resultat = []
    for m in mots:
        if m in MOTS_VIDES:
            continue
        if len(m) > 4 and m[-1] in "sx":  # pluriels simples
            m = m[:-1]
        resultat.append(m)
    return resultat


def lire_fichier(chemin):
    ext = os.path.splitext(chemin)[1].lower()
    if ext in (".txt", ".md", ".csv"):
        for enc in ("utf-8-sig", "cp1252"):
            try:
                with open(chemin, encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        return ""
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join((page.extract_text() or "") for page in PdfReader(chemin).pages)
    if ext == ".docx":
        import docx
        d = docx.Document(chemin)
        parties = [p.text for p in d.paragraphs]
        for tableau in d.tables:
            for ligne in tableau.rows:
                parties.append(" | ".join(cell.text for cell in ligne.cells))
        return "\n\n".join(parties)
    return ""


def decouper(texte, taille=TAILLE_EXTRAIT):
    paragraphes = [p.strip() for p in re.split(r"\n\s*\n", texte) if p.strip()]
    morceaux, courant = [], ""
    for p in paragraphes:
        phrases = [p] if len(p) <= taille else re.split(r"(?<=[.!?])\s+", p)
        for ph in phrases:
            while len(ph) > taille:  # phrase interminable : coupe brute
                if courant:
                    morceaux.append(courant)
                    courant = ""
                morceaux.append(ph[:taille])
                ph = ph[taille:]
            if len(courant) + len(ph) + 1 > taille and courant:
                morceaux.append(courant)
                courant = ph
            else:
                courant = (courant + " " + ph).strip()
    if courant:
        morceaux.append(courant)
    return morceaux


class Docs:
    def __init__(self, dossiers):
        self.dossiers = dossiers
        self.chunks = []      # {"source", "texte", "tf", "len"}
        self.df = Counter()
        self.fichiers = []
        self.erreurs = []
        self.pret = False
        self.verrou = threading.Lock()

    def reindex(self):
        chunks, df, fichiers, erreurs = [], Counter(), [], []
        for dossier in self.dossiers:
            for racine, sous_dossiers, noms in os.walk(dossier):
                sous_dossiers[:] = [d for d in sous_dossiers if not d.startswith(".")]
                for nom in noms:
                    chemin = os.path.join(racine, nom)
                    if os.path.splitext(nom)[1].lower() not in EXTENSIONS or nom.startswith("~$"):
                        continue
                    try:
                        if os.path.getsize(chemin) > TAILLE_MAX:
                            erreurs.append(nom + " (trop gros)")
                            continue
                        texte = lire_fichier(chemin)
                    except ImportError:
                        erreurs.append(nom + " (bibliothèque manquante : pypdf ou python-docx)")
                        continue
                    except Exception as exc:
                        erreurs.append(nom + " (" + type(exc).__name__ + ")")
                        continue
                    morceaux = decouper(texte)
                    if not morceaux:
                        erreurs.append(nom + " (aucun texte lisible)")
                        continue
                    fichiers.append(nom)
                    for m in morceaux:
                        tf = Counter(jetons(m))
                        if not tf:
                            continue
                        chunks.append({"source": nom, "texte": m, "tf": tf, "len": sum(tf.values())})
                        df.update(tf.keys())
        with self.verrou:
            self.chunks, self.df, self.fichiers, self.erreurs = chunks, df, fichiers, erreurs
            self.pret = True
        return len(fichiers), len(chunks)

    def chercher(self, question, k=3):
        with self.verrou:
            chunks, df = self.chunks, self.df
        mots = set(jetons(question))
        if not chunks or not mots:
            return []
        n = len(chunks)
        moyenne = sum(c["len"] for c in chunks) / n
        resultats = []
        for c in chunks:
            score = 0.0
            for m in mots:
                f = c["tf"].get(m, 0)
                if not f:
                    continue
                idf = math.log(1 + (n - df[m] + 0.5) / (df[m] + 0.5))
                score += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * c["len"] / moyenne))
            if score > 0:
                resultats.append({"source": c["source"], "texte": c["texte"], "score": score})
        resultats.sort(key=lambda r: r["score"], reverse=True)
        return resultats[:k]

    def liste(self):
        return list(self.fichiers)

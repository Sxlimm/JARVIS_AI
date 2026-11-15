"""pc_diag.py - Diagnostic intégré : « JARVIS fais un diagnostic ».

Teste un par un les éléments dont JARVIS dépend et écrit un rapport (diagnostic.txt). Le rapport ne
contient ni mot de passe, ni jeton, ni contact, ni message : seulement l'état des composants et les
dernières erreurs du journal (chemins personnels masqués). Tu peux l'envoyer pour qu'on te dépanne.
"""
import importlib.util
import json
import os
import platform
import socket
import sys
import tempfile
import time
import urllib.request
from datetime import datetime

OK, ATTENTION, ERREUR, INFO = "OK", "ATTENTION", "ERREUR", "INFO"

REQUIS = {"vosk": "vosk", "sounddevice": "sounddevice", "pyttsx3": "pyttsx3", "pyautogui": "pyautogui",
          "pyperclip": "pyperclip", "psutil": "psutil", "PIL": "pillow"}
FACULTATIFS = {"pypdf": "pypdf (lire les PDF)", "docx": "python-docx (lire les Word)", "ddgs": "ddgs (recherche web)",
               "pygetwindow": "pygetwindow (coller le code, fermer des logiciels)",
               "uiautomation": "uiautomation (voir l'écran)", "winocr": "winocr (lire le texte de l'écran)",
               "faster_whisper": "faster-whisper (meilleure compréhension)", "piper": "piper-tts (voix naturelle)",
               "numpy": "numpy"}
PIP = {"pillow": "pillow", "pypdf (lire les PDF)": "pypdf", "python-docx (lire les Word)": "python-docx",
       "ddgs (recherche web)": "ddgs", "pygetwindow (coller le code, fermer des logiciels)": "pygetwindow",
       "uiautomation (voir l'écran)": "uiautomation", "winocr (lire le texte de l'écran)": "winocr",
       "faster-whisper (meilleure compréhension)": "faster-whisper", "piper-tts (voix naturelle)": "piper-tts"}


def _present(module):
    try:
        return importlib.util.find_spec(module) is not None
    except (ValueError, ImportError):
        return module in sys.modules  # module déjà chargé mais sans description : il est bien là


def _manquants(modules):
    return [nom for mod, nom in modules.items() if not _present(mod)]


def verif_paquets(c):
    requis = _manquants(REQUIS)
    facultatifs = _manquants(FACULTATIFS)
    if requis:
        cmd = " ".join(PIP.get(n, n) for n in requis)
        return ERREUR, "Paquets indispensables absents : %s. Dans PowerShell : py -m pip install %s" % (", ".join(requis), cmd)
    if facultatifs:
        cmd = " ".join(PIP.get(n, n.split()[0]) for n in facultatifs)
        return ATTENTION, "Fonctions limitées, paquets absents : %s. Pour les installer : py -m pip install %s" % (
            ", ".join(facultatifs), cmd)
    return OK, "Tous les paquets sont présents."


def verif_systeme(c):
    version = platform.version()
    release = platform.release()
    try:
        if platform.system() == "Windows" and release == "10" and int(version.split(".")[-1]) >= 22000:
            release = "11"
    except ValueError:
        pass
    return INFO, "%s %s, Python %s." % (platform.system(), release, sys.version.split()[0])


def verif_memoire(c):
    import psutil
    m = psutil.virtual_memory()
    libre, total = m.available / 1024 ** 3, m.total / 1024 ** 3
    if libre < 1.0:
        return ERREUR, "Seulement %.1f Go libres sur %.1f Go : JARVIS va ramer. Ferme des programmes ou coupe Whisper." % (libre, total)
    if libre < 1.8:
        return ATTENTION, "%.1f Go libres sur %.1f Go : juste pour Ollama, Whisper et Piper en même temps." % (libre, total)
    return OK, "%.1f Go libres sur %.1f Go." % (libre, total)


def verif_micro(c):
    import sounddevice as sd
    try:
        appareil = sd.query_devices(kind="input")
    except Exception as exc:
        return ERREUR, "Aucun micro par défaut : %s. Vérifie Paramètres > Confidentialité > Microphone." % exc
    try:
        sd.check_input_settings(channels=1, samplerate=16000)
    except Exception as exc:
        return ERREUR, "Le micro « %s » refuse 16 kHz mono : %s" % (appareil.get("name", "?"), exc)
    return OK, "Micro par défaut : %s." % appareil.get("name", "?")


def verif_vosk(c):
    if not os.path.isdir(c.vosk_dir):
        return ERREUR, "Dossier du modèle vocal absent : %s. Lance INSTALLER.bat." % os.path.basename(c.vosk_dir)
    manque = [d for d in ("am", "conf", "graph") if not os.path.isdir(os.path.join(c.vosk_dir, d))]
    if manque:
        return ERREUR, "Modèle vocal incomplet (manque : %s). Re-télécharge vosk-model-small-fr-0.22." % ", ".join(manque)
    return OK, "Modèle vocal Vosk présent."


def verif_ollama(c):
    if not c.ollama_actif():
        return ERREUR, "Ollama ne répond pas. Lance-le (icône Ollama) ou tape « ollama serve »."
    modeles = c.lister_modeles()
    manque = [m for m in (c.model_name,) if m not in modeles]
    if manque:
        return ERREUR, "Ollama répond mais le modèle %s est absent. Tape : ollama pull %s" % (manque[0], manque[0])
    detail = "Ollama répond, %d modèle(s) installé(s), modèle actuel %s." % (len(modeles), c.model_name)
    if c.model_code not in modeles:
        return ATTENTION, detail + " Modèle de code absent : ollama pull %s" % c.model_code
    return OK, detail


def verif_vitesse(c):
    """Petit test de génération : mesure la vitesse réelle du modèle sur ce PC."""
    if not c.ollama_actif():
        return INFO, "Test sauté (Ollama absent)."
    charge = {"model": c.model_name, "stream": False, "keep_alive": "10m",
              "options": {"num_predict": 12, "temperature": 0},
              "messages": [{"role": "user", "content": "Compte de un à dix, en lettres."}]}
    debut = time.time()
    try:
        with urllib.request.urlopen(c.requete_ollama(json.dumps(charge).encode("utf-8")), timeout=120) as r:
            rep = json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        return ERREUR, "Le test de génération a échoué : %s" % exc
    duree = time.time() - debut
    n, t = rep.get("eval_count", 0), rep.get("eval_duration", 0)
    charge_s = rep.get("load_duration", 0) / 1e9
    vitesse = n / (t / 1e9) if n and t else 0
    detail = "%.1f mots/s environ (%d éléments en %.1f s, dont %.1f s de chargement du modèle)." % (vitesse, n, duree, charge_s)
    if vitesse and vitesse < 2:
        return ATTENTION, detail + " Très lent : prends un modèle plus petit (qwen3.5:2b ou qwen2.5:1.5b)."
    if vitesse and vitesse < 5:
        return ATTENTION, detail + " Lent mais utilisable pour de courtes réponses."
    return OK, detail


def verif_whisper(c):
    if not _present("faster_whisper"):
        return ATTENTION, "faster-whisper absent : JARVIS utilise seulement Vosk (moins bon sur les noms étrangers)."
    if not c.whisper.pret:
        return ATTENTION, "Whisper n'est pas chargé%s. Au premier lancement il se télécharge (150 Mo, Internet requis)." % (
            " (" + c.whisper.erreur[:120] + ")" if c.whisper.erreur else " (encore en cours ?)")
    debut = time.time()
    try:
        c.whisper.transcrire(b"\x00\x00" * 16000)
    except Exception as exc:
        return ERREUR, "Whisper est chargé mais plante à la transcription : %s" % exc
    return OK, "Whisper (%s) fonctionne, %.1f s pour 1 s d'audio." % (c.whisper.taille, time.time() - debut)


def verif_voix(c):
    fichier = os.path.join(c.dossier_voix, c.voix_piper)
    if c.piper.pret:
        debut = time.time()
        try:
            import wave
            chemin = os.path.join(tempfile.gettempdir(), "jarvis_test_voix.wav")
            with wave.open(chemin, "wb") as wav:
                (c.piper.voix.synthesize_wav if hasattr(c.piper.voix, "synthesize_wav") else c.piper.voix.synthesize)("Test.", wav)
            os.remove(chemin)
        except Exception as exc:
            return ERREUR, "Piper est chargé mais la synthèse échoue : %s" % exc
        return OK, "Voix Piper fonctionne (%.1f s pour une courte phrase)." % (time.time() - debut)
    voix = []
    try:
        voix = [v.name for v in c.tts.getProperty("voices")]
    except Exception:
        pass
    francaise = [v for v in voix if any(k in v.lower() for k in ("french", "français", "francais", "hortense", "julie", "paul", "fr-fr"))]
    base = "Voix Piper absente (%s)" % ("fichier absent" if not os.path.exists(fichier) else "non chargée")
    if francaise:
        return ATTENTION, base + " : JARVIS utilise la voix Windows (%s). Pour une voix naturelle, relance INSTALLER.bat." % francaise[0]
    return ERREUR, base + " et aucune voix française Windows : ajoute-la dans Paramètres > Heure et langue > Voix."


def verif_ecran(c):
    morceaux = []
    statut = OK
    try:
        import uiautomation as auto
        auto.GetForegroundControl()
        morceaux.append("UI Automation répond")
    except Exception as exc:
        morceaux.append("UI Automation indisponible (%s)" % str(exc)[:60])
        statut = ATTENTION
    try:
        import pyautogui
        import winocr
        image = pyautogui.screenshot()
        try:
            winocr.recognize_pil_sync(image, "fr")
            morceaux.append("OCR français OK")
        except Exception:
            winocr.recognize_pil_sync(image, "en")
            morceaux.append("OCR : pack de langue française absent (Paramètres > Heure et langue > Langue), anglais seul")
            statut = ATTENTION
    except ImportError:
        morceaux.append("OCR indisponible : py -m pip install winocr")
        statut = ATTENTION
    except Exception as exc:
        morceaux.append("OCR en erreur (%s)" % str(exc)[:60])
        statut = ATTENTION
    return statut, ". ".join(morceaux) + "."


def verif_web(c):
    if not c.interface_web:
        return INFO, "Interface web désactivée (INTERFACE_WEB = False)."
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/" % c.port_web, timeout=4) as r:
            if r.status == 200:
                return OK, "Interface web active sur le port %d%s." % (
                    c.port_web, " et ouverte au réseau" if c.acces_reseau else " (ce PC seulement)")
    except Exception as exc:
        return ERREUR, "Interface web injoignable sur le port %d : %s" % (c.port_web, exc)
    return ERREUR, "Interface web : réponse inattendue."


def verif_internet(c):
    try:
        socket.create_connection(("duckduckgo.com", 443), timeout=4).close()
        return OK, "Internet joignable (recherche web, météo, vidéos)."
    except OSError:
        return ATTENTION, "Pas d'Internet : la recherche web, la météo et les vidéos ne marcheront pas (le reste oui)."


def verif_donnees(c):
    morceaux = []
    if c.logiciels.pret:
        morceaux.append("%d logiciels connus" % len(c.logiciels.entrees))
    else:
        morceaux.append("liste des logiciels pas encore prête")
    if c.docs.pret:
        morceaux.append("%d document(s) lus" % len(c.docs.fichiers) + (" (non lus : %d)" % len(c.docs.erreurs) if c.docs.erreurs else ""))
    else:
        morceaux.append("documents pas encore lus")
    morceaux.append("%d contact(s)" % len(c.contacts.donnees))
    morceaux.append("%d rappel(s) en attente" % len(c.rappels.liste))
    statut = OK if c.logiciels.pret and c.docs.pret else ATTENTION
    return statut, ", ".join(morceaux) + "."


def verif_maison(c):
    if not c.maison.configuree:
        return INFO, "Home Assistant non configuré (facultatif)."
    try:
        c.maison._requete("/api/")
        return OK, "Home Assistant répond, %d appareils vus." % len(c.maison.entites())
    except Exception as exc:
        return ERREUR, "Home Assistant injoignable : %s" % exc


def verif_fichiers(c):
    try:
        chemin = os.path.join(c.app_dir, ".test_ecriture")
        with open(chemin, "w") as f:
            f.write("ok")
        os.remove(chemin)
    except OSError as exc:
        return ERREUR, "JARVIS ne peut pas écrire dans son dossier (mémoire, journal) : %s" % exc
    return OK, "Écriture possible dans le dossier de JARVIS."


def derniers_erreurs(c, maximum=6):
    journal = os.path.join(c.app_dir, "jarvis.log")
    if not os.path.exists(journal):
        return []
    try:
        with open(journal, encoding="utf-8", errors="replace") as f:
            lignes = f.readlines()[-400:]
    except OSError:
        return []
    err = [l.strip() for l in lignes if " ERROR " in l or "Traceback" in l or l.startswith(("  File", "ImportError", "ModuleNotFound"))]
    return err[-maximum:]


VERIFICATIONS = [("Paquets Python", verif_paquets), ("Système", verif_systeme), ("Mémoire", verif_memoire),
                 ("Micro", verif_micro), ("Modèle vocal Vosk", verif_vosk), ("Ollama", verif_ollama),
                 ("Vitesse du modèle", verif_vitesse), ("Whisper", verif_whisper), ("Voix", verif_voix),
                 ("Lecture de l'écran", verif_ecran), ("Interface web", verif_web), ("Internet", verif_internet),
                 ("Données (logiciels, documents...)", verif_donnees), ("Maison connectée", verif_maison),
                 ("Dossier de JARVIS", verif_fichiers)]


def lancer(c, progression=None):
    """Exécute toutes les vérifications. Renvoie {"lignes": [(statut, nom, détail)], "texte": rapport, "compte": {...}}."""
    lignes = []
    for i, (nom, fonction) in enumerate(VERIFICATIONS, 1):
        if progression:
            progression("Diagnostic %d/%d : %s..." % (i, len(VERIFICATIONS), nom))
        try:
            statut, detail = fonction(c)
        except Exception as exc:
            statut, detail = ERREUR, "La vérification a planté : %s: %s" % (type(exc).__name__, exc)
        lignes.append((statut, nom, detail))
    compte = {s: sum(1 for l in lignes if l[0] == s) for s in (OK, ATTENTION, ERREUR, INFO)}
    en_tete = "DIAGNOSTIC JARVIS - %s" % datetime.now().strftime("%d/%m/%Y %H:%M")
    corps = ["[%s] %s : %s" % l for l in lignes]
    resume = "Résumé : %d OK, %d attention, %d erreur(s)." % (compte[OK], compte[ATTENTION], compte[ERREUR])
    erreurs = derniers_erreurs(c)
    texte = "\n".join([en_tete, ""] + corps + ["", resume] + (["", "Dernières erreurs du journal :"] + erreurs if erreurs else []))
    home = os.path.expanduser("~")
    texte = texte.replace(home, "~").replace(home.replace("\\", "/"), "~")
    return {"lignes": lignes, "texte": texte, "compte": compte}

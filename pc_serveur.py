"""pc_serveur.py - Interface web de JARVIS : parler à JARVIS depuis un navigateur ou un téléphone.

Sécurité : un jeton secret est exigé pour chaque message (fichier jarvis_jeton.txt). Par défaut le serveur
n'écoute que ce PC (127.0.0.1). Pour le téléphone, active ACCES_RESEAU dans jarvis.py et passe par
Tailscale (réseau privé chiffré) : n'ouvre JAMAIS ce port sur Internet depuis ta box.
"""
import hmac
import http.server
import json
import os
import secrets
import threading

PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>JARVIS</title>
<style>
body{margin:0;background:#101820;color:#e8f1f5;font-family:system-ui,sans-serif;display:flex;flex-direction:column;height:100dvh}
#log{flex:1;overflow-y:auto;padding:14px}
.m{margin:8px 0;padding:10px 12px;border-radius:12px;max-width:85%;white-space:pre-wrap;word-wrap:break-word}
.v{background:#1f3a4d;margin-left:auto}.j{background:#16252f;border:1px solid #2b4a5e}
form{display:flex;gap:8px;padding:10px;background:#0b1117}
input{flex:1;padding:12px;border-radius:10px;border:1px solid #2b4a5e;background:#16252f;color:inherit;font-size:16px}
button{padding:12px 16px;border:0;border-radius:10px;background:#2aa6c9;color:#04141b;font-weight:700;font-size:16px}
</style></head><body><div id="log"></div>
<form id="f"><input id="t" autocomplete="off" placeholder="Parlez à JARVIS..."><button>Envoyer</button></form>
<script>
const p=new URLSearchParams(location.search);
if(p.get("jeton")){localStorage.setItem("jarvis_jeton",p.get("jeton"));history.replaceState(null,"",location.pathname);}
const jeton=localStorage.getItem("jarvis_jeton")||"";
const log=document.getElementById("log"),t=document.getElementById("t");
function ajouter(classe,texte){const d=document.createElement("div");d.className="m "+classe;d.textContent=texte;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
document.getElementById("f").addEventListener("submit",async e=>{
  e.preventDefault();const texte=t.value.trim();if(!texte)return;t.value="";ajouter("v",texte);
  const attente=ajouter("j","...");
  try{
    const r=await fetch("/api/message",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+jeton},body:JSON.stringify({texte})});
    attente.remove();
    if(r.status===401){ajouter("j","Jeton invalide : ouvrez l'adresse affichée dans la fenêtre de JARVIS.");return;}
    const d=await r.json();(d.reponses||[]).forEach(x=>ajouter("j",x));
  }catch(err){attente.remove();ajouter("j","JARVIS ne répond pas.");}
});
ajouter("j","Bonjour Salim. Écrivez votre demande.");
</script></body></html>"""


def charger_jeton(chemin):
    """Lit le jeton secret, ou le crée au premier lancement."""
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as f:
            jeton = f.read().strip()
        if len(jeton) >= 16:
            return jeton
    jeton = secrets.token_urlsafe(18)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(jeton)
    return jeton


def creer_serveur(repondre, jeton, hote="127.0.0.1", port=8765):
    class Gestionnaire(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _envoyer(self, code, contenu, type_contenu="application/json; charset=utf-8"):
            donnees = contenu.encode("utf-8") if isinstance(contenu, str) else contenu
            self.send_response(code)
            self.send_header("Content-Type", type_contenu)
            self.send_header("Content-Length", str(len(donnees)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(donnees)

        def _autorise(self):
            recu = self.headers.get("Authorization", "")
            return hmac.compare_digest(recu.encode("utf-8"), ("Bearer " + jeton).encode("utf-8"))

        def do_GET(self):
            if self.path.split("?")[0] == "/":
                self._envoyer(200, PAGE, "text/html; charset=utf-8")
            else:
                self._envoyer(404, json.dumps({"erreur": "introuvable"}))

        def do_POST(self):
            if self.path != "/api/message":
                self._envoyer(404, json.dumps({"erreur": "introuvable"}))
                return
            if not self._autorise():
                self._envoyer(401, json.dumps({"erreur": "jeton invalide"}))
                return
            try:
                taille = int(self.headers.get("Content-Length", "0"))
                if not 0 < taille <= 4096:
                    raise ValueError
                texte = str(json.loads(self.rfile.read(taille)).get("texte", "")).strip()[:500]
                if not texte:
                    raise ValueError
            except (ValueError, TypeError):
                self._envoyer(400, json.dumps({"erreur": "message invalide"}))
                return
            self._envoyer(200, json.dumps({"reponses": repondre(texte)}, ensure_ascii=False))

    serveur = http.server.ThreadingHTTPServer((hote, port), Gestionnaire)
    serveur.daemon_threads = True
    return serveur


def demarrer(repondre, jeton, hote="127.0.0.1", port=8765):
    serveur = creer_serveur(repondre, jeton, hote, port)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur

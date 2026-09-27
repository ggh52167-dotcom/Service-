from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from datetime import datetime, timedelta
import sqlite3, os, time

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
DB = os.path.join(os.path.dirname(__file__), "site.db")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "3004")

DEFAULT_SETTINGS = {
    "ads_enabled": "1",
    "rewarded_enabled": "0",
    "ad_top": "",
    "ad_middle": "",
    "ad_bottom": "",
    "ad_service": "",
    "rewarded_code": "",
    "currency_rates": "EUR=1;USD=1.08;GBP=0.86;XOF=655.957;NGN=1500;GHS=16.5",
}

DEFAULT_SERVICES = [
    ("Générateur de code QR", "Crée un QR code à partir d'un lien ou d'un texte.", "qr", 1),
    ("Convertisseur de monnaie", "Convertit des montants entre devises avec des taux configurables.", "currency", 1),
    ("Convertisseur de texte", "Transforme rapidement un texte en majuscules, minuscules ou titre.", "text", 1),
    ("Compteur de mots", "Analyse le nombre de mots et de caractères d'un texte.", "counter", 0),
    ("Générateur de mot de passe", "Génère un mot de passe aléatoire côté navigateur.", "password", 1),
    ("Formateur JSON", "Vérifie et met en forme un objet JSON.", "json", 1),
    ("Générateur de slug", "Transforme un titre en URL propre.", "slug", 0),
    ("Calculateur de pourcentage", "Calcule rapidement un pourcentage.", "percent", 0),
]

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute("""CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE, reward_required INTEGER DEFAULT 0, active INTEGER DEFAULT 1)""")
    con.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT, event TEXT, service_id INTEGER,
        created_at TEXT NOT NULL)""")
    for k,v in DEFAULT_SETTINGS.items():
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
    if con.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
        for row in DEFAULT_SERVICES:
            con.execute("INSERT INTO services(name,description,slug,reward_required) VALUES(?,?,?,?)", row)
    con.commit(); con.close()

def settings():
    con=db()
    data={r["key"]:r["value"] for r in con.execute("SELECT key,value FROM settings")}
    con.close()
    return data

def log_event(event, service_id=None):
    con=db()
    con.execute("INSERT INTO events(ip,event,service_id,created_at) VALUES(?,?,?,?)",
                (request.headers.get("X-Forwarded-For", request.remote_addr), event, service_id, datetime.utcnow().isoformat()))
    con.commit(); con.close()

def rate_limit(key, seconds=60):
    now=time.time()
    data=session.get("limits", {})
    last=data.get(key,0)
    if now-last < seconds: return False
    data[key]=now
    session["limits"]=data
    return True

def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapped

@app.context_processor
def inject():
    return {"site_settings": settings()}

@app.route("/")
def home():
    con=db()
    services=con.execute("SELECT * FROM services WHERE active=1 ORDER BY id DESC").fetchall()
    con.close()
    log_event("page_view")
    return render_template("index.html", services=services)

@app.route("/service/<slug>")
def service(slug):
    con=db()
    s=con.execute("SELECT * FROM services WHERE slug=? AND active=1",(slug,)).fetchone()
    con.close()
    if not s: return "Service introuvable",404
    log_event("service_view", s["id"])
    return render_template("service.html", service=s)

@app.post("/api/reward/start")
def reward_start():
    s_id=request.json.get("service_id")
    if not s_id: return jsonify(ok=False,error="Service manquant"),400
    if not rate_limit("reward_start", 30):
        return jsonify(ok=False,error="Veuillez patienter avant de recommencer."),429
    # Cette route NE donne aucune récompense. Elle démarre uniquement le flux.
    log_event("reward_start", s_id)
    return jsonify(ok=True, message="Flux publicitaire démarré. La validation doit être fournie par le fournisseur publicitaire.")

@app.post("/api/reward/validate")
def reward_validate():
    s_id=request.json.get("service_id")
    provider_token=request.json.get("provider_token","")
    # Ne jamais considérer un simple clic comme une preuve.
    if not provider_token:
        return jsonify(ok=False,error="Aucune preuve publicitaire valide reçue."),400
    # TODO: remplacer par la vérification serveur du fournisseur Adsterra
    # lorsque leur format/API de publicité récompensée fournit une preuve vérifiable.
    return jsonify(ok=False,error="Validation publicitaire non configurée. Ajoutez le mécanisme de validation officiel du format choisi."),501

@app.route("/use/<int:service_id>")
def use_service(service_id):
    con=db(); s=con.execute("SELECT * FROM services WHERE id=? AND active=1",(service_id,)).fetchone(); con.close()
    if not s: return "Service introuvable",404
    # Démonstration: les services sans récompense sont accessibles.
    if s["reward_required"]:
        return redirect(url_for("service", slug=s["slug"], locked=1))
    log_event("service_use", service_id)
    return render_template("tool.html", service=s)

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        if request.form.get("password")==ADMIN_PASSWORD:
            session["admin"]=True
            return redirect(url_for("admin"))
        return render_template("admin_login.html", error="Mot de passe incorrect.")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin():
    con=db()
    services=con.execute("SELECT * FROM services ORDER BY id DESC").fetchall()
    stats=con.execute("SELECT event, COUNT(*) n FROM events GROUP BY event ORDER BY n DESC").fetchall()
    con.close()
    return render_template("admin.html", services=services, stats=stats, s=settings())

@app.post("/admin/settings")
@admin_required
def admin_settings():
    con=db()
    allowed=["ads_enabled","rewarded_enabled","ad_top","ad_middle","ad_bottom","ad_service","rewarded_code","currency_rates"]
    for key in allowed:
        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",(key,request.form.get(key,"")))
    con.commit(); con.close()
    return redirect(url_for("admin"))

@app.post("/admin/service/add")
@admin_required
def admin_service_add():
    name=request.form["name"].strip()
    desc=request.form["description"].strip()
    slug=request.form["slug"].strip().lower().replace(" ","-")
    reward=1 if request.form.get("reward_required") else 0
    con=db()
    try:
        con.execute("INSERT INTO services(name,description,slug,reward_required) VALUES(?,?,?,?)",(name,desc,slug,reward))
        con.commit()
    except sqlite3.IntegrityError:
        pass
    con.close()
    return redirect(url_for("admin"))

@app.post("/admin/service/<int:service_id>/toggle")
@admin_required
def toggle_service(service_id):
    con=db()
    con.execute("UPDATE services SET active=1-active WHERE id=?",(service_id,))
    con.commit(); con.close()
    return redirect(url_for("admin"))

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=True)
else:
    init_db()

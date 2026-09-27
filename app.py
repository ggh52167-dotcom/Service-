from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from datetime import datetime
import sqlite3
import os
import time

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

DB = os.path.join(
    os.path.dirname(__file__),
    "site.db"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "3004"
)


# ============================================================
# CONFIGURATION PAR DÉFAUT
# ============================================================

DEFAULT_SETTINGS = {
    "ads_enabled": "1",

    # Publicités classiques
    "ad_top": "",
    "ad_middle": "",
    "ad_bottom": "",
    "ad_service": "",

    # Conservés pour compatibilité avec une ancienne base.
    # Ils ne sont plus utilisés pour bloquer les services.
    "rewarded_enabled": "0",
    "rewarded_code": "",

    # Taux configurables depuis l'administration
    "currency_rates":
        "EUR=1;USD=1.08;GBP=0.86;XOF=655.957;NGN=1500;GHS=16.5"
}


# ============================================================
# SERVICES PAR DÉFAUT
# ============================================================

DEFAULT_SERVICES = [

    (
        "Générateur de code QR",
        "Crée un QR code à partir d'un lien ou d'un texte.",
        "qr",
        1
    ),

    (
        "Convertisseur de monnaie",
        "Convertit des montants entre devises avec des taux configurables.",
        "currency",
        1
    ),

    (
        "Convertisseur de texte",
        "Transforme rapidement un texte en majuscules, minuscules ou titre.",
        "text",
        1
    ),

    (
        "Compteur de mots",
        "Analyse le nombre de mots et de caractères d'un texte.",
        "counter",
        1
    ),

    (
        "Générateur de mot de passe",
        "Génère un mot de passe aléatoire côté navigateur.",
        "password",
        1
    ),

    (
        "Formateur JSON",
        "Vérifie et met en forme un objet JSON.",
        "json",
        1
    ),

    (
        "Générateur de slug",
        "Transforme un titre en URL propre.",
        "slug",
        1
    ),

    (
        "Calculateur de pourcentage",
        "Calcule rapidement un pourcentage.",
        "percent",
        1
    )

]


# ============================================================
# BASE DE DONNÉES
# ============================================================

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():

    con = db()

    con.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            reward_required INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            event TEXT,
            service_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    # Ajouter les paramètres manquants
    for key, value in DEFAULT_SETTINGS.items():

        con.execute(
            """
            INSERT OR IGNORE INTO settings(key, value)
            VALUES (?, ?)
            """,
            (key, value)
        )

    # Ajouter les services seulement si la table est vide
    count = con.execute(
        "SELECT COUNT(*) FROM services"
    ).fetchone()[0]

    if count == 0:

        for name, description, slug, reward in DEFAULT_SERVICES:

            con.execute(
                """
                INSERT INTO services
                (name, description, slug, reward_required, active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (
                    name,
                    description,
                    slug,
                    0,
                )
            )

    con.commit()
    con.close()


# ============================================================
# PARAMÈTRES DU SITE
# ============================================================

def settings():

    con = db()

    data = {
        row["key"]: row["value"]
        for row in con.execute(
            "SELECT key, value FROM settings"
        )
    }

    con.close()

    return data


# ============================================================
# STATISTIQUES
# ============================================================

def log_event(event, service_id=None):

    con = db()

    ip = request.headers.get(
        "X-Forwarded-For",
        request.remote_addr
    )

    con.execute(
        """
        INSERT INTO events
        (ip, event, service_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            ip,
            event,
            service_id,
            datetime.utcnow().isoformat()
        )
    )

    con.commit()
    con.close()


# ============================================================
# LIMITE SIMPLE CÔTÉ SERVEUR
# ============================================================

def rate_limit(key, seconds=60):

    now = time.time()

    data = session.get(
        "limits",
        {}
    )

    last = data.get(
        key,
        0
    )

    if now - last < seconds:
        return False

    data[key] = now

    session["limits"] = data

    return True


# ============================================================
# PROTECTION ADMINISTRATION
# ============================================================

def admin_required(f):

    @wraps(f)
    def wrapped(*args, **kwargs):

        if not session.get("admin"):
            return redirect(
                url_for("admin_login")
            )

        return f(*args, **kwargs)

    return wrapped


# ============================================================
# VARIABLES DISPONIBLES DANS LES TEMPLATES
# ============================================================

@app.context_processor
def inject():

    return {
        "site_settings": settings()
    }


# ============================================================
# ACCUEIL
# ============================================================

@app.route("/")
def home():

    con = db()

    services = con.execute(
        """
        SELECT *
        FROM services
        WHERE active = 1
        ORDER BY id DESC
        """
    ).fetchall()

    con.close()

    log_event("page_view")

    return render_template(
        "index.html",
        services=services
    )


# ============================================================
# PAGE D'UN SERVICE
# ============================================================

@app.route("/service/<slug>")
def service(slug):

    con = db()

    service_data = con.execute(
        """
        SELECT *
        FROM services
        WHERE slug = ?
        AND active = 1
        """,
        (slug,)
    ).fetchone()

    con.close()

    if not service_data:

        return "Service introuvable", 404

    log_event(
        "service_view",
        service_data["id"]
    )

    return render_template(
        "service.html",
        service=service_data
    )


# ============================================================
# UTILISATION DIRECTE D'UN SERVICE
# ============================================================

@app.route("/use/<int:service_id>")
def use_service(service_id):

    con = db()

    service_data = con.execute(
        """
        SELECT *
        FROM services
        WHERE id = ?
        AND active = 1
        """,
        (service_id,)
    ).fetchone()

    con.close()

    if not service_data:

        return "Service introuvable", 404

    # IMPORTANT :
    # Aucun blocage publicitaire.
    # Aucun clic publicitaire obligatoire.
    # Le service est accessible directement.

    log_event(
        "service_use",
        service_id
    )

    return redirect(
        url_for(
            "service",
            slug=service_data["slug"]
        )
    )


# ============================================================
# CONNEXION ADMIN
# ============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        )

        if password == ADMIN_PASSWORD:

            session["admin"] = True

            return redirect(
                url_for("admin")
            )

        return render_template(
            "admin_login.html",
            error="Mot de passe incorrect."
        )

    return render_template(
        "admin_login.html"
    )


# ============================================================
# DÉCONNEXION ADMIN
# ============================================================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
)
    # ============================================================
# TABLEAU DE BORD ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    con = db()

    services = con.execute(
        """
        SELECT *
        FROM services
        ORDER BY id DESC
        """
    ).fetchall()

    stats = con.execute(
        """
        SELECT
            event,
            COUNT(*) AS n
        FROM events
        GROUP BY event
        ORDER BY n DESC
        """
    ).fetchall()

    con.close()

    return render_template(
        "admin.html",
        services=services,
        stats=stats,
        s=settings()
    )


# ============================================================
# PARAMÈTRES PUBLICITAIRES
# ============================================================

@app.post("/admin/settings")
@admin_required
def admin_settings():

    con = db()

    allowed = [
        "ads_enabled",
        "ad_top",
        "ad_middle",
        "ad_bottom",
        "ad_service",
        "currency_rates"
    ]

    for key in allowed:

        value = request.form.get(
            key,
            ""
        )

        con.execute(
            """
            INSERT OR REPLACE INTO settings
            (key, value)
            VALUES (?, ?)
            """,
            (
                key,
                value
            )
        )

    # Le système récompensé est définitivement désactivé
    con.execute(
        """
        INSERT OR REPLACE INTO settings
        (key, value)
        VALUES (?, ?)
        """,
        (
            "rewarded_enabled",
            "0"
        )
    )

    con.execute(
        """
        INSERT OR REPLACE INTO settings
        (key, value)
        VALUES (?, ?)
        """,
        (
            "rewarded_code",
            ""
        )
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# ============================================================
# AJOUTER UN SERVICE
# ============================================================

@app.post("/admin/service/add")
@admin_required
def admin_service_add():

    name = request.form.get(
        "name",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    slug = request.form.get(
        "slug",
        ""
    ).strip().lower().replace(
        " ",
        "-"
    )

    if not name or not description or not slug:

        return redirect(
            url_for("admin")
        )

    con = db()

    try:

        # Tous les nouveaux services sont accessibles
        # sans publicité obligatoire.

        con.execute(
            """
            INSERT INTO services
            (
                name,
                description,
                slug,
                reward_required,
                active
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                description,
                slug,
                0,
                1
            )
        )

        con.commit()

    except sqlite3.IntegrityError:

        pass

    finally:

        con.close()

    return redirect(
        url_for("admin")
    )


# ============================================================
# ACTIVER / DÉSACTIVER UN SERVICE
# ============================================================

@app.post(
    "/admin/service/<int:service_id>/toggle"
)
@admin_required
def toggle_service(service_id):

    con = db()

    con.execute(
        """
        UPDATE services
        SET active = 1 - active
        WHERE id = ?
        """,
        (service_id,)
    )

    con.commit()
    con.close()

    return redirect(
        url_for("admin")
    )


# ============================================================
# ROUTE DE SANTÉ POUR L'HÉBERGEMENT
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "Video Services"
    })


# ============================================================
# ERREUR 404
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return render_template(
        "index.html"
    ), 404


# ============================================================
# INITIALISATION
# ============================================================

init_db()


# ============================================================
# LANCEMENT LOCAL / RENDER
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=True
)

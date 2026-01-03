from flask import Flask, redirect, render_template, request, url_for
from dotenv import load_dotenv
import os
import git
import hmac
import hashlib
from db import db_read, db_write
from auth import login_manager, authenticate, register_user
from flask_login import login_user, logout_user, login_required, current_user
import logging
from flask import jsonify

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Load .env variablescf
load_dotenv()
W_SECRET = os.getenv("W_SECRET")

# Init flask app
app = Flask(__name__)
app.config["DEBUG"] = True
app.secret_key = "supersecret"

# Init auth
login_manager.init_app(app)
login_manager.login_view = "login"

# DON'T CHANGE
def is_valid_signature(x_hub_signature, data, private_key):
    hash_algorithm, github_signature = x_hub_signature.split('=', 1)
    algorithm = hashlib.__dict__.get(hash_algorithm)
    encoded_key = bytes(private_key, 'latin-1')
    mac = hmac.new(encoded_key, msg=data, digestmod=algorithm)
    return hmac.compare_digest(mac.hexdigest(), github_signature)

# DON'T CHANGE
@app.post('/update_server')
def webhook():
    x_hub_signature = request.headers.get('X-Hub-Signature')
    if is_valid_signature(x_hub_signature, request.data, W_SECRET):
        repo = git.Repo('./mysite')
        origin = repo.remotes.origin
        origin.pull()
        return 'Updated PythonAnywhere successfully', 200
    return 'Unathorized', 401

# Auth routes
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        user = authenticate(
            request.form["username"],
            request.form["password"]
        )

        if user:
            login_user(user)
            return redirect(url_for("index"))

        error = "Benutzername oder Passwort ist falsch."

    return render_template(
        "auth.html",
        title="In dein Konto einloggen",
        action=url_for("login"),
        button_label="Einloggen",
        error=error,
        footer_text="Noch kein Konto?",
        footer_link_url=url_for("register"),
        footer_link_label="Registrieren"
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        ok = register_user(username, password)
        if ok:
            return redirect(url_for("login"))

        error = "Benutzername existiert bereits."

    return render_template(
        "auth.html",
        title="Neues Konto erstellen",
        action=url_for("register"),
        button_label="Registrieren",
        error=error,
        footer_text="Du hast bereits ein Konto?",
        footer_link_url=url_for("login"),
        footer_link_label="Einloggen"
    )

@app.route("/")
@login_required
def index():
    return render_template("index.html")

# buchen Route 
@app.route("/buchen", methods=["GET", "POST"])
@login_required
def buchen():
    nutzer = {}
    fehler = None

    # Alle Plätze aus DB holen
    try:
        alle_plaetze = db_read("SELECT * FROM tennisplatz ORDER BY tennisanlage, platznummer")
        if not alle_plaetze:
            alle_plaetze = []
        # Alle Tennisanlagen extrahieren (ohne Duplikate)
        anlagen = sorted(list(set([p["tennisanlage"] for p in alle_plaetze])))
    except Exception as e:
        logging.error(f"Fehler beim Laden der Tennisplätze: {e}")
        alle_plaetze = []
        anlagen = []
        fehler = "Fehler beim Laden der Tennisplätze."

    if request.method == "POST":
        # 1. NUTZER VERARBEITEN
        nid = request.form.get("nid")
        
        if nid:
            # Bestehender Nutzer
            nutzer = db_read("SELECT * FROM nutzer WHERE nid=%s", (nid,), single=True)
            if not nutzer:
                fehler = "Diese Nutzer-ID existiert nicht!"
                return render_template(
                    "buchen.html",
                    nutzer={},
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )
        else:
            # Neuer Nutzer erstellen
            vorname = request.form.get("vorname", "").strip()
            nachname = request.form.get("nachname", "").strip()
            geburtsdatum = request.form.get("geburtsdatum")
            email = request.form.get("email", "").strip()
            
            if not vorname or not nachname or not email:
                fehler = "Bitte alle Pflichtfelder (*) ausfüllen."
                return render_template(
                    "buchen.html",
                    nutzer={},
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )
            
            # Leeres Geburtsdatum auf None setzen
            if not geburtsdatum:
                geburtsdatum = None
            
            # Nutzer in DB speichern
            try:
                db_write(
                    "INSERT INTO nutzer (vorname, nachname, geburtsdatum, email) VALUES (%s,%s,%s,%s)",
                    (vorname, nachname, geburtsdatum, email)
                )
                # Neu erstellten Nutzer abrufen
                nutzer = db_read("SELECT * FROM nutzer WHERE email=%s", (email,), single=True)
            except Exception as e:
                logging.error(f"Fehler beim Erstellen des Nutzers: {e}")
                fehler = "Fehler beim Erstellen des Nutzers. Möglicherweise existiert die E-Mail bereits."
                return render_template(
                    "buchen.html",
                    nutzer={},
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )

        # 2. BUCHUNG VERARBEITEN
        if nutzer:
            tennisanlage = request.form.get("tennisanlage", "").strip()
            platznummer_str = request.form.get("platznummer", "").strip()
            spieldatum = request.form.get("spieldatum")
            beginn = request.form.get("beginn")
            ende = request.form.get("ende")

            # Validierung
            if not tennisanlage or not platznummer_str or not spieldatum or not beginn or not ende:
                fehler = "Bitte alle Buchungsdetails ausfüllen."
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )

            # Prüfen ob Datum in der Zukunft liegt
            from datetime import date, time
            heute = date.today()
            spiel_datum = date.fromisoformat(spieldatum)
            
            if spiel_datum < heute:
                fehler = "Buchungen sind nur für heute oder zukünftige Termine möglich."
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )

            # Öffnungszeiten prüfen (7:00 - 20:00)
            beginn_time = time.fromisoformat(beginn)
            ende_time = time.fromisoformat(ende)
            oeffnung = time(7, 0)
            schliessung = time(20, 0)

            if beginn_time < oeffnung or ende_time > schliessung:
                fehler = "Buchungen sind nur zwischen 7:00 und 20:00 Uhr möglich."
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )

            if beginn_time >= ende_time:
                fehler = "Die Endzeit muss nach der Startzeit liegen."
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )

            try:
                platznummer = int(platznummer_str)
            except ValueError:
                fehler = "Ungültige Platznummer."
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )

            # Tennisplatz aus DB suchen
            platz = db_read(
                "SELECT * FROM tennisplatz WHERE tennisanlage=%s AND platznummer=%s",
                (tennisanlage, platznummer),
                single=True
            )

            if not platz:
                fehler = f"Tennisplatz '{tennisanlage}' mit Platznummer {platznummer} existiert nicht in der Datenbank!"
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )

            # Prüfen ob der Platz zur gewählten Zeit bereits gebucht ist
            konflikt = db_read(
                """SELECT * FROM buchung 
                   WHERE tid = %s 
                   AND spieldatum = %s 
                   AND (
                       (spielbeginn < %s AND spielende > %s) OR
                       (spielbeginn < %s AND spielende > %s) OR
                       (spielbeginn >= %s AND spielende <= %s)
                   )""",
                (platz["tid"], spieldatum, ende, beginn, beginn, ende, beginn, ende),
                single=True
            )

            if konflikt:
                fehler = "Dieser Platz ist zum gewählten Zeitpunkt nicht mehr verfügbar. Bitte wählen Sie einen anderen Zeitraum."
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )

            # Buchung speichern
            try:
                db_write(
                    "INSERT INTO buchung (nid, tid, spieldatum, spielbeginn, spielende) VALUES (%s,%s,%s,%s,%s)",
                    (nutzer["nid"], platz["tid"], spieldatum, beginn, ende)
                )
                return redirect(url_for("bbestätigt"))
            except Exception as e:
                logging.error(f"Fehler beim Speichern der Buchung: {e}")
                fehler = "Fehler beim Speichern der Buchung."
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze
                )

    return render_template(
        "buchen.html",
        nutzer=nutzer,
        fehler=fehler,
        anlagen=anlagen,
        alle_plaetze=alle_plaetze
    )

# java script 
@app.route("/get_nutzer/<int:nid>")
@login_required
def get_nutzer(nid):
    user = db_read("SELECT * FROM nutzer WHERE nid=%s", (nid,), single=True)
    if not user:
        return jsonify({})
    return jsonify({
        "vorname": user["vorname"],
        "nachname": user["nachname"],
        "geburtsdatum": str(user["geburtsdatum"]) if user["geburtsdatum"] else "",
        "email": user["email"]
    })


@app.route("/bbestätigt")
@login_required
def bbestätigt():
    return render_template("bbestätigt.html")

@app.route("/stornieren")
@login_required
def stornieren():
    return render_template("stornieren.html")

@app.route("/sbestätigt")
@login_required
def sbestätigt():
    return render_template("sbestätigt.html")

@app.route("/verwaltung")
@login_required
def verwaltung():
    return render_template("verwaltung.html")

@app.route("/tennisplätze")
@login_required
def tennisplätze():
    return render_template("tennisplätze.html")

@app.route("/wartungsarbeiter")
@login_required
def wartungsarbeiter():
    return render_template("wartungsarbeiter.html")
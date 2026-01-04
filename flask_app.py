from flask import Flask, redirect, render_template, request, url_for, jsonify, session
from dotenv import load_dotenv
import os
import git
import hmac
import hashlib
from db import db_read, db_write
from auth import login_manager, authenticate, register_user
from flask_login import login_user, logout_user, login_required, current_user
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Load .env variables
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

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    return render_template("index.html")

# buchen
@app.route("/buchen", methods=["GET", "POST"])
@login_required
def buchen():
    nutzer = {}
    fehler = None
    form_data = {}  # Speichert Formulardaten bei Fehler

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
        # Formulardaten speichern
        form_data = {
            'nid': request.form.get("nid", ""),
            'vorname': request.form.get("vorname", ""),
            'nachname': request.form.get("nachname", ""),
            'geburtsdatum': request.form.get("geburtsdatum", ""),
            'email': request.form.get("email", ""),
            'tennisanlage': request.form.get("tennisanlage", ""),
            'platznummer': request.form.get("platznummer", ""),
            'spieldatum': request.form.get("spieldatum", ""),
            'beginn': request.form.get("beginn", ""),
            'ende': request.form.get("ende", "")
        }

        # 1. NUTZER VERARBEITEN
        nid = form_data['nid']
        
        if nid:
            # Bestehender Nutzer über NID laden
            nutzer = db_read("SELECT * FROM nutzer WHERE nid=%s", (nid,), single=True)
            if not nutzer:
                fehler = "Diese Nutzer-ID existiert nicht in der Datenbank."
                form_data['nid'] = ''  # NID-Feld leeren
                return render_template(
                    "buchen.html",
                    nutzer={},
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )
            
            # Altersüberprüfung für bestehende Nutzer
            if nutzer.get('geburtsdatum'):
                from datetime import date
                geburtsdatum_date = nutzer['geburtsdatum']
                if isinstance(geburtsdatum_date, str):
                    geburtsdatum_date = date.fromisoformat(geburtsdatum_date)
                
                heute = date.today()
                alter = heute.year - geburtsdatum_date.year
                if (heute.month, heute.day) < (geburtsdatum_date.month, geburtsdatum_date.day):
                    alter -= 1
                
                if alter < 16:
                    fehler = "Sie müssen mindestens 16 Jahre alt sein, um einen Tennisplatz zu buchen."
                    return render_template(
                        "buchen.html",
                        nutzer={},
                        fehler=fehler,
                        anlagen=anlagen,
                        alle_plaetze=alle_plaetze,
                        form_data=form_data
                    )
        else:
            # Neuer Nutzer erstellen
            vorname = form_data['vorname'].strip()
            nachname = form_data['nachname'].strip()
            geburtsdatum = form_data['geburtsdatum']
            email = form_data['email'].strip()
            
            if not vorname or not nachname or not email:
                fehler = "Bitte alle Pflichtfelder (*) ausfüllen."
                return render_template(
                    "buchen.html",
                    nutzer={},
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )
            
            # Altersüberprüfung: Mindestens 16 Jahre alt
            if geburtsdatum:
                from datetime import date
                geburtsdatum_date = date.fromisoformat(geburtsdatum)
                heute = date.today()
                alter = heute.year - geburtsdatum_date.year
                if (heute.month, heute.day) < (geburtsdatum_date.month, geburtsdatum_date.day):
                    alter -= 1
                
                if alter < 16:
                    fehler = "Sie müssen mindestens 16 Jahre alt sein, um einen Tennisplatz zu buchen."
                    return render_template(
                        "buchen.html",
                        nutzer={},
                        fehler=fehler,
                        anlagen=anlagen,
                        alle_plaetze=alle_plaetze,
                        form_data=form_data
                    )
            
            # Prüfen ob Email bereits existiert (anderer Nutzer mit gleicher Email)
            bestehender_nutzer = db_read("SELECT * FROM nutzer WHERE email=%s", (email,), single=True)
            if bestehender_nutzer:
                # Email existiert bereits - Nutzer hat seine NID vergessen
                nutzer = bestehender_nutzer
            else:
                # Neuen Nutzer erstellen
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
                    fehler = "Fehler beim Erstellen des Nutzers."
                    return render_template(
                        "buchen.html",
                        nutzer={},
                        fehler=fehler,
                        anlagen=anlagen,
                        alle_plaetze=alle_plaetze,
                        form_data=form_data
                    )

        # 2. BUCHUNG VERARBEITEN
        if nutzer:
            tennisanlage = form_data['tennisanlage'].strip()
            platznummer_str = form_data['platznummer'].strip()
            spieldatum = form_data['spieldatum']
            beginn = form_data['beginn']
            ende = form_data['ende']

            # Validierung
            if not tennisanlage or not platznummer_str or not spieldatum or not beginn or not ende:
                fehler = "Bitte alle Buchungsdetails ausfüllen."
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            # Prüfen ob Datum in der Zukunft oder heute liegt
            from datetime import date, time, datetime
            heute = date.today()
            jetzt = datetime.now()
            spiel_datum = date.fromisoformat(spieldatum)
            
            if spiel_datum < heute:
                fehler = "Buchungen sind nur für heute oder zukünftige Termine möglich."
                form_data['spieldatum'] = ''
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            # Öffnungszeiten prüfen (7:00 - 20:00)
            beginn_time = time.fromisoformat(beginn)
            ende_time = time.fromisoformat(ende)
            oeffnung = time(7, 0)
            schliessung = time(20, 0)

            # Prüfen ob Zeiten auf volle oder halbe Stunden sind
            if (beginn_time.minute not in [0, 30]) or (ende_time.minute not in [0, 30]):
                fehler = "Buchungen sind nur zu vollen oder halben Stunden möglich (z.B. 14:00 oder 14:30). Zeiten wie 12:20 oder 15:45 sind nicht erlaubt."
                form_data['beginn'] = ''
                form_data['ende'] = ''
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            if beginn_time < oeffnung or ende_time > schliessung:
                fehler = "Buchungen sind nur zwischen 7:00 und 20:00 Uhr möglich."
                form_data['beginn'] = ''
                form_data['ende'] = ''
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            # Prüfen ob Startzeit in der Vergangenheit liegt (wenn heute gebucht wird)
            if spiel_datum == heute:
                aktuelle_zeit = jetzt.time()
                if beginn_time <= aktuelle_zeit:
                    fehler = "Die Startzeit liegt in der Vergangenheit. Bitte wählen Sie eine spätere Uhrzeit."
                    form_data['beginn'] = ''
                    form_data['ende'] = ''
                    return render_template(
                        "buchen.html",
                        nutzer=nutzer,
                        fehler=fehler,
                        anlagen=anlagen,
                        alle_plaetze=alle_plaetze,
                        form_data=form_data
                    )

            if beginn_time >= ende_time:
                fehler = "Die Endzeit muss nach der Startzeit liegen."
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            # Prüfen ob Spielzeit maximal 60 Minuten ist
            from datetime import datetime, timedelta
            dauer = datetime.combine(date.today(), ende_time) - datetime.combine(date.today(), beginn_time)
            if dauer > timedelta(hours=1):
                fehler = "Die maximale Buchungsdauer beträgt 1 Stunde (60 Minuten)."
                form_data['beginn'] = ''
                form_data['ende'] = ''
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
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
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
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
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            # Prüfen ob der Platz zur gewählten Zeit bereits gebucht ist
            # Zwei Zeiträume überschneiden sich, wenn: Start1 < Ende2 UND Start2 < Ende1
            konflikt = db_read(
                """SELECT * FROM buchung 
                   WHERE tid = %s 
                   AND spieldatum = %s 
                   AND NOT (spielende <= %s OR spielbeginn >= %s)""",
                (platz["tid"], spieldatum, beginn, ende),
                single=True
            )

            if konflikt:
                # Prüfen ob es der gleiche Nutzer ist
                if konflikt["nid"] == nutzer["nid"]:
                    fehler = "Sie haben für diesen Platz am gewählten Datum bereits eine Buchung."
                else:
                    fehler = "Dieser Platz ist zum gewählten Zeitpunkt nicht mehr verfügbar. Bitte wählen Sie einen anderen Zeitraum."
                # Zeitfelder löschen bei Konflikt
                form_data['beginn'] = ''
                form_data['ende'] = ''
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            # Buchung speichern
            try:
                db_write(
                    "INSERT INTO buchung (nid, tid, spieldatum, spielbeginn, spielende) VALUES (%s,%s,%s,%s,%s)",
                    (nutzer["nid"], platz["tid"], spieldatum, beginn, ende)
                )
                
                # Buchungsnummer abrufen
                letzte_buchung = db_read(
                    "SELECT buchungsnummer FROM buchung WHERE nid=%s ORDER BY buchungsnummer DESC LIMIT 1",
                    (nutzer["nid"],),
                    single=True
                )
                
                # Daten DIREKT speichern ohne Formatierung
                session['buchungs_nr'] = letzte_buchung['buchungsnummer']
                session['nutzer_nid'] = nutzer["nid"]
                session['nutzer_vorname'] = nutzer["vorname"]
                session['nutzer_nachname'] = nutzer["nachname"]
                session['nutzer_email'] = nutzer.get("email", "")
                session['nutzer_geburtsdatum'] = str(nutzer.get("geburtsdatum", "")) if nutzer.get("geburtsdatum") else ""
                session['buchung_anlage'] = tennisanlage
                session['buchung_platz'] = platznummer
                session['buchung_datum'] = spieldatum  # Format: YYYY-MM-DD
                session['buchung_beginn'] = beginn  # Format: HH:MM
                session['buchung_ende'] = ende  # Format: HH:MM
                
                from datetime import datetime
                session['buchung_zeitpunkt'] = datetime.now().strftime("%d.%m.%Y um %H:%M Uhr")
                
                return redirect(url_for("bbestätigt"))
            except Exception as e:
                logging.error(f"Fehler beim Speichern der Buchung: {e}")
                fehler = "Fehler beim Speichern der Buchung."
                return render_template(
                    "buchen.html",
                    nutzer=nutzer,
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

    return render_template(
        "buchen.html",
        nutzer=nutzer,
        fehler=fehler,
        anlagen=anlagen,
        alle_plaetze=alle_plaetze,
        form_data=form_data
    )


# Route für JavaScript - Nutzer-Daten abrufen
@app.route("/get_nutzer/<int:nid>")
@login_required
def get_nutzer(nid):
    try:
        user = db_read("SELECT * FROM nutzer WHERE nid=%s", (nid,), single=True)
        if not user:
            return jsonify({"exists": False})
        return jsonify({
            "exists": True,
            "vorname": user["vorname"] or "",
            "nachname": user["nachname"] or "",
            "geburtsdatum": str(user["geburtsdatum"]) if user.get("geburtsdatum") else "",
            "email": user["email"] or ""
        })
    except Exception as e:
        logging.error(f"Fehler bei get_nutzer: {e}")
        return jsonify({"exists": False, "error": str(e)})


# Ersetze die /stornieren Route in app.py mit dieser korrigierten Version:
# Ersetze die /stornieren Route in app.py mit dieser korrigierten Version:

@app.route("/stornieren", methods=["GET", "POST"])
@login_required
def stornieren():
    fehler = None
    form_data = {}

    # Alle Plätze aus DB holen
    try:
        alle_plaetze = db_read("SELECT * FROM tennisplatz ORDER BY tennisanlage, platznummer")
        if not alle_plaetze:
            alle_plaetze = []
        anlagen = sorted(list(set([p["tennisanlage"] for p in alle_plaetze])))
    except Exception as e:
        logging.error(f"Fehler beim Laden der Tennisplätze: {e}")
        alle_plaetze = []
        anlagen = []
        fehler = "Fehler beim Laden der Tennisplätze."

    if request.method == "POST":
        # Formulardaten speichern
        form_data = {
            'buchungsnummer': request.form.get("buchungsnummer", ""),
            'nid': request.form.get("nid", ""),
            'vorname': request.form.get("vorname", ""),
            'nachname': request.form.get("nachname", ""),
            'email': request.form.get("email", ""),
            'tennisanlage': request.form.get("tennisanlage", ""),
            'platznummer': request.form.get("platznummer", ""),
            'spieldatum': request.form.get("spieldatum", ""),
            'beginn': request.form.get("beginn", ""),
            'ende': request.form.get("ende", "")
        }

        buchungsnummer = form_data['buchungsnummer'].strip()
        
        buchung = None

        # Fall 1: Suche über Buchungsnummer + E-Mail
        if buchungsnummer:
            email = form_data['email'].strip()
            
            # E-Mail Validierung
            if not email:
                fehler = "Bitte geben Sie Ihre E-Mail-Adresse zur Bestätigung ein."
                return render_template(
                    "stornieren.html",
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )
            
            try:
                buchung = db_read(
                    """SELECT b.*, n.vorname, n.nachname, n.email, t.tennisanlage, t.platznummer
                       FROM buchung b
                       JOIN nutzer n ON b.nid = n.nid
                       JOIN tennisplatz t ON b.tid = t.tid
                       WHERE b.buchungsnummer = %s AND n.email = %s""",
                    (buchungsnummer, email),
                    single=True
                )
                
                if not buchung:
                    fehler = "Buchung mit dieser Buchungsnummer und E-Mail-Adresse wurde nicht gefunden. Bitte überprüfen Sie Ihre Angaben."
                    form_data['buchungsnummer'] = ''
                    form_data['email'] = ''
                    return render_template(
                        "stornieren.html",
                        fehler=fehler,
                        anlagen=anlagen,
                        alle_plaetze=alle_plaetze,
                        form_data=form_data
                    )
            except Exception as e:
                logging.error(f"Fehler bei Buchungssuche: {e}")
                fehler = "Fehler bei der Suche nach der Buchung."
                return render_template(
                    "stornieren.html",
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

        # Fall 2: Suche über Personalien + Buchungsdetails
        else:
            vorname = form_data['vorname'].strip()
            nachname = form_data['nachname'].strip()
            email = form_data['email'].strip()
            tennisanlage = form_data['tennisanlage'].strip()
            platznummer = form_data['platznummer'].strip()
            spieldatum = form_data['spieldatum']
            beginn = form_data['beginn']

            # Validierung: Alle Felder müssen ausgefüllt sein
            if not vorname or not nachname or not email:
                fehler = "Bitte geben Sie Vorname, Nachname und E-Mail-Adresse ein."
                return render_template(
                    "stornieren.html",
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            # Validierung der Buchungsdetails
            if not tennisanlage or not platznummer or not spieldatum or not beginn:
                fehler = "Bitte alle Buchungsdetails ausfüllen."
                return render_template(
                    "stornieren.html",
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            # Nutzer über Name und Email finden
            nutzer = db_read(
                "SELECT * FROM nutzer WHERE vorname=%s AND nachname=%s AND email=%s",
                (vorname, nachname, email),
                single=True
            )
            
            if not nutzer:
                fehler = "Kein Nutzer mit diesen Personalien gefunden."
                return render_template(
                    "stornieren.html",
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            # Tennisplatz finden
            try:
                platznummer_int = int(platznummer)
            except ValueError:
                fehler = "Ungültige Platznummer."
                return render_template(
                    "stornieren.html",
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            platz = db_read(
                "SELECT * FROM tennisplatz WHERE tennisanlage=%s AND platznummer=%s",
                (tennisanlage, platznummer_int),
                single=True
            )

            if not platz:
                fehler = f"Tennisplatz '{tennisanlage}' mit Platznummer {platznummer_int} existiert nicht."
                return render_template(
                    "stornieren.html",
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

            # Buchung finden
            try:
                buchung = db_read(
                    """SELECT b.*, n.vorname, n.nachname, n.email, t.tennisanlage, t.platznummer
                       FROM buchung b
                       JOIN nutzer n ON b.nid = n.nid
                       JOIN tennisplatz t ON b.tid = t.tid
                       WHERE b.nid = %s AND b.tid = %s AND b.spieldatum = %s AND b.spielbeginn = %s""",
                    (nutzer["nid"], platz["tid"], spieldatum, beginn),
                    single=True
                )

                if not buchung:
                    fehler = "Keine Buchung mit diesen Angaben gefunden."
                    return render_template(
                        "stornieren.html",
                        fehler=fehler,
                        anlagen=anlagen,
                        alle_plaetze=alle_plaetze,
                        form_data=form_data
                    )
            except Exception as e:
                logging.error(f"Fehler bei Buchungssuche: {e}")
                fehler = "Fehler bei der Suche nach der Buchung."
                return render_template(
                    "stornieren.html",
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

        # Buchung gefunden - Stornierung durchführen
        if buchung:
            # Prüfen ob Buchung in der Vergangenheit liegt
            from datetime import date, datetime
            heute = date.today()
            jetzt = datetime.now()
            
            spieldatum_date = buchung['spieldatum']
            if isinstance(spieldatum_date, str):
                spieldatum_date = date.fromisoformat(spieldatum_date)
            
            # Wenn Spieldatum in der Vergangenheit liegt
            if spieldatum_date < heute:
                fehler = "Diese Buchung liegt in der Vergangenheit und kann nicht mehr storniert werden."
                return render_template(
                    "stornieren.html",
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )
            
            # Wenn Spieldatum heute ist, prüfen ob Spielbeginn schon vorbei ist
            if spieldatum_date == heute:
                from datetime import time
                spielbeginn_time = buchung['spielbeginn']
                if isinstance(spielbeginn_time, str):
                    spielbeginn_time = time.fromisoformat(spielbeginn_time)
                
                aktuelle_zeit = jetzt.time()
                if spielbeginn_time <= aktuelle_zeit:
                    fehler = "Der Spielbeginn liegt in der Vergangenheit. Diese Buchung kann nicht mehr storniert werden."
                    return render_template(
                        "stornieren.html",
                        fehler=fehler,
                        anlagen=anlagen,
                        alle_plaetze=alle_plaetze,
                        form_data=form_data
                    )

            # Buchung löschen
            try:
                db_write(
                    "DELETE FROM buchung WHERE buchungsnummer = %s",
                    (buchung['buchungsnummer'],)
                )

                # Daten für Bestätigungsseite in Session speichern
                session['stornierung_buchungsnummer'] = buchung['buchungsnummer']
                session['stornierung_nid'] = buchung['nid']
                session['stornierung_vorname'] = buchung['vorname']
                session['stornierung_nachname'] = buchung['nachname']
                session['stornierung_email'] = buchung['email']
                session['stornierung_tennisanlage'] = buchung['tennisanlage']
                session['stornierung_platznummer'] = buchung['platznummer']
                session['stornierung_spieldatum'] = str(buchung['spieldatum'])
                session['stornierung_spielbeginn'] = str(buchung['spielbeginn'])
                session['stornierung_spielende'] = str(buchung['spielende'])
                session['stornierung_zeitpunkt'] = datetime.now().strftime("%d.%m.%Y um %H:%M Uhr")

                return redirect(url_for("sbestätigt"))

            except Exception as e:
                logging.error(f"Fehler beim Stornieren der Buchung: {e}")
                fehler = "Fehler beim Stornieren der Buchung."
                return render_template(
                    "stornieren.html",
                    fehler=fehler,
                    anlagen=anlagen,
                    alle_plaetze=alle_plaetze,
                    form_data=form_data
                )

    return render_template(
        "stornieren.html",
        fehler=fehler,
        anlagen=anlagen,
        alle_plaetze=alle_plaetze,
        form_data=form_data
    )

#sbestätigt Route
@app.route("/sbestätigt")
@login_required
def sbestätigt():
    # Daten aus Session holen
    buchungsnummer = session.get('stornierung_buchungsnummer', '')
    nid = session.get('stornierung_nid', '')
    vorname = session.get('stornierung_vorname', '')
    nachname = session.get('stornierung_nachname', '')
    email = session.get('stornierung_email', '')
    tennisanlage = session.get('stornierung_tennisanlage', '')
    platznummer = session.get('stornierung_platznummer', '')
    spieldatum_raw = session.get('stornierung_spieldatum', '')
    spielbeginn = session.get('stornierung_spielbeginn', '')
    spielende = session.get('stornierung_spielende', '')
    stornierungszeitpunkt = session.get('stornierung_zeitpunkt', '')

    if not buchungsnummer:
        return redirect(url_for("stornieren"))

    # Datum formatieren
    spieldatum_formatiert = spieldatum_raw
    if spieldatum_raw and len(spieldatum_raw) == 10:
        teile = spieldatum_raw.split('-')
        if len(teile) == 3:
            spieldatum_formatiert = f"{teile[2]}.{teile[1]}.{teile[0]}"

    return render_template("sbestätigt.html",
        buchungsnummer=buchungsnummer,
        nid=nid,
        vorname=vorname,
        nachname=nachname,
        email=email,
        tennisanlage=tennisanlage,
        platznummer=platznummer,
        spieldatum_formatiert=spieldatum_formatiert,
        spielbeginn_formatiert=spielbeginn,
        spielende_formatiert=spielende,
        stornierungszeitpunkt=stornierungszeitpunkt
    )

@app.route("/verwaltung")
@login_required
def verwaltung():
    return render_template("verwaltung.html")


# Ersetze die kompletten tennisplätze und get_tennisplatz Routen in deiner app.py:

# API Route für AJAX - Tennisplatz-Daten abrufen
@app.route("/get_tennisplatz/<int:tid>")
@login_required
def get_tennisplatz(tid):
    try:
        platz = db_read("SELECT * FROM tennisplatz WHERE tid=%s", (tid,), single=True)
        if not platz:
            return jsonify({"exists": False})
        return jsonify({
            "exists": True,
            "tid": platz["tid"],
            "tennisanlage": platz["tennisanlage"] or "",
            "platznummer": platz["platznummer"] or "",
            "belag": platz["belag"] or "",
            "wartung": str(platz["datum_der_wartung"]) if platz.get("datum_der_wartung") else ""
        })
    except Exception as e:
        logging.error(f"Fehler bei get_tennisplatz: {e}")
        return jsonify({"exists": False, "error": str(e)})


# tennisplätze route
@app.route("/tennisplätze", methods=["GET", "POST"])
@login_required
def tennisplätze():
    fehler = None
    erfolg = None
    
    if request.method == "POST":
        aktion = request.form.get("aktion")
        
        # Tennisplatz hinzufügen
        if aktion == "hinzufuegen":
            anlage = request.form.get("anlage", "").strip()
            platznummer = request.form.get("platznummer", "").strip()
            belag = request.form.get("belag", "").strip()
            wartung = request.form.get("wartung", "").strip()
            
            if not anlage or not platznummer or not belag or not wartung:
                fehler = "Bitte alle Pflichtfelder ausfüllen (Tennisanlage, Platznummer, Belag, Wartungsdatum)."
            else:
                try:
                    platznummer_int = int(platznummer)
                    
                    # Prüfen ob Platz bereits existiert
                    existiert = db_read(
                        "SELECT * FROM tennisplatz WHERE tennisanlage=%s AND platznummer=%s",
                        (anlage, platznummer_int),
                        single=True
                    )
                    
                    if existiert:
                        fehler = f"Tennisplatz '{anlage}' mit Platznummer {platznummer_int} existiert bereits."
                    else:
                        # Default Wartungsarbeiter-ID = 1 (falls du keinen bestimmten hast)
                        # Du kannst das später anpassen, um einen echten Wartungsarbeiter auszuwählen
                        db_write(
                            "INSERT INTO tennisplatz (tennisanlage, platznummer, belag, datum_der_wartung, wid) VALUES (%s,%s,%s,%s,%s)",
                            (anlage, platznummer_int, belag, wartung, 1)
                        )
                        erfolg = f"Tennisplatz '{anlage}' - Platz {platznummer_int} wurde erfolgreich hinzugefügt."
                        
                except ValueError:
                    fehler = "Platznummer muss eine Zahl sein."
                except Exception as e:
                    logging.error(f"Fehler beim Hinzufügen des Tennisplatzes: {e}")
                    fehler = f"Fehler beim Hinzufügen des Tennisplatzes: {str(e)}"
        
        # Tennisplatz ändern
        elif aktion == "aendern":
            platz_id = request.form.get("platz_id", "").strip()
            anlage = request.form.get("anlage", "").strip()
            platznummer = request.form.get("platznummer", "").strip()
            belag = request.form.get("belag", "").strip()
            wartung = request.form.get("wartung", "").strip()
            
            if not platz_id or not anlage or not platznummer or not belag or not wartung:
                fehler = "Bitte alle Pflichtfelder ausfüllen (Tennisplatz-ID, Tennisanlage, Platznummer, Belag, Wartungsdatum)."
            else:
                try:
                    tid = int(platz_id)
                    platznummer_int = int(platznummer)
                    
                    # Prüfen ob Platz existiert
                    platz = db_read("SELECT * FROM tennisplatz WHERE tid=%s", (tid,), single=True)
                    
                    if not platz:
                        fehler = f"Tennisplatz mit ID {tid} existiert nicht."
                    else:
                        # Alle Felder aktualisieren
                        db_write(
                            "UPDATE tennisplatz SET tennisanlage=%s, platznummer=%s, belag=%s, datum_der_wartung=%s WHERE tid=%s",
                            (anlage, platznummer_int, belag, wartung, tid)
                        )
                        
                        erfolg = f"Tennisplatz mit ID {tid} wurde erfolgreich aktualisiert."
                        
                except ValueError:
                    fehler = "Tennisplatz-ID und Platznummer müssen Zahlen sein."
                except Exception as e:
                    logging.error(f"Fehler beim Ändern des Tennisplatzes: {e}")
                    fehler = f"Fehler beim Ändern des Tennisplatzes: {str(e)}"
        
        # Tennisplatz löschen
        elif aktion == "loeschen":
            platz_id = request.form.get("platz_id", "").strip()
            
            if not platz_id:
                fehler = "Bitte Tennisplatz-ID eingeben."
            else:
                try:
                    tid = int(platz_id)
                    
                    # Prüfen ob Platz existiert
                    platz = db_read("SELECT * FROM tennisplatz WHERE tid=%s", (tid,), single=True)
                    
                    if not platz:
                        fehler = f"Tennisplatz mit ID {tid} existiert nicht."
                    else:
                        # Prüfen ob noch Buchungen für diesen Platz existieren
                        buchungen = db_read("SELECT * FROM buchung WHERE tid=%s", (tid,))
                        
                        if buchungen and len(buchungen) > 0:
                            fehler = f"Tennisplatz mit ID {tid} kann nicht gelöscht werden, da noch {len(buchungen)} Buchung(en) vorhanden sind. Bitte erst alle Buchungen stornieren."
                        else:
                            db_write("DELETE FROM tennisplatz WHERE tid=%s", (tid,))
                            erfolg = f"Tennisplatz '{platz['tennisanlage']}' - Platz {platz['platznummer']} (ID: {tid}) wurde erfolgreich gelöscht."
                            
                except ValueError:
                    fehler = "Tennisplatz-ID muss eine Zahl sein."
                except Exception as e:
                    logging.error(f"Fehler beim Löschen des Tennisplatzes: {e}")
                    fehler = f"Fehler beim Löschen des Tennisplatzes: {str(e)}"
    
    # Alle Tennisplätze für die Übersicht laden - sortiert nach ID
    # datum_der_wartung wird als "wartung" umbenannt für das Template
    try:
        alle_plaetze = db_read("SELECT tid, tennisanlage, platznummer, belag, datum_der_wartung, wid FROM tennisplatz ORDER BY tid")
        # Umbenennen für Template-Kompatibilität
        if alle_plaetze:
            for platz in alle_plaetze:
                platz['wartung'] = platz.get('datum_der_wartung')
    except Exception as e:
        logging.error(f"Fehler beim Laden der Tennisplätze: {e}")
        alle_plaetze = []
    
    return render_template("tennisplätze.html", fehler=fehler, erfolg=erfolg, alle_plaetze=alle_plaetze)

# API Route für AJAX - Wartungsarbeiter-Daten abrufen
@app.route("/get_wartungsarbeiter/<int:wid>")
@login_required
def get_wartungsarbeiter(wid):
    try:
        arbeiter = db_read("SELECT * FROM wartungsarbeiter WHERE wid=%s", (wid,), single=True)
        if not arbeiter:
            return jsonify({"exists": False})
        return jsonify({
            "exists": True,
            "wid": arbeiter["wid"],
            "vorname": arbeiter["vorname"] or "",
            "nachname": arbeiter["nachname"] or "",
            "geburtsdatum": str(arbeiter["geburtsdatum"]) if arbeiter.get("geburtsdatum") else ""
        })
    except Exception as e:
        logging.error(f"Fehler bei get_wartungsarbeiter: {e}")
        return jsonify({"exists": False, "error": str(e)})


# wartungsarbeiter route - KOMPLETTE VERSION ZUM ERSETZEN
@app.route("/wartungsarbeiter", methods=["GET", "POST"])
@login_required
def wartungsarbeiter():
    fehler = None
    erfolg = None
    
    if request.method == "POST":
        aktion = request.form.get("aktion")
        
        # Wartungsarbeiter hinzufügen
        if aktion == "hinzufuegen":
            vorname = request.form.get("vorname", "").strip()
            nachname = request.form.get("nachname", "").strip()
            geburtsdatum = request.form.get("geburtsdatum", "").strip()
            
            if not vorname or not nachname or not geburtsdatum:
                fehler = "Bitte alle Pflichtfelder ausfüllen (Vorname, Nachname, Geburtsdatum)."
            else:
                try:
                    # Prüfen ob Arbeiter bereits existiert
                    existiert = db_read(
                        "SELECT * FROM wartungsarbeiter WHERE vorname=%s AND nachname=%s AND geburtsdatum=%s",
                        (vorname, nachname, geburtsdatum),
                        single=True
                    )
                    
                    if existiert:
                        fehler = f"Wartungsarbeiter '{vorname} {nachname}' mit diesem Geburtsdatum existiert bereits."
                    else:
                        db_write(
                            "INSERT INTO wartungsarbeiter (vorname, nachname, geburtsdatum) VALUES (%s,%s,%s)",
                            (vorname, nachname, geburtsdatum)
                        )
                        erfolg = f"Wartungsarbeiter '{vorname} {nachname}' wurde erfolgreich hinzugefügt."
                        
                except Exception as e:
                    logging.error(f"Fehler beim Hinzufügen des Wartungsarbeiters: {e}")
                    fehler = f"Fehler beim Hinzufügen des Wartungsarbeiters: {str(e)}"
        
        # Wartungsarbeiter löschen
        elif aktion == "loeschen":
            arbeiter_id = request.form.get("arbeiter_id", "").strip()
            
            if not arbeiter_id:
                fehler = "Bitte Wartungsarbeiter-ID eingeben."
            else:
                try:
                    wid = int(arbeiter_id)
                    
                    # Prüfen ob Arbeiter existiert
                    arbeiter = db_read("SELECT * FROM wartungsarbeiter WHERE wid=%s", (wid,), single=True)
                    
                    if not arbeiter:
                        fehler = f"Wartungsarbeiter mit ID {wid} existiert nicht."
                    else:
                        # Tennisplätze, die diesem Arbeiter zugeordnet sind, auf NULL setzen
                        db_write("UPDATE tennisplatz SET wid=NULL WHERE wid=%s", (wid,))
                        
                        # Wartungsarbeiter löschen
                        db_write("DELETE FROM wartungsarbeiter WHERE wid=%s", (wid,))
                        erfolg = f"Wartungsarbeiter '{arbeiter['vorname']} {arbeiter['nachname']}' (ID: {wid}) wurde erfolgreich gelöscht. Alle zugeordneten Tennisplätze wurden aktualisiert."
                            
                except ValueError:
                    fehler = "Wartungsarbeiter-ID muss eine Zahl sein."
                except Exception as e:
                    logging.error(f"Fehler beim Löschen des Wartungsarbeiters: {e}")
                    fehler = f"Fehler beim Löschen des Wartungsarbeiters: {str(e)}"
    
    # Alle Wartungsarbeiter für die Übersicht laden - sortiert nach ID
    try:
        alle_arbeiter = db_read("SELECT wid, vorname, nachname, geburtsdatum FROM wartungsarbeiter ORDER BY wid")
        if not alle_arbeiter:
            alle_arbeiter = []
    except Exception as e:
        logging.error(f"Fehler beim Laden der Wartungsarbeiter: {e}")
        alle_arbeiter = []
    
    return render_template("wartungsarbeiter.html", fehler=fehler, erfolg=erfolg, alle_arbeiter=alle_arbeiter)
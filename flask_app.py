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
                
                # Buchungsnummer abrufen (die gerade erstellte Buchung)
                letzte_buchung = db_read(
                    "SELECT * FROM buchung WHERE nid=%s ORDER BY buchungsnummer DESC LIMIT 1",
                    (nutzer["nid"],),
                    single=True
                )
                
                # Datum formatieren für Session
                from datetime import datetime
                spieldatum_obj = datetime.strptime(spieldatum, '%Y-%m-%d')
                spieldatum_formatiert = spieldatum_obj.strftime('%d.%m.%Y')
                
                # Geburtsdatum formatieren falls vorhanden
                geburtsdatum_str = ""
                if nutzer.get("geburtsdatum"):
                    try:
                        if isinstance(nutzer["geburtsdatum"], str):
                            geburtsdatum_obj = datetime.strptime(nutzer["geburtsdatum"], '%Y-%m-%d')
                        else:
                            geburtsdatum_obj = nutzer["geburtsdatum"]
                        geburtsdatum_str = geburtsdatum_obj.strftime('%d.%m.%Y')
                    except:
                        pass
                
                # Spielzeiten formatieren (HH:MM ohne Sekunden)
                spielbeginn_str = str(letzte_buchung['spielbeginn'])
                spielende_str = str(letzte_buchung['spielende'])
                
                # Falls Zeitformat HH:MM:SS ist, nur HH:MM nehmen
                if len(spielbeginn_str) > 5:
                    spielbeginn_str = spielbeginn_str[:5]
                if len(spielende_str) > 5:
                    spielende_str = spielende_str[:5]
                
                # Alle Daten in Session speichern für Bestätigungsseite
                session['buchung_details'] = {
                    'buchungsnummer': letzte_buchung['buchungsnummer'],
                    'nid': nutzer["nid"],
                    'vorname': nutzer["vorname"],
                    'nachname': nutzer["nachname"],
                    'email': nutzer.get("email", ""),
                    'geburtsdatum': geburtsdatum_str,
                    'tennisanlage': tennisanlage,
                    'platznummer': platznummer,
                    'belag': platz.get("belag", "unbekannt"),
                    'spieldatum': spieldatum,
                    'spieldatum_formatiert': spieldatum_formatiert,
                    'spielbeginn': spielbeginn_str,
                    'spielende': spielende_str,
                    'buchungszeitpunkt': datetime.now().strftime("%d.%m.%Y um %H:%M Uhr")
                }
                
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


@app.route("/bbestätigt")
@login_required
def bbestätigt():
    buchung = session.get('buchung_details', {})
    
    if not buchung:
        return redirect(url_for("buchen"))
    
    return render_template("bbestätigt.html", 
        buchungsnummer=buchung.get('buchungsnummer'),
        nid=buchung.get('nid'),
        vorname=buchung.get('vorname'),
        nachname=buchung.get('nachname'),
        email=buchung.get('email'),
        geburtsdatum=buchung.get('geburtsdatum'),
        tennisanlage=buchung.get('tennisanlage'),
        platznummer=buchung.get('platznummer'),
        belag=buchung.get('belag'),
        spieldatum_formatiert=buchung.get('spieldatum_formatiert'),
        spielbeginn_formatiert=buchung.get('spielbeginn'),
        spielende_formatiert=buchung.get('spielende'),
        buchungszeitpunkt=buchung.get('buchungszeitpunkt')
    )

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
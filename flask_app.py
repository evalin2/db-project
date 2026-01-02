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

@app.route("/buchen")
@login_required
def buchen():
    return render_template("buchen.html")

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

@app.route("/log")
@login_required
def log():
    return render_template("log.html")

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

# Definierter Benutzername und Passwort
USERNAME = "max"
PASSWORD = "1234"

@app.route("/log", methods=["GET", "POST"])
@login_required
def log():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == USERNAME and password == PASSWORD:
            return redirect(url_for("verwaltung"))  # Weiterleitung bei Erfolg
        else:
            return "<h3>Benutzername oder Passwort ist falsch!</h3><a href='/'>Zurück zum Log</a>"

    return render_template("log.html")  # Zeige das Login-Formular

@app.route("/verwaltung")
@login_required
def welcome():
    return "<h2>Willkommen auf der Zielseite!</h2>"

if __name__ == "__main__":
    app.run(debug=True)

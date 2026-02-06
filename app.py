import os
import uuid
import logging
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
import magic  # pip install python-magic-bin  (Windows) or python-magic (Linux/macOS)

from wtforms import StringField, TextAreaField, SelectField, IntegerField, FileField
from wtforms.validators import DataRequired, Email, NumberRange, Optional, Length

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────

app = Flask(__name__)

# NEVER hard-code secrets in production
app.secret_key = os.environ.get("SECRET_KEY") or "dev-fallback-do-not-use-in-prod-2026"

# Folder & limits
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}
ALLOWED_MIMETYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

DB_FILE = "nexusai_jobs.db"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Rate limiting (protects against spam submissions)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per hour"],
    storage_uri="memory://",
)

# CSRF
csrf = CSRFProtect(app)

def init_db():
    if not os.path.exists(DB_FILE):
        import sqlite3
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")  # better concurrency
        c.execute(
            """
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                location TEXT NOT NULL,
                experience_years INTEGER NOT NULL,
                cover_letter TEXT,
                cv_filename TEXT,
                consent_given INTEGER NOT NULL DEFAULT 0,
                submitted_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()
        logger.info("Database and applications table created.")

init_db()

# ────────────────────────────────────────────────
# FORMS
# ────────────────────────────────────────────────

class ApplicationForm(FlaskForm):
    position = SelectField(
        "Position", validators=[DataRequired(message="Please select a position")]
    )
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    phone = StringField("Phone Number", validators=[DataRequired(), Length(max=30)])
    location = StringField("Location (City, Country)", validators=[DataRequired(), Length(max=100)])
    experience = IntegerField(
        "Years of Relevant Experience",
        validators=[DataRequired(), NumberRange(min=0, max=60)],
    )
    cover_letter = TextAreaField(
        "Cover Letter", validators=[DataRequired(), Length(max=4000)]
    )
    cv = FileField("CV/Resume", validators=[Optional()])
    consent = StringField(  # We'll check it's "on"
        "I consent to data processing", validators=[DataRequired()]
    )

    def validate_cv(self, field):
        if field.data and field.data.filename:
            filename = field.data.filename
            if "." not in filename or filename.rsplit(".", 1)[1].lower() not in ALLOWED_EXTENSIONS:
                raise ValueError("Only PDF, DOC, DOCX allowed")

            # Real content-type check
            mime = magic.Magic(mime=True)
            content = field.data.read(1024)
            field.data.seek(0)
            detected = mime.from_buffer(content)
            if detected not in ALLOWED_MIMETYPES:
                raise ValueError("Invalid file content – only PDF/Word documents allowed")

# ────────────────────────────────────────────────
# ROUTES
# ────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/careers")
def careers():
    form = ApplicationForm()
    # Populate positions dynamically if you want – for now static
    form.position.choices = [
        ("", "Select Position"),
        # You can keep the same groups as in HTML or load from config later
        ("Senior Full-Stack Developer", "Senior Full-Stack Developer"),
        ("Junior Developer", "Junior Developer"),
        # ... add others
    ]
    return render_template("careers.html", form=form)

@app.route("/apply", methods=["POST"])
@limiter.limit("6 per hour")  # anti-spam
def apply():
    form = ApplicationForm()

    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", "error")
        return redirect(url_for("careers") + "#apply")

    # File handling
    cv_filename = None
    cv_file = form.cv.data
    if cv_file and cv_file.filename:
        ext = cv_file.filename.rsplit(".", 1)[1].lower()
        cv_filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], cv_filename)
        cv_file.save(save_path)
        logger.info(f"CV uploaded: {cv_filename}")

    try:
        import sqlite3
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO applications
            (position, full_name, email, phone, location, experience_years,
             cover_letter, cv_filename, consent_given, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                form.position.data,
                form.full_name.data.strip(),
                form.email.data.strip(),
                form.phone.data.strip(),
                form.location.data.strip(),
                form.experience.data,
                form.cover_letter.data.strip(),
                cv_filename,
                1 if form.consent.data == "on" else 0,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        conn.close()

        flash("Application submitted successfully! We'll be in touch soon.", "success")
        logger.info(f"New application: {form.position.data} – {form.email.data}")

    except Exception as e:
        logger.exception("Application submission failed")
        flash("Sorry, something went wrong. Please try again later.", "error")

    return redirect(url_for("careers") + "#apply")

# Keep admin simple for now – PROTECT THIS PROPERLY LATER
@app.route("/admin/applications")
def view_applications():
    # TODO: add real authentication (Flask-Login, basic auth, API key, etc.)
    # For now – at least log access
    logger.warning(f"Admin applications viewed from IP: {request.remote_addr}")

    import sqlite3
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM applications ORDER BY submitted_at DESC")
    rows = c.fetchall()
    conn.close()

    return render_template("admin.html", applications=rows)

if __name__ == "__main__":
    # Development only
    app.run(debug=True, host="0.0.0.0", port=5001)
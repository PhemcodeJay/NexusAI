from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime
import os
import uuid

app = Flask(__name__)
app.secret_key = "super-secret-change-me-in-production-2026"
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure uploads directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database file
DB_FILE = "nexusai_jobs.db"

def init_db():
    """Create the SQLite database and table if they don't exist"""
    if not os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
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
                submitted_at TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        print("Database and table created.")

# Initialize DB on startup
init_db()

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    """Render the home page"""
    return render_template('index.html')

@app.route('/careers')
def careers():
    """Render the careers page"""
    return render_template('careers.html')

@app.route('/apply', methods=['POST'])
def apply():
    """Handle job application submissions with CV upload"""
    try:
        position = request.form.get('position', '').strip()
        full_name = request.form.get('fullName', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        location = request.form.get('location', '').strip()
        experience = request.form.get('experience', '0').strip()
        cover_letter = request.form.get('coverLetter', '').strip()
        
        # File upload handling
        cv_filename = None
        if 'cv' in request.files:
            cv_file = request.files['cv']
            if cv_file and cv_file.filename != '':
                if allowed_file(cv_file.filename):
                    # Generate unique filename
                    original_filename = cv_file.filename
                    file_ext = original_filename.rsplit('.', 1)[1].lower()
                    unique_filename = f"{uuid.uuid4().hex}.{file_ext}"
                    cv_filename = unique_filename
                    
                    # Save file
                    cv_file.save(os.path.join(app.config['UPLOAD_FOLDER'], cv_filename))
                else:
                    flash("Invalid file type. Please upload PDF, DOC, DOCX, or TXT files only.", "error")
                    return redirect(url_for('careers') + "#apply")

        # Basic validation
        errors = []
        if not position:
            errors.append("Please select a position.")
        if not full_name:
            errors.append("Full name is required.")
        if not email or "@" not in email:
            errors.append("Valid email is required.")
        if not phone:
            errors.append("Phone number is required.")
        if not location:
            errors.append("Location is required.")
        
        try:
            exp_years = int(experience)
            if exp_years < 0:
                errors.append("Experience cannot be negative.")
        except ValueError:
            errors.append("Experience must be a number.")
            
        # CV is optional but recommended
        if not cv_filename:
            flash("Note: No CV uploaded. Please consider attaching your CV for better consideration.", "warning")

        if errors:
            for msg in errors:
                flash(msg, "error")
            return redirect(url_for('careers') + "#apply")

        # Save to SQLite
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO applications 
            (position, full_name, email, phone, location, experience_years, cover_letter, cv_filename, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            position,
            full_name,
            email,
            phone,
            location,
            exp_years,
            cover_letter,
            cv_filename,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()

        flash("Application submitted successfully! We will contact you soon.", "success")
        return redirect(url_for('careers') + "#apply")

    except Exception as e:
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(url_for('careers') + "#apply")

@app.route('/admin/applications')
def view_applications():
    """Admin view of applications - PROTECT THIS IN PRODUCTION!"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM applications ORDER BY submitted_at DESC")
    rows = c.fetchall()
    conn.close()

    # Create a simple HTML table for admin view
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NexusAI - Job Applications</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
            th { background-color: #0a2540; color: white; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            .has-cv { color: green; font-weight: bold; }
            .no-cv { color: gray; }
        </style>
    </head>
    <body>
        <h1>Job Applications</h1>
        <table>
            <tr>
                <th>ID</th>
                <th>Position</th>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Location</th>
                <th>Experience</th>
                <th>CV</th>
                <th>Submitted</th>
            </tr>
    """
    
    for row in rows:
        has_cv = "Yes" if row[8] else "No"
        cv_class = "has-cv" if row[8] else "no-cv"
        html += f"""
            <tr>
                <td>{row[0]}</td>
                <td>{row[1]}</td>
                <td>{row[2]}</td>
                <td><a href="mailto:{row[3]}">{row[3]}</a></td>
                <td>{row[4]}</td>
                <td>{row[5]}</td>
                <td>{row[6]} years</td>
                <td class="{cv_class}">{has_cv}</td>
                <td>{row[9]}</td>
            </tr>
        """
    
    html += """
        </table>
        <p><a href="/">Back to Home</a></p>
        <p><strong>Total Applications:</strong> """ + str(len(rows)) + """</p>
    </body>
    </html>
    """
    
    return html

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
import random
from flask import render_template, url_for, Flask, request, redirect, json, jsonify, session, flash
import pymysql
import requests
from werkzeug.utils import secure_filename
import re
from datetime import date, datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
load_dotenv()


# ---------------- EMAIL OTP ----------------
def send_otp_email(receiver_email, otp):
    sender_email = os.getenv("EMAIL_USER")
    app_password = os.getenv("EMAIL_PASS")

    subject = "OTP Verification - The Knowledge Hub Library"
    body = f"""
Hello,

Your One-Time Password (OTP) is: {otp}

Please do not share this OTP with anyone.

Regards,
The Knowledge Hub Library
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False


# ---------------- FLASK APP ----------------
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')


# ---------------- MYSQL (PyMySQL) ----------------
def get_db_connection():
    return pymysql.connect(
        host="maglev.proxy.rlwy.net",
        user="root",
        password="xyGQQjuqWZxRndtFQxRYTulRwcHtQWue",
        database="railway",
        port=43539,
        ssl={"ssl": {}},
        cursorclass=pymysql.cursors.DictCursor  # 👈 THIS LINE
    )



# ---------------- FILE UPLOAD ----------------
UPLOAD_FOLDER = os.path.join(app.root_path, 'static')
UPLOAD_FOLDER_USER = 'static/uploads'
app.config['UPLOAD_FOLDER_USER'] = UPLOAD_FOLDER_USER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)



# ---------------- VALIDATION HELPERS ----------------
def validate_mobile(number):
    pattern = r'^[6-9]\d{9}$'   # Only 10-digit starting 6–9
    return bool(re.match(pattern, number))

def validate_email(email):
    pattern = r'^[^@]+@[^@]+\.[^@]+$'
    return bool(re.match(pattern, email))

# ---------------- ROUTES ----------------
@app.route('/', methods=['GET', 'POST'])
def owner():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    return render_template('overview.html')

@app.route("/db-test")
def db_test():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM books")
    result = cur.fetchone()
    cur.close()
    conn.close()
    return f"Books in Railway DB: {result['total']}"


# ========== STAFF ==========
@app.route('/add_staff', methods=['GET', 'POST'])
def add_staff():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        name = request.form.get("name").strip()
        phone = request.form.get("phone").strip()
        password = request.form.get("password").strip()

        # Validate Full Name (only letters, optional first & last name)
        import re
        if not re.fullmatch(r"[A-Za-z]{2,20}( [A-Za-z]{2,20})?", name):
            flash("⚠️ Please enter a valid name (letters only, first and last name optional).", "error")
            return redirect(url_for('add_staff'))

        # Validate Phone number (assuming validate_mobile function exists)
        if not validate_mobile(phone):
            flash("⚠️ Please enter a valid 10-digit phone number.", "error")
            return redirect(url_for('add_staff'))

        # Insert into database
        cur.execute(
            "INSERT INTO signup_staff(name, phone, password) VALUES (%s, %s, %s)",
            (name, phone, password)
        )
        conn.commit()
        cur.close()

        flash("✅ Staff added successfully!", "success")
        return redirect(url_for('add_staff'))  # Redirect ensures flash message shows properly

    return render_template('add_staff.html')


@app.route('/view_staff', methods=['GET'])
def view_staff():
    search = request.args.get('search', '').strip()

    conn = get_db_connection()
    cur = conn.cursor()


    if search:
        cur.execute("""
            SELECT * FROM signup_staff
            WHERE name LIKE %s
               OR phone LIKE %s
               OR admin_id LIKE %s
        """, (f"%{search}%", f"%{search}%", f"%{search}%"))
    else:
        cur.execute("SELECT * FROM signup_staff")

    staff_data = cur.fetchall()
    cur.close()

    return render_template(
        "view_staff.html",
        staff_data=staff_data,
        search=search
    )

@app.route('/search_staff')
def search_staff():
    query = request.args.get('q', '').strip()

    conn = get_db_connection()
    cur = conn.cursor()

    if query:
        cur.execute("""
            SELECT * FROM signup_staff
            WHERE name LIKE %s
               OR phone LIKE %s
               OR admin_id LIKE %s
        """, (f"%{query}%", f"%{query}%", f"%{query}%"))
    else:
        cur.execute("SELECT * FROM signup_staff")

    data = cur.fetchall()
    cur.close()

    return jsonify(data)


# ========== ADMIN ==========
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS total_books FROM books")
    total_books = cur.fetchone()['total_books']

    cur.execute("SELECT COUNT(*) AS issued_books FROM borrowers WHERE status='Borrowed'")
    issued_books = cur.fetchone()['issued_books']

    cur.execute("SELECT COUNT(*) AS total_members FROM member_records")
    total_members = cur.fetchone()['total_members']

    cur.execute("SELECT COUNT(*) AS total_staff FROM signup_staff")
    total_staff = cur.fetchone()['total_staff']

    cur.close()

    return render_template(
        "overview.html",
        total_books=total_books,
        issued_books=issued_books,
        total_members=total_members,
        total_staff=total_staff
    )



@app.route('/logout')
def logout():
    session.clear()
    flash("✅ Logged out successfully!", "success")
    return redirect(url_for('admin_login'))

@app.route('/admin_settings', methods=['GET', 'POST'])
def admin_settings():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        name = request.form.get('name')
        mailid = request.form.get('mailid')
        phone = request.form.get('phone')

        # Get current photo
        cur.execute("SELECT photo FROM signup_staff WHERE admin_id=%s", [session['admin_id']])
        current_admin = cur.fetchone()
        photo_filename = current_admin.get('photo') if current_admin and current_admin.get('photo') else None

        # Handle new photo
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '' and allowed_file(file.filename):
                # Delete old photo if exists
                if photo_filename and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)):
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))
                    except:
                        pass

                # Save new photo
                filename = secure_filename(f"admin_{session['admin_id']}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo_filename = filename

                # ✅ Keep photo constant after update
                session['photo'] = photo_filename

        # Update DB
        cur.execute("""
            UPDATE signup_staff 
            SET name=%s, mailid=%s, phone=%s, photo=%s 
            WHERE admin_id=%s
        """, (name, mailid, phone, photo_filename, session['admin_id']))
        conn.commit()
        cur.close()

        flash("✅ Profile updated successfully!", "success")
        return redirect(url_for('admin_settings'))

    # GET - Fetch admin data
    cur.execute("SELECT * FROM signup_staff WHERE admin_id=%s", [session['admin_id']])
    admin = cur.fetchone()
    cur.close()

    return render_template('admin_settings.html', admin=admin)




@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST': 
        phone = request.form.get("phone")
        password = request.form.get("password")

        if not validate_mobile(phone):
            flash("⚠️ Enter a valid 10-digit phone number.", "danger")
            return redirect(url_for('admin_login'))

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM signup_staff WHERE phone=%s AND password=%s", (phone, password))  
        result = cur.fetchone()
        cur.close()

        if result:
            session['phone'] = phone
            session['admin_id'] = result['admin_id']
            session['admin_name'] = result['name']
            flash("✅ Login successful!", "success")
            return redirect(url_for('overview'))
        else:
            flash("❌ Invalid phone or password", "danger")
    return render_template('admin_login.html')

@app.route('/overview')
def overview():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()

    # Total Books
    cur.execute("SELECT COUNT(*) AS total FROM books")
    row = cur.fetchone()
    total_books = row['total'] if row else 0

    # Issued Books (Currently Borrowed books - not returned)
    cur.execute("SELECT COUNT(*) AS issued FROM borrowers WHERE status='Borrowed'")
    row = cur.fetchone()
    issued_books = row['issued'] if row else 0

    # Total Members
    cur.execute("SELECT COUNT(*) AS members FROM member_records")
    row = cur.fetchone()
    total_members = row['members'] if row else 0

    # Total Staff
    cur.execute("SELECT COUNT(*) AS staff FROM signup_staff")
    row = cur.fetchone()
    total_staff = row['staff'] if row else 0

    cur.close()

    return render_template(
        'overview.html',
        total_books=total_books,
        issued_books=issued_books,
        total_members=total_members,
        total_staff=total_staff
    )

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':

        # ================= STEP 1: SEND OTP =================
        if 'otp_sent' not in session:
            phone = request.form.get('phone')

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM signup_staff WHERE phone=%s", [phone])
            user = cur.fetchone()
            cur.close()

            if not user:
                flash('❌ Phone number not found!', 'error')
                return render_template('forgot_password.html', otp_sent=False)

            email = user.get('email') or user.get('mailid')
            if not email:
                flash('❌ Email not found for this user.', 'error')
                return render_template('forgot_password.html', otp_sent=False)

            otp = random.randint(1000, 9999)

            # 🔥 SEND OTP USING GMAIL SMTP
            email_sent = send_otp_email(email, otp)

            if not email_sent:
                flash('❌ Failed to send OTP. Please try again.', 'error')
                return render_template('forgot_password.html', otp_sent=False)

            session['otp_sent'] = True
            session['otp'] = str(otp)
            session['phone'] = phone
            session['reset_admin_id'] = user['admin_id']

            flash('✅ OTP has been sent to your registered email.', 'success')
            return render_template('forgot_password.html', otp_sent=True)

        # ================= STEP 2: VERIFY OTP =================
        else:
            entered_otp = request.form.get('otp')

            if entered_otp == session.get('otp'):
                flash('✅ OTP verified successfully!', 'success')
                return redirect(url_for('reset_password'))
            else:
                flash('❌ Invalid OTP, please try again.', 'error')
                return render_template('forgot_password.html', otp_sent=True)

    # ================= DEFAULT GET =================
    return render_template('forgot_password.html', otp_sent=False)




@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if 'reset_admin_id' not in session:
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash('❌ Passwords do not match!', 'error')
            return render_template('reset_password.html')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE signup_staff SET password=%s WHERE admin_id=%s",
            (new_password, session['reset_admin_id'])
        )
        conn.commit()
        cur.close()

        # 🔥 CLEAR OTP SESSION
        session.pop('otp', None)
        session.pop('otp_sent', None)
        session.pop('reset_admin_id', None)
        session.pop('phone', None)

        flash('✅ Password reset successfully! Please login.', 'success')
        return redirect(url_for('admin_login'))

    return render_template('reset_password.html')



@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        current_pass = request.form.get('current_password')
        new_pass = request.form.get('new_password')
        admin_id = session['admin_id']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password FROM signup_staff WHERE admin_id=%s", [admin_id])
        result = cur.fetchone()

        if result and current_pass == result['password']:
            cur.execute("UPDATE signup_staff SET password=%s WHERE admin_id=%s", (new_pass, admin_id))
            conn.commit()
            flash("✅ Password changed successfully!", "success")   
        else:
            flash("❌ Incorrect current password!", "danger")
        cur.close()
    return render_template('change_password.html')

# ========== BOOKS ==========
@app.route('/add_book', methods=['GET', 'POST'])
def add_book():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()

    # ✅ Fetch all admins, genres, and only shelves that are NOT full
    cur.execute("SELECT admin_id FROM signup_staff")
    admin = cur.fetchall()
    cur.execute("SELECT genre_id, genre_name FROM genre ORDER BY genre_name ASC")
    genres = cur.fetchall()
    cur.execute("""
        SELECT shelf_id, shelf_name 
        FROM shelf 
        WHERE total_count < capacity 
        ORDER BY shelf_name ASC
    """)
    shelves = cur.fetchall()

    if request.method == 'POST':
        # --- ✅ Collect Form Data ---
        book_name = request.form.get('book_name', '').strip().title()
        author = request.form.get('author', '').strip().title()
        publication = request.form.get('publication', '').strip().title()
        year = request.form.get('year', '').strip()
        genre_name = request.form.get('genre_name', '').strip().title()
        copies = request.form.get('copies', '').strip()
        description = request.form.get('description', '').strip().capitalize()
        amount = request.form.get('amount', '').strip()
        shelf_name = request.form.get('shelf', '').strip()
        admin_id = session.get('admin_id')

        # --- ✅ Server-side Validation ---
        errors = []

        # ✅ Book Name validation (now allows numbers & special characters)
        if not book_name or len(book_name) > 100:
            errors.append("Book name must be between 1-100 characters")
        # No regex validation for book name - allows any characters

        # Author validation
        if not author or len(author) > 50:
            errors.append("Author name must be between 1-50 characters")
        elif not re.match(r'^[A-Za-z\s]+$', author):
            errors.append("Author name can only contain alphabets and spaces")

        # Publication validation
        if publication and len(publication) > 100:
            errors.append("Publication name must be 100 characters or less")
        elif publication and not re.match(r'^[A-Za-z\s]*$', publication):
            errors.append("Publication name can only contain alphabets and spaces")

        # Genre validation
        if not genre_name or len(genre_name) > 30:
            errors.append("Genre must be between 1-30 characters")
        elif not re.match(r'^[A-Za-z\s]+$', genre_name):
            errors.append("Genre can only contain alphabets and spaces")

        # Shelf validation
        if not shelf_name or len(shelf_name) > 20:
            errors.append("Shelf must be between 1-20 characters")
        elif not re.match(r'^[A-Za-z0-9\s]+$', shelf_name):
            errors.append("Shelf can only contain alphanumeric characters and spaces")

        # Description validation
        if not description or len(description) > 500:
            errors.append("Description must be between 1-500 characters")

        # Amount validation
        if amount:
            if len(amount) > 4:
                errors.append("Amount must be 4 digits or less")
            elif not re.match(r'^[0-9]+$', amount):
                errors.append("Amount can only contain numbers")
            elif int(amount) > 1000:
                errors.append("Amount cannot exceed ₹1000")

        # Copies validation
        try:
            copies = int(copies)
            if copies < 1 or copies > 10:
                errors.append("Copies must be between 1-10")
        except (ValueError, TypeError):
            errors.append("Copies must be a valid number between 1-10")

        # Year validation
        if year:
            try:
                year_int = int(year)
                if year_int < 1800 or year_int > 2025:
                    errors.append("Year must be between 1800-2025")
            except ValueError:
                errors.append("Year must be a valid number")

        # If there are validation errors, return to form
        if errors:
            for error in errors:
                flash(error, "danger")
            cur.close()
            return redirect(url_for('add_book'))

        # Convert copies to int after validation
        copies = int(copies)

        # --- ✅ Handle Genre ---
        cur.execute("SELECT genre_id FROM genre WHERE LOWER(genre_name) = LOWER(%s)", (genre_name,))
        existing_genre = cur.fetchone()
        if existing_genre:
            genre_id = existing_genre['genre_id']
        else:
            cur.execute("INSERT INTO genre (genre_name) VALUES (%s)", (genre_name,))
            conn.commit()
            genre_id = cur.lastrowid

        # --- ✅ Normalize Shelf Name ---
        def normalize_shelf_name(raw):
            s = re.sub(r'\s+', ' ', raw).strip()
            parts = s.split(' ')
            normalized = []
            for p in parts:
                if re.match(r'^[aA]\d+$', p) or re.match(r'^[rR]\d+$', p):
                    normalized.append(p.upper())
                else:
                    normalized.append(p.title())
            return ' '.join(normalized)

        shelf_name = normalize_shelf_name(shelf_name)

        # --- ✅ Find Shelf Record ---
        cur.execute("SELECT * FROM shelf WHERE LOWER(shelf_name) = LOWER(%s)", (shelf_name,))
        shelf_record = cur.fetchone()

        if not shelf_record:
            # Create a new shelf if not exists (default capacity = 10)
            cur.execute(
                "INSERT INTO shelf (shelf_name, genre_id, total_count, capacity) VALUES (%s, %s, %s, %s)",
                (shelf_name, genre_id, 0, 10)
            )
            conn.commit()
            shelf_id = cur.lastrowid
            total_count = 0
            capacity = 10
        else:
            shelf_id = shelf_record['shelf_id']
            total_count = shelf_record['total_count']
            capacity = shelf_record['capacity']

        # --- ✅ Capacity Check ---
        if total_count + copies > capacity:
            flash(f"You can add only up to {capacity} books in shelf '{shelf_name}'. "
                  f"Currently it has {total_count}, so you can add at most {capacity - total_count} more.", "danger")
            cur.close()
            return redirect(url_for('add_book'))

        # --- ✅ Insert Book ---
        cur.execute("""
            INSERT INTO books
            (book_name, author, publication, year, genre_name, genre_id, copies, description, amount, shelf_name, shelf_id, admin_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (book_name, author, publication, year, genre_name, genre_id, copies, description, amount, shelf_name, shelf_id, admin_id))

        # --- ✅ Update Shelf Count ---
        new_total = total_count + copies
        if new_total > capacity:
            new_total = capacity  # Safety cap

        cur.execute("UPDATE shelf SET total_count = %s WHERE shelf_id = %s", (new_total, shelf_id))
        conn.commit()

        cur.close()
        flash("Book added successfully!", "success")
        return redirect(url_for('add_book'))

    # ✅ Render with only shelves that are not full
    return render_template('add_book.html', active_section='add_book', admin=admin, genres=genres, shelves=shelves)

@app.route('/update_book/<int:book_id>', methods=['GET', 'POST'])
def update_book(book_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()

    # helper: normalize shelf name (same as add_book)
    def normalize_shelf_name(raw):
        s = re.sub(r'\s+', ' ', (raw or '')).strip()
        parts = s.split(' ')
        normalized = []
        for p in parts:
            if re.match(r'^[aA]\d+$', p) or re.match(r'^[rR]\d+$', p):
                normalized.append(p.upper())
            else:
                normalized.append(p.title())
        return ' '.join(normalized)

    try:
        # Fetch lists for form selects (admins, genres, shelves not full)
        cur.execute("SELECT admin_id FROM signup_staff")
        admin_list = cur.fetchall()
        cur.execute("SELECT genre_id, genre_name FROM genre ORDER BY genre_name ASC")
        genres = cur.fetchall()
        cur.execute("""
            SELECT shelf_id, shelf_name 
            FROM shelf 
            WHERE total_count < capacity 
            ORDER BY shelf_name ASC
        """)
        available_shelves = cur.fetchall()

        # Fetch existing book
        cur.execute("SELECT * FROM books WHERE book_id = %s", (book_id,))
        book = cur.fetchone()
        if not book:
            cur.close()
            flash("Book not found.", "danger")
            return redirect(url_for('view_books'))  # adjust to your listing route

        if request.method == 'GET':
            # Render form pre-filled with book data
            return render_template(
                'update_book.html',
                book=book,
                admin=admin_list,
                genres=genres,
                shelves=available_shelves,
                
            )

        # --------------- POST handling ---------------
        # Collect form values (use existing values as fallback)
        book_name = request.form.get('book_name', book['book_name']).strip().title()
        author = request.form.get('author', book['author']).strip().title()
        publication = request.form.get('publication', book['publication']).strip().title()
        year = request.form.get('year', book.get('year'))
        genre_name = request.form.get('genre_name', book.get('genre_name', '')).strip().title()
        copies_raw = request.form.get('copies', book['copies'])
        try:
            copies = int(copies_raw)
            if copies < 0:
                raise ValueError()
        except Exception:
            flash("Invalid number of copies.", "danger")
            cur.close()
            return redirect(url_for('update_book', book_id=book_id))
        description = request.form.get('description', book.get('description') or '').strip().capitalize()
        amount = request.form.get('amount', book.get('amount'))
        shelf_name_input = request.form.get('shelf', book.get('shelf_name') or '').strip()
        shelf_name = normalize_shelf_name(shelf_name_input)
        admin_id = session.get('admin_id')

        # --- Handle genre existence/creation (same logic as add_book) ---
        cur.execute("SELECT genre_id FROM genre WHERE LOWER(genre_name) = LOWER(%s)", (genre_name,))
        existing_genre = cur.fetchone()
        if existing_genre:
            genre_id = existing_genre['genre_id']
        else:
            cur.execute("INSERT INTO genre (genre_name) VALUES (%s)", (genre_name,))
            conn.commit()
            genre_id = cur.lastrowid

        # --- Find or create target shelf ---
        cur.execute("SELECT * FROM shelf WHERE LOWER(shelf_name) = LOWER(%s)", (shelf_name,))
        target_shelf = cur.fetchone()
        if not target_shelf:
            # create shelf default capacity 10
            cur.execute(
                "INSERT INTO shelf (shelf_name, genre_id, total_count, capacity) VALUES (%s, %s, %s, %s)",
                (shelf_name, genre_id, 0, 10)
            )
            conn.commit()
            target_shelf_id = cur.lastrowid
            target_total = 0
            target_capacity = 10
        else:
            target_shelf_id = target_shelf['shelf_id']
            target_total = target_shelf['total_count']
            target_capacity = target_shelf['capacity']

        # --- Get old shelf info & old copies from current book row ---
        old_shelf_id = book.get('shelf_id')
        old_shelf_name = book.get('shelf_name')
        old_copies = int(book.get('copies') or 0)

        # If old shelf id exists, fetch its current totals (fresh)
        if old_shelf_id:
            cur.execute("SELECT * FROM shelf WHERE shelf_id = %s", (old_shelf_id,))
            old_shelf = cur.fetchone()
            if old_shelf:
                old_shelf_total = old_shelf['total_count']
                old_shelf_capacity = old_shelf['capacity']
            else:
                # fallback safety
                old_shelf_total = 0
                old_shelf_capacity = 10
        else:
            old_shelf = None
            old_shelf_total = 0
            old_shelf_capacity = 10

        # --- Capacity checks and compute new totals ---
        # Case A: same shelf (by id)
        if old_shelf_id == target_shelf_id:
            # delta to apply to that shelf
            delta = copies - old_copies
            new_total_for_shelf = old_shelf_total + delta
            if new_total_for_shelf > target_capacity:
                flash(f"Cannot set copies to {copies}. Shelf '{shelf_name}' capacity ({target_capacity}) would be exceeded. "
                      f"Current shelf count: {old_shelf_total}, change needed: {delta}.", "danger")
                cur.close()
                return redirect(url_for('update_book', book_id=book_id))
            # safe: update shelf total_count later
            update_old_shelf = True
            update_target_shelf = False  # same shelf handled by one update
        else:
            # shelf changed: subtract old_copies from old shelf, add copies to target shelf
            new_total_old_shelf = max(0, old_shelf_total - old_copies)
            new_total_target_shelf = target_total + copies
            if new_total_target_shelf > target_capacity:
                flash(f"Cannot move book to shelf '{shelf_name}' with {copies} copies: target shelf capacity ({target_capacity}) would be exceeded. "
                      f"Target current: {target_total}.", "danger")
                cur.close()
                return redirect(url_for('update_book', book_id=book_id))
            update_old_shelf = True
            update_target_shelf = True

        # --- All checks passed: perform update inside transaction-like block ---
        try:
            # Update books row (update fields)
            cur.execute("""
                UPDATE books
                SET book_name=%s, author=%s, publication=%s, year=%s,
                    genre_name=%s, genre_id=%s, copies=%s, description=%s,
                    amount=%s, shelf_name=%s, shelf_id=%s, admin_id=%s
                WHERE book_id = %s
            """, (book_name, author, publication, year, genre_name, genre_id, copies,
                  description, amount, shelf_name, target_shelf_id, admin_id, book_id))

            # Update shelf totals
            if old_shelf_id == target_shelf_id:
                # single update for that shelf
                cur.execute("UPDATE shelf SET total_count = total_count + %s WHERE shelf_id = %s", (copies - old_copies, target_shelf_id))
            else:
                # subtract from old shelf (if existed)
                if old_shelf_id:
                    cur.execute("UPDATE shelf SET total_count = GREATEST(total_count - %s, 0) WHERE shelf_id = %s", (old_copies, old_shelf_id))
                # add to new shelf
                cur.execute("UPDATE shelf SET total_count = total_count + %s WHERE shelf_id = %s", (copies, target_shelf_id))

            conn.commit()
        except Exception as e:
            conn.rollback()
            cur.close()
            flash("An error occurred while updating the book: " + str(e), "danger")
            return redirect(url_for('update_book', book_id=book_id))

        cur.close()
        flash("Book updated successfully!", "success")
        return redirect(url_for('view_books'))  # adjust to your listing route

    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        cur.close()
        flash("Unexpected error: " + str(e), "danger")
        return redirect(url_for('view_books'))
    
@app.route('/view_books', methods=['GET'])
def view_books():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of items per page

    # ✅ Use DictCursor consistently
    conn = get_db_connection()
    cur = conn.cursor()

    # Get all book names
    cur.execute("SELECT book_name FROM books")
    all_books = cur.fetchall()

    # Count total books for pagination
    if search:
        cur.execute("SELECT COUNT(*) AS count FROM books WHERE book_name LIKE %s", ('%' + search + '%',))
    else:
        cur.execute("SELECT COUNT(*) AS count FROM books")

    # ✅ Access by key name instead of index
    result = cur.fetchone()
    total_books = result['count'] if result else 0
    total_pages = (total_books + per_page - 1) // per_page  # Ceiling division

    # Calculate offset
    offset = (page - 1) * per_page

    # Fetch books with pagination
    if search:
        cur.execute("""
            SELECT * FROM books 
            WHERE book_name LIKE %s 
            ORDER BY book_id DESC 
            LIMIT %s OFFSET %s
        """, ('%' + search + '%', per_page, offset))
    else:
        cur.execute("""
            SELECT * FROM books 
            ORDER BY book_id DESC 
            LIMIT %s OFFSET %s
        """, (per_page, offset))

    books = cur.fetchall()
    cur.close()

    return render_template(
        'view_books.html',
        books=books,
        all_books=all_books,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_books=total_books
    )


@app.route('/manage_books', methods=['GET'])
def manage_books():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()

    # Pagination setup
    per_page = 10  # number of books per page
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * per_page

    # Get total number of books
    cur.execute("SELECT COUNT(*) AS total FROM books")
    total_books = cur.fetchone()['total']
    total_pages = (total_books + per_page - 1) // per_page

    # Fetch paginated books
    cur.execute("""
        SELECT * FROM books 
        ORDER BY book_id DESC 
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    books = cur.fetchall()
    cur.close()

    return render_template(
        'manage_books.html',
        books=books,
        page=page,
        total_pages=total_pages,
        total_books=total_books,
        per_page=per_page
    )

@app.route('/delete_book/<int:book_id>', methods=['GET', 'POST'])
def delete_book(book_id):
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM books WHERE book_id = %s", (book_id,))
        conn.commit()
        flash("✅ Book deleted successfully!", "success")

    except Exception as e:
        conn.rollback()
        print("DELETE BOOK ERROR:", e)
        flash("❌ Failed to delete book", "danger")

    finally:
        cur.close()
        conn.close()

    return redirect(url_for('manage_books'))

@app.route('/member_records', methods=['GET', 'POST'])
def member_records():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()
    members = []
    member_info = None
    show_form = True
    new_member_id = None

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()

        # Only phone check
        if 'check_phone' in request.form:
            cur.execute("SELECT * FROM member_records WHERE phone = %s", (phone,))
            member_info = cur.fetchone()
            if member_info:
                # ✅ Store member_id in session when phone found
                session['member_id'] = member_info['member_id']
                flash(f"✅ Phone already registered with Name: {member_info['name']} and Email: {member_info['email']}", "info")
                show_form = False
            else:
                flash("ℹ️ Phone not registered. You can fill the form to add new member.", "info")

        # Full form submission
        else:
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            joining_date = request.form.get('joining_date')
            address = request.form.get('address', '').strip()
            photo = request.files['photo']
            admin_id = session['admin_id']

            

            # Validate
            if not validate_mobile(phone):
                flash("⚠️ Please enter a valid 10-digit phone number.", "danger")
            elif not validate_email(email):
                flash("⚠️ Please enter a valid email address.", "danger")
            else:
                cur.execute("SELECT * FROM member_records WHERE phone = %s", (phone,))
                existing_member = cur.fetchone()
                if existing_member:
                    session['member_id'] = existing_member['member_id']
                    flash(f"✅ Member '{existing_member['name']}' already exists. You can borrow directly.", "info")
                    show_form = False
                    member_info = existing_member
                else:
                    if photo and allowed_file(photo.filename):
                     filename = secure_filename(photo.filename)
                     unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            
                     photo_save_path = os.path.join(app.config['UPLOAD_FOLDER_USER'], unique_filename)
                     photo.save(photo_save_path)

                     photo_db_path = os.path.join('uploads/users', unique_filename).replace("\\", "/")
                    else:
                      flash("Invalid file format or no photo uploaded. Please upload a valid image.", "error")
                      return redirect(url_for('member_records'))
            cur.execute("""
                        INSERT INTO member_records (name, phone, email, joining_date, address, admin_id, photo_path)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (name, phone, email, joining_date, address, admin_id, photo_db_path))
            conn.commit()
            new_member_id = cur.lastrowid
            session['member_id'] = new_member_id
            flash(f"✅ New member '{name}' added successfully!", "success")
                    
                    # ✅ Redirect to all_books.html
            cur.close()
            return redirect(url_for('all_books'))

    # Fetch all members for table - NEW members FIRST
    cur.execute("""
    SELECT m.*, s.name AS admin_name
    FROM member_records m
    LEFT JOIN signup_staff s ON m.admin_id = s.admin_id
    ORDER BY m.member_id DESC
""")

    members_data = cur.fetchall()

    members = []
    for member in members_data:
        member_dict = dict(member)
        if new_member_id and member['member_id'] == new_member_id:
            member_dict['is_new'] = True
        else:
            member_dict['is_new'] = False
        members.append(member_dict)

    cur.close()
    return render_template('member_records.html', members=members, member_info=member_info, show_form=show_form)


@app.route('/update_member/<int:member_id>', methods=['GET', 'POST'])
def update_member(member_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM member_records WHERE member_id=%s", (member_id,))
    member = cur.fetchone()

    if member and member['joining_date']:
        member['joining_date'] = member['joining_date'].strftime('%Y-%m-%d')

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        joining_date = request.form['joining_date']
        address = request.form['address']
        admin_id = session['admin_id']

        if not validate_mobile(phone):
            flash(" Enter a valid 10-digit phone number.", "danger")
            return redirect(url_for('update_member', member_id=member_id))
        if not validate_email(email):
            flash(" Enter a valid email address.", "danger")
            return redirect(url_for('update_member', member_id=member_id))

        cur.execute("""
            UPDATE member_records
            SET name=%s, phone=%s, email=%s, joining_date=%s, address=%s, admin_id=%s
            WHERE member_id=%s
        """, (name, phone, email, joining_date, address, admin_id, member_id))
        conn.commit()
        flash('✅ Member updated successfully!', 'success')
        return redirect(url_for('member_records'))

    cur.close()
    return render_template('update_member.html', member=member)

@app.route('/delete_member/<int:member_id>')
def delete_member(member_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            "DELETE FROM member_records WHERE member_id = %s",
            (member_id,)
        )
        conn.commit()
        flash('✅ Member deleted successfully!', 'success')

    except Exception as e:
        conn.rollback()
        print("DELETE MEMBER ERROR:", e)
        flash('❌ Failed to delete member', 'danger')

    finally:
        cur.close()
        conn.close()

    return redirect(url_for('member_records'))

# ========== BORROWING ==========
@app.route('/all_books', methods=['GET'])
def all_books():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    search = request.args.get('search', '')
    conn = get_db_connection()
    cur = conn.cursor()
    if search:
        cur.execute("SELECT * FROM books WHERE book_name LIKE %s", ('%' + search + '%',))
    else:
        cur.execute("SELECT * FROM books")
    books = cur.fetchall()
    cur.close()
    return render_template("all_books.html", books=books)

@app.route('/confirm_borrow', methods=['GET', 'POST'])
def confirm_borrow():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    selected_book_ids = request.form.getlist('selected_books')
    if not selected_book_ids:
        flash(" No books were selected for borrowing.", "error")
        return redirect(url_for('all_books'))

    conn = get_db_connection()
    cur = conn.cursor()
    placeholders = ', '.join(['%s'] * len(selected_book_ids))
    query = f"SELECT book_id, book_name, author, amount FROM books WHERE book_id IN ({placeholders})"
    cur.execute(query, selected_book_ids)
    selected_books_details = cur.fetchall()
    cur.close()
    

    return render_template("confirm_borrow.html",selected_books=selected_books_details,selected_book_ids=selected_book_ids)

@app.route('/finalize_borrow', methods=['POST'])
def finalize_borrow():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    member_id = session.get('member_id')
    borrow_date_str = request.form.get('issue_date')
    duration = int(request.form.get('duration'))
    book_ids = request.form.getlist('book_ids')
    amounts = request.form.getlist('amounts')

    borrow_date = datetime.strptime(borrow_date_str, '%Y-%m-%d')
    return_date = borrow_date + timedelta(days=duration)
    fine_per_day = 5
    fine = (duration - 30) * fine_per_day if duration > 30 else 0

    book_total = 0
    conn = get_db_connection()
    cur = conn.cursor()

    for i in range(len(book_ids)):
        book_id = book_ids[i]
        amount = float(amounts[i])

        # ✅ Check if book is available
        cur.execute("SELECT copies FROM books WHERE book_id = %s", (book_id,))
        book = cur.fetchone()

        if not book or book['copies'] <= 0:
            flash(f"❌ Book ID {book_id} is out of stock!", "danger")
            continue  # skip out-of-stock book

        total_amount = amount * duration
        book_total += total_amount

        # ✅ Borrow record insert
        cur.execute("""
            INSERT INTO borrowers (book_id, borrow_date, return_date, duration, total_amount, member_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (book_id, borrow_date_str, return_date.strftime('%Y-%m-%d'), duration, total_amount, member_id))

        # ✅ Reduce stock
        cur.execute("UPDATE books SET copies = copies - 1 WHERE book_id = %s", (book_id,))

    grand_total = book_total + fine
    conn.commit()
    cur.close()

    flash(f"""
        ✅ Borrow Recorded Successfully!<br>
        📘 Total Amount: ₹{book_total:.2f}<br>
        💰 Fine: ₹{fine:.2f}<br>
        🧾 Grand Total: ₹{grand_total:.2f}
    """, "success")
    return redirect(url_for('borrow_records'))

from datetime import date
from flask import render_template, request, redirect, url_for, session

@app.route('/borrow_records', methods=['GET', 'POST'])
def borrow_records():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()

    current_date = date.today().strftime('%Y-%m-%d')
    start_date = request.args.get('start_date', current_date)
    end_date = request.args.get('end_date', current_date)
    filter_type = request.args.get('filter', '')
    books = []

    # 🔵 DATE RANGE FILTER (POST)
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        filter_type = 'date'

        cur.execute("""
            SELECT b.borrow_id, m.name, m.phone, m.email,
                   bk.book_name, bk.author,
                   b.borrow_date, b.return_date, b.status, b.fine,
                   DATEDIFF(b.return_date, b.borrow_date) AS duration,
                   DATEDIFF(CURDATE(), b.return_date) AS overdue_days,
                   b.total_amount
            FROM borrowers AS b
            INNER JOIN member_records AS m ON b.member_id = m.member_id
            INNER JOIN books AS bk ON b.book_id = bk.book_id
            WHERE DATE(b.borrow_date) BETWEEN %s AND %s
            ORDER BY b.borrow_date DESC
        """, (start_date, end_date))

    else:
        # 🔵 INITIAL LOAD → SHOW ALL RECORDS
        if filter_type == 'overdue':
            cur.execute("""
                SELECT b.borrow_id, m.name, m.phone, m.email,
                       bk.book_name, bk.author,
                       b.borrow_date, b.return_date, b.status, b.fine,
                       DATEDIFF(b.return_date, b.borrow_date) AS duration,
                       DATEDIFF(CURDATE(), b.return_date) AS overdue_days,
                       b.total_amount
                FROM borrowers AS b
                INNER JOIN member_records AS m ON b.member_id = m.member_id
                INNER JOIN books AS bk ON b.book_id = bk.book_id
                WHERE b.status != 'Returned'
                  AND CURDATE() > b.return_date
                ORDER BY b.return_date ASC
            """)

        else:
            # 🔵 DEFAULT & "ALL" → SAME BEHAVIOR
            cur.execute("""
                SELECT b.borrow_id, m.name, m.phone, m.email,
                       bk.book_name, bk.author,
                       b.borrow_date, b.return_date, b.status, b.fine,
                       DATEDIFF(b.return_date, b.borrow_date) AS duration,
                       DATEDIFF(CURDATE(), b.return_date) AS overdue_days,
                       b.total_amount
                FROM borrowers AS b
                INNER JOIN member_records AS m ON b.member_id = m.member_id
                INNER JOIN books AS bk ON b.book_id = bk.book_id
                ORDER BY b.borrow_date DESC
            """)

    books = cur.fetchall()
    cur.close()

    return render_template(
        'borrow_records.html',
        books=books,
        current_date=current_date,
        start_date=start_date,
        end_date=end_date,
        filter_type=filter_type
    )


@app.route('/mark_return/<int:borrow_id>', methods=['POST'])
def mark_return(borrow_id):
    if 'admin_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403

    conn = get_db_connection()
    cur = conn.cursor()

    # 🔹 Fetch borrow record details
    cur.execute("""
        SELECT return_date, status FROM borrowers WHERE borrow_id = %s
    """, (borrow_id,))
    borrow_record = cur.fetchone()

    if not borrow_record:
        cur.close()
        return jsonify({'success': False, 'error': 'Borrow record not found'})

    if borrow_record['status'] == 'Returned':
        cur.close()
        return jsonify({'success': False, 'error': 'Already returned'})

    # 🔹 Calculate fine (₹10 per day overdue)
    today = date.today()
    return_date = borrow_record['return_date']
    fine = 0

    if today > return_date:
        overdue_days = (today - return_date).days
        fine = overdue_days * 10  # Rs.10 per day

    # 🔹 Update status and fine in DB
    cur.execute("""
        UPDATE borrowers
        SET status = 'Returned', fine = %s
        WHERE borrow_id = %s
    """, (fine, borrow_id))

    conn.commit()
    cur.close()

    return jsonify({'success': True, 'fine': fine})

if __name__ == '__main__':
    app.run(debug=True)








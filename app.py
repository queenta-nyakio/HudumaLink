import os
import secrets

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_file, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import get_db_connection, initialize_database

app = Flask(__name__)

# Limit the total size of one registration request to 15 MB.
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

# Keep verification documents outside the public static directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRIVATE_DOCUMENTS_DIR = os.path.join(
    app.instance_path, "provider_documents"
)
os.makedirs(PRIVATE_DOCUMENTS_DIR, exist_ok=True)

# Allowed document formats.
ALLOWED_ID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
ALLOWED_PROOF_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx"
}

def validate_upload(uploaded_file, allowed_extensions):
    """Check that a file was selected and its extension is allowed."""
    if uploaded_file is None or not uploaded_file.filename:
        return False

    original_name = secure_filename(uploaded_file.filename)

    if not original_name:
        return False

    extension = os.path.splitext(original_name)[1].lower()

    return extension in allowed_extensions


def save_private_upload(uploaded_file):
    """Save a document privately under a randomly generated filename."""
    original_name = secure_filename(uploaded_file.filename)
    extension = os.path.splitext(original_name)[1].lower()

    # Generate a new filename instead of trusting the uploaded filename.
    stored_filename = secrets.token_hex(16) + extension

    file_path = os.path.join(
        PRIVATE_DOCUMENTS_DIR,
        stored_filename
    )

    uploaded_file.save(file_path)

    # Return the stored filename and safe original filename.
    return stored_filename, original_name


def delete_private_uploads(filenames):
    """Remove uploaded files if a registration operation fails."""
    for filename in filenames:
        if not filename:
            continue

        # Only allow a plain filename, not a supplied directory path.
        if os.path.basename(filename) != filename:
            continue

        file_path = os.path.join(
            PRIVATE_DOCUMENTS_DIR,
            filename
        )

        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except OSError:
                app.logger.exception(
                    "Could not remove a temporary provider document."
                )

# =========================================================

# APPLICATION CONFIGURATION

# =========================================================

app.secret_key = "hudumalink-development-secret-key"

# =========================================================

# INITIALIZE DATABASE

# =========================================================

initialize_database()

# =========================================================

# SERVICE REQUEST DATABASE TABLE

# =========================================================

def initialize_service_requests_table():

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""

        CREATE TABLE IF NOT EXISTS service_requests (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            provider_id INTEGER NOT NULL,

            service_id INTEGER NOT NULL,

            request_description TEXT NOT NULL,

            preferred_date TEXT,

            status TEXT NOT NULL DEFAULT 'pending',

            request_status TEXT DEFAULT 'pending',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            requested_at TEXT DEFAULT CURRENT_TIMESTAMP,

            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            completed_at TEXT

        )

    """)

    existing_columns = {

        row["name"]

        for row in cursor.execute(

            "PRAGMA table_info(service_requests)"

        ).fetchall()

    }

    migrations = {

        "request_description": "TEXT",

        "preferred_date": "TEXT",

        "status": "TEXT DEFAULT 'pending'",

        "request_status": "TEXT DEFAULT 'pending'",

        "created_at": "TEXT",

        "requested_at": "TEXT",

        "updated_at": "TEXT",

        "completed_at": "TEXT"

    }

    for column, definition in migrations.items():

        if column not in existing_columns:

            cursor.execute(

                f"ALTER TABLE service_requests "

                f"ADD COLUMN {column} {definition}"

            )

    cursor.execute("""

        UPDATE service_requests

        SET status = COALESCE(

            NULLIF(status, ''),

            NULLIF(request_status, ''),

            'pending'

        )

    """)

    cursor.execute("""

        UPDATE service_requests

        SET request_status = COALESCE(

            NULLIF(request_status, ''),

            NULLIF(status, ''),

            'pending'

        )

    """)

    cursor.execute("""

        UPDATE service_requests

        SET created_at = COALESCE(created_at, requested_at, CURRENT_TIMESTAMP)

    """)

    cursor.execute("""

        UPDATE service_requests

        SET requested_at = COALESCE(requested_at, created_at, CURRENT_TIMESTAMP)

    """)

    cursor.execute("""

        UPDATE service_requests

        SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)

    """)

    connection.commit()

    connection.close()

initialize_service_requests_table()

# =========================================================

# HOME PAGE

# =========================================================

@app.route("/")

def home():

    return render_template("home.html")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    role = request.form.get("role", "")

    # Validate common fields.
    if not full_name or not email or not phone or not password:
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("register"))

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("register"))

    if role not in ["user", "provider"]:
        flash("Please select a valid account type.", "error")
        return redirect(url_for("register"))

    # Provider-only information.
    location = ""
    description = ""
    id_front = None
    id_back = None
    proof_document = None

    if role == "provider":
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()

        if not location:
            flash(
                "Service providers must provide their location.",
                "error"
            )
            return redirect(url_for("register"))

        id_front = request.files.get("id_front")
        id_back = request.files.get("id_back")
        proof_document = request.files.get("proof_document")

        if not validate_upload(id_front, ALLOWED_ID_EXTENSIONS):
            flash("Please upload a valid ID front document.", "error")
            return redirect(url_for("register"))

        if not validate_upload(id_back, ALLOWED_ID_EXTENSIONS):
            flash("Please upload a valid ID back document.", "error")
            return redirect(url_for("register"))

        if not validate_upload(
            proof_document, ALLOWED_PROOF_EXTENSIONS
        ):
            flash("Please upload valid proof of service.", "error")
            return redirect(url_for("register"))

    hashed_password = generate_password_hash(password)
    connection = get_db_connection()
    cursor = connection.cursor()

    saved_files = []
    old_files_to_delete = []
    is_resubmission = False

    try:
        if role == "user":
            cursor.execute("""
                INSERT INTO users (
                    full_name, email, phone, password, role
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                full_name,
                email,
                phone,
                hashed_password,
                "user"
            ))

        else:
            # Check whether this email already belongs to a provider.
            cursor.execute("""
                SELECT id, verification_status
                FROM service_providers
                WHERE email = ?
            """, (email,))

            existing_provider = cursor.fetchone()

            if existing_provider:
                provider_id = existing_provider["id"]
                current_status = existing_provider[
                    "verification_status"
                ]

                if current_status == "approved":
                    flash(
                        "This provider account is already approved. "
                        "Please log in instead.",
                        "error"
                    )
                    return redirect(url_for("register"))

                if current_status == "pending":
                    flash(
                        "Your provider application is already pending. "
                        "Please wait for the administrator's decision.",
                        "error"
                    )
                    return redirect(url_for("register"))

                if current_status == "revoked":
                    flash(
                        "This provider account has been revoked. "
                        "Please contact the administrator.",
                        "error"
                    )
                    return redirect(url_for("register"))

                if current_status != "rejected":
                    flash(
                        "An account already exists with this email. "
                        "Please contact the administrator.",
                        "error"
                    )
                    return redirect(url_for("register"))

                # Only rejected providers may resubmit using this email.
                is_resubmission = True

            # Prevent a phone number from being assigned to a
            # different provider account.
            excluded_id = (
                existing_provider["id"]
                if existing_provider else -1
            )

            cursor.execute("""
                SELECT id
                FROM service_providers
                WHERE phone = ? AND id != ?
            """, (phone, excluded_id))

            if cursor.fetchone():
                flash(
                    "This phone number belongs to another provider "
                    "account. Please use your own registered number.",
                    "error"
                )
                return redirect(url_for("register"))

            # Keep a copy of the previous document filenames so
            # they can be removed after a successful resubmission.
            if is_resubmission:
                cursor.execute("""
                    SELECT id_front_path, id_back_path, proof_path
                    FROM provider_documents
                    WHERE provider_id = ?
                """, (provider_id,))

                old_documents = cursor.fetchone()

                if old_documents:
                    old_files_to_delete = [
                        old_documents["id_front_path"],
                        old_documents["id_back_path"],
                        old_documents["proof_path"]
                    ]

                # Update the existing rejected provider instead
                # of inserting a duplicate account.
                cursor.execute("""
                    UPDATE service_providers
                    SET full_name = ?,
                        phone = ?,
                        password = ?,
                        location = ?,
                        description = ?,
                        verification_status = 'pending'
                    WHERE id = ?
                """, (
                    full_name,
                    phone,
                    hashed_password,
                    location,
                    description,
                    provider_id
                ))

            else:
                # Create a new provider account.
                cursor.execute("""
                    INSERT INTO service_providers (
                        full_name,
                        email,
                        phone,
                        password,
                        location,
                        description,
                        verification_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    full_name,
                    email,
                    phone,
                    hashed_password,
                    location,
                    description,
                    "pending"
                ))

                provider_id = cursor.lastrowid

            # Save the newly submitted documents privately.
            front_filename, _ = save_private_upload(id_front)
            saved_files.append(front_filename)

            back_filename, _ = save_private_upload(id_back)
            saved_files.append(back_filename)

            proof_filename, proof_original_name = (
                save_private_upload(proof_document)
            )
            saved_files.append(proof_filename)

            # Replace the old document record on resubmission.
            if is_resubmission and old_documents:
                cursor.execute("""
                    UPDATE provider_documents
                    SET id_front_path = ?,
                        id_back_path = ?,
                        proof_path = ?,
                        proof_original_name = ?,
                        review_status = 'pending',
                        admin_notes = NULL,
                        uploaded_at = CURRENT_TIMESTAMP,
                        reviewed_at = NULL
                    WHERE provider_id = ?
                """, (
                    front_filename,
                    back_filename,
                    proof_filename,
                    proof_original_name,
                    provider_id
                ))

            else:
                cursor.execute("""
                    INSERT INTO provider_documents (
                        provider_id,
                        id_front_path,
                        id_back_path,
                        proof_path,
                        proof_original_name,
                        review_status
                    )
                    VALUES (?, ?, ?, ?, ?, 'pending')
                    ON CONFLICT(provider_id) DO UPDATE SET
                        id_front_path = excluded.id_front_path,
                        id_back_path = excluded.id_back_path,
                        proof_path = excluded.proof_path,
                        proof_original_name =
                            excluded.proof_original_name,
                        review_status = 'pending',
                        admin_notes = NULL,
                        uploaded_at = CURRENT_TIMESTAMP,
                        reviewed_at = NULL
                """, (
                    provider_id,
                    front_filename,
                    back_filename,
                    proof_filename,
                    proof_original_name
                ))

        connection.commit()

        # Delete the old documents only after the new submission
        # has been successfully committed.
        if is_resubmission:
            delete_private_uploads(old_files_to_delete)

            flash(
                "Your application has been resubmitted successfully. "
                "Your new documents are awaiting administrator review.",
                "success"
            )
        elif role == "provider":
            flash(
                "Registration successful. Your documents have been "
                "submitted for administrator review. Your account "
                "is pending approval.",
                "success"
            )
        else:
            flash(
                "Registration successful. You can now log in.",
                "success"
            )

    except Exception:
        connection.rollback()

        # Remove newly saved files if the database operation fails.
        delete_private_uploads(saved_files)

        app.logger.exception("Registration failed.")

        flash(
            "Registration failed. The email or phone number may "
            "already exist, or the submitted information could "
            "not be saved. Please check and try again.",
            "error"
        )

    finally:
        connection.close()

    return redirect(url_for("login"))

# =========================================================

# LOGIN

# =========================================================

@app.route("/login", methods=["GET", "POST"])

def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()

        password = request.form.get("password", "")

        connection = get_db_connection()

        cursor = connection.cursor()

        cursor.execute("""

            SELECT *

            FROM users

            WHERE email = ?

        """, (email,))

        user = cursor.fetchone()

        if user and check_password_hash(user["password"], password):

            session.clear()

            session["user_id"] = user["id"]

            session["full_name"] = user["full_name"]

            session["role"] = user["role"]

            connection.close()

            if user["role"] == "admin":

                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("user_dashboard"))

        cursor.execute("""

            SELECT *

            FROM service_providers

            WHERE email = ?

        """, (email,))

        provider = cursor.fetchone()

        connection.close()

        if provider and check_password_hash(provider["password"], password):

            # Only providers whose current status is approved may log in.
            status = provider["verification_status"]

            if status != "approved":
                if status == "pending":
                    message = (
                        "Your provider account is waiting "
                        "for administrator approval."
                    )
                elif status == "rejected":
                    message = (
                        "Your provider application was rejected "
                        "by the administrator."
                    )
                elif status == "revoked":
                    message = (
                        "Your provider approval has been revoked. "
                        "Please contact the administrator."
                    )
                else:
                    message = (
                        "Your provider account is not approved. "
                        "Please contact the administrator."
                    )

                flash(message, "error")
                return redirect(url_for("login"))

            session.clear()

            session["provider_id"] = provider["id"]

            session["full_name"] = provider["full_name"]

            session["role"] = "provider"

            return redirect(url_for("provider_dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")

# =========================================================

# USER DASHBOARD

# =========================================================

@app.route("/user/dashboard")

def user_dashboard():

    if session.get("role") != "user":

        return redirect(url_for("login"))

    return render_template(

        "user_dashboard.html",

        name=session.get("full_name")

    )

# =========================================================

# FIND SERVICES - APPROVED PROVIDERS DIRECTORY

# =========================================================

@app.route("/find-services")

def find_services():

    if session.get("role") != "user":

        return redirect(url_for("login"))

    search_query = request.args.get("q", "").strip()

    search_pattern = f"%{search_query}%"

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""

        SELECT

            sp.id,

            sp.full_name,

            sp.location,

            sp.description,

            (

                SELECT GROUP_CONCAT(s.service_name, ', ')

                FROM services AS s

                WHERE s.provider_id = sp.id

            ) AS services,

            (

                SELECT AVG(r.rating)

                FROM reviews AS r

                WHERE r.provider_id = sp.id

            ) AS average_rating,

            (

                SELECT COUNT(*)

                FROM reviews AS r

                WHERE r.provider_id = sp.id

            ) AS review_count

        FROM service_providers AS sp

        WHERE sp.verification_status = 'approved'

        AND (

            sp.full_name LIKE ?

            OR sp.location LIKE ?

            OR EXISTS (

                SELECT 1

                FROM services AS s

                WHERE s.provider_id = sp.id

                AND s.service_name LIKE ?

            )

        )

        ORDER BY

            CASE WHEN average_rating IS NULL THEN 1 ELSE 0 END,

            average_rating DESC,

            sp.full_name ASC

    """, (

        search_pattern,

        search_pattern,

        search_pattern

    ))

    providers = cursor.fetchall()

    connection.close()

    return render_template(

        "find_services.html",

        name=session.get("full_name"),

        providers=providers,

        search_query=search_query

    )

# =========================================================

# REQUEST A SERVICE

# =========================================================

@app.route("/service/<int:service_id>/request", methods=["GET", "POST"])

def request_service(service_id):

    if session.get("role") != "user":

        return redirect(url_for("login"))

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""

        SELECT

            s.id,

            s.service_name,

            s.description AS service_description,

            s.price,

            s.availability,

            sp.id AS provider_id,

            sp.full_name AS provider_name,

            sp.location

        FROM services AS s

        JOIN service_providers AS sp ON s.provider_id = sp.id

        WHERE s.id = ?

          AND sp.verification_status = 'approved'

    """, (service_id,))

    service = cursor.fetchone()

    connection.close()

    if service is None:

        flash("This service is unavailable.", "error")

        return redirect(url_for("find_services"))

    if request.method == "POST":

        description = request.form.get(

            "request_description", ""

        ).strip()

        preferred_date = request.form.get(

            "preferred_date", ""

        ).strip()

        if not description:

            flash("Please describe the service you need.", "error")

            return render_template("request_service.html", service=service)

        connection = get_db_connection()

        cursor = connection.cursor()

        try:

            cursor.execute("""

                INSERT INTO service_requests (

                    user_id,

                    provider_id,

                    service_id,

                    request_description,

                    preferred_date,

                    status,

                    request_status

                )

                VALUES (?, ?, ?, ?, ?, 'pending', 'pending')

            """, (

                session.get("user_id"),

                service["provider_id"],

                service["id"],

                description,

                preferred_date or None

            ))

            connection.commit()

        except Exception:

            connection.rollback()

            connection.close()

            flash(

                "Your request could not be saved. Please try again.",

                "error"

            )

            return redirect(

                url_for("request_service", service_id=service_id)

            )

        connection.close()

        flash(

            "Your service request has been submitted successfully.",

            "success"

        )

        return redirect(url_for("my_requests"))

    return render_template("request_service.html", service=service)

# =========================================================

# CUSTOMER SERVICE REQUESTS

# =========================================================

@app.route("/my-requests")

def my_requests():

    if session.get("role") != "user":

        return redirect(url_for("login"))

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""

        SELECT

            sr.id,

            sr.request_description,

            sr.preferred_date,

            COALESCE(

                NULLIF(sr.status, ''),

                sr.request_status,

                'pending'

            ) AS status,

            COALESCE(sr.created_at, sr.requested_at) AS created_at,

            s.service_name,

            sp.full_name AS provider_name,

            sp.location,

            r.id AS review_id

        FROM service_requests AS sr

        JOIN services AS s ON sr.service_id = s.id

        JOIN service_providers AS sp ON sr.provider_id = sp.id

        LEFT JOIN reviews AS r ON r.request_id = sr.id

        WHERE sr.user_id = ?

        ORDER BY sr.id DESC

    """, (session.get("user_id"),))

    requests_list = cursor.fetchall()

    connection.close()

    return render_template(

        "my_requests.html",

        name=session.get("full_name"),

        requests=requests_list

    )

# =========================================================

# CUSTOMER REVIEWS

# =========================================================

@app.route("/request/<int:request_id>/review", methods=["GET", "POST"])

def review_request(request_id):

    if session.get("role") != "user":

        return redirect(url_for("login"))

    user_id = session.get("user_id")

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""

        SELECT

            sr.id,

            sr.user_id,

            sr.provider_id,

            COALESCE(

                NULLIF(sr.status, ''),

                sr.request_status,

                'pending'

            ) AS status,

            s.service_name,

            sp.full_name AS provider_name

        FROM service_requests AS sr

        JOIN services AS s ON sr.service_id = s.id

        JOIN service_providers AS sp ON sr.provider_id = sp.id

        WHERE sr.id = ?

          AND sr.user_id = ?

    """, (request_id, user_id))

    service_request = cursor.fetchone()

    if service_request is None:

        connection.close()

        flash("Service request not found.", "error")

        return redirect(url_for("my_requests"))

    if (service_request["status"] or "").lower() != "completed":

        connection.close()

        flash("You can only review a completed service.", "error")

        return redirect(url_for("my_requests"))

    cursor.execute("""

        SELECT id

        FROM reviews

        WHERE request_id = ?

    """, (request_id,))

    if cursor.fetchone():

        connection.close()

        flash(

            "You have already reviewed this service request.",

            "error"

        )

        return redirect(url_for("my_requests"))

    if request.method == "POST":

        rating_value = request.form.get("rating", "").strip()

        comment = request.form.get("comment", "").strip()

        try:

            rating = int(rating_value)

        except (TypeError, ValueError):

            rating = 0

        if rating < 1 or rating > 5:

            connection.close()

            flash(

                "Please select a rating from 1 to 5 stars.",

                "error"

            )

            return redirect(

                url_for("review_request", request_id=request_id)

            )

        if len(comment) > 1000:

            connection.close()

            flash(

                "Your review must not exceed 1000 characters.",

                "error"

            )

            return redirect(

                url_for("review_request", request_id=request_id)

            )

        try:

            cursor.execute("""

                INSERT INTO reviews (

                    user_id,

                    provider_id,

                    request_id,

                    rating,

                    comment

                )

                VALUES (?, ?, ?, ?, ?)

            """, (

                user_id,

                service_request["provider_id"],

                request_id,

                rating,

                comment or None

            ))

            connection.commit()

        except Exception:

            connection.rollback()

            connection.close()

            flash(

                "The review could not be saved. It may already exist.",

                "error"

            )

            return redirect(url_for("my_requests"))

        connection.close()

        flash("Thank you! Your review has been submitted.", "success")

        return redirect(url_for("my_requests"))

    connection.close()

    return render_template(

        "review_request.html",

        service_request=service_request

    )

# =========================================================

# PROVIDER DASHBOARD

# =========================================================

@app.route("/provider/dashboard")

def provider_dashboard():

    if session.get("role") != "provider":

        return redirect(url_for("login"))

    return render_template(

        "provider_dashboard.html",

        name=session.get("full_name")

    )

# =========================================================

# VIEW SERVICE PROVIDER PROFILE

# =========================================================

@app.route("/provider/profile/<int:provider_id>")

def provider_profile(provider_id):

    if session.get("role") != "user":

        return redirect(url_for("login"))

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""

        SELECT

            sp.id,

            sp.full_name,

            sp.location,

            sp.description,

            sp.verification_status,

            (

                SELECT AVG(r.rating)

                FROM reviews AS r

                WHERE r.provider_id = sp.id

            ) AS average_rating,

            (

                SELECT COUNT(*)

                FROM reviews AS r

                WHERE r.provider_id = sp.id

            ) AS review_count

        FROM service_providers AS sp

        WHERE sp.id = ?

          AND sp.verification_status = 'approved'

    """, (provider_id,))

    provider = cursor.fetchone()

    if provider is None:

        connection.close()

        flash("Provider not found or not approved.", "error")

        return redirect(url_for("find_services"))

    cursor.execute("""

        SELECT id, service_name, description, price, availability

        FROM services

        WHERE provider_id = ?

        ORDER BY service_name ASC

    """, (provider_id,))

    services = cursor.fetchall()

    connection.close()

    return render_template(

        "provider_profile.html",

        name=session.get("full_name"),

        provider=provider,

        services=services

    )

# =========================================================

# ADMIN DASHBOARD

# =========================================================

@app.route("/admin/dashboard")

def admin_dashboard():

    if session.get("role") != "admin":

        return redirect(url_for("login"))

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""

        SELECT *

        FROM service_providers

        ORDER BY created_at DESC

    """)

    providers = cursor.fetchall()

    connection.close()

    return render_template(

        "admin_dashboard.html",

        name=session.get("full_name"),

        providers=providers

    )


# =========================================================
# APPROVE SERVICE PROVIDER
# =========================================================

@app.route(
    "/admin/provider/<int:provider_id>/approve",
    methods=["POST"]
)
def approve_provider(provider_id):
    if session.get("role") != "admin":
        flash("Administrator access is required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT id, verification_status
            FROM service_providers
            WHERE id = ?
        """, (provider_id,))
        provider = cursor.fetchone()

        if provider is None:
            flash("Service provider not found.", "error")
            return redirect(url_for("admin_dashboard"))

        if provider["verification_status"] != "pending":
            flash(
                "Only providers with pending applications can be approved. "
                "Rejected providers must resubmit their documents first.",
                "error"
            )
            return redirect(url_for("admin_dashboard"))

        cursor.execute("""
            SELECT id_front_path, id_back_path, proof_path
            FROM provider_documents
            WHERE provider_id = ?
        """, (provider_id,))
        documents = cursor.fetchone()

        if documents is None:
            flash(
                "Approval denied: this provider has no submitted documents.",
                "error"
            )
            return redirect(url_for("admin_dashboard"))

        filenames = [
            documents["id_front_path"],
            documents["id_back_path"],
            documents["proof_path"]
        ]

        # Verify that all three files exist in private storage.
        for filename in filenames:
            if (
                not filename
                or os.path.basename(filename) != filename
                or not os.path.isfile(
                    os.path.join(PRIVATE_DOCUMENTS_DIR, filename)
                )
            ):
                flash(
                    "Approval denied: one or more documents are missing. "
                    "Ask the provider to resubmit their documents.",
                    "error"
                )
                return redirect(url_for("admin_dashboard"))

        cursor.execute("""
            UPDATE service_providers
            SET verification_status = 'approved',
                verified_by = ?
            WHERE id = ? AND verification_status = 'pending'
        """, (session.get("user_id"), provider_id))

        cursor.execute("""
            UPDATE provider_documents
            SET review_status = 'approved',
                reviewed_at = CURRENT_TIMESTAMP,
                admin_notes = NULL
            WHERE provider_id = ?
        """, (provider_id,))

        connection.commit()
        flash("Provider documents verified and provider approved.", "success")

    except Exception:
        connection.rollback()
        app.logger.exception("Provider approval failed.")
        flash("The provider could not be approved. Please try again.", "error")

    finally:
        connection.close()

    return redirect(url_for("admin_dashboard"))


# =========================================================
# REJECT SERVICE PROVIDER
# =========================================================

@app.route(
    "/admin/provider/<int:provider_id>/reject",
    methods=["POST"]
)
def reject_provider(provider_id):
    if session.get("role") != "admin":
        flash("Administrator access is required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT id, verification_status
            FROM service_providers
            WHERE id = ?
        """, (provider_id,))
        provider = cursor.fetchone()

        if provider is None:
            flash("Service provider not found.", "error")
            return redirect(url_for("admin_dashboard"))

        if provider["verification_status"] != "pending":
            flash(
                "Only providers with pending applications can be rejected.",
                "error"
            )
            return redirect(url_for("admin_dashboard"))

        cursor.execute("""
            UPDATE service_providers
            SET verification_status = 'rejected',
                verified_by = ?
            WHERE id = ?
        """, (session.get("user_id"), provider_id))

        cursor.execute("""
            UPDATE provider_documents
            SET review_status = 'rejected',
                reviewed_at = CURRENT_TIMESTAMP
            WHERE provider_id = ?
        """, (provider_id,))

        connection.commit()
        flash(
            "Provider application rejected. The provider may resubmit "
            "with updated documents.",
            "success"
        )

    except Exception:
        connection.rollback()
        app.logger.exception("Provider rejection failed.")
        flash("The provider could not be rejected. Please try again.", "error")

    finally:
        connection.close()

    return redirect(url_for("admin_dashboard"))

# =========================================================
# ADMIN: REVIEW PROVIDER DOCUMENTS
# =========================================================

@app.route("/admin/provider/<int:provider_id>/documents")
def admin_provider_documents(provider_id):
    if session.get("role") != "admin":
        flash("Administrator access is required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            sp.id,
            sp.full_name,
            sp.email,
            sp.phone,
            sp.location,
            sp.description,
            sp.verification_status,
            pd.id_front_path,
            pd.id_back_path,
            pd.proof_path,
            pd.proof_original_name,
            pd.review_status,
            pd.admin_notes,
            pd.uploaded_at,
            pd.reviewed_at
        FROM service_providers AS sp
        LEFT JOIN provider_documents AS pd
            ON pd.provider_id = sp.id
        WHERE sp.id = ?
    """, (provider_id,))

    provider = cursor.fetchone()
    connection.close()

    if provider is None:
        flash("Service provider not found.", "error")
        return redirect(url_for("admin_dashboard"))

    if not all([
        provider["id_front_path"],
        provider["id_back_path"],
        provider["proof_path"]
    ]):
        flash(
            "One or more documents have not been submitted.",
            "error"
        )

    return render_template(
        "admin_provider_documents.html",
        name=session.get("full_name"),
        provider=provider
    )


# =========================================================
# ADMIN: SECURELY OPEN ONE PROVIDER DOCUMENT
# =========================================================

@app.route(
    "/admin/provider/<int:provider_id>/documents/<document_type>"
)
def admin_provider_document_file(provider_id, document_type):
    if session.get("role") != "admin":
        flash("Administrator access is required.", "error")
        return redirect(url_for("login"))

    # Only these three document types can be requested.
    document_columns = {
        "id-front": "id_front_path",
        "id-back": "id_back_path",
        "proof": "proof_path"
    }

    column = document_columns.get(document_type)

    if column is None:
        abort(404)

    connection = get_db_connection()
    cursor = connection.cursor()

    # The filename comes from this provider's database record,
    # never from a path supplied by the browser.
    cursor.execute(f"""
        SELECT {column}
        FROM provider_documents
        WHERE provider_id = ?
    """, (provider_id,))

    document = cursor.fetchone()
    connection.close()

    if document is None:
        abort(404)

    stored_filename = document[column]

    if (
        not stored_filename
        or os.path.basename(stored_filename) != stored_filename
    ):
        abort(404)

    file_path = os.path.realpath(
        os.path.join(PRIVATE_DOCUMENTS_DIR, stored_filename)
    )
    private_directory = os.path.realpath(PRIVATE_DOCUMENTS_DIR)

    # Prevent access to paths outside the private document directory.
    if os.path.commonpath([private_directory, file_path]) != private_directory:
        abort(404)

    if not os.path.isfile(file_path):
        abort(404)

    extension = os.path.splitext(stored_filename)[1].lower()

    # PDFs and images can open in the browser. Word documents download.
    download_file = extension in {".doc", ".docx"}

    return send_file(
        file_path,
        as_attachment=download_file,
        download_name=stored_filename
    )


# =========================================================
# REVOKE PROVIDER APPROVAL
# =========================================================

@app.route(
    "/admin/provider/<int:provider_id>/revoke",
    methods=["POST"]
)
def revoke_provider(provider_id):
    if session.get("role") != "admin":
        flash("Administrator access is required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, verification_status
        FROM service_providers
        WHERE id = ?
    """, (provider_id,))

    provider = cursor.fetchone()

    if provider is None:
        connection.close()
        flash("Service provider not found.", "error")
        return redirect(url_for("admin_dashboard"))

    if provider["verification_status"] != "approved":
        connection.close()
        flash(
            "Only an approved provider can have approval revoked.",
            "error"
        )
        return redirect(url_for("admin_dashboard"))

    try:
        cursor.execute("""
            UPDATE service_providers
            SET verification_status = 'revoked',
                verified_by = ?
            WHERE id = ?
        """, (session.get("user_id"), provider_id))
        connection.commit()
    except Exception:
        connection.rollback()
        connection.close()
        flash("Unable to revoke provider approval.", "error")
        return redirect(url_for("admin_dashboard"))

    connection.close()
    flash("Provider approval revoked successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/provider/services")

def provider_services():

    if session.get("role") != "provider":

        return redirect(url_for("login"))

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""

        SELECT *

        FROM services

        WHERE provider_id = ?

        ORDER BY created_at DESC

    """, (session.get("provider_id"),))

    services = cursor.fetchall()

    connection.close()

    return render_template(

        "provider_services.html",

        name=session.get("full_name"),

        services=services

    )

# =========================================================
# ADMIN: VIEW REGISTERED USERS
# =========================================================

@app.route("/admin/users")
def admin_users():

    if session.get("role") != "admin":
        flash("Administrator access is required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, full_name, email, phone, account_status, created_at
        FROM users
        WHERE role = 'user'
        ORDER BY created_at DESC
    """)

    users = cursor.fetchall()
    connection.close()

    return render_template(
        "admin_users.html",
        name=session.get("full_name"),
        users=users
    )


# =========================================================
# ADMIN: VIEW ALL LISTED SERVICES
# =========================================================

@app.route("/admin/services")
def admin_services():

    if session.get("role") != "admin":
        flash("Administrator access is required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            s.id,
            s.service_name,
            s.description,
            s.price,
            s.availability,
            s.pricing_type,
            s.created_at,
            sp.full_name AS provider_name,
            sp.location AS provider_location,
            sp.verification_status
        FROM services AS s
        JOIN service_providers AS sp
            ON s.provider_id = sp.id
        ORDER BY s.created_at DESC
    """)

    services = cursor.fetchall()
    connection.close()

    return render_template(
        "admin_services.html",
        name=session.get("full_name"),
        services=services
    )


# =========================================================
# ADMIN: VIEW ALL SERVICE REQUESTS
# =========================================================

@app.route("/admin/requests")
def admin_requests():

    if session.get("role") != "admin":
        flash("Administrator access is required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            sr.id,
            sr.request_description,
            sr.preferred_date,
            COALESCE(
                NULLIF(sr.status, ''),
                NULLIF(sr.request_status, ''),
                'pending'
            ) AS status,
            COALESCE(
                sr.created_at,
                sr.requested_at
            ) AS created_at,
            u.full_name AS customer_name,
            sp.full_name AS provider_name,
            s.service_name
        FROM service_requests AS sr
        JOIN users AS u
            ON sr.user_id = u.id
        JOIN service_providers AS sp
            ON sr.provider_id = sp.id
        JOIN services AS s
            ON sr.service_id = s.id
        ORDER BY sr.id DESC
    """)

    requests_list = cursor.fetchall()
    connection.close()

    return render_template(
        "admin_requests.html",
        name=session.get("full_name"),
        requests=requests_list
    )


# =========================================================
# ADMIN: VIEW CUSTOMER REVIEWS AND RATINGS
# =========================================================

@app.route("/admin/reviews")
def admin_reviews():

    if session.get("role") != "admin":
        flash("Administrator access is required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            r.id,
            r.rating,
            r.comment,
            r.created_at,
            u.full_name AS customer_name,
            sp.full_name AS provider_name,
            s.service_name,
            sr.id AS request_id
        FROM reviews AS r
        JOIN users AS u
            ON r.user_id = u.id
        JOIN service_providers AS sp
            ON r.provider_id = sp.id
        JOIN service_requests AS sr
            ON r.request_id = sr.id
        JOIN services AS s
            ON sr.service_id = s.id
        ORDER BY r.created_at DESC
    """)

    reviews = cursor.fetchall()
    connection.close()

    return render_template(
        "admin_reviews.html",
        name=session.get("full_name"),
        reviews=reviews
    )


# =========================================================

# ADD SERVICE

# =========================================================

@app.route("/provider/services/add", methods=["GET", "POST"])

def add_service():

    if session.get("role") != "provider":

        return redirect(url_for("login"))

    if request.method == "POST":

        service_name = request.form.get(

            "service_name", ""

        ).strip()

        description = request.form.get(

            "description", ""

        ).strip()

        pricing_type = request.form.get(

            "pricing_type", "fixed"

        ).strip()

        price_input = request.form.get("price", "").strip()

        pricing_notes = request.form.get(

            "pricing_notes", ""

        ).strip()

        availability = request.form.get(

            "availability", "Available"

        ).strip()

        allowed_pricing_types = {

            "fixed",

            "starting_from",

            "hourly",

            "quotation"

        }

        if not service_name:

            flash("Please enter the service name.", "error")

            return redirect(url_for("add_service"))

        if pricing_type not in allowed_pricing_types:

            flash("Please select a valid pricing method.", "error")

            return redirect(url_for("add_service"))

        if availability not in {"Available", "Unavailable"}:

            flash("Please select valid availability.", "error")

            return redirect(url_for("add_service"))

        price = None

        if pricing_type != "quotation":

            if not price_input:

                flash(

                    "Enter a price for the selected pricing method.",

                    "error"

                )

                return redirect(url_for("add_service"))

            try:

                price = float(price_input)

                if price <= 0:

                    raise ValueError

            except ValueError:

                flash(

                    "Price must be a number greater than zero.",

                    "error"

                )

                return redirect(url_for("add_service"))

        connection = get_db_connection()

        try:

            connection.execute("""

                INSERT INTO services (

                    provider_id,

                    service_name,

                    description,

                    price,

                    availability,

                    pricing_type,

                    pricing_notes

                )

                VALUES (?, ?, ?, ?, ?, ?, ?)

            """, (

                session.get("provider_id"),

                service_name,

                description,

                price,

                availability,

                pricing_type,

                pricing_notes or None

            ))

            connection.commit()

        except Exception:

            connection.rollback()

            flash("Failed to add service. Please try again.", "error")

            connection.close()

            return redirect(url_for("add_service"))

        connection.close()

        flash("Service added successfully.", "success")

        return redirect(url_for("provider_services"))

    return render_template(

        "add_service.html",

        name=session.get("full_name")

    )

# =========================================================

# EDIT EXISTING SERVICE

# =========================================================

@app.route(

    "/provider/services/<int:service_id>/edit",

    methods=["GET", "POST"]

)

def edit_service(service_id):

    if session.get("role") != "provider":

        return redirect(url_for("login"))

    provider_id = session.get("provider_id")

    connection = get_db_connection()

    cursor = connection.cursor()

    # Confirm that this service belongs to the logged-in provider.

    cursor.execute("""

        SELECT *

        FROM services

        WHERE id = ? AND provider_id = ?

    """, (service_id, provider_id))

    service = cursor.fetchone()

    if service is None:

        connection.close()

        flash("Service not found or you cannot edit it.", "error")

        return redirect(url_for("provider_services"))

    if request.method == "POST":

        service_name = request.form.get(

            "service_name", ""

        ).strip()

        description = request.form.get(

            "description", ""

        ).strip()

        pricing_type = request.form.get(

            "pricing_type", "fixed"

        ).strip()

        price_input = request.form.get(

            "price", ""

        ).strip()

        pricing_notes = request.form.get(

            "pricing_notes", ""

        ).strip()

        availability = request.form.get(

            "availability", "Available"

        ).strip()

        allowed_pricing_types = {

            "fixed",

            "starting_from",

            "hourly",

            "quotation"

        }

        if not service_name:

            connection.close()

            flash("Please enter the service name.", "error")

            return redirect(

                url_for("edit_service", service_id=service_id)

            )

        if pricing_type not in allowed_pricing_types:

            connection.close()

            flash("Please select a valid pricing method.", "error")

            return redirect(

                url_for("edit_service", service_id=service_id)

            )

        if availability not in {"Available", "Unavailable"}:

            connection.close()

            flash("Please select a valid availability option.", "error")

            return redirect(

                url_for("edit_service", service_id=service_id)

            )

        # Quotation-only services do not require a price in advance.

        price = None

        if pricing_type != "quotation":

            if not price_input:

                connection.close()

                flash(

                    "Please enter a price for this pricing method.",

                    "error"

                )

                return redirect(

                    url_for("edit_service", service_id=service_id)

                )

            try:

                price = float(price_input)

                if price <= 0:

                    raise ValueError

            except ValueError:

                connection.close()

                flash(

                    "Price must be a number greater than zero.",

                    "error"

                )

                return redirect(

                    url_for("edit_service", service_id=service_id)

                )

        try:

            cursor.execute("""

                UPDATE services

                SET service_name = ?,

                    description = ?,

                    price = ?,

                    availability = ?,

                    pricing_type = ?,

                    pricing_notes = ?

                WHERE id = ? AND provider_id = ?

            """, (

                service_name,

                description,

                price,

                availability,

                pricing_type,

                pricing_notes or None,

                service_id,

                provider_id

            ))

            connection.commit()

        except Exception:

            connection.rollback()

            connection.close()

            flash(

                "The service could not be updated. "

                "Check that the database has the pricing columns.",

                "error"

            )

            return redirect(

                url_for("edit_service", service_id=service_id)

            )

        connection.close()

        flash("Service updated successfully.", "success")

        return redirect(url_for("provider_services"))

    connection.close()

    return render_template(

        "edit_service.html",

        service=service,

        name=session.get("full_name")

    )

# =========================================================

# DELETE EXISTING SERVICE

# =========================================================

@app.route(

    "/provider/services/<int:service_id>/delete",

    methods=["POST"]

)

def delete_service(service_id):

    if session.get("role") != "provider":

        return redirect(url_for("login"))

    provider_id = session.get("provider_id")

    connection = get_db_connection()

    cursor = connection.cursor()

    # Verify ownership before attempting deletion.

    cursor.execute("""

        SELECT id, service_name

        FROM services

        WHERE id = ? AND provider_id = ?

    """, (service_id, provider_id))

    service = cursor.fetchone()

    if service is None:

        connection.close()

        flash("Service not found or you cannot delete it.", "error")

        return redirect(url_for("provider_services"))

    # Preserve service request history.

    cursor.execute("""

        SELECT COUNT(*) AS request_count

        FROM service_requests

        WHERE service_id = ?

    """, (service_id,))

    result = cursor.fetchone()

    request_count = result["request_count"]

    if request_count > 0:

        connection.close()

        flash(

            "This service has existing customer requests and cannot "

            "be deleted. Edit it and set availability to Unavailable "

            "if you no longer offer it.",

            "error"

        )

        return redirect(url_for("provider_services"))

    try:

        cursor.execute("""

            DELETE FROM services

            WHERE id = ? AND provider_id = ?

        """, (service_id, provider_id))

        connection.commit()

    except Exception:

        connection.rollback()

        connection.close()

        flash("The service could not be deleted.", "error")

        return redirect(url_for("provider_services"))

    connection.close()

    flash("Service deleted successfully.", "success")

    return redirect(url_for("provider_services"))

# =========================================================

# PROVIDER REQUEST MANAGEMENT

# =========================================================

@app.route("/provider/requests")

def provider_requests():

    if session.get("role") != "provider":

        flash("Please log in as an approved service provider.", "error")

        return redirect(url_for("login"))

    provider_id = session.get("provider_id")

    if not provider_id:

        flash("Provider session not found. Please log in again.", "error")

        return redirect(url_for("login"))

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""

        SELECT

            sr.id,

            sr.user_id,

            sr.service_id,

            sr.request_description,

            sr.preferred_date,

            COALESCE(

                NULLIF(sr.status, ''),

                sr.request_status,

                'pending'

            ) AS status,

            COALESCE(sr.created_at, sr.requested_at) AS request_date,

            s.service_name,

            s.price,

            u.full_name AS customer_name,

            u.phone AS customer_phone

        FROM service_requests AS sr

        JOIN services AS s ON sr.service_id = s.id

        JOIN users AS u ON sr.user_id = u.id

        WHERE sr.provider_id = ?

        ORDER BY COALESCE(sr.created_at, sr.requested_at) DESC

    """, (provider_id,))

    requests_list = cursor.fetchall()

    connection.close()

    return render_template(

        "provider_requests.html",

        requests=requests_list

    )

@app.route(

    "/provider/requests/<int:request_id>/update",

    methods=["POST"]

)

def update_request_status(request_id):

    if session.get("role") != "provider":

        flash("Please log in as an approved service provider.", "error")

        return redirect(url_for("login"))

    provider_id = session.get("provider_id")

    if not provider_id:

        flash("Provider session not found. Please log in again.", "error")

        return redirect(url_for("login"))

    action = request.form.get("action", "").strip().lower()

    allowed_actions = {

        "accept": ("pending", "accepted"),

        "reject": ("pending", "rejected"),

        "complete": ("accepted", "completed")

    }

    if action not in allowed_actions:

        flash("Invalid request action.", "error")

        return redirect(url_for("provider_requests"))

    old_status, new_status = allowed_actions[action]

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""

        SELECT id, status, request_status

        FROM service_requests

        WHERE id = ? AND provider_id = ?

    """, (request_id, provider_id))

    service_request = cursor.fetchone()

    if not service_request:

        connection.close()

        flash(

            "Request not found or you do not have permission to manage it.",

            "error"

        )

        return redirect(url_for("provider_requests"))

    current_status = (

        service_request["status"]

        or service_request["request_status"]

        or "pending"

    ).lower()

    if current_status != old_status:

        connection.close()

        flash(

            f"This request cannot be changed from '{current_status}' "

            f"using that action.",

            "error"

        )

        return redirect(url_for("provider_requests"))

    cursor.execute("""

        UPDATE service_requests

        SET status = ?,

            request_status = ?,

            updated_at = CURRENT_TIMESTAMP,

            completed_at = CASE

                WHEN ? = 'completed' THEN CURRENT_TIMESTAMP

                ELSE completed_at

            END

        WHERE id = ? AND provider_id = ?

    """, (

        new_status,

        new_status,

        new_status,

        request_id,

        provider_id

    ))

    connection.commit()

    connection.close()

    flash(f"Request successfully marked as {new_status}.", "success")

    return redirect(url_for("provider_requests"))

# =========================================================

# LOGOUT

# =========================================================

@app.route("/logout")

def logout():

    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("home"))

# =========================================================

# RUN APPLICATION

# =========================================================

if __name__ == "__main__":

    app.run(debug=True)

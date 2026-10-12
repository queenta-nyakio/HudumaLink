
import sqlite3
import os
from werkzeug.security import generate_password_hash


# Database location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_DIR = os.path.join(BASE_DIR, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "huduma_link.db")


def get_db_connection():
    """Create and return a database connection."""
    os.makedirs(DATABASE_DIR, exist_ok=True)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables():
    """Create the HudumaLink tables if they do not already exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Service providers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT NOT NULL,
            password TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT,
            verification_status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Provider verification documents
    # Documents are stored as private files, not inside the public static folder.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS provider_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL UNIQUE,
            id_front_path TEXT NOT NULL,
            id_back_path TEXT NOT NULL,
            proof_path TEXT NOT NULL,
            proof_original_name TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending',
            admin_notes TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            FOREIGN KEY (provider_id)
                REFERENCES service_providers(id)
                ON DELETE CASCADE
        )
    """)

    # Services offered by providers
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL,
            service_name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            availability TEXT DEFAULT 'Available',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id)
                REFERENCES service_providers(id)
                ON DELETE CASCADE
        )
    """)

    # Service requests made by users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider_id INTEGER NOT NULL,
            service_id INTEGER,
            request_details TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY (provider_id)
                REFERENCES service_providers(id)
                ON DELETE CASCADE,
            FOREIGN KEY (service_id)
                REFERENCES services(id)
                ON DELETE SET NULL
        )
    """)

    # Reviews and ratings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY (provider_id)
                REFERENCES service_providers(id)
                ON DELETE CASCADE
        )
    """)

    # Apply safe additions for databases created by earlier versions.
    # Existing data and tables are preserved.
    _add_column_if_missing(
        cursor, "users", "role",
        "TEXT NOT NULL DEFAULT 'user'"
    )
    _add_column_if_missing(
        cursor, "users", "created_at",
        "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )

    _add_column_if_missing(
        cursor, "service_providers", "location",
        "TEXT NOT NULL DEFAULT ''"
    )
    _add_column_if_missing(
        cursor, "service_providers", "description",
        "TEXT"
    )
    _add_column_if_missing(
        cursor, "service_providers", "verification_status",
        "TEXT NOT NULL DEFAULT 'pending'"
    )
    _add_column_if_missing(
        cursor, "service_providers", "created_at",
        "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )

    _add_column_if_missing(
        cursor, "services", "availability",
        "TEXT DEFAULT 'Available'"
    )
    _add_column_if_missing(
        cursor, "services", "created_at",
        "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )

    _add_column_if_missing(
        cursor, "service_requests", "service_id",
        "INTEGER"
    )
    _add_column_if_missing(
        cursor, "service_requests", "request_details",
        "TEXT"
    )
    _add_column_if_missing(
        cursor, "service_requests", "status",
        "TEXT NOT NULL DEFAULT 'Pending'"
    )
    _add_column_if_missing(
        cursor, "service_requests", "created_at",
        "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )

    _add_column_if_missing(
        cursor, "reviews", "comment",
        "TEXT"
    )
    _add_column_if_missing(
        cursor, "reviews", "created_at",
        "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )

    conn.commit()
    conn.close()


def _add_column_if_missing(cursor, table_name, column_name, definition):
    """Add a column only if it does not already exist."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {
        row[1] for row in cursor.fetchall()
    }

    if column_name not in existing_columns:
        cursor.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} {definition}"
        )


def create_initial_data():
    """Create the default administrator and demo providers if missing."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Default administrator
    admin_email = "admin@hudumalink.com"
    cursor.execute(
        "SELECT id FROM users WHERE email = ?",
        (admin_email,)
    )

    if cursor.fetchone() is None:
        cursor.execute("""
            INSERT INTO users
                (full_name, email, phone, password, role)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "System Administrator",
            admin_email,
            "0700000000",
            generate_password_hash("Admin@123"),
            "admin"
        ))

    # Demo providers
    demo_providers = [
        (
            "John Mwangi",
            "john@example.com",
            "0711111111",
            "Nairobi",
            "Plumbing and pipe repair services"
        ),
        (
            "Mary Wanjiku",
            "mary@example.com",
            "0722222222",
            "Nyeri",
            "Professional house cleaning services"
        ),
        (
            "Peter Kamau",
            "peter@example.com",
            "0733333333",
            "Nairobi",
            "Electrical installation and repair"
        ),
        (
            "Grace Njeri",
            "grace@example.com",
            "0744444444",
            "Thika",
            "Hair styling and beauty services"
        ),
        (
            "David Otieno",
            "david@example.com",
            "0755555555",
            "Nyeri",
            "Carpentry and furniture repair"
        )
    ]

    
    for provider in demo_providers:
        # Skip demo providers if their email OR phone already exists.
        cursor.execute("""
            SELECT id
            FROM service_providers
            WHERE email = ? OR phone = ?
        """, (provider[1], provider[2]))

        if cursor.fetchone() is not None:
            continue

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
            provider[0],
            provider[1],
            provider[2],
            generate_password_hash("Provider@123"),
            provider[3],
            provider[4],
            "approved"
        ))

        cursor.execute(
            "SELECT id FROM service_providers WHERE email = ?",
            (provider[1],)
        )

        if cursor.fetchone() is None:
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
                provider[0],
                provider[1],
                provider[2],
                generate_password_hash("Provider@123"),
                provider[3],
                provider[4],
                "approved"
            ))

    conn.commit()
    conn.close()


def initialize_database():
    """Create tables and insert initial data."""
    create_tables()
    create_initial_data()


if __name__ == "__main__":
    initialize_database()
    print("HudumaLink database initialized successfully.")

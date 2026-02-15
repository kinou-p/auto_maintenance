
import sqlite3
from pathlib import Path

# Path to the database file
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "auto_maintenance.db"

def migrate():
    print(f"Checking database at: {DB_PATH}")
    if not DB_PATH.exists():
        print("Database file not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(workflows)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "updates_stats" in columns:
            print("Column 'updates_stats' already exists.")
        else:
            print("Adding 'updates_stats' column...")
            # SQLite does not support JSON type directly in DDL (it uses TEXT), 
            # but we can verify if it accepts JSON keyword or just use TEXT. 
            # SQLAlchemy maps JSON to JSON or TEXT. Let's use JSON if possible, or TEXT.
            # Usually 'JSON' as type name is accepted by SQLite for compatibility but stored as TEXT/BLOB.
            # We use DEFAULT '{}' to handle existing rows.
            cursor.execute("ALTER TABLE workflows ADD COLUMN updates_stats JSON DEFAULT '{}' NOT NULL")
            conn.commit()
            print("Column added successfully.")

    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()

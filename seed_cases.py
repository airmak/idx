"""
IDx Case Seeder
Reads case JSON files from the cases/ directory and inserts them into the SQLite database.
Idempotent — skips cases that already exist.
Run directly: python seed_cases.py
Also called automatically at app startup.
"""

import os
import json
import glob
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "idx.db")
CASES_DIR = os.path.join(BASE_DIR, "cases")

REQUIRED_KEYS = {
    "case_id", "mode", "specialty", "diagnosis", "icd_category",
    "one_liner", "stage2", "stage3", "stage5", "debrief", "ddx_hints"
}


def get_engine():
    return create_engine(f"sqlite:///{DB_PATH}", echo=False)


def init_db(engine):
    """Create tables if they don't exist."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_uid TEXT UNIQUE NOT NULL,
                mode TEXT NOT NULL,
                specialty TEXT NOT NULL,
                diagnosis TEXT NOT NULL,
                case_data TEXT NOT NULL,
                times_played INTEGER DEFAULT 0,
                times_correct INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS session_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                case_uid TEXT NOT NULL,
                score INTEGER,
                correct BOOLEAN,
                user_id INTEGER,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        # Migration: add user_id to session_history if missing
        try:
            conn.execute(text("SELECT user_id FROM session_history LIMIT 1"))
        except Exception:
            try:
                conn.execute(text("ALTER TABLE session_history ADD COLUMN user_id INTEGER"))
                conn.commit()
            except Exception:
                pass


def validate_case(data: dict, filename: str) -> bool:
    """Validate that a case has the required top-level keys."""
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        print(f"  [SKIP] {filename}: missing required keys: {missing}")
        return False
    if data.get("mode") not in ("easy", "attending"):
        print(f"  [SKIP] {filename}: mode must be 'easy' or 'attending', got: {data.get('mode')}")
        return False
    return True


def seed(verbose=True):
    """
    Seed the database with all cases in the cases/ directory.
    Returns (seeded_count, skipped_count).
    """
    engine = get_engine()
    init_db(engine)

    case_files = sorted(glob.glob(os.path.join(CASES_DIR, "*.json")))

    if not case_files:
        if verbose:
            print(f"No case files found in {CASES_DIR}/")
        return 0, 0

    seeded = 0
    skipped = 0
    errors = 0

    for filepath in case_files:
        filename = os.path.basename(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            if verbose:
                print(f"  [ERROR] {filename}: invalid JSON — {e}")
            errors += 1
            continue
        except OSError as e:
            if verbose:
                print(f"  [ERROR] {filename}: could not read — {e}")
            errors += 1
            continue

        if not validate_case(data, filename):
            errors += 1
            continue

        case_uid = data["case_id"]
        try:
            with engine.connect() as conn:
                existing = conn.execute(
                    text("SELECT id FROM cases WHERE case_uid = :uid"),
                    {"uid": case_uid}
                ).fetchone()

                if existing:
                    if verbose:
                        print(f"  [SKIP] {filename} (case_uid={case_uid}): already exists")
                    skipped += 1
                    continue

                conn.execute(
                    text("""
                        INSERT INTO cases (case_uid, mode, specialty, diagnosis, case_data)
                        VALUES (:uid, :mode, :specialty, :diagnosis, :case_data)
                    """),
                    {
                        "uid": case_uid,
                        "mode": data["mode"],
                        "specialty": data["specialty"],
                        "diagnosis": data["diagnosis"],
                        "case_data": json.dumps(data)
                    }
                )
                conn.commit()
                if verbose:
                    print(f"  [OK] {filename} - {data['diagnosis']} ({data['mode']}, {data['specialty']})")
                seeded += 1

        except SQLAlchemyError as e:
            if verbose:
                print(f"  [ERROR] {filename}: database error - {e}")
            errors += 1

    if verbose:
        print(f"\nSeeding complete: {seeded} seeded, {skipped} already existed (skipped), {errors} errors.")

    return seeded, skipped


if __name__ == "__main__":
    print(f"IDx Case Seeder")
    print(f"Database: {DB_PATH}")
    print(f"Cases directory: {CASES_DIR}\n")
    seed(verbose=True)

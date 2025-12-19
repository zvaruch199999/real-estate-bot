import sqlite3
from datetime import datetime, UTC

DB_NAME = "offers.db"


def get_db():
    return sqlite3.connect(DB_NAME)


def init_db():
    db = get_db()
    cur = db.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT,
        category TEXT,
        street TEXT,
        district TEXT,
        advantages TEXT,
        rent TEXT,
        deposit TEXT,
        commission TEXT,
        parking TEXT,
        settlement TEXT,
        viewing TEXT,
        broker TEXT,
        photos TEXT,
        status TEXT
    )
    """)

    db.commit()
    db.close()


def norm(value):
    return value if value else ""


def create_offer(data: dict):
    db = get_db()
    cur = db.cursor()

    cur.execute("""
    INSERT INTO offers (
        created_at, category, street, district, advantages,
        rent, deposit, commission, parking, settlement,
        viewing, broker, photos, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now(UTC).isoformat(),
        norm(data.get("category")),
        norm(data.get("street")),
        norm(data.get("district")),
        norm(data.get("advantages")),
        norm(data.get("rent")),
        norm(data.get("deposit")),
        norm(data.get("commission")),
        norm(data.get("parking")),
        norm(data.get("settlement")),
        norm(data.get("viewing")),
        norm(data.get("broker")),
        ",".join(data.get("photos", [])),
        norm(data.get("status")),
    ))

    db.commit()
    db.close()

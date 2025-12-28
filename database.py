import json
import aiosqlite
from datetime import datetime, timezone

DB_PATH = "data/bot.db"

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

STATUS_DRAFT = "DRAFT"
STATUS_ACTIVE = "ACTIVE"
STATUS_RESERVE = "RESERVE"
STATUS_WITHDRAWN = "WITHDRAWN"   # показуємо як "Знято"
STATUS_CLOSED = "CLOSED"

STATUS_LABELS = {
    STATUS_DRAFT: "📝 Чернетка",
    STATUS_ACTIVE: "🟢 Актуально",
    STATUS_RESERVE: "🟡 Резерв",
    STATUS_WITHDRAWN: "⚫️ Знято",
    STATUS_CLOSED: "✅ Угода закрита",
}

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS listings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER UNIQUE,
            status TEXT,
            category TEXT,
            housing_type TEXT,
            street TEXT,
            city TEXT,
            district TEXT,
            advantages TEXT,
            rent TEXT,
            deposit TEXT,
            commission TEXT,
            parking TEXT,
            settlement_from TEXT,
            viewings_from TEXT,
            broker TEXT,
            photos_json TEXT,
            group_chat_id INTEGER,
            group_message_id INTEGER,
            created_at TEXT,
            updated_at TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS status_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER,
            number INTEGER,
            status TEXT,
            changed_by TEXT,
            changed_at TEXT
        )
        """)
        await db.commit()

async def _next_number(db: aiosqlite.Connection) -> int:
    cur = await db.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM listings")
    (n,) = await cur.fetchone()
    await cur.close()
    return int(n)

async def create_listing(broker: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN")
        number = await _next_number(db)
        ts = now_iso()
        await db.execute("""
            INSERT INTO listings(
                number,status,category,housing_type,street,city,district,advantages,
                rent,deposit,commission,parking,settlement_from,viewings_from,broker,
                photos_json,group_chat_id,group_message_id,created_at,updated_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            number, STATUS_DRAFT,
            "", "", "", "", "", "",
            "", "", "", "", "", "",
            broker, json.dumps([]), None, None, ts, ts
        ))
        await db.execute("""
            INSERT INTO status_history(listing_id, number, status, changed_by, changed_at)
            VALUES((SELECT id FROM listings WHERE number=?), ?, ?, ?, ?)
        """, (number, number, STATUS_DRAFT, broker, ts))
        await db.commit()
        return number

async def get_listing(number: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM listings WHERE number=?", (number,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

async def update_field(number: int, field: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE listings SET {field}=?, updated_at=? WHERE number=?",
            (value, now_iso(), number)
        )
        await db.commit()

async def add_photo(number: int, file_id: str):
    listing = await get_listing(number)
    if not listing:
        return
    photos = json.loads(listing["photos_json"] or "[]")
    photos.append(file_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE listings SET photos_json=?, updated_at=? WHERE number=?",
            (json.dumps(photos), now_iso(), number)
        )
        await db.commit()

async def clear_photos(number: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE listings SET photos_json=?, updated_at=? WHERE number=?",
            (json.dumps([]), now_iso(), number)
        )
        await db.commit()

async def set_group_message(number: int, chat_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE listings
            SET group_chat_id=?, group_message_id=?, updated_at=?
            WHERE number=?
        """, (chat_id, message_id, now_iso(), number))
        await db.commit()

async def set_status(number: int, status: str, changed_by: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE listings
            SET status=?, updated_at=?
            WHERE number=?
        """, (status, now_iso(), number))

        await db.execute("""
            INSERT INTO status_history(listing_id, number, status, changed_by, changed_at)
            VALUES((SELECT id FROM listings WHERE number=?), ?, ?, ?, ?)
        """, (number, number, status, changed_by, now_iso()))
        await db.commit()

async def delete_listing(number: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM status_history WHERE number=?", (number,))
        await db.execute("DELETE FROM listings WHERE number=?", (number,))
        await db.commit()

async def stats_period(start_iso: str, end_iso: str):
    """
    Рахує по history: скільки разів за період ставили кожен статус,
    і по маклерам — скільки разів кожен статус.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # totals
        cur = await db.execute("""
            SELECT status, COUNT(*) as cnt
            FROM status_history
            WHERE changed_at >= ? AND changed_at < ?
            GROUP BY status
        """, (start_iso, end_iso))
        totals = {row[0]: row[1] for row in await cur.fetchall()}
        await cur.close()

        # by broker
        cur = await db.execute("""
            SELECT changed_by, status, COUNT(*) as cnt
            FROM status_history
            WHERE changed_at >= ? AND changed_at < ?
            GROUP BY changed_by, status
            ORDER BY changed_by
        """, (start_iso, end_iso))
        by_broker = {}
        rows = await cur.fetchall()
        await cur.close()

        for who, st, cnt in rows:
            by_broker.setdefault(who or "—", {})
            by_broker[who or "—"][st] = cnt

        return totals, by_broker

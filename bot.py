# bot.py
# ORANDA SK — Real Estate Telegram Bot (aiogram 3.7+)
# ✅ Працює з aiogram>=3.7 (parse_mode через DefaultBotProperties)
# ✅ Створення пропозиції (категорія → тип житла (+ Інше) → поля → фото → превʼю → публікація)
# ✅ Публікація в групу: фото альбомом + окремий пост з кнопками статусів під ним
# ✅ Статуси: 🟢 Актуально / 🟡 Резерв / ⚫️ Знято / ✅ Угода закрита
# ✅ Немає "Чернетка", нема "Неактуально", нема "withdraw"
# ✅ Редагування пропозиції по номеру пункту (в боті)
# ✅ Статистика Day/Month/Year + по маклерам (кожен статус окремо)
# ✅ /export — експорт CSV (без openpyxl)

import asyncio
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

# ---------------------------
# ENV
# ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не заданий в Environment")

# ТИ МАЄШ GROUP_CHAT_ID — використовуємо його (і лишаємо fallback на GROUP_ID)
GROUP_CHAT_ID_RAW = os.getenv("GROUP_CHAT_ID") or os.getenv("GROUP_ID")
if not GROUP_CHAT_ID_RAW:
    raise RuntimeError("GROUP_CHAT_ID (або GROUP_ID) не заданий в Environment")
try:
    GROUP_CHAT_ID = int(GROUP_CHAT_ID_RAW)
except ValueError:
    raise RuntimeError("GROUP_CHAT_ID має бути числом (наприклад -1001234567890)")

TZ = ZoneInfo(os.getenv("TZ", "Europe/Bratislava"))

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "bot.db"


# ---------------------------
# DB
# ---------------------------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                k TEXT PRIMARY KEY,
                v TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_no INTEGER UNIQUE NOT NULL,
                creator_id INTEGER NOT NULL,
                creator_username TEXT,
                category TEXT,
                housing_type TEXT,
                street TEXT,
                city TEXT,
                district TEXT,
                perks TEXT,
                rent TEXT,
                deposit TEXT,
                commission TEXT,
                parking TEXT,
                move_in TEXT,
                viewings TEXT,
                broker TEXT,
                photos_json TEXT DEFAULT '[]',
                group_message_id INTEGER,
                status TEXT DEFAULT 'АКТУАЛЬНО',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS status_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                by_user_id INTEGER,
                by_username TEXT,
                ts TEXT NOT NULL,
                FOREIGN KEY(offer_id) REFERENCES offers(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS offer_posts (
                offer_id INTEGER PRIMARY KEY,
                group_chat_id INTEGER NOT NULL,
                group_message_id INTEGER NOT NULL,
                FOREIGN KEY(offer_id) REFERENCES offers(id)
            )
            """
        )
        conn.commit()


def meta_get(key: str, default: str = "") -> str:
    with db() as conn:
        row = conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return row["v"] if row else default


def meta_set(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (key, value),
        )
        conn.commit()


def next_offer_no() -> int:
    last = int(meta_get("last_offer_no", "0"))
    last += 1
    meta_set("last_offer_no", str(last))
    return last


def create_offer(creator_id: int, creator_username: Optional[str]) -> int:
    offer_no = next_offer_no()
    now = datetime.now(TZ).isoformat()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO offers(
              offer_no, creator_id, creator_username,
              category, housing_type, street, city, district, perks,
              rent, deposit, commission, parking, move_in, viewings, broker,
              photos_json, status, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                offer_no,
                creator_id,
                creator_username or None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                creator_username or None,  # broker default
                "[]",
                "АКТУАЛЬНО",  # одразу нормальний статус, без "чернеток"
                now,
                now,
            ),
        )
        offer_id = conn.execute("SELECT id FROM offers WHERE offer_no=?", (offer_no,)).fetchone()["id"]
        conn.commit()
    return offer_id


def get_offer(offer_id: int) -> sqlite3.Row:
    with db() as conn:
        row = conn.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
        if not row:
            raise RuntimeError("Offer not found")
        return row


def get_offer_by_no(offer_no: int) -> Optional[sqlite3.Row]:
    with db() as conn:
        return conn.execute("SELECT * FROM offers WHERE offer_no=?", (offer_no,)).fetchone()


def update_offer_field(offer_id: int, field: str, value: Optional[str]) -> None:
    now = datetime.now(TZ).isoformat()
    with db() as conn:
        conn.execute(f"UPDATE offers SET {field}=?, updated_at=? WHERE id=?", (value, now, offer_id))
        conn.commit()


def add_offer_photo(offer_id: int, file_id: str) -> int:
    with db() as conn:
        row = conn.execute("SELECT photos_json FROM offers WHERE id=?", (offer_id,)).fetchone()
        photos = json.loads(row["photos_json"] or "[]")
        photos.append(file_id)
        conn.execute(
            "UPDATE offers SET photos_json=?, updated_at=? WHERE id=?",
            (json.dumps(photos), datetime.now(TZ).isoformat(), offer_id),
        )
        conn.commit()
        return len(photos)


def set_offer_status(offer_id: int, status: str, by_user_id: int, by_username: Optional[str]) -> None:
    now = datetime.now(TZ).isoformat()
    with db() as conn:
        conn.execute("UPDATE offers SET status=?, updated_at=? WHERE id=?", (status, now, offer_id))
        conn.execute(
            "INSERT INTO status_events(offer_id,status,by_user_id,by_username,ts) VALUES(?,?,?,?,?)",
            (offer_id, status, by_user_id, by_username, now),
        )
        conn.commit()


def save_offer_group_post(offer_id: int, group_chat_id: int, group_message_id: int) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO offer_posts(offer_id, group_chat_id, group_message_id) VALUES(?,?,?) "
            "ON CONFLICT(offer_id) DO UPDATE SET group_chat_id=excluded.group_chat_id, group_message_id=excluded.group_message_id",
            (offer_id, group_chat_id, group_message_id),
        )
        conn.execute(
            "UPDATE offers SET group_message_id=?, updated_at=? WHERE id=?",
            (group_message_id, datetime.now(TZ).isoformat(), offer_id),
        )
        conn.commit()


# ---------------------------
# STATISTICS
# ---------------------------
STATUSES = {
    "АКТУАЛЬНО": ("🟢", "Актуально"),
    "РЕЗЕРВ": ("🟡", "Резерв"),
    "ЗНЯТО": ("⚫️", "Знято"),
    "ЗАКРИТО": ("✅", "Угода закрита"),
}


def period_bounds(kind: str) -> Tuple[datetime, datetime]:
    now = datetime.now(TZ)
    if kind == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end
    if kind == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    if kind == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
        return start, end
    raise ValueError("Unknown period")


def stats_for_period(kind: str) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]]]:
    start, end = period_bounds(kind)
    start_iso, end_iso = start.isoformat(), end.isoformat()
    totals: Dict[str, int] = {k: 0 for k in STATUSES.keys()}
    per_broker: Dict[str, Dict[str, int]] = {}

    with db() as conn:
        rows = conn.execute(
            """
            SELECT status, COALESCE(by_username, '') AS u, COUNT(*) AS c
            FROM status_events
            WHERE ts >= ? AND ts < ?
            GROUP BY status, u
            """,
            (start_iso, end_iso),
        ).fetchall()

    for r in rows:
        st = r["status"]
        u = r["u"] or "—"
        c = int(r["c"])
        if st not in totals:
            continue
        totals[st] += c
        if u not in per_broker:
            per_broker[u] = {k: 0 for k in STATUSES.keys()}
        per_broker[u][st] += c

    return totals, per_broker


def render_stats() -> str:
    now = datetime.now(TZ)
    parts: List[str] = ["📊 <b>Статистика статусів</b>\n"]

    for kind, title in [("day", f"День ({now.date()})"), ("month", f"Місяць ({now:%Y-%m})"), ("year", f"Рік ({now:%Y})")]:
        totals, per_broker = stats_for_period(kind)
        parts.append(f"<b>{title}</b>")
        for st, (emoji, name) in STATUSES.items():
            parts.append(f"{emoji} {name}: <b>{totals.get(st, 0)}</b>")
        parts.append("")
        parts.append("👨‍💼 <b>По маклерам (кожен статус окремо)</b>")
        if not per_broker:
            parts.append("— немає змін статусів за період\n")
        else:
            # Сортуємо по сумі
            def total_sum(u: str) -> int:
                return sum(per_broker[u].values())

            for u in sorted(per_broker.keys(), key=total_sum, reverse=True):
                line = [f"• <b>{u}</b>:"]
                for st, (emoji, name) in STATUSES.items():
                    line.append(f"{emoji}{per_broker[u].get(st, 0)}")
                parts.append(" ".join(line))
            parts.append("")
        parts.append("")

    return "\n".join(parts).strip()


# ---------------------------
# OFFER TEXT
# ---------------------------
FIELDS = [
    ("category", "🏷️", "Категорія"),
    ("housing_type", "🏠", "Тип житла"),
    ("street", "📍", "Вулиця"),
    ("city", "🏙️", "Місто"),
    ("district", "🗺️", "Район"),
    ("perks", "✨", "Переваги"),
    ("rent", "💶", "Оренда"),
    ("deposit", "🔐", "Депозит"),
    ("commission", "🤝", "Комісія"),
    ("parking", "🚗", "Паркінг"),
    ("move_in", "📦", "Заселення від"),
    ("viewings", "👀", "Огляди від"),
    ("broker", "🧑‍💼", "Маклер"),
]


def fmt(v: Any) -> str:
    if v is None:
        return "—"
    s = str(v).strip()
    return s if s else "—"


def offer_no_str(offer_no: int) -> str:
    return f"{offer_no:04d}"


def offer_text(offer_row: sqlite3.Row) -> str:
    st_key = offer_row["status"] or "АКТУАЛЬНО"
    st_emoji, st_name = STATUSES.get(st_key, ("🟢", "Актуально"))
    lines = []
    lines.append(f"🏡 <b>ПРОПОЗИЦІЯ #{offer_no_str(offer_row['offer_no'])}</b>")
    lines.append(f"📊 <b>Статус:</b> {st_emoji} <b>{st_name}</b>")
    lines.append("")
    for key, emo, label in FIELDS:
        val = fmt(offer_row[key])
        # трохи косметики для грошей
        if key in ("rent", "deposit", "commission") and val != "—" and "€" not in val:
            # якщо користувач ввів лише число — додаємо €
            if val.replace(" ", "").replace(",", "").replace(".", "").isdigit():
                val = f"{val}€"
        lines.append(f"{emo} <b>{label}:</b> {val}")
    return "\n".join(lines)


# ---------------------------
# KEYBOARDS
# ---------------------------
def kb_categories() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Оренда", callback_data="cat:ОРЕНДА"),
                InlineKeyboardButton(text="Продаж", callback_data="cat:ПРОДАЖ"),
            ]
        ]
    )


def kb_housing_types() -> InlineKeyboardMarkup:
    # з "Інше..." як просив
    rows = [
        [InlineKeyboardButton(text="Кімната", callback_data="ht:Кімната"),
         InlineKeyboardButton(text="1-кімн.", callback_data="ht:1-кімн.")],
        [InlineKeyboardButton(text="2-кімн.", callback_data="ht:2-кімн."),
         InlineKeyboardButton(text="3-кімн.", callback_data="ht:3-кімн.")],
        [InlineKeyboardButton(text="Будинок", callback_data="ht:Будинок"),
         InlineKeyboardButton(text="Студія", callback_data="ht:Студія")],
        [InlineKeyboardButton(text="Інше...", callback_data="ht:__OTHER__")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_photos_done() -> InlineKeyboardMarkup:
    # КНОПКА тут потрібна (як ти просив повернути)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos:done")]
        ]
    )


def kb_preview_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📤 Публікувати", callback_data="pv:publish"),
                InlineKeyboardButton(text="✏️ Редагувати", callback_data="pv:edit"),
            ],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="pv:cancel")],
        ]
    )


def kb_statuses(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢 Актуально", callback_data=f"st:{offer_id}:АКТУАЛЬНО"),
                InlineKeyboardButton(text="🟡 Резерв", callback_data=f"st:{offer_id}:РЕЗЕРВ"),
            ],
            [
                InlineKeyboardButton(text="⚫️ Знято", callback_data=f"st:{offer_id}:ЗНЯТО"),
                InlineKeyboardButton(text="✅ Угода закрита", callback_data=f"st:{offer_id}:ЗАКРИТО"),
            ],
        ]
    )


# ---------------------------
# FSM
# ---------------------------
class CreateOffer(StatesGroup):
    category = State()
    housing_type = State()
    housing_type_custom = State()
    street = State()
    city = State()
    district = State()
    perks = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in = State()
    viewings = State()
    broker = State()
    photos = State()
    preview = State()


class EditOffer(StatesGroup):
    choose_field = State()
    new_value = State()
    housing_type_custom = State()


# ---------------------------
# ROUTER
# ---------------------------
router = Router()


# ---------------------------
# HELPERS
# ---------------------------
def user_mention(u: types.User) -> str:
    if u.username:
        return f"@{u.username}"
    return f"{u.full_name}"


async def safe_answer(cb: types.CallbackQuery) -> None:
    try:
        await cb.answer()
    except Exception:
        pass


async def send_offer_preview(bot: Bot, chat_id: int, offer_row: sqlite3.Row) -> None:
    photos = json.loads(offer_row["photos_json"] or "[]")
    if photos:
        await send_photos(bot, chat_id, photos)
    await bot.send_message(chat_id, offer_text(offer_row), reply_markup=kb_preview_actions())


async def send_photos(bot: Bot, chat_id: int, photos: List[str]) -> None:
    if not photos:
        return
    if len(photos) == 1:
        await bot.send_photo(chat_id, photos[0])
        return
    media = [InputMediaPhoto(media=pid) for pid in photos[:10]]  # telegram limits
    # якщо більше 10 — шлемо пакетами
    for i in range(0, len(media), 10):
        await bot.send_media_group(chat_id, media[i:i + 10])


async def publish_to_group(bot: Bot, offer_id: int, by_user: types.User) -> None:
    offer_row = get_offer(offer_id)
    photos = json.loads(offer_row["photos_json"] or "[]")

    # 1) Спочатку альбом фото (як в тебе вже працювало)
    if photos:
        await send_photos(bot, GROUP_CHAT_ID, photos)

    # 2) Потім пост з текстом і кнопками статусів
    msg = await bot.send_message(
        GROUP_CHAT_ID,
        offer_text(offer_row),
        reply_markup=kb_statuses(offer_id),
    )
    save_offer_group_post(offer_id, GROUP_CHAT_ID, msg.message_id)

    # 3) Логуємо початковий статус як подію (важливо для статистики)
    set_offer_status(
        offer_id,
        status="АКТУАЛЬНО",
        by_user_id=by_user.id,
        by_username=user_mention(by_user),
    )


def edit_menu_text(offer_no: int) -> str:
    # Нумерація пунктів 1..13 (без статусів)
    lines = [f"✏️ <b>Редагування пропозиції #{offer_no_str(offer_no)}</b>"]
    lines.append("Напиши <b>номер пункту 1–13</b>, який хочеш змінити.")
    lines.append("Наприклад: <b>2</b>\n")
    lines.append("<b>Список:</b>")
    for i, (_, emo, label) in enumerate(FIELDS, start=1):
        lines.append(f"{i}. {label}")
    return "\n".join(lines)


def field_by_number(n: int) -> Tuple[str, str, str]:
    # returns (key, emoji, label)
    return FIELDS[n - 1]


# ---------------------------
# COMMANDS
# ---------------------------
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привіт!\n\n"
        "Команди:\n"
        "• /new — створити пропозицію\n"
        "• /stats — статистика\n"
        "• /export — експорт CSV\n"
        "• /id — показати chat id\n"
    )


@router.message(Command("id"))
async def cmd_id(message: types.Message):
    await message.answer(f"Your ID: <b>{message.from_user.id}</b>\nCurrent chat ID: <b>{message.chat.id}</b>")


@router.message(Command("new"))
async def cmd_new(message: types.Message, state: FSMContext):
    # створюємо офер і йдемо по кроках
    offer_id = create_offer(message.from_user.id, user_mention(message.from_user))
    await state.update_data(offer_id=offer_id)
    await state.set_state(CreateOffer.category)
    await message.answer("Обери категорію:", reply_markup=kb_categories())


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    await message.answer(render_stats())


@router.message(Command("export"))
async def cmd_export(message: types.Message):
    # експорт CSV (щоб не тягнути openpyxl)
    now = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    path = DATA_DIR / f"offers_export_{now}.csv"

    with db() as conn:
        rows = conn.execute(
            """
            SELECT offer_no, status, category, housing_type, street, city, district,
                   perks, rent, deposit, commission, parking, move_in, viewings, broker,
                   created_at, updated_at
            FROM offers
            ORDER BY offer_no ASC
            """
        ).fetchall()

    header = [
        "offer_no", "status", "category", "housing_type", "street", "city", "district",
        "perks", "rent", "deposit", "commission", "parking", "move_in", "viewings", "broker",
        "created_at", "updated_at",
    ]

    # simple csv write
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([r[h] for h in header])

    await message.answer_document(types.FSInputFile(path), caption="📄 Експорт CSV готовий")


# ---------------------------
# CREATE FLOW — CALLBACKS
# ---------------------------
@router.callback_query(StateFilter(CreateOffer.category), F.data.startswith("cat:"))
async def on_category(cb: types.CallbackQuery, state: FSMContext):
    await safe_answer(cb)
    data = await state.get_data()
    offer_id = data["offer_id"]

    category = cb.data.split(":", 1)[1]
    update_offer_field(offer_id, "category", category)

    await state.set_state(CreateOffer.housing_type)
    await cb.message.answer("Обери тип житла:", reply_markup=kb_housing_types())


@router.callback_query(StateFilter(CreateOffer.housing_type), F.data.startswith("ht:"))
async def on_housing_type(cb: types.CallbackQuery, state: FSMContext):
    await safe_answer(cb)
    data = await state.get_data()
    offer_id = data["offer_id"]

    value = cb.data.split(":", 1)[1]
    if value == "__OTHER__":
        await state.set_state(CreateOffer.housing_type_custom)
        await cb.message.answer("✍️ Напиши свій варіант типу житла:")
        return

    update_offer_field(offer_id, "housing_type", value)
    await state.set_state(CreateOffer.street)
    await cb.message.answer("📍 Вулиця (можна коротко, напр. Grabova 12):")


@router.message(StateFilter(CreateOffer.housing_type_custom))
async def on_housing_type_custom(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt:
        await message.answer("Напиши текстом тип житла:")
        return
    data = await state.get_data()
    offer_id = data["offer_id"]
    update_offer_field(offer_id, "housing_type", txt)

    await state.set_state(CreateOffer.street)
    await message.answer("📍 Вулиця (можна коротко, напр. Grabova 12):")


# ---------------------------
# CREATE FLOW — TEXT FIELDS
# ---------------------------
async def set_and_next(state: FSMContext, offer_id: int, field: str, next_state: State, prompt: str, message: types.Message):
    val = (message.text or "").strip()
    if val in ("-", "—", "0") and field not in ("rent", "deposit", "commission"):
        # дозволяємо очищення
        val = None
    update_offer_field(offer_id, field, val if val else None)
    await state.set_state(next_state)
    await message.answer(prompt)


@router.message(StateFilter(CreateOffer.street))
async def on_street(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await set_and_next(state, data["offer_id"], "street", CreateOffer.city, "🏙️ Місто:", message)


@router.message(StateFilter(CreateOffer.city))
async def on_city(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await set_and_next(state, data["offer_id"], "city", CreateOffer.district, "🗺️ Район:", message)


@router.message(StateFilter(CreateOffer.district))
async def on_district(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await set_and_next(state, data["offer_id"], "district", CreateOffer.perks, "✨ Переваги (через кому або текст):", message)


@router.message(StateFilter(CreateOffer.perks))
async def on_perks(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await set_and_next(state, data["offer_id"], "perks", CreateOffer.rent, "💶 Оренда (напр. 350€):", message)


@router.message(StateFilter(CreateOffer.rent))
async def on_rent(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await set_and_next(state, data["offer_id"], "rent", CreateOffer.deposit, "🔐 Депозит (напр. 350€):", message)


@router.message(StateFilter(CreateOffer.deposit))
async def on_deposit(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await set_and_next(state, data["offer_id"], "deposit", CreateOffer.commission, "🤝 Комісія (напр. 98€):", message)


@router.message(StateFilter(CreateOffer.commission))
async def on_commission(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await set_and_next(state, data["offer_id"], "commission", CreateOffer.parking, "🚗 Паркінг (так/ні або опис):", message)


@router.message(StateFilter(CreateOffer.parking))
async def on_parking(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await set_and_next(state, data["offer_id"], "parking", CreateOffer.move_in, "📦 Заселення від (напр. Вже / 01.01):", message)


@router.message(StateFilter(CreateOffer.move_in))
async def on_move_in(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await set_and_next(state, data["offer_id"], "move_in", CreateOffer.viewings, "👀 Огляди від (напр. Вже / 10:00):", message)


@router.message(StateFilter(CreateOffer.viewings))
async def on_viewings(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await set_and_next(state, data["offer_id"], "viewings", CreateOffer.broker, "🧑‍💼 Маклер (наприклад @username). Можна залишити як є:", message)


@router.message(StateFilter(CreateOffer.broker))
async def on_broker(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    val = (message.text or "").strip()
    if not val:
        val = user_mention(message.from_user)
    update_offer_field(offer_id, "broker", val)

    await state.set_state(CreateOffer.photos)
    await message.answer("📸 Надішли фото. Коли закінчиш — натисни кнопку або напиши /done", reply_markup=kb_photos_done())


# ---------------------------
# PHOTO COLLECTION
# ---------------------------
@router.message(StateFilter(CreateOffer.photos), Command("done"))
async def done_photos_cmd(message: types.Message, state: FSMContext):
    await finish_photos(message, state)


@router.callback_query(StateFilter(CreateOffer.photos), F.data == "photos:done")
async def done_photos_cb(cb: types.CallbackQuery, state: FSMContext):
    await safe_answer(cb)
    # для кнопки важливо: відповісти, а далі завершити
    msg = cb.message
    fake_message = types.Message(
        message_id=msg.message_id,
        date=msg.date,
        chat=msg.chat,
        from_user=cb.from_user,
        sender_chat=msg.sender_chat,
        content_type="text",
        text="/done",
    )
    await finish_photos(fake_message, state)


@router.message(StateFilter(CreateOffer.photos), F.photo)
async def on_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]

    # найбільше фото
    file_id = message.photo[-1].file_id
    n = add_offer_photo(offer_id, file_id)
    await message.answer(f"📸 Фото додано ({n}).", reply_markup=kb_photos_done())


@router.message(StateFilter(CreateOffer.photos))
async def on_photo_other(message: types.Message, state: FSMContext):
    # Підтримка тексту "Готово" (бо ти це хотів раніше)
    txt = (message.text or "").strip().lower()
    if txt in ("готово", "done", "/done"):
        await finish_photos(message, state)
        return
    await message.answer("Надішли фото або /done щоб завершити.", reply_markup=kb_photos_done())


async def finish_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    offer_row = get_offer(offer_id)
    photos = json.loads(offer_row["photos_json"] or "[]")
    if not photos:
        await message.answer("⚠️ Спочатку додай хоча б 1 фото.", reply_markup=kb_photos_done())
        return

    # ВАЖЛИВО: щоб не плодило дублікати — ставимо state preview і більше /done не обробляємо як finish
    await state.set_state(CreateOffer.preview)

    await message.answer("👉 <b>Це фінальний вигляд пропозиції</b> (перевір):")
    await send_offer_preview(message.bot, message.chat.id, get_offer(offer_id))


# ---------------------------
# PREVIEW ACTIONS
# ---------------------------
@router.callback_query(StateFilter(CreateOffer.preview), F.data == "pv:publish")
async def on_publish(cb: types.CallbackQuery, state: FSMContext):
    await safe_answer(cb)
    data = await state.get_data()
    offer_id = data["offer_id"]

    await publish_to_group(cb.bot, offer_id, cb.from_user)
    offer_row = get_offer(offer_id)
    await cb.message.answer(f"✅ Пропозицію #{offer_no_str(offer_row['offer_no'])} опубліковано в групу.")
    await state.clear()


@router.callback_query(StateFilter(CreateOffer.preview), F.data == "pv:edit")
async def on_preview_edit(cb: types.CallbackQuery, state: FSMContext):
    await safe_answer(cb)
    data = await state.get_data()
    offer_id = data["offer_id"]
    offer_row = get_offer(offer_id)

    await state.set_state(EditOffer.choose_field)
    await state.update_data(offer_id=offer_id)
    await cb.message.answer(edit_menu_text(offer_row["offer_no"]))


@router.callback_query(StateFilter(CreateOffer.preview), F.data == "pv:cancel")
async def on_cancel(cb: types.CallbackQuery, state: FSMContext):
    await safe_answer(cb)
    await cb.message.answer("❌ Скасовано.")
    await state.clear()


# ---------------------------
# EDIT FLOW (BOT CHAT)
# ---------------------------
@router.message(StateFilter(EditOffer.choose_field))
async def on_edit_choose_field(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer("Напиши номер пункту <b>1–13</b> цифрою.")
        return

    n = int(txt)
    if n < 1 or n > len(FIELDS):
        await message.answer("Номер має бути в діапазоні <b>1–13</b>.")
        return

    key, emo, label = field_by_number(n)
    data = await state.get_data()
    offer_id = data["offer_id"]

    await state.update_data(edit_field=key, edit_field_label=label)

    if key == "housing_type":
        # показуємо список типів + Інше
        await state.set_state(CreateOffer.housing_type)  # переюзаємо хендлер ht:
        await state.update_data(offer_id=offer_id)
        await message.answer("Обери тип житла:", reply_markup=kb_housing_types())
        return

    await state.set_state(EditOffer.new_value)
    await message.answer(f"{emo} <b>{label}</b>\nНапиши нове значення (або '-' щоб очистити):")


@router.message(StateFilter(EditOffer.new_value))
async def on_edit_new_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    field = data["edit_field"]
    label = data.get("edit_field_label", field)

    val = (message.text or "").strip()
    if val in ("-", "—"):
        val = None

    update_offer_field(offer_id, field, val if val else None)

    offer_row = get_offer(offer_id)
    await state.clear()

    await message.answer("✅ Оновлено. Ось оновлений вигляд:")
    await send_offer_preview(message.bot, message.chat.id, offer_row)


# ---------------------------
# STATUS BUTTONS IN GROUP
# ---------------------------
@router.callback_query(F.data.startswith("st:"))
async def on_status_change(cb: types.CallbackQuery):
    await safe_answer(cb)

    # працює в групі
    # st:<offer_id>:<STATUS>
    try:
        _, offer_id_s, status = cb.data.split(":", 2)
        offer_id = int(offer_id_s)
        if status not in STATUSES:
            return
    except Exception:
        return

    # оновлюємо статус + лог події
    set_offer_status(
        offer_id,
        status=status,
        by_user_id=cb.from_user.id,
        by_username=user_mention(cb.from_user),
    )

    # редагуємо текст цього повідомлення (НЕ видаляємо, тому воно не зникає)
    offer_row = get_offer(offer_id)
    try:
        await cb.message.edit_text(
            offer_text(offer_row),
            reply_markup=kb_statuses(offer_id),
        )
    except Exception:
        # якщо не можна редагувати (наприклад старе повідомлення) — просто відправимо нове
        await cb.message.answer(offer_text(offer_row), reply_markup=kb_statuses(offer_id))


# ---------------------------
# FALLBACK: /new /stats /export також як текст
# ---------------------------
@router.message(F.text)
async def text_shortcuts(message: types.Message):
    t = (message.text or "").strip().lower()
    if t in ("зробити пропозицію", "створити", "+ зробити пропозицію", "new"):
        # без reply клавіатур — як ти просив
        await cmd_new(message, FSMContext(storage=MemoryStorage(), key=types.StorageKey(bot_id=0, chat_id=0, user_id=0)))  # won't be used
        return


# ---------------------------
# MAIN
# ---------------------------
async def main():
    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Пуллінг
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

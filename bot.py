# bot.py
# ORANDA SK — Real Estate Telegram Bot (Aiogram 3.7+)
# ✅ Створення пропозиції + фото (альбом)
# ✅ Попередній перегляд: Публікувати / Редагувати / Скасувати
# ✅ Публікація в групу: альбом + повідомлення з кнопками статусу (під пропозицією)
# ✅ Статуси: ❔ Невідома / 🟢 Актуально / 🟡 Резерв / ⚫️ Знято / ✅ Угода закрита
# ✅ Статистика (день/місяць/рік): загалом + по маклерах (кількість кожного статусу)
# ✅ /export (Excel) — генерує файл і надсилає в чат
#
# 🔧 Правки:
# 1) При створенні пропозиції ставимо статус: ❔ Невідома
# 2) Паркінг: можна обрати кнопкою або вписати текстом
# 3) Додано поле "Прописка" перед паркінгом
# 4) Додано поле "Джерело ключів" останнім перед фото

import os
import json
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State

from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import FSInputFile

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None


# =========================
# ENV / CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GROUP_CHAT_ID_RAW = (os.getenv("GROUP_CHAT_ID") or os.getenv("GROUP_ID") or "").strip()

DATA_DIR = os.getenv("DATA_DIR", "data")
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "database.db"))

ALLOWED_USER_IDS_RAW = (os.getenv("ALLOWED_USER_IDS") or "").strip()
ALLOWED_USER_IDS = set()
if ALLOWED_USER_IDS_RAW:
    for part in ALLOWED_USER_IDS_RAW.split(","):
        part = part.strip()
        if part.isdigit():
            ALLOWED_USER_IDS.add(int(part))

APP_TZ = timezone.utc


STATUS = {
    "unknown": "❔ Невідома",
    "active": "🟢 Актуально",
    "reserve": "🟡 Резерв",
    "removed": "⚫️ Знято",
    "closed": "✅ Угода закрита",
}
STATUS_ORDER = ["unknown", "active", "reserve", "removed", "closed"]


# =========================
# DB
# =========================
def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)


def db_conn() -> sqlite3.Connection:
    ensure_dirs()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def ensure_column(cur: sqlite3.Cursor, table: str, column: str, column_def: str):
    cur.execute(f"PRAGMA table_info({table});")
    existing = [row[1] for row in cur.fetchall()]
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def};")


def init_db():
    con = db_conn()
    cur = con.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seq INTEGER UNIQUE,
            created_at TEXT,
            category TEXT,
            housing_type TEXT,
            street TEXT,
            city TEXT,
            district TEXT,
            advantages TEXT,
            rent TEXT,
            deposit TEXT,
            commission TEXT,
            registration TEXT DEFAULT '',
            parking TEXT,
            move_in_from TEXT,
            viewings_from TEXT,
            keys_source TEXT DEFAULT '',
            broker_username TEXT,
            broker_user_id INTEGER,
            photos_json TEXT,
            current_status TEXT,
            is_published INTEGER DEFAULT 0,
            published_chat_id INTEGER,
            published_message_id INTEGER
        );
        """
    )

    # ✅ Якщо база вже існувала раніше, ці колонки додадуться автоматично
    ensure_column(cur, "offers", "registration", "TEXT DEFAULT ''")
    ensure_column(cur, "offers", "keys_source", "TEXT DEFAULT ''")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS status_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER,
            at TEXT,
            status TEXT,
            username TEXT,
            user_id INTEGER
        );
        """
    )

    con.commit()
    con.close()


def now_iso() -> str:
    return datetime.now(tz=APP_TZ).isoformat(timespec="seconds")


def next_seq() -> int:
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM offers;")
    row = cur.fetchone()
    con.close()
    return int(row["next_seq"])


def update_offer(offer_id: int, **fields):
    if not fields:
        return
    keys = list(fields.keys())
    vals = [fields[k] for k in keys]
    sets = ", ".join([f"{k} = ?" for k in keys])
    con = db_conn()
    cur = con.cursor()
    cur.execute(f"UPDATE offers SET {sets} WHERE id = ?;", (*vals, offer_id))
    con.commit()
    con.close()


def get_offer(offer_id: int) -> Optional[sqlite3.Row]:
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT * FROM offers WHERE id = ?;", (offer_id,))
    row = cur.fetchone()
    con.close()
    return row


def set_status(offer_id: int, status: str, username: str, user_id: int):
    if status not in STATUS:
        return

    update_offer(offer_id, current_status=status)

    con = db_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO status_events (offer_id, at, status, username, user_id) VALUES (?, ?, ?, ?, ?);",
        (offer_id, now_iso(), status, username, user_id),
    )
    con.commit()
    con.close()


def create_offer(broker_username: str, broker_user_id: int) -> int:
    seq = next_seq()
    created = now_iso()

    con = db_conn()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO offers (
            seq, created_at, category, housing_type, street, city, district, advantages,
            rent, deposit, commission, registration, parking, move_in_from, viewings_from,
            keys_source, broker_username, broker_user_id, photos_json, current_status, is_published
        ) VALUES (?, ?, '', '', '', '', '', '', '', '', '', '', '', '', '', '', ?, ?, '[]', ?, 0);
        """,
        (seq, created, broker_username, broker_user_id, "unknown"),
    )
    con.commit()
    offer_id = cur.lastrowid
    con.close()

    set_status(offer_id, "unknown", username=broker_username, user_id=broker_user_id)
    return offer_id


def add_photo(offer_id: int, file_id: str):
    offer = get_offer(offer_id)
    if not offer:
        return
    try:
        photos = json.loads(offer["photos_json"] or "[]")
    except Exception:
        photos = []
    photos.append(file_id)
    update_offer(offer_id, photos_json=json.dumps(photos, ensure_ascii=False))


# =========================
# HELPERS
# =========================
def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def offer_title(seq: int) -> str:
    return f"🏡 <b>ПРОПОЗИЦІЯ #{seq:04d}</b>"


def offer_text(offer: sqlite3.Row) -> str:
    seq = int(offer["seq"])
    status = (offer["current_status"] or "unknown").strip()
    st = STATUS.get(status, "❔ Невідома")

    def line(emoji: str, label: str, key: str):
        val = offer[key] or "—"
        return f"{emoji} <b>{label}:</b> {esc(str(val))}"

    broker = offer["broker_username"] or "—"
    if broker and not broker.startswith("@"):
        broker = f"@{broker}"

    parts = [
        offer_title(seq),
        f"📊 <b>Статус:</b> {st}",
        "",
        line("🏷️", "Категорія", "category"),
        line("🏠", "Тип житла", "housing_type"),
        line("📍", "Вулиця", "street"),
        line("🏙️", "Місто", "city"),
        line("🗺️", "Район", "district"),
        line("✨", "Переваги", "advantages"),
        line("💶", "Оренда", "rent"),
        line("🔐", "Депозит", "deposit"),
        line("🤝", "Комісія", "commission"),
        line("🪪", "Прописка", "registration"),
        line("🚗", "Паркінг", "parking"),
        line("📦", "Заселення від", "move_in_from"),
        line("👀", "Огляди від", "viewings_from"),
        line("🔑", "Джерело ключів", "keys_source"),
        f"🧑‍💼 <b>Маклер:</b> {esc(broker)}",
    ]
    return "\n".join(parts)


def kb_category() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Оренда", callback_data="cat:Оренда"),
                InlineKeyboardButton(text="Продаж", callback_data="cat:Продаж"),
            ]
        ]
    )


def kb_housing_type() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Кімната", callback_data="ht:Кімната"),
            InlineKeyboardButton(text="1-кімн.", callback_data="ht:1-кімн."),
        ],
        [
            InlineKeyboardButton(text="2-кімн.", callback_data="ht:2-кімн."),
            InlineKeyboardButton(text="3-кімн.", callback_data="ht:3-кімн."),
        ],
        [
            InlineKeyboardButton(text="Будинок", callback_data="ht:Будинок"),
            InlineKeyboardButton(text="Студія", callback_data="ht:Студія"),
        ],
        [InlineKeyboardButton(text="Інше…", callback_data="ht_other")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_parking() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Є", callback_data="park:Є"),
                InlineKeyboardButton(text="Немає", callback_data="park:Немає"),
            ]
        ]
    )


def kb_photos_done() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos_done")]
        ]
    )


def kb_preview_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📣 Публікувати", callback_data="pub"),
                InlineKeyboardButton(text="✏️ Редагувати", callback_data="edit"),
            ],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")],
        ]
    )


def kb_status_buttons(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢 Актуально", callback_data=f"st:{offer_id}:active"),
                InlineKeyboardButton(text="🟡 Резерв", callback_data=f"st:{offer_id}:reserve"),
            ],
            [
                InlineKeyboardButton(text="⚫️ Знято", callback_data=f"st:{offer_id}:removed"),
                InlineKeyboardButton(text="✅ Угода закрита", callback_data=f"st:{offer_id}:closed"),
            ],
        ]
    )


# =========================
# FSM
# =========================
class OfferFSM(StatesGroup):
    CATEGORY = State()
    HOUSING_TYPE = State()
    HOUSING_TYPE_OTHER = State()
    STREET = State()
    CITY = State()
    DISTRICT = State()
    ADVANTAGES = State()
    RENT = State()
    DEPOSIT = State()
    COMMISSION = State()
    REGISTRATION = State()
    PARKING = State()
    MOVE_IN_FROM = State()
    VIEWINGS_FROM = State()
    KEYS_SOURCE = State()
    PHOTOS = State()
    PREVIEW = State()
    EDIT_CHOOSE = State()
    EDIT_VALUE = State()


EDIT_FIELDS = [
    (1, "Категорія", "category"),
    (2, "Тип житла", "housing_type"),
    (3, "Вулиця", "street"),
    (4, "Місто", "city"),
    (5, "Район", "district"),
    (6, "Переваги", "advantages"),
    (7, "Оренда", "rent"),
    (8, "Депозит", "deposit"),
    (9, "Комісія", "commission"),
    (10, "Прописка", "registration"),
    (11, "Паркінг", "parking"),
    (12, "Заселення від", "move_in_from"),
    (13, "Огляди від", "viewings_from"),
    (14, "Джерело ключів", "keys_source"),
    (15, "Маклер", "broker_username"),
]


def edit_list_text(seq: int) -> str:
    lines = [
        f"✏️ <b>Редагування #{seq:04d}</b>",
        "Напиши номер пункту 1–15, який хочеш змінити.",
        "",
        "<b>Список:</b>",
    ]
    for num, name, _ in EDIT_FIELDS:
        lines.append(f"{num}. {name}")
    return "\n".join(lines)


# =========================
# ROUTER
# =========================
router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_allowed(message.from_user.id):
        return

    txt = (
        "👋 Привіт!\n\n"
        "Команди:\n"
        "• /new — створити пропозицію\n"
        "• /stats — статистика (день/місяць/рік)\n"
        "• /export [all|day|month|year] — Excel\n\n"
        "Підказка: фото додавай у кінці, заверши кнопкою ✅ Готово або /done."
    )
    await message.answer(txt)


@router.message(Command("new"))
async def cmd_new(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return

    username = message.from_user.username or str(message.from_user.id)
    if username and not username.startswith("@"):
        username = f"@{username}"

    offer_id = create_offer(broker_username=username, broker_user_id=message.from_user.id)
    await state.set_data({"offer_id": offer_id})
    await state.set_state(OfferFSM.CATEGORY)

    await message.answer("Обери категорію:", reply_markup=kb_category())


# ---------- CATEGORY ----------
@router.callback_query(OfferFSM.CATEGORY, F.data.startswith("cat:"))
async def cb_category(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]

    category = call.data.split(":", 1)[1].strip()
    update_offer(offer_id, category=category)

    await state.set_state(OfferFSM.HOUSING_TYPE)
    await call.message.answer("Обери тип житла:", reply_markup=kb_housing_type())
    await call.answer()


# ---------- HOUSING TYPE ----------
@router.callback_query(OfferFSM.HOUSING_TYPE, F.data.startswith("ht:"))
async def cb_housing_type(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]

    ht = call.data.split(":", 1)[1].strip()
    update_offer(offer_id, housing_type=ht)

    await state.set_state(OfferFSM.STREET)
    await call.message.answer("📍 Напиши <b>вулицю</b> (або адресу коротко):")
    await call.answer()


@router.callback_query(OfferFSM.HOUSING_TYPE, F.data == "ht_other")
async def cb_housing_type_other(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(OfferFSM.HOUSING_TYPE_OTHER)
    await call.message.answer("🏠 Напиши свій варіант <b>типу житла</b>:")
    await call.answer()


@router.message(OfferFSM.HOUSING_TYPE_OTHER)
async def msg_housing_type_other(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]

    ht = (message.text or "").strip()
    if not ht:
        await message.answer("Напиши текстом тип житла.")
        return

    update_offer(offer_id, housing_type=ht)
    await state.set_state(OfferFSM.STREET)
    await message.answer("📍 Напиши <b>вулицю</b> (або адресу коротко):")


# ---------- TEXT STEPS ----------
async def _save_and_next_text(message: types.Message, state: FSMContext, field: str, next_state: State, prompt: str):
    data = await state.get_data()
    offer_id = data["offer_id"]
    val = (message.text or "").strip()
    update_offer(offer_id, **{field: val})
    await state.set_state(next_state)
    await message.answer(prompt)


@router.message(OfferFSM.STREET)
async def msg_street(message: types.Message, state: FSMContext):
    await _save_and_next_text(message, state, "street", OfferFSM.CITY, "🏙️ Напиши <b>місто</b>:")


@router.message(OfferFSM.CITY)
async def msg_city(message: types.Message, state: FSMContext):
    await _save_and_next_text(message, state, "city", OfferFSM.DISTRICT, "🗺️ Напиши <b>район</b>:")


@router.message(OfferFSM.DISTRICT)
async def msg_district(message: types.Message, state: FSMContext):
    await _save_and_next_text(message, state, "district", OfferFSM.ADVANTAGES, "✨ Напиши <b>переваги</b> (коротко):")


@router.message(OfferFSM.ADVANTAGES)
async def msg_advantages(message: types.Message, state: FSMContext):
    await _save_and_next_text(message, state, "advantages", OfferFSM.RENT, "💶 Напиши <b>оренду</b> (наприклад 350€):")


@router.message(OfferFSM.RENT)
async def msg_rent(message: types.Message, state: FSMContext):
    await _save_and_next_text(message, state, "rent", OfferFSM.DEPOSIT, "🔐 Напиши <b>депозит</b>:")


@router.message(OfferFSM.DEPOSIT)
async def msg_deposit(message: types.Message, state: FSMContext):
    await _save_and_next_text(message, state, "deposit", OfferFSM.COMMISSION, "🤝 Напиши <b>комісію</b>:")


@router.message(OfferFSM.COMMISSION)
async def msg_commission(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    update_offer(offer_id, commission=(message.text or "").strip())

    await state.set_state(OfferFSM.REGISTRATION)
    await message.answer("🪪 Напиши <b>прописка</b> / чи можлива реєстрація:")


@router.message(OfferFSM.REGISTRATION)
async def msg_registration(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    update_offer(offer_id, registration=(message.text or "").strip())

    await state.set_state(OfferFSM.PARKING)
    await message.answer(
        "🚗 Паркінг: обери кнопкою або <b>напиши текстом</b> (наприклад: 'підземний 50€')",
        reply_markup=kb_parking(),
    )


# Паркінг кнопкою
@router.callback_query(OfferFSM.PARKING, F.data.startswith("park:"))
async def cb_parking(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    parking = call.data.split(":", 1)[1].strip()
    update_offer(offer_id, parking=parking)

    await state.set_state(OfferFSM.MOVE_IN_FROM)
    await call.message.answer("📦 Напиши <b>заселення від</b> (наприклад 'вже' або дата):")
    await call.answer()


# Паркінг текстом
@router.message(OfferFSM.PARKING)
async def msg_parking_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    parking = (message.text or "").strip()
    if not parking:
        await message.answer("Напиши текстом паркінг або обери кнопкою.", reply_markup=kb_parking())
        return

    update_offer(offer_id, parking=parking)
    await state.set_state(OfferFSM.MOVE_IN_FROM)
    await message.answer("📦 Напиши <b>заселення від</b> (наприклад 'вже' або дата):")


@router.message(OfferFSM.MOVE_IN_FROM)
async def msg_move_in(message: types.Message, state: FSMContext):
    await _save_and_next_text(message, state, "move_in_from", OfferFSM.VIEWINGS_FROM, "👀 Напиши <b>огляди від</b>:")


@router.message(OfferFSM.VIEWINGS_FROM)
async def msg_viewings(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    update_offer(offer_id, viewings_from=(message.text or "").strip())

    await state.set_state(OfferFSM.KEYS_SOURCE)
    await message.answer("🔑 Напиши <b>джерело ключів</b>:")


@router.message(OfferFSM.KEYS_SOURCE)
async def msg_keys_source(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    update_offer(offer_id, keys_source=(message.text or "").strip())

    await state.set_state(OfferFSM.PHOTOS)
    await message.answer("📸 Надішли фото. Коли закінчиш — натисни ✅ Готово або /done.", reply_markup=kb_photos_done())


# ---------- PHOTOS ----------
@router.message(OfferFSM.PHOTOS, F.photo)
async def msg_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]

    file_id = message.photo[-1].file_id
    add_photo(offer_id, file_id)

    offer = get_offer(offer_id)
    try:
        photos = json.loads(offer["photos_json"] or "[]")
    except Exception:
        photos = []
    await message.answer(f"📸 Фото додано ({len(photos)}). Натисни ✅ Готово або /done.", reply_markup=kb_photos_done())


@router.message(OfferFSM.PHOTOS, Command("done"))
async def cmd_done_photos(message: types.Message, state: FSMContext):
    await finish_photos_and_preview(message, state)


@router.callback_query(OfferFSM.PHOTOS, F.data == "photos_done")
async def cb_done_photos(call: types.CallbackQuery, state: FSMContext):
    await finish_photos_and_preview(call.message, state)
    await call.answer()


@router.message(OfferFSM.PHOTOS)
async def msg_photos_other(message: types.Message, state: FSMContext):
    t = (message.text or "").strip().lower()
    if t in ("готово", "done"):
        await finish_photos_and_preview(message, state)
        return
    await message.answer("📸 Надішли фото або натисни ✅ Готово (/done).", reply_markup=kb_photos_done())


async def finish_photos_and_preview(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    offer = get_offer(offer_id)
    if not offer:
        await message.answer("❗️Пропозицію не знайдено.")
        await state.clear()
        return

    await state.set_state(OfferFSM.PREVIEW)

    try:
        photos = json.loads(offer["photos_json"] or "[]")
    except Exception:
        photos = []

    if photos:
        media = [types.InputMediaPhoto(media=p) for p in photos[:10]]
        await message.answer_media_group(media=media)

    await message.answer(offer_text(offer), reply_markup=kb_preview_actions())
    await message.answer("👉 Це фінальний вигляд. Обери дію:", reply_markup=kb_preview_actions())


# ---------- PREVIEW ACTIONS ----------
@router.callback_query(OfferFSM.PREVIEW, F.data == "cancel")
async def cb_cancel(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offer_id = data.get("offer_id")
    offer = get_offer(offer_id) if offer_id else None

    if offer and int(offer["is_published"] or 0) == 0:
        con = db_conn()
        cur = con.cursor()
        cur.execute("DELETE FROM status_events WHERE offer_id = ?;", (offer_id,))
        cur.execute("DELETE FROM offers WHERE id = ?;", (offer_id,))
        con.commit()
        con.close()

    await state.clear()
    await call.message.answer("❌ Скасовано.")
    await call.answer()


@router.callback_query(OfferFSM.PREVIEW, F.data == "edit")
async def cb_edit(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    offer = get_offer(offer_id)
    if not offer:
        await call.message.answer("❗️Пропозицію не знайдено.")
        await state.clear()
        await call.answer()
        return

    await state.set_state(OfferFSM.EDIT_CHOOSE)
    await call.message.answer(edit_list_text(int(offer["seq"])))
    await call.answer()


@router.callback_query(OfferFSM.PREVIEW, F.data == "pub")
async def cb_publish(call: types.CallbackQuery, state: FSMContext):
    if not GROUP_CHAT_ID_RAW:
        await call.message.answer("❗️Не задано GROUP_CHAT_ID / GROUP_ID в Railway (Variables).")
        await call.answer()
        return

    try:
        group_id = int(GROUP_CHAT_ID_RAW)
    except Exception:
        await call.message.answer("❗️GROUP_CHAT_ID має бути числом (наприклад -1001234567890).")
        await call.answer()
        return

    data = await state.get_data()
    offer_id = data["offer_id"]
    offer = get_offer(offer_id)
    if not offer:
        await call.message.answer("❗️Пропозицію не знайдено.")
        await state.clear()
        await call.answer()
        return

    if int(offer["is_published"] or 0) == 1:
        await call.message.answer("ℹ️ Уже опубліковано.")
        await call.answer()
        return

    try:
        photos = json.loads(offer["photos_json"] or "[]")
    except Exception:
        photos = []

    if photos:
        media = [types.InputMediaPhoto(media=p) for p in photos[:10]]
        await call.bot.send_media_group(chat_id=group_id, media=media)

    msg = await call.bot.send_message(
        chat_id=group_id,
        text=offer_text(offer),
        reply_markup=kb_status_buttons(offer_id),
    )

    update_offer(
        offer_id,
        is_published=1,
        published_chat_id=group_id,
        published_message_id=msg.message_id,
    )

    await call.message.answer(f"✅ Пропозицію #{int(offer['seq']):04d} опубліковано в групу.")
    await state.clear()
    await call.answer()


# ---------- EDIT FLOW ----------
@router.message(OfferFSM.EDIT_CHOOSE)
async def msg_edit_choose(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    offer = get_offer(offer_id)
    if not offer:
        await message.answer("❗️Пропозицію не знайдено.")
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Напиши номер пункту 1–15 (наприклад 2).")
        return

    num = int(text)
    field_map = {n: (name, key) for n, name, key in EDIT_FIELDS}
    if num not in field_map:
        await message.answer("Невірний номер. Напиши 1–15.")
        return

    name, key = field_map[num]
    await state.update_data({"edit_field_key": key, "edit_field_name": name})

    if key == "category":
        await state.set_state(OfferFSM.CATEGORY)
        await message.answer("Обери категорію:", reply_markup=kb_category())
        return

    if key == "housing_type":
        await state.set_state(OfferFSM.HOUSING_TYPE)
        await message.answer("Обери тип житла:", reply_markup=kb_housing_type())
        return

    if key == "parking":
        await state.set_state(OfferFSM.PARKING)
        await message.answer("🚗 Паркінг: обери кнопкою або напиши текстом.", reply_markup=kb_parking())
        return

    await state.set_state(OfferFSM.EDIT_VALUE)
    await message.answer(f"✏️ Впиши нове значення для <b>{esc(name)}</b>:")


@router.message(OfferFSM.EDIT_VALUE)
async def msg_edit_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    key = data.get("edit_field_key")

    offer = get_offer(offer_id)
    if not offer or not key:
        await message.answer("❗️Немає даних для редагування.")
        await state.clear()
        return

    val = (message.text or "").strip()

    if key == "broker_username":
        if val and not val.startswith("@"):
            val = f"@{val}"

    update_offer(offer_id, **{key: val})

    offer2 = get_offer(offer_id)
    await state.set_state(OfferFSM.PREVIEW)

    await message.answer("✅ Оновлено. Ось новий вигляд:")
    await message.answer(offer_text(offer2), reply_markup=kb_preview_actions())


# ---------- STATUS BUTTONS (GROUP) ----------
@router.callback_query(F.data.startswith("st:"))
async def cb_status(call: types.CallbackQuery):
    parts = call.data.split(":")
    if len(parts) != 3:
        await call.answer("Помилка", show_alert=False)
        return

    offer_id = int(parts[1])
    status = parts[2]

    if status not in STATUS:
        await call.answer("Невірний статус", show_alert=False)
        return

    if not is_allowed(call.from_user.id):
        await call.answer()
        return

    offer = get_offer(offer_id)
    if not offer:
        await call.answer("Пропозицію не знайдено", show_alert=False)
        return

    username = call.from_user.username or str(call.from_user.id)
    if username and not username.startswith("@"):
        username = f"@{username}"

    set_status(offer_id, status, username=username, user_id=call.from_user.id)

    offer2 = get_offer(offer_id)
    try:
        await call.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=offer_text(offer2),
            reply_markup=kb_status_buttons(offer_id),
        )
    except Exception:
        pass

    await call.answer("✅ Оновлено", show_alert=False)


# =========================
# STATS
# =========================
def _period_bounds(period: str) -> Tuple[datetime, datetime]:
    now = datetime.now(tz=APP_TZ)
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    if period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
        return start, end
    raise ValueError("Unknown period")


def stats_for_period(period: str) -> Dict[str, Any]:
    start, end = _period_bounds(period)
    start_iso = start.isoformat(timespec="seconds")
    end_iso = end.isoformat(timespec="seconds")

    con = db_conn()
    cur = con.cursor()

    cur.execute(
        """
        SELECT status, COUNT(*) as cnt
        FROM status_events
        WHERE at >= ? AND at < ?
        GROUP BY status;
        """,
        (start_iso, end_iso),
    )
    rows = cur.fetchall()
    total = {k: 0 for k in STATUS_ORDER}
    for r in rows:
        st = r["status"]
        if st in total:
            total[st] = int(r["cnt"])

    cur.execute(
        """
        SELECT username, status, COUNT(*) as cnt
        FROM status_events
        WHERE at >= ? AND at < ?
        GROUP BY username, status
        ORDER BY username ASC;
        """,
        (start_iso, end_iso),
    )
    rows2 = cur.fetchall()
    per_broker: Dict[str, Dict[str, int]] = {}
    for r in rows2:
        u = r["username"] or "—"
        st = r["status"]
        if st not in STATUS:
            continue
        per_broker.setdefault(u, {k: 0 for k in STATUS_ORDER})
        per_broker[u][st] = int(r["cnt"])

    con.close()

    label = {
        "day": start.strftime("%Y-%m-%d"),
        "month": start.strftime("%Y-%m"),
        "year": start.strftime("%Y"),
    }[period]

    return {"label": label, "total": total, "per_broker": per_broker}


def format_stats() -> str:
    day = stats_for_period("day")
    month = stats_for_period("month")
    year = stats_for_period("year")

    def block(title: str, d: Dict[str, Any]) -> str:
        t = d["total"]
        return (
            f"<b>{title} ({d['label']})</b>\n"
            f"{STATUS['unknown']}: {t['unknown']}\n"
            f"{STATUS['active']}: {t['active']}\n"
            f"{STATUS['reserve']}: {t['reserve']}\n"
            f"{STATUS['removed']}: {t['removed']}\n"
            f"{STATUS['closed']}: {t['closed']}\n"
        )

    def broker_block(title: str, d: Dict[str, Any]) -> str:
        lines = [f"🧑‍💼 <b>{title} — по маклерах ({d['label']})</b>"]
        if not d["per_broker"]:
            lines.append("— немає змін статусів")
            return "\n".join(lines)

        for broker, counts in d["per_broker"].items():
            lines.append(f"\n<b>{esc(broker)}</b>")
            lines.append(f"  {STATUS['unknown']}: {counts['unknown']}")
            lines.append(f"  {STATUS['active']}: {counts['active']}")
            lines.append(f"  {STATUS['reserve']}: {counts['reserve']}")
            lines.append(f"  {STATUS['removed']}: {counts['removed']}")
            lines.append(f"  {STATUS['closed']}: {counts['closed']}")
        return "\n".join(lines)

    parts = [
        "📊 <b>Статистика (зміни статусів)</b>\n",
        block("День", day),
        block("Місяць", month),
        block("Рік", year),
        "",
        broker_block("День", day),
        "",
        broker_block("Місяць", month),
        "",
        broker_block("Рік", year),
    ]
    return "\n".join(parts)


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer(format_stats())


# =========================
# EXPORT (EXCEL)
# =========================
def export_to_excel(filepath: str, period: str = "all") -> None:
    if Workbook is None:
        raise RuntimeError("openpyxl не встановлений")

    start_iso = None
    end_iso = None
    if period in ("day", "month", "year"):
        start_dt, end_dt = _period_bounds(period)
        start_iso = start_dt.isoformat(timespec="seconds")
        end_iso = end_dt.isoformat(timespec="seconds")

    con = db_conn()
    cur = con.cursor()

    if start_iso and end_iso:
        cur.execute(
            "SELECT * FROM offers WHERE created_at >= ? AND created_at < ? ORDER BY seq ASC;",
            (start_iso, end_iso),
        )
    else:
        cur.execute("SELECT * FROM offers ORDER BY seq ASC;")
    offers = cur.fetchall()

    if start_iso and end_iso:
        cur.execute(
            """
            SELECT se.*, o.seq AS offer_seq
            FROM status_events se
            LEFT JOIN offers o ON o.id = se.offer_id
            WHERE se.at >= ? AND se.at < ?
            ORDER BY se.at ASC;
            """,
            (start_iso, end_iso),
        )
    else:
        cur.execute(
            """
            SELECT se.*, o.seq AS offer_seq
            FROM status_events se
            LEFT JOIN offers o ON o.id = se.offer_id
            ORDER BY se.at ASC;
            """
        )
    events = cur.fetchall()
    con.close()

    wb = Workbook()

    ws = wb.active
    ws.title = "Offers"
    ws.append(
        [
            "SEQ",
            "CreatedAt",
            "Status",
            "Category",
            "HousingType",
            "Street",
            "City",
            "District",
            "Advantages",
            "Rent",
            "Deposit",
            "Commission",
            "Registration",
            "Parking",
            "MoveInFrom",
            "ViewingsFrom",
            "KeysSource",
            "Broker",
            "BrokerUserId",
            "PhotosCount",
            "PublishedChatId",
            "PublishedMessageId",
        ]
    )

    for r in offers:
        try:
            photos = json.loads(r["photos_json"] or "[]")
        except Exception:
            photos = []
        st = (r["current_status"] or "unknown").strip()
        ws.append(
            [
                r["seq"],
                r["created_at"],
                STATUS.get(st, st),
                r["category"],
                r["housing_type"],
                r["street"],
                r["city"],
                r["district"],
                r["advantages"],
                r["rent"],
                r["deposit"],
                r["commission"],
                r["registration"],
                r["parking"],
                r["move_in_from"],
                r["viewings_from"],
                r["keys_source"],
                r["broker_username"],
                r["broker_user_id"],
                len(photos),
                r["published_chat_id"],
                r["published_message_id"],
            ]
        )

    ws2 = wb.create_sheet("StatusEvents")
    ws2.append(["At", "OfferSEQ", "Status", "Username", "UserId"])
    for e in events:
        st = e["status"]
        ws2.append(
            [
                e["at"],
                e["offer_seq"],
                STATUS.get(st, st),
                e["username"],
                e["user_id"],
            ]
        )

    wb.save(filepath)


@router.message(Command("export"))
async def cmd_export(message: types.Message):
    if not is_allowed(message.from_user.id):
        return

    if Workbook is None:
        await message.answer("❗️Додай openpyxl в requirements.txt (openpyxl==3.1.5) і перезапусти деплой.")
        return

    args = (message.text or "").split(maxsplit=1)
    period = "all"
    if len(args) == 2:
        period = args[1].strip().lower()

    if period not in ("all", "day", "month", "year"):
        await message.answer("❗️Використання: /export [all|day|month|year]\nНаприклад: /export month")
        return

    ensure_dirs()
    ts = datetime.now(tz=APP_TZ).strftime("%Y-%m-%d_%H-%M")
    filename = f"orenda_export_{period}_{ts}.xlsx"
    filepath = os.path.join(DATA_DIR, filename)

    try:
        export_to_excel(filepath, period=period)
        doc = FSInputFile(filepath, filename=filename)
        await message.answer_document(doc, caption=f"📄 Excel експорт: <b>{period}</b>")
    finally:
        try:
            os.remove(filepath)
        except Exception:
            pass


# =========================
# MAIN
# =========================
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не заданий")

    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

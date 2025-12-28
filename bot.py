import asyncio
import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InputMediaPhoto,
    Message,
    BufferedInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# -------------------- Налаштування --------------------

import os

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
GROUP_CHAT_ID_RAW = (os.getenv("GROUP_CHAT_ID") or os.getenv("GROUP_ID") or "").strip()
DB_PATH = (os.getenv("DB_PATH") or "data/bot.db").strip()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("real_estate_bot")

router = Router()

STATUS_ACTIVE = "ACTIVE"          # 🟢 Актуально
STATUS_RESERVED = "RESERVED"      # 🟡 Резерв
STATUS_REMOVED = "REMOVED"        # ⚫ Знято
STATUS_DEAL_CLOSED = "DEAL_CLOSED"  # ✅ Угода закрита
STATUS_DRAFT = "DRAFT"            # Чернетка (не показуємо в статистиці)

STATUS_LABEL = {
    STATUS_ACTIVE: "🟢 Актуально",
    STATUS_RESERVED: "🟡 Резерв",
    STATUS_REMOVED: "⚫ Знято",
    STATUS_DEAL_CLOSED: "✅ Угода закрита",
    STATUS_DRAFT: "📝 Чернетка",
}

FIELDS = [
    ("category", "🏷️ Категорія"),
    ("living", "🏠 Тип житла"),
    ("street", "📍 Вулиця"),
    ("city", "🏙️ Місто"),
    ("district", "🗺️ Район"),
    ("advantages", "✨ Переваги"),
    ("rent", "💶 Оренда"),
    ("deposit", "🔐 Депозит"),
    ("commission", "🤝 Комісія"),
    ("parking", "🚗 Паркінг"),
    ("move_in", "📦 Заселення від"),
    ("viewings", "👀 Огляди від"),
    ("broker", "🧑‍💼 Маклер"),
]


def require_env(name: str, value: str) -> str:
    if not value:
        raise RuntimeError(f"{name} не заданий (Railway → Variables)")
    return value


def parse_group_chat_id() -> int:
    raw = require_env("GROUP_CHAT_ID", GROUP_CHAT_ID_RAW)
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError("GROUP_CHAT_ID має бути числом, наприклад -1001234567890")


def offer_num(offer_id: int) -> str:
    return f"#{offer_id:04d}"


def username_or_name(msg_or_cb) -> str:
    u = getattr(msg_or_cb.from_user, "username", None)
    if u:
        return f"@{u}"
    return getattr(msg_or_cb.from_user, "full_name", "—") or "—"


# -------------------- FSM --------------------

class CreateOffer(StatesGroup):
    category = State()
    living = State()
    street = State()
    city = State()
    district = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in = State()
    viewings = State()
    broker = State()
    photos = State()
    preview = State()
    edit_choose_field = State()
    edit_new_value = State()


# -------------------- DB --------------------

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) if os.path.dirname(DB_PATH) else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            created_by_id INTEGER NOT NULL,
            created_by_username TEXT,
            status TEXT NOT NULL,
            data_json TEXT NOT NULL,
            group_chat_id INTEGER,
            group_message_id INTEGER
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS offer_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            pos INTEGER NOT NULL,
            FOREIGN KEY(offer_id) REFERENCES offers(id)
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            by_id INTEGER NOT NULL,
            by_username TEXT,
            old_status TEXT,
            new_status TEXT NOT NULL,
            FOREIGN KEY(offer_id) REFERENCES offers(id)
        )
        """)
        await db.commit()


async def create_offer_row(user_id: int, username: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO offers(created_at, created_by_id, created_by_username, status, data_json) VALUES(?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), user_id, username, STATUS_DRAFT, "{}"),
        )
        await db.commit()
        return cur.lastrowid


async def update_offer_data(offer_id: int, data: Dict[str, Any]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE offers SET data_json=? WHERE id=?",
                         (json.dumps(data, ensure_ascii=False), offer_id))
        await db.commit()


async def get_offer(offer_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM offers WHERE id=?", (offer_id,))
        row = await cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["data"] = json.loads(d["data_json"] or "{}")
        return d


async def add_photo(offer_id: int, file_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COALESCE(MAX(pos), 0) FROM offer_photos WHERE offer_id=?", (offer_id,))
        maxpos = (await cur.fetchone())[0] or 0
        await db.execute(
            "INSERT INTO offer_photos(offer_id, file_id, pos) VALUES (?,?,?)",
            (offer_id, file_id, maxpos + 1),
        )
        await db.commit()


async def get_photos(offer_id: int) -> List[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT file_id FROM offer_photos WHERE offer_id=? ORDER BY pos ASC",
            (offer_id,),
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def set_group_message(offer_id: int, chat_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE offers SET group_chat_id=?, group_message_id=? WHERE id=?",
            (chat_id, message_id, offer_id),
        )
        await db.commit()


async def set_offer_status(offer_id: int, new_status: str, by_id: int, by_username: str):
    offer = await get_offer(offer_id)
    if not offer:
        return
    old = offer["status"]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE offers SET status=? WHERE id=?", (new_status, offer_id))
        await db.execute(
            "INSERT INTO status_log(offer_id, ts, by_id, by_username, old_status, new_status) VALUES (?,?,?,?,?,?)",
            (offer_id, datetime.now(timezone.utc).isoformat(), by_id, by_username, old, new_status),
        )
        await db.commit()


async def set_offer_published_active_if_draft(offer_id: int):
    offer = await get_offer(offer_id)
    if not offer:
        return
    if offer["status"] == STATUS_DRAFT:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE offers SET status=? WHERE id=?", (STATUS_ACTIVE, offer_id))
            await db.commit()


async def stats_created_by_status(start_iso: str, end_iso: str) -> Dict[str, int]:
    # Скільки створено пропозицій у періоді (по поточному статусу), без DRAFT
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT status, COUNT(*)
            FROM offers
            WHERE created_at >= ? AND created_at < ? AND status != ?
            GROUP BY status
            """,
            (start_iso, end_iso, STATUS_DRAFT),
        )
        rows = await cur.fetchall()
        out = {STATUS_ACTIVE: 0, STATUS_RESERVED: 0, STATUS_REMOVED: 0, STATUS_DEAL_CLOSED: 0}
        for st, c in rows:
            out[st] = c
        return out


async def stats_broker_status_changes(start_iso: str, end_iso: str) -> Dict[str, Dict[str, int]]:
    # Хто скільки разів ставив статуси (з логів)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT COALESCE(by_username,'—') AS who, new_status, COUNT(*)
            FROM status_log
            WHERE ts >= ? AND ts < ?
            GROUP BY who, new_status
            ORDER BY who
            """,
            (start_iso, end_iso),
        )
        rows = await cur.fetchall()
        result: Dict[str, Dict[str, int]] = {}
        for who, st, c in rows:
            result.setdefault(who, {})
            result[who][st] = c
        return result


async def export_offers_rows() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM offers WHERE status != ? ORDER BY id ASC", (STATUS_DRAFT,))
        rows = await cur.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["data"] = json.loads(d["data_json"] or "{}")
            out.append(d)
        return out


# -------------------- Keyboards --------------------

def kb_category() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 Оренда", callback_data="cat:Оренда"),
            InlineKeyboardButton(text="🏡 Продаж", callback_data="cat:Продаж"),
        ],
    ])


def kb_living() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛏 Кімната", callback_data="liv:Кімната"),
            InlineKeyboardButton(text="🏢 Студія", callback_data="liv:Студія"),
        ],
        [
            InlineKeyboardButton(text="🏠 1к", callback_data="liv:1к"),
            InlineKeyboardButton(text="🏠 2к", callback_data="liv:2к"),
        ],
        [
            InlineKeyboardButton(text="🏠 3к", callback_data="liv:3к"),
            InlineKeyboardButton(text="🏠 4к", callback_data="liv:4к"),
        ],
        [
            InlineKeyboardButton(text="✍️ Інше (написати)", callback_data="liv:OTHER"),
        ],
    ])


def kb_photos_done() -> InlineKeyboardMarkup:
    # Кнопка "на фоні" (Inline під повідомленням)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="photos:done")]
    ])


def kb_preview_actions(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Публікувати", callback_data=f"prev:pub:{offer_id}"),
            InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"prev:edit:{offer_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Скасувати", callback_data=f"prev:cancel:{offer_id}"),
        ]
    ])


def kb_status(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Актуально", callback_data=f"st:{offer_id}:{STATUS_ACTIVE}"),
            InlineKeyboardButton(text="🟡 Резерв", callback_data=f"st:{offer_id}:{STATUS_RESERVED}"),
        ],
        [
            InlineKeyboardButton(text="⚫ Знято", callback_data=f"st:{offer_id}:{STATUS_REMOVED}"),
            InlineKeyboardButton(text="✅ Угода закрита", callback_data=f"st:{offer_id}:{STATUS_DEAL_CLOSED}"),
        ]
    ])


# -------------------- Helpers: text & preview --------------------

def format_offer_text(offer_id: int, offer: Dict[str, Any]) -> str:
    data = offer["data"]
    status = offer["status"]
    lines = [
        f"🏡 <b>ПРОПОЗИЦІЯ {offer_num(offer_id)}</b>",
        f"📊 <b>Статус:</b> {STATUS_LABEL.get(status, status)}",
        "",
    ]
    for key, title in FIELDS:
        val = (data.get(key) or "").strip()
        if not val:
            val = "—"
        if key in ("rent", "deposit", "commission") and val != "—":
            if "€" not in val:
                val = f"{val}€"
        lines.append(f"{title}: {val}")
    return "\n".join(lines)


async def send_offer_album_with_caption(bot: Bot, chat_id: int, offer_id: int, caption: str, photos: List[str]):
    if not photos:
        await bot.send_message(chat_id, caption)
        return

    media = []
    for i, fid in enumerate(photos[:10]):  # TG: до 10 в альбомі
        if i == 0:
            media.append(InputMediaPhoto(media=fid, caption=caption, parse_mode="HTML"))
        else:
            media.append(InputMediaPhoto(media=fid))
    await bot.send_media_group(chat_id, media=media)


def edit_fields_text(offer_id: int) -> str:
    lines = [
        f"✏️ <b>Редагування {offer_num(offer_id)}</b>",
        "Напиши номер пункту 1–13, який хочеш змінити.",
        "Наприклад: <b>7</b> (Оренда)",
        "",
        "<b>Список:</b>",
    ]
    for i, (_, title) in enumerate(FIELDS, start=1):
        lines.append(f"{i}. {title}")
    return "\n".join(lines)


def period_ranges(now_utc: datetime):
    day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    month_start = day_start.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)

    year_start = day_start.replace(month=1, day=1)
    year_end = year_start.replace(year=year_start.year + 1)

    return (day_start, day_end), (month_start, month_end), (year_start, year_end)


def fmt_counts(title: str, counts: Dict[str, int]) -> str:
    return (
        f"<b>{title}</b>\n"
        f"🟢 Актуально: <b>{counts.get(STATUS_ACTIVE, 0)}</b>\n"
        f"🟡 Резерв: <b>{counts.get(STATUS_RESERVED, 0)}</b>\n"
        f"⚫ Знято: <b>{counts.get(STATUS_REMOVED, 0)}</b>\n"
        f"✅ Угода закрита: <b>{counts.get(STATUS_DEAL_CLOSED, 0)}</b>\n"
    )


def fmt_brokers(title: str, data: Dict[str, Dict[str, int]]) -> str:
    lines = [f"<b>{title}</b>"]
    if not data:
        lines.append("— немає змін статусів")
        return "\n".join(lines)

    for who, m in data.items():
        lines.append(
            f"👤 <b>{who}</b>: "
            f"🟢{m.get(STATUS_ACTIVE, 0)}  "
            f"🟡{m.get(STATUS_RESERVED, 0)}  "
            f"⚫{m.get(STATUS_REMOVED, 0)}  "
            f"✅{m.get(STATUS_DEAL_CLOSED, 0)}"
        )
    return "\n".join(lines)


# -------------------- Commands --------------------

@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "✅ Бот працює.\n\n"
        "Команди:\n"
        "➕ /create — створити пропозицію\n"
        "📊 /stats — статистика\n"
        "📤 /export — експорт CSV\n"
        "❌ /cancel — скасувати"
    )


@router.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("✅ Скасовано.")


@router.message(Command("create"))
async def cmd_create(m: Message, state: FSMContext):
    offer_id = await create_offer_row(m.from_user.id, username_or_name(m))
    await state.clear()
    await state.update_data(offer_id=offer_id, data={})
    await state.set_state(CreateOffer.category)
    await m.answer(f"🆕 Створюємо пропозицію {offer_num(offer_id)}.\n\n1) Обери категорію:", reply_markup=kb_category())


# -------------------- Steps --------------------

async def save_field(state: FSMContext, key: str, value: str):
    st = await state.get_data()
    data = st.get("data", {})
    data[key] = (value or "").strip()
    await state.update_data(data=data)
    offer_id = st.get("offer_id")
    if offer_id:
        await update_offer_data(offer_id, data)


@router.callback_query(CreateOffer.category, F.data.startswith("cat:"))
async def step_category_cb(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    cat = cb.data.split(":", 1)[1]
    await save_field(state, "category", cat)
    await state.set_state(CreateOffer.living)
    await cb.message.answer("2) Обери тип житла або натисни «Інше (написати)»:", reply_markup=kb_living())


@router.callback_query(CreateOffer.living, F.data.startswith("liv:"))
async def step_living_cb(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    val = cb.data.split(":", 1)[1]
    if val == "OTHER":
        await cb.message.answer("✍️ Напиши свій варіант типу житла:")
        return
    await save_field(state, "living", val)
    await state.set_state(CreateOffer.street)
    await cb.message.answer("3) 📍 Вулиця:")


@router.message(CreateOffer.living)
async def step_living_text(m: Message, state: FSMContext):
    await save_field(state, "living", m.text)
    await state.set_state(CreateOffer.street)
    await m.answer("3) 📍 Вулиця:")


@router.message(CreateOffer.street)
async def step_street(m: Message, state: FSMContext):
    await save_field(state, "street", m.text)
    await state.set_state(CreateOffer.city)
    await m.answer("4) 🏙️ Місто:")


@router.message(CreateOffer.city)
async def step_city(m: Message, state: FSMContext):
    await save_field(state, "city", m.text)
    await state.set_state(CreateOffer.district)
    await m.answer("5) 🗺️ Район:")


@router.message(CreateOffer.district)
async def step_district(m: Message, state: FSMContext):
    await save_field(state, "district", m.text)
    await state.set_state(CreateOffer.advantages)
    await m.answer("6) ✨ Переваги:")


@router.message(CreateOffer.advantages)
async def step_adv(m: Message, state: FSMContext):
    await save_field(state, "advantages", m.text)
    await state.set_state(CreateOffer.rent)
    await m.answer("7) 💶 Оренда (сума або текст):")


@router.message(CreateOffer.rent)
async def step_rent(m: Message, state: FSMContext):
    await save_field(state, "rent", m.text)
    await state.set_state(CreateOffer.deposit)
    await m.answer("8) 🔐 Депозит (сума або «—»):")


@router.message(CreateOffer.deposit)
async def step_deposit(m: Message, state: FSMContext):
    await save_field(state, "deposit", m.text)
    await state.set_state(CreateOffer.commission)
    await m.answer("9) 🤝 Комісія (сума або «—»):")


@router.message(CreateOffer.commission)
async def step_commission(m: Message, state: FSMContext):
    await save_field(state, "commission", m.text)
    await state.set_state(CreateOffer.parking)
    await m.answer("10) 🚗 Паркінг:")


@router.message(CreateOffer.parking)
async def step_parking(m: Message, state: FSMContext):
    await save_field(state, "parking", m.text)
    await state.set_state(CreateOffer.move_in)
    await m.answer("11) 📦 Заселення від:")


@router.message(CreateOffer.move_in)
async def step_move_in(m: Message, state: FSMContext):
    await save_field(state, "move_in", m.text)
    await state.set_state(CreateOffer.viewings)
    await m.answer("12) 👀 Огляди від:")


@router.message(CreateOffer.viewings)
async def step_viewings(m: Message, state: FSMContext):
    await save_field(state, "viewings", m.text)
    await state.set_state(CreateOffer.broker)
    await m.answer("13) 🧑‍💼 Маклер (нік):")


@router.message(CreateOffer.broker)
async def step_broker(m: Message, state: FSMContext):
    await save_field(state, "broker", m.text)
    await state.set_state(CreateOffer.photos)
    await m.answer(
        "📷 Надсилай фото.\n"
        "Коли закінчиш — натисни «✅ Готово» або напиши /done чи «готово».",
        reply_markup=kb_photos_done()
    )


# -------------------- Photos --------------------

@router.message(CreateOffer.photos, F.photo)
async def photo_add_step(m: Message, state: FSMContext):
    st = await state.get_data()
    offer_id = st.get("offer_id")
    if not offer_id:
        await m.answer("Помилка: немає ID пропозиції. Зроби /create заново.")
        return
    file_id = m.photo[-1].file_id
    await add_photo(offer_id, file_id)
    photos = await get_photos(offer_id)
    await m.answer(f"📸 Фото додано ({len(photos)}).", reply_markup=kb_photos_done())


@router.callback_query(CreateOffer.photos, F.data == "photos:done")
async def photos_done_cb(cb: CallbackQuery, state: FSMContext, bot: Bot):
    await cb.answer()
    await finalize_preview(cb.message, state, bot)


@router.message(CreateOffer.photos, F.text)
async def photos_text(m: Message, state: FSMContext, bot: Bot):
    t = (m.text or "").strip().lower()
    if t in {"/done", "done", "готово", "✅ готово"}:
        await finalize_preview(m, state, bot)
        return
    await m.answer("Надішли фото або натисни «✅ Готово» / напиши /done.", reply_markup=kb_photos_done())


async def finalize_preview(m: Message, state: FSMContext, bot: Bot):
    st = await state.get_data()
    offer_id = st.get("offer_id")
    if not offer_id:
        await m.answer("Помилка: немає ID. Зроби /create заново.")
        return

    offer = await get_offer(offer_id)
    if not offer:
        await m.answer("Помилка: пропозицію не знайдено.")
        return

    photos = await get_photos(offer_id)
    caption = format_offer_text(offer_id, offer)

    await m.answer("👇 <b>Превʼю пропозиції (перед публікацією)</b>")
    await send_offer_album_with_caption(bot, m.chat.id, offer_id, caption, photos)
    await m.answer("Вибери дію:", reply_markup=kb_preview_actions(offer_id))

    await state.set_state(CreateOffer.preview)


# -------------------- Preview actions --------------------

@router.callback_query(CreateOffer.preview, F.data.startswith("prev:cancel:"))
async def prev_cancel(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await cb.message.answer("✅ Скасовано. /create — щоб почати заново.")


@router.callback_query(CreateOffer.preview, F.data.startswith("prev:edit:"))
async def prev_edit(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    offer_id = int(cb.data.split(":")[2])
    await state.update_data(edit_offer_id=offer_id)
    await state.set_state(CreateOffer.edit_choose_field)
    await cb.message.answer(edit_fields_text(offer_id))


@router.callback_query(CreateOffer.preview, F.data.startswith("prev:pub:"))
async def prev_publish(cb: CallbackQuery, state: FSMContext, bot: Bot):
    await cb.answer()
    offer_id = int(cb.data.split(":")[2])

    offer = await get_offer(offer_id)
    if not offer:
        await cb.message.answer("Не знайдено пропозицію.")
        return

    group_id = parse_group_chat_id()
    await set_offer_published_active_if_draft(offer_id)
    offer = await get_offer(offer_id)  # оновили статус
    photos = await get_photos(offer_id)

    # 1) Альбом в групу
    caption = format_offer_text(offer_id, offer)
    await send_offer_album_with_caption(bot, group_id, offer_id, caption, photos)

    # 2) Окреме керуюче повідомлення з кнопками статусів (повний текст, щоб було зрозуміло)
    control_text = caption
    control_msg = await bot.send_message(group_id, control_text, reply_markup=kb_status(offer_id))
    await set_group_message(offer_id, group_id, control_msg.message_id)

    await cb.message.answer(f"✅ Опубліковано в групу: {offer_num(offer_id)}")
    await state.clear()


# -------------------- Editing --------------------

@router.message(CreateOffer.edit_choose_field)
async def edit_choose(m: Message, state: FSMContext):
    st = await state.get_data()
    offer_id = st.get("edit_offer_id")
    if not offer_id:
        await m.answer("Немає активного редагування. Натисни «Редагувати» в превʼю.")
        return

    try:
        idx = int((m.text or "").strip())
    except Exception:
        await m.answer("Напиши номер пункту 1–13.")
        return

    if not (1 <= idx <= len(FIELDS)):
        await m.answer("Номер має бути в межах 1–13.")
        return

    key, title = FIELDS[idx - 1]
    await state.update_data(edit_field_key=key, edit_field_title=title)
    await state.set_state(CreateOffer.edit_new_value)
    await m.answer(f"Введи нове значення для: <b>{title}</b>")


@router.message(CreateOffer.edit_new_value)
async def edit_new_value(m: Message, state: FSMContext, bot: Bot):
    st = await state.get_data()
    offer_id = st.get("edit_offer_id")
    key = st.get("edit_field_key")

    if not offer_id or not key:
        await m.answer("Помилка редагування. Спробуй ще раз.")
        await state.set_state(CreateOffer.preview)
        return

    offer = await get_offer(offer_id)
    if not offer:
        await m.answer("Не знайдено пропозицію.")
        return

    data = offer["data"]
    data[key] = (m.text or "").strip()
    await update_offer_data(offer_id, data)

    # показуємо превʼю знову
    await state.set_state(CreateOffer.preview)
    photos = await get_photos(offer_id)
    offer = await get_offer(offer_id)
    caption = format_offer_text(offer_id, offer)

    await m.answer("✅ Оновлено. Ось нове превʼю:")
    await send_offer_album_with_caption(bot, m.chat.id, offer_id, caption, photos)
    await m.answer("Вибери дію:", reply_markup=kb_preview_actions(offer_id))


# -------------------- Status buttons in group --------------------

@router.callback_query(F.data.startswith("st:"))
async def status_set(cb: CallbackQuery, bot: Bot):
    # st:{offer_id}:{status}
    await cb.answer()
    try:
        _, offer_id_str, new_status = cb.data.split(":")
        offer_id = int(offer_id_str)
    except Exception:
        return

    offer = await get_offer(offer_id)
    if not offer:
        return

    await set_offer_status(offer_id, new_status, cb.from_user.id, username_or_name(cb))
    updated = await get_offer(offer_id)
    if not updated:
        return

    # редагуємо ТЕ саме повідомлення (не видаляємо) — тому нічого не “зникає”
    new_text = format_offer_text(offer_id, updated)
    try:
        await cb.message.edit_text(new_text, reply_markup=kb_status(offer_id))
    except Exception:
        # якщо не можна редагувати — дублюємо новим
        await bot.send_message(cb.message.chat.id, new_text, reply_markup=kb_status(offer_id))


# -------------------- Stats --------------------

@router.message(Command("stats"))
async def cmd_stats(m: Message):
    now = datetime.now(timezone.utc)
    (d1, d2), (m1, m2), (y1, y2) = period_ranges(now)

    day_counts = await stats_created_by_status(d1.isoformat(), d2.isoformat())
    month_counts = await stats_created_by_status(m1.isoformat(), m2.isoformat())
    year_counts = await stats_created_by_status(y1.isoformat(), y2.isoformat())

    day_b = await stats_broker_status_changes(d1.isoformat(), d2.isoformat())
    month_b = await stats_broker_status_changes(m1.isoformat(), m2.isoformat())
    year_b = await stats_broker_status_changes(y1.isoformat(), y2.isoformat())

    text = (
        "📊 <b>Статистика</b>\n\n"
        "📌 <b>Створено пропозицій за період (по поточному статусу)</b>\n\n"
        + fmt_counts(f"День ({d1.date()})", day_counts) + "\n"
        + fmt_counts(f"Місяць ({m1.strftime('%Y-%m')})", month_counts) + "\n"
        + fmt_counts(f"Рік ({y1.year})", year_counts) + "\n"
        + "\n"
        "🧾 <b>Хто скільки ставив статусів (з логів натискань)</b>\n\n"
        + fmt_brokers(f"День ({d1.date()})", day_b) + "\n\n"
        + fmt_brokers(f"Місяць ({m1.strftime('%Y-%m')})", month_b) + "\n\n"
        + fmt_brokers(f"Рік ({y1.year})", year_b)
    )
    await m.answer(text)


# -------------------- Export CSV --------------------

@router.message(Command("export"))
async def cmd_export(m: Message):
    rows = await export_offers_rows()
    if not rows:
        await m.answer("Немає даних для експорту.")
        return

    output = io.StringIO()
    writer = csv.writer(output)

    # header
    writer.writerow([
        "id", "created_at", "created_by", "status",
        "category", "living", "street", "city", "district",
        "advantages", "rent", "deposit", "commission",
        "parking", "move_in", "viewings", "broker"
    ])

    for r in rows:
        d = r["data"]
        writer.writerow([
            r["id"],
            r["created_at"],
            r.get("created_by_username") or r["created_by_id"],
            r["status"],
            d.get("category", ""),
            d.get("living", ""),
            d.get("street", ""),
            d.get("city", ""),
            d.get("district", ""),
            d.get("advantages", ""),
            d.get("rent", ""),
            d.get("deposit", ""),
            d.get("commission", ""),
            d.get("parking", ""),
            d.get("move_in", ""),
            d.get("viewings", ""),
            d.get("broker", ""),
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")  # Excel нормально читає укр
    file = BufferedInputFile(csv_bytes, filename="offers_export.csv")
    await m.answer_document(file, caption="📄 Експорт CSV (відкривається в Excel/Google Sheets)")


# -------------------- Run --------------------

async def main():
    require_env("BOT_TOKEN", BOT_TOKEN)
    require_env("GROUP_CHAT_ID", GROUP_CHAT_ID_RAW)

    await init_db()

    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

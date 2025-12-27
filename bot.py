import asyncio
import datetime as dt
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

# ===================== ENV / CONFIG =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID_RAW = os.getenv("GROUP_CHAT_ID")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не заданий у Variables (Railway).")
if not GROUP_CHAT_ID_RAW:
    raise RuntimeError("GROUP_CHAT_ID не заданий у Variables (Railway).")

GROUP_CHAT_ID = int(GROUP_CHAT_ID_RAW)

ADMIN_IDS: set[int] = set()
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.add(int(x))

DB_PATH = os.getenv("DB_PATH", "data/bot.db")  # можна не задавати
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ===================== DB =====================
def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db() -> None:
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            category TEXT,
            property_type TEXT,
            street TEXT,
            city TEXT,
            district TEXT,
            advantages TEXT,
            rent TEXT,
            deposit TEXT,
            commission TEXT,
            parking TEXT,
            move_in TEXT,
            viewing TEXT,
            broker TEXT,
            photos_json TEXT NOT NULL,
            author_id INTEGER NOT NULL,
            author_username TEXT,
            group_album_first_msg_id INTEGER,
            group_control_msg_id INTEGER
        )
        """
    )
    con.commit()
    con.close()

def create_offer(author_id: int, author_username: str) -> int:
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO offers (created_at, status, photos_json, author_id, author_username)
        VALUES (?, ?, ?, ?, ?)
        """,
        (dt.datetime.now(dt.timezone.utc).isoformat(), "🟢 Актуально", "[]", author_id, author_username),
    )
    offer_id = int(cur.lastrowid)
    con.commit()
    con.close()
    return offer_id

def update_offer_fields(offer_id: int, fields: Dict[str, Any]) -> None:
    if not fields:
        return
    con = db()
    cur = con.cursor()
    cols = ", ".join([f"{k}=?" for k in fields.keys()])
    vals = list(fields.values())
    vals.append(offer_id)
    cur.execute(f"UPDATE offers SET {cols} WHERE id=?", vals)
    con.commit()
    con.close()

def get_offer(offer_id: int) -> Optional[Dict[str, Any]]:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM offers WHERE id=?", (offer_id,))
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None

def set_offer_status(offer_id: int, status_text: str) -> None:
    update_offer_fields(offer_id, {"status": status_text})

def set_offer_photos(offer_id: int, photo_ids: List[str]) -> None:
    update_offer_fields(offer_id, {"photos_json": json.dumps(photo_ids, ensure_ascii=False)})

def set_offer_group_msgs(offer_id: int, album_first_id: int, control_msg_id: int) -> None:
    update_offer_fields(
        offer_id,
        {"group_album_first_msg_id": album_first_id, "group_control_msg_id": control_msg_id},
    )

# ===================== STATES / FLOW =====================
class OfferFSM(StatesGroup):
    category = State()
    property_type = State()
    street = State()
    city = State()
    district = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in = State()
    viewing = State()
    broker = State()
    photos = State()
    review = State()
    edit_value = State()

FIELDS_ORDER: List[Tuple[str, str, str]] = [
    ("category", "Категорія", "2) Категорія: Оренда або Продажа"),
    ("property_type", "Проживання", "3) Проживання: ліжко / кімната / студія / 1к / 2к / 3к / 4к / інше"),
    ("street", "Вулиця", "4) Вулиця: напиши (наприклад: вул. Шевченка 10)"),
    ("city", "Місто", "5) Місто: напиши"),
    ("district", "Район", "6) Район: напиши"),
    ("advantages", "Переваги", "7) Переваги житла: напиши"),
    ("rent", "Оренда", "8) Оренда: напиши суму"),
    ("deposit", "Депозит", "9) Депозит: напиши суму"),
    ("commission", "Комісія", "10) Комісія: напиши суму"),
    ("parking", "Паркінг", "11) Паркінг: напиши"),
    ("move_in", "Заселення від", "12) Заселення від: напиши"),
    ("viewing", "Огляди від", "13) Огляди від: напиши"),
    ("broker", "Маклер", "14) Маклер: напиши нік (наприклад: @nickname)"),
]

PROPERTY_TYPES = [
    "Ліжко",
    "Кімната",
    "Студія",
    "1к квартира",
    "2к квартира",
    "3к квартира",
    "4к квартира",
    "Інше (напишу свій варіант)",
]

def offer_num(offer_id: int) -> str:
    return f"{offer_id:04d}"

def normalize_text(s: str) -> str:
    return (s or "").strip()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def can_manage_offer(user_id: int, offer: Dict[str, Any]) -> bool:
    return is_admin(user_id) or int(offer["author_id"]) == int(user_id)

def status_kb(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Актуально", callback_data=f"st:active:{offer_id}"),
            InlineKeyboardButton(text="🟡 Резерв", callback_data=f"st:reserve:{offer_id}"),
            InlineKeyboardButton(text="🔴 Неактуально", callback_data=f"st:inactive:{offer_id}"),
        ]
    ])

def build_offer_text(offer: Dict[str, Any], with_emoji: bool = True) -> str:
    # Емодзі + нумерація пунктів
    emoji = {
        "category": "📌",
        "property_type": "🏠",
        "street": "📍",
        "city": "🏙️",
        "district": "🗺️",
        "advantages": "✨",
        "rent": "💶",
        "deposit": "🔒",
        "commission": "🧾",
        "parking": "🅿️",
        "move_in": "📅",
        "viewing": "👀",
        "broker": "👤",
    }
    lines = []
    lines.append(f"🏠 **ПРОПОЗИЦІЯ #{offer_num(int(offer['id']))}**")
    lines.append(f"📊 **Статус:** {offer.get('status','')}")
    lines.append("")

    idx = 2
    for key, title, _prompt in FIELDS_ORDER:
        val = offer.get(key) or "—"
        em = emoji.get(key, "•") if with_emoji else "•"
        lines.append(f"{idx}. {em} **{title}:** {val}")
        idx += 1

    created_at = offer.get("created_at")
    if created_at:
        lines.append("")
        lines.append(f"🕒 **Дата створення:** {created_at.split('T')[0]}")
    return "\n".join(lines)

def review_instructions() -> str:
    return (
        "\n\n✅ Якщо все вірно — напиши: **ПУБЛІКУВАТИ**\n"
        "✏️ Щоб змінити пункт — напиши: **ЗМІНИТИ 5** (будь-який номер 2–14)\n"
        "❌ Скасувати — напиши: **СКАСУВАТИ**"
    )

def parse_edit_cmd(text: str) -> Optional[int]:
    m = re.match(r"^\s*змінити\s+(\d+)\s*$", text.strip().lower())
    if not m:
        return None
    return int(m.group(1))

def field_by_number(n: int) -> Optional[str]:
    # 2..14 відповідає FIELDS_ORDER[0..12]
    if n < 2 or n > 14:
        return None
    return FIELDS_ORDER[n - 2][0]

def prompt_for_field(field_key: str) -> str:
    for k, _title, prompt in FIELDS_ORDER:
        if k == field_key:
            return prompt
    return "Напиши значення:"

# ===================== COMMANDS =====================
@dp.message(Command("start"))
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "👋 Вітаю! Я бот для створення пропозицій нерухомості.\n\n"
        "Щоб почати — напиши команду: /new\n"
        "Або просто напиши текст: **Зробити пропозицію**"
    )

@dp.message(Command("new"))
async def cmd_new(msg: Message, state: FSMContext):
    await state.clear()
    author_username = msg.from_user.username or "без_ніка"
    oid = create_offer(msg.from_user.id, author_username)
    await state.update_data(offer_id=oid, photos=[])
    await state.set_state(OfferFSM.category)
    await msg.answer("1) Натиснути кнопку «Зробити пропозицію» ✅ (вже зроблено)\n\n2) Категорія: Оренда або Продажа")

@dp.message(F.text.lower() == "зробити пропозицію")
async def text_new(msg: Message, state: FSMContext):
    await cmd_new(msg, state)

# ===================== STEP HANDLERS =====================
async def save_and_next(msg: Message, state: FSMContext, field_key: str, next_state: State):
    oid = (await state.get_data()).get("offer_id")
    if not oid:
        await msg.answer("❌ Немає активної пропозиції. Напиши /new")
        return
    val = normalize_text(msg.text)
    update_offer_fields(int(oid), {field_key: val})
    await state.set_state(next_state)

@dp.message(OfferFSM.category)
async def s_category(msg: Message, state: FSMContext):
    val = normalize_text(msg.text).lower()
    if val not in ("оренда", "продажа", "продаж", "продажа/продаж"):
        await msg.answer("Напиши **Оренда** або **Продажа**")
        return
    val_norm = "Оренда" if val.startswith("орен") else "Продажа"
    oid = (await state.get_data()).get("offer_id")
    update_offer_fields(int(oid), {"category": val_norm})
    await state.set_state(OfferFSM.property_type)
    await msg.answer("3) Проживання: напиши один варіант:\n- " + "\n- ".join(PROPERTY_TYPES))

@dp.message(OfferFSM.property_type)
async def s_property_type(msg: Message, state: FSMContext):
    val = normalize_text(msg.text)
    if val.lower().startswith("інше"):
        await msg.answer("Напиши свій варіант типу житла (інше):")
        await state.update_data(expect_custom_property=True)
        return
    # якщо попередньо чекали custom
    data = await state.get_data()
    if data.get("expect_custom_property"):
        await state.update_data(expect_custom_property=False)

    oid = data.get("offer_id")
    update_offer_fields(int(oid), {"property_type": val})
    await state.set_state(OfferFSM.street)
    await msg.answer("4) Вулиця: напиши (наприклад: вул. Шевченка 10)")

@dp.message(OfferFSM.street)
async def s_street(msg: Message, state: FSMContext):
    await save_and_next(msg, state, "street", OfferFSM.city)
    await msg.answer("5) Місто: напиши")

@dp.message(OfferFSM.city)
async def s_city(msg: Message, state: FSMContext):
    await save_and_next(msg, state, "city", OfferFSM.district)
    await msg.answer("6) Район: напиши")

@dp.message(OfferFSM.district)
async def s_district(msg: Message, state: FSMContext):
    await save_and_next(msg, state, "district", OfferFSM.advantages)
    await msg.answer("7) Переваги житла: напиши")

@dp.message(OfferFSM.advantages)
async def s_adv(msg: Message, state: FSMContext):
    await save_and_next(msg, state, "advantages", OfferFSM.rent)
    await msg.answer("8) Оренда: напиши суму")

@dp.message(OfferFSM.rent)
async def s_rent(msg: Message, state: FSMContext):
    await save_and_next(msg, state, "rent", OfferFSM.deposit)
    await msg.answer("9) Депозит: напиши суму")

@dp.message(OfferFSM.deposit)
async def s_deposit(msg: Message, state: FSMContext):
    await save_and_next(msg, state, "deposit", OfferFSM.commission)
    await msg.answer("10) Комісія: напиши суму")

@dp.message(OfferFSM.commission)
async def s_comm(msg: Message, state: FSMContext):
    await save_and_next(msg, state, "commission", OfferFSM.parking)
    await msg.answer("11) Паркінг: напиши")

@dp.message(OfferFSM.parking)
async def s_parking(msg: Message, state: FSMContext):
    await save_and_next(msg, state, "parking", OfferFSM.move_in)
    await msg.answer("12) Заселення від: напиши")

@dp.message(OfferFSM.move_in)
async def s_move_in(msg: Message, state: FSMContext):
    await save_and_next(msg, state, "move_in", OfferFSM.viewing)
    await msg.answer("13) Огляди від: напиши")

@dp.message(OfferFSM.viewing)
async def s_view(msg: Message, state: FSMContext):
    await save_and_next(msg, state, "viewing", OfferFSM.broker)
    await msg.answer("14) Маклер: напиши нік (наприклад: @nickname)")

@dp.message(OfferFSM.broker)
async def s_broker(msg: Message, state: FSMContext):
    oid = (await state.get_data()).get("offer_id")
    val = normalize_text(msg.text)
    if not val.startswith("@"):
        await msg.answer("Нік має починатися з @ (наприклад: @nickname)")
        return
    update_offer_fields(int(oid), {"broker": val})
    await state.set_state(OfferFSM.photos)
    await msg.answer(
        "15) Завантаж фото.\n"
        "Надсилай фото (можна багато).\n\n"
        "Коли закінчиш — напиши: **ГОТОВО**"
    )

# ===================== PHOTOS =====================
@dp.message(OfferFSM.photos, F.photo)
async def s_photo_collect(msg: Message, state: FSMContext):
    data = await state.get_data()
    photos: List[str] = data.get("photos", [])
    photos.append(msg.photo[-1].file_id)
    await state.update_data(photos=photos)
    await msg.answer(f"📷 Фото додано: {len(photos)}")

@dp.message(OfferFSM.photos, F.text)
async def s_photo_done(msg: Message, state: FSMContext):
    if msg.text.strip().lower() != "готово":
        await msg.answer("Надсилай фото або напиши **ГОТОВО** коли закінчиш.")
        return

    data = await state.get_data()
    oid = data.get("offer_id")
    photos: List[str] = data.get("photos", [])
    if not photos:
        await msg.answer("❌ Потрібно хоча б одне фото.")
        return

    set_offer_photos(int(oid), photos)

    offer = get_offer(int(oid))
    text = build_offer_text(offer)
    media = [InputMediaPhoto(media=p) for p in photos]
    # Caption тільки на першому фото
    media[0].caption = text
    media[0].parse_mode = "Markdown"

    await bot.send_media_group(msg.chat.id, media)
    await state.set_state(OfferFSM.review)
    await msg.answer("16) Пропозиція готова." + review_instructions())

# ===================== REVIEW / EDIT =====================
@dp.message(OfferFSM.review, F.text)
async def s_review(msg: Message, state: FSMContext):
    t = msg.text.strip().lower()
    data = await state.get_data()
    oid = int(data.get("offer_id") or 0)
    if not oid:
        await msg.answer("❌ Немає активної пропозиції. /new")
        return

    if t == "скасувати":
        await state.clear()
        await msg.answer("❌ Скасовано. Для нової пропозиції: /new")
        return

    if t == "публікувати":
        await publish_offer(msg, oid)
        await state.clear()
        return

    n = parse_edit_cmd(msg.text)
    if n is None:
        await msg.answer("Не зрозумів. Напиши **ПУБЛІКУВАТИ** або **ЗМІНИТИ 5** або **СКАСУВАТИ**.")
        return

    field_key = field_by_number(n)
    if not field_key:
        await msg.answer("Невірний номер. Можна 2–14. Наприклад: **ЗМІНИТИ 8**")
        return

    await state.update_data(edit_field=field_key)
    await state.set_state(OfferFSM.edit_value)
    await msg.answer("✏️ " + prompt_for_field(field_key))

@dp.message(OfferFSM.edit_value, F.text)
async def s_edit_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    oid = int(data.get("offer_id") or 0)
    field_key = data.get("edit_field")
    if not oid or not field_key:
        await msg.answer("❌ Помилка стану. /new")
        await state.clear()
        return

    val = normalize_text(msg.text)
    # мінімальна валідація ніка
    if field_key == "broker" and not val.startswith("@"):
        await msg.answer("Нік має починатися з @ (наприклад: @nickname). Спробуй ще раз:")
        return

    update_offer_fields(oid, {field_key: val})

    offer = get_offer(oid)
    preview = build_offer_text(offer)
    await msg.answer("✅ Оновлено.\n\n" + preview + review_instructions(), parse_mode="Markdown")
    await state.set_state(OfferFSM.review)

# ===================== PUBLISH + GROUP CONTROLS =====================
async def publish_offer(msg: Message, offer_id: int) -> None:
    offer = get_offer(offer_id)
    if not offer:
        await msg.answer("❌ Пропозицію не знайдено.")
        return

    photos = json.loads(offer.get("photos_json") or "[]")
    if not photos:
        await msg.answer("❌ Немає фото.")
        return

    caption = build_offer_text(offer)

    media = [InputMediaPhoto(media=p) for p in photos]
    media[0].caption = caption
    media[0].parse_mode = "Markdown"

    # 1) Альбом у групу
    album_msgs = await bot.send_media_group(GROUP_CHAT_ID, media)
    album_first_id = album_msgs[0].message_id

    # 2) Окреме керування статусом (щоб було де редагувати текст та кнопки)
    control_text = (
        f"🏠 ПРОПОЗИЦІЯ #{offer_num(offer_id)}\n"
        f"📊 Статус: {offer.get('status','')}\n"
        f"👤 Маклер: {offer.get('broker') or '—'}\n"
        f"🕒 Дата: {str(offer.get('created_at',''))[:10]}"
    )
    control_msg = await bot.send_message(
        GROUP_CHAT_ID,
        control_text,
        reply_markup=status_kb(offer_id),
    )

    set_offer_group_msgs(offer_id, album_first_id, control_msg.message_id)

    await msg.answer(f"✅ Опубліковано в групу: пропозиція #{offer_num(offer_id)}")

@dp.callback_query(F.data.startswith("st:"))
async def cb_status(cb: CallbackQuery):
    try:
        _p, code, offer_id_s = cb.data.split(":")
        offer_id = int(offer_id_s)
    except Exception:
        await cb.answer("Помилка")
        return

    offer = get_offer(offer_id)
    if not offer:
        await cb.answer("Не знайдено")
        return

    # Захист: тільки автор або адмін
    if not can_manage_offer(cb.from_user.id, offer):
        await cb.answer("❌ Немає прав")
        return

    status_map = {
        "active": "🟢 Актуально",
        "reserve": "🟡 Резерв",
        "inactive": "🔴 Неактуально",
    }
    if code not in status_map:
        await cb.answer("Помилка статусу")
        return

    new_status = status_map[code]
    set_offer_status(offer_id, new_status)

    # Оновити контрольне повідомлення
    new_control_text = (
        f"🏠 ПРОПОЗИЦІЯ #{offer_num(offer_id)}\n"
        f"📊 Статус: {new_status}\n"
        f"👤 Маклер: {offer.get('broker') or '—'}\n"
        f"🕒 Дата: {str(offer.get('created_at',''))[:10]}"
    )
    try:
        await cb.message.edit_text(new_control_text, reply_markup=status_kb(offer_id))
    except Exception:
        # Якщо не вдається редагувати (наприклад, message too old) — просто ігноруємо
        pass

    # Оновити caption першого фото альбому (щоб у групі теж було видно актуальний статус в описі)
    offer2 = get_offer(offer_id) or offer
    album_first_id = offer2.get("group_album_first_msg_id")
    if album_first_id:
        try:
            photos = json.loads(offer2.get("photos_json") or "[]")
            caption = build_offer_text(offer2)
            # editMessageCaption тільки для першого повідомлення альбому
            await bot.edit_message_caption(
                chat_id=GROUP_CHAT_ID,
                message_id=int(album_first_id),
                caption=caption,
                parse_mode="Markdown",
            )
        except Exception:
            pass

    await cb.answer(f"Статус: {new_status}")

# ===================== OPTIONAL: /stats =====================
@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT status, COUNT(*) as c FROM offers GROUP BY status")
    rows = cur.fetchall()
    con.close()

    if not rows:
        await msg.answer("Поки що немає пропозицій.")
        return

    lines = ["📊 Статистика по статусах:"]
    for r in rows:
        lines.append(f"- {r['status']}: {r['c']}")
    await msg.answer("\n".join(lines))

# ===================== MAIN =====================
async def main():
    init_db()
    print("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

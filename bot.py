import asyncio
import json
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, GROUP_CHAT_ID, DB_PATH
from database import DB, STATUS_ACTIVE, STATUS_RESERVE, STATUS_REMOVED, STATUS_CLOSED
from keyboards import (
    kb_done_photos, kb_preview_actions, kb_status,
    kb_housing_type, kb_category
)
from states import CreateOffer, EditOffer


db = DB(DB_PATH)

STATUS_LABELS = {
    STATUS_ACTIVE: "🟢 Актуально",
    STATUS_RESERVE: "🟡 Резерв",
    STATUS_REMOVED: "⚫️ Знято",
    STATUS_CLOSED: "✅ Угода закрита",
}

FIELD_ORDER = [
    ("category", "🏷️ Категорія"),
    ("housing_type", "🏠 Тип житла"),
    ("street", "📍 Вулиця"),
    ("city", "🏙️ Місто"),
    ("district", "🗺️ Район"),
    ("advantages", "✨ Переваги"),
    ("rent", "💶 Оренда"),
    ("deposit", "🔑 Депозит"),
    ("commission", "🤝 Комісія"),
    ("parking", "🚗 Паркінг"),
    ("move_in", "📦 Заселення від"),
    ("view_from", "👀 Огляди від"),
    ("broker", "🧑‍💼 Маклер"),
]

def username_of(msg: Message) -> str:
    u = msg.from_user
    if u.username:
        return f"@{u.username}"
    # якщо нема username — хоча б імʼя
    return (u.full_name or "—").strip()

def fmt_offer_text(num: int, status: str, fields: dict, broker_username: str) -> str:
    # Без "Чернетка". Статус завжди один із 4.
    lines = []
    lines.append(f"🏡 <b>ПРОПОЗИЦІЯ #{num:04d}</b>")
    lines.append(f"📊 <b>Статус:</b> {STATUS_LABELS.get(status, status)}")
    lines.append("")
    for key, label in FIELD_ORDER:
        if key == "broker":
            val = broker_username or fields.get("broker") or "—"
        else:
            val = fields.get(key) or "—"
        lines.append(f"{label}: <b>{val}</b>")
    return "\n".join(lines)

def parse_fields(offer: dict) -> dict:
    return json.loads(offer["fields_json"])

def parse_photos(offer: dict) -> list[str]:
    return json.loads(offer["photos_json"])

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso(dt: datetime) -> str:
    return dt.isoformat()

def start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)

def start_of_month(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

def start_of_year(dt: datetime) -> datetime:
    return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

# -------------------- COMMANDS / MENU --------------------

async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привіт! Я ORANDA SK бот.\n\n"
        "Команди:\n"
        "• /new — створити пропозицію\n"
        "• /stats — статистика\n"
        "• /help — допомога\n"
    )

async def cmd_help(message: Message, state: FSMContext):
    await message.answer(
        "Як працюю:\n"
        "1) /new — заповнюєш поля\n"
        "2) Надсилаєш фото\n"
        "3) ✅ Готово або /done\n"
        "4) Дивишся превʼю → 📤 Публікувати\n\n"
        "Статуси в групі під пропозицією:\n"
        "🟢 Актуально / 🟡 Резерв / ⚫️ Знято / ✅ Угода закрита"
    )

async def cmd_new(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(offer_id=None)
    await message.answer("Обери категорію:", reply_markup=kb_category())
    await state.set_state(CreateOffer.category)

async def cmd_stats(message: Message):
    now = now_utc()
    d0 = start_of_day(now); d1 = d0.replace(day=d0.day)  # dummy
    m0 = start_of_month(now)
    y0 = start_of_year(now)

    # end boundaries
    d_end = d0.replace(hour=23, minute=59, second=59, microsecond=999999)  # not used directly
    # use [start, start+1day)
    d_next = d0 + (datetime.min.replace(tzinfo=timezone.utc) - datetime.min.replace(tzinfo=timezone.utc))  # noop
    d_next = d0 + (now - now)  # reset, then:
    from datetime import timedelta
    d_next = d0 + timedelta(days=1)
    m_next = (m0.replace(day=28) + timedelta(days=4)).replace(day=1)  # next month
    y_next = y0.replace(year=y0.year + 1)

    day_stats = db.stats_status_changes(iso(d0), iso(d_next))
    mon_stats = db.stats_status_changes(iso(m0), iso(m_next))
    yr_stats = db.stats_status_changes(iso(y0), iso(y_next))

    def block(title: str, pack: dict) -> str:
        t = pack["totals_by_status"]
        return (
            f"<b>{title}</b>\n"
            f"🟢 Актуально: {t.get(STATUS_ACTIVE,0)}\n"
            f"🟡 Резерв: {t.get(STATUS_RESERVE,0)}\n"
            f"⚫️ Знято: {t.get(STATUS_REMOVED,0)}\n"
            f"✅ Угода закрита: {t.get(STATUS_CLOSED,0)}\n"
        )

    def brokers_block(title: str, pack: dict) -> str:
        by = pack["by_broker"]
        if not by:
            return f"<b>{title}</b>\n—\n"
        lines = [f"<b>{title}</b>"]
        for broker, m in sorted(by.items(), key=lambda x: x[0].lower()):
            lines.append(
                f"• {broker}: "
                f"🟢{m.get(STATUS_ACTIVE,0)} "
                f"🟡{m.get(STATUS_RESERVE,0)} "
                f"⚫️{m.get(STATUS_REMOVED,0)} "
                f"✅{m.get(STATUS_CLOSED,0)}"
            )
        return "\n".join(lines) + "\n"

    text = []
    text.append("📈 <b>Статистика (зміни статусів)</b>\n")
    text.append(block(f"День ({d0.date()})", day_stats))
    text.append(block(f"Місяць ({m0.strftime('%Y-%m')})", mon_stats))
    text.append(block(f"Рік ({y0.year})", yr_stats))

    text.append("\n🧑‍💼 <b>Хто скільки ставив статусів</b>\n")
    text.append(brokers_block(f"День ({d0.date()})", day_stats))
    text.append(brokers_block(f"Місяць ({m0.strftime('%Y-%m')})", mon_stats))
    text.append(brokers_block(f"Рік ({y0.year})", yr_stats))

    await message.answer("\n".join(text))

# Тригери під твої вбудовані кнопки
async def menu_triggers(message: Message, state: FSMContext):
    t = (message.text or "").strip()
    if "Зробити пропозицію" in t:
        return await cmd_new(message, state)
    if "Статистика" in t:
        return await cmd_stats(message)
    if "Допомога" in t:
        return await cmd_help(message, state)

# -------------------- CREATE FLOW --------------------

async def on_category_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    category = call.data.split("cat:", 1)[1]
    await state.update_data(category=category)
    await call.message.answer("Обери тип житла:", reply_markup=kb_housing_type())
    await state.set_state(CreateOffer.housing_type)

async def on_housing_type_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    val = call.data.split("ht:", 1)[1]
    if val == "__custom__":
        await call.message.answer("Напиши свій варіант типу житла:")
        await state.set_state(CreateOffer.housing_type_custom)
        return
    await state.update_data(housing_type=val)
    await call.message.answer("Вулиця (наприклад: Грабова 12):")
    await state.set_state(CreateOffer.street)

async def on_housing_type_custom(message: Message, state: FSMContext):
    await state.update_data(housing_type=message.text.strip())
    await message.answer("Вулиця (наприклад: Грабова 12):")
    await state.set_state(CreateOffer.street)

async def on_street(message: Message, state: FSMContext):
    await state.update_data(street=message.text.strip())
    await message.answer("Місто:")
    await state.set_state(CreateOffer.city)

async def on_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await message.answer("Район:")
    await state.set_state(CreateOffer.district)

async def on_district(message: Message, state: FSMContext):
    await state.update_data(district=message.text.strip())
    await message.answer("Переваги (коротко, через кому):")
    await state.set_state(CreateOffer.advantages)

async def on_advantages(message: Message, state: FSMContext):
    await state.update_data(advantages=message.text.strip())
    await message.answer("Оренда (сума, напр. 350€):")
    await state.set_state(CreateOffer.rent)

async def on_rent(message: Message, state: FSMContext):
    await state.update_data(rent=message.text.strip())
    await message.answer("Депозит (сума):")
    await state.set_state(CreateOffer.deposit)

async def on_deposit(message: Message, state: FSMContext):
    await state.update_data(deposit=message.text.strip())
    await message.answer("Комісія (сума):")
    await state.set_state(CreateOffer.commission)

async def on_commission(message: Message, state: FSMContext):
    await state.update_data(commission=message.text.strip())
    await message.answer("Паркінг (є/нема/сума):")
    await state.set_state(CreateOffer.parking)

async def on_parking(message: Message, state: FSMContext):
    await state.update_data(parking=message.text.strip())
    await message.answer("Заселення від (наприклад: Вже / 01.01):")
    await state.set_state(CreateOffer.move_in)

async def on_move_in(message: Message, state: FSMContext):
    await state.update_data(move_in=message.text.strip())
    await message.answer("Огляди від (наприклад: Вже / 15:00):")
    await state.set_state(CreateOffer.view_from)

async def on_view_from(message: Message, state: FSMContext):
    await state.update_data(view_from=message.text.strip())
    await message.answer("Маклер (нік, напр. @zvarych1):")
    await state.set_state(CreateOffer.broker)

async def on_broker(message: Message, state: FSMContext):
    broker = message.text.strip()
    data = await state.get_data()

    fields = {
        "category": data.get("category"),
        "housing_type": data.get("housing_type"),
        "street": data.get("street"),
        "city": data.get("city"),
        "district": data.get("district"),
        "advantages": data.get("advantages"),
        "rent": data.get("rent"),
        "deposit": data.get("deposit"),
        "commission": data.get("commission"),
        "parking": data.get("parking"),
        "move_in": data.get("move_in"),
        "view_from": data.get("view_from"),
        "broker": broker,
    }

    offer = db.create_offer(
        creator_id=message.from_user.id,
        creator_username=username_of(message),
        broker_username=broker,
        fields=fields
    )

    await state.update_data(offer_id=offer["id"], photo_done=False)
    await message.answer(
        "📸 Надішли фото.\nКоли закінчиш — натисни ✅ <b>Готово</b> або введи /done.",
        reply_markup=kb_done_photos()
    )
    await state.set_state(CreateOffer.photos)

# -------------------- PHOTO COLLECTION --------------------

async def on_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data.get("offer_id")
    if not offer_id:
        return

    if data.get("photo_done"):
        # вже завершили — не додаємо, щоб не було дублікатів
        return

    if not message.photo:
        return

    file_id = message.photo[-1].file_id
    count = db.add_photo(offer_id, file_id)
    await message.answer(f"📸 Фото додано ({count})", reply_markup=kb_done_photos())

async def finish_photos(state: FSMContext, chat_message: Message | None = None, chat_call: CallbackQuery | None = None):
    data = await state.get_data()
    offer_id = data.get("offer_id")
    if not offer_id:
        return

    # анти-дубль: якщо вже завершено — нічого не робимо
    if data.get("photo_done"):
        if chat_call:
            await chat_call.answer("Вже завершено ✅", show_alert=False)
        return

    offer = db.get_offer(offer_id)
    photos = parse_photos(offer)

    if not photos:
        # без фото — не даємо завершити
        if chat_call:
            await chat_call.answer("Додай хоча б 1 фото.", show_alert=True)
        if chat_message:
            await chat_message.answer("Додай хоча б 1 фото, потім ✅ Готово.")
        return

    await state.update_data(photo_done=True)

    fields = parse_fields(offer)
    text = fmt_offer_text(offer["num"], offer["status"], fields, offer["broker_username"]) + "\n<i>(не опубліковано)</i>"

    # Превʼю альбомом (якщо фото багато — Telegram сам зробить сітку)
    media = []
    for i, fid in enumerate(photos[:10]):
        if i == 0:
            media.append(InputMediaPhoto(media=fid, caption=text, parse_mode="HTML"))
        else:
            media.append(InputMediaPhoto(media=fid))
    try:
        if chat_call:
            await chat_call.message.answer_media_group(media)
            await chat_call.message.answer("👇 Це фінальний вигляд пропозиції", reply_markup=kb_preview_actions(offer_id))
        else:
            await chat_message.answer_media_group(media)
            await chat_message.answer("👇 Це фінальний вигляд пропозиції", reply_markup=kb_preview_actions(offer_id))
    except Exception:
        # якщо не вийшло альбомом — хоч текст покажемо
        if chat_call:
            await chat_call.message.answer(text, reply_markup=kb_preview_actions(offer_id))
        else:
            await chat_message.answer(text, reply_markup=kb_preview_actions(offer_id))

    await state.clear()

async def on_done_cmd(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() in ["/done", "done", "готово", "✅ готово"]:
        await finish_photos(state, chat_message=message)

async def on_done_cb(call: CallbackQuery, state: FSMContext):
    if call.data == "photos:done":
        await call.answer()
        await finish_photos(state, chat_call=call)

# -------------------- PREVIEW ACTIONS --------------------

async def on_cancel(call: CallbackQuery, state: FSMContext):
    await call.answer()
    offer_id = int(call.data.split("cancel:", 1)[1])
    await state.clear()
    await call.message.answer("❌ Скасовано.")

async def on_publish(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.answer()
    offer_id = int(call.data.split("pub:", 1)[1])

    offer = db.get_offer(offer_id)
    if not offer:
        await call.message.answer("Не знайдено пропозицію.")
        return

    if offer.get("published_at"):
        await call.message.answer("Вже опубліковано ✅")
        return

    photos = parse_photos(offer)
    fields = parse_fields(offer)

    text = fmt_offer_text(offer["num"], offer["status"], fields, offer["broker_username"])

    # 1) Альбом у групу
    media = []
    for i, fid in enumerate(photos[:10]):
        if i == 0:
            media.append(InputMediaPhoto(media=fid, caption=text, parse_mode="HTML"))
        else:
            media.append(InputMediaPhoto(media=fid))

    album_msgs = await bot.send_media_group(GROUP_CHAT_ID, media)
    album_first_id = album_msgs[0].message_id if album_msgs else None

    # 2) Окреме повідомлення з кнопками статусів (саме воно буде змінюватись)
    ctrl_msg = await bot.send_message(
        GROUP_CHAT_ID,
        text,
        reply_markup=kb_status(offer_id),
        parse_mode="HTML"
    )

    db.set_published(offer_id, ctrl_msg.message_id, album_first_id or 0)

    await call.message.answer(f"✅ Пропозицію #{offer['num']:04d} опубліковано в групу")

async def on_edit(call: CallbackQuery, state: FSMContext):
    await call.answer()
    offer_id = int(call.data.split("edit:", 1)[1])
    offer = db.get_offer(offer_id)
    if not offer:
        await call.message.answer("Не знайдено пропозицію.")
        return

    # Список 1-13
    lines = [f"✏️ <b>Редагування пропозиції #{offer['num']:04d}</b>",
             "Напиши номер пункту 1–13, який хочеш змінити.\n",
             "<b>Список:</b>"]
    for i, (key, label) in enumerate(FIELD_ORDER, start=1):
        if key == "broker":
            lines.append(f"{i}. Маклер")
        else:
            # label already has emoji
            # clean label for listing
            clean = label.split(" ", 1)[1] if " " in label else label
            lines.append(f"{i}. {clean}")

    await state.set_state(EditOffer.choose_field_num)
    await state.update_data(edit_offer_id=offer_id)
    await call.message.answer("\n".join(lines), parse_mode="HTML")

async def on_edit_choose_num(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer("Введи число 1–13.")
        return

    n = int(txt)
    if n < 1 or n > len(FIELD_ORDER):
        await message.answer("Номер має бути 1–13.")
        return

    offer_id = (await state.get_data()).get("edit_offer_id")
    key = FIELD_ORDER[n - 1][0]

    await state.update_data(edit_field_key=key)

    # якщо це тип житла — дамо кнопки + інше
    if key == "housing_type":
        await message.answer("Обери тип житла або натисни «Інше…»:", reply_markup=kb_housing_type())
        # чекаємо callback ht:...
        return

    await state.set_state(EditOffer.enter_value)
    await message.answer("Напиши нове значення:")

async def on_edit_enter_value(message: Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data.get("edit_offer_id")
    key = data.get("edit_field_key")
    if not offer_id or not key:
        await state.clear()
        return

    value = (message.text or "").strip()

    if key == "broker":
        db.set_broker(offer_id, value)
        db.update_field(offer_id, "broker", value)
    else:
        db.update_field(offer_id, key, value)

    offer = db.get_offer(offer_id)
    fields = parse_fields(offer)
    text = fmt_offer_text(offer["num"], offer["status"], fields, offer["broker_username"]) + "\n<i>(не опубліковано)</i>"

    await message.answer("✅ Оновлено. Ось нове превʼю:")
    await message.answer(text, parse_mode="HTML", reply_markup=kb_preview_actions(offer_id))
    await state.clear()

# callback для housing_type під час редагування
async def on_edit_housing_type_cb(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if (await state.get_state()) != EditOffer.choose_field_num.state:
        # якщо не в режимі редагування — це створення обробить інший handler
        return

    await call.answer()
    offer_id = data.get("edit_offer_id")
    if not offer_id:
        await state.clear()
        return

    val = call.data.split("ht:", 1)[1]
    if val == "__custom__":
        await call.message.answer("Напиши свій варіант типу житла:")
        await state.set_state(EditOffer.housing_type_custom)
        return

    db.update_field(offer_id, "housing_type", val)
    offer = db.get_offer(offer_id)
    fields = parse_fields(offer)
    text = fmt_offer_text(offer["num"], offer["status"], fields, offer["broker_username"]) + "\n<i>(не опубліковано)</i>"

    await call.message.answer("✅ Оновлено. Ось нове превʼю:")
    await call.message.answer(text, parse_mode="HTML", reply_markup=kb_preview_actions(offer_id))
    await state.clear()

async def on_edit_housing_type_custom(message: Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data.get("edit_offer_id")
    if not offer_id:
        await state.clear()
        return

    val = (message.text or "").strip()
    db.update_field(offer_id, "housing_type", val)

    offer = db.get_offer(offer_id)
    fields = parse_fields(offer)
    text = fmt_offer_text(offer["num"], offer["status"], fields, offer["broker_username"]) + "\n<i>(не опубліковано)</i>"

    await message.answer("✅ Оновлено. Ось нове превʼю:")
    await message.answer(text, parse_mode="HTML", reply_markup=kb_preview_actions(offer_id))
    await state.clear()

# -------------------- GROUP STATUS BUTTONS --------------------

async def on_status_change(call: CallbackQuery):
    # st:{offer_id}:{status}
    await call.answer()
    parts = call.data.split(":")
    if len(parts) != 3:
        return
    offer_id = int(parts[1])
    new_status = parts[2]

    offer = db.get_offer(offer_id)
    if not offer:
        return

    # оновлюємо статус + лог
    db.set_status(offer_id, new_status)

    offer = db.get_offer(offer_id)
    fields = parse_fields(offer)
    text = fmt_offer_text(offer["num"], offer["status"], fields, offer["broker_username"])

    # ВАЖЛИВО: лише редагуємо повідомлення, НЕ видаляємо => “не пропадає”
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_status(offer_id))
    except Exception:
        # якщо не вдалось редагувати (наприклад, те саме) — просто ігноруємо
        pass

# -------------------- MAIN --------------------

async def main():
    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Команди
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_new, Command("new"))
    dp.message.register(cmd_stats, Command("stats"))

    # Тригери твоїх вбудованих кнопок (Reply keyboard ти робиш сам)
    dp.message.register(menu_triggers, F.text)

    # Callbacks категорія / тип житла
    dp.callback_query.register(on_category_cb, F.data.startswith("cat:"))

    # ВАЖЛИВО: housing_type callback використовується і в створенні, і в редагуванні
    dp.callback_query.register(on_edit_housing_type_cb, F.data.startswith("ht:"))
    dp.callback_query.register(on_housing_type_cb, F.data.startswith("ht:"))

    # Створення: по станах
    dp.message.register(on_housing_type_custom, CreateOffer.housing_type_custom)
    dp.message.register(on_street, CreateOffer.street)
    dp.message.register(on_city, CreateOffer.city)
    dp.message.register(on_district, CreateOffer.district)
    dp.message.register(on_advantages, CreateOffer.advantages)
    dp.message.register(on_rent, CreateOffer.rent)
    dp.message.register(on_deposit, CreateOffer.deposit)
    dp.message.register(on_commission, CreateOffer.commission)
    dp.message.register(on_parking, CreateOffer.parking)
    dp.message.register(on_move_in, CreateOffer.move_in)
    dp.message.register(on_view_from, CreateOffer.view_from)
    dp.message.register(on_broker, CreateOffer.broker)

    # Фото
    dp.callback_query.register(on_done_cb, F.data == "photos:done")
    dp.message.register(on_done_cmd, CreateOffer.photos)  # /done або "Готово"
    dp.message.register(on_photo, CreateOffer.photos, F.photo)

    # Превʼю кнопки
    dp.callback_query.register(on_publish, F.data.startswith("pub:"))
    dp.callback_query.register(on_edit, F.data.startswith("edit:"))
    dp.callback_query.register(on_cancel, F.data.startswith("cancel:"))

    # Редагування
    dp.message.register(on_edit_choose_num, EditOffer.choose_field_num)
    dp.message.register(on_edit_enter_value, EditOffer.enter_value)
    dp.message.register(on_edit_housing_type_custom, EditOffer.housing_type_custom)

    # Статуси в групі
    dp.callback_query.register(on_status_change, F.data.startswith("st:"))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

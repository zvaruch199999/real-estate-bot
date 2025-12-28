import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery, InputMediaPhoto,
    ReplyKeyboardRemove, FSInputFile
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, DB_PATH, get_group_chat_id, require_env
from states import OfferForm, EditForm
from keyboards import (
    category_kb, housing_type_kb,
    preview_kb, status_kb, photos_done_kb
)
from database import DB, STATUS_ACTIVE, STATUS_RESERVED, STATUS_REMOVED, STATUS_CLOSED
from excel import export_offers_csv

router = Router()
db = DB(DB_PATH)

STATUS_LABEL = {
    STATUS_ACTIVE: "🟢 Актуально",
    STATUS_RESERVED: "🟡 Резерв",
    STATUS_REMOVED: "🔴 Знято",
    STATUS_CLOSED: "✅ Закрито",
}

FIELD_MAP = {
    2: ("category", "Категорія"),
    3: ("housing_type", "Вид житла"),
    4: ("street", "Вулиця"),
    5: ("city", "Місто"),
    6: ("district", "Район"),
    7: ("advantages", "Переваги"),
    8: ("rent", "Оренда"),
    9: ("deposit", "Депозит"),
    10: ("commission", "Комісія"),
    11: ("parking", "Паркінг"),
    12: ("move_in_from", "Заселення від"),
    13: ("viewings_from", "Огляди від"),
    14: ("broker", "Маклер"),
}


def norm_username(m: Message) -> str:
    if m.from_user and m.from_user.username:
        return "@" + m.from_user.username
    if m.from_user:
        return f"{m.from_user.full_name}"
    return "(unknown)"


def offer_text(offer_id: int, data: dict) -> str:
    # емодзі + нумерація
    status = STATUS_LABEL.get(data.get("status", STATUS_ACTIVE), "🟢 Актуально")
    return (
        f"🏡 <b>НОВА ПРОПОЗИЦІЯ #{offer_id:04d}</b>\n"
        f"📊 <b>Статус:</b> {status}\n\n"
        f"🏷 <b>Категорія:</b> {data.get('category','—')}\n"
        f"🏠 <b>Вид житла:</b> {data.get('housing_type','—')}\n"
        f"📍 <b>Адреса:</b> {data.get('street','—')}, {data.get('city','—')}\n"
        f"🗺 <b>Район:</b> {data.get('district','—')}\n"
        f"✨ <b>Переваги:</b> {data.get('advantages','—')}\n"
        f"💶 <b>Оренда:</b> {data.get('rent','—')}\n"
        f"🔐 <b>Депозит:</b> {data.get('deposit','—')}\n"
        f"🤝 <b>Комісія:</b> {data.get('commission','—')}\n"
        f"🚗 <b>Паркінг:</b> {data.get('parking','—')}\n"
        f"📅 <b>Заселення від:</b> {data.get('move_in_from','—')}\n"
        f"👀 <b>Огляди від:</b> {data.get('viewings_from','—')}\n"
        f"🧑‍💼 <b>Маклер:</b> {data.get('broker','—')}\n"
    )


def edit_list_text(offer_id: int) -> str:
    lines = [f"✏️ <b>Редагування пропозиції #{offer_id:04d}</b>",
             "Напиши номер пункту, який хочеш змінити (2–14).",
             "Наприклад: <b>8</b>\n",
             "<b>Список:</b>"]
    for k in sorted(FIELD_MAP.keys()):
        lines.append(f"{k}. {FIELD_MAP[k][1]}")
    return "\n".join(lines)


async def send_album(chat_id: int, bot: Bot, photos: list[str]):
    if not photos:
        return
    media = [InputMediaPhoto(media=pid) for pid in photos]
    await bot.send_media_group(chat_id, media=media)


def period_bounds_day(dt: datetime) -> tuple[str, str]:
    start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()

def period_bounds_month(dt: datetime) -> tuple[str, str]:
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year+1, month=1)
    else:
        end = start.replace(month=start.month+1)
    return start.isoformat(), end.isoformat()

def period_bounds_year(dt: datetime) -> tuple[str, str]:
    start = dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year+1)
    return start.isoformat(), end.isoformat()


def fmt_stats_block(title: str, counts: dict) -> str:
    a = counts.get(STATUS_ACTIVE, 0)
    r = counts.get(STATUS_RESERVED, 0)
    rm = counts.get(STATUS_REMOVED, 0)
    c = counts.get(STATUS_CLOSED, 0)
    return (
        f"<b>{title}</b>\n"
        f"🟢 Актуально: <b>{a}</b>\n"
        f"🟡 Резерв: <b>{r}</b>\n"
        f"🔴 Знято: <b>{rm}</b>\n"
        f"✅ Закрито: <b>{c}</b>\n"
    )


def fmt_broker_block(title: str, broker_stats: dict) -> str:
    # broker_stats: username -> {status->count}
    lines = [f"🧑‍💼 <b>{title}</b>"]
    if not broker_stats:
        lines.append("— немає змін статусів")
        return "\n".join(lines)

    for u, st_map in broker_stats.items():
        a = st_map.get(STATUS_ACTIVE, 0)
        r = st_map.get(STATUS_RESERVED, 0)
        rm = st_map.get(STATUS_REMOVED, 0)
        c = st_map.get(STATUS_CLOSED, 0)
        lines.append(
            f"{u} → 🟢{a} 🟡{r} 🔴{rm} ✅{c}"
        )
    return "\n".join(lines)


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Команди:\n"
        "/new — створити пропозицію\n"
        "/stats — статистика\n"
        "/export — експорт CSV\n",
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(OfferForm.category)
    await message.answer("🏷 Обери категорію:", reply_markup=category_kb())


# ---------- CATEGORY ----------
@router.callback_query(F.data.startswith("cat:"), OfferForm.category)
async def on_category(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":", 1)[1]
    await cb.answer()
    if val == "__other__":
        await state.update_data(category=None)
        await cb.message.answer("✍️ Впиши свою категорію текстом:")
        return
    await state.update_data(category=val)
    await state.set_state(OfferForm.housing_type)
    await cb.message.answer("🏠 Обери вид житла:", reply_markup=housing_type_kb())

@router.message(OfferForm.category)
async def category_text(message: Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await state.set_state(OfferForm.housing_type)
    await message.answer("🏠 Обери вид житла:", reply_markup=housing_type_kb())


# ---------- HOUSING TYPE ----------
@router.callback_query(F.data.startswith("ht:"), OfferForm.housing_type)
async def on_ht(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":", 1)[1]
    await cb.answer()
    if val == "__other__":
        await state.update_data(housing_type=None)
        await cb.message.answer("✍️ Впиши свій варіант виду житла:")
        return
    await state.update_data(housing_type=val)
    await state.set_state(OfferForm.street)
    await cb.message.answer("📍 Вулиця:")

@router.message(OfferForm.housing_type)
async def ht_text(message: Message, state: FSMContext):
    await state.update_data(housing_type=message.text.strip())
    await state.set_state(OfferForm.street)
    await message.answer("📍 Вулиця:")


# ---------- TEXT STEPS ----------
@router.message(OfferForm.street)
async def street_step(message: Message, state: FSMContext):
    await state.update_data(street=message.text.strip())
    await state.set_state(OfferForm.city)
    await message.answer("🏙 Місто:")

@router.message(OfferForm.city)
async def city_step(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(OfferForm.district)
    await message.answer("🗺 Район:")

@router.message(OfferForm.district)
async def district_step(message: Message, state: FSMContext):
    await state.update_data(district=message.text.strip())
    await state.set_state(OfferForm.advantages)
    await message.answer("✨ Переваги:")

@router.message(OfferForm.advantages)
async def adv_step(message: Message, state: FSMContext):
    await state.update_data(advantages=message.text.strip())
    await state.set_state(OfferForm.rent)
    await message.answer("💶 Оренда (наприклад 350€):")

@router.message(OfferForm.rent)
async def rent_step(message: Message, state: FSMContext):
    await state.update_data(rent=message.text.strip())
    await state.set_state(OfferForm.deposit)
    await message.answer("🔐 Депозит:")

@router.message(OfferForm.deposit)
async def dep_step(message: Message, state: FSMContext):
    await state.update_data(deposit=message.text.strip())
    await state.set_state(OfferForm.commission)
    await message.answer("🤝 Комісія:")

@router.message(OfferForm.commission)
async def com_step(message: Message, state: FSMContext):
    await state.update_data(commission=message.text.strip())
    await state.set_state(OfferForm.parking)
    await message.answer("🚗 Паркінг:")

@router.message(OfferForm.parking)
async def park_step(message: Message, state: FSMContext):
    await state.update_data(parking=message.text.strip())
    await state.set_state(OfferForm.move_in_from)
    await message.answer("📅 Заселення від:")

@router.message(OfferForm.move_in_from)
async def move_step(message: Message, state: FSMContext):
    await state.update_data(move_in_from=message.text.strip())
    await state.set_state(OfferForm.viewings_from)
    await message.answer("👀 Огляди від:")

@router.message(OfferForm.viewings_from)
async def view_step(message: Message, state: FSMContext):
    await state.update_data(viewings_from=message.text.strip())
    await state.set_state(OfferForm.broker)
    await message.answer("🧑‍💼 Маклер (нік або ім'я):")

@router.message(OfferForm.broker)
async def broker_step(message: Message, state: FSMContext):
    await state.update_data(broker=message.text.strip())
    await state.update_data(photos=[])
    await state.set_state(OfferForm.photos)
    await message.answer(
        "📸 Надішли фото. Коли закінчиш — натисни ✅ Готово або напиши /done",
        reply_markup=photos_done_kb()
    )


# ---------- PHOTOS ----------
@router.message(OfferForm.photos)
async def photo_collector(message: Message, state: FSMContext):
    txt = (message.text or "").strip().lower()

    if txt in {"✅ готово", "готово", "/done"}:
        await done_photos(message, state, message.bot)
        return

    if not message.photo:
        await message.answer("Надішли фото або натисни ✅ Готово.")
        return

    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(photo_id)
    await state.update_data(photos=photos)
    await message.answer(f"📷 Фото додано ({len(photos)})")

@router.message(Command("done"))
async def done_cmd(message: Message, state: FSMContext):
    # Якщо людина ввела /done не в фото-стані — ігноруємо м’яко
    if (await state.get_state()) != OfferForm.photos.state:
        await message.answer("Команда /done працює під час додавання фото.")
        return
    await done_photos(message, state, message.bot)

async def done_photos(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    photos = data.get("photos", [])

    # створюємо пропозицію в БД
    offer_id = await db.create_offer(
        created_by_id=message.from_user.id,
        created_by_username=norm_username(message),
        data=data
    )
    await db.set_photos(offer_id, photos)

    # показати превʼю в боті (альбом + текст + кнопки)
    if photos:
        await send_album(message.chat.id, bot, photos)

    offer = await db.get_offer(offer_id)
    text = offer_text(offer_id, offer)

    await message.answer("👇 <b>Фінальний вигляд (перед публікацією)</b>", reply_markup=ReplyKeyboardRemove())
    await message.answer(text, reply_markup=status_kb(offer_id))
    await message.answer("Обери дію:", reply_markup=preview_kb(offer_id))
    await state.set_state(OfferForm.preview)


# ---------- PREVIEW ACTIONS ----------
@router.callback_query(F.data.startswith("cancel:"))
async def cancel_offer(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Скасовано")
    await cb.message.answer("❌ Скасовано.")
    await state.clear()

@router.callback_query(F.data.startswith("edit:"))
async def edit_offer(cb: CallbackQuery, state: FSMContext):
    offer_id = int(cb.data.split(":", 1)[1])
    await cb.answer()
    await state.update_data(edit_offer_id=offer_id)
    await state.set_state(EditForm.choose_field)
    await cb.message.answer(edit_list_text(offer_id))

@router.message(EditForm.choose_field)
async def edit_choose_field(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer("Впиши число (2–14).")
        return
    n = int(txt)
    if n not in FIELD_MAP:
        await message.answer("Номер має бути в межах 2–14.")
        return

    offer_id = (await state.get_data()).get("edit_offer_id")
    field_key, field_name = FIELD_MAP[n]
    await state.update_data(edit_field_key=field_key, edit_field_name=field_name)
    await state.set_state(EditForm.enter_value)
    await message.answer(f"✍️ Впиши нове значення для: <b>{field_name}</b>")

@router.message(EditForm.enter_value)
async def edit_enter_value(message: Message, state: FSMContext):
    st = await state.get_data()
    offer_id = st.get("edit_offer_id")
    field_key = st.get("edit_field_key")
    field_name = st.get("edit_field_name")

    await db.update_offer_field(offer_id, field_key, message.text.strip())
    offer = await db.get_offer(offer_id)

    await message.answer("✅ Оновлено.")
    await message.answer(offer_text(offer_id, offer), reply_markup=status_kb(offer_id))
    await message.answer("Обери дію:", reply_markup=preview_kb(offer_id))
    await state.set_state(OfferForm.preview)


@router.callback_query(F.data.startswith("pub:"))
async def publish_offer(cb: CallbackQuery, bot: Bot):
    offer_id = int(cb.data.split(":", 1)[1])
    await cb.answer()

    group_chat_id = get_group_chat_id()
    offer = await db.get_offer(offer_id)
    photos = await db.get_photos(offer_id)

    # 1) в групу — альбом
    if photos:
        await send_album(group_chat_id, bot, photos)

    # 2) окремим повідомленням — текст + кнопки статусів
    text_msg = await bot.send_message(
        group_chat_id,
        offer_text(offer_id, offer),
        reply_markup=status_kb(offer_id)
    )
    await db.set_group_message(offer_id, group_chat_id, text_msg.message_id)

    await cb.message.answer(f"✅ Пропозицію #{offer_id:04d} опубліковано в групу.")


# ---------- STATUS BUTTONS ----------
@router.callback_query(F.data.startswith("st:"))
async def change_status(cb: CallbackQuery, bot: Bot):
    _, offer_id_str, new_status = cb.data.split(":")
    offer_id = int(offer_id_str)

    offer = await db.get_offer(offer_id)
    if not offer:
        await cb.answer("Не знайдено", show_alert=True)
        return

    username = cb.from_user.username
    username = "@" + username if username else cb.from_user.full_name

    old = await db.change_status(offer_id, cb.from_user.id, username, new_status)
    await cb.answer("Ок")

    # оновити текст в групі (НЕ видаляємо нічого!)
    offer = await db.get_offer(offer_id)

    group_chat_id = offer.get("group_chat_id")
    group_message_id = offer.get("group_message_id")

    if group_chat_id and group_message_id:
        try:
            await bot.edit_message_text(
                chat_id=group_chat_id,
                message_id=group_message_id,
                text=offer_text(offer_id, offer),
                reply_markup=status_kb(offer_id)
            )
        except Exception:
            pass

    # оновити якщо натискали в приваті/боті
    try:
        await cb.message.edit_text(
            offer_text(offer_id, offer),
            reply_markup=status_kb(offer_id)
        )
    except Exception:
        pass


# ---------- STATS ----------
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    now = datetime.utcnow()

    d1, d2 = period_bounds_day(now)
    m1, m2 = period_bounds_month(now)
    y1, y2 = period_bounds_year(now)

    day_counts = await db.stats_counts(d1, d2)
    mon_counts = await db.stats_counts(m1, m2)
    year_counts = await db.stats_counts(y1, y2)

    day_b = await db.stats_by_broker_status(d1, d2)
    mon_b = await db.stats_by_broker_status(m1, m2)
    year_b = await db.stats_by_broker_status(y1, y2)

    text = (
        "📊 <b>Статистика</b>\n\n"
        + fmt_stats_block(f"День ({d1[:10]})", day_counts) + "\n"
        + fmt_stats_block(f"Місяць ({m1[:7]})", mon_counts) + "\n"
        + fmt_stats_block(f"Рік ({y1[:4]})", year_counts) + "\n"
        + "\n"
        + fmt_broker_block(f"По маклерах — День ({d1[:10]})", day_b) + "\n\n"
        + fmt_broker_block(f"По маклерах — Місяць ({m1[:7]})", mon_b) + "\n\n"
        + fmt_broker_block(f"По маклерах — Рік ({y1[:4]})", year_b)
    )
    await message.answer(text)


# ---------- EXPORT ----------
@router.message(Command("export"))
async def cmd_export(message: Message):
    out_path = "data/offers_export.csv"
    await export_offers_csv(DB_PATH, out_path)
    await message.answer_document(FSInputFile(out_path), caption="📄 Експорт CSV (відкривається в Excel/Google Sheets)")


async def main():
    require_env("BOT_TOKEN", BOT_TOKEN)
    await db.init()

    bot = Bot(BOT_TOKEN, parse_mode="HTML")
    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

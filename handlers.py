import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InputMediaPhoto

import db
import pricing
from config import (
    ADMIN_TELEGRAM_ID, AGENT_LEADS_CHAT_ID, COMPANY_NAME, COMPANY_CONTACTS,
    PROPERTY_TYPES, PEAK_RULE_NOTE,
)
import keyboards as kb

router = Router()
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return ADMIN_TELEGRAM_ID != 0 and user_id == ADMIN_TELEGRAM_ID


# ---------- FSM ----------
class AgentRegistration(StatesGroup):
    name = State()
    agency = State()
    contact = State()


class LeadForm(StatesGroup):
    name = State()
    contact = State()
    dates = State()
    budget = State()
    comment = State()
    confirm = State()


class AdminAddProperty(StatesGroup):
    id = State()
    title = State()
    district = State()
    bedrooms = State()
    sqm = State()
    view = State()
    pool_access = State()
    address = State()
    map_link = State()
    max_guests = State()
    description = State()
    deposit = State()
    utilities = State()
    prices_text = State()


class AdminEditField(StatesGroup):
    waiting_value = State()


class PriceCalc(StatesGroup):
    check_in = State()
    check_out = State()


class CatalogFlow(StatesGroup):
    check_in = State()
    check_out = State()


class AdminEditPrices(StatesGroup):
    waiting_text = State()


class AdminEditLinks(StatesGroup):
    waiting_text = State()


class AdminPhotoUpload(StatesGroup):
    uploading = State()


class AdminSettingEdit(StatesGroup):
    waiting_value = State()


class AdminBroadcast(StatesGroup):
    waiting_message = State()
    confirming = State()


WELCOME_TEXT = (
    f"🌴 Привет! Это <b>{COMPANY_NAME}</b>\n\n"
    "Помогаем агентам быстро находить и бронировать виллы и апартаменты для "
    "клиентов — с актуальными ценами и без лишней переписки.\n\n"
    "Готовы подобрать объект? Выберите, что интересует:"
)


async def get_welcome_text() -> str:
    return await db.get_setting("welcome_text", WELCOME_TEXT)


async def get_company_name() -> str:
    return await db.get_setting("company_name", COMPANY_NAME)


async def get_contact(key: str, default: str) -> str:
    return await db.get_setting(f"contact_{key}", default)


SETTINGS_LABELS = {
    "welcome_text": "Приветственное сообщение",
    "company_name": "Название компании",
    "contact_telegram": "Telegram менеджера",
    "contact_phone": "Телефон",
    "contact_email": "Email",
}

PRICES_FORMAT_HINT = (
    "Введите цены по 11 периодам, каждая строка в формате:\n"
    "<code>Период:месяц/ночь</code>\n\n"
    "Пример:\n"
    "<code>Январь:210000/7000\n"
    "Февраль:180000/6000\n"
    "Март:135000/4500\n"
    "Апрель:66000/2200\n"
    "Май:54000/1800\n"
    "Июнь–Август:48000/1600\n"
    "Сентябрь:45000/1500\n"
    "Октябрь:66000/2200\n"
    "Ноябрь:96000/3200\n"
    "1–15 декабря:150000/5000\n"
    "15–31 декабря:210000/7000</code>"
)


def _parse_prices_text(text: str) -> list[dict]:
    result = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        period, rest = line.split(":", 1)
        rest = rest.strip()
        if "/" not in rest:
            continue
        month_s, night_s = rest.split("/", 1)
        try:
            month = int(month_s.strip().replace(" ", ""))
            night = int(night_s.strip().replace(" ", ""))
        except ValueError:
            continue
        result.append({
            "period": period.strip(),
            "price_month_thb": month,
            "price_night_thb": night,
        })
    return result


def _format_property_card(p: dict, show_price_hint: bool = True) -> str:
    bedrooms = p.get("bedrooms")
    bedrooms_text = "студия" if bedrooms == 0 else (str(bedrooms) if bedrooms is not None else "—")
    status_map = {"available": "✅ Доступен", "booked": "🔴 Забронирован"}

    lines = [
        f"<b>{p['title']}</b> ({p['id']})",
        f"Статус: {status_map.get(p.get('status'), p.get('status'))}",
        f"📍 Район: {p.get('district') or '—'}",
    ]
    if p.get("sqm"):
        lines.append(f"📐 Площадь: {p['sqm']} м²")
    lines.append(f"🛏 Спальни: {bedrooms_text}")
    if p.get("view"):
        lines.append(f"🌅 Вид: {p['view']}")
    if p.get("pool_access"):
        lines.append(f"🏊 Бассейн: {p['pool_access']}")
    if p.get("max_guests"):
        mg = p["max_guests"]
        lines.append(f"👥 Макс. гостей: {mg}")
    if p.get("address"):
        lines.append(f"🏠 Адрес: {p['address']}")
    if p.get("map_link"):
        lines.append(f'🗺 <a href="{p["map_link"]}">Показать на карте</a>')

    if p.get("description"):
        lines.append("")
        lines.append(p["description"])

    if p.get("deposit"):
        lines.append("")
        lines.append(f"💳 Депозит: {p['deposit']}")
    if p.get("utilities_included"):
        lines.append(f"🔌 Коммунальные услуги: {p['utilities_included']}")

    lines.append("")
    if show_price_hint:
        lines.append("💰 Нажмите «Рассчитать цену на даты», чтобы узнать стоимость для конкретных дат.")

    links = p.get("links") or []
    if links:
        lines.append("")
        lines.append("🔗 Доп. материалы:")
        for link in links:
            lines.append(link)

    return "\n".join(lines)


# ---------- Регистрация агента + /start ----------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    agent = await db.get_agent_by_telegram_id(message.from_user.id)
    if not agent and not is_admin(message.from_user.id):
        await state.set_state(AgentRegistration.name)
        await message.answer(
            "👋 Похоже, вы здесь впервые. Давайте познакомимся — это займёт 30 секунд.\n\n"
            "Как вас зовут?"
        )
        return
    text = await get_welcome_text()
    await message.answer(text, reply_markup=kb.main_menu_kb(is_admin(message.from_user.id)))


@router.message(Command("getid"))
async def cmd_getid(message: Message):
    await message.answer(
        f"ID этого чата: <code>{message.chat.id}</code>\n\n"
        "Скопируйте это значение в переменную AGENT_LEADS_CHAT_ID на Railway, "
        "чтобы заявки от агентов приходили сюда."
    )


@router.message(AgentRegistration.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AgentRegistration.agency)
    await message.answer("Название вашего агентства?")


@router.message(AgentRegistration.agency)
async def reg_agency(message: Message, state: FSMContext):
    await state.update_data(agency=message.text)
    await state.set_state(AgentRegistration.contact)
    await message.answer("Контакт для связи (телефон/WhatsApp/Telegram)?")


@router.message(AgentRegistration.contact)
async def reg_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.register_agent(
        telegram_id=message.from_user.id,
        telegram_username=message.from_user.username,
        name=data["name"],
        agency=data["agency"],
        contact=message.text,
    )
    await state.clear()
    await message.answer(
        f"Готово, {data['name']}! Теперь у вас есть доступ к каталогу и заявкам.",
        reply_markup=kb.main_menu_kb(is_admin(message.from_user.id)),
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = await get_welcome_text()
    await call.message.edit_text(text, reply_markup=kb.main_menu_kb(is_admin(call.from_user.id)))
    await call.answer()


# ---------- Каталог: тип -> даты -> район -> список ----------
@router.callback_query(F.data == "catalog")
async def cb_catalog(call: CallbackQuery, state: FSMContext):
    await state.update_data(catalog_type=None, catalog_check_in=None, catalog_check_out=None, catalog_district=None)
    await call.message.edit_text("🏡 Выберите тип объекта:", reply_markup=kb.catalog_types_kb())
    await call.answer()


@router.callback_query(F.data.startswith("type:"))
async def cb_type(call: CallbackQuery, state: FSMContext):
    prop_type = call.data.split(":", 1)[1]
    await state.update_data(catalog_type=prop_type)
    await state.set_state(CatalogFlow.check_in)
    label = PROPERTY_TYPES.get(prop_type, prop_type)
    await call.message.edit_text(
        f"{label}\n\nВведите дату заезда (ДД.ММ.ГГГГ), чтобы подобрать варианты и сразу увидеть цену:",
        reply_markup=kb.cancel_kb(),
    )
    await call.answer()


@router.message(CatalogFlow.check_in)
async def catalog_check_in(message: Message, state: FSMContext):
    try:
        check_in = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "Не получилось распознать дату. Введите в формате ДД.ММ.ГГГГ:",
            reply_markup=kb.cancel_kb(),
        )
        return
    await state.update_data(catalog_check_in=check_in.isoformat())
    await state.set_state(CatalogFlow.check_out)
    await message.answer("Дата выезда (ДД.ММ.ГГГГ):", reply_markup=kb.cancel_kb())


@router.message(CatalogFlow.check_out)
async def catalog_check_out(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        check_out = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
        check_in = datetime.fromisoformat(data["catalog_check_in"]).date()
    except ValueError:
        await message.answer(
            "Не получилось распознать дату. Введите в формате ДД.ММ.ГГГГ:",
            reply_markup=kb.cancel_kb(),
        )
        return
    if check_out <= check_in:
        await message.answer(
            "Дата выезда должна быть позже даты заезда. Введите ещё раз:",
            reply_markup=kb.cancel_kb(),
        )
        return

    await state.update_data(catalog_check_out=check_out.isoformat())
    await state.set_state(None)

    prop_type = data["catalog_type"]
    districts = await db.get_districts_by_type(prop_type)
    if not districts:
        await message.answer(
            "По этому типу объектов пока нет доступных вариантов.",
            reply_markup=kb.main_menu_kb(is_admin(message.from_user.id)),
        )
        return

    label = PROPERTY_TYPES.get(prop_type, prop_type)
    await message.answer(
        f"{label}\n📅 {check_in.strftime('%d.%m.%Y')} → {check_out.strftime('%d.%m.%Y')}\n\n"
        "Выберите район:",
        reply_markup=kb.district_list_kb(districts),
    )


@router.callback_query(F.data.startswith("district:"))
async def cb_district(call: CallbackQuery, state: FSMContext):
    district = call.data.split(":", 1)[1]
    data = await state.get_data()
    prop_type = data.get("catalog_type")
    await state.update_data(catalog_district=district)

    items = await db.get_properties_by_type_district(prop_type, district)
    if not items:
        await call.answer("В этом районе пока нет доступных объектов", show_alert=True)
        return

    check_in = datetime.fromisoformat(data["catalog_check_in"]).date()
    check_out = datetime.fromisoformat(data["catalog_check_out"]).date()

    items_with_price = []
    for p in items:
        try:
            result = pricing.calculate_stay_price(check_in, check_out, p.get("prices") or [])
            total = result["total_thb"]
        except pricing.DateRangeError:
            total = None
        items_with_price.append((p, total))

    label = PROPERTY_TYPES.get(prop_type, prop_type)
    await call.message.edit_text(
        f"{label} • 📍 {district}\n📅 {check_in.strftime('%d.%m.%Y')} → {check_out.strftime('%d.%m.%Y')}\n\n"
        "Выберите объект (цена указана за весь период):",
        reply_markup=kb.properties_by_district_kb(items_with_price),
    )
    await call.answer()


@router.callback_query(F.data == "back_to_districts")
async def cb_back_to_districts(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prop_type = data.get("catalog_type")
    districts = await db.get_districts_by_type(prop_type)
    label = PROPERTY_TYPES.get(prop_type, prop_type)
    await call.message.edit_text(
        f"{label}\n\nВыберите район:", reply_markup=kb.district_list_kb(districts)
    )
    await call.answer()


@router.callback_query(F.data.startswith("prop:"))
async def cb_property_card(call: CallbackQuery, state: FSMContext):
    prop_id = call.data.split(":", 1)[1]
    p = await db.get_property_by_id(prop_id)
    if not p:
        await call.answer("Объект не найден", show_alert=True)
        return
    await state.update_data(last_property_id=prop_id)

    data = await state.get_data()
    text = _format_property_card(p, show_price_hint=not (data.get("catalog_check_in") and data.get("catalog_check_out")))

    ci_raw, co_raw = data.get("catalog_check_in"), data.get("catalog_check_out")
    if ci_raw and co_raw:
        check_in = datetime.fromisoformat(ci_raw).date()
        check_out = datetime.fromisoformat(co_raw).date()
        try:
            result = pricing.calculate_stay_price(check_in, check_out, p.get("prices") or [])
            price_lines = [
                f"📅 {check_in.strftime('%d.%m.%Y')} → {check_out.strftime('%d.%m.%Y')} "
                f"({result['nights']} ноч.)",
            ]
            for item in result["breakdown"]:
                if item["nights"] is None:
                    price_lines.append(f"• {item['period']}: {item['amount']:,} THB".replace(",", " "))
                else:
                    price_lines.append(
                        f"• {item['period']}: {item['nights']} × {item['rate']:,} = {item['amount']:,} THB".replace(",", " ")
                    )
            price_lines.append(f"💰 <b>Итого: {result['total_thb']:,} THB</b>".replace(",", " "))
            if result["peak_rule_applied"]:
                price_lines.append(PEAK_RULE_NOTE)
            text = "\n".join(price_lines) + "\n\n" + text
        except pricing.DateRangeError:
            pass

    if len(text) > 4000:
        text = text[:3990] + "\n\n…(сокращено)"

    photos = p.get("photos") or []
    if photos:
        media = [InputMediaPhoto(media=file_id) for file_id in photos[:10]]
        try:
            await call.message.answer_media_group(media=media)
        except Exception as e:
            logger.error("Не удалось отправить фото объекта %s: %s", prop_id, e)

    await call.message.edit_text(
        text, reply_markup=kb.property_card_kb(prop_id), disable_web_page_preview=True
    )
    await call.answer()


# ---------- Расчёт цены по датам ----------
@router.callback_query(F.data.startswith("calc_price:"))
async def cb_calc_price_start(call: CallbackQuery, state: FSMContext):
    prop_id = call.data.split(":", 1)[1]
    p = await db.get_property_by_id(prop_id)
    if not p:
        await call.answer("Объект не найден", show_alert=True)
        return
    await state.update_data(calc_property_id=prop_id)
    await state.set_state(PriceCalc.check_in)
    await call.message.edit_text(
        f"📅 Расчёт цены для <b>{p['title']}</b>\n\n"
        "Введите дату заезда в формате ДД.ММ.ГГГГ (например, 15.12.2026):",
        reply_markup=kb.cancel_kb(),
    )
    await call.answer()


@router.message(PriceCalc.check_in)
async def calc_price_check_in(message: Message, state: FSMContext):
    try:
        check_in = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "Не получилось распознать дату. Введите в формате ДД.ММ.ГГГГ (например, 15.12.2026):",
            reply_markup=kb.cancel_kb(),
        )
        return
    await state.update_data(check_in=check_in.isoformat())
    await state.set_state(PriceCalc.check_out)
    await message.answer(
        "Теперь дату выезда в том же формате (ДД.ММ.ГГГГ):",
        reply_markup=kb.cancel_kb(),
    )


@router.message(PriceCalc.check_out)
async def calc_price_check_out(message: Message, state: FSMContext):
    data = await state.get_data()
    prop_id = data["calc_property_id"]
    check_in = datetime.fromisoformat(data["check_in"]).date()

    try:
        check_out = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "Не получилось распознать дату. Введите в формате ДД.ММ.ГГГГ (например, 25.12.2026):",
            reply_markup=kb.cancel_kb(),
        )
        return

    p = await db.get_property_by_id(prop_id)
    if not p:
        await state.clear()
        await message.answer("Объект больше не найден.", reply_markup=kb.main_menu_kb(is_admin(message.from_user.id)))
        return

    try:
        result = pricing.calculate_stay_price(check_in, check_out, p.get("prices") or [])
    except pricing.DateRangeError as e:
        await message.answer(
            f"⚠️ {e}. Введите дату выезда ещё раз (ДД.ММ.ГГГГ):",
            reply_markup=kb.cancel_kb(),
        )
        return

    await state.update_data(check_out=check_out.isoformat())
    await state.set_state(None)

    lines = [
        f"📅 <b>{p['title']}</b>",
        f"Заезд: {check_in.strftime('%d.%m.%Y')} → Выезд: {check_out.strftime('%d.%m.%Y')}",
        f"Ночей: {result['nights']}",
        "",
    ]
    for item in result["breakdown"]:
        if item["nights"] is None:
            lines.append(f"• {item['period']}: {item['amount']:,} THB ({item['note']})".replace(",", " "))
        else:
            lines.append(
                f"• {item['period']}: {item['nights']} ноч. × {item['rate']:,} = {item['amount']:,} THB".replace(",", " ")
            )
    lines.append("")
    lines.append(f"💰 <b>Итого: {result['total_thb']:,} THB</b>".replace(",", " "))
    if result["peak_rule_applied"]:
        lines.append("")
        lines.append(PEAK_RULE_NOTE)

    await message.answer("\n".join(lines), reply_markup=kb.after_calc_kb(prop_id))


# ---------- Контакты ----------
@router.callback_query(F.data == "contacts")
async def cb_contacts(call: CallbackQuery):
    company_name = await get_company_name()
    tg = await get_contact("telegram", COMPANY_CONTACTS["telegram_manager"])
    phone = await get_contact("phone", COMPANY_CONTACTS["phone"])
    email = await get_contact("email", COMPANY_CONTACTS["email"])
    text = (
        f"📞 <b>Контакты {company_name}</b>\n\n"
        f"Telegram: {tg}\n"
        f"Телефон: {phone}\n"
        f"Email: {email}\n"
    )
    await call.message.edit_text(text, reply_markup=kb.contacts_kb())
    await call.answer()


# ---------- Заявка ----------
@router.callback_query(F.data == "lead_start")
async def cb_lead_start(call: CallbackQuery, state: FSMContext):
    await state.update_data(property_id=None, property_title=None, dates_prefilled=False)
    await state.set_state(LeadForm.name)
    await call.message.edit_text("📝 Как зовут вашего клиента?", reply_markup=kb.cancel_kb())
    await call.answer()


@router.callback_query(F.data.startswith("lead_for:"))
async def cb_lead_for_property(call: CallbackQuery, state: FSMContext):
    prop_id = call.data.split(":", 1)[1]
    p = await db.get_property_by_id(prop_id)
    title = p["title"] if p else prop_id
    await state.update_data(property_id=prop_id, property_title=title)

    data = await state.get_data()
    ci_raw, co_raw = data.get("catalog_check_in"), data.get("catalog_check_out")
    if ci_raw and co_raw:
        check_in = datetime.fromisoformat(ci_raw).date()
        check_out = datetime.fromisoformat(co_raw).date()
        dates_str = f"{check_in.strftime('%d.%m.%Y')} - {check_out.strftime('%d.%m.%Y')}"
        await state.update_data(dates=dates_str, dates_prefilled=True)
    else:
        await state.update_data(dates_prefilled=False)

    await state.set_state(LeadForm.name)
    await call.message.edit_text(
        f"📝 Заявка по объекту: <b>{title}</b>\n\nКак зовут вашего клиента?",
        reply_markup=kb.cancel_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "lead_cancel")
async def cb_lead_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "Заявка отменена.", reply_markup=kb.main_menu_kb(is_admin(call.from_user.id))
    )
    await call.answer()


@router.message(LeadForm.name)
async def lead_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(LeadForm.contact)
    await message.answer("Контакт клиента (телефон/WhatsApp/Telegram)?", reply_markup=kb.cancel_kb())


@router.message(LeadForm.contact)
async def lead_contact(message: Message, state: FSMContext):
    await state.update_data(contact=message.text)
    data = await state.get_data()
    if data.get("dates_prefilled"):
        await state.set_state(LeadForm.budget)
        await message.answer(
            f"📅 Даты: {data.get('dates')} (взяты из подбора)\n\n"
            "Бюджет клиента? (можно пропустить)",
            reply_markup=kb.skip_kb(),
        )
        return
    await state.set_state(LeadForm.dates)
    await message.answer("На какие даты?", reply_markup=kb.cancel_kb())


@router.message(LeadForm.dates)
async def lead_dates(message: Message, state: FSMContext):
    await state.update_data(dates=message.text)
    await state.set_state(LeadForm.budget)
    await message.answer("Бюджет клиента? (можно пропустить)", reply_markup=kb.skip_kb())


@router.callback_query(LeadForm.budget, F.data == "lead_skip")
async def lead_budget_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(budget="не указан")
    await _ask_comment(call.message, state)
    await call.answer()


@router.message(LeadForm.budget)
async def lead_budget(message: Message, state: FSMContext):
    await state.update_data(budget=message.text)
    await _ask_comment(message, state)


async def _ask_comment(message: Message, state: FSMContext):
    await state.set_state(LeadForm.comment)
    await message.answer("Комментарий? (можно пропустить)", reply_markup=kb.skip_kb())


@router.callback_query(LeadForm.comment, F.data == "lead_skip")
async def lead_comment_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(comment="—")
    await _show_summary(call.message, state)
    await call.answer()


@router.message(LeadForm.comment)
async def lead_comment(message: Message, state: FSMContext):
    await state.update_data(comment=message.text)
    await _show_summary(message, state)


async def _show_summary(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(LeadForm.confirm)
    lines = ["Проверьте заявку:\n"]
    if data.get("property_title"):
        lines.append(f"🏠 Объект: {data['property_title']}")
    lines.append(f"👤 Клиент: {data.get('name')}")
    lines.append(f"📞 Контакт: {data.get('contact')}")
    lines.append(f"📅 Даты: {data.get('dates')}")
    lines.append(f"💰 Бюджет: {data.get('budget')}")
    lines.append(f"💬 Комментарий: {data.get('comment')}")
    await message.answer("\n".join(lines), reply_markup=kb.confirm_lead_kb())


@router.callback_query(LeadForm.confirm, F.data == "lead_confirm")
async def lead_confirm(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = call.from_user

    agent = await db.get_agent_by_telegram_id(user.id)
    agent_id = agent["id"] if agent else None
    agent_label = f"{agent['name']} ({agent['agency']})" if agent else "не зарегистрирован"

    await db.create_lead(
        source="agent",
        property_id=data.get("property_id"),
        property_title=data.get("property_title"),
        client_name=data.get("name"),
        client_contact=data.get("contact"),
        dates=data.get("dates"),
        budget=data.get("budget"),
        comment=data.get("comment"),
        agent_id=agent_id,
        telegram_user_id=user.id,
        telegram_username=user.username,
    )

    company_name = await get_company_name()
    lead_text_lines = [
        f"🆕 <b>Новая заявка от агента — {company_name}</b>",
        "",
        f"🧑‍💼 Агент: {agent_label}",
    ]
    if data.get("property_title"):
        lead_text_lines.append(f"🏠 Объект: {data['property_title']}")
    lead_text_lines += [
        f"👤 Клиент: {data.get('name')}",
        f"📞 Контакт клиента: {data.get('contact')}",
        f"📅 Даты: {data.get('dates')}",
        f"💰 Бюджет: {data.get('budget')}",
        f"💬 Комментарий: {data.get('comment')}",
        "",
        f"Telegram агента: @{user.username}" if user.username else f"Telegram ID агента: {user.id}",
    ]
    lead_text = "\n".join(lead_text_lines)

    if AGENT_LEADS_CHAT_ID:
        try:
            await bot.send_message(AGENT_LEADS_CHAT_ID, lead_text)
        except Exception as e:
            logger.error("Не удалось отправить заявку: %s", e)
    else:
        logger.warning("AGENT_LEADS_CHAT_ID не настроен: %s", lead_text)

    await state.clear()
    await call.message.edit_text(
        "✅ Заявка отправлена менеджеру!",
        reply_markup=kb.main_menu_kb(is_admin(user.id)),
    )
    await call.answer("Отправлено!")


# ================= АДМИН-ПАНЕЛЬ =================

@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text("⚙️ Админ-панель:", reply_markup=kb.admin_menu_kb())
    await call.answer()


@router.callback_query(F.data == "admin_properties_menu")
async def cb_admin_properties_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text("🏠 Объекты:", reply_markup=kb.admin_properties_menu_kb())
    await call.answer()


# ---- Агенты ----
@router.callback_query(F.data == "admin_agents_menu")
async def cb_admin_agents_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text("👥 Агенты:", reply_markup=kb.admin_agents_menu_kb())
    await call.answer()


@router.callback_query(F.data == "admin_agents")
async def cb_admin_agents(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    agents = await db.get_all_agents_with_stats()
    if not agents:
        text = "Пока нет зарегистрированных агентов."
    else:
        lines = ["👥 <b>Агенты</b>\n"]
        for a in agents:
            lines.append(
                f"• {a['name']} ({a['agency']}) — заявок: {a['leads_count']}, "
                f"контакт: {a.get('contact') or '—'}"
            )
        text = "\n".join(lines)
    await call.message.edit_text(text, reply_markup=kb.admin_agents_menu_kb())
    await call.answer()


@router.callback_query(F.data == "admin_agents_delete")
async def cb_admin_agents_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    markup = await kb.admin_agents_pick_kb()
    await call.message.edit_text("Выберите агента для удаления:", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("admin_agent_del_pick:"))
async def cb_admin_agent_del_pick(call: CallbackQuery):
    agent_id = int(call.data.split(":", 1)[1])
    agent = await db.get_agent_by_id(agent_id)
    if not agent:
        await call.answer("Агент не найден", show_alert=True)
        return
    await call.message.edit_text(
        f"Удалить агента <b>{agent['name']} ({agent['agency']})</b>? "
        "Он сможет заново зарегистрироваться через /start.",
        reply_markup=kb.admin_agent_confirm_delete_kb(agent_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_agent_del_confirm:"))
async def cb_admin_agent_del_confirm(call: CallbackQuery):
    agent_id = int(call.data.split(":", 1)[1])
    await db.delete_agent(agent_id)
    await call.message.edit_text("Агент удалён.", reply_markup=kb.admin_agents_menu_kb())
    await call.answer("Удалено")


# ---- Заявки ----
@router.callback_query(F.data == "admin_leads")
async def cb_admin_leads(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    leads = await db.get_recent_leads(15)
    if not leads:
        text = "Заявок пока не было."
    else:
        lines = ["📨 <b>Последние заявки</b>\n"]
        for l in leads:
            src = "агент" if l["source"] == "agent" else "гость"
            agent_part = f" • {l['agent_name']} ({l['agent_agency']})" if l.get("agent_name") else ""
            when = l["created_at"].strftime("%d.%m %H:%M") if l.get("created_at") else ""
            lines.append(
                f"• {when} [{src}]{agent_part}\n"
                f"  {l.get('property_title') or '—'} · {l.get('client_name')} · {l.get('dates')}"
            )
        text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n\n…(сокращено)"
    await call.message.edit_text(text, reply_markup=kb.back_to_admin_kb())
    await call.answer()


# ---- Статистика ----
@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    s = await db.get_stats()
    by_type_lines = "\n".join(f"  • {t}: {c}" for t, c in s["by_type"].items())
    by_status_lines = "\n".join(f"  • {st}: {c}" for st, c in s["by_status"].items())
    by_source_lines = "\n".join(f"  • {src}: {c}" for src, c in s["leads_by_source"].items()) or "  —"
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"🏠 Объектов всего: {s['total_properties']}\n{by_type_lines}\n\n"
        f"Статусы:\n{by_status_lines}\n\n"
        f"👥 Агентов: {s['total_agents']}\n\n"
        f"📨 Заявок всего: {s['total_leads']}\n"
        f"  • сегодня: {s['leads_today']}\n"
        f"  • за 7 дней: {s['leads_week']}\n"
        f"  По источнику:\n{by_source_lines}"
    )
    await call.message.edit_text(text, reply_markup=kb.back_to_admin_kb())
    await call.answer()


# ---- Настройки бота ----
@router.callback_query(F.data == "admin_settings_menu")
async def cb_admin_settings_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text("⚙️ Настройки бота:", reply_markup=kb.admin_settings_menu_kb())
    await call.answer()


@router.callback_query(F.data.startswith("admin_setting_edit:"))
async def cb_admin_setting_edit(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":", 1)[1]
    defaults = {
        "welcome_text": WELCOME_TEXT,
        "company_name": COMPANY_NAME,
        "contact_telegram": COMPANY_CONTACTS["telegram_manager"],
        "contact_phone": COMPANY_CONTACTS["phone"],
        "contact_email": COMPANY_CONTACTS["email"],
    }
    current = await db.get_setting(key, defaults.get(key, ""))
    label = SETTINGS_LABELS.get(key, key)
    await state.update_data(setting_key=key)
    await state.set_state(AdminSettingEdit.waiting_value)
    await call.message.edit_text(
        f"✏️ <b>{label}</b>\n\nТекущее значение:\n{current}\n\nВведите новое значение:"
    )
    await call.answer()


@router.message(AdminSettingEdit.waiting_value)
async def admin_setting_apply(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data["setting_key"]
    await db.set_setting(key, message.text)
    await state.clear()
    label = SETTINGS_LABELS.get(key, key)
    await message.answer(f"Готово, «{label}» обновлено.", reply_markup=kb.admin_settings_menu_kb())


# ---- Рассылка агентам ----
@router.callback_query(F.data == "admin_broadcast_start")
async def cb_admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    await state.set_state(AdminBroadcast.waiting_message)
    await call.message.edit_text("Введите текст сообщения для рассылки всем агентам:")
    await call.answer()


@router.message(AdminBroadcast.waiting_message)
async def admin_broadcast_preview(message: Message, state: FSMContext):
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminBroadcast.confirming)
    await message.answer(
        f"Предпросмотр:\n\n{message.text}\n\nОтправить всем агентам?",
        reply_markup=kb.admin_broadcast_confirm_kb(),
    )


@router.callback_query(AdminBroadcast.confirming, F.data == "admin_broadcast_confirm")
async def admin_broadcast_send(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    ids = await db.get_all_agent_telegram_ids()
    sent, failed = 0, 0
    for tg_id in ids:
        try:
            await bot.send_message(tg_id, f"📢 {text}")
            sent += 1
        except Exception as e:
            logger.warning("Рассылка: не удалось отправить агенту %s: %s", tg_id, e)
            failed += 1
    await state.clear()
    await call.message.edit_text(
        f"Готово. Отправлено: {sent}, не удалось: {failed}.",
        reply_markup=kb.admin_menu_kb(),
    )
    await call.answer()


# ---- Удаление объекта ----
@router.callback_query(F.data == "admin_delete")
async def cb_admin_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    markup = await kb.admin_pick_property_kb("admin_delete_pick")
    await call.message.edit_text("Выберите объект для удаления:", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("admin_delete_pick:"))
async def cb_admin_delete_pick(call: CallbackQuery):
    prop_id = call.data.split(":", 1)[1]
    await call.message.edit_text(
        f"Точно удалить объект <b>{prop_id}</b>? Это необратимо.",
        reply_markup=kb.admin_confirm_delete_kb(prop_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_delete_confirm:"))
async def cb_admin_delete_confirm(call: CallbackQuery):
    prop_id = call.data.split(":", 1)[1]
    await db.delete_property(prop_id)
    await call.message.edit_text(f"Объект {prop_id} удалён.", reply_markup=kb.admin_properties_menu_kb())
    await call.answer("Удалено")


# ---- Быстрый статус ----
@router.callback_query(F.data == "admin_status")
async def cb_admin_status(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    markup = await kb.admin_pick_property_kb("admin_status_pick")
    await call.message.edit_text("Выберите объект:", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("admin_status_pick:"))
async def cb_admin_status_pick(call: CallbackQuery):
    prop_id = call.data.split(":", 1)[1]
    await call.message.edit_text(
        f"Новый статус для {prop_id}:", reply_markup=kb.admin_status_pick_value_kb(prop_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_status_set:"))
async def cb_admin_status_set(call: CallbackQuery):
    _, prop_id, new_status = call.data.split(":", 2)
    await db.update_property_field(prop_id, "status", new_status)
    await call.message.edit_text(
        f"Статус {prop_id} обновлён: {new_status}", reply_markup=kb.admin_properties_menu_kb()
    )
    await call.answer("Готово")


# ---- Редактирование поля ----
@router.callback_query(F.data == "admin_edit")
async def cb_admin_edit(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    markup = await kb.admin_pick_property_kb("admin_edit_pick")
    await call.message.edit_text("Выберите объект для редактирования:", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("admin_edit_pick:"))
async def cb_admin_edit_pick(call: CallbackQuery):
    prop_id = call.data.split(":", 1)[1]
    await call.message.edit_text(
        f"Что меняем в {prop_id}?", reply_markup=kb.admin_edit_fields_kb(prop_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_edit_field:"))
async def cb_admin_edit_field(call: CallbackQuery, state: FSMContext):
    _, prop_id, field = call.data.split(":", 2)
    await state.update_data(edit_property_id=prop_id, edit_field=field)
    await state.set_state(AdminEditField.waiting_value)
    await call.message.edit_text(f"Введите новое значение для «{field}»:")
    await call.answer()


@router.message(AdminEditField.waiting_value)
async def admin_edit_apply(message: Message, state: FSMContext):
    data = await state.get_data()
    prop_id = data["edit_property_id"]
    field = data["edit_field"]
    value = message.text
    if field in ("bedrooms", "max_guests"):
        try:
            value = int(value)
        except ValueError:
            await message.answer("Нужно число. Попробуйте ещё раз.")
            return
    await db.update_property_field(prop_id, field, value)
    await state.clear()
    await message.answer(f"Готово, {field} обновлено.", reply_markup=kb.admin_properties_menu_kb())


# ---- Редактирование типа объекта ----
@router.callback_query(F.data.startswith("admin_edit_type:"))
async def cb_admin_edit_type(call: CallbackQuery):
    prop_id = call.data.split(":", 1)[1]
    await call.message.edit_text(
        f"Новый тип для {prop_id}:", reply_markup=kb.admin_edit_type_pick_kb(prop_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_edit_type_set:"))
async def cb_admin_edit_type_set(call: CallbackQuery):
    _, prop_id, new_type = call.data.split(":", 2)
    await db.update_property_field(prop_id, "type", new_type)
    await call.message.edit_text(
        f"Тип объекта {prop_id} обновлён.", reply_markup=kb.admin_properties_menu_kb()
    )
    await call.answer("Готово")


# ---- Редактирование цен (все периоды разом) ----
@router.callback_query(F.data.startswith("admin_edit_prices:"))
async def cb_admin_edit_prices(call: CallbackQuery, state: FSMContext):
    prop_id = call.data.split(":", 1)[1]
    p = await db.get_property_by_id(prop_id)
    current_lines = []
    for period in (p.get("prices") or []):
        current_lines.append(f"{period['period']}:{period['price_month_thb']}/{period['price_night_thb']}")
    current_text = "\n".join(current_lines) if current_lines else "(цены не заданы)"
    await state.update_data(edit_property_id=prop_id)
    await state.set_state(AdminEditPrices.waiting_text)
    await call.message.edit_text(
        f"Текущие цены для {prop_id}:\n<code>{current_text}</code>\n\n"
        f"Пришлите новый список полностью (заменит старый):\n\n{PRICES_FORMAT_HINT}"
    )
    await call.answer()


@router.message(AdminEditPrices.waiting_text)
async def admin_edit_prices_apply(message: Message, state: FSMContext):
    prices = _parse_prices_text(message.text)
    if not prices:
        await message.answer(
            "Не удалось распознать цены. Проверьте формат и отправьте ещё раз.\n\n"
            + PRICES_FORMAT_HINT
        )
        return
    data = await state.get_data()
    prop_id = data["edit_property_id"]
    await db.update_property_prices(prop_id, prices)
    await state.clear()
    await message.answer(
        f"Готово, цены для {prop_id} обновлены ({len(prices)} периодов).",
        reply_markup=kb.admin_properties_menu_kb(),
    )


# ---- Редактирование ссылок ----
@router.callback_query(F.data.startswith("admin_edit_links:"))
async def cb_admin_edit_links(call: CallbackQuery, state: FSMContext):
    prop_id = call.data.split(":", 1)[1]
    p = await db.get_property_by_id(prop_id)
    current = "\n".join(p.get("links") or []) or "(ссылок нет)"
    await state.update_data(edit_property_id=prop_id)
    await state.set_state(AdminEditLinks.waiting_text)
    await call.message.edit_text(
        f"Текущие ссылки для {prop_id}:\n{current}\n\n"
        "Пришлите новый список ссылок, каждая с новой строки (заменит старый). "
        "Чтобы очистить - отправьте «-»."
    )
    await call.answer()


@router.message(AdminEditLinks.waiting_text)
async def admin_edit_links_apply(message: Message, state: FSMContext):
    text = message.text.strip()
    links = [] if text == "-" else [l.strip() for l in text.splitlines() if l.strip()]
    data = await state.get_data()
    prop_id = data["edit_property_id"]
    await db.update_property_links(prop_id, links)
    await state.clear()
    await message.answer(
        f"Готово, ссылки для {prop_id} обновлены ({len(links)} шт.).",
        reply_markup=kb.admin_properties_menu_kb(),
    )


# ---- Фото объекта ----
@router.callback_query(F.data == "admin_photos")
async def cb_admin_photos(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    markup = await kb.admin_pick_property_kb("admin_photos_pick")
    await call.message.edit_text("Выберите объект:", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("admin_photos_pick:"))
async def cb_admin_photos_pick(call: CallbackQuery):
    prop_id = call.data.split(":", 1)[1]
    p = await db.get_property_by_id(prop_id)
    count = len(p.get("photos") or []) if p else 0
    await call.message.edit_text(
        f"🖼 Фото объекта {prop_id} (сейчас: {count} шт.):",
        reply_markup=kb.admin_photos_menu_kb(prop_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_photos_add:"))
async def cb_admin_photos_add(call: CallbackQuery, state: FSMContext):
    prop_id = call.data.split(":", 1)[1]
    await state.update_data(photos_property_id=prop_id)
    await state.set_state(AdminPhotoUpload.uploading)
    await call.message.edit_text(
        "Отправляйте фото по одному (можно несколько сообщений подряд). "
        "Когда закончите — напишите «Готово»."
    )
    await call.answer()


@router.message(AdminPhotoUpload.uploading, F.photo)
async def admin_photo_received(message: Message, state: FSMContext):
    data = await state.get_data()
    prop_id = data["photos_property_id"]
    file_id = message.photo[-1].file_id
    count = await db.append_property_photo(prop_id, file_id)
    await message.answer(f"📸 Добавлено. Всего фото у объекта: {count}. Ещё, или «Готово»?")


@router.message(AdminPhotoUpload.uploading, F.text.lower().in_({"готово", "done", "/done"}))
async def admin_photo_done(message: Message, state: FSMContext):
    data = await state.get_data()
    prop_id = data["photos_property_id"]
    await state.clear()
    await message.answer(
        f"Готово, загрузка фото для {prop_id} завершена.",
        reply_markup=kb.admin_properties_menu_kb(),
    )


@router.callback_query(F.data.startswith("admin_photos_view:"))
async def cb_admin_photos_view(call: CallbackQuery):
    prop_id = call.data.split(":", 1)[1]
    p = await db.get_property_by_id(prop_id)
    photos = (p.get("photos") or []) if p else []
    if not photos:
        await call.answer("У этого объекта пока нет фото", show_alert=True)
        return
    media = [InputMediaPhoto(media=file_id) for file_id in photos[:10]]
    await call.message.answer_media_group(media=media)
    await call.answer()


@router.callback_query(F.data.startswith("admin_photos_clear:"))
async def cb_admin_photos_clear(call: CallbackQuery):
    prop_id = call.data.split(":", 1)[1]
    await db.clear_property_photos(prop_id)
    await call.message.edit_text(
        f"Все фото объекта {prop_id} удалены.", reply_markup=kb.admin_properties_menu_kb()
    )
    await call.answer("Удалено")


# ---- Добавление нового объекта ----
@router.callback_query(F.data == "admin_add")
async def cb_admin_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещён", show_alert=True)
        return
    await state.set_state(AdminAddProperty.id)
    await call.message.edit_text(
        "Добавляем новый объект.\n\nВведите ID/тикер (например, XYZ-100):"
    )
    await call.answer()


@router.message(AdminAddProperty.id)
async def admin_add_id(message: Message, state: FSMContext):
    existing = await db.get_property_by_id(message.text.strip())
    if existing:
        await message.answer("Объект с таким ID уже есть. Введите другой ID:")
        return
    await state.update_data(id=message.text.strip())
    await state.set_state(AdminAddProperty.title)
    await message.answer("Название объекта:")


@router.message(AdminAddProperty.title)
async def admin_add_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdminAddProperty.district)
    await message.answer("Район:")


@router.message(AdminAddProperty.district)
async def admin_add_district(message: Message, state: FSMContext):
    await state.update_data(district=message.text)
    await state.set_state(AdminAddProperty.bedrooms)
    await message.answer("Количество спален (0 - если студия):")


@router.message(AdminAddProperty.bedrooms)
async def admin_add_bedrooms(message: Message, state: FSMContext):
    try:
        bedrooms = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно число. Введите количество спален:")
        return
    await state.update_data(bedrooms=bedrooms)
    await state.set_state(AdminAddProperty.sqm)
    await message.answer("Площадь в м² (можно текстом, напр. '85+15'):")


@router.message(AdminAddProperty.sqm)
async def admin_add_sqm(message: Message, state: FSMContext):
    await state.update_data(sqm=message.text)
    await state.set_state(AdminAddProperty.view)
    await message.answer("Вид (напр. sea view, пусто - просто '-'):")


@router.message(AdminAddProperty.view)
async def admin_add_view(message: Message, state: FSMContext):
    view = message.text.strip()
    await state.update_data(view="" if view == "-" else view)
    await state.set_state(AdminAddProperty.pool_access)
    await message.answer("Бассейн (common / private / нет):")


@router.message(AdminAddProperty.pool_access)
async def admin_add_pool(message: Message, state: FSMContext):
    await state.update_data(pool_access=message.text)
    await state.set_state(AdminAddProperty.address)
    await message.answer("Адрес (или '-' если нет):")


@router.message(AdminAddProperty.address)
async def admin_add_address(message: Message, state: FSMContext):
    address = message.text.strip()
    await state.update_data(address=None if address == "-" else address)
    await state.set_state(AdminAddProperty.map_link)
    await message.answer("Ссылка на карту (или '-' если нет):")


@router.message(AdminAddProperty.map_link)
async def admin_add_maplink(message: Message, state: FSMContext):
    link = message.text.strip()
    await state.update_data(map_link=None if link == "-" else link)
    await state.set_state(AdminAddProperty.max_guests)
    await message.answer("Максимум гостей (число, или '-' если неизвестно):")


@router.message(AdminAddProperty.max_guests)
async def admin_add_maxguests(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "-":
        max_guests = None
    else:
        try:
            max_guests = int(text)
        except ValueError:
            await message.answer("Нужно число или '-'. Попробуйте ещё раз:")
            return
    await state.update_data(max_guests=max_guests)
    await state.set_state(AdminAddProperty.description)
    await message.answer("Краткое описание объекта (или '-' если пропустить):")


@router.message(AdminAddProperty.description)
async def admin_add_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    await state.update_data(description="" if desc == "-" else desc)
    await state.set_state(AdminAddProperty.deposit)
    await message.answer("Депозит (например, «1 месяц аренды», или '-' если нет):")


@router.message(AdminAddProperty.deposit)
async def admin_add_deposit(message: Message, state: FSMContext):
    deposit = message.text.strip()
    await state.update_data(deposit=None if deposit == "-" else deposit)
    await state.set_state(AdminAddProperty.utilities)
    await message.answer(
        "Коммунальные услуги - что входит, что оплачивается отдельно "
        "(например, «Интернет и уборка включены, электричество отдельно», или '-'):"
    )


@router.message(AdminAddProperty.utilities)
async def admin_add_utilities(message: Message, state: FSMContext):
    utilities = message.text.strip()
    await state.update_data(utilities_included=None if utilities == "-" else utilities)
    await state.set_state(AdminAddProperty.prices_text)
    await message.answer(PRICES_FORMAT_HINT)


@router.message(AdminAddProperty.prices_text)
async def admin_add_prices(message: Message, state: FSMContext):
    prices = _parse_prices_text(message.text)
    if not prices:
        await message.answer(
            "Не удалось распознать цены. Проверьте формат и отправьте ещё раз.\n\n"
            + PRICES_FORMAT_HINT
        )
        return
    data = await state.get_data()
    prop = {
        "id": data["id"],
        "type": "apartment",  # уточним типом отдельно ниже
        "title": data["title"],
        "district": data["district"],
        "bedrooms": data["bedrooms"],
        "sqm": data["sqm"],
        "view": data.get("view", ""),
        "pool_access": data["pool_access"],
        "address": data.get("address"),
        "map_link": data.get("map_link"),
        "max_guests": data.get("max_guests"),
        "links": [],
        "prices": prices,
        "currency": "THB",
        "description": data.get("description", ""),
        "deposit": data.get("deposit"),
        "utilities_included": data.get("utilities_included"),
        "photos": [],
        "status": "available",
    }
    await state.update_data(_pending_property=prop)
    await message.answer("Тип объекта:", reply_markup=kb.admin_type_pick_kb())


@router.callback_query(F.data.startswith("admin_new_type:"))
async def admin_add_type_final(call: CallbackQuery, state: FSMContext):
    prop_type = call.data.split(":", 1)[1]
    data = await state.get_data()
    prop = data.get("_pending_property")
    if not prop:
        await call.answer("Что-то пошло не так, начните заново через /start", show_alert=True)
        await state.clear()
        return
    prop["type"] = prop_type
    await db.upsert_property(prop)
    await state.clear()
    await call.message.edit_text(
        f"✅ Объект {prop['id']} добавлен!", reply_markup=kb.admin_properties_menu_kb()
    )
    await call.answer("Сохранено")

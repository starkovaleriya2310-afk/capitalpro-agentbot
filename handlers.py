import logging

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

import db
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
    prices_text = State()


class AdminEditField(StatesGroup):
    waiting_value = State()


WELCOME_TEXT = (
    f"👋 Добро пожаловать в агентский бот <b>{COMPANY_NAME}</b>!\n\n"
    "Здесь актуальные цены на объекты (уже с учётом комиссии) и быстрая "
    "отправка заявок по вашим клиентам."
)

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


def _format_property_card(p: dict) -> str:
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

    prices = p.get("prices") or []
    if prices:
        lines.append("")
        lines.append(f"💰 <b>Цены по сезонам ({p.get('currency', 'THB')}, для агентов):</b>")
        for period in prices:
            lines.append(
                f"• {period['period']}: {period['price_month_thb']:,} /мес "
                f"({period['price_night_thb']:,} /ночь)".replace(",", " ")
            )
        lines.append("")
        lines.append(PEAK_RULE_NOTE)

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
    await message.answer(WELCOME_TEXT, reply_markup=kb.main_menu_kb(is_admin(message.from_user.id)))


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
    await call.message.edit_text(WELCOME_TEXT, reply_markup=kb.main_menu_kb(is_admin(call.from_user.id)))
    await call.answer()


# ---------- Каталог ----------
@router.callback_query(F.data == "catalog")
async def cb_catalog(call: CallbackQuery):
    await call.message.edit_text("🏡 Выберите тип объекта:", reply_markup=kb.catalog_types_kb())
    await call.answer()


@router.callback_query(F.data.startswith("type:"))
async def cb_type(call: CallbackQuery, state: FSMContext):
    prop_type = call.data.split(":", 1)[1]
    await state.update_data(last_type=prop_type)
    label = PROPERTY_TYPES.get(prop_type, prop_type)
    markup = await kb.properties_list_kb(prop_type)
    await call.message.edit_text(f"{label}\n\nВыберите объект:", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data == "back_to_list")
async def cb_back_to_list(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prop_type = data.get("last_type", "villa")
    label = PROPERTY_TYPES.get(prop_type, prop_type)
    markup = await kb.properties_list_kb(prop_type)
    await call.message.edit_text(f"{label}\n\nВыберите объект:", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("prop:"))
async def cb_property_card(call: CallbackQuery, state: FSMContext):
    prop_id = call.data.split(":", 1)[1]
    p = await db.get_property_by_id(prop_id)
    if not p:
        await call.answer("Объект не найден", show_alert=True)
        return
    await state.update_data(last_property_id=prop_id)
    text = _format_property_card(p)
    if len(text) > 4000:
        text = text[:3990] + "\n\n…(сокращено)"
    await call.message.edit_text(
        text, reply_markup=kb.property_card_kb(prop_id), disable_web_page_preview=True
    )
    await call.answer()


# ---------- Контакты ----------
@router.callback_query(F.data == "contacts")
async def cb_contacts(call: CallbackQuery):
    text = (
        f"📞 <b>Контакты {COMPANY_NAME}</b>\n\n"
        f"Telegram: {COMPANY_CONTACTS['telegram_manager']}\n"
        f"Телефон: {COMPANY_CONTACTS['phone']}\n"
        f"Email: {COMPANY_CONTACTS['email']}\n"
    )
    await call.message.edit_text(text, reply_markup=kb.contacts_kb())
    await call.answer()


# ---------- Заявка ----------
@router.callback_query(F.data == "lead_start")
async def cb_lead_start(call: CallbackQuery, state: FSMContext):
    await state.update_data(property_id=None, property_title=None)
    await state.set_state(LeadForm.name)
    await call.message.edit_text("📝 Как зовут вашего клиента?", reply_markup=kb.cancel_kb())
    await call.answer()


@router.callback_query(F.data.startswith("lead_for:"))
async def cb_lead_for_property(call: CallbackQuery, state: FSMContext):
    prop_id = call.data.split(":", 1)[1]
    p = await db.get_property_by_id(prop_id)
    title = p["title"] if p else prop_id
    await state.update_data(property_id=prop_id, property_title=title)
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

    lead_text_lines = [
        "🆕 <b>Новая заявка от агента — Capital Pro | Phuket</b>",
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
    await call.message.edit_text(text, reply_markup=kb.admin_menu_kb())
    await call.answer()


# ---- Удаление ----
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
    await call.message.edit_text(f"Объект {prop_id} удалён.", reply_markup=kb.admin_menu_kb())
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
        f"Статус {prop_id} обновлён: {new_status}", reply_markup=kb.admin_menu_kb()
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
    await message.answer(f"Готово, {field} обновлено.", reply_markup=kb.admin_menu_kb())


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
        f"✅ Объект {prop['id']} добавлен!", reply_markup=kb.admin_menu_kb()
    )
    await call.answer("Сохранено")

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import PROPERTY_TYPES
import db

# Группы районов для нового флоу "Район → Тип". Rawai/Naiharn и Kata/Karon
# объединены в одну кнопку — у них общая небольшая база объектов.
DISTRICT_GROUPS = [
    ("rawai_naiharn", "📍 Rawai / Naiharn", ["Rawai", "Naiharn"]),
    ("kata_karon", "📍 Kata / Karon", ["Kata", "Karon"]),
    ("bangtao", "📍 Bangtao", ["Bangtao"]),
    ("layan", "📍 Layan", ["Layan"]),
    ("surin", "📍 Surin", ["Surin"]),
    ("kamala", "📍 Kamala", ["Kamala"]),
    ("naiyang", "📍 Naiyang", ["Naiyang"]),
    ("maikhao", "📍 Maikhao", ["Maikhao"]),
]


def get_group_by_slug(slug: str):
    for s, label, districts in DISTRICT_GROUPS:
        if s == slug:
            return label, districts
    return None, []


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🏡 Каталог объектов", callback_data="catalog")
    b.button(text="📝 Оставить заявку", callback_data="lead_start")
    b.button(text="📞 Контакты", callback_data="contacts")
    if is_admin:
        b.button(text="⚙️ Админ-панель", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


async def district_groups_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    existing = set(await db.get_all_districts())
    for slug, label, districts in DISTRICT_GROUPS:
        if any(d in existing for d in districts):
            b.button(text=label, callback_data=f"distgroup:{slug}")
    b.button(text="⬅️ В главное меню", callback_data="main_menu")
    b.adjust(1)
    return b.as_markup()


def types_for_group_kb(slug: str, types: list[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in types:
        label = PROPERTY_TYPES.get(t, t)
        b.button(text=label, callback_data=f"type_for:{slug}:{t}")
    b.button(text="⬅️ К районам", callback_data="catalog")
    b.adjust(1)
    return b.as_markup()


def browse_or_dates_kb(slug: str, prop_type: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📋 Показать все объекты", callback_data=f"browse:{slug}:{prop_type}")
    b.button(text="📅 Указать даты (сразу с ценой)", callback_data=f"dates_for:{slug}:{prop_type}")
    b.button(text="⬅️ К типам", callback_data=f"distgroup:{slug}")
    b.adjust(1)
    return b.as_markup()


async def properties_list_kb(property_type: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    items = await db.get_properties_by_type(property_type)
    for p in items:
        icon = "✅" if p["status"] == "available" else "🔴"
        label = f"{icon} {p['title']} — {p['district']}"
        b.button(text=label, callback_data=f"prop:{p['id']}")
    b.button(text="⬅️ К типам объектов", callback_data="catalog")
    b.adjust(1)
    return b.as_markup()


def properties_by_group_kb(slug: str, items_with_price: list[tuple]) -> InlineKeyboardMarkup:
    """items_with_price: список (property_dict, total_thb или None)"""
    b = InlineKeyboardBuilder()
    for p, total in items_with_price:
        title = p["title"]
        if total is not None:
            price_part = f" — {total:,} THB".replace(",", " ")
        else:
            price_part = ""
        label = f"{title}{price_part}"
        if len(label) > 64:
            max_title_len = 64 - len(price_part) - 1
            label = f"{title[:max_title_len]}…{price_part}"
        b.button(text=label, callback_data=f"prop:{p['id']}")
    b.button(text="⬅️ К районам", callback_data="catalog")
    b.adjust(1)
    return b.as_markup()


def property_card_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📅 Рассчитать цену на другие даты", callback_data=f"calc_price:{property_id}")
    b.button(text="📝 Заявка по этому объекту", callback_data=f"lead_for:{property_id}")
    b.button(text="⬅️ К каталогу", callback_data="catalog")
    b.button(text="🏠 В главное меню", callback_data="main_menu")
    b.adjust(1)
    return b.as_markup()


def contacts_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📝 Оставить заявку", callback_data="lead_start")
    b.button(text="⬅️ В главное меню", callback_data="main_menu")
    b.adjust(1)
    return b.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="❌ Отменить", callback_data="lead_cancel")
    b.adjust(1)
    return b.as_markup()


def skip_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Пропустить", callback_data="lead_skip")
    b.button(text="❌ Отменить", callback_data="lead_cancel")
    b.adjust(2)
    return b.as_markup()


def confirm_lead_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Отправить заявку", callback_data="lead_confirm")
    b.button(text="❌ Отменить", callback_data="lead_cancel")
    b.adjust(1)
    return b.as_markup()


# ---------- Админ-панель ----------

def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🏠 Объекты", callback_data="admin_properties_menu")
    b.button(text="👥 Агенты", callback_data="admin_agents_menu")
    b.button(text="📨 Заявки", callback_data="admin_leads")
    b.button(text="⚙️ Настройки бота", callback_data="admin_settings_menu")
    b.button(text="📊 Статистика", callback_data="admin_stats")
    b.button(text="📢 Рассылка агентам", callback_data="admin_broadcast_start")
    b.button(text="⬅️ В главное меню", callback_data="main_menu")
    b.adjust(1)
    return b.as_markup()


def admin_properties_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить объект", callback_data="admin_add")
    b.button(text="✏️ Редактировать объект", callback_data="admin_edit")
    b.button(text="🖼 Фото объекта", callback_data="admin_photos")
    b.button(text="🔄 Статус (доступен/забронирован)", callback_data="admin_status")
    b.button(text="📅 Брони / занятость", callback_data="admin_bookings")
    b.button(text="🗑 Удалить объект", callback_data="admin_delete")
    b.button(text="⬅️ В админ-панель", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


async def admin_pick_property_kb(prefix: str) -> InlineKeyboardMarkup:
    """prefix: 'admin_edit_pick' / 'admin_status_pick' / 'admin_delete_pick' / 'admin_photos_pick'"""
    b = InlineKeyboardBuilder()
    items = await db.get_all_properties()
    for p in items:
        b.button(text=f"{p['id']} — {p['title']}", callback_data=f"{prefix}:{p['id']}")
    b.button(text="⬅️ В админ-панель", callback_data="admin_properties_menu")
    b.adjust(1)
    return b.as_markup()


def admin_edit_fields_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    fields = [
        ("title", "Название"), ("district", "Район"), ("bedrooms", "Спальни"),
        ("sqm", "Площадь"), ("view", "Вид"), ("pool_access", "Бассейн"),
        ("address", "Адрес"), ("map_link", "Ссылка на карту"),
        ("max_guests", "Макс. гостей"), ("description", "Описание"),
        ("deposit", "Депозит"), ("utilities_included", "Коммуналка/что включено"),
        ("currency", "Валюта"),
    ]
    for key, label in fields:
        b.button(text=label, callback_data=f"admin_edit_field:{property_id}:{key}")
    b.button(text="🏷 Тип объекта", callback_data=f"admin_edit_type:{property_id}")
    b.button(text="💰 Цены (все периоды)", callback_data=f"admin_edit_prices:{property_id}")
    b.button(text="🔗 Ссылки (фото/инфо)", callback_data=f"admin_edit_links:{property_id}")
    b.button(text="⬅️ Отмена", callback_data="admin_properties_menu")
    b.adjust(2)
    return b.as_markup()


def admin_edit_type_pick_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in PROPERTY_TYPES.items():
        b.button(text=label, callback_data=f"admin_edit_type_set:{property_id}:{key}")
    b.button(text="⬅️ Отмена", callback_data=f"admin_edit_pick:{property_id}")
    b.adjust(1)
    return b.as_markup()


def admin_photos_menu_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить фото", callback_data=f"admin_photos_add:{property_id}")
    b.button(text="👀 Посмотреть текущие", callback_data=f"admin_photos_view:{property_id}")
    b.button(text="🗑 Удалить все фото", callback_data=f"admin_photos_clear:{property_id}")
    b.button(text="⬅️ В админ-панель", callback_data="admin_properties_menu")
    b.adjust(1)
    return b.as_markup()


def admin_agents_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📋 Список + статистика", callback_data="admin_agents")
    b.button(text="🗑 Удалить агента", callback_data="admin_agents_delete")
    b.button(text="⬅️ В админ-панель", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


async def admin_agents_pick_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    agents = await db.get_all_agents_with_stats()
    for a in agents:
        b.button(text=f"{a['name']} ({a['agency']})", callback_data=f"admin_agent_del_pick:{a['id']}")
    b.button(text="⬅️ Отмена", callback_data="admin_agents_menu")
    b.adjust(1)
    return b.as_markup()


def admin_agent_confirm_delete_kb(agent_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Да, удалить", callback_data=f"admin_agent_del_confirm:{agent_id}")
    b.button(text="⬅️ Отмена", callback_data="admin_agents_menu")
    b.adjust(1)
    return b.as_markup()


def admin_settings_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Приветственное сообщение", callback_data="admin_setting_edit:welcome_text")
    b.button(text="✏️ Название компании", callback_data="admin_setting_edit:company_name")
    b.button(text="✏️ Telegram менеджера", callback_data="admin_setting_edit:contact_telegram")
    b.button(text="✏️ Телефон", callback_data="admin_setting_edit:contact_phone")
    b.button(text="✏️ Email", callback_data="admin_setting_edit:contact_email")
    b.button(text="⬅️ В админ-панель", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


def admin_broadcast_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📢 Отправить всем агентам", callback_data="admin_broadcast_confirm")
    b.button(text="❌ Отмена", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


def back_to_admin_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ В админ-панель", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


def admin_status_pick_value_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Доступен", callback_data=f"admin_status_set:{property_id}:available")
    b.button(text="🔴 Забронирован", callback_data=f"admin_status_set:{property_id}:booked")
    b.button(text="⬅️ Отмена", callback_data="admin_properties_menu")
    b.adjust(1)
    return b.as_markup()


def admin_confirm_delete_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Да, удалить", callback_data=f"admin_delete_confirm:{property_id}")
    b.button(text="❌ Отмена", callback_data="admin_properties_menu")
    b.adjust(1)
    return b.as_markup()


def admin_type_pick_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in PROPERTY_TYPES.items():
        b.button(text=label, callback_data=f"admin_new_type:{key}")
    b.adjust(1)
    return b.as_markup()


def after_calc_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📝 Заявка на эти даты", callback_data=f"lead_for:{property_id}")
    b.button(text="📅 Другие даты", callback_data=f"calc_price:{property_id}")
    b.button(text="⬅️ К объекту", callback_data=f"prop:{property_id}")
    b.adjust(1)
    return b.as_markup()


def admin_bookings_menu_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить бронь", callback_data=f"admin_booking_add:{property_id}")
    b.button(text="📋 Список броней", callback_data=f"admin_booking_list:{property_id}")
    b.button(text="⬅️ В админ-панель", callback_data="admin_properties_menu")
    b.adjust(1)
    return b.as_markup()


def admin_booking_delete_kb(property_id: str, bookings: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for bk in bookings:
        label = f"{bk['check_in'].strftime('%d.%m.%y')} - {bk['check_out'].strftime('%d.%m.%y')}"
        b.button(text=f"🗑 {label}", callback_data=f"admin_booking_del:{bk['id']}:{property_id}")
    b.button(text="⬅️ Назад", callback_data=f"admin_bookings_back:{property_id}")
    b.adjust(1)
    return b.as_markup()

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import PROPERTY_TYPES
import db


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🏡 Каталог объектов", callback_data="catalog")
    b.button(text="📝 Оставить заявку", callback_data="lead_start")
    b.button(text="📞 Контакты", callback_data="contacts")
    if is_admin:
        b.button(text="⚙️ Админ-панель", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


def catalog_types_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in PROPERTY_TYPES.items():
        b.button(text=label, callback_data=f"type:{key}")
    b.button(text="⬅️ В главное меню", callback_data="main_menu")
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


def property_card_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📝 Заявка по этому объекту", callback_data=f"lead_for:{property_id}")
    b.button(text="⬅️ К списку объектов", callback_data="back_to_list")
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
    b.button(text="➕ Добавить объект", callback_data="admin_add")
    b.button(text="✏️ Редактировать объект", callback_data="admin_edit")
    b.button(text="🔄 Статус объекта (быстро)", callback_data="admin_status")
    b.button(text="🗑 Удалить объект", callback_data="admin_delete")
    b.button(text="👥 Список агентов", callback_data="admin_agents")
    b.button(text="⬅️ В главное меню", callback_data="main_menu")
    b.adjust(1)
    return b.as_markup()


async def admin_pick_property_kb(prefix: str) -> InlineKeyboardMarkup:
    """prefix: 'admin_edit_pick' / 'admin_status_pick' / 'admin_delete_pick'"""
    b = InlineKeyboardBuilder()
    items = await db.get_all_properties()
    for p in items:
        b.button(text=f"{p['id']} — {p['title']}", callback_data=f"{prefix}:{p['id']}")
    b.button(text="⬅️ В админ-панель", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


def admin_edit_fields_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    fields = [
        ("title", "Название"), ("district", "Район"), ("bedrooms", "Спальни"),
        ("sqm", "Площадь"), ("view", "Вид"), ("pool_access", "Бассейн"),
        ("address", "Адрес"), ("map_link", "Ссылка на карту"),
        ("max_guests", "Макс. гостей"), ("description", "Описание"),
    ]
    for key, label in fields:
        b.button(text=label, callback_data=f"admin_edit_field:{property_id}:{key}")
    b.button(text="⬅️ Отмена", callback_data="admin_menu")
    b.adjust(2)
    return b.as_markup()


def admin_status_pick_value_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Доступен", callback_data=f"admin_status_set:{property_id}:available")
    b.button(text="🔴 Забронирован", callback_data=f"admin_status_set:{property_id}:booked")
    b.button(text="⬅️ Отмена", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


def admin_confirm_delete_kb(property_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Да, удалить", callback_data=f"admin_delete_confirm:{property_id}")
    b.button(text="❌ Отмена", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


def admin_type_pick_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in PROPERTY_TYPES.items():
        b.button(text=label, callback_data=f"admin_new_type:{key}")
    b.adjust(1)
    return b.as_markup()

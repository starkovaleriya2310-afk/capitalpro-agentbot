"""
Конфигурация агентского бота Capital Pro | Phuket
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("AGENT_BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# ID чата, куда падают заявки от агентов (группа сотрудников или ваш личный chat_id)
AGENT_LEADS_CHAT_ID = os.getenv("AGENT_LEADS_CHAT_ID", "")

# Ваш личный Telegram ID - только у вас доступ к админ-панели
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

COMPANY_NAME = "Capital Pro | Phuket"

COMPANY_CONTACTS = {
    "telegram_manager": "@your_manager_username",
    "phone": "+66 00 000 0000",
    "email": "info@capitalpro.example",
    "website": "https://capitalpro.example",
}

PROPERTY_TYPES = {
    "villa": "🏡 Виллы",
    "apartment": "🏢 Апартаменты",
    "townhouse": "🏘 Таунхаусы",
}

# Пиковый период (декабрь-январь): бронь короче 30 дней всё равно
# считается по полной месячной цене соответствующего периода.
PEAK_RULE_NOTE = (
    "⚠️ Для бронирований в декабре-январе короче 30 дней действует "
    "полная месячная цена соответствующего периода (не посуточная)."
)

"""
Слой доступа к общей базе данных Capital Pro | Phuket.
Используется обоими ботами (агентским и гостевым).
"""
import json
import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_pool(dsn: str):
    global _pool
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    return _pool


async def close_pool():
    if _pool:
        await _pool.close()


def _row_to_property(row) -> dict:
    d = dict(row)
    for key in ("links", "prices", "photos"):
        if isinstance(d.get(key), str):
            d[key] = json.loads(d[key])
    return d


# ---------- PROPERTIES ----------

async def get_all_properties() -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM properties ORDER BY district, title")
        return [_row_to_property(r) for r in rows]


async def get_properties_by_type(prop_type: str) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM properties WHERE type = $1 ORDER BY district, title", prop_type
        )
        return [_row_to_property(r) for r in rows]


async def get_property_by_id(property_id: str) -> Optional[dict]:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM properties WHERE id = $1", property_id)
        return _row_to_property(row) if row else None


async def count_properties() -> int:
    async with _pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM properties")


async def upsert_property(p: dict):
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO properties (
                id, type, title, district, bedrooms, sqm, view, pool_access,
                address, map_link, max_guests, links, prices, currency,
                description, photos, status, deposit, utilities_included, updated_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19, now()
            )
            ON CONFLICT (id) DO UPDATE SET
                type = EXCLUDED.type,
                title = EXCLUDED.title,
                district = EXCLUDED.district,
                bedrooms = EXCLUDED.bedrooms,
                sqm = EXCLUDED.sqm,
                view = EXCLUDED.view,
                pool_access = EXCLUDED.pool_access,
                address = EXCLUDED.address,
                map_link = EXCLUDED.map_link,
                max_guests = EXCLUDED.max_guests,
                links = EXCLUDED.links,
                prices = EXCLUDED.prices,
                currency = EXCLUDED.currency,
                description = EXCLUDED.description,
                photos = EXCLUDED.photos,
                status = EXCLUDED.status,
                deposit = EXCLUDED.deposit,
                utilities_included = EXCLUDED.utilities_included,
                updated_at = now()
            """,
            p["id"], p["type"], p["title"], p.get("district"), p.get("bedrooms"),
            p.get("sqm"), p.get("view"), p.get("pool_access"), p.get("address"),
            p.get("map_link"), p.get("max_guests"),
            json.dumps(p.get("links") or []),
            json.dumps(p.get("prices") or []),
            p.get("currency", "THB"), p.get("description", ""),
            json.dumps(p.get("photos") or []),
            p.get("status", "available"),
            p.get("deposit"), p.get("utilities_included"),
        )


async def update_property_field(property_id: str, field: str, value):
    allowed = {
        "type", "title", "district", "bedrooms", "sqm", "view", "pool_access",
        "address", "map_link", "max_guests", "currency", "description", "status",
        "deposit", "utilities_included",
    }
    if field not in allowed:
        raise ValueError(f"Field '{field}' is not editable via update_property_field")
    async with _pool.acquire() as conn:
        await conn.execute(
            f"UPDATE properties SET {field} = $1, updated_at = now() WHERE id = $2",
            value, property_id,
        )


async def delete_property(property_id: str):
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM properties WHERE id = $1", property_id)


# ---------- AGENTS ----------

async def get_agent_by_telegram_id(telegram_id: int) -> Optional[dict]:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM agents WHERE telegram_id = $1", telegram_id
        )
        return dict(row) if row else None


async def register_agent(telegram_id: int, telegram_username: str, name: str, agency: str, contact: str):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO agents (telegram_id, telegram_username, name, agency, contact)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (telegram_id) DO UPDATE SET
                telegram_username = EXCLUDED.telegram_username,
                name = EXCLUDED.name,
                agency = EXCLUDED.agency,
                contact = EXCLUDED.contact
            RETURNING *
            """,
            telegram_id, telegram_username, name, agency, contact,
        )
        return dict(row)


async def get_all_agents_with_stats() -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.*, COUNT(l.id) AS leads_count
            FROM agents a
            LEFT JOIN leads l ON l.agent_id = a.id
            GROUP BY a.id
            ORDER BY leads_count DESC, a.registered_at DESC
            """
        )
        return [dict(r) for r in rows]


# ---------- LEADS ----------

async def create_lead(
    source: str,
    property_id: Optional[str],
    property_title: Optional[str],
    client_name: str,
    client_contact: str,
    dates: str,
    budget: str,
    comment: str,
    agent_id: Optional[int],
    telegram_user_id: int,
    telegram_username: Optional[str],
) -> dict:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO leads (
                source, property_id, property_title, client_name, client_contact,
                dates, budget, comment, agent_id, telegram_user_id, telegram_username
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            RETURNING *
            """,
            source, property_id, property_title, client_name, client_contact,
            dates, budget, comment, agent_id, telegram_user_id, telegram_username,
        )
        return dict(row)


# ---------- Фильтрация для нового флоу (тип -> даты -> район -> список) ----------

async def get_districts_by_type(prop_type: str) -> list[str]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT district FROM properties
            WHERE type = $1 AND status = 'available' AND district IS NOT NULL
            ORDER BY district
            """,
            prop_type,
        )
        return [r["district"] for r in rows]


async def get_all_districts() -> list[str]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT district FROM properties WHERE status = 'available' AND district IS NOT NULL"
        )
        return [r["district"] for r in rows]


async def get_types_by_districts(districts: list[str]) -> list[str]:
    """Какие типы объектов реально есть в наборе районов (для группового выбора Rawai/Naiharn и т.п.)."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT type FROM properties
            WHERE district = ANY($1::text[]) AND status = 'available' AND type IS NOT NULL
            ORDER BY type
            """,
            districts,
        )
        return [r["type"] for r in rows]


async def get_properties_by_type_districts(prop_type: str, districts: list[str]) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM properties
            WHERE type = $1 AND district = ANY($2::text[]) AND status = 'available'
            ORDER BY title
            """,
            prop_type, districts,
        )
        return [_row_to_property(r) for r in rows]


async def get_properties_by_type_district(prop_type: str, district: str) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM properties
            WHERE type = $1 AND district = $2 AND status = 'available'
            ORDER BY title
            """,
            prop_type, district,
        )
        return [_row_to_property(r) for r in rows]


# ---------- SETTINGS (редактируемые тексты бота) ----------

async def get_setting(key: str, default: str = None) -> str:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        return row["value"] if row else default


async def set_setting(key: str, value: str):
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO settings (key, value, updated_at) VALUES ($1, $2, now())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            key, value,
        )


# ---------- Расширенное редактирование объектов (JSONB поля) ----------

async def update_property_prices(property_id: str, prices: list[dict]):
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE properties SET prices = $1, updated_at = now() WHERE id = $2",
            json.dumps(prices), property_id,
        )


async def update_property_links(property_id: str, links: list[str]):
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE properties SET links = $1, updated_at = now() WHERE id = $2",
            json.dumps(links), property_id,
        )


async def append_property_photo(property_id: str, file_id: str) -> int:
    """Возвращает новое количество фото."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE properties
            SET photos = photos || $1::jsonb, updated_at = now()
            WHERE id = $2
            RETURNING jsonb_array_length(photos) AS cnt
            """,
            json.dumps([file_id]), property_id,
        )
        return row["cnt"] if row else 0


async def clear_property_photos(property_id: str):
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE properties SET photos = '[]'::jsonb, updated_at = now() WHERE id = $1",
            property_id,
        )


# ---------- AGENTS: доп. функции ----------

async def get_agent_by_id(agent_id: int):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
        return dict(row) if row else None


async def delete_agent(agent_id: int):
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM agents WHERE id = $1", agent_id)


async def get_all_agent_telegram_ids() -> list[int]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT telegram_id FROM agents")
        return [r["telegram_id"] for r in rows]


# ---------- LEADS: просмотр ----------

async def get_recent_leads(limit: int = 15) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT l.*, a.name AS agent_name, a.agency AS agent_agency
            FROM leads l
            LEFT JOIN agents a ON a.id = l.agent_id
            ORDER BY l.created_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]


# ---------- СТАТИСТИКА ----------

async def get_stats() -> dict:
    async with _pool.acquire() as conn:
        total_props = await conn.fetchval("SELECT COUNT(*) FROM properties")
        by_type = await conn.fetch(
            "SELECT type, COUNT(*) AS cnt FROM properties GROUP BY type ORDER BY cnt DESC"
        )
        by_status = await conn.fetch(
            "SELECT status, COUNT(*) AS cnt FROM properties GROUP BY status"
        )
        total_agents = await conn.fetchval("SELECT COUNT(*) FROM agents")
        total_leads = await conn.fetchval("SELECT COUNT(*) FROM leads")
        leads_today = await conn.fetchval(
            "SELECT COUNT(*) FROM leads WHERE created_at::date = CURRENT_DATE"
        )
        leads_week = await conn.fetchval(
            "SELECT COUNT(*) FROM leads WHERE created_at >= now() - interval '7 days'"
        )
        leads_by_source = await conn.fetch(
            "SELECT source, COUNT(*) AS cnt FROM leads GROUP BY source"
        )
        return {
            "total_properties": total_props,
            "by_type": {r["type"]: r["cnt"] for r in by_type},
            "by_status": {r["status"]: r["cnt"] for r in by_status},
            "total_agents": total_agents,
            "total_leads": total_leads,
            "leads_today": leads_today,
            "leads_week": leads_week,
            "leads_by_source": {r["source"]: r["cnt"] for r in leads_by_source},
        }


# ---------- BOOKINGS (календарь занятости, вводится вручную через админку) ----------

async def add_booking(property_id: str, check_in, check_out, note: str = None) -> dict:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO bookings (property_id, check_in, check_out, note)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            property_id, check_in, check_out, note,
        )
        return dict(row)


async def get_bookings_for_property(property_id: str, upcoming_only: bool = True) -> list[dict]:
    async with _pool.acquire() as conn:
        if upcoming_only:
            rows = await conn.fetch(
                """
                SELECT * FROM bookings
                WHERE property_id = $1 AND check_out >= CURRENT_DATE
                ORDER BY check_in
                """,
                property_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE property_id = $1 ORDER BY check_in",
                property_id,
            )
        return [dict(r) for r in rows]


async def get_overlapping_bookings(property_id: str, check_in, check_out) -> list[dict]:
    """Брони, пересекающиеся с указанным диапазоном [check_in, check_out)."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM bookings
            WHERE property_id = $1
              AND check_in < $3
              AND check_out > $2
            ORDER BY check_in
            """,
            property_id, check_in, check_out,
        )
        return [dict(r) for r in rows]


async def is_property_available(property_id: str, check_in, check_out) -> bool:
    overlapping = await get_overlapping_bookings(property_id, check_in, check_out)
    return len(overlapping) == 0


async def get_booking_by_id(booking_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM bookings WHERE id = $1", booking_id)
        return dict(row) if row else None


async def delete_booking(booking_id: int):
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM bookings WHERE id = $1", booking_id)

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
                description, photos, status, updated_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17, now()
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
        )


async def update_property_field(property_id: str, field: str, value):
    allowed = {
        "type", "title", "district", "bedrooms", "sqm", "view", "pool_access",
        "address", "map_link", "max_guests", "currency", "description", "status",
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

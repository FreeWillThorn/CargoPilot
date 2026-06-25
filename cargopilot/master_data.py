from __future__ import annotations

import json
import sqlite3
from typing import Any

from .foundation import ROLE_ADMIN, utc_now

WAREHOUSE_RECEIVING = "receiving"
WAREHOUSE_PORT = "port"
WAREHOUSE_TYPES = {WAREHOUSE_RECEIVING, WAREHOUSE_PORT}

SUPPLIER_FIELDS = {
    "name",
    "contact_name",
    "phone",
    "email",
    "wechat",
    "address",
    "business_id",
    "store_url",
    "usual_categories",
    "notes",
}
CONSIGNEE_FIELDS = {
    "company_name",
    "contact_name",
    "email",
    "phone",
    "tax_id",
    "address",
    "default_destination_port",
    "default_trade_term",
    "default_sales_currency",
    "document_preferences",
    "notes",
}
WAREHOUSE_FIELDS = {"type", "name", "contact_name", "phone", "address", "notes"}


def require_admin(role: str) -> None:
    if role != ROLE_ADMIN:
        raise PermissionError("admin role required")


def create_supplier(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    name: str,
    contact_name: str = "",
    phone: str = "",
    email: str = "",
    wechat: str = "",
    address: str = "",
    business_id: str = "",
    store_url: str = "",
    usual_categories: list[str] | None = None,
    notes: str = "",
) -> tuple[int, list[str]]:
    require_admin(actor_role)
    warnings = _supplier_duplicate_warnings(conn, name)
    now = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO suppliers (
            name, contact_name, phone, email, wechat, address, business_id,
            store_url, usual_categories, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            contact_name,
            phone,
            email,
            wechat,
            address,
            business_id,
            store_url,
            json.dumps(usual_categories or []),
            notes,
            now,
            now,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid), warnings


def update_supplier(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    supplier_id: int,
    **changes: Any,
) -> list[str]:
    require_admin(actor_role)
    warnings = _supplier_duplicate_warnings(conn, changes["name"], exclude_id=supplier_id) if "name" in changes else []
    _update(conn, "suppliers", SUPPLIER_FIELDS, supplier_id, changes)
    return warnings


def list_suppliers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM suppliers ORDER BY name"))


def create_consignee(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    company_name: str,
    contact_name: str = "",
    email: str = "",
    phone: str = "",
    tax_id: str = "",
    address: str = "",
    default_destination_port: str = "",
    default_trade_term: str = "",
    default_sales_currency: str = "",
    document_preferences: str = "",
    notes: str = "",
) -> int:
    require_admin(actor_role)
    now = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO consignees (
            company_name, contact_name, email, phone, tax_id, address,
            default_destination_port, default_trade_term, default_sales_currency,
            document_preferences, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_name,
            contact_name,
            email,
            phone,
            tax_id,
            address,
            default_destination_port,
            default_trade_term,
            default_sales_currency,
            document_preferences,
            notes,
            now,
            now,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def update_consignee(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    consignee_id: int,
    **changes: Any,
) -> None:
    require_admin(actor_role)
    _update(conn, "consignees", CONSIGNEE_FIELDS, consignee_id, changes)


def get_consignee_order_defaults(conn: sqlite3.Connection, consignee_id: int) -> dict[str, str]:
    row = conn.execute("SELECT * FROM consignees WHERE id = ?", (consignee_id,)).fetchone()
    if row is None:
        raise KeyError(consignee_id)
    return {
        "destination_port": row["default_destination_port"],
        "trade_term": row["default_trade_term"],
        "sales_currency": row["default_sales_currency"],
    }


def create_warehouse(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    type: str,
    name: str,
    contact_name: str = "",
    phone: str = "",
    address: str = "",
    notes: str = "",
) -> int:
    require_admin(actor_role)
    if type not in WAREHOUSE_TYPES:
        raise ValueError(f"unknown warehouse type: {type}")
    now = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO warehouses (type, name, contact_name, phone, address, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (type, name, contact_name, phone, address, notes, now, now),
    )
    conn.commit()
    return int(cursor.lastrowid)


def update_warehouse(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    warehouse_id: int,
    **changes: Any,
) -> None:
    require_admin(actor_role)
    if "type" in changes and changes["type"] not in WAREHOUSE_TYPES:
        raise ValueError(f"unknown warehouse type: {changes['type']}")
    _update(conn, "warehouses", WAREHOUSE_FIELDS, warehouse_id, changes)


def list_warehouses(conn: sqlite3.Connection, type: str | None = None) -> list[sqlite3.Row]:
    if type is None:
        return list(conn.execute("SELECT * FROM warehouses ORDER BY name"))
    if type not in WAREHOUSE_TYPES:
        raise ValueError(f"unknown warehouse type: {type}")
    return list(conn.execute("SELECT * FROM warehouses WHERE type = ? ORDER BY name", (type,)))


def _supplier_duplicate_warnings(
    conn: sqlite3.Connection,
    name: str,
    *,
    exclude_id: int | None = None,
) -> list[str]:
    params: list[Any] = [name.lower()]
    sql = "SELECT id FROM suppliers WHERE lower(name) = ?"
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)
    duplicate = conn.execute(sql, params).fetchone()
    return [f"Supplier name already exists: {name}"] if duplicate else []


def _update(
    conn: sqlite3.Connection,
    table: str,
    allowed_fields: set[str],
    row_id: int,
    changes: dict[str, Any],
) -> None:
    unknown = set(changes) - allowed_fields
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
    if not changes:
        return
    if "usual_categories" in changes:
        changes["usual_categories"] = json.dumps(changes["usual_categories"])
    assignments = ", ".join(f"{field} = ?" for field in changes)
    values = list(changes.values()) + [utc_now(), row_id]
    conn.execute(
        f"UPDATE {table} SET {assignments}, updated_at = ? WHERE id = ?",
        values,
    )
    conn.commit()

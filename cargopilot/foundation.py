from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLE_ADMIN = "admin"
ROLE_WAREHOUSE = "warehouse"

WAREHOUSE_ACTIONS = frozenset(
    {
        "import_orders:view",
        "goods_lines:view",
        "goods_lines:update_receiving",
        "goods_lines:update_logistics",
        "receiving_records:create",
        "files:create_receiving_photo",
    }
)

DEFAULT_SETTINGS: dict[str, Any] = {
    "seller": {
        "company_name": "",
        "address": "",
        "phone": "",
        "email": "",
        "tax_or_business_id": "",
        "bank_info": "",
    },
    "defaults": {
        "origin_country": "China",
        "origin_port": "",
        "purchase_currency": "CNY",
        "sales_currency": "EUR",
    },
    "containers": {
        "20GP": {"max_cbm": 28, "max_weight_kg": 28000},
        "40GP": {"max_cbm": 58, "max_weight_kg": 28000},
        "40HQ": {"max_cbm": 68, "max_weight_kg": 28000},
    },
    "reminders": {"lead_days": 3},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'warehouse')),
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    owner_type TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    file_category TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    uploaded_by_user_id INTEGER NOT NULL REFERENCES users(id),
    uploaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY,
    actor_user_id INTEGER NOT NULL REFERENCES users(id),
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    contact_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    wechat TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    business_id TEXT NOT NULL DEFAULT '',
    store_url TEXT NOT NULL DEFAULT '',
    usual_categories TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consignees (
    id INTEGER PRIMARY KEY,
    company_name TEXT NOT NULL,
    contact_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    tax_id TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    default_destination_port TEXT NOT NULL DEFAULT '',
    default_trade_term TEXT NOT NULL DEFAULT '',
    default_sales_currency TEXT NOT NULL DEFAULT '',
    document_preferences TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('receiving', 'port')),
    name TEXT NOT NULL,
    contact_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_counters (
    year INTEGER PRIMARY KEY,
    next_number INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS import_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    consignee_id INTEGER REFERENCES consignees(id),
    receiving_warehouse_id INTEGER REFERENCES warehouses(id),
    port_warehouse_id INTEGER REFERENCES warehouses(id),
    trade_term TEXT NOT NULL DEFAULT '',
    origin_country TEXT NOT NULL DEFAULT '',
    origin_port TEXT NOT NULL DEFAULT '',
    destination_country TEXT NOT NULL DEFAULT '',
    destination_port TEXT NOT NULL DEFAULT '',
    order_status TEXT NOT NULL DEFAULT 'draft',
    expected_received_date TEXT,
    expected_loading_date TEXT,
    expected_departure_date TEXT,
    expected_arrival_date TEXT,
    actual_received_date TEXT,
    actual_loading_date TEXT,
    actual_departure_date TEXT,
    actual_arrival_date TEXT,
    purchase_currency TEXT NOT NULL DEFAULT '',
    sales_currency TEXT NOT NULL DEFAULT '',
    internal_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goods_lines (
    id INTEGER PRIMARY KEY,
    import_order_id INTEGER NOT NULL REFERENCES import_orders(id) ON DELETE CASCADE,
    supplier_id INTEGER REFERENCES suppliers(id),
    customer_item_no TEXT NOT NULL DEFAULT '',
    sku_or_model TEXT NOT NULL DEFAULT '',
    product_url TEXT NOT NULL DEFAULT '',
    cn_name TEXT NOT NULL DEFAULT '',
    en_name TEXT NOT NULL DEFAULT '',
    customs_en_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    hs_code TEXT NOT NULL DEFAULT '',
    quantity REAL,
    unit TEXT NOT NULL DEFAULT '',
    packaging_method TEXT NOT NULL DEFAULT '',
    carton_count INTEGER,
    units_per_carton REAL,
    carton_gross_weight_kg REAL,
    gross_weight REAL,
    carton_length_cm REAL,
    carton_width_cm REAL,
    carton_height_cm REAL,
    volume_cbm REAL,
    shipping_mark TEXT NOT NULL DEFAULT '',
    logistics_status TEXT NOT NULL DEFAULT 'not_ordered',
    compliance_status TEXT NOT NULL DEFAULT 'not_required',
    target_markup REAL,
    target_margin REAL,
    sales_unit_price REAL,
    sales_currency TEXT NOT NULL DEFAULT '',
    purchase_unit_price REAL,
    purchase_currency TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finance_lines (
    id INTEGER PRIMARY KEY,
    import_order_id INTEGER NOT NULL REFERENCES import_orders(id) ON DELETE CASCADE,
    goods_line_id INTEGER REFERENCES goods_lines(id) ON DELETE CASCADE,
    line_kind TEXT NOT NULL CHECK (line_kind IN ('cost', 'charge')),
    line_type TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    exchange_rate_to_base REAL NOT NULL,
    line_date TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS domestic_tracking_numbers (
    id INTEGER PRIMARY KEY,
    goods_line_id INTEGER NOT NULL REFERENCES goods_lines(id) ON DELETE CASCADE,
    tracking_no TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS receiving_records (
    id INTEGER PRIMARY KEY,
    goods_line_id INTEGER NOT NULL REFERENCES goods_lines(id) ON DELETE CASCADE,
    domestic_tracking_number_id INTEGER REFERENCES domestic_tracking_numbers(id) ON DELETE SET NULL,
    received_carton_count INTEGER NOT NULL,
    package_condition TEXT NOT NULL DEFAULT '',
    arrival_exception_type TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS containers (
    id INTEGER PRIMARY KEY,
    import_order_id INTEGER NOT NULL REFERENCES import_orders(id) ON DELETE CASCADE,
    container_type TEXT NOT NULL,
    container_number TEXT NOT NULL,
    seal_number TEXT NOT NULL,
    loading_date TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loading_records (
    id INTEGER PRIMARY KEY,
    container_id INTEGER NOT NULL REFERENCES containers(id) ON DELETE CASCADE,
    goods_line_id INTEGER NOT NULL REFERENCES goods_lines(id) ON DELETE CASCADE,
    loaded_carton_count INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    import_order_id INTEGER NOT NULL REFERENCES import_orders(id) ON DELETE CASCADE,
    document_type TEXT NOT NULL CHECK (document_type IN ('commercial_invoice', 'packing_list')),
    version INTEGER NOT NULL,
    document_number TEXT NOT NULL,
    status TEXT NOT NULL,
    xlsx_path TEXT NOT NULL,
    pdf_path TEXT NOT NULL,
    generated_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: str | Path = "cargopilot.sqlite3") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _ensure_column(conn, "finance_lines", "line_date", "TEXT NOT NULL DEFAULT ''")
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO system_settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, json.dumps(value), utc_now()),
        )
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def can(role: str, action: str) -> bool:
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_WAREHOUSE:
        return action in WAREHOUSE_ACTIONS
    return False


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return (
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def create_user(
    conn: sqlite3.Connection,
    *,
    email: str,
    name: str,
    role: str,
    password: str,
) -> int:
    if role not in {ROLE_ADMIN, ROLE_WAREHOUSE}:
        raise ValueError(f"unknown role: {role}")
    salt, password_hash = hash_password(password)
    cursor = conn.execute(
        """
        INSERT INTO users (email, name, role, password_hash, password_salt, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (email, name, role, password_hash, salt, utc_now()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def authenticate(conn: sqlite3.Connection, email: str, password: str) -> sqlite3.Row | None:
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None:
        return None
    salt = base64.b64decode(user["password_salt"])
    _, candidate_hash = hash_password(password, salt)
    if hmac.compare_digest(candidate_hash, user["password_hash"]):
        return user
    return None


def record_file_metadata(
    conn: sqlite3.Connection,
    *,
    owner_type: str,
    owner_id: int,
    file_category: str,
    file_name: str,
    file_type: str,
    storage_path: str,
    uploaded_by_user_id: int,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO files (
            owner_type, owner_id, file_category, file_name, file_type,
            storage_path, uploaded_by_user_id, uploaded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_type,
            owner_id,
            file_category,
            file_name,
            file_type,
            storage_path,
            uploaded_by_user_id,
            utc_now(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def record_audit_log(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    target_type: str,
    target_id: int,
    field_name: str,
    old_value: Any,
    new_value: Any,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO audit_logs (
            actor_user_id, target_type, target_id, field_name,
            old_value, new_value, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor_user_id,
            target_type,
            target_id,
            field_name,
            json.dumps(old_value),
            json.dumps(new_value),
            utc_now(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def get_setting(conn: sqlite3.Connection, key: str) -> Any:
    row = conn.execute("SELECT value_json FROM system_settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise KeyError(key)
    return json.loads(row["value_json"])


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        """
        INSERT INTO system_settings (key, value_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value_json = excluded.value_json,
            updated_at = excluded.updated_at
        """,
        (key, json.dumps(value), utc_now()),
    )
    conn.commit()

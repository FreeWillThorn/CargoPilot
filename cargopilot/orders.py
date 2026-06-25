from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from .foundation import get_setting, utc_now
from .master_data import require_admin

ORDER_STATUS_DRAFT = "draft"
GOODS_STATUS_NOT_ORDERED = "not_ordered"
COMPLIANCE_STATUS_NOT_REQUIRED = "not_required"

IMPORT_ORDER_LIST_COLUMNS = (
    "id",
    "order_no",
    "consignee_id",
    "destination_port",
    "order_status",
    "expected_loading_date",
)

IMPORT_ORDER_DETAIL_TABS = (
    "overview",
    "goods_lines",
    "logistics_receiving",
    "container_loading",
    "export_documents",
    "cost_profit",
    "files",
    "modification_history",
)

GOODS_LINE_FIELD_GROUPS = {
    "basic": (
        "supplier_id",
        "customer_item_no",
        "product_url",
        "cn_name",
        "en_name",
        "customs_en_name",
        "sku_or_model",
        "category",
        "hs_code",
        "quantity",
        "unit",
        "packaging_method",
    ),
    "pricing": (
        "target_markup",
        "target_margin",
        "sales_unit_price",
        "sales_currency",
        "purchase_unit_price",
        "purchase_currency",
    ),
    "packaging": (
        "carton_count",
        "units_per_carton",
        "carton_length_cm",
        "carton_width_cm",
        "carton_height_cm",
        "carton_gross_weight_kg",
        "gross_weight",
        "volume_cbm",
        "shipping_mark",
    ),
    "logistics": ("logistics_status",),
    "compliance": ("compliance_status",),
    "files": (),
}

IMPORT_ORDER_FIELDS = {
    "order_no",
    "consignee_id",
    "receiving_warehouse_id",
    "port_warehouse_id",
    "trade_term",
    "origin_country",
    "origin_port",
    "destination_country",
    "destination_port",
    "order_status",
    "expected_received_date",
    "expected_loading_date",
    "expected_departure_date",
    "expected_arrival_date",
    "actual_received_date",
    "actual_loading_date",
    "actual_departure_date",
    "actual_arrival_date",
    "purchase_currency",
    "sales_currency",
    "internal_notes",
}

GOODS_LINE_FIELDS = {
    field
    for group in GOODS_LINE_FIELD_GROUPS.values()
    for field in group
} | {"import_order_id", "notes"}


def next_order_no(conn: sqlite3.Connection, year: int | None = None) -> str:
    year = year or datetime.now(timezone.utc).year
    row = conn.execute("SELECT next_number FROM order_counters WHERE year = ?", (year,)).fetchone()
    number = 1 if row is None else int(row["next_number"])
    conn.execute(
        """
        INSERT INTO order_counters (year, next_number)
        VALUES (?, ?)
        ON CONFLICT(year) DO UPDATE SET next_number = excluded.next_number
        """,
        (year, number + 1),
    )
    conn.commit()
    return f"CP-{year}-{number:04d}"


def create_import_order(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    order_no: str | None = None,
    consignee_id: int | None = None,
    receiving_warehouse_id: int | None = None,
    port_warehouse_id: int | None = None,
    **fields: Any,
) -> int:
    require_admin(actor_role)
    defaults = _order_defaults(conn, consignee_id)
    data = {
        **defaults,
        **fields,
        "order_no": order_no or next_order_no(conn),
        "consignee_id": consignee_id,
        "receiving_warehouse_id": receiving_warehouse_id,
        "port_warehouse_id": port_warehouse_id,
    }
    unknown = set(data) - IMPORT_ORDER_FIELDS
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
    now = utc_now()
    columns = list(data) + ["created_at", "updated_at"]
    values = list(data.values()) + [now, now]
    cursor = conn.execute(
        f"INSERT INTO import_orders ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        values,
    )
    conn.commit()
    return int(cursor.lastrowid)


def update_import_order(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    import_order_id: int,
    **changes: Any,
) -> None:
    require_admin(actor_role)
    _update(conn, "import_orders", IMPORT_ORDER_FIELDS, import_order_id, changes)


def list_import_order_cards(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"SELECT {', '.join(IMPORT_ORDER_LIST_COLUMNS)} FROM import_orders ORDER BY created_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def create_goods_line(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    import_order_id: int,
    **fields: Any,
) -> int:
    require_admin(actor_role)
    data = {
        "import_order_id": import_order_id,
        "logistics_status": GOODS_STATUS_NOT_ORDERED,
        "compliance_status": COMPLIANCE_STATUS_NOT_REQUIRED,
        **fields,
    }
    unknown = set(data) - GOODS_LINE_FIELDS
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
    now = utc_now()
    columns = list(data) + ["created_at", "updated_at"]
    values = list(data.values()) + [now, now]
    cursor = conn.execute(
        f"INSERT INTO goods_lines ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        values,
    )
    conn.commit()
    return int(cursor.lastrowid)


def update_goods_line(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    goods_line_id: int,
    **changes: Any,
) -> None:
    require_admin(actor_role)
    _update(conn, "goods_lines", GOODS_LINE_FIELDS - {"import_order_id"}, goods_line_id, changes)


def goods_line_split_key(row: sqlite3.Row | dict[str, Any]) -> tuple[Any, str, str, str]:
    return (
        row["supplier_id"],
        row["sku_or_model"] or "",
        row["customs_en_name"] or "",
        row["packaging_method"] or "",
    )


def _order_defaults(conn: sqlite3.Connection, consignee_id: int | None) -> dict[str, Any]:
    settings_defaults = get_setting(conn, "defaults")
    data = {
        "origin_country": settings_defaults.get("origin_country", ""),
        "origin_port": settings_defaults.get("origin_port", ""),
        "purchase_currency": settings_defaults.get("purchase_currency", ""),
        "sales_currency": settings_defaults.get("sales_currency", ""),
        "order_status": ORDER_STATUS_DRAFT,
    }
    if consignee_id is not None:
        consignee = conn.execute("SELECT * FROM consignees WHERE id = ?", (consignee_id,)).fetchone()
        if consignee is None:
            raise KeyError(consignee_id)
        data.update(
            {
                "destination_port": consignee["default_destination_port"],
                "trade_term": consignee["default_trade_term"],
                "sales_currency": consignee["default_sales_currency"] or data["sales_currency"],
            }
        )
    return data


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
    assignments = ", ".join(f"{field} = ?" for field in changes)
    values = list(changes.values()) + [utc_now(), row_id]
    conn.execute(f"UPDATE {table} SET {assignments}, updated_at = ? WHERE id = ?", values)
    conn.commit()

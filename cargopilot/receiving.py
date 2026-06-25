from __future__ import annotations

import sqlite3
from typing import Any

from .foundation import ROLE_ADMIN, ROLE_WAREHOUSE, can, record_file_metadata, utc_now

ARRIVAL_EXCEPTION_TYPES = {
    "missing_cartons",
    "extra_cartons",
    "damaged_cartons",
    "unclear_shipping_mark",
    "wrong_goods",
    "dimension_weight_mismatch",
}


def search_receiving(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    query: str,
) -> list[dict[str, Any]]:
    _require_receiving_access(actor_role)
    pattern = f"%{query}%"
    rows = conn.execute(
        """
        SELECT
            goods_lines.id AS goods_line_id,
            goods_lines.cn_name,
            goods_lines.customs_en_name,
            goods_lines.shipping_mark,
            goods_lines.logistics_status,
            import_orders.order_no,
            group_concat(domestic_tracking_numbers.tracking_no, ',') AS tracking_numbers
        FROM goods_lines
        JOIN import_orders ON import_orders.id = goods_lines.import_order_id
        LEFT JOIN domestic_tracking_numbers ON domestic_tracking_numbers.goods_line_id = goods_lines.id
        WHERE import_orders.order_no LIKE ?
           OR domestic_tracking_numbers.tracking_no LIKE ?
           OR goods_lines.shipping_mark LIKE ?
        GROUP BY goods_lines.id
        ORDER BY import_orders.order_no, goods_lines.id
        """,
        (pattern, pattern, pattern),
    ).fetchall()
    return [dict(row) for row in rows]


def add_domestic_tracking_number(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    goods_line_id: int,
    tracking_no: str,
    notes: str = "",
) -> int:
    _require_receiving_access(actor_role)
    existing = conn.execute(
        """
        SELECT id FROM domestic_tracking_numbers
        WHERE goods_line_id = ? AND tracking_no = ?
        """,
        (goods_line_id, tracking_no),
    ).fetchone()
    if existing:
        return int(existing["id"])
    cursor = conn.execute(
        """
        INSERT INTO domestic_tracking_numbers (goods_line_id, tracking_no, notes, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (goods_line_id, tracking_no, notes, utc_now()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def record_receiving(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    actor_user_id: int,
    goods_line_id: int,
    received_carton_count: int,
    package_condition: str = "",
    domestic_tracking_no: str = "",
    arrival_exception_type: str = "",
    notes: str = "",
    receiving_photo_path: str = "",
) -> int:
    _require_receiving_access(actor_role)
    if arrival_exception_type and arrival_exception_type not in ARRIVAL_EXCEPTION_TYPES:
        raise ValueError(f"unknown arrival exception: {arrival_exception_type}")
    tracking_id = None
    if domestic_tracking_no:
        tracking_id = add_domestic_tracking_number(
            conn,
            actor_role=actor_role,
            goods_line_id=goods_line_id,
            tracking_no=domestic_tracking_no,
        )
    cursor = conn.execute(
        """
        INSERT INTO receiving_records (
            goods_line_id, domestic_tracking_number_id, received_carton_count,
            package_condition, arrival_exception_type, notes, created_by_user_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            goods_line_id,
            tracking_id,
            received_carton_count,
            package_condition,
            arrival_exception_type,
            notes,
            actor_user_id,
            utc_now(),
        ),
    )
    receiving_record_id = int(cursor.lastrowid)
    conn.execute(
        "UPDATE goods_lines SET logistics_status = ?, updated_at = ? WHERE id = ?",
        ("exception" if arrival_exception_type else "received_at_warehouse", utc_now(), goods_line_id),
    )
    conn.commit()
    if receiving_photo_path:
        record_file_metadata(
            conn,
            owner_type="receiving_record",
            owner_id=receiving_record_id,
            file_category="receiving_photo",
            file_name=receiving_photo_path.rsplit("/", 1)[-1],
            file_type="image",
            storage_path=receiving_photo_path,
            uploaded_by_user_id=actor_user_id,
        )
    return receiving_record_id


def resolve_arrival_exception(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    goods_line_id: int,
    resolved_status: str = "received_at_warehouse",
) -> None:
    _require_receiving_access(actor_role)
    conn.execute(
        "UPDATE goods_lines SET logistics_status = ?, updated_at = ? WHERE id = ?",
        (resolved_status, utc_now(), goods_line_id),
    )
    conn.commit()


def _require_receiving_access(role: str) -> None:
    if role == ROLE_ADMIN:
        return
    if role == ROLE_WAREHOUSE and can(role, "receiving_records:create"):
        return
    raise PermissionError("receiving access required")

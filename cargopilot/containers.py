from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .calculations import calculate_cbm, calculate_gross_weight
from .foundation import get_setting, record_file_metadata, utc_now
from .master_data import require_admin
from .spreadsheet_io import export_rows_xlsx

CONTAINER_ORDER = ("20GP", "40GP", "40HQ")


def recommend_container(conn: sqlite3.Connection, import_order_id: int) -> dict[str, Any]:
    totals = _order_totals(conn, import_order_id)
    references = get_setting(conn, "containers")
    for container_type in CONTAINER_ORDER:
        ref = references[container_type]
        if totals["total_cbm"] <= ref["max_cbm"] and totals["total_gross_weight"] <= ref["max_weight_kg"]:
            return {**totals, "recommended_type": container_type}
    return {**totals, "recommended_type": "40HQ+"}


def create_container(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    import_order_id: int,
    container_type: str,
    container_number: str,
    seal_number: str,
    loading_date: str,
    notes: str = "",
) -> int:
    require_admin(actor_role)
    cursor = conn.execute(
        """
        INSERT INTO containers (
            import_order_id, container_type, container_number, seal_number,
            loading_date, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (import_order_id, container_type, container_number, seal_number, loading_date, notes, utc_now()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def record_loading(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    actor_user_id: int,
    container_id: int,
    goods_line_id: int,
    loaded_carton_count: int,
    notes: str = "",
    loading_photo_path: str = "",
) -> int:
    require_admin(actor_role)
    container = conn.execute("SELECT * FROM containers WHERE id = ?", (container_id,)).fetchone()
    goods_line = conn.execute("SELECT * FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
    if container is None or goods_line is None:
        raise KeyError("container or goods line not found")
    if container["import_order_id"] != goods_line["import_order_id"]:
        raise ValueError("Container cannot load Goods Lines from another Import Order")
    cursor = conn.execute(
        """
        INSERT INTO loading_records (container_id, goods_line_id, loaded_carton_count, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (container_id, goods_line_id, loaded_carton_count, notes, utc_now()),
    )
    loading_record_id = int(cursor.lastrowid)
    conn.execute(
        "UPDATE goods_lines SET logistics_status = 'loaded', updated_at = ? WHERE id = ?",
        (utc_now(), goods_line_id),
    )
    conn.commit()
    if loading_photo_path:
        record_file_metadata(
            conn,
            owner_type="loading_record",
            owner_id=loading_record_id,
            file_category="loading_photo",
            file_name=loading_photo_path.rsplit("/", 1)[-1],
            file_type="image",
            storage_path=loading_photo_path,
            uploaded_by_user_id=actor_user_id,
        )
    return loading_record_id


def loading_list(conn: sqlite3.Connection, import_order_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            containers.container_number,
            containers.seal_number,
            containers.container_type,
            goods_lines.id AS goods_line_id,
            goods_lines.customs_en_name,
            goods_lines.carton_count,
            loading_records.loaded_carton_count,
            goods_lines.*
        FROM loading_records
        JOIN containers ON containers.id = loading_records.container_id
        JOIN goods_lines ON goods_lines.id = loading_records.goods_line_id
        WHERE containers.import_order_id = ?
        ORDER BY containers.container_number, goods_lines.id
        """,
        (import_order_id,),
    ).fetchall()
    return [_loading_row(row) for row in rows]


def export_loading_list(conn: sqlite3.Connection, import_order_id: int, path: str | Path) -> None:
    headers = [
        "container_number",
        "seal_number",
        "container_type",
        "goods_line_id",
        "customs_en_name",
        "loaded_carton_count",
        "cbm",
        "gross_weight",
    ]
    export_rows_xlsx(path, headers, loading_list(conn, import_order_id))


def _order_totals(conn: sqlite3.Connection, import_order_id: int) -> dict[str, float]:
    rows = conn.execute("SELECT * FROM goods_lines WHERE import_order_id = ?", (import_order_id,)).fetchall()
    return {
        "total_cbm": sum(calculate_cbm(row) or 0 for row in rows),
        "total_gross_weight": sum(calculate_gross_weight(row) or 0 for row in rows),
    }


def _loading_row(row: sqlite3.Row) -> dict[str, Any]:
    line_cbm = calculate_cbm(row) or 0
    line_weight = calculate_gross_weight(row) or 0
    carton_count = row["carton_count"] or 0
    ratio = row["loaded_carton_count"] / carton_count if carton_count else 0
    return {
        "container_number": row["container_number"],
        "seal_number": row["seal_number"],
        "container_type": row["container_type"],
        "goods_line_id": row["goods_line_id"],
        "customs_en_name": row["customs_en_name"],
        "loaded_carton_count": row["loaded_carton_count"],
        "cbm": line_cbm * ratio,
        "gross_weight": line_weight * ratio,
    }

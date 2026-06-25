from __future__ import annotations

import sqlite3
from typing import Any

from .calculations import (
    STAGE_CONTAINER_ESTIMATE,
    STAGE_FINAL_DOCUMENTS,
    STAGE_PURCHASING,
    STAGE_RECEIVING,
    check_goods_line_stage,
)

ORDER_STATUS_COLORS = {
    "draft": "gray",
    "purchasing": "blue",
    "receiving": "orange",
    "received": "cyan",
    "moving_to_port": "purple",
    "at_port_warehouse": "indigo",
    "loaded": "green",
    "at_sea": "navy",
    "arrived": "teal",
    "completed": "dark_gray",
    "cancelled": "red",
}

LOGISTICS_RANK = {
    "not_ordered": 0,
    "ordered": 1,
    "supplier_preparing": 2,
    "domestic_shipped": 3,
    "received_at_warehouse": 4,
    "checked": 5,
    "moved_to_port_warehouse": 6,
    "loaded": 7,
    "at_sea": 8,
}

ORDER_STATUS_TARGET_RANK = {
    "purchasing": 1,
    "receiving": 4,
    "received": 5,
    "moving_to_port": 6,
    "at_port_warehouse": 6,
    "loaded": 7,
    "at_sea": 8,
    "arrived": 8,
    "completed": 8,
}

ORDER_STATUS_CHECK_STAGE = {
    "purchasing": STAGE_PURCHASING,
    "receiving": STAGE_RECEIVING,
    "received": STAGE_CONTAINER_ESTIMATE,
    "moving_to_port": STAGE_CONTAINER_ESTIMATE,
    "at_port_warehouse": STAGE_CONTAINER_ESTIMATE,
    "loaded": STAGE_FINAL_DOCUMENTS,
    "at_sea": STAGE_FINAL_DOCUMENTS,
}


def dashboard_orders(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    consignee_id: int | None = None,
) -> list[dict[str, Any]]:
    clauses = ["import_orders.order_status != 'cancelled'"]
    params: list[Any] = []
    if status is not None:
        clauses.append("import_orders.order_status = ?")
        params.append(status)
    if consignee_id is not None:
        clauses.append("import_orders.consignee_id = ?")
        params.append(consignee_id)
    orders = conn.execute(
        f"""
        SELECT import_orders.*, consignees.company_name AS consignee_name
        FROM import_orders
        LEFT JOIN consignees ON consignees.id = import_orders.consignee_id
        WHERE {' AND '.join(clauses)}
        ORDER BY import_orders.created_at DESC
        """,
        params,
    ).fetchall()
    return [_dashboard_card(conn, order) for order in orders]


def order_stage_progress(conn: sqlite3.Connection, import_order_id: int) -> int:
    order = conn.execute("SELECT * FROM import_orders WHERE id = ?", (import_order_id,)).fetchone()
    if order is None:
        raise KeyError(import_order_id)
    target_rank = ORDER_STATUS_TARGET_RANK.get(order["order_status"])
    if target_rank is None:
        return 0
    goods = conn.execute(
        "SELECT logistics_status FROM goods_lines WHERE import_order_id = ?",
        (import_order_id,),
    ).fetchall()
    if not goods:
        return 0
    complete = sum(
        1
        for row in goods
        if row["logistics_status"] != "exception"
        and LOGISTICS_RANK.get(row["logistics_status"], 0) >= target_rank
    )
    return round(complete / len(goods) * 100)


def _dashboard_card(conn: sqlite3.Connection, order: sqlite3.Row) -> dict[str, Any]:
    exception_count = _exception_count(conn, order["id"])
    missing_data_count = _missing_data_count(conn, order["id"], order["order_status"])
    return {
        "id": order["id"],
        "order_no": order["order_no"],
        "consignee": order["consignee_name"] or "",
        "destination_port": order["destination_port"],
        "order_status": order["order_status"],
        "status_color": ORDER_STATUS_COLORS[order["order_status"]],
        "order_stage_progress": order_stage_progress(conn, order["id"]),
        "expected_loading_date": order["expected_loading_date"],
        "exception_count": exception_count,
        "has_exception_badge": exception_count > 0,
        "missing_data_count": missing_data_count,
        "exception_link": {"filter": "exceptions", "import_order_id": order["id"]},
        "missing_data_link": {"filter": "missing_data", "import_order_id": order["id"]},
    }


def _exception_count(conn: sqlite3.Connection, import_order_id: int) -> int:
    row = conn.execute(
        """
        SELECT count(*) AS count
        FROM goods_lines
        WHERE import_order_id = ? AND logistics_status = 'exception'
        """,
        (import_order_id,),
    ).fetchone()
    return int(row["count"])


def _missing_data_count(conn: sqlite3.Connection, import_order_id: int, order_status: str) -> int:
    stage = ORDER_STATUS_CHECK_STAGE.get(order_status, STAGE_PURCHASING)
    goods = conn.execute("SELECT id FROM goods_lines WHERE import_order_id = ?", (import_order_id,)).fetchall()
    return sum(1 for row in goods if check_goods_line_stage(conn, goods_line_id=row["id"], stage=stage).blocked)

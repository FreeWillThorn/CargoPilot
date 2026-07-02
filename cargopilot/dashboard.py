from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from .calculations import (
    STAGE_CONTAINER_ESTIMATE,
    STAGE_FINAL_DOCUMENTS,
    STAGE_PURCHASING,
    STAGE_RECEIVING,
    check_goods_line_stage,
)
from .foundation import get_setting

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
    "supplier_preparing": 1,
    "domestic_shipped": 2,
    "received_at_warehouse": 3,
    "checked": 3,
    "moved_to_port_warehouse": 4,
    "loaded": 5,
    "at_sea": 6,
    "exception": 0,
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
    goods = conn.execute(
        "SELECT logistics_status FROM goods_lines WHERE import_order_id = ?",
        (import_order_id,),
    ).fetchall()
    if not goods:
        return 0
    max_rank = LOGISTICS_RANK["at_sea"]
    average_rank = sum(LOGISTICS_RANK.get(row["logistics_status"], 0) for row in goods) / len(goods)
    return round(average_rank / max_rank * 100)


def current_logistics_point(conn: sqlite3.Connection, import_order_id: int) -> str:
    rows = conn.execute(
        "SELECT logistics_status FROM goods_lines WHERE import_order_id = ?",
        (import_order_id,),
    ).fetchall()
    if not rows:
        return "empty"
    statuses = [row["logistics_status"] for row in rows]
    if "exception" in statuses:
        return "exception"
    min_rank = min(LOGISTICS_RANK.get(status, 0) for status in statuses)
    if min_rank < LOGISTICS_RANK["received_at_warehouse"]:
        return "supplier_side"
    if min_rank < LOGISTICS_RANK["moved_to_port_warehouse"]:
        return "receiving_warehouse"
    if min_rank < LOGISTICS_RANK["loaded"]:
        return "port_warehouse"
    if min_rank < LOGISTICS_RANK["at_sea"]:
        return "loaded"
    return "at_sea"


def global_search(conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    pattern = f"%{query}%"
    results: list[dict[str, Any]] = []
    results.extend(
        _search_rows(
            conn,
            "import_order",
            """
            SELECT import_orders.id, import_orders.order_no AS label
            FROM import_orders
            LEFT JOIN consignees ON consignees.id = import_orders.consignee_id
            WHERE import_orders.order_no LIKE ? OR consignees.company_name LIKE ?
            """,
            (pattern, pattern),
        )
    )
    results.extend(
        _search_rows(
            conn,
            "goods_line",
            """
            SELECT goods_lines.id, goods_lines.cn_name || ' / ' || goods_lines.customs_en_name AS label
            FROM goods_lines
            LEFT JOIN suppliers ON suppliers.id = goods_lines.supplier_id
            LEFT JOIN domestic_tracking_numbers ON domestic_tracking_numbers.goods_line_id = goods_lines.id
            WHERE goods_lines.cn_name LIKE ?
               OR goods_lines.en_name LIKE ?
               OR goods_lines.customs_en_name LIKE ?
               OR goods_lines.shipping_mark LIKE ?
               OR suppliers.name LIKE ?
               OR domestic_tracking_numbers.tracking_no LIKE ?
            GROUP BY goods_lines.id
            """,
            (pattern, pattern, pattern, pattern, pattern, pattern),
        )
    )
    if _table_exists(conn, "containers"):
        results.extend(
            _search_rows(
                conn,
                "container",
                "SELECT id, container_number AS label FROM containers WHERE container_number LIKE ?",
                (pattern,),
            )
        )
    return results


def goods_line_tracking(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    supplier_id: int | None = None,
    consignee_id: int | None = None,
    import_order_id: int | None = None,
    exception_only: bool = False,
    missing_fields: bool = False,
    expected_loading_date: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["import_orders.order_status != 'cancelled'"]
    params: list[Any] = []
    if status is not None:
        clauses.append("goods_lines.logistics_status = ?")
        params.append(status)
    if supplier_id is not None:
        clauses.append("goods_lines.supplier_id = ?")
        params.append(supplier_id)
    if consignee_id is not None:
        clauses.append("import_orders.consignee_id = ?")
        params.append(consignee_id)
    if import_order_id is not None:
        clauses.append("goods_lines.import_order_id = ?")
        params.append(import_order_id)
    if exception_only:
        clauses.append("goods_lines.logistics_status = 'exception'")
    if expected_loading_date is not None:
        clauses.append("import_orders.expected_loading_date = ?")
        params.append(expected_loading_date)
    rows = conn.execute(
        f"""
        SELECT
            goods_lines.*,
            import_orders.order_no,
            import_orders.expected_loading_date,
            consignees.company_name AS consignee_name,
            suppliers.name AS supplier_name
        FROM goods_lines
        JOIN import_orders ON import_orders.id = goods_lines.import_order_id
        LEFT JOIN consignees ON consignees.id = import_orders.consignee_id
        LEFT JOIN suppliers ON suppliers.id = goods_lines.supplier_id
        WHERE {' AND '.join(clauses)}
        ORDER BY import_orders.expected_loading_date, import_orders.order_no, goods_lines.id
        """,
        params,
    ).fetchall()
    result = [dict(row) for row in rows]
    if missing_fields:
        result = [
            row
            for row in result
            if check_goods_line_stage(conn, goods_line_id=row["id"], stage=STAGE_FINAL_DOCUMENTS).blocked
        ]
    return result


def reminders(conn: sqlite3.Connection, *, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    lead_days = int(get_setting(conn, "reminders").get("lead_days", 3))
    output: list[dict[str, Any]] = []
    for order in conn.execute("SELECT * FROM import_orders WHERE order_status NOT IN ('completed', 'cancelled')"):
        if order["expected_loading_date"]:
            loading_date = date.fromisoformat(order["expected_loading_date"])
            if 0 <= (loading_date - today).days <= lead_days and order_stage_progress(conn, order["id"]) < 100:
                output.append(
                    {
                        "type": "goods_not_received_before_loading",
                        "import_order_id": order["id"],
                        "message": f"{order['order_no']} 预计装柜前仍有货物未全部到仓",
                    }
                )
    for row in goods_line_tracking(conn, missing_fields=True):
        output.append(
            {
                "type": "missing_document_fields",
                "import_order_id": row["import_order_id"],
                "goods_line_id": row["id"],
                "message": f"{row['order_no']} 货物项 {row['id']} 缺少单证字段",
            }
        )
    for row in conn.execute(
        """
        SELECT goods_lines.id, goods_lines.import_order_id, import_orders.order_no
        FROM goods_lines
        JOIN import_orders ON import_orders.id = goods_lines.import_order_id
        WHERE goods_lines.compliance_status NOT IN ('not_required', 'approved')
        """
    ):
        output.append(
            {
                "type": "compliance_not_approved",
                "import_order_id": row["import_order_id"],
                "goods_line_id": row["id"],
                "message": f"{row['order_no']} 货物项 {row['id']} 质检/合规未通过",
            }
        )
    return output


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
        "current_logistics_point": current_logistics_point(conn, order["id"]),
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


def _search_rows(
    conn: sqlite3.Connection,
    kind: str,
    sql: str,
    params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    return [{"type": kind, "id": row["id"], "label": row["label"] or ""} for row in conn.execute(sql, params)]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None

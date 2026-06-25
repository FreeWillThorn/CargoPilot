from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any

from .foundation import utc_now

STAGE_PURCHASING = "purchasing"
STAGE_CONTAINER_ESTIMATE = "container_estimate"
STAGE_RECEIVING = "receiving"
STAGE_FINAL_DOCUMENTS = "final_documents"
STAGE_LOADING_COMPLETE = "loading_complete"


@dataclass
class RequirementCheck:
    warnings: list[str]
    blockers: list[str]

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)


def calculate_cbm(row: sqlite3.Row | dict[str, Any]) -> float | None:
    if row["volume_cbm"] is not None:
        return row["volume_cbm"]
    required = ["carton_length_cm", "carton_width_cm", "carton_height_cm", "carton_count"]
    if any(row[field] is None for field in required):
        return None
    return row["carton_length_cm"] * row["carton_width_cm"] * row["carton_height_cm"] / 1_000_000 * row["carton_count"]


def calculate_gross_weight(row: sqlite3.Row | dict[str, Any]) -> float | None:
    if row["gross_weight"] is not None:
        return row["gross_weight"]
    if row["carton_gross_weight_kg"] is None or row["carton_count"] is None:
        return None
    return row["carton_gross_weight_kg"] * row["carton_count"]


def apply_package_calculations(conn: sqlite3.Connection, goods_line_id: int) -> None:
    row = _goods_line(conn, goods_line_id)
    conn.execute(
        """
        UPDATE goods_lines
        SET gross_weight = COALESCE(gross_weight, ?),
            volume_cbm = COALESCE(volume_cbm, ?),
            updated_at = ?
        WHERE id = ?
        """,
        (calculate_gross_weight(row), calculate_cbm(row), utc_now(), goods_line_id),
    )
    conn.commit()


def check_goods_line_stage(
    conn: sqlite3.Connection,
    *,
    goods_line_id: int,
    stage: str,
    context: dict[str, Any] | None = None,
) -> RequirementCheck:
    row = _goods_line(conn, goods_line_id)
    context = context or {}
    if stage == STAGE_PURCHASING:
        return _check(row, ["supplier_id", "cn_name", "quantity"], ["purchase_unit_price", "sales_unit_price", "target_markup"])
    if stage == STAGE_CONTAINER_ESTIMATE:
        return _check(
            row,
            [
                "carton_count",
                "units_per_carton",
                "carton_length_cm",
                "carton_width_cm",
                "carton_height_cm",
                "carton_gross_weight_kg",
            ],
        )
    if stage == STAGE_RECEIVING:
        blockers = []
        if not _has_tracking_number(conn, goods_line_id):
            blockers.append("domestic_tracking_no")
        if _missing(row["shipping_mark"]):
            blockers.append("shipping_mark")
        if _missing(context.get("received_carton_count")):
            blockers.append("received_carton_count")
        warnings = [] if context.get("has_receiving_photo") else ["receiving_photo"]
        return RequirementCheck(warnings=warnings, blockers=blockers)
    if stage == STAGE_FINAL_DOCUMENTS:
        blockers = [
            field
            for field in ["customs_en_name", "hs_code", "quantity", "carton_count", "sales_unit_price", "sales_currency"]
            if _missing(row[field])
        ]
        if calculate_gross_weight(row) is None:
            blockers.append("gross_weight")
        if calculate_cbm(row) is None:
            blockers.append("volume_cbm")
        blockers.extend(_missing_consignee_fields(conn, row["import_order_id"]))
        return RequirementCheck(warnings=[], blockers=blockers)
    if stage == STAGE_LOADING_COMPLETE:
        blockers = [field for field in ["container_type", "container_number", "seal_number", "loading_date"] if _missing(context.get(field))]
        warnings = [] if context.get("has_loading_photo") else ["loading_photo"]
        return RequirementCheck(warnings=warnings, blockers=blockers)
    raise ValueError(f"unknown stage: {stage}")


def _check(
    row: sqlite3.Row,
    required_fields: list[str],
    one_of: list[str] | None = None,
) -> RequirementCheck:
    blockers = [field for field in required_fields if _missing(row[field])]
    if one_of and all(_missing(row[field]) for field in one_of):
        blockers.append("/".join(one_of))
    return RequirementCheck(warnings=[], blockers=blockers)


def _goods_line(conn: sqlite3.Connection, goods_line_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
    if row is None:
        raise KeyError(goods_line_id)
    return row


def _has_tracking_number(conn: sqlite3.Connection, goods_line_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM domestic_tracking_numbers WHERE goods_line_id = ? LIMIT 1",
        (goods_line_id,),
    ).fetchone()
    return row is not None


def _missing_consignee_fields(conn: sqlite3.Connection, import_order_id: int) -> list[str]:
    row = conn.execute(
        """
        SELECT consignees.company_name, consignees.address
        FROM import_orders
        LEFT JOIN consignees ON consignees.id = import_orders.consignee_id
        WHERE import_orders.id = ?
        """,
        (import_order_id,),
    ).fetchone()
    if row is None or _missing(row["company_name"]) or _missing(row["address"]):
        return ["consignee_document_information"]
    return []


def _missing(value: Any) -> bool:
    return value is None or value == ""

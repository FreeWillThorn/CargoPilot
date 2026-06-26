from __future__ import annotations

import sqlite3
from typing import Any

from .foundation import utc_now
from .master_data import require_admin

LINE_COST = "cost"
LINE_CHARGE = "charge"

COST_TYPES = {
    "purchase",
    "domestic_logistics",
    "warehouse",
    "inspection_certificate",
    "document_customs",
    "sea_freight",
    "other",
    "adjustment",
}
CHARGE_TYPES = {"product_sales", "freight_service", "pass_through", "other", "adjustment"}


def calculate_sales_price(
    purchase_unit_price: float,
    *,
    target_markup: float | None = None,
    target_margin: float | None = None,
    manual_sales_unit_price: float | None = None,
) -> float:
    if manual_sales_unit_price is not None:
        return manual_sales_unit_price
    if target_markup is not None:
        return purchase_unit_price * (1 + target_markup)
    if target_margin is not None:
        if target_margin >= 1:
            raise ValueError("target_margin must be less than 1")
        return purchase_unit_price / (1 - target_margin)
    return purchase_unit_price


def update_goods_line_quote(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    goods_line_id: int,
    purchase_unit_price: float,
    purchase_currency: str,
    sales_currency: str,
    target_markup: float | None = None,
    target_margin: float | None = None,
    manual_sales_unit_price: float | None = None,
) -> float:
    require_admin(actor_role)
    sales_unit_price = calculate_sales_price(
        purchase_unit_price,
        target_markup=target_markup,
        target_margin=target_margin,
        manual_sales_unit_price=manual_sales_unit_price,
    )
    conn.execute(
        """
        UPDATE goods_lines
        SET purchase_unit_price = ?,
            purchase_currency = ?,
            sales_currency = ?,
            target_markup = ?,
            target_margin = ?,
            sales_unit_price = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            purchase_unit_price,
            purchase_currency,
            sales_currency,
            target_markup,
            target_margin,
            sales_unit_price,
            utc_now(),
            goods_line_id,
        ),
    )
    conn.commit()
    return sales_unit_price


def add_finance_line(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    import_order_id: int,
    line_kind: str,
    line_type: str,
    amount: float,
    currency: str,
    exchange_rate_to_base: float = 1,
    goods_line_id: int | None = None,
    notes: str = "",
) -> int:
    require_admin(actor_role)
    _validate_line(line_kind, line_type)
    cursor = conn.execute(
        """
        INSERT INTO finance_lines (
            import_order_id, goods_line_id, line_kind, line_type,
            amount, currency, exchange_rate_to_base, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_order_id,
            goods_line_id,
            line_kind,
            line_type,
            amount,
            currency,
            exchange_rate_to_base,
            notes,
            utc_now(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def update_finance_line(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    finance_line_id: int,
    goods_line_id: int | None,
    line_kind: str,
    line_type: str,
    amount: float,
    currency: str,
    exchange_rate_to_base: float = 1,
    notes: str = "",
) -> None:
    require_admin(actor_role)
    _validate_line(line_kind, line_type)
    conn.execute(
        """
        UPDATE finance_lines
        SET goods_line_id = ?,
            line_kind = ?,
            line_type = ?,
            amount = ?,
            currency = ?,
            exchange_rate_to_base = ?,
            notes = ?
        WHERE id = ?
        """,
        (
            goods_line_id,
            line_kind,
            line_type,
            amount,
            currency,
            exchange_rate_to_base,
            notes,
            finance_line_id,
        ),
    )
    conn.commit()


def delete_finance_line(conn: sqlite3.Connection, *, actor_role: str, finance_line_id: int) -> None:
    require_admin(actor_role)
    conn.execute("DELETE FROM finance_lines WHERE id = ?", (finance_line_id,))
    conn.commit()


def calculate_profit(
    conn: sqlite3.Connection,
    *,
    import_order_id: int,
    base_currency: str,
) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT * FROM finance_lines WHERE import_order_id = ?",
        (import_order_id,),
    ).fetchall()
    costs = sum(
        row["amount"] * row["exchange_rate_to_base"]
        for row in rows
        if row["line_kind"] == LINE_COST
    )
    charges = sum(
        row["amount"] * row["exchange_rate_to_base"]
        for row in rows
        if row["line_kind"] == LINE_CHARGE
    )
    return {
        "base_currency": base_currency,
        "total_cost": costs,
        "total_charge": charges,
        "profit": charges - costs,
    }


def _validate_line(line_kind: str, line_type: str) -> None:
    if line_kind == LINE_COST and line_type in COST_TYPES:
        return
    if line_kind == LINE_CHARGE and line_type in CHARGE_TYPES:
        return
    raise ValueError(f"invalid finance line: {line_kind}/{line_type}")

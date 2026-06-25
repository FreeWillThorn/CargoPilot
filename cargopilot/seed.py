from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3

from .containers import create_container, record_loading
from .documents import DOC_COMMERCIAL_INVOICE, DOC_PACKING_LIST, generate_export_document
from .finance import LINE_CHARGE, LINE_COST, add_finance_line
from .foundation import ROLE_ADMIN, ROLE_WAREHOUSE, connect, create_user, initialize_database, set_setting
from .master_data import WAREHOUSE_PORT, WAREHOUSE_RECEIVING, create_consignee, create_supplier, create_warehouse
from .orders import create_goods_line, create_import_order, update_goods_line
from .receiving import add_domestic_tracking_number, record_receiving


DEFAULT_DB = Path("data/cargopilot.sqlite3")


def seed_demo(db_path: str | Path = DEFAULT_DB) -> dict[str, int]:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        initialize_database(conn)
        _ensure_users(conn)
        _ensure_settings(conn)
        consignee_id = _ensure_consignee(conn)
        supplier_id = _ensure_supplier(conn)
        receiving_warehouse_id = _ensure_warehouse(conn, WAREHOUSE_RECEIVING, "Ningbo Demo Receiving")
        port_warehouse_id = _ensure_warehouse(conn, WAREHOUSE_PORT, "Ningbo Port Warehouse")
        order_id = _ensure_order(conn, consignee_id, receiving_warehouse_id, port_warehouse_id)
        cup_id = _ensure_goods_line(
            conn,
            order_id,
            supplier_id,
            sku_or_model="CUP-A1",
            customs_en_name="Ceramic Cup",
            carton_count=10,
            quantity=100,
            sales_unit_price=2.5,
        )
        plate_id = _ensure_goods_line(
            conn,
            order_id,
            supplier_id,
            sku_or_model="PLATE-B2",
            customs_en_name="Porcelain Plate",
            carton_count=8,
            quantity=80,
            sales_unit_price=3.2,
        )
        add_domestic_tracking_number(conn, actor_role=ROLE_ADMIN, goods_line_id=cup_id, tracking_no="YT-DEMO-001")
        add_domestic_tracking_number(conn, actor_role=ROLE_ADMIN, goods_line_id=plate_id, tracking_no="YT-DEMO-002")
        _ensure_receiving(conn, cup_id)
        _ensure_finance(conn, order_id, cup_id, plate_id)
        container_id = _ensure_container(conn, order_id)
        _ensure_loading(conn, container_id, cup_id)
        _ensure_documents(conn, order_id, db_path.parent / "documents")
        return {"order_id": order_id, "cup_goods_line_id": cup_id, "plate_goods_line_id": plate_id}
    finally:
        conn.close()


def _ensure_users(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM users WHERE email = 'admin@example.com'").fetchone() is None:
        create_user(conn, email="admin@example.com", name="Admin", role=ROLE_ADMIN, password="admin")
    if conn.execute("SELECT 1 FROM users WHERE email = 'warehouse@example.com'").fetchone() is None:
        create_user(conn, email="warehouse@example.com", name="Warehouse", role=ROLE_WAREHOUSE, password="warehouse")


def _ensure_settings(conn: sqlite3.Connection) -> None:
    set_setting(
        conn,
        "seller",
        {
            "company_name": "CargoPilot Trading Ltd",
            "address": "Ningbo, China",
            "phone": "+86 574 0000 0000",
            "email": "ops@cargopilot.local",
            "tax_or_business_id": "",
            "bank_info": "",
        },
    )
    set_setting(
        conn,
        "defaults",
        {
            "origin_country": "China",
            "origin_port": "Ningbo",
            "purchase_currency": "CNY",
            "sales_currency": "EUR",
        },
    )
    set_setting(conn, "reminders", {"lead_days": 5})


def _ensure_consignee(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM consignees WHERE company_name = 'Euro Demo Import GmbH'").fetchone()
    if row:
        return int(row["id"])
    return create_consignee(
        conn,
        actor_role=ROLE_ADMIN,
        company_name="Euro Demo Import GmbH",
        contact_name="Anna Keller",
        email="anna@example.eu",
        phone="+49 30 0000",
        tax_id="DEMO-EORI",
        address="Demo Strasse 1, Berlin, Germany",
        default_destination_port="Hamburg",
        default_trade_term="FOB",
        default_sales_currency="EUR",
    )


def _ensure_supplier(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM suppliers WHERE name = 'Yiwu Demo Ceramics'").fetchone()
    if row:
        return int(row["id"])
    supplier_id, _ = create_supplier(
        conn,
        actor_role=ROLE_ADMIN,
        name="Yiwu Demo Ceramics",
        contact_name="Chen Wei",
        phone="+86 138 0000 0000",
        email="sales@demo-ceramics.cn",
        store_url="https://1688.com/demo-ceramics",
        usual_categories=["ceramic tableware"],
    )
    return supplier_id


def _ensure_warehouse(conn: sqlite3.Connection, warehouse_type: str, name: str) -> int:
    row = conn.execute("SELECT id FROM warehouses WHERE type = ? AND name = ?", (warehouse_type, name)).fetchone()
    if row:
        return int(row["id"])
    return create_warehouse(
        conn,
        actor_role=ROLE_ADMIN,
        type=warehouse_type,
        name=name,
        contact_name="Warehouse Team",
        phone="+86 574 1000",
        address="Ningbo Demo Logistics Park",
    )


def _ensure_order(conn: sqlite3.Connection, consignee_id: int, receiving_warehouse_id: int, port_warehouse_id: int) -> int:
    row = conn.execute("SELECT id FROM import_orders WHERE order_no = 'CP-DEMO-0001'").fetchone()
    if row:
        return int(row["id"])
    return create_import_order(
        conn,
        actor_role=ROLE_ADMIN,
        order_no="CP-DEMO-0001",
        consignee_id=consignee_id,
        receiving_warehouse_id=receiving_warehouse_id,
        port_warehouse_id=port_warehouse_id,
        trade_term="FOB",
        origin_country="China",
        origin_port="Ningbo",
        destination_country="Germany",
        destination_port="Hamburg",
        order_status="receiving",
        expected_loading_date="2026-07-10",
        purchase_currency="CNY",
        sales_currency="EUR",
        internal_notes="Demo order for first MVP review",
    )


def _ensure_goods_line(
    conn: sqlite3.Connection,
    order_id: int,
    supplier_id: int,
    *,
    sku_or_model: str,
    customs_en_name: str,
    carton_count: int,
    quantity: int,
    sales_unit_price: float,
) -> int:
    row = conn.execute(
        "SELECT id FROM goods_lines WHERE import_order_id = ? AND sku_or_model = ?",
        (order_id, sku_or_model),
    ).fetchone()
    values = {
        "supplier_id": supplier_id,
        "customer_item_no": sku_or_model,
        "sku_or_model": sku_or_model,
        "product_url": f"https://detail.1688.com/offer/{sku_or_model}.html",
        "cn_name": "陶瓷餐具",
        "en_name": customs_en_name,
        "customs_en_name": customs_en_name,
        "category": "ceramic tableware",
        "hs_code": "691200",
        "quantity": quantity,
        "unit": "pcs",
        "packaging_method": "carton",
        "carton_count": carton_count,
        "units_per_carton": quantity / carton_count,
        "carton_length_cm": 40,
        "carton_width_cm": 30,
        "carton_height_cm": 20,
        "carton_gross_weight_kg": 8,
        "shipping_mark": "CP-DEMO-MARK",
        "target_markup": 0.25,
        "sales_unit_price": sales_unit_price,
        "sales_currency": "EUR",
        "purchase_unit_price": round(sales_unit_price * 7, 2),
        "purchase_currency": "CNY",
    }
    if row:
        update_goods_line(conn, actor_role=ROLE_ADMIN, goods_line_id=int(row["id"]), **values)
        return int(row["id"])
    return create_goods_line(conn, actor_role=ROLE_ADMIN, import_order_id=order_id, **values)


def _ensure_receiving(conn: sqlite3.Connection, goods_line_id: int) -> None:
    if conn.execute("SELECT 1 FROM receiving_records WHERE goods_line_id = ?", (goods_line_id,)).fetchone():
        return
    admin_id = conn.execute("SELECT id FROM users WHERE email = 'admin@example.com'").fetchone()["id"]
    record_receiving(
        conn,
        actor_role=ROLE_ADMIN,
        actor_user_id=int(admin_id),
        goods_line_id=goods_line_id,
        domestic_tracking_no="YT-DEMO-001",
        received_carton_count=10,
        package_condition="ok",
    )


def _ensure_finance(conn: sqlite3.Connection, order_id: int, cup_id: int, plate_id: int) -> None:
    if conn.execute("SELECT 1 FROM finance_lines WHERE import_order_id = ?", (order_id,)).fetchone():
        return
    add_finance_line(conn, actor_role=ROLE_ADMIN, import_order_id=order_id, goods_line_id=cup_id, line_kind=LINE_COST, line_type="purchase", amount=1750, currency="CNY", exchange_rate_to_base=0.13)
    add_finance_line(conn, actor_role=ROLE_ADMIN, import_order_id=order_id, goods_line_id=plate_id, line_kind=LINE_COST, line_type="purchase", amount=1792, currency="CNY", exchange_rate_to_base=0.13)
    add_finance_line(conn, actor_role=ROLE_ADMIN, import_order_id=order_id, line_kind=LINE_CHARGE, line_type="product_sales", amount=506, currency="EUR")


def _ensure_container(conn: sqlite3.Connection, order_id: int) -> int:
    row = conn.execute("SELECT id FROM containers WHERE container_number = 'DEMO1234567'").fetchone()
    if row:
        return int(row["id"])
    return create_container(
        conn,
        actor_role=ROLE_ADMIN,
        import_order_id=order_id,
        container_type="20GP",
        container_number="DEMO1234567",
        seal_number="SEAL-DEMO",
        loading_date="2026-07-10",
    )


def _ensure_loading(conn: sqlite3.Connection, container_id: int, goods_line_id: int) -> None:
    if conn.execute("SELECT 1 FROM loading_records WHERE container_id = ? AND goods_line_id = ?", (container_id, goods_line_id)).fetchone():
        return
    admin_id = conn.execute("SELECT id FROM users WHERE email = 'admin@example.com'").fetchone()["id"]
    record_loading(
        conn,
        actor_role=ROLE_ADMIN,
        actor_user_id=int(admin_id),
        container_id=container_id,
        goods_line_id=goods_line_id,
        loaded_carton_count=10,
    )


def _ensure_documents(conn: sqlite3.Connection, order_id: int, output_dir: Path) -> None:
    for document_type in (DOC_COMMERCIAL_INVOICE, DOC_PACKING_LIST):
        if conn.execute("SELECT 1 FROM documents WHERE import_order_id = ? AND document_type = ?", (order_id, document_type)).fetchone():
            continue
        generate_export_document(
            conn,
            actor_role=ROLE_ADMIN,
            import_order_id=order_id,
            document_type=document_type,
            output_dir=output_dir,
            final=False,
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed CargoPilot demo data")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    args = parser.parse_args(argv)
    result = seed_demo(args.db)
    print(f"Seeded CargoPilot demo data in {args.db}")
    print(f"Demo order id: {result['order_id']}")
    print("Login: admin@example.com / admin or warehouse@example.com / warehouse")


if __name__ == "__main__":
    main()

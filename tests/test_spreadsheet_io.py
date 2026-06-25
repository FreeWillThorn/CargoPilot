import tempfile
import unittest
from pathlib import Path

from cargopilot.foundation import ROLE_ADMIN, connect, initialize_database
from cargopilot.master_data import create_supplier
from cargopilot.orders import create_goods_line, create_import_order
from cargopilot.spreadsheet_io import (
    CUSTOMER_PURCHASE_HEADERS,
    SUPPLIER_PACKAGE_HEADERS,
    export_goods_lines,
    export_rows_xlsx,
    import_customer_purchase_list,
    import_supplier_package_logistics,
    read_xlsx_rows,
)


class SpreadsheetIoTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_customer_purchase_import_creates_supplier_and_goods_line(self):
        order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN, order_no="CP-2026-0001")
        path = self.tmp_path / "customer.xlsx"
        export_rows_xlsx(
            path,
            CUSTOMER_PURCHASE_HEADERS,
            [
                {
                    "order_no": "CP-2026-0001",
                    "supplier_name": "Yiwu Cups",
                    "customer_item_no": "C-1",
                    "product_url": "https://1688.example/item",
                    "cn_name": "杯子",
                    "en_name": "Cup",
                    "customs_en_name": "Ceramic Cup",
                    "sku_or_model": "A1",
                    "category": "ceramic",
                    "hs_code": "691200",
                    "quantity": 100,
                    "unit": "pcs",
                    "target_markup": 0.2,
                    "sales_unit_price": "",
                    "sales_currency": "EUR",
                    "notes": "first row",
                }
            ],
        )

        result = import_customer_purchase_list(self.conn, actor_role=ROLE_ADMIN, path=path)
        self.assertEqual(result.created, 1)
        self.assertEqual(result.errors, [])

        supplier = self.conn.execute("SELECT * FROM suppliers WHERE name = 'Yiwu Cups'").fetchone()
        goods = self.conn.execute("SELECT * FROM goods_lines WHERE import_order_id = ?", (order_id,)).fetchone()
        self.assertEqual(goods["supplier_id"], supplier["id"])
        self.assertEqual(goods["product_url"], "https://1688.example/item")
        self.assertEqual(goods["customs_en_name"], "Ceramic Cup")

    def test_invalid_headers_report_clear_error(self):
        path = self.tmp_path / "bad.xlsx"
        export_rows_xlsx(path, ["wrong"], [{"wrong": "value"}])

        result = import_customer_purchase_list(self.conn, actor_role=ROLE_ADMIN, path=path)
        self.assertEqual(result.created, 0)
        self.assertIn("Invalid headers", result.errors[0])

    def test_supplier_package_import_updates_existing_goods_line(self):
        order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN, order_no="CP-2026-0002")
        supplier_id, _ = create_supplier(self.conn, actor_role=ROLE_ADMIN, name="Yiwu Cups")
        goods_line_id = create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=order_id,
            supplier_id=supplier_id,
            sku_or_model="A1",
            customs_en_name="Ceramic Cup",
        )
        path = self.tmp_path / "package.xlsx"
        export_rows_xlsx(
            path,
            SUPPLIER_PACKAGE_HEADERS,
            [
                {
                    "order_no": "CP-2026-0002",
                    "supplier_name": "Yiwu Cups",
                    "sku_or_model": "A1",
                    "customs_en_name": "Ceramic Cup",
                    "carton_count": 10,
                    "units_per_carton": 12,
                    "carton_length_cm": 40,
                    "carton_width_cm": 30,
                    "carton_height_cm": 20,
                    "carton_gross_weight_kg": 8,
                    "domestic_tracking_no": "YT123",
                    "shipping_mark": "CP-1",
                    "purchase_unit_price": 9,
                    "purchase_currency": "CNY",
                    "supplier_invoice_no": "INV-1",
                    "notes": "packed",
                }
            ],
        )

        result = import_supplier_package_logistics(self.conn, actor_role=ROLE_ADMIN, path=path)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.errors, [])

        goods = self.conn.execute("SELECT * FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        tracking = self.conn.execute("SELECT * FROM domestic_tracking_numbers WHERE goods_line_id = ?", (goods_line_id,)).fetchone()
        self.assertEqual(goods["carton_count"], 10)
        self.assertEqual(goods["shipping_mark"], "CP-1")
        self.assertEqual(tracking["tracking_no"], "YT123")

    def test_export_shape(self):
        order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN, order_no="CP-2026-0003")
        create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=order_id,
            cn_name="杯子",
            customs_en_name="Ceramic Cup",
        )
        path = self.tmp_path / "goods.xlsx"
        export_goods_lines(self.conn, path)

        rows = read_xlsx_rows(path)
        self.assertIn("customs_en_name", rows[0])
        self.assertIn("Ceramic Cup", rows[1])


if __name__ == "__main__":
    unittest.main()

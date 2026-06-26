import tempfile
import unittest
from pathlib import Path

from cargopilot.foundation import ROLE_ADMIN, connect, initialize_database
from cargopilot.master_data import create_supplier
from cargopilot.orders import create_goods_line, create_import_order
from cargopilot.spreadsheet_io import (
    CUSTOMER_PURCHASE_HEADERS,
    FINANCE_COST_UPLOAD_HEADERS,
    ORDER_GOODS_UPLOAD_HEADERS,
    SUPPLIER_PACKAGE_HEADERS,
    export_goods_lines,
    export_rows_xlsx,
    import_customer_purchase_list,
    import_finance_cost_upload,
    import_order_goods_upload,
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

    def test_order_goods_upload_imports_chinese_template(self):
        order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN, order_no="CP-2026-0004")
        path = self.tmp_path / "goods-upload.xlsx"
        export_rows_xlsx(
            path,
            ORDER_GOODS_UPLOAD_HEADERS,
            [
                {
                    "产品名称": "提梁四方皮包/绿色",
                    "数量（非包裹数）": 10,
                    "实际付款": 1690,
                    "链接": "https://1688.example/bag",
                    "厂家名称": "宏门工厂",
                },
                {
                    "产品名称": "提梁四方皮包/黑色",
                    "数量（非包裹数）": 10,
                    "实际付款": "-",
                    "链接": "",
                    "厂家名称": "宏门工厂",
                },
            ],
        )

        result = import_order_goods_upload(self.conn, actor_role=ROLE_ADMIN, import_order_id=order_id, path=path)
        self.assertEqual(result.created, 2)
        self.assertEqual(result.errors, [])

        supplier = self.conn.execute("SELECT * FROM suppliers WHERE name = '宏门工厂'").fetchone()
        rows = self.conn.execute("SELECT * FROM goods_lines WHERE import_order_id = ? ORDER BY id", (order_id,)).fetchall()
        self.assertEqual(rows[0]["supplier_id"], supplier["id"])
        self.assertEqual(rows[0]["cn_name"], "提梁四方皮包/绿色")
        self.assertEqual(rows[0]["purchase_unit_price"], 169)
        self.assertEqual(rows[1]["purchase_unit_price"], None)

    def test_order_goods_upload_reports_invalid_rows(self):
        order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN, order_no="CP-2026-0005")
        path = self.tmp_path / "bad-goods-upload.xlsx"
        export_rows_xlsx(path, ORDER_GOODS_UPLOAD_HEADERS, [{"产品名称": "", "数量（非包裹数）": "x"}])

        result = import_order_goods_upload(self.conn, actor_role=ROLE_ADMIN, import_order_id=order_id, path=path)
        self.assertEqual(result.created, 0)
        self.assertIn("产品名称不能为空", result.errors[0])

    def test_finance_cost_upload_imports_cost_lines(self):
        order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN, order_no="CP-2026-0006")
        path = self.tmp_path / "cost-upload.xlsx"
        export_rows_xlsx(
            path,
            FINANCE_COST_UPLOAD_HEADERS,
            [
                {
                    "中文项目 (Item)": "海运费",
                    "English Description": "Ocean Freight (The container)",
                    "Amount": 2400,
                    "Currency": "USD",
                    "说明备注 (Remarks)": "Main carriage sea freight",
                },
                {
                    "中文项目 (Item)": "集装箱操作费",
                    "English Description": "Container Handling Charge",
                    "Amount": 25,
                    "Currency": "CNY",
                    "说明备注 (Remarks)": "",
                },
            ],
        )

        result = import_finance_cost_upload(self.conn, actor_role=ROLE_ADMIN, import_order_id=order_id, path=path)
        self.assertEqual(result.created, 2)
        self.assertEqual(result.errors, [])
        rows = self.conn.execute("SELECT * FROM finance_lines WHERE import_order_id = ? ORDER BY id", (order_id,)).fetchall()
        self.assertEqual(rows[0]["line_type"], "sea_freight")
        self.assertEqual(rows[0]["amount"], 2400)
        self.assertEqual(rows[0]["currency"], "USD")
        self.assertEqual(rows[1]["line_type"], "other")

    def test_finance_cost_upload_reports_invalid_amounts(self):
        order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN, order_no="CP-2026-0007")
        path = self.tmp_path / "bad-cost-upload.xlsx"
        export_rows_xlsx(path, FINANCE_COST_UPLOAD_HEADERS, [{"中文项目 (Item)": "海运费", "English Description": "Ocean Freight", "Amount": "x", "Currency": "USD"}])

        result = import_finance_cost_upload(self.conn, actor_role=ROLE_ADMIN, import_order_id=order_id, path=path)
        self.assertEqual(result.created, 0)
        self.assertIn("Amount 无效", result.errors[0])

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

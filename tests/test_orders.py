import unittest

from cargopilot.foundation import ROLE_ADMIN, ROLE_WAREHOUSE, connect, initialize_database
from cargopilot.master_data import (
    WAREHOUSE_PORT,
    WAREHOUSE_RECEIVING,
    create_consignee,
    create_supplier,
    create_warehouse,
)
from cargopilot.orders import (
    GOODS_LINE_FIELD_GROUPS,
    IMPORT_ORDER_DETAIL_TABS,
    IMPORT_ORDER_LIST_COLUMNS,
    create_goods_line,
    create_import_order,
    goods_line_split_key,
    list_import_order_cards,
    next_order_no,
    update_import_order,
)


class OrdersTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_order_number_generation(self):
        self.assertEqual(next_order_no(self.conn, 2026), "CP-2026-0001")
        self.assertEqual(next_order_no(self.conn, 2026), "CP-2026-0002")

    def test_create_import_order_uses_consignee_defaults(self):
        consignee_id = create_consignee(
            self.conn,
            actor_role=ROLE_ADMIN,
            company_name="Euro Import GmbH",
            default_destination_port="Hamburg",
            default_trade_term="FOB",
            default_sales_currency="EUR",
        )
        receiving_id = create_warehouse(
            self.conn,
            actor_role=ROLE_ADMIN,
            type=WAREHOUSE_RECEIVING,
            name="Receiving",
        )
        port_id = create_warehouse(
            self.conn,
            actor_role=ROLE_ADMIN,
            type=WAREHOUSE_PORT,
            name="Port",
        )

        order_id = create_import_order(
            self.conn,
            actor_role=ROLE_ADMIN,
            consignee_id=consignee_id,
            receiving_warehouse_id=receiving_id,
            port_warehouse_id=port_id,
        )

        order = self.conn.execute("SELECT * FROM import_orders WHERE id = ?", (order_id,)).fetchone()
        self.assertTrue(order["order_no"].startswith("CP-"))
        self.assertEqual(order["destination_port"], "Hamburg")
        self.assertEqual(order["trade_term"], "FOB")
        self.assertEqual(order["sales_currency"], "EUR")

        update_import_order(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=order_id,
            order_no="CUSTOM-1",
        )
        updated = self.conn.execute("SELECT order_no FROM import_orders WHERE id = ?", (order_id,)).fetchone()
        self.assertEqual(updated["order_no"], "CUSTOM-1")

    def test_create_incomplete_goods_line(self):
        order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN)
        goods_line_id = create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=order_id,
            cn_name="杯子",
            quantity=100,
        )

        row = self.conn.execute("SELECT * FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        self.assertEqual(row["cn_name"], "杯子")
        self.assertEqual(row["quantity"], 100)
        self.assertEqual(row["logistics_status"], "not_ordered")
        self.assertEqual(row["customs_en_name"], "")
        self.assertIsNone(row["carton_count"])

    def test_goods_line_split_key(self):
        supplier_id, _ = create_supplier(self.conn, actor_role=ROLE_ADMIN, name="Supplier")
        first = {
            "supplier_id": supplier_id,
            "sku_or_model": "A1",
            "customs_en_name": "Ceramic Cup",
            "packaging_method": "12/carton",
        }
        second = {**first, "packaging_method": "24/carton"}

        self.assertNotEqual(goods_line_split_key(first), goods_line_split_key(second))

    def test_warehouse_user_cannot_manage_orders_or_goods_lines(self):
        with self.assertRaises(PermissionError):
            create_import_order(self.conn, actor_role=ROLE_WAREHOUSE)

    def test_list_and_detail_ui_contracts(self):
        self.assertEqual(
            IMPORT_ORDER_LIST_COLUMNS,
            ("id", "order_no", "consignee_id", "destination_port", "order_status", "expected_loading_date"),
        )
        self.assertIn("goods_lines", IMPORT_ORDER_DETAIL_TABS)
        self.assertIn("packaging", GOODS_LINE_FIELD_GROUPS)

        order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN, order_no="CP-2026-9999")
        cards = list_import_order_cards(self.conn)
        self.assertEqual(cards, [
            {
                "id": order_id,
                "order_no": "CP-2026-9999",
                "consignee_id": None,
                "destination_port": "",
                "order_status": "draft",
                "expected_loading_date": None,
            }
        ])


if __name__ == "__main__":
    unittest.main()

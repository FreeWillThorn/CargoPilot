import unittest

from cargopilot.dashboard import ORDER_STATUS_COLORS, dashboard_orders, order_stage_progress
from cargopilot.foundation import ROLE_ADMIN, connect, initialize_database
from cargopilot.master_data import create_consignee
from cargopilot.orders import create_goods_line, create_import_order


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)
        self.consignee_id = create_consignee(
            self.conn,
            actor_role=ROLE_ADMIN,
            company_name="Euro Import",
            address="Berlin",
        )

    def tearDown(self):
        self.conn.close()

    def test_status_colors_match_prd(self):
        self.assertEqual(ORDER_STATUS_COLORS["draft"], "gray")
        self.assertEqual(ORDER_STATUS_COLORS["purchasing"], "blue")
        self.assertEqual(ORDER_STATUS_COLORS["receiving"], "orange")
        self.assertEqual(ORDER_STATUS_COLORS["loaded"], "green")
        self.assertEqual(ORDER_STATUS_COLORS["cancelled"], "red")

    def test_progress_uses_goods_line_count(self):
        order_id = create_import_order(
            self.conn,
            actor_role=ROLE_ADMIN,
            consignee_id=self.consignee_id,
            order_status="receiving",
        )
        create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=order_id,
            logistics_status="received_at_warehouse",
        )
        create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=order_id,
            logistics_status="domestic_shipped",
        )

        self.assertEqual(order_stage_progress(self.conn, order_id), 50)

    def test_dashboard_card_data_and_clickable_filters(self):
        order_id = create_import_order(
            self.conn,
            actor_role=ROLE_ADMIN,
            consignee_id=self.consignee_id,
            order_no="CP-2026-0001",
            order_status="purchasing",
            destination_port="Hamburg",
            expected_loading_date="2026-07-01",
        )
        create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=order_id,
            logistics_status="exception",
        )
        create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=order_id,
            logistics_status="ordered",
        )

        cards = dashboard_orders(self.conn)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["order_no"], "CP-2026-0001")
        self.assertEqual(cards[0]["consignee"], "Euro Import")
        self.assertEqual(cards[0]["status_color"], "blue")
        self.assertEqual(cards[0]["exception_count"], 1)
        self.assertTrue(cards[0]["has_exception_badge"])
        self.assertEqual(cards[0]["exception_link"], {"filter": "exceptions", "import_order_id": order_id})
        self.assertGreater(cards[0]["missing_data_count"], 0)
        self.assertEqual(cards[0]["missing_data_link"], {"filter": "missing_data", "import_order_id": order_id})

    def test_basic_filters(self):
        create_import_order(
            self.conn,
            actor_role=ROLE_ADMIN,
            consignee_id=self.consignee_id,
            order_status="purchasing",
        )
        create_import_order(
            self.conn,
            actor_role=ROLE_ADMIN,
            consignee_id=self.consignee_id,
            order_status="completed",
        )

        self.assertEqual(len(dashboard_orders(self.conn, status="purchasing")), 1)
        self.assertEqual(len(dashboard_orders(self.conn, consignee_id=self.consignee_id)), 2)


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import date

from cargopilot.dashboard import (
    current_logistics_point,
    global_search,
    goods_line_tracking,
    reminders,
)
from cargopilot.foundation import ROLE_ADMIN, connect, initialize_database
from cargopilot.master_data import create_consignee, create_supplier
from cargopilot.orders import create_goods_line, create_import_order
from cargopilot.receiving import add_domestic_tracking_number


class FullDashboardTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)
        self.consignee_id = create_consignee(
            self.conn,
            actor_role=ROLE_ADMIN,
            company_name="Euro Import",
            address="Berlin",
        )
        self.supplier_id, _ = create_supplier(self.conn, actor_role=ROLE_ADMIN, name="Yiwu Cups")
        self.order_id = create_import_order(
            self.conn,
            actor_role=ROLE_ADMIN,
            order_no="CP-2026-0001",
            consignee_id=self.consignee_id,
            order_status="receiving",
            expected_loading_date="2026-07-01",
        )
        self.goods_line_id = create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            supplier_id=self.supplier_id,
            cn_name="杯子",
            customs_en_name="Ceramic Cup",
            shipping_mark="CP-MARK",
            logistics_status="domestic_shipped",
        )
        add_domestic_tracking_number(
            self.conn,
            actor_role=ROLE_ADMIN,
            goods_line_id=self.goods_line_id,
            tracking_no="YT123",
        )

    def tearDown(self):
        self.conn.close()

    def test_current_logistics_point(self):
        self.assertEqual(current_logistics_point(self.conn, self.order_id), "supplier_side")
        self.conn.execute(
            "UPDATE goods_lines SET logistics_status = 'received_at_warehouse' WHERE id = ?",
            (self.goods_line_id,),
        )
        self.assertEqual(current_logistics_point(self.conn, self.order_id), "receiving_warehouse")

    def test_global_search(self):
        labels = {(row["type"], row["label"]) for row in global_search(self.conn, "CP-2026")}
        self.assertIn(("import_order", "CP-2026-0001"), labels)

        goods_results = global_search(self.conn, "YT123")
        self.assertEqual(goods_results[0]["type"], "goods_line")
        self.assertIn("Ceramic Cup", goods_results[0]["label"])

        self.assertEqual(global_search(self.conn, "Euro Import")[0]["type"], "import_order")
        self.assertEqual(global_search(self.conn, "Yiwu Cups")[0]["type"], "goods_line")
        self.assertEqual(global_search(self.conn, "CP-MARK")[0]["type"], "goods_line")

    def test_goods_line_tracking_filters(self):
        self.assertEqual(len(goods_line_tracking(self.conn, status="domestic_shipped")), 1)
        self.assertEqual(len(goods_line_tracking(self.conn, supplier_id=self.supplier_id)), 1)
        self.assertEqual(len(goods_line_tracking(self.conn, consignee_id=self.consignee_id)), 1)
        self.assertEqual(len(goods_line_tracking(self.conn, import_order_id=self.order_id)), 1)
        self.assertEqual(len(goods_line_tracking(self.conn, missing_fields=True)), 1)

    def test_reminders(self):
        output = reminders(self.conn, today=date(2026, 6, 29))
        types = {item["type"] for item in output}
        self.assertIn("goods_not_received_before_loading", types)
        self.assertIn("missing_document_fields", types)

        self.conn.execute(
            "UPDATE goods_lines SET compliance_status = 'required' WHERE id = ?",
            (self.goods_line_id,),
        )
        types = {item["type"] for item in reminders(self.conn, today=date(2026, 6, 29))}
        self.assertIn("compliance_not_approved", types)


if __name__ == "__main__":
    unittest.main()

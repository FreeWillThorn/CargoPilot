import unittest

from cargopilot.finance import LINE_COST, add_finance_line
from cargopilot.foundation import ROLE_ADMIN, ROLE_WAREHOUSE, connect, create_user, initialize_database
from cargopilot.master_data import create_supplier
from cargopilot.orders import create_goods_line, create_import_order
from cargopilot.receiving import (
    add_domestic_tracking_number,
    record_receiving,
    resolve_arrival_exception,
    search_receiving,
)


class ReceivingTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)
        self.admin_id = create_user(
            self.conn,
            email="admin@example.com",
            name="Admin",
            role=ROLE_ADMIN,
            password="secret",
        )
        self.warehouse_user_id = create_user(
            self.conn,
            email="warehouse@example.com",
            name="Warehouse",
            role=ROLE_WAREHOUSE,
            password="secret",
        )
        self.order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN, order_no="CP-2026-0001")
        self.supplier_id, _ = create_supplier(self.conn, actor_role=ROLE_ADMIN, name="Supplier")
        self.goods_line_id = create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            supplier_id=self.supplier_id,
            cn_name="杯子",
            customs_en_name="Ceramic Cup",
            shipping_mark="CP-MARK",
        )

    def tearDown(self):
        self.conn.close()

    def test_search_by_order_tracking_or_shipping_mark(self):
        add_domestic_tracking_number(
            self.conn,
            actor_role=ROLE_WAREHOUSE,
            goods_line_id=self.goods_line_id,
            tracking_no="YT123",
        )

        self.assertEqual(search_receiving(self.conn, actor_role=ROLE_WAREHOUSE, query="CP-2026")[0]["goods_line_id"], self.goods_line_id)
        self.assertEqual(search_receiving(self.conn, actor_role=ROLE_WAREHOUSE, query="YT123")[0]["goods_line_id"], self.goods_line_id)
        self.assertEqual(search_receiving(self.conn, actor_role=ROLE_WAREHOUSE, query="CP-MARK")[0]["goods_line_id"], self.goods_line_id)

    def test_partial_receiving_and_photo_metadata(self):
        first = record_receiving(
            self.conn,
            actor_role=ROLE_WAREHOUSE,
            actor_user_id=self.warehouse_user_id,
            goods_line_id=self.goods_line_id,
            domestic_tracking_no="YT1",
            received_carton_count=3,
            package_condition="ok",
            receiving_photo_path="uploads/receive-1.jpg",
        )
        record_receiving(
            self.conn,
            actor_role=ROLE_WAREHOUSE,
            actor_user_id=self.warehouse_user_id,
            goods_line_id=self.goods_line_id,
            domestic_tracking_no="YT2",
            received_carton_count=2,
            package_condition="ok",
        )

        count = self.conn.execute(
            "SELECT count(*) AS count FROM receiving_records WHERE goods_line_id = ?",
            (self.goods_line_id,),
        ).fetchone()["count"]
        photo = self.conn.execute(
            "SELECT * FROM files WHERE owner_type = 'receiving_record' AND owner_id = ?",
            (first,),
        ).fetchone()
        self.assertEqual(count, 2)
        self.assertEqual(photo["storage_path"], "uploads/receive-1.jpg")

    def test_exception_and_resolution(self):
        record_receiving(
            self.conn,
            actor_role=ROLE_WAREHOUSE,
            actor_user_id=self.warehouse_user_id,
            goods_line_id=self.goods_line_id,
            received_carton_count=1,
            arrival_exception_type="damaged_cartons",
        )
        row = self.conn.execute("SELECT logistics_status FROM goods_lines WHERE id = ?", (self.goods_line_id,)).fetchone()
        self.assertEqual(row["logistics_status"], "exception")

        resolve_arrival_exception(
            self.conn,
            actor_role=ROLE_WAREHOUSE,
            goods_line_id=self.goods_line_id,
            resolved_status="checked",
        )
        row = self.conn.execute("SELECT logistics_status FROM goods_lines WHERE id = ?", (self.goods_line_id,)).fetchone()
        self.assertEqual(row["logistics_status"], "checked")

    def test_warehouse_permission_limits(self):
        with self.assertRaises(PermissionError):
            add_finance_line(
                self.conn,
                actor_role=ROLE_WAREHOUSE,
                import_order_id=self.order_id,
                line_kind=LINE_COST,
                line_type="purchase",
                amount=1,
                currency="CNY",
            )


if __name__ == "__main__":
    unittest.main()

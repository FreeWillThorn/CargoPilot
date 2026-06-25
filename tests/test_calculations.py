import unittest

from cargopilot.calculations import (
    STAGE_CONTAINER_ESTIMATE,
    STAGE_FINAL_DOCUMENTS,
    STAGE_LOADING_COMPLETE,
    STAGE_PURCHASING,
    STAGE_RECEIVING,
    apply_package_calculations,
    calculate_cbm,
    calculate_gross_weight,
    check_goods_line_stage,
)
from cargopilot.foundation import ROLE_ADMIN, connect, initialize_database
from cargopilot.master_data import create_consignee, create_supplier
from cargopilot.orders import create_goods_line, create_import_order


class CalculationsTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)
        self.supplier_id, _ = create_supplier(self.conn, actor_role=ROLE_ADMIN, name="Supplier")
        self.consignee_id = create_consignee(
            self.conn,
            actor_role=ROLE_ADMIN,
            company_name="Euro Import",
            address="Berlin",
        )
        self.order_id = create_import_order(
            self.conn,
            actor_role=ROLE_ADMIN,
            consignee_id=self.consignee_id,
        )

    def tearDown(self):
        self.conn.close()

    def test_cbm_and_gross_weight_calculation_and_override(self):
        goods_line_id = create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            carton_count=10,
            carton_length_cm=40,
            carton_width_cm=30,
            carton_height_cm=20,
            carton_gross_weight_kg=8,
        )
        row = self.conn.execute("SELECT * FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        self.assertEqual(calculate_cbm(row), 0.24)
        self.assertEqual(calculate_gross_weight(row), 80)

        self.conn.execute("UPDATE goods_lines SET volume_cbm = 0.5, gross_weight = 90 WHERE id = ?", (goods_line_id,))
        row = self.conn.execute("SELECT * FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        self.assertEqual(calculate_cbm(row), 0.5)
        self.assertEqual(calculate_gross_weight(row), 90)

    def test_apply_package_calculations_does_not_overwrite_manual_values(self):
        goods_line_id = create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            carton_count=2,
            carton_length_cm=100,
            carton_width_cm=50,
            carton_height_cm=50,
            carton_gross_weight_kg=10,
            gross_weight=99,
        )

        apply_package_calculations(self.conn, goods_line_id)
        row = self.conn.execute("SELECT gross_weight, volume_cbm FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        self.assertEqual(row["gross_weight"], 99)
        self.assertEqual(row["volume_cbm"], 0.5)

    def test_stage_blockers(self):
        goods_line_id = create_goods_line(self.conn, actor_role=ROLE_ADMIN, import_order_id=self.order_id)
        purchasing = check_goods_line_stage(self.conn, goods_line_id=goods_line_id, stage=STAGE_PURCHASING)
        self.assertTrue(purchasing.blocked)
        self.assertIn("supplier_id", purchasing.blockers)

        self.conn.execute(
            """
            UPDATE goods_lines
            SET supplier_id = ?, cn_name = '杯子', quantity = 100, target_markup = 0.2,
                carton_count = 10, units_per_carton = 10,
                carton_length_cm = 40, carton_width_cm = 30, carton_height_cm = 20,
                carton_gross_weight_kg = 8, shipping_mark = 'CP-1',
                customs_en_name = 'Ceramic Cup', hs_code = '691200',
                sales_unit_price = 2, sales_currency = 'EUR'
            WHERE id = ?
            """,
            (self.supplier_id, goods_line_id),
        )
        self.conn.execute(
            "INSERT INTO domestic_tracking_numbers (goods_line_id, tracking_no, created_at) VALUES (?, 'YT1', datetime('now'))",
            (goods_line_id,),
        )

        self.assertFalse(check_goods_line_stage(self.conn, goods_line_id=goods_line_id, stage=STAGE_PURCHASING).blocked)
        self.assertFalse(check_goods_line_stage(self.conn, goods_line_id=goods_line_id, stage=STAGE_CONTAINER_ESTIMATE).blocked)

        receiving = check_goods_line_stage(
            self.conn,
            goods_line_id=goods_line_id,
            stage=STAGE_RECEIVING,
            context={"received_carton_count": 10},
        )
        self.assertFalse(receiving.blocked)
        self.assertEqual(receiving.warnings, ["receiving_photo"])

        final_docs = check_goods_line_stage(self.conn, goods_line_id=goods_line_id, stage=STAGE_FINAL_DOCUMENTS)
        self.assertFalse(final_docs.blocked)

        loading = check_goods_line_stage(
            self.conn,
            goods_line_id=goods_line_id,
            stage=STAGE_LOADING_COMPLETE,
            context={"container_type": "40HQ", "container_number": "MSKU1", "seal_number": "S1"},
        )
        self.assertTrue(loading.blocked)
        self.assertIn("loading_date", loading.blockers)
        self.assertEqual(loading.warnings, ["loading_photo"])


if __name__ == "__main__":
    unittest.main()

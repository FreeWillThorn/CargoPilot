import unittest

from cargopilot.finance import (
    LINE_CHARGE,
    LINE_COST,
    add_finance_line,
    calculate_profit,
    calculate_sales_price,
    update_goods_line_quote,
)
from cargopilot.foundation import ROLE_ADMIN, ROLE_WAREHOUSE, connect, initialize_database
from cargopilot.orders import create_goods_line, create_import_order


class FinanceTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)
        self.order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN)
        self.goods_line_id = create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            cn_name="杯子",
        )

    def tearDown(self):
        self.conn.close()

    def test_markup_margin_and_manual_quote(self):
        self.assertEqual(calculate_sales_price(100, target_markup=0.2), 120)
        self.assertEqual(calculate_sales_price(100, target_margin=0.2), 125)
        self.assertEqual(
            calculate_sales_price(100, target_markup=0.5, manual_sales_unit_price=130),
            130,
        )

    def test_update_goods_line_quote(self):
        sales_price = update_goods_line_quote(
            self.conn,
            actor_role=ROLE_ADMIN,
            goods_line_id=self.goods_line_id,
            purchase_unit_price=10,
            purchase_currency="CNY",
            sales_currency="EUR",
            target_markup=0.3,
        )
        self.assertEqual(sales_price, 13)

        row = self.conn.execute(
            "SELECT purchase_unit_price, target_markup, sales_unit_price FROM goods_lines WHERE id = ?",
            (self.goods_line_id,),
        ).fetchone()
        self.assertEqual(row["purchase_unit_price"], 10)
        self.assertEqual(row["target_markup"], 0.3)
        self.assertEqual(row["sales_unit_price"], 13)

    def test_cost_charge_and_profit_totals(self):
        add_finance_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            goods_line_id=self.goods_line_id,
            line_kind=LINE_COST,
            line_type="purchase",
            amount=1000,
            currency="CNY",
            exchange_rate_to_base=0.13,
        )
        add_finance_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            line_kind=LINE_COST,
            line_type="sea_freight",
            amount=200,
            currency="EUR",
        )
        add_finance_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            line_kind=LINE_CHARGE,
            line_type="product_sales",
            amount=500,
            currency="EUR",
        )
        add_finance_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            line_kind=LINE_CHARGE,
            line_type="adjustment",
            amount=-20,
            currency="EUR",
        )

        self.assertEqual(
            calculate_profit(self.conn, import_order_id=self.order_id, base_currency="EUR"),
            {
                "base_currency": "EUR",
                "total_cost": 330,
                "total_charge": 480,
                "profit": 150,
            },
        )

    def test_finance_is_admin_only(self):
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

import json
import unittest

from cargopilot.foundation import ROLE_ADMIN, ROLE_WAREHOUSE, connect, initialize_database
from cargopilot.master_data import (
    WAREHOUSE_PORT,
    WAREHOUSE_RECEIVING,
    create_consignee,
    create_supplier,
    create_warehouse,
    get_consignee_order_defaults,
    list_suppliers,
    list_warehouses,
    update_consignee,
    update_supplier,
    update_warehouse,
)


class MasterDataTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_supplier_crud_and_duplicate_warning(self):
        supplier_id, warnings = create_supplier(
            self.conn,
            actor_role=ROLE_ADMIN,
            name="Yiwu Cups",
            contact_name="Chen",
            phone="13800000000",
            email="sales@example.com",
            wechat="yiwu-cups",
            address="Yiwu",
            business_id="BUS-1",
            store_url="https://shop.1688.com",
            usual_categories=["ceramic"],
            notes="primary supplier",
        )
        self.assertEqual(warnings, [])

        _, duplicate_warnings = create_supplier(
            self.conn,
            actor_role=ROLE_ADMIN,
            name="Yiwu Cups",
        )
        self.assertEqual(duplicate_warnings, ["Supplier name already exists: Yiwu Cups"])

        update_warnings = update_supplier(
            self.conn,
            actor_role=ROLE_ADMIN,
            supplier_id=supplier_id,
            usual_categories=["ceramic", "glass"],
        )
        self.assertEqual(update_warnings, [])

        supplier = list_suppliers(self.conn)[0]
        self.assertEqual(json.loads(supplier["usual_categories"]), ["ceramic", "glass"])

    def test_master_data_is_admin_only(self):
        with self.assertRaises(PermissionError):
            create_supplier(self.conn, actor_role=ROLE_WAREHOUSE, name="Blocked")

    def test_consignee_crud_and_order_defaults(self):
        consignee_id = create_consignee(
            self.conn,
            actor_role=ROLE_ADMIN,
            company_name="Euro Import GmbH",
            contact_name="Anna",
            email="anna@example.eu",
            phone="+49 1",
            tax_id="DE123",
            address="Berlin",
            default_destination_port="Hamburg",
            default_trade_term="FOB",
            default_sales_currency="EUR",
            document_preferences="standard",
        )

        defaults = get_consignee_order_defaults(self.conn, consignee_id)
        self.assertEqual(
            defaults,
            {
                "destination_port": "Hamburg",
                "trade_term": "FOB",
                "sales_currency": "EUR",
            },
        )

        update_consignee(
            self.conn,
            actor_role=ROLE_ADMIN,
            consignee_id=consignee_id,
            default_destination_port="Rotterdam",
        )
        self.assertEqual(get_consignee_order_defaults(self.conn, consignee_id)["destination_port"], "Rotterdam")

    def test_warehouse_crud_and_types(self):
        receiving_id = create_warehouse(
            self.conn,
            actor_role=ROLE_ADMIN,
            type=WAREHOUSE_RECEIVING,
            name="Ningbo Receiving",
        )
        create_warehouse(
            self.conn,
            actor_role=ROLE_ADMIN,
            type=WAREHOUSE_PORT,
            name="Ningbo Port",
        )

        update_warehouse(
            self.conn,
            actor_role=ROLE_ADMIN,
            warehouse_id=receiving_id,
            phone="0574",
        )

        receiving = list_warehouses(self.conn, WAREHOUSE_RECEIVING)
        self.assertEqual(len(receiving), 1)
        self.assertEqual(receiving[0]["phone"], "0574")

        with self.assertRaises(ValueError):
            create_warehouse(self.conn, actor_role=ROLE_ADMIN, type="unknown", name="Bad")


if __name__ == "__main__":
    unittest.main()

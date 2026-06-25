import tempfile
import unittest
from pathlib import Path

from cargopilot.documents import (
    DOC_COMMERCIAL_INVOICE,
    DOC_PACKING_LIST,
    DocumentBlockedError,
    build_document_data,
    generate_export_document,
)
from cargopilot.foundation import ROLE_ADMIN, connect, initialize_database, set_setting
from cargopilot.master_data import create_consignee
from cargopilot.orders import create_goods_line, create_import_order
from cargopilot.spreadsheet_io import read_xlsx_rows


class DocumentsTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)
        set_setting(
            self.conn,
            "seller",
            {
                "company_name": "CargoPilot Ltd",
                "address": "Ningbo",
                "phone": "",
                "email": "",
                "tax_or_business_id": "",
                "bank_info": "",
            },
        )
        self.consignee_id = create_consignee(
            self.conn,
            actor_role=ROLE_ADMIN,
            company_name="Euro Import",
            address="Berlin",
        )
        self.order_id = create_import_order(
            self.conn,
            actor_role=ROLE_ADMIN,
            order_no="CP-2026-0001",
            consignee_id=self.consignee_id,
            trade_term="FOB",
            origin_port="Ningbo",
            destination_port="Hamburg",
        )

    def tearDown(self):
        self.conn.close()

    def add_complete_goods_line(self):
        return create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            customs_en_name="Ceramic Cup",
            hs_code="691200",
            quantity=100,
            unit="pcs",
            carton_count=10,
            carton_length_cm=40,
            carton_width_cm=30,
            carton_height_cm=20,
            carton_gross_weight_kg=8,
            sales_unit_price=2,
            sales_currency="EUR",
            shipping_mark="CP-MARK",
        )

    def test_final_generation_blocks_missing_fields_but_draft_can_generate(self):
        create_goods_line(self.conn, actor_role=ROLE_ADMIN, import_order_id=self.order_id)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(DocumentBlockedError) as error:
                generate_export_document(
                    self.conn,
                    actor_role=ROLE_ADMIN,
                    import_order_id=self.order_id,
                    document_type=DOC_COMMERCIAL_INVOICE,
                    output_dir=tmp,
                    final=True,
                )
            self.assertTrue(error.exception.blockers)

            draft = generate_export_document(
                self.conn,
                actor_role=ROLE_ADMIN,
                import_order_id=self.order_id,
                document_type=DOC_COMMERCIAL_INVOICE,
                output_dir=tmp,
                final=False,
            )
            self.assertEqual(draft["status"], "draft")
            self.assertTrue(Path(draft["xlsx_path"]).exists())
            self.assertTrue(Path(draft["pdf_path"]).exists())

    def test_invoice_data_totals_and_versioned_outputs(self):
        self.add_complete_goods_line()

        with tempfile.TemporaryDirectory() as tmp:
            first = generate_export_document(
                self.conn,
                actor_role=ROLE_ADMIN,
                import_order_id=self.order_id,
                document_type=DOC_COMMERCIAL_INVOICE,
                output_dir=tmp,
            )
            second = generate_export_document(
                self.conn,
                actor_role=ROLE_ADMIN,
                import_order_id=self.order_id,
                document_type=DOC_COMMERCIAL_INVOICE,
                output_dir=tmp,
            )

            self.assertEqual(first["document_number"], "CP-2026-0001-INV-V1")
            self.assertEqual(second["document_number"], "CP-2026-0001-INV-V2")
            self.assertEqual(Path(first["pdf_path"]).read_bytes()[:5], b"%PDF-")
            rows = read_xlsx_rows(first["xlsx_path"])
            self.assertIn("Ceramic Cup", [cell for row in rows for cell in row])

        data = build_document_data(
            self.conn,
            import_order_id=self.order_id,
            document_type=DOC_COMMERCIAL_INVOICE,
            version=3,
        )
        self.assertEqual(data["totals"]["line_amount"], 200)

    def test_packing_list_totals(self):
        self.add_complete_goods_line()
        data = build_document_data(
            self.conn,
            import_order_id=self.order_id,
            document_type=DOC_PACKING_LIST,
            version=1,
        )
        self.assertEqual(data["document_number"], "CP-2026-0001-PL-V1")
        self.assertEqual(data["totals"]["carton_count"], 10)
        self.assertEqual(data["totals"]["gross_weight"], 80)
        self.assertEqual(data["totals"]["cbm"], 0.24)


if __name__ == "__main__":
    unittest.main()

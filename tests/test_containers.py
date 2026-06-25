import tempfile
import unittest
from pathlib import Path

from cargopilot.containers import (
    create_container,
    export_loading_list,
    loading_list,
    recommend_container,
    record_loading,
)
from cargopilot.foundation import ROLE_ADMIN, connect, create_user, initialize_database
from cargopilot.orders import create_goods_line, create_import_order
from cargopilot.spreadsheet_io import read_xlsx_rows


class ContainersTest(unittest.TestCase):
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
        self.order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN)
        self.goods_line_id = create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            customs_en_name="Ceramic Cup",
            carton_count=100,
            carton_length_cm=40,
            carton_width_cm=30,
            carton_height_cm=20,
            carton_gross_weight_kg=8,
        )

    def tearDown(self):
        self.conn.close()

    def test_container_recommendation(self):
        recommendation = recommend_container(self.conn, self.order_id)
        self.assertEqual(recommendation["total_cbm"], 2.4)
        self.assertEqual(recommendation["total_gross_weight"], 800)
        self.assertEqual(recommendation["recommended_type"], "20GP")

    def test_multiple_containers_and_split_goods_line(self):
        first = create_container(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            container_type="20GP",
            container_number="MSKU1",
            seal_number="S1",
            loading_date="2026-07-01",
        )
        second = create_container(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            container_type="20GP",
            container_number="MSKU2",
            seal_number="S2",
            loading_date="2026-07-01",
        )

        record_loading(
            self.conn,
            actor_role=ROLE_ADMIN,
            actor_user_id=self.admin_id,
            container_id=first,
            goods_line_id=self.goods_line_id,
            loaded_carton_count=60,
            loading_photo_path="uploads/load.jpg",
        )
        record_loading(
            self.conn,
            actor_role=ROLE_ADMIN,
            actor_user_id=self.admin_id,
            container_id=second,
            goods_line_id=self.goods_line_id,
            loaded_carton_count=40,
        )

        rows = loading_list(self.conn, self.order_id)
        self.assertEqual([row["loaded_carton_count"] for row in rows], [60, 40])
        self.assertEqual(sum(row["cbm"] for row in rows), 2.4)
        self.assertEqual(sum(row["gross_weight"] for row in rows), 800)
        photo = self.conn.execute("SELECT * FROM files WHERE file_category = 'loading_photo'").fetchone()
        self.assertEqual(photo["storage_path"], "uploads/load.jpg")

    def test_container_rejects_goods_line_from_other_order(self):
        other_order_id = create_import_order(self.conn, actor_role=ROLE_ADMIN)
        other_goods_line_id = create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=other_order_id,
        )
        container_id = create_container(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            container_type="20GP",
            container_number="MSKU1",
            seal_number="S1",
            loading_date="2026-07-01",
        )

        with self.assertRaises(ValueError):
            record_loading(
                self.conn,
                actor_role=ROLE_ADMIN,
                actor_user_id=self.admin_id,
                container_id=container_id,
                goods_line_id=other_goods_line_id,
                loaded_carton_count=1,
            )

    def test_export_loading_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            container_id = create_container(
                self.conn,
                actor_role=ROLE_ADMIN,
                import_order_id=self.order_id,
                container_type="20GP",
                container_number="MSKU1",
                seal_number="S1",
                loading_date="2026-07-01",
            )
            record_loading(
                self.conn,
                actor_role=ROLE_ADMIN,
                actor_user_id=self.admin_id,
                container_id=container_id,
                goods_line_id=self.goods_line_id,
                loaded_carton_count=100,
            )
            path = Path(tmp) / "loading.xlsx"
            export_loading_list(self.conn, self.order_id, path)
            rows = read_xlsx_rows(path)
            self.assertIn("container_number", rows[0])
            self.assertIn("MSKU1", rows[1])


if __name__ == "__main__":
    unittest.main()

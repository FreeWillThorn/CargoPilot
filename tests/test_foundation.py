import json
import unittest

from cargopilot.foundation import (
    ROLE_ADMIN,
    ROLE_WAREHOUSE,
    authenticate,
    can,
    connect,
    create_user,
    get_setting,
    initialize_database,
    record_audit_log,
    record_file_metadata,
    set_setting,
)


class FoundationTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_role_permissions(self):
        self.assertTrue(can(ROLE_ADMIN, "finance:view"))
        self.assertTrue(can(ROLE_WAREHOUSE, "import_orders:view"))
        self.assertTrue(can(ROLE_WAREHOUSE, "goods_lines:update_receiving"))
        self.assertFalse(can(ROLE_WAREHOUSE, "finance:view"))
        self.assertFalse(can("unknown", "import_orders:view"))

    def test_user_authentication(self):
        create_user(
            self.conn,
            email="admin@example.com",
            name="Admin",
            role=ROLE_ADMIN,
            password="correct horse battery staple",
        )

        user = authenticate(self.conn, "admin@example.com", "correct horse battery staple")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], ROLE_ADMIN)
        self.assertIsNone(authenticate(self.conn, "admin@example.com", "wrong"))

    def test_file_metadata_stores_path_not_bytes(self):
        user_id = create_user(
            self.conn,
            email="warehouse@example.com",
            name="Warehouse",
            role=ROLE_WAREHOUSE,
            password="secret",
        )

        file_id = record_file_metadata(
            self.conn,
            owner_type="goods_line",
            owner_id=42,
            file_category="receiving_photo",
            file_name="arrival.jpg",
            file_type="image/jpeg",
            storage_path="uploads/arrival.jpg",
            uploaded_by_user_id=user_id,
        )

        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(files)").fetchall()
        }
        self.assertIn("storage_path", columns)
        self.assertNotIn("file_bytes", columns)

        row = self.conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        self.assertEqual(row["storage_path"], "uploads/arrival.jpg")

    def test_audit_log_records_change(self):
        user_id = create_user(
            self.conn,
            email="admin@example.com",
            name="Admin",
            role=ROLE_ADMIN,
            password="secret",
        )

        log_id = record_audit_log(
            self.conn,
            actor_user_id=user_id,
            target_type="goods_line",
            target_id=7,
            field_name="carton_count",
            old_value=10,
            new_value=12,
        )

        row = self.conn.execute("SELECT * FROM audit_logs WHERE id = ?", (log_id,)).fetchone()
        self.assertEqual(row["actor_user_id"], user_id)
        self.assertEqual(row["field_name"], "carton_count")
        self.assertEqual(json.loads(row["old_value"]), 10)
        self.assertEqual(json.loads(row["new_value"]), 12)

    def test_system_settings_defaults_and_update(self):
        self.assertEqual(get_setting(self.conn, "reminders")["lead_days"], 3)
        self.assertIn("40HQ", get_setting(self.conn, "containers"))

        set_setting(self.conn, "defaults", {"origin_country": "China", "origin_port": "Ningbo"})
        self.assertEqual(get_setting(self.conn, "defaults")["origin_port"], "Ningbo")

    def test_ai_intake_storage_tables_exist(self):
        tables = {
            row["name"]
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        self.assertIn("customs_goods_versions", tables)
        self.assertNotIn("assistant_supplier_message_drafts", tables)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from cargopilot.foundation import connect
from cargopilot.seed import seed_demo


class SeedTest(unittest.TestCase):
    def test_demo_seed_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "demo.sqlite3"
            first = seed_demo(db_path)
            second = seed_demo(db_path)

            conn = connect(db_path)
            try:
                orders = conn.execute("SELECT count(*) AS count FROM import_orders WHERE order_no = 'CP-DEMO-0001'").fetchone()
                goods = conn.execute("SELECT count(*) AS count FROM goods_lines WHERE import_order_id = ?", (first["order_id"],)).fetchone()
                documents = conn.execute("SELECT xlsx_path, pdf_path FROM documents ORDER BY id").fetchall()
            finally:
                conn.close()

            self.assertEqual(first, second)
            self.assertEqual(orders["count"], 1)
            self.assertEqual(goods["count"], 2)
            self.assertTrue(documents)
            self.assertTrue(Path(documents[0]["xlsx_path"]).exists())
            self.assertTrue(Path(documents[0]["pdf_path"]).exists())


if __name__ == "__main__":
    unittest.main()

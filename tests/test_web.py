from http import HTTPStatus
from http.cookies import SimpleCookie
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cargopilot.foundation import ROLE_ADMIN, ROLE_WAREHOUSE, connect, create_user, initialize_database
from cargopilot.master_data import create_consignee
from cargopilot.orders import create_goods_line, create_import_order
from cargopilot.spreadsheet_io import export_rows_xlsx
from cargopilot.web import CargoPilotHandler, SESSIONS


class DummyRequest(CargoPilotHandler):
    def __init__(self):
        pass


class WebShellTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "app.sqlite3"
        conn = connect(self.db_path)
        initialize_database(conn)
        self.admin_id = create_user(conn, email="admin@example.com", name="Admin", role=ROLE_ADMIN, password="admin")
        self.warehouse_id = create_user(conn, email="warehouse@example.com", name="Warehouse", role=ROLE_WAREHOUSE, password="warehouse")
        consignee_id = create_consignee(conn, actor_role=ROLE_ADMIN, company_name="Euro Import", address="Berlin")
        self.order_id = create_import_order(
            conn,
            actor_role=ROLE_ADMIN,
            order_no="CP-2026-0001",
            consignee_id=consignee_id,
            destination_port="Hamburg",
            order_status="purchasing",
            sales_currency="EUR",
        )
        self.goods_line_id = create_goods_line(
            conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            sku_or_model="CUP-A1",
            cn_name="杯子",
            customs_en_name="Ceramic Cup",
            shipping_mark="CP-MARK",
            quantity=100,
            unit="pcs",
            purchase_unit_price=10,
            purchase_currency="CNY",
            sales_currency="EUR",
        )
        conn.close()
        SESSIONS.clear()
        self.db_patch = patch("cargopilot.web.APP_DB", self.db_path)
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        SESSIONS.clear()
        self.tmp.cleanup()

    def test_root_redirects_without_session(self):
        response = self.request("GET", "/")
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], "/login")

    def test_login_sets_session_cookie(self):
        response = self.request("POST", "/login", body="email=admin%40example.com&password=admin")
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], "/dashboard")
        self.assertIn("session=", response["headers"]["Set-Cookie"])

    def test_admin_dashboard_navigation_and_cards(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        response = self.request("GET", "/dashboard", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertIn("Documents", response["body"])
        self.assertIn("Settings", response["body"])
        self.assertIn("CP-2026-0001", response["body"])
        self.assertIn("Hamburg", response["body"])
        self.assertIn("supplier_side", response["body"])
        self.assertIn(f"/tracking?import_order_id={self.order_id}&missing_fields=1", response["body"])

    def test_warehouse_navigation_is_restricted(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        response = self.request("GET", "/dashboard", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertIn("Warehouse Receiving", response["body"])
        self.assertNotIn("Excel &amp; Finance", response["body"])
        self.assertNotIn("Suppliers", response["body"])
        self.assertNotIn("Consignees", response["body"])
        self.assertNotIn("Documents", response["body"])
        self.assertNotIn("Settings", response["body"])

    def test_admin_can_manage_master_data(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        response = self.request(
            "POST",
            "/suppliers",
            body="name=Yiwu+Cups&contact_name=Chen&phone=138&email=sales%40example.com&store_url=https%3A%2F%2F1688.example",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", "/suppliers", cookie=f"session={token}")["body"]
        self.assertIn("Yiwu Cups", page)
        self.assertIn("https://1688.example", page)

        self.request(
            "POST",
            "/consignees",
            body="company_name=Nordic+Import&email=a%40b.eu&default_destination_port=Hamburg&default_sales_currency=EUR",
            cookie=f"session={token}",
        )
        self.assertIn("Nordic Import", self.request("GET", "/consignees", cookie=f"session={token}")["body"])

        self.request(
            "POST",
            "/warehouses",
            body="type=receiving&name=Ningbo+Receiving&phone=0574",
            cookie=f"session={token}",
        )
        self.assertIn("Ningbo Receiving", self.request("GET", "/warehouses", cookie=f"session={token}")["body"])

    def test_warehouse_user_cannot_access_master_data(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        response = self.request("GET", "/suppliers", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)
        response = self.request("POST", "/suppliers", body="name=Blocked", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)

    def test_admin_can_update_settings(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        response = self.request(
            "POST",
            "/settings",
            body="seller_company_name=CargoPilot+Ltd&seller_address=Ningbo&origin_country=China&origin_port=Ningbo&purchase_currency=CNY&sales_currency=EUR&lead_days=5",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", "/settings", cookie=f"session={token}")["body"]
        self.assertIn("CargoPilot Ltd", page)
        self.assertIn("Ningbo", page)

    def test_admin_can_create_order_and_goods_line(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        response = self.request(
            "POST",
            "/orders",
            body="order_no=CP-2026-0002&destination_port=Rotterdam&trade_term=FOB&expected_loading_date=2026-07-01",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        order_path = response["headers"]["Location"]
        order_page = self.request("GET", order_path, cookie=f"session={token}")["body"]
        self.assertIn("CP-2026-0002", order_page)
        self.assertIn("goods_lines", order_page)

        response = self.request(
            "POST",
            f"{order_path}/goods-lines",
            body="cn_name=%E6%9D%AF%E5%AD%90&customs_en_name=Ceramic+Cup&quantity=100&unit=pcs&sku_or_model=A1",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        edit_path = response["headers"]["Location"]
        edit_page = self.request("GET", edit_path, cookie=f"session={token}")["body"]
        self.assertIn("Ceramic Cup", edit_page)

        self.request(
            "POST",
            edit_path,
            body="cn_name=%E6%9D%AF%E5%AD%90&customs_en_name=Ceramic+Mug&quantity=100&unit=pcs&sku_or_model=A1",
            cookie=f"session={token}",
        )
        self.assertIn("Ceramic Mug", self.request("GET", edit_path, cookie=f"session={token}")["body"])

    def test_warehouse_user_can_view_orders_but_not_create(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        response = self.request("GET", "/orders", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertNotIn("新增订单", response["body"])

        response = self.request("POST", "/orders", body="order_no=BLOCKED", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)

    def test_dashboard_filters_tracking_and_search_urls(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        page = self.request("GET", "/dashboard?status=purchasing", cookie=f"session={token}")["body"]
        self.assertIn("CP-2026-0001", page)
        page = self.request("GET", "/dashboard?status=loaded", cookie=f"session={token}")["body"]
        self.assertIn("<strong>0</strong><span>活跃订单</span>", page)
        self.assertIn("暂无订单", page)

        tracking = self.request("GET", "/tracking?status=not_ordered", cookie=f"session={token}")["body"]
        self.assertIn("Ceramic Cup", tracking)
        self.assertIn("CP-MARK", tracking)

        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE goods_lines SET logistics_status = 'exception' WHERE id = ?", (self.goods_line_id,))
            conn.commit()
        finally:
            conn.close()
        exception_page = self.request("GET", f"/tracking?import_order_id={self.order_id}&exception_only=1", cookie=f"session={token}")["body"]
        self.assertIn("exception", exception_page)

        search = self.request("GET", "/search?q=CP-MARK", cookie=f"session={token}")["body"]
        self.assertIn("goods_line", search)
        self.assertIn(f"/goods-lines/{self.goods_line_id}/edit", search)

    def test_admin_can_use_excel_and_finance_screen(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        page = self.request("GET", "/excel-finance", cookie=f"session={token}")["body"]
        self.assertIn("Excel &amp; Finance", page)
        self.assertIn("CUP-A1", page)

        response = self.request(
            "POST",
            "/finance/quote",
            body=f"goods_line_id={self.goods_line_id}&purchase_unit_price=10&purchase_currency=CNY&target_markup=0.3&sales_currency=EUR",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", "/excel-finance", cookie=f"session={token}")["body"]
        self.assertIn('value="13.0"', page)

        self.request(
            "POST",
            "/finance/line",
            body=f"import_order_id={self.order_id}&goods_line_id={self.goods_line_id}&line_kind=cost&cost_type=purchase&charge_type=product_sales&amount=100&currency=EUR&exchange_rate_to_base=1&notes=buy",
            cookie=f"session={token}",
        )
        self.request(
            "POST",
            "/finance/line",
            body=f"import_order_id={self.order_id}&line_kind=charge&cost_type=purchase&charge_type=product_sales&amount=160&currency=EUR&exchange_rate_to_base=1&notes=sell",
            cookie=f"session={token}",
        )
        page = self.request("GET", "/excel-finance", cookie=f"session={token}")["body"]
        self.assertIn("60.00", page)
        self.assertIn("product_sales", page)

    def test_excel_import_errors_and_export_download(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        bad_file = Path(self.tmp.name) / "bad.xlsx"
        export_rows_xlsx(bad_file, ["wrong"], [{"wrong": "value"}])

        page = self.request(
            "POST",
            "/excel/customer-import",
            body=f"path={bad_file}",
            cookie=f"session={token}",
        )["body"]
        self.assertIn("Invalid headers", page)

        response = self.request("GET", "/exports/goods-lines.xlsx", cookie=f"session={token}", decode=False)
        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertEqual(response["body"][:2], b"PK")

    def test_warehouse_user_cannot_access_finance_screen(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        response = self.request("GET", "/excel-finance", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)
        response = self.request("POST", "/finance/line", body=f"import_order_id={self.order_id}", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)

    def test_admin_can_create_container_loading_and_export_list(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        page = self.request("GET", "/shipping-docs", cookie=f"session={token}")["body"]
        self.assertIn("Shipping &amp; Documents", page)

        response = self.request(
            "POST",
            "/containers",
            body=f"import_order_id={self.order_id}&container_type=20GP&container_number=MSKU1&seal_number=S1&loading_date=2026-07-01",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)

        conn = connect(self.db_path)
        try:
            container_id = conn.execute("SELECT id FROM containers WHERE container_number = 'MSKU1'").fetchone()["id"]
        finally:
            conn.close()
        photo = Path(self.tmp.name) / "loading.jpg"
        photo.write_bytes(b"photo")
        response = self.request(
            "POST",
            "/loading-records",
            body=f"container_id={container_id}&goods_line_id={self.goods_line_id}&loaded_carton_count=5&loading_photo_path={photo}",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", "/shipping-docs", cookie=f"session={token}")["body"]
        self.assertIn("MSKU1", page)
        self.assertIn("Ceramic Cup", page)

        download = self.request("GET", f"/exports/loading-list.xlsx?import_order_id={self.order_id}", cookie=f"session={token}", decode=False)
        self.assertEqual(download["status"], HTTPStatus.OK)
        self.assertEqual(download["body"][:2], b"PK")

    def test_document_generation_blockers_and_downloads(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        blocked = self.request(
            "POST",
            "/documents/generate",
            body=f"import_order_id={self.order_id}&document_type=commercial_invoice&status=final",
            cookie=f"session={token}",
        )
        self.assertEqual(blocked["status"], HTTPStatus.OK)
        self.assertIn("Export Document is blocked", blocked["body"])
        self.assertIn("hs_code", blocked["body"])

        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                UPDATE goods_lines
                SET hs_code = '691200', carton_count = 10, carton_length_cm = 40,
                    carton_width_cm = 30, carton_height_cm = 20, carton_gross_weight_kg = 8,
                    sales_unit_price = 2, sales_currency = 'EUR'
                WHERE id = ?
                """,
                (self.goods_line_id,),
            )
            conn.commit()
        finally:
            conn.close()

        generated = self.request(
            "POST",
            "/documents/generate",
            body=f"import_order_id={self.order_id}&document_type=commercial_invoice&status=final",
            cookie=f"session={token}",
        )
        self.assertIn("CP-2026-0001-INV-V1", generated["body"])

        conn = connect(self.db_path)
        try:
            document_id = conn.execute("SELECT id FROM documents WHERE document_type = 'commercial_invoice'").fetchone()["id"]
        finally:
            conn.close()
        xlsx = self.request("GET", f"/downloads/document/{document_id}/xlsx", cookie=f"session={token}", decode=False)
        pdf = self.request("GET", f"/downloads/document/{document_id}/pdf", cookie=f"session={token}", decode=False)
        self.assertEqual(xlsx["body"][:2], b"PK")
        self.assertEqual(pdf["body"][:5], b"%PDF-")

    def test_warehouse_user_cannot_access_shipping_docs(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        response = self.request("GET", "/shipping-docs", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)

    def test_warehouse_user_can_search_and_record_receiving(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        page = self.request("GET", "/receiving?q=CP-MARK", cookie=f"session={token}")["body"]
        self.assertIn("CP-MARK", page)
        self.assertIn("Ceramic Cup", page)

        photo = Path(self.tmp.name) / "receive.jpg"
        photo.write_bytes(b"photo")
        response = self.request(
            "POST",
            "/receiving/record",
            body=f"goods_line_id={self.goods_line_id}&query=CP-MARK&domestic_tracking_no=YT999&received_carton_count=4&package_condition=ok&receiving_photo_path={photo}",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], "/receiving?q=CP-MARK")

        conn = connect(self.db_path)
        try:
            goods = conn.execute("SELECT logistics_status FROM goods_lines WHERE id = ?", (self.goods_line_id,)).fetchone()
            receiving_count = conn.execute("SELECT count(*) AS count FROM receiving_records WHERE goods_line_id = ?", (self.goods_line_id,)).fetchone()
            file_row = conn.execute("SELECT storage_path FROM files WHERE file_category = 'receiving_photo'").fetchone()
        finally:
            conn.close()
        self.assertEqual(goods["logistics_status"], "received_at_warehouse")
        self.assertEqual(receiving_count["count"], 1)
        self.assertTrue(Path(file_row["storage_path"]).exists())

    def test_warehouse_user_can_record_and_resolve_exception(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        self.request(
            "POST",
            "/receiving/record",
            body=f"goods_line_id={self.goods_line_id}&query=CP-MARK&received_carton_count=1&arrival_exception_type=damaged_cartons",
            cookie=f"session={token}",
        )
        page = self.request("GET", "/receiving?q=CP-MARK", cookie=f"session={token}")["body"]
        self.assertIn("exception", page)
        self.assertIn("解除异常", page)

        self.request(
            "POST",
            "/receiving/resolve",
            body=f"goods_line_id={self.goods_line_id}&query=CP-MARK",
            cookie=f"session={token}",
        )
        conn = connect(self.db_path)
        try:
            goods = conn.execute("SELECT logistics_status FROM goods_lines WHERE id = ?", (self.goods_line_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(goods["logistics_status"], "received_at_warehouse")

    def request(self, method, path, body="", cookie="", decode=True):
        handler = DummyRequest()
        sent = {"headers": {}}
        handler.path = path
        handler.headers = {"Content-Length": str(len(body)), "Cookie": cookie}
        handler.rfile = _Reader(body.encode())
        handler.wfile = _Writer(sent)
        handler.send_response = lambda status: sent.update(status=status)
        handler.send_header = lambda key, value: sent["headers"].__setitem__(key, value)
        handler.end_headers = lambda: None
        if method == "GET":
            handler.do_GET()
        else:
            handler.do_POST()
        sent["body"] = sent.get("body", b"").decode() if decode else sent.get("body", b"")
        return sent


class _Reader:
    def __init__(self, body):
        self.body = body

    def read(self, length):
        return self.body[:length]


class _Writer:
    def __init__(self, sent):
        self.sent = sent

    def write(self, body):
        self.sent["body"] = self.sent.get("body", b"") + body


if __name__ == "__main__":
    unittest.main()

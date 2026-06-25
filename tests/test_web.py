from http import HTTPStatus
from http.cookies import SimpleCookie
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cargopilot.foundation import ROLE_ADMIN, ROLE_WAREHOUSE, connect, create_user, initialize_database
from cargopilot.master_data import create_consignee
from cargopilot.orders import create_import_order
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
        create_import_order(
            conn,
            actor_role=ROLE_ADMIN,
            order_no="CP-2026-0001",
            consignee_id=consignee_id,
            destination_port="Hamburg",
            order_status="purchasing",
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

    def test_warehouse_navigation_is_restricted(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        response = self.request("GET", "/dashboard", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertIn("Warehouse Receiving", response["body"])
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

    def request(self, method, path, body="", cookie=""):
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
        sent["body"] = sent.get("body", b"").decode()
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

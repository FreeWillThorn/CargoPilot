from http import HTTPStatus
from http.cookies import SimpleCookie
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from cargopilot.foundation import ROLE_ADMIN, ROLE_WAREHOUSE, connect, create_user, initialize_database
from cargopilot.master_data import WAREHOUSE_RECEIVING, create_consignee, create_warehouse
from cargopilot.order_assistant import CHINESE_GOODS_HEADERS, REVIEW_APPROVED_FOR_DRAFT
from cargopilot.orders import create_goods_line, create_import_order
from cargopilot.spreadsheet_io import FINANCE_COST_UPLOAD_HEADERS, ORDER_GOODS_UPLOAD_HEADERS, export_rows_xlsx
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
        self.receiving_warehouse_id = create_warehouse(
            conn,
            actor_role=ROLE_ADMIN,
            type=WAREHOUSE_RECEIVING,
            name="Ningbo Receiving",
            contact_name="Li",
            phone="0574",
            address="Ningbo warehouse",
        )
        self.order_id = create_import_order(
            conn,
            actor_role=ROLE_ADMIN,
            order_no="CP-2026-0001",
            consignee_id=consignee_id,
            receiving_warehouse_id=self.receiving_warehouse_id,
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
        for label in ["Dashboard", "订单详情", "货物详情", "仓库盘点", "基础资料", "海运单证", "成本利润"]:
            self.assertIn(label, response["body"])
        nav_labels = ["Dashboard", "订单详情", "货物详情", "仓库盘点", "海运单证", "成本利润", "基础资料"]
        nav_positions = [response["body"].index(f">{label}</a>") for label in nav_labels]
        self.assertEqual(nav_positions, sorted(nav_positions))
        self.assertNotIn("订单项目", response["body"])
        for old_label in ["Goods Lines", "Excel &amp; Finance", "Shipping &amp; Documents"]:
            self.assertNotIn(old_label, response["body"])
        self.assertNotIn("管理/设置", response["body"])
        self.assertNotIn("系统设置", response["body"])
        self.assertNotIn("仓库资料", response["body"])
        self.assertIn("CP-2026-0001", response["body"])
        self.assertIn("Hamburg", response["body"])
        self.assertIn("采购中", response["body"])
        self.assertIn("供应商处", response["body"])
        self.assertIn("出口订单", response["body"])
        self.assertIn('select name="status" onchange="this.form.submit()"', response["body"])
        self.assertNotIn(">筛选</button>", response["body"])
        self.assertIn('href="/orders"', response["body"])
        self.assertIn(f"/shipping-docs?import_order_id={self.order_id}", response["body"])

        filtered = self.request("GET", "/dashboard?status=loaded", cookie=f"session={token}")["body"]
        self.assertIn("出口订单", filtered)
        self.assertIn("暂无订单", filtered)
        self.assertIn('select name="status" onchange="this.form.submit()"', filtered)

    def test_warehouse_navigation_is_restricted(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        response = self.request("GET", "/dashboard", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.OK)
        for label in ["Dashboard", "订单详情", "货物详情", "仓库盘点"]:
            self.assertIn(label, response["body"])
        self.assertNotIn("海运单证", response["body"])
        self.assertNotIn("成本利润", response["body"])
        self.assertNotIn("基础资料", response["body"])
        self.assertNotIn("管理/设置", response["body"])
        self.assertNotIn("Excel &amp; Finance", response["body"])
        self.assertNotIn("Suppliers", response["body"])
        self.assertNotIn("Consignees", response["body"])
        self.assertNotIn("Documents", response["body"])
        self.assertNotIn("Settings", response["body"])

    def test_navigation_active_state_follows_section(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        tracking = self.request("GET", "/tracking", cookie=f"session={token}")["body"]
        self.assertIn('<a href="/tracking" class="active">货物详情</a>', tracking)
        self.assertIn('<a href="/dashboard">Dashboard</a>', tracking)

        goods_edit = self.request("GET", f"/goods-lines/{self.goods_line_id}/edit", cookie=f"session={token}")["body"]
        self.assertIn('<a href="/tracking" class="active">货物详情</a>', goods_edit)

        basic_data = self.request("GET", "/basic-data", cookie=f"session={token}")["body"]
        self.assertIn('<a href="/basic-data" class="active">基础资料</a>', basic_data)

    def test_action_drawer_is_closeable_overlay(self):
        css = self.request("GET", "/static/app.css")["body"]
        self.assertIn(".action-drawer[open] { position:fixed;", css)
        self.assertIn('content:" 关闭"', css)
        self.assertIn(".app { height:100dvh;", css)
        self.assertIn(".tracking-scroll { max-height:calc(100dvh - 270px); min-height:300px; overflow:auto; }", css)
        self.assertIn(".tracking-scroll table { min-width:2320px; }", css)
        self.assertIn(".warehouse-scroll { max-height:440px; overflow:auto; }", css)
        self.assertIn(".warehouse-scroll table { min-width:1280px; }", css)
        self.assertIn(".master-data-scroll { max-height:380px; overflow:auto; }", css)
        self.assertIn(".master-data-scroll table { min-width:920px; }", css)
        page = self.request("GET", "/login")["body"]
        self.assertIn('event.key === "Escape"', page)
        self.assertIn("event.target === drawer", page)

    def test_admin_can_manage_master_data(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        response = self.request(
            "POST",
            "/basic-data/suppliers",
            body="name=Yiwu+Cups&contact_name=Chen&phone=138&email=sales%40example.com&store_url=https%3A%2F%2F1688.example",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", "/basic-data", cookie=f"session={token}")["body"]
        for label in ["基础资料", "供应商", "客户", "仓库", "大模型配置", "公司信息"]:
            self.assertIn(label, page)
        self.assertEqual(page.count("master-data-scroll"), 5)
        self.assertIn("Yiwu Cups", page)
        self.assertIn("https://1688.example", page)

        self.request(
            "POST",
            "/basic-data/consignees",
            body="company_name=Nordic+Import&email=a%40b.eu&default_destination_port=Hamburg&default_sales_currency=EUR",
            cookie=f"session={token}",
        )
        self.assertIn("Nordic Import", self.request("GET", "/basic-data", cookie=f"session={token}")["body"])

        self.request(
            "POST",
            "/basic-data/warehouses",
            body="type=receiving&name=Ningbo+Receiving&phone=0574",
            cookie=f"session={token}",
        )
        warehouses_page = self.request("GET", "/basic-data", cookie=f"session={token}")["body"]
        self.assertIn("Ningbo Receiving", warehouses_page)
        self.assertIn("<select name=\"type\">", warehouses_page)
        self.assertIn("收货仓库", warehouses_page)

        legacy = self.request("GET", "/suppliers", cookie=f"session={token}")
        self.assertEqual(legacy["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(legacy["headers"]["Location"], "/basic-data")

    def test_warehouse_user_cannot_access_master_data(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        response = self.request("GET", "/basic-data", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)
        response = self.request("POST", "/basic-data/suppliers", body="name=Blocked", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)
        response = self.request("POST", f"/orders/{self.order_id}/edit", body="order_no=Blocked", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)
        response = self.request("POST", f"/orders/{self.order_id}/cancel", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)
        response = self.request("POST", "/orders/consignees", body="company_name=Blocked", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)

    def test_admin_can_update_settings(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        response = self.request(
            "POST",
            "/basic-data/settings",
            body="seller_company_name=CargoPilot+Ltd&seller_address=Ningbo&seller_tax_or_business_id=TAX123&seller_bank_info=Bank&origin_country=China&origin_port=Ningbo&purchase_currency=CNY&sales_currency=EUR&lead_days=5",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", "/basic-data", cookie=f"session={token}")["body"]
        self.assertIn("CargoPilot Ltd", page)
        self.assertIn("Ningbo", page)
        self.assertIn("TAX123", page)
        self.assertIn("Bank", page)

    def test_admin_can_save_and_validate_llm_settings(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        payload = {
            "choices": [{"message": {"content": json.dumps({"ok": True})}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        with patch("cargopilot.order_assistant.request.urlopen", return_value=_MockDeepSeekResponse(payload)):
            response = self.request(
                "POST",
                "/basic-data/llm-settings",
                body="deepseek_api_key=sk-test&deepseek_model=deepseek-chat&deepseek_api_base=https%3A%2F%2Fapi.deepseek.com%2Fchat%2Fcompletions&deepseek_timeout_seconds=12&validate=1",
                cookie=f"session={token}",
            )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", "/basic-data", cookie=f"session={token}")["body"]
        self.assertIn("大模型配置", page)
        self.assertIn("已配置（本地设置）", page)
        self.assertIn("验证成功", page)
        self.assertIn("连接验证成功", page)

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
        self.assertTrue(order_path.startswith("/orders?order_id="))
        order_page = self.request("GET", order_path, cookie=f"session={token}")["body"]
        self.assertIn("CP-2026-0002", order_page)
        self.assertIn("订单详情", order_page)
        self.assertNotIn("货物明细", order_page)
        self.assertIn("当前订单", order_page)
        self.assertIn("scroll-panel", order_page)
        self.assertIn("收货客户", order_page)
        self.assertIn('aria-label="编辑订单"', order_page)
        self.assertIn('aria-label="取消订单"', order_page)
        order_id = order_path.rsplit("=", 1)[1]
        self.assertIn(f"<option value='{order_id}' selected>CP-2026-0002</option>", order_page)

        response = self.request(
            "POST",
            f"/orders/{order_id}/edit",
            body="order_no=CP-2026-0002A&destination_port=Antwerp&trade_term=CIF&expected_loading_date=2026-07-02&sales_currency=EUR",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        edited = self.request("GET", response["headers"]["Location"], cookie=f"session={token}")["body"]
        self.assertIn("CP-2026-0002A", edited)
        self.assertIn("Antwerp", edited)

        response = self.request("POST", f"/orders/{order_id}/cancel", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        cancelled = self.request("GET", response["headers"]["Location"], cookie=f"session={token}")["body"]
        self.assertIn("已取消", cancelled)

        response = self.request(
            "POST",
            f"/orders/{order_id}/goods-lines",
            body="cn_name=%E6%9D%AF%E5%AD%90&customs_en_name=Ceramic+Cup&quantity=100&unit=pcs&sku_or_model=A1",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], f"/orders?order_id={order_id}")
        conn = connect(self.db_path)
        try:
            created_goods = conn.execute("SELECT * FROM goods_lines WHERE import_order_id = ? AND customs_en_name = 'Ceramic Cup'", (order_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(created_goods)

        edit_path = f"/goods-lines/{int(self.goods_line_id)}/edit"
        self.request(
            "POST",
            edit_path,
            body="cn_name=%E6%9D%AF%E5%AD%90&customs_en_name=Ceramic+Mug&quantity=100&unit=pcs&sku_or_model=A1",
            cookie=f"session={token}",
        )
        edit_page = self.request("GET", edit_path, cookie=f"session={token}")["body"]
        self.assertIn("Ceramic Mug", edit_page)
        self.assertIn(f'href="/tracking?import_order_id={self.order_id}"', edit_page)
        self.assertIn('aria-label="返回货物详情"', edit_page)
        self.assertIn(f'action="/goods-lines/{int(self.goods_line_id)}/delete"', edit_page)

    def test_admin_can_manage_consignees_from_basic_data(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        order_page = self.request("GET", f"/orders?order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertNotIn('aria-label="新增收货客户"', order_page)
        self.assertNotIn('aria-label="编辑收货客户"', order_page)

        response = self.request(
            "POST",
            "/basic-data/consignees",
            body="company_name=Nordic+Import&contact_name=Anna&phone=123&email=a%40b.eu",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], "/basic-data#consignees")
        page = self.request("GET", "/basic-data", cookie=f"session={token}")["body"]
        self.assertIn("Nordic Import", page)
        self.assertIn('aria-label="编辑客户"', page)

        conn = connect(self.db_path)
        try:
            consignee_id = conn.execute("SELECT id FROM consignees WHERE company_name = 'Nordic Import'").fetchone()["id"]
        finally:
            conn.close()
        response = self.request(
            "POST",
            f"/basic-data/consignees/{consignee_id}/edit",
            body="company_name=Nordic+Import+Ltd&phone=456",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", "/basic-data", cookie=f"session={token}")["body"]
        self.assertIn("Nordic Import Ltd", page)

        response = self.request(
            "POST",
            f"/basic-data/consignees/{consignee_id}/delete",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        conn = connect(self.db_path)
        try:
            deleted = conn.execute("SELECT id FROM consignees WHERE id = ?", (consignee_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNone(deleted)

    def test_admin_can_upload_goods_lines_from_goods_details(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        upload = Path(self.tmp.name) / "goods-upload.xlsx"
        export_rows_xlsx(
            upload,
            ORDER_GOODS_UPLOAD_HEADERS,
            [
                {
                    "产品名称": "黑陶侧把茶具套装",
                    "数量（非包裹数）": 5,
                    "实际付款": 500,
                    "链接": "https://1688.example/tea",
                    "厂家名称": "宏门工厂",
                }
            ],
        )
        body, content_type = multipart_body(
            {"return_to": f"/tracking?import_order_id={self.order_id}"},
            {"file": ("goods-upload.xlsx", upload.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        response = self.request(
            "POST",
            f"/orders/{self.order_id}/goods-lines/import",
            body=body,
            content_type=content_type,
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertIn("已导入 1 个货物项", response["body"])
        self.assertIn("货物详情", response["body"])
        conn = connect(self.db_path)
        try:
            goods = conn.execute("SELECT * FROM goods_lines WHERE cn_name = '黑陶侧把茶具套装'").fetchone()
        finally:
            conn.close()
        self.assertEqual(goods["purchase_unit_price"], 100)

    def test_goods_line_upload_reports_invalid_rows(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        upload = Path(self.tmp.name) / "bad-goods-upload.xlsx"
        export_rows_xlsx(upload, ORDER_GOODS_UPLOAD_HEADERS, [{"产品名称": "", "数量（非包裹数）": "x"}])
        body, content_type = multipart_body(
            {"return_to": f"/tracking?import_order_id={self.order_id}"},
            {"file": ("bad-goods-upload.xlsx", upload.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        response = self.request(
            "POST",
            f"/orders/{self.order_id}/goods-lines/import",
            body=body,
            content_type=content_type,
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertIn("导入错误", response["body"])
        self.assertIn("产品名称不能为空", response["body"])

    def test_admin_can_delete_goods_line_from_edit_page(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        response = self.request(
            "POST",
            f"/goods-lines/{self.goods_line_id}/delete",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], f"/tracking?import_order_id={self.order_id}")
        conn = connect(self.db_path)
        try:
            row = conn.execute("SELECT id FROM goods_lines WHERE id = ?", (self.goods_line_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNone(row)

    def test_warehouse_user_cannot_delete_goods_line(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id

        response = self.request(
            "POST",
            f"/goods-lines/{self.goods_line_id}/delete",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)
        conn = connect(self.db_path)
        try:
            row = conn.execute("SELECT id FROM goods_lines WHERE id = ?", (self.goods_line_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)

    def test_admin_can_update_order_status_from_order_project(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        response = self.request(
            "POST",
            "/orders/status",
            body=f"order_id={self.order_id}&order_status=receiving",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", response["headers"]["Location"], cookie=f"session={token}")["body"]
        self.assertIn("收货中", page)
        self.assertIn('name="order_status"', page)
        self.assertNotIn("更新订单状态", page)

        conn = connect(self.db_path)
        try:
            audit = conn.execute(
                "SELECT * FROM audit_logs WHERE target_type = 'import_order' AND target_id = ? AND field_name = 'order_status'",
                (self.order_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(audit)

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
        self.assertIn('<a href="/orders"><article><strong>0</strong><span>活跃订单</span></article></a>', page)
        self.assertIn("暂无订单", page)

        tracking = self.request("GET", "/tracking?status=not_ordered", cookie=f"session={token}")["body"]
        self.assertIn("货物详情", tracking)
        self.assertIn("手动添加货物项", tracking)
        self.assertIn("上传 Excel 货物清单", tracking)
        self.assertIn("Ceramic Cup", tracking)
        self.assertIn("CP-MARK", tracking)
        self.assertIn("未下单", tracking)

        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE goods_lines SET logistics_status = 'exception' WHERE id = ?", (self.goods_line_id,))
            conn.commit()
        finally:
            conn.close()
        exception_page = self.request("GET", f"/tracking?import_order_id={self.order_id}&exception_only=1", cookie=f"session={token}")["body"]
        self.assertIn("异常", exception_page)

        search = self.request("GET", "/search?q=CP-MARK", cookie=f"session={token}")["body"]
        self.assertIn("goods_line", search)
        self.assertIn(f"/goods-lines/{self.goods_line_id}/edit", search)

    def test_goods_tracking_is_order_scoped_and_updates_status(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                UPDATE goods_lines
                SET carton_count = 10, units_per_carton = 10,
                    carton_length_cm = 40, carton_width_cm = 30, carton_height_cm = 20,
                    carton_gross_weight_kg = 8,
                    purchase_unit_price = 10, purchase_currency = 'CNY',
                    target_markup = 0.3, sales_unit_price = 13, sales_currency = 'EUR'
                WHERE id = ?
                """,
                (self.goods_line_id,),
            )
            conn.commit()
        finally:
            conn.close()

        page = self.request("GET", f"/tracking?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        for label in ["货物详情", "货物项", "供应商", "SKU/型号", "每箱数量", "外箱尺寸(cm)", "单箱毛重(kg)", "CBM", "总毛重(kg)", "采购单价", "采购币种", "目标加价率", "销售单价", "销售币种", "国内物流单号", "货物物流状态", "操作"]:
            self.assertIn(label, page)
        self.assertNotIn("缺资料", page)
        self.assertNotIn("<th>异常</th>", page)
        self.assertNotIn("只看异常", page)
        self.assertIn("Ceramic Cup", page)
        self.assertIn("CP-2026-0001", page)
        self.assertIn("40 x 30 x 20", page)
        self.assertIn("<td>0.24</td>", page)
        self.assertIn("<td>80</td>", page)
        self.assertIn("<td>10</td>", page)
        self.assertIn("<td>CNY</td>", page)
        self.assertIn("<td>0.3</td>", page)
        self.assertIn("<td>13</td>", page)
        self.assertIn("<td>EUR</td>", page)
        self.assertIn('name="logistics_status"', page)
        self.assertIn("tracking-scroll", page)
        self.assertIn('select name="import_order_id" onchange="this.form.submit()"', page)
        self.assertNotIn(">筛选</button>", page)
        self.assertNotIn("<summary>更新</summary>", page)

        response = self.request(
            "POST",
            "/tracking/status",
            body=f"goods_line_id={self.goods_line_id}&import_order_id={self.order_id}&logistics_status=domestic_shipped",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], f"/tracking?import_order_id={self.order_id}")
        page = self.request("GET", response["headers"]["Location"], cookie=f"session={token}")["body"]
        self.assertIn("国内运输中", page)
        self.assertIn("table-scroll", page)

        conn = connect(self.db_path)
        try:
            audit = conn.execute(
                "SELECT * FROM audit_logs WHERE target_type = 'goods_line' AND target_id = ? AND field_name = 'logistics_status'",
                (self.goods_line_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(audit)

    def test_goods_logistics_status_choices_are_simplified(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE goods_lines SET logistics_status = 'supplier_preparing' WHERE id = ?", (self.goods_line_id,))
            conn.commit()
        finally:
            conn.close()

        page = self.request("GET", f"/tracking?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("已下单/备货中", page)
        self.assertNotIn('value="supplier_preparing"', page)
        self.assertNotIn('value="checked"', page)

    def test_admin_can_use_excel_and_finance_screen(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        page = self.request("GET", "/excel-finance", cookie=f"session={token}")["body"]
        self.assertIn("成本利润", page)
        self.assertIn("订单利润总览", page)
        self.assertNotIn("货物项报价表", page)
        self.assertIn("客户收费明细", page)
        self.assertIn("汇率/币种提示", page)
        self.assertIn("CUP-A1", page)
        self.assertIn("新增成本", page)
        self.assertIn("新增客户收费", page)
        self.assertIn("上传 Excel 成本", page)
        self.assertIn('name="file" type="file"', page)
        self.assertNotIn("<h2>新增成本/收费</h2>", page)
        self.assertIn("货物销售总值", page)
        self.assertIn(f'href="/tracking?import_order_id={self.order_id}"', page)
        self.assertIn("查看货物详情", page)

        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE goods_lines SET sales_unit_price = 13, sales_currency = 'EUR' WHERE id = ?", (self.goods_line_id,))
            conn.commit()
        finally:
            conn.close()
        page = self.request("GET", "/excel-finance", cookie=f"session={token}")["body"]
        self.assertIn("<strong>EUR 1300.00</strong>", page)

        self.request(
            "POST",
            "/finance/line",
            body=f"import_order_id={self.order_id}&goods_line_id={self.goods_line_id}&line_kind=cost&cost_type=purchase&charge_type=product_sales&amount=100&currency=EUR&exchange_rate_to_base=1&line_date=2026-06-01&notes=buy",
            cookie=f"session={token}",
        )
        self.request(
            "POST",
            "/finance/line",
            body=f"import_order_id={self.order_id}&line_kind=charge&cost_type=purchase&charge_type=product_sales&amount=160&currency=EUR&exchange_rate_to_base=1&line_date=2026-06-02&notes=sell",
            cookie=f"session={token}",
        )
        page = self.request("GET", "/excel-finance", cookie=f"session={token}")["body"]
        self.assertIn("60.00", page)
        self.assertIn("合计", page)
        self.assertIn("2026-06-01", page)
        self.assertIn("2026-06-02", page)
        self.assertIn("入账金额", page)
        self.assertIn("入账日期", page)
        self.assertIn("product_sales", page)
        self.assertIn("aria-label=\"编辑\"", page)
        self.assertIn("aria-label=\"删除\"", page)

        conn = connect(self.db_path)
        try:
            cost_id = conn.execute("SELECT id FROM finance_lines WHERE notes = 'buy'").fetchone()["id"]
        finally:
            conn.close()
        response = self.request(
            "POST",
            f"/finance-lines/{cost_id}/edit",
            body=f"import_order_id={self.order_id}&goods_line_id={self.goods_line_id}&line_kind=cost&cost_type=warehouse&amount=120&currency=EUR&exchange_rate_to_base=1&notes=storage",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], f"/excel-finance?import_order_id={self.order_id}")
        page = self.request("GET", response["headers"]["Location"], cookie=f"session={token}")["body"]
        self.assertIn("warehouse", page)
        self.assertIn("40.00", page)

        response = self.request(
            "POST",
            f"/finance-lines/{cost_id}/delete",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], f"/excel-finance?import_order_id={self.order_id}")
        conn = connect(self.db_path)
        try:
            deleted = conn.execute("SELECT id FROM finance_lines WHERE id = ?", (cost_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNone(deleted)

        upload = Path(self.tmp.name) / "cost-upload.xlsx"
        export_rows_xlsx(
            upload,
            FINANCE_COST_UPLOAD_HEADERS,
            [
                {
                    "中文项目 (Item)": "海运费",
                    "English Description": "Ocean Freight (The container)",
                    "Amount": 2400,
                    "Currency": "USD",
                    "说明备注 (Remarks)": "Main carriage sea freight",
                }
            ],
        )
        body, content_type = multipart_body({"import_order_id": str(self.order_id)}, {"file": ("cost-upload.xlsx", upload.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        response = self.request(
            "POST",
            "/finance/cost-import",
            body=body,
            content_type=content_type,
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertIn("已导入 1 条成本", response["body"])
        self.assertIn("sea_freight", response["body"])

        bad_upload = Path(self.tmp.name) / "bad-cost-upload.xlsx"
        export_rows_xlsx(bad_upload, FINANCE_COST_UPLOAD_HEADERS, [{"中文项目 (Item)": "海运费", "English Description": "Ocean Freight", "Amount": "x", "Currency": "USD"}])
        body, content_type = multipart_body({"import_order_id": str(self.order_id)}, {"file": ("bad-cost-upload.xlsx", bad_upload.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        response = self.request(
            "POST",
            "/finance/cost-import",
            body=body,
            content_type=content_type,
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertIn("Amount 无效", response["body"])

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
        response = self.request("POST", "/finance-lines/1/edit", body=f"import_order_id={self.order_id}", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)
        response = self.request("POST", "/finance-lines/1/delete", body=f"import_order_id={self.order_id}", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)

    def test_admin_can_create_container_loading_and_export_list(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        page = self.request("GET", f"/shipping-docs?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("海运单证", page)
        self.assertIn("单证阻塞项", page)
        self.assertIn("document-blocker-scroll", page)
        self.assertIn("商业发票版本", page)
        self.assertIn("合规文件列表", page)
        self.assertIn('<details class="action-drawer"><summary>新增集装箱</summary>', page)
        self.assertIn('<details class="action-drawer"><summary>记录装箱</summary>', page)
        self.assertIn("上传/登记合规文件", page)
        self.assertIn('name="loading_photo" type="file"', page)
        self.assertIn('name="file" type="file"', page)

        certificate = Path(self.tmp.name) / "co.pdf"
        certificate.write_bytes(b"pdf")
        response = self.request(
            "POST",
            "/compliance-files",
            body=f"import_order_id={self.order_id}&file_category=certificate_origin&path={certificate}",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], f"/shipping-docs?import_order_id={self.order_id}")
        page = self.request("GET", response["headers"]["Location"], cookie=f"session={token}")["body"]
        self.assertIn("产地证", page)
        self.assertIn("co.pdf", page)

        body, content_type = multipart_body(
            {"import_order_id": str(self.order_id), "file_category": "inspection_certificate"},
            {"file": ("inspection.pdf", b"pdf2", "application/pdf")},
        )
        response = self.request(
            "POST",
            "/compliance-files",
            body=body,
            content_type=content_type,
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        conn = connect(self.db_path)
        try:
            file_row = conn.execute("SELECT storage_path FROM files WHERE file_name = 'inspection.pdf'").fetchone()
        finally:
            conn.close()
        self.assertTrue(Path(file_row["storage_path"]).exists())

        response = self.request(
            "POST",
            "/containers",
            body=f"import_order_id={self.order_id}&container_type=20GP&container_number=MSKU1&seal_number=S1&loading_date=2026-07-01&sea_freight_amount=200&sea_freight_currency=EUR&sea_freight_exchange_rate=1",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        finance = self.request("GET", f"/excel-finance?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("sea_freight", finance)
        self.assertIn("200.0", finance)

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
        self.assertIn("HS Code", blocked["body"])

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
        page = self.request("GET", f"/receiving?warehouse_id={self.receiving_warehouse_id}&q=CP-MARK", cookie=f"session={token}")["body"]
        self.assertIn("仓库信息", page)
        self.assertIn("待入库", page)
        self.assertIn("CP-MARK", page)
        self.assertIn("Ceramic Cup", page)
        self.assertIn("未下单", page)
        self.assertIn('name="receiving_photo" type="file"', page)
        self.assertIn("warehouse-scroll", page)
        self.assertNotIn('class="mini-input" form="receive-', page)
        self.assertNotIn('aria-label="新增仓库"', page)
        self.assertNotIn('aria-label="编辑仓库"', page)

        photo = Path(self.tmp.name) / "receive.jpg"
        photo.write_bytes(b"photo")
        response = self.request(
            "POST",
            "/receiving/record",
            body=f"goods_line_id={self.goods_line_id}&warehouse_id={self.receiving_warehouse_id}&status=all&query=CP-MARK&domestic_tracking_no=YT999&received_carton_count=4&package_condition=ok&receiving_photo_path={photo}",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], f"/receiving?warehouse_id={self.receiving_warehouse_id}&status=all&q=CP-MARK")

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

    def test_admin_can_manage_warehouses_from_basic_data(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        page = self.request("GET", f"/receiving?warehouse_id={self.receiving_warehouse_id}", cookie=f"session={token}")["body"]
        self.assertNotIn('aria-label="新增仓库"', page)
        self.assertNotIn('aria-label="编辑仓库"', page)
        self.assertNotIn('aria-label="删除仓库"', page)

        response = self.request(
            "POST",
            "/basic-data/warehouses",
            body="type=port&name=Shanghai+Port&contact_name=Wu&phone=021&address=Shanghai",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], "/basic-data#warehouses")
        page = self.request("GET", "/basic-data", cookie=f"session={token}")["body"]
        self.assertIn("Shanghai Port", page)
        conn = connect(self.db_path)
        try:
            new_warehouse_id = conn.execute("SELECT id FROM warehouses WHERE name = 'Shanghai Port'").fetchone()["id"]
        finally:
            conn.close()

        response = self.request(
            "POST",
            f"/basic-data/warehouses/{new_warehouse_id}/edit",
            body="type=port&name=Shanghai+Port+Edited&contact_name=Wu&phone=022&address=Shanghai",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", "/basic-data", cookie=f"session={token}")["body"]
        self.assertIn("Shanghai Port Edited", page)

        response = self.request(
            "POST",
            f"/basic-data/warehouses/{self.receiving_warehouse_id}/delete",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertIn("该仓库已关联订单，不能删除", response["body"])

        response = self.request(
            "POST",
            f"/basic-data/warehouses/{new_warehouse_id}/delete",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        conn = connect(self.db_path)
        try:
            deleted = conn.execute("SELECT id FROM warehouses WHERE id = ?", (new_warehouse_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNone(deleted)

    def test_warehouse_user_cannot_manage_warehouses_from_receiving(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        response = self.request(
            "POST",
            "/receiving/warehouses",
            body="type=receiving&name=Blocked",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)
        response = self.request(
            "POST",
            f"/receiving/warehouses/{self.receiving_warehouse_id}/edit",
            body="type=receiving&name=Blocked",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)
        response = self.request(
            "POST",
            f"/receiving/warehouses/{self.receiving_warehouse_id}/delete",
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)

        body, content_type = multipart_body(
            {
                "goods_line_id": str(self.goods_line_id),
                "warehouse_id": str(self.receiving_warehouse_id),
                "status": "all",
                "query": "CP-MARK",
                "received_carton_count": "1",
            },
            {"receiving_photo": ("receive-upload.jpg", b"photo2", "image/jpeg")},
        )
        response = self.request(
            "POST",
            "/receiving/record",
            body=body,
            content_type=content_type,
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        conn = connect(self.db_path)
        try:
            file_row = conn.execute("SELECT storage_path FROM files WHERE file_name = 'receive-upload.jpg'").fetchone()
        finally:
            conn.close()
        self.assertTrue(Path(file_row["storage_path"]).exists())

    def test_goods_line_form_uses_chinese_field_labels(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        page = self.request("GET", f"/goods-lines/{self.goods_line_id}/edit", cookie=f"session={token}")["body"]

        for label in ["基本信息", "报价利润", "包装尺寸", "报关英文品名", "目标加价率", "单箱毛重(kg)"]:
            self.assertIn(label, page)
        self.assertIn("select name='logistics_status'", page)
        self.assertIn("select name='compliance_status'", page)
        for raw_label in [">customs_en_name<", ">target_markup<", ">carton_gross_weight_kg<"]:
            self.assertNotIn(raw_label, page)

    def test_warehouse_user_can_record_and_resolve_exception(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        self.request(
            "POST",
            "/receiving/record",
            body=f"goods_line_id={self.goods_line_id}&warehouse_id={self.receiving_warehouse_id}&status=exception&query=CP-MARK&received_carton_count=1&arrival_exception_type=damaged_cartons",
            cookie=f"session={token}",
        )
        page = self.request("GET", f"/receiving?warehouse_id={self.receiving_warehouse_id}&status=exception&q=CP-MARK", cookie=f"session={token}")["body"]
        self.assertIn("exception", page)
        self.assertIn("解除异常", page)

        self.request(
            "POST",
            "/receiving/resolve",
            body=f"goods_line_id={self.goods_line_id}&warehouse_id={self.receiving_warehouse_id}&status=exception&query=CP-MARK",
            cookie=f"session={token}",
        )
        conn = connect(self.db_path)
        try:
            goods = conn.execute("SELECT logistics_status FROM goods_lines WHERE id = ?", (self.goods_line_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(goods["logistics_status"], "received_at_warehouse")

    def test_order_assistant_buttons_live_inside_existing_workflows(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        orders = self.request("GET", f"/orders?order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("订单助手", orders)
        self.assertIn("AI检查订单", orders)
        self.assertIn("暂无 AI 运行记录", orders)
        self.assertNotIn('href="/assistant"', orders)

        tracking = self.request("GET", f"/tracking?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("AI检查货物资料", tracking)

        docs = self.request("GET", f"/shipping-docs?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("AI检查单证阻塞项", docs)
        self.assertIn("AI生成单证草稿", docs)

        finance = self.request("GET", f"/excel-finance?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("AI检查利润风险", finance)

    def test_order_assistant_review_gate_before_change_draft_confirmation(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        upload_path = Path(self.tmp.name) / "assistant-goods.xlsx"
        export_rows_xlsx(
            upload_path,
            CHINESE_GOODS_HEADERS,
            [{"产品名称": "AI待确认货物", "数量（非包裹数）": 3, "箱数量": 1}],
        )

        response = self.request(
            "POST",
            "/assistant/run",
            body=urlencode({
                "import_order_id": self.order_id,
                "task_template": "file_text_intake",
                "path": str(upload_path),
                "return_to": f"/orders?order_id={self.order_id}",
            }),
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        assistant_page = self.request("GET", f"/orders?order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn('class="assistant-lane"', assistant_page)
        self.assertIn('class="assistant-run"', assistant_page)
        self.assertIn("资料导入", assistant_page)

        conn = connect(self.db_path)
        try:
            self.assertIsNone(conn.execute("SELECT * FROM goods_lines WHERE cn_name = 'AI待确认货物'").fetchone())
            self.assertIsNone(conn.execute("SELECT * FROM change_drafts WHERE draft_type = 'goods_line'").fetchone())
            review = conn.execute("SELECT * FROM review_requests WHERE draft_type = 'goods_line' ORDER BY id DESC").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(review)

        self.request(
            "POST",
            "/assistant/review",
            body=urlencode({
                "review_request_id": review["id"],
                "status": REVIEW_APPROVED_FOR_DRAFT,
                "return_to": f"/orders?order_id={self.order_id}",
            }),
            cookie=f"session={token}",
        )
        conn = connect(self.db_path)
        try:
            draft = conn.execute("SELECT * FROM change_drafts WHERE draft_type = 'goods_line' ORDER BY id DESC").fetchone()
            self.assertIsNone(conn.execute("SELECT * FROM goods_lines WHERE cn_name = 'AI待确认货物'").fetchone())
        finally:
            conn.close()
        self.assertIsNotNone(draft)

        self.request(
            "POST",
            f"/assistant/drafts/{draft['id']}/confirm",
            body=urlencode({
                "return_to": f"/orders?order_id={self.order_id}",
                "final_values_json": json.dumps({"cn_name": "管理员确认货物"}, ensure_ascii=False),
            }),
            cookie=f"session={token}",
        )
        conn = connect(self.db_path)
        try:
            created = conn.execute("SELECT * FROM goods_lines WHERE cn_name = '管理员确认货物'").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(created)

    def request(self, method, path, body="", cookie="", decode=True, content_type="application/x-www-form-urlencoded"):
        handler = DummyRequest()
        sent = {"headers": {}}
        handler.path = path
        body_bytes = body if isinstance(body, bytes) else body.encode()
        handler.headers = {"Content-Length": str(len(body_bytes)), "Cookie": cookie, "Content-Type": content_type}
        handler.rfile = _Reader(body_bytes)
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


class _MockDeepSeekResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def multipart_body(fields, files):
    boundary = "----cargopilot-test"
    chunks = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode(),
            b"\r\n",
        ])
    for name, (filename, data, content_type) in files.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            data,
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


if __name__ == "__main__":
    unittest.main()

from http import HTTPStatus
from http.cookies import SimpleCookie
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from cargopilot.foundation import ROLE_ADMIN, ROLE_WAREHOUSE, connect, create_user, initialize_database
from cargopilot.master_data import WAREHOUSE_RECEIVING, create_consignee, create_supplier, create_warehouse
from cargopilot.order_assistant import CHINESE_GOODS_HEADERS, REVIEW_APPROVED_FOR_DRAFT
from cargopilot.orders import create_goods_line, create_import_order
from cargopilot.spreadsheet_io import FINANCE_COST_UPLOAD_HEADERS, ORDER_GOODS_UPLOAD_HEADERS, export_rows_xlsx
from cargopilot.web import CargoPilotHandler, SESSIONS, classify_assistant_source


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

    def test_ai_intake_classifies_natural_language_order_command(self):
        self.assertEqual(
            classify_assistant_source(text="把test1订单中所有的货物物流状态设置成海运中"),
            "order_command",
        )
        self.assertEqual(
            classify_assistant_source(text="把订单中的货物信息全部删除"),
            "order_command",
        )
        self.assertEqual(classify_assistant_source(text="删除这个订单"), "order_command")
        self.assertEqual(classify_assistant_source(name="265956379_放行单.pdf", path="/tmp/265956379_放行单.pdf"), "customs_declaration")
        self.assertEqual(classify_assistant_source(name="unknown.pdf", path="/tmp/unknown.pdf", text="这是海运单，请提取集装箱数据"), "waybill")
        self.assertEqual(classify_assistant_source(name="265956379_VerifyCopy.pdf", path="/tmp/265956379_VerifyCopy.pdf", text="这是海运单，请提取集装箱数据"), "waybill")

    def test_admin_dashboard_navigation_and_cards(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        response = self.request("GET", "/dashboard", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.OK)
        for label in ["Dashboard", "订单详情", "货物详情", "仓库盘点", "订单智能体", "AI资料收集箱", "基础资料", "海运单证", "成本利润"]:
            self.assertIn(label, response["body"])
        nav_labels = ["Dashboard", "订单详情", "货物详情", "仓库盘点", "订单智能体", "AI资料收集箱", "海运单证", "成本利润", "基础资料"]
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
        self.assertNotIn("订单智能体", response["body"])
        self.assertNotIn("AI资料收集箱", response["body"])
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

        order_agent = self.request("GET", "/order-agent", cookie=f"session={token}")["body"]
        self.assertIn('<a href="/order-agent" class="active">订单智能体</a>', order_agent)

    def test_order_agent_empty_state_and_retained_conversation(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        page = self.request("GET", "/order-agent", cookie=f"session={token}")["body"]
        self.assertIn("订单智能体", page)
        self.assertIn("AI资料收集箱", page)
        self.assertIn("不关联进口订单", page)
        self.assertIn("请先新建或打开一个订单智能体对话", page)
        self.assertIn('name="files" type="file"', page)
        self.assertIn('textarea name="message"', page)
        self.assertIn("order-agent-conversation-scroll", page)
        self.assertIn("order-agent-list-scroll", page)
        self.assertIn("order-agent-workspace-scroll", page)
        self.assertIn("Agent Processing Trace", page)
        self.assertIn("暂无处理轨迹", page)
        self.assertIn("结果区", page)
        self.assertIn("暂无结果", page)

        response = self.request(
            "POST",
            "/order-agent/conversations",
            body=urlencode({"title": "供应商资料建单", "message": "帮我根据这些资料创建一个订单"}),
            cookie=f"session={token}",
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertTrue(response["headers"]["Location"].startswith("/order-agent?conversation_id="))
        conversation_id = int(response["headers"]["Location"].rsplit("=", 1)[1])

        refreshed = self.request("GET", response["headers"]["Location"], cookie=f"session={token}")["body"]
        self.assertIn("供应商资料建单", refreshed)
        self.assertIn("帮我根据这些资料创建一个订单", refreshed)
        self.assertIn("未关联订单", refreshed)
        self.assertIn('name="files" type="file"', refreshed)
        self.assertIn("保存并解析资料", refreshed)

        conn = connect(self.db_path)
        try:
            conversation = conn.execute("SELECT * FROM order_agent_conversations WHERE id = ?", (conversation_id,)).fetchone()
            self.assertIsNone(conn.execute("SELECT * FROM assistant_runs").fetchone())
        finally:
            conn.close()
        self.assertIsNone(conversation["import_order_id"])
        self.assertEqual(conversation["status"], "draft")
        self.assertIn("帮我根据这些资料创建一个订单", conversation["messages_json"])

    def test_order_agent_can_associate_order_append_message_and_close(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        response = self.request(
            "POST",
            "/order-agent/conversations",
            body=urlencode({"import_order_id": self.order_id, "message": "帮我检查这个订单清关和单证风险"}),
            cookie=f"session={token}",
        )
        conversation_id = int(response["headers"]["Location"].rsplit("=", 1)[1])
        page = self.request("GET", response["headers"]["Location"], cookie=f"session={token}")["body"]
        self.assertIn("CP-2026-0001", page)
        self.assertIn(f"<option value='{self.order_id}' selected>CP-2026-0001</option>", page)

        self.request(
            "POST",
            f"/order-agent/conversations/{conversation_id}/messages",
            body=urlencode({"message": "补充：目的港 Rotterdam"}),
            cookie=f"session={token}",
        )
        page = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("补充：目的港 Rotterdam", page)

        response = self.request("POST", f"/order-agent/conversations/{conversation_id}/close", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        closed = self.request("GET", response["headers"]["Location"], cookie=f"session={token}")["body"]
        self.assertIn("已关闭", closed)
        self.assertIn("<button type=\"submit\" disabled>保存并解析资料</button>", closed)

        ai_intake = self.request("GET", f"/ai-intake?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("AI资料收集箱", ai_intake)
        self.assertIn("AI处理资料", ai_intake)

    def test_order_agent_message_batch_records_trace_summaries_without_assistant_run(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        response = self.request(
            "POST",
            "/order-agent/conversations",
            body=urlencode({"message": "先开一个资料录入会话"}),
            cookie=f"session={token}",
        )
        conversation_id = int(response["headers"]["Location"].rsplit("=", 1)[1])
        goods_xlsx = Path(self.tmp.name) / "goods.xlsx"
        export_rows_xlsx(
            goods_xlsx,
            CHINESE_GOODS_HEADERS,
            [{"产品名称": "批量测试杯", "数量（非包裹数）": 2}],
        )
        files = [
            ("files", "goods.xlsx", goods_xlsx.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("files", "notes.txt", "供应商备注：目的港 Hamburg".encode(), "text/plain"),
            ("files", "scan.pdf", b"%PDF-1.4\n", "application/pdf"),
        ]
        body, content_type = multipart_body(
            {"message": "这次先只解析资料", "source_text": "供应商确认 7 月出货"},
            files,
        )

        with patch("cargopilot.order_assistant._pdf_text_with_pypdf", return_value=("", "PDF 未包含可直接提取的文字")):
            with patch("cargopilot.order_assistant.shutil.which", return_value=None):
                post = self.request(
                    "POST",
                    f"/order-agent/conversations/{conversation_id}/messages",
                    body=body,
                    cookie=f"session={token}",
                    content_type=content_type,
                )

        self.assertEqual(post["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(post["headers"]["Location"], f"/order-agent?conversation_id={conversation_id}")
        conn = connect(self.db_path)
        try:
            conversation = conn.execute("SELECT * FROM order_agent_conversations WHERE id = ?", (conversation_id,)).fetchone()
            self.assertEqual(conn.execute("SELECT COUNT(*) AS count FROM assistant_runs").fetchone()["count"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS count FROM change_drafts").fetchone()["count"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS count FROM review_requests").fetchone()["count"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS count FROM assistant_suggestions").fetchone()["count"], 0)
        finally:
            conn.close()
        trace = json.loads(conversation["trace_json"])
        result = json.loads(conversation["result_json"])
        trace_text = json.dumps(trace, ensure_ascii=False)
        self.assertIn("goods.xlsx", trace_text)
        self.assertIn("notes.txt", trace_text)
        self.assertIn("scan.pdf", trace_text)
        self.assertIn("1 行数据", trace_text)
        self.assertIn("扫描件 OCR 需要安装", trace_text)
        self.assertIn("粘贴资料", trace_text)
        source_names = {source["name"] for source in result["source_summaries"]}
        self.assertIn("goods.xlsx", source_names)
        self.assertIn("notes.txt", source_names)
        self.assertNotIn("scan.pdf", source_names)
        self.assertIn("粘贴资料", source_names)

        page = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("Agent Processing Trace", page)
        self.assertIn("goods.xlsx", page)
        self.assertIn("notes.txt", page)
        self.assertIn("scan.pdf", page)
        self.assertIn("扫描件 OCR 需要安装", page)
        self.assertIn("粘贴资料", page)
        self.assertIn("不会在后续 Agent 成功前生成录入申请、风险提示或草稿", page)

    def test_order_agent_task_understanding_classifies_data_entry_and_keeps_raw_response_collapsed(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        create_response = self.request(
            "POST",
            "/order-agent/conversations",
            body=urlencode({"message": "先开一个资料录入会话"}),
            cookie=f"session={token}",
        )
        conversation_id = int(create_response["headers"]["Location"].rsplit("=", 1)[1])
        model_output = {
            "needsDataEntry": True,
            "needsRiskPrompting": False,
            "refusal": False,
            "refusalReason": "",
            "businessSummary": "用户希望根据资料创建订单，只需要资料录入。",
            "confidence": 0.91,
            "nextAction": "data_entry",
            "missingInformation": ["客户", "目的港"],
        }
        payload = {"choices": [{"message": {"content": json.dumps(model_output, ensure_ascii=False)}}], "usage": {"prompt_tokens": 10, "completion_tokens": 8}}
        captured = []

        def fake_urlopen(req, timeout):
            captured.append(json.loads(req.data.decode()))
            return _MockDeepSeekResponse(payload)

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret", "DEEPSEEK_MODEL": "deepseek-reasoner"}):
            with patch("cargopilot.order_assistant.request.urlopen", side_effect=fake_urlopen) as mocked:
                post = self.request(
                    "POST",
                    f"/order-agent/conversations/{conversation_id}/messages",
                    body=urlencode({"message": "帮我根据这些资料创建一个订单"}),
                    cookie=f"session={token}",
                )

        self.assertEqual(post["status"], HTTPStatus.SEE_OTHER)
        self.assertTrue(mocked.called)
        request_payload = json.loads(captured[0]["messages"][1]["content"])
        self.assertEqual(request_payload["agentName"], "task_understanding")
        self.assertEqual(request_payload["selectedImportOrder"], None)
        self.assertIn("帮我根据这些资料创建一个订单", request_payload["naturalLanguageInput"])
        page = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("任务理解结果", page)
        self.assertIn("用户希望根据资料创建订单，只需要资料录入。", page)
        self.assertIn("资料录入", page)
        self.assertIn("不做风险提示", page)
        self.assertIn("<details><summary>原始信息</summary>", page)
        self.assertNotIn("<details open", page)
        self.assertIn("needsDataEntry", page)

        conn = connect(self.db_path)
        try:
            conversation = conn.execute("SELECT * FROM order_agent_conversations WHERE id = ?", (conversation_id,)).fetchone()
            result = json.loads(conversation["result_json"])
            self.assertTrue(result["task_understanding"]["needs_data_entry"])
            self.assertFalse(result["task_understanding"]["needs_risk_prompting"])
            self.assertEqual(conn.execute("SELECT COUNT(*) AS count FROM assistant_runs").fetchone()["count"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS count FROM change_drafts").fetchone()["count"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS count FROM review_requests").fetchone()["count"], 0)
        finally:
            conn.close()

    def test_order_agent_task_understanding_classifies_risk_prompt_with_selected_order_context(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        create_response = self.request(
            "POST",
            "/order-agent/conversations",
            body=urlencode({"import_order_id": self.order_id, "message": "检查风险会话"}),
            cookie=f"session={token}",
        )
        conversation_id = int(create_response["headers"]["Location"].rsplit("=", 1)[1])
        model_output = {
            "needsDataEntry": False,
            "needsRiskPrompting": True,
            "refusal": False,
            "refusalReason": "",
            "businessSummary": "用户要求检查清关和单证风险，只需要风险提示。",
            "confidence": 0.88,
            "nextAction": "risk_prompting",
            "missingInformation": [],
        }
        payload = {"choices": [{"message": {"content": json.dumps(model_output, ensure_ascii=False)}}], "usage": {}}
        captured = []

        def fake_urlopen(req, timeout):
            captured.append(json.loads(req.data.decode()))
            return _MockDeepSeekResponse(payload)

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret"}):
            with patch("cargopilot.order_assistant.request.urlopen", side_effect=fake_urlopen):
                self.request(
                    "POST",
                    f"/order-agent/conversations/{conversation_id}/messages",
                    body=urlencode({"message": "帮我检查这个订单清关和单证风险"}),
                    cookie=f"session={token}",
                )

        request_payload = json.loads(captured[0]["messages"][1]["content"])
        self.assertEqual(request_payload["selectedImportOrder"]["orderNo"], "CP-2026-0001")
        self.assertEqual(request_payload["selectedImportOrder"]["destinationPort"], "Hamburg")
        page = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("不做资料录入", page)
        self.assertIn("风险提示", page)
        self.assertIn("用户要求检查清关和单证风险", page)

    def test_order_agent_file_only_task_understanding_uses_attachment_summaries(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        create_response = self.request("POST", "/order-agent/conversations", body=urlencode({"message": ""}), cookie=f"session={token}")
        conversation_id = int(create_response["headers"]["Location"].rsplit("=", 1)[1])
        goods_xlsx = Path(self.tmp.name) / "file-only.xlsx"
        export_rows_xlsx(goods_xlsx, CHINESE_GOODS_HEADERS, [{"产品名称": "文件货物", "数量（非包裹数）": 1}])
        body, content_type = multipart_body({}, [("files", "file-only.xlsx", goods_xlsx.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")])
        model_output = {
            "needsDataEntry": True,
            "needsRiskPrompting": False,
            "refusal": False,
            "refusalReason": "",
            "businessSummary": "只有附件资料，默认进入资料录入。",
            "confidence": 0.8,
            "nextAction": "data_entry",
            "missingInformation": [],
        }
        payload = {"choices": [{"message": {"content": json.dumps(model_output, ensure_ascii=False)}}], "usage": {}}
        captured = []

        def fake_urlopen(req, timeout):
            captured.append(json.loads(req.data.decode()))
            return _MockDeepSeekResponse(payload)

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret"}):
            with patch("cargopilot.order_assistant.request.urlopen", side_effect=fake_urlopen):
                self.request(
                    "POST",
                    f"/order-agent/conversations/{conversation_id}/messages",
                    body=body,
                    cookie=f"session={token}",
                    content_type=content_type,
                )

        request_payload = json.loads(captured[0]["messages"][1]["content"])
        self.assertEqual(request_payload["naturalLanguageInput"], "")
        self.assertEqual(request_payload["attachmentSummaries"][0]["name"], "file-only.xlsx")
        page = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("只有附件资料，默认进入资料录入。", page)

    def test_order_agent_data_entry_agent_creates_editable_drafts_without_writing_records(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        conn = connect(self.db_path)
        try:
            before = {
                table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
                for table in ["import_orders", "goods_lines", "suppliers", "consignees", "change_drafts"]
            }
        finally:
            conn.close()
        create_response = self.request("POST", "/order-agent/conversations", body=urlencode({"message": "资料录入会话"}), cookie=f"session={token}")
        conversation_id = int(create_response["headers"]["Location"].rsplit("=", 1)[1])
        task_output = {
            "needsDataEntry": True,
            "needsRiskPrompting": False,
            "refusal": False,
            "refusalReason": "",
            "businessSummary": "需要生成资料录入草稿。",
            "confidence": 0.92,
            "nextAction": "data_entry",
            "missingInformation": [],
        }
        data_output = {
            "businessSummary": "已识别订单、货物和供应商草稿。",
            "missingInformation": ["客户"],
            "unmappedInformation": [{"field": "付款方式", "value": "TT"}],
            "drafts": [
                {
                    "draftType": "import_order_create",
                    "proposedValues": {
                        "destination_port": "Rotterdam",
                        "trade_term": "FOB",
                        "order_no": "USER-SHOULD-NOT-WRITE",
                        "order_status": "completed",
                    },
                    "confidence": 0.8,
                },
                {
                    "draftType": "goods_line_create",
                    "proposedValues": {"cn_name": "白杯子", "unknown_color": "white"},
                    "confidence": 0.77,
                },
                {
                    "draftType": "supplier_create_or_reuse",
                    "proposedValues": {"name": "供应商ABC", "phone": "123", "bank_account": "private"},
                    "confidence": 0.7,
                },
            ],
        }
        captured = []

        def fake_urlopen(req, timeout):
            body = json.loads(req.data.decode())
            captured.append(json.loads(body["messages"][1]["content"]))
            agent_name = captured[-1]["agentName"]
            output = task_output if agent_name == "task_understanding" else data_output
            payload = {"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}], "usage": {}}
            return _MockDeepSeekResponse(payload)

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret"}):
            with patch("cargopilot.order_assistant.request.urlopen", side_effect=fake_urlopen):
                response = self.request(
                    "POST",
                    f"/order-agent/conversations/{conversation_id}/messages",
                    body=urlencode({"message": "帮我根据这些资料创建一个订单"}),
                    cookie=f"session={token}",
                )

        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(captured[1]["agentName"], "data_entry")
        self.assertIn("fieldAllowlist", captured[1])
        self.assertIn("destination_port", captured[1]["fieldAllowlist"]["import_order_create"])
        conn = connect(self.db_path)
        try:
            conversation = conn.execute("SELECT * FROM order_agent_conversations WHERE id = ?", (conversation_id,)).fetchone()
            after = {
                table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
                for table in ["import_orders", "goods_lines", "suppliers", "consignees", "change_drafts"]
            }
        finally:
            conn.close()
        self.assertEqual(conversation["status"], "waiting_for_input")
        self.assertEqual(before, after)
        result = json.loads(conversation["result_json"])
        drafts = result["data_entry"]["drafts"]
        self.assertEqual(drafts[0]["proposed_values"]["destination_port"], "Rotterdam")
        self.assertNotIn("order_no", drafts[0]["proposed_values"])
        self.assertNotIn("order_status", drafts[0]["proposed_values"])
        self.assertEqual(drafts[1]["proposed_values"]["cn_name"], "白杯子")
        self.assertIn("unknown_color", drafts[1]["unmapped_fields"])
        self.assertIn("bank_account", drafts[2]["unmapped_fields"])
        self.assertIn("客户", result["data_entry"]["missing_information"])

        page = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("资料录入草稿", page)
        self.assertIn("订单创建草稿", page)
        self.assertIn("货物项草稿", page)
        self.assertIn("白杯子", page)
        self.assertIn("未映射信息", page)
        self.assertIn("unknown_color", page)
        self.assertIn("order-agent-draft-table-scroll", page)

    def test_order_agent_executes_order_creation_draft_after_confirmation(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        conn = connect(self.db_path)
        try:
            create_supplier(conn, actor_role=ROLE_ADMIN, name="供应商ABC", phone="旧电话")
            before = {
                table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
                for table in ["import_orders", "goods_lines", "suppliers", "consignees"]
            }
        finally:
            conn.close()
        create_response = self.request("POST", "/order-agent/conversations", body=urlencode({"message": "创建订单"}), cookie=f"session={token}")
        conversation_id = int(create_response["headers"]["Location"].rsplit("=", 1)[1])
        task_output = {
            "needsDataEntry": True,
            "needsRiskPrompting": False,
            "refusal": False,
            "refusalReason": "",
            "businessSummary": "用户要根据资料创建订单。",
            "confidence": 0.95,
            "nextAction": "data_entry",
            "missingInformation": [],
        }
        data_output = {
            "businessSummary": "已生成可确认的订单创建草稿。",
            "missingInformation": [],
            "drafts": [
                {"draftType": "import_order_create", "proposedValues": {"destination_port": "Rotterdam", "trade_term": "FOB"}, "confidence": 0.9},
                {"draftType": "consignee_create_or_reuse", "proposedValues": {"name": "Euro Import"}, "confidence": 0.9},
                {"draftType": "supplier_create_or_reuse", "proposedValues": {"name": "供应商ABC"}, "confidence": 0.9},
                {"draftType": "goods_line_create", "proposedValues": {"cn_name": "白杯子", "quantity": 12, "unit": "pcs"}, "confidence": 0.9},
            ],
        }

        def fake_urlopen(req, timeout):
            body = json.loads(req.data.decode())
            agent_name = json.loads(body["messages"][1]["content"])["agentName"]
            output = task_output if agent_name == "task_understanding" else data_output
            return _MockDeepSeekResponse({"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}], "usage": {}})

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret"}):
            with patch("cargopilot.order_assistant.request.urlopen", side_effect=fake_urlopen):
                self.request(
                    "POST",
                    f"/order-agent/conversations/{conversation_id}/messages",
                    body=urlencode({"message": "帮我根据资料创建订单"}),
                    cookie=f"session={token}",
                )

        conn = connect(self.db_path)
        try:
            unchanged = {
                table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
                for table in ["import_orders", "goods_lines", "suppliers", "consignees"]
            }
        finally:
            conn.close()
        self.assertEqual(before, unchanged)
        page_before = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("确认执行草稿", page_before)
        self.assertIn("供应商 供应商ABC：将复用已有记录", page_before)
        execute_body = urlencode({
            "draft_count": "4",
            "draft_1_type": "import_order_create",
            "draft_1_destination_port": "Rotterdam",
            "draft_1_trade_term": "FOB",
            "draft_2_type": "consignee_create_or_reuse",
            "draft_2_name": "Euro Import",
            "draft_3_type": "supplier_create_or_reuse",
            "draft_3_name": "供应商ABC",
            "draft_4_type": "goods_line_create",
            "draft_4_cn_name": "白杯子",
            "draft_4_quantity": "12",
            "draft_4_unit": "pcs",
        })
        execute_response = self.request(
            "POST",
            f"/order-agent/conversations/{conversation_id}/execute",
            body=execute_body,
            cookie=f"session={token}",
        )

        self.assertEqual(execute_response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(execute_response["headers"]["Location"], f"/order-agent?conversation_id={conversation_id}")
        conn = connect(self.db_path)
        try:
            after = {
                table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
                for table in ["import_orders", "goods_lines", "suppliers", "consignees"]
            }
            new_order = conn.execute("SELECT * FROM import_orders WHERE destination_port = 'Rotterdam'").fetchone()
            new_line = conn.execute("SELECT goods_lines.*, suppliers.name AS supplier_name FROM goods_lines LEFT JOIN suppliers ON suppliers.id = goods_lines.supplier_id WHERE goods_lines.import_order_id = ?", (new_order["id"],)).fetchone()
        finally:
            conn.close()
        self.assertEqual(after["import_orders"], before["import_orders"] + 1)
        self.assertEqual(after["goods_lines"], before["goods_lines"] + 1)
        self.assertEqual(after["suppliers"], before["suppliers"])
        self.assertEqual(after["consignees"], before["consignees"])
        self.assertNotEqual(new_order["order_no"], "USER-SHOULD-NOT-WRITE")
        self.assertEqual(new_order["order_no"], "CP-2026-0002")
        self.assertEqual(new_line["cn_name"], "白杯子")
        self.assertEqual(new_line["supplier_name"], "供应商ABC")
        page_after = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("创建完成：CP-2026-0002", page_after)
        self.assertIn("已留在订单智能体，不自动跳转", page_after)
        self.assertIn("本草稿已执行，不能重复确认。", page_after)

    def test_order_agent_executes_selected_order_update_drafts_and_blocks_cross_order_goods(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        conn = connect(self.db_path)
        try:
            other_order_id = create_import_order(
                conn,
                actor_role=ROLE_ADMIN,
                order_no="CP-2026-OTHER",
                receiving_warehouse_id=self.receiving_warehouse_id,
                destination_port="Paris",
            )
            other_goods_id = create_goods_line(
                conn,
                actor_role=ROLE_ADMIN,
                import_order_id=other_order_id,
                cn_name="别的订单杯子",
                logistics_status="not_ordered",
            )
        finally:
            conn.close()
        create_response = self.request(
            "POST",
            "/order-agent/conversations",
            body=urlencode({"import_order_id": str(self.order_id), "message": "更新当前订单"}),
            cookie=f"session={token}",
        )
        conversation_id = int(create_response["headers"]["Location"].rsplit("=", 1)[1])
        task_output = {
            "needsDataEntry": True,
            "needsRiskPrompting": False,
            "refusal": False,
            "refusalReason": "",
            "businessSummary": "用户要更新当前订单资料。",
            "confidence": 0.95,
            "nextAction": "data_entry",
            "missingInformation": [],
        }
        data_output = {
            "businessSummary": "已生成当前订单更新草稿。",
            "missingInformation": [],
            "drafts": [
                {"draftType": "import_order_update", "targetId": self.order_id, "proposedValues": {"destination_port": "Rotterdam"}, "confidence": 0.9},
                {"draftType": "goods_line_update", "targetId": self.goods_line_id, "proposedValues": {"logistics_status": "at_sea"}, "confidence": 0.9},
                {"draftType": "goods_line_update", "targetId": other_goods_id, "proposedValues": {"logistics_status": "arrived"}, "confidence": 0.9},
            ],
        }
        captured = []

        def fake_urlopen(req, timeout):
            body = json.loads(req.data.decode())
            payload = json.loads(body["messages"][1]["content"])
            captured.append(payload)
            output = task_output if payload["agentName"] == "task_understanding" else data_output
            return _MockDeepSeekResponse({"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}], "usage": {}})

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret"}):
            with patch("cargopilot.order_assistant.request.urlopen", side_effect=fake_urlopen):
                self.request(
                    "POST",
                    f"/order-agent/conversations/{conversation_id}/messages",
                    body=urlencode({"message": "把当前订单目的港改成 Rotterdam，货物改成海运中"}),
                    cookie=f"session={token}",
                )

        self.assertEqual(captured[1]["selectedImportOrder"]["id"], self.order_id)
        page_before = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("订单更新草稿", page_before)
        self.assertIn("货物项更新草稿", page_before)
        self.assertIn("当前 Hamburg → 建议 Rotterdam", page_before)
        self.assertIn("当前 未下单 → 建议 海运中", page_before)
        self.assertIn("目标货物项不属于当前订单", page_before)
        execute_response = self.request(
            "POST",
            f"/order-agent/conversations/{conversation_id}/execute",
            body=urlencode({
                "draft_count": "3",
                "draft_1_type": "import_order_update",
                "draft_1_target_id": str(self.order_id),
                "draft_1_destination_port": "Rotterdam",
                "draft_2_type": "goods_line_update",
                "draft_2_target_id": str(self.goods_line_id),
                "draft_2_logistics_status": "at_sea",
                "draft_3_type": "goods_line_update",
                "draft_3_target_id": str(other_goods_id),
                "draft_3_logistics_status": "arrived",
            }),
            cookie=f"session={token}",
        )

        self.assertEqual(execute_response["headers"]["Location"], f"/order-agent?conversation_id={conversation_id}")
        conn = connect(self.db_path)
        try:
            order = conn.execute("SELECT destination_port FROM import_orders WHERE id = ?", (self.order_id,)).fetchone()
            goods = conn.execute("SELECT logistics_status FROM goods_lines WHERE id = ?", (self.goods_line_id,)).fetchone()
            other_goods = conn.execute("SELECT logistics_status FROM goods_lines WHERE id = ?", (other_goods_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(order["destination_port"], "Rotterdam")
        self.assertEqual(goods["logistics_status"], "at_sea")
        self.assertEqual(other_goods["logistics_status"], "not_ordered")
        page_after = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("更新完成", page_after)
        self.assertIn("货物项 #", page_after)
        self.assertIn("已拦截", page_after)

    def test_order_agent_task_understanding_missing_config_fails_without_local_fallback(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        create_response = self.request("POST", "/order-agent/conversations", body=urlencode({"message": "失败测试"}), cookie=f"session={token}")
        conversation_id = int(create_response["headers"]["Location"].rsplit("=", 1)[1])

        with patch.dict("os.environ", {}, clear=True):
            post = self.request(
                "POST",
                f"/order-agent/conversations/{conversation_id}/messages",
                body=urlencode({"message": "帮我根据资料创建订单"}),
                cookie=f"session={token}",
            )

        self.assertEqual(post["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("任务理解失败", page)
        self.assertIn("DeepSeek 未配置或缺少 API Key", page)
        self.assertNotIn("任务理解结果", page)
        conn = connect(self.db_path)
        try:
            conversation = conn.execute("SELECT * FROM order_agent_conversations WHERE id = ?", (conversation_id,)).fetchone()
            result = json.loads(conversation["result_json"])
            self.assertNotIn("task_understanding", result)
            self.assertIn("task_understanding_error", result)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS count FROM assistant_runs").fetchone()["count"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS count FROM change_drafts").fetchone()["count"], 0)
        finally:
            conn.close()

    def test_order_agent_task_understanding_bad_model_output_fails_without_partial_result(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        create_response = self.request("POST", "/order-agent/conversations", body=urlencode({"message": "坏输出测试"}), cookie=f"session={token}")
        conversation_id = int(create_response["headers"]["Location"].rsplit("=", 1)[1])
        payload = {"choices": [{"message": {"content": json.dumps({"businessSummary": "缺字段"}, ensure_ascii=False)}}], "usage": {}}

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret"}):
            with patch("cargopilot.order_assistant.request.urlopen", return_value=_MockDeepSeekResponse(payload)):
                self.request(
                    "POST",
                    f"/order-agent/conversations/{conversation_id}/messages",
                    body=urlencode({"message": "帮我检查风险"}),
                    cookie=f"session={token}",
                )

        page = self.request("GET", f"/order-agent?conversation_id={conversation_id}", cookie=f"session={token}")["body"]
        self.assertIn("任务理解失败", page)
        self.assertIn("模型输出不可用", page)
        self.assertNotIn("任务理解结果", page)

    def test_warehouse_user_cannot_access_order_agent(self):
        token = "warehouse-token"
        SESSIONS[token] = self.warehouse_id
        response = self.request("GET", "/order-agent", cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.FORBIDDEN)

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
        self.assertIn(".order-agent-conversation-scroll { max-height:calc(100dvh - 330px); overflow:auto; }", css)
        self.assertIn(".order-agent-workspace-scroll { max-height:calc(100dvh - 330px); min-height:360px; overflow:auto; }", css)
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
                body="deepseek_api_key=sk-test&deepseek_model=deepseek-reasoner&deepseek_api_base=https%3A%2F%2Fapi.deepseek.com&deepseek_timeout_seconds=12&validate=1",
                cookie=f"session={token}",
            )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        page = self.request("GET", "/basic-data", cookie=f"session={token}")["body"]
        self.assertIn("大模型配置", page)
        self.assertIn("已配置（本地设置）", page)
        self.assertIn("deepseek-reasoner", page)
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

    def test_ai_intake_is_primary_admin_workflow(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id

        dashboard = self.request("GET", "/dashboard", cookie=f"session={token}")["body"]
        self.assertIn('<a href="/ai-intake">AI资料收集箱</a>', dashboard)

        assistant = self.request("GET", f"/ai-intake?import_order_id={self.order_id}", cookie=f"session={token}")
        self.assertEqual(assistant["status"], HTTPStatus.OK)
        self.assertIn("AI资料收集箱", assistant["body"])
        self.assertIn('select name="import_order_id"', assistant["body"])
        self.assertIn(f"<option value='{self.order_id}' selected>CP-2026-0001</option>", assistant["body"])
        for label in ["上传资料", "资料内容", "AI处理资料"]:
            self.assertIn(label, assistant["body"])
        for removed_label in ["供应商 Excel", "供应商邮件正文", "聊天记录", "PDF 单证", "仓库收货备注"]:
            self.assertNotIn(f"<label>{removed_label}", assistant["body"])
        self.assertIn('name="files" type="file"', assistant["body"])
        self.assertIn("multiple", assistant["body"])
        self.assertIn('name="real_data_confirmed" type="checkbox" value="1" checked', assistant["body"])
        self.assertIn("AI 正在处理资料", assistant["body"])
        self.assertIn("Router 路由器", assistant["body"])
        self.assertIn("真实回传信息", assistant["body"])
        self.assertIn("本次真实提交", assistant["body"])
        self.assertIn("服务端已返回", assistant["body"])
        self.assertIn("aiIntakeSubmit", assistant["body"])
        self.assertIn("确认并查看结果", assistant["body"])
        self.assertIn("ai-busy-confirm", assistant["body"])
        self.assertNotIn("<h2>识别结果</h2>", assistant["body"])
        self.assertNotIn("供应商消息草稿", assistant["body"])
        self.assertNotIn("生成供应商消息", assistant["body"])
        self.assertNotIn("订单助手", assistant["body"])
        self.assertNotIn("需跟进", assistant["body"])
        self.assertNotIn("管理员最终值 JSON", assistant["body"])

        SESSIONS["warehouse-token"] = self.warehouse_id
        restricted = self.request("GET", "/ai-intake", cookie="session=warehouse-token")
        self.assertEqual(restricted["status"], HTTPStatus.FORBIDDEN)

        orders = self.request("GET", f"/orders?order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertNotIn("订单助手", orders)
        self.assertNotIn("暂无 AI 运行记录", orders)
        self.assertNotIn('class="assistant-panel"', orders)
        self.assertIn(f'href="/ai-intake?import_order_id={self.order_id}#ai-intake-workspace"', orders)

        tracking = self.request("GET", f"/tracking?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn(f'href="/ai-intake?import_order_id={self.order_id}#ai-intake-workspace"', tracking)

        docs = self.request("GET", f"/shipping-docs?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn(f'href="/ai-intake?import_order_id={self.order_id}#ai-intake-workspace"', docs)

        finance = self.request("GET", f"/excel-finance?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn(f'href="/ai-intake?import_order_id={self.order_id}#ai-intake-workspace"', finance)

    def test_order_assistant_review_gate_before_change_draft_confirmation(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        upload_path = Path(self.tmp.name) / "assistant-goods.xlsx"
        export_rows_xlsx(
            upload_path,
            CHINESE_GOODS_HEADERS,
            [{"产品名称": "AI待确认货物", "数量（非包裹数）": 3, "箱数量": 1}],
        )

        body, content_type = multipart_body(
            {
                "import_order_id": str(self.order_id),
                "task_template": "file_text_intake",
                "return_to": f"/ai-intake?import_order_id={self.order_id}#ai-intake-workspace",
            },
            [("files", "assistant-goods.xlsx", upload_path.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
        )
        response = self.request(
            "POST",
            "/assistant/run",
            body=body,
            cookie=f"session={token}",
            content_type=content_type,
        )
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        self.assertEqual(response["headers"]["Location"], f"/ai-intake?import_order_id={self.order_id}#ai-intake-workspace")
        assistant_page = self.request("GET", f"/ai-intake?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn('class="assistant-lane"', assistant_page)
        self.assertIn('class="assistant-run"', assistant_page)
        self.assertIn("资料导入", assistant_page)
        self.assertIn("运行记录 <span class=\"count-badge\">1</span>", assistant_page)
        self.assertIn("识别数据录入 <span class=\"count-badge\">", assistant_page)
        self.assertIn("查看历史", assistant_page)

        conn = connect(self.db_path)
        try:
            self.assertIsNone(conn.execute("SELECT * FROM goods_lines WHERE cn_name = 'AI待确认货物'").fetchone())
            self.assertIsNone(conn.execute("SELECT * FROM change_drafts WHERE draft_type = 'goods_line'").fetchone())
            run = conn.execute("SELECT * FROM assistant_runs ORDER BY id DESC").fetchone()
            suggestion_id = conn.execute(
                """
                INSERT INTO assistant_suggestions (
                    assistant_run_id, import_order_id, agent_name, level, target_type,
                    target_id, suggestion_type, title, reason, source_references_json, created_at
                )
                VALUES (?, ?, '结构化录入 Agent', 'review-needed', 'goods_line', NULL, 'draft_candidate', 'AI待确认货物', '需要管理员确认后写入系统', '[]', '2026-06-28T00:00:00+00:00')
                """,
                (run["id"], self.order_id),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO review_requests (
                    assistant_suggestion_id, import_order_id, status, draft_candidate_json,
                    agent_name, draft_type, target_type, target_id, original_values_json,
                    source_references_json, confidence, created_at, updated_at
                )
                VALUES (?, ?, 'pending_review', ?, '结构化录入 Agent', 'goods_line', 'goods_line', NULL, '{}', '[]', 0.85, '2026-06-28T00:00:00+00:00', '2026-06-28T00:00:00+00:00')
                """,
                (suggestion_id, self.order_id, json.dumps({"cn_name": "AI待确认货物", "quantity": 3}, ensure_ascii=False)),
            )
            conn.commit()
            review = conn.execute("SELECT * FROM review_requests WHERE draft_type = 'goods_line' ORDER BY id DESC").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(review)

        batch_page = self.request("GET", f"/ai-intake?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("批准本类生成草稿", batch_page)
        self.assertIn("已识别货物清单", batch_page)
        self.assertIn("第一条：AI待确认货物", batch_page)
        self.assertIn("同类数据已合并到上方批量处理", batch_page)
        self.assertNotIn("其他草稿", batch_page)
        self.assertNotIn('action="/assistant/review"', batch_page)

        self.request(
            "POST",
            "/assistant/review-group",
            body=urlencode({
                "import_order_id": self.order_id,
                "draft_type": "goods_line",
                "status": REVIEW_APPROVED_FOR_DRAFT,
                "return_to": f"/ai-intake?import_order_id={self.order_id}#assistant-reviews",
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
        draft_page = self.request("GET", f"/ai-intake?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("待确认变更草稿", draft_page)
        self.assertIn("确认本类写入", draft_page)
        self.assertIn("逐项修改", draft_page)
        self.assertIn("确认写入系统", draft_page)
        self.assertIn("货物项草稿", draft_page)
        self.assertIn("同类草稿已合并到上方批量处理", draft_page)
        self.assertIn(f'id="draft-{draft["id"]}"', draft_page)
        self.assertNotIn("<pre>", draft_page)
        self.assertNotIn("管理员最终值 JSON", draft_page)

        self.request(
            "POST",
            "/assistant/draft-group",
            body=urlencode({
                "import_order_id": self.order_id,
                "draft_type": "goods_line",
                "action": "confirm",
                "return_to": f"/ai-intake?import_order_id={self.order_id}#assistant-drafts",
            }),
            cookie=f"session={token}",
        )
        conn = connect(self.db_path)
        try:
            created = conn.execute("SELECT * FROM goods_lines WHERE cn_name = 'AI待确认货物'").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(created)

    def test_ai_intake_no_recognized_data_is_visible_without_approve_action(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        body = urlencode(
            {
                "import_order_id": str(self.order_id),
                "task_template": "file_text_intake",
                "source_text": "这是一份会议纪要，天气很好。",
                "return_to": f"/ai-intake?import_order_id={self.order_id}#ai-intake-workspace",
            }
        )

        response = self.request("POST", "/assistant/run", body=body, cookie=f"session={token}")
        self.assertEqual(response["status"], HTTPStatus.SEE_OTHER)
        assistant_page = self.request("GET", f"/ai-intake?import_order_id={self.order_id}", cookie=f"session={token}")["body"]

        self.assertIn("未识别到有效数据", assistant_page)
        self.assertIn("AI/本地解析没有从本次资料中提取到可录入或需核查的业务数据。", assistant_page)
        self.assertNotIn("批准生成草稿", assistant_page)
        self.assertNotIn("需跟进", assistant_page)

    def test_ai_intake_no_recognized_data_is_collapsed(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        body = {
            "import_order_id": str(self.order_id),
            "task_template": "file_text_intake",
            "source_text": "这是一份会议纪要，天气很好。",
            "return_to": f"/ai-intake?import_order_id={self.order_id}#ai-intake-workspace",
        }
        for _ in range(2):
            self.request("POST", "/assistant/run", body=urlencode(body), cookie=f"session={token}")

        assistant_page = self.request("GET", f"/ai-intake?import_order_id={self.order_id}", cookie=f"session={token}")["body"]

        self.assertEqual(assistant_page.count("<strong>未识别到有效数据"), 1)
        self.assertIn("共 2 次", assistant_page)
        self.assertIn("识别数据录入 <span class=\"count-badge\">1</span>", assistant_page)

    def test_ai_intake_archive_clears_active_counts_to_history(self):
        token = "admin-token"
        SESSIONS[token] = self.admin_id
        self.request(
            "POST",
            "/assistant/run",
            body=urlencode({
                "import_order_id": self.order_id,
                "task_template": "AI检查货物资料",
                "return_to": f"/ai-intake?import_order_id={self.order_id}#assistant-runs",
            }),
            cookie=f"session={token}",
        )
        before = self.request("GET", f"/ai-intake?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("运行记录 <span class=\"count-badge\">1</span>", before)

        response = self.request(
            "POST",
            "/assistant/archive",
            body=urlencode({
                "import_order_id": self.order_id,
                "kind": "runs",
                "return_to": f"/ai-intake?import_order_id={self.order_id}#assistant-runs",
            }),
            cookie=f"session={token}",
        )
        self.assertEqual(response["headers"]["Location"], f"/ai-intake?import_order_id={self.order_id}#assistant-runs")
        after = self.request("GET", f"/ai-intake?import_order_id={self.order_id}", cookie=f"session={token}")["body"]
        self.assertIn("运行记录 <span class=\"count-badge\">0</span>", after)
        self.assertIn("AI资料收集箱历史", after)
        self.assertIn("关闭", after)

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
    file_items = files.items() if isinstance(files, dict) else files
    for item in file_items:
        if len(item) == 2:
            name, (filename, data, content_type) = item
        else:
            name, filename, data, content_type = item
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

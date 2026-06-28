import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from cargopilot.finance import LINE_CHARGE, LINE_COST, add_finance_line
from cargopilot.foundation import ROLE_ADMIN, ROLE_WAREHOUSE, connect, create_user, initialize_database, set_setting
from cargopilot.master_data import create_consignee
from cargopilot.order_assistant import (
    AGENT_COMPLIANCE_RISK,
    AGENT_DOCUMENT_DRAFT,
    AGENT_GOODS_REVIEW,
    AGENT_ORDER_REVIEW,
    AGENT_PROFIT_RISK,
    AGENT_STRUCTURED_INTAKE,
    CHANGE_DRAFT_STATUS_LABELS,
    DRAFT_CONFIRMED,
    LEVEL_BLOCKING_RISK,
    REVIEW_APPROVED_FOR_DRAFT,
    REVIEW_STATUS_LABELS,
    RUN_FAILED,
    RUN_SUCCEEDED,
    SUGGESTION_LEVEL_LABELS,
    Source,
    confirm_change_draft,
    create_assistant_run,
    deepseek_error_message,
    list_order_assistant_items,
    normalize_deepseek_api_base,
    retry_assistant_run,
    route_agents,
    run_assistant,
    set_run_status,
    structured_intake_agent,
    update_review_request_status,
    validate_agent_response,
)
from cargopilot.orders import create_goods_line, create_import_order
from cargopilot.spreadsheet_io import export_rows_xlsx


class OrderAssistantTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_database(self.conn)
        self.admin_id = create_user(
            self.conn,
            email="admin@example.com",
            name="Admin",
            role=ROLE_ADMIN,
            password="admin",
        )
        consignee_id = create_consignee(
            self.conn,
            actor_role=ROLE_ADMIN,
            company_name="Euro Import",
            address="Berlin",
            default_destination_port="Hamburg",
            default_sales_currency="EUR",
        )
        self.order_id = create_import_order(
            self.conn,
            actor_role=ROLE_ADMIN,
            order_no="CP-2026-0001",
            consignee_id=consignee_id,
            destination_port="Hamburg",
            trade_term="FOB",
            expected_loading_date="2026-07-01",
            sales_currency="EUR",
        )
        self.goods_line_id = create_goods_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            cn_name="木制儿童餐具",
            customs_en_name="Wooden Kids Tableware",
            hs_code="441900",
            quantity=10,
            unit="pcs",
            carton_count=2,
            carton_length_cm=40,
            carton_width_cm=30,
            carton_height_cm=20,
            carton_gross_weight_kg=8,
            gross_weight=16,
            volume_cbm=0.048,
            shipping_mark="CP-1",
            sales_unit_price=20,
            sales_currency="EUR",
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_contract_labels_and_required_order_scope(self):
        self.assertEqual(SUGGESTION_LEVEL_LABELS["review-needed"], "需核查")
        self.assertEqual(REVIEW_STATUS_LABELS["pending_review"], "待核查")
        self.assertEqual(CHANGE_DRAFT_STATUS_LABELS["draft"], "待确认草稿")

        run_id = create_assistant_run(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            actor_user_id=self.admin_id,
            task_template="AI检查订单",
        )
        run = self.conn.execute("SELECT * FROM assistant_runs WHERE id = ?", (run_id,)).fetchone()
        self.assertEqual(run["import_order_id"], self.order_id)
        self.assertIn("selected_order_read", run["allowed_tools_json"])

        with self.assertRaises(PermissionError):
            create_assistant_run(
                self.conn,
                actor_role=ROLE_WAREHOUSE,
                import_order_id=self.order_id,
                task_template="AI检查订单",
            )

    def test_agent_response_validation_rejects_bad_shapes_and_forbidden_actions(self):
        validate_agent_response({"suggestions": [], "drafts": [], "reviewNeededFields": [], "usage": {}})
        with self.assertRaises(ValueError):
            validate_agent_response({"suggestions": [], "drafts": [], "usage": {}})
        with self.assertRaises(ValueError):
            validate_agent_response(
                {
                    "suggestions": [
                        {
                            "level": LEVEL_BLOCKING_RISK,
                            "targetType": "import_order",
                            "targetId": self.order_id,
                            "suggestionType": "risk",
                            "title": "bad",
                        }
                    ],
                    "drafts": [],
                    "reviewNeededFields": [],
                    "usage": {},
                }
            )
        with self.assertRaises(ValueError):
            validate_agent_response(
                {
                    "suggestions": [],
                    "drafts": [{"draftType": "supplier", "targetType": "supplier"}],
                    "reviewNeededFields": [],
                    "usage": {},
                }
            )

    def test_router_uses_task_templates_and_source_rules(self):
        self.assertEqual(
            route_agents("AI检查订单"),
            [AGENT_ORDER_REVIEW, AGENT_GOODS_REVIEW, AGENT_COMPLIANCE_RISK],
        )
        agents = route_agents(
            "file_text_intake",
            [
                Source("excel", path="goods.xlsx", name="goods.xlsx"),
                Source("chat", text="报价 amount 100 invoice packing certificate", name="chat"),
            ],
        )
        for agent in [AGENT_STRUCTURED_INTAKE, AGENT_COMPLIANCE_RISK, AGENT_PROFIT_RISK, AGENT_DOCUMENT_DRAFT]:
            self.assertIn(agent, agents)

    def test_structured_intake_extracts_goods_drafts_and_review_needed_fields(self):
        path = self.tmp_path / "goods.xlsx"
        export_rows_xlsx(
            path,
            [
                "产品名称",
                "数量（非包裹数）",
                "箱数量",
                "实际付款",
                "链接",
                "厂家名称",
                "外箱尺寸(cm)",
                "单箱毛重(kg)",
                "CBM",
                "总毛重(kg)",
                "麦头",
                "国内物流单号",
                "货物物流状态",
            ],
            [
                {
                    "产品名称": "提梁四方皮包/6件/绿色",
                    "数量（非包裹数）": 10,
                    "箱数量": 2,
                    "实际付款": 1690,
                    "链接": "https://1688.example/bag",
                    "厂家名称": "宏门工厂",
                    "外箱尺寸(cm)": "47*34*31",
                    "单箱毛重(kg)": 10.2,
                    "CBM": 0.099,
                    "总毛重(kg)": 20.4,
                    "麦头": "CP0626-01",
                    "国内物流单号": "SF202606260002",
                    "货物物流状态": "已揽收",
                },
                {
                    "产品名称": "硅胶led灯灯带",
                    "数量（非包裹数）": "60米",
                    "箱数量": 1,
                    "实际付款": "-",
                    "链接": "https://1688.example/light",
                },
            ],
        )

        output = structured_intake_agent([Source("excel", path=str(path), name=path.name)])
        self.assertEqual(len(output["drafts"]), 2)
        first = output["drafts"][0]["proposedValues"]
        self.assertEqual(first["cn_name"], "提梁四方皮包/6件/绿色")
        self.assertEqual(first["carton_length_cm"], 47)
        self.assertEqual(first["purchase_unit_price"], 169)
        self.assertEqual(output["drafts"][0]["sourceReferences"][0]["row"], 2)
        review_fields = {field["fieldName"] for field in output["reviewNeededFields"]}
        self.assertIn("quantity", review_fields)
        self.assertIn("supplier_name_reference", review_fields)

        self.assertIsNone(self.conn.execute("SELECT * FROM goods_lines WHERE cn_name = '提梁四方皮包/6件/绿色'").fetchone())

    def test_run_assistant_persists_suggestions_reviews_and_drafts(self):
        path = self.tmp_path / "goods.xlsx"
        export_rows_xlsx(
            path,
            [
                "产品名称",
                "数量（非包裹数）",
                "箱数量",
                "实际付款",
                "链接",
                "厂家名称",
                "外箱尺寸(cm)",
                "单箱毛重(kg)",
                "CBM",
                "总毛重(kg)",
                "麦头",
                "国内物流单号",
                "货物物流状态",
            ],
            [{"产品名称": "黑陶侧把茶具套装", "数量（非包裹数）": 5, "箱数量": 1, "实际付款": "-"}],
        )
        run_id = run_assistant(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            actor_user_id=self.admin_id,
            task_template="file_text_intake",
            sources=[Source("excel", path=str(path), name=path.name)],
        )
        run = self.conn.execute("SELECT * FROM assistant_runs WHERE id = ?", (run_id,)).fetchone()
        self.assertEqual(run["status"], RUN_SUCCEEDED)
        items = list_order_assistant_items(self.conn, self.order_id)
        self.assertEqual(len(items["change_drafts"]), 0)
        self.assertGreaterEqual(len(items["review_requests"]), 1)
        self.assertGreaterEqual(len(items["runs"]), 1)
        self.assertEqual(items["review_requests"][0]["import_order_id"], self.order_id)

    def test_compliance_document_and_profit_agents_create_scoped_findings(self):
        run_id = run_assistant(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            task_template="AI检查订单",
            actor_user_id=self.admin_id,
        )
        suggestions = self.conn.execute(
            "SELECT * FROM assistant_suggestions WHERE assistant_run_id = ?",
            (run_id,),
        ).fetchall()
        self.assertTrue(any(row["agent_name"] == AGENT_COMPLIANCE_RISK for row in suggestions))
        self.assertTrue(any("合规" in row["title"] or "文件" in row["title"] for row in suggestions))

        run_id = run_assistant(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            task_template="AI生成单证草稿",
            actor_user_id=self.admin_id,
        )
        drafts = self.conn.execute("SELECT * FROM change_drafts WHERE assistant_run_id = ?", (run_id,)).fetchall()
        self.assertEqual(len(drafts), 0)
        review_candidates = self.conn.execute("SELECT * FROM review_requests WHERE import_order_id = ?", (self.order_id,)).fetchall()
        self.assertTrue(any("commercial_invoice" in row["draft_candidate_json"] for row in review_candidates))

        add_finance_line(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            line_kind=LINE_COST,
            line_type="purchase",
            amount=100,
            currency="EUR",
        )
        run_id = run_assistant(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            task_template="AI检查利润风险",
            actor_user_id=self.admin_id,
        )
        profit_suggestions = self.conn.execute(
            "SELECT * FROM assistant_suggestions WHERE assistant_run_id = ?",
            (run_id,),
        ).fetchall()
        self.assertTrue(any(row["level"] == LEVEL_BLOCKING_RISK for row in profit_suggestions))

    def test_confirm_change_draft_is_required_before_goods_line_write(self):
        path = self.tmp_path / "goods.xlsx"
        export_rows_xlsx(
            path,
            [
                "产品名称",
                "数量（非包裹数）",
                "箱数量",
                "实际付款",
                "链接",
                "厂家名称",
                "外箱尺寸(cm)",
                "单箱毛重(kg)",
                "CBM",
                "总毛重(kg)",
                "麦头",
                "国内物流单号",
                "货物物流状态",
            ],
            [{"产品名称": "待确认货物", "数量（非包裹数）": 3, "箱数量": 1}],
        )
        run_assistant(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            task_template="file_text_intake",
            sources=[Source("excel", path=str(path), name=path.name)],
        )
        draft = self.conn.execute("SELECT * FROM change_drafts WHERE draft_type = 'goods_line' ORDER BY id DESC").fetchone()
        self.assertIsNone(self.conn.execute("SELECT * FROM goods_lines WHERE cn_name = '待确认货物'").fetchone())
        self.assertIsNone(draft)

        review = self.conn.execute(
            "SELECT * FROM review_requests WHERE draft_type = 'goods_line' ORDER BY id DESC"
        ).fetchone()
        change_draft_id = update_review_request_status(
            self.conn,
            actor_role=ROLE_ADMIN,
            review_request_id=review["id"],
            status=REVIEW_APPROVED_FOR_DRAFT,
        )
        draft = self.conn.execute("SELECT * FROM change_drafts WHERE id = ?", (change_draft_id,)).fetchone()

        goods_line_id = confirm_change_draft(self.conn, actor_role=ROLE_ADMIN, change_draft_id=draft["id"])
        created = self.conn.execute("SELECT * FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        updated_draft = self.conn.execute("SELECT * FROM change_drafts WHERE id = ?", (draft["id"],)).fetchone()
        self.assertEqual(created["cn_name"], "待确认货物")
        self.assertEqual(updated_draft["status"], DRAFT_CONFIRMED)

    def test_external_model_requires_confirmation_when_key_is_configured(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret"}):
            run_id = run_assistant(
                self.conn,
                actor_role=ROLE_ADMIN,
                import_order_id=self.order_id,
                task_template="AI检查订单",
                actor_user_id=self.admin_id,
            )
        run = self.conn.execute("SELECT * FROM assistant_runs WHERE id = ?", (run_id,)).fetchone()
        self.assertEqual(run["status"], RUN_FAILED)
        self.assertIn("confirmation", run["error"])

    def test_failed_run_can_be_retried(self):
        run_id = create_assistant_run(
            self.conn,
            actor_role=ROLE_ADMIN,
            import_order_id=self.order_id,
            actor_user_id=self.admin_id,
            task_template="AI检查利润风险",
        )
        set_run_status(self.conn, run_id, RUN_FAILED, error="temporary failure")
        retry_id = retry_assistant_run(self.conn, actor_role=ROLE_ADMIN, run_id=run_id)
        retry = self.conn.execute("SELECT * FROM assistant_runs WHERE id = ?", (retry_id,)).fetchone()
        self.assertEqual(retry["status"], RUN_SUCCEEDED)

    def test_confirmed_deepseek_json_call_persists_usage_and_findings(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "suggestions": [
                                    {
                                        "agentName": AGENT_PROFIT_RISK,
                                        "level": "suggestion",
                                        "targetType": "import_order",
                                        "targetId": self.order_id,
                                        "suggestionType": "model_profit_hint",
                                        "title": "模型利润提示",
                                        "reason": "DeepSeek 返回的结构化建议。",
                                        "sourceReferences": [],
                                    }
                                ],
                                "drafts": [],
                                "reviewNeededFields": [],
                                "usage": {},
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        }
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret", "DEEPSEEK_MODEL": "deepseek-chat"}):
            with patch("cargopilot.order_assistant.request.urlopen", return_value=_DeepSeekResponse(payload)) as mocked:
                run_id = run_assistant(
                    self.conn,
                    actor_role=ROLE_ADMIN,
                    import_order_id=self.order_id,
                    task_template="AI检查利润风险",
                    actor_user_id=self.admin_id,
                    real_data_confirmed=True,
                )

        self.assertTrue(mocked.called)
        run = self.conn.execute("SELECT * FROM assistant_runs WHERE id = ?", (run_id,)).fetchone()
        suggestion = self.conn.execute("SELECT * FROM assistant_suggestions WHERE assistant_run_id = ?", (run_id,)).fetchone()
        usage = self.conn.execute("SELECT * FROM assistant_model_usage WHERE assistant_run_id = ? AND agent_name = ?", (run_id, AGENT_PROFIT_RISK)).fetchone()
        self.assertEqual(run["status"], RUN_SUCCEEDED)
        self.assertEqual(suggestion["title"], "模型利润提示")
        self.assertEqual(usage["model_name"], "deepseek-chat")
        self.assertEqual(usage["input_tokens"], 11)

    def test_deepseek_can_use_local_settings_without_env_key(self):
        set_setting(
            self.conn,
            "deepseek",
            {
                "api_key": "local-secret",
                "model": "deepseek-local",
                "api_base": "https://api.deepseek.com/chat/completions",
                "timeout_seconds": 30,
            },
        )
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "suggestions": [],
                                "drafts": [],
                                "reviewNeededFields": [],
                                "usage": {},
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        with patch.dict("os.environ", {}, clear=True):
            with patch("cargopilot.order_assistant.request.urlopen", return_value=_DeepSeekResponse(payload)):
                run_id = run_assistant(
                    self.conn,
                    actor_role=ROLE_ADMIN,
                    import_order_id=self.order_id,
                    task_template="AI检查利润风险",
                    actor_user_id=self.admin_id,
                    real_data_confirmed=True,
                )
        usage = self.conn.execute("SELECT * FROM assistant_model_usage WHERE assistant_run_id = ? AND agent_name = ?", (run_id, AGENT_PROFIT_RISK)).fetchone()
        self.assertEqual(usage["model_name"], "deepseek-local")

    def test_deepseek_base_url_is_normalized(self):
        self.assertEqual(
            normalize_deepseek_api_base("https://api.deepseek.com"),
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(
            normalize_deepseek_api_base("https://api.deepseek.com/chat/completions"),
            "https://api.deepseek.com/chat/completions",
        )
        self.assertIn(
            "SSL_CERT_FILE",
            deepseek_error_message(Exception("[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain")),
        )

    def test_invalid_deepseek_json_fails_without_partial_suggestions(self):
        payload = {"choices": [{"message": {"content": "not json"}}], "usage": {}}
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret"}):
            with patch("cargopilot.order_assistant.request.urlopen", return_value=_DeepSeekResponse(payload)):
                run_id = run_assistant(
                    self.conn,
                    actor_role=ROLE_ADMIN,
                    import_order_id=self.order_id,
                    task_template="AI检查利润风险",
                    actor_user_id=self.admin_id,
                    real_data_confirmed=True,
                )
        run = self.conn.execute("SELECT * FROM assistant_runs WHERE id = ?", (run_id,)).fetchone()
        suggestions = self.conn.execute("SELECT * FROM assistant_suggestions WHERE assistant_run_id = ?", (run_id,)).fetchall()
        self.assertEqual(run["status"], RUN_FAILED)
        self.assertEqual(suggestions, [])


class _DeepSeekResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


if __name__ == "__main__":
    unittest.main()

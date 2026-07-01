from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import date
from pathlib import Path
import html
import json
import os
import shutil
import secrets
import sqlite3
from urllib.parse import parse_qs, quote, urlparse

from .containers import CONTAINER_ORDER, create_container, export_loading_list, loading_list, recommend_container, record_loading
from .calculations import STAGE_FINAL_DOCUMENTS, calculate_cbm, calculate_gross_weight, check_goods_line_stage
from .dashboard import ORDER_STATUS_COLORS, dashboard_orders, global_search, goods_line_tracking, reminders
from .documents import (
    DOC_COMMERCIAL_INVOICE,
    DOC_PACKING_LIST,
    DOCUMENT_TYPES,
    DocumentBlockedError,
    generate_export_document,
)
from .finance import (
    CHARGE_TYPES,
    COST_TYPES,
    LINE_CHARGE,
    LINE_COST,
    add_finance_line,
    calculate_profit,
    delete_finance_line,
    update_finance_line,
)
from .foundation import ROLE_ADMIN, ROLE_WAREHOUSE, authenticate, connect, create_user, get_setting, initialize_database, record_audit_log, record_file_metadata, set_setting, utc_now
from .master_data import (
    WAREHOUSE_PORT,
    WAREHOUSE_RECEIVING,
    create_consignee,
    create_supplier,
    create_warehouse,
    list_suppliers,
    list_warehouses,
    update_consignee,
    update_supplier,
    update_warehouse,
)
from .orders import (
    GOODS_LINE_FIELD_GROUPS,
    IMPORT_ORDER_DETAIL_TABS,
    create_goods_line,
    create_import_order,
    update_import_order,
    update_goods_line,
)
from .order_assistant import (
    CHANGE_DRAFT_STATUS_LABELS,
    REVIEW_APPROVED_FOR_DRAFT,
    REVIEW_IGNORED,
    REVIEW_PENDING,
    REVIEW_STATUS_LABELS,
    RUN_STATUS_LABELS,
    SUGGESTION_LEVEL_LABELS,
    TASK_CHECK_DOC_BLOCKERS,
    TASK_CHECK_GOODS,
    TASK_CHECK_ORDER,
    TASK_CHECK_PROFIT,
    TASK_DRAFT_DOCS,
    TASK_FILE_TEXT_INTAKE,
    Source,
    archive_assistant_items,
    confirm_change_draft,
    is_order_command_text,
    list_order_assistant_items,
    normalize_deepseek_api_base,
    reject_change_draft,
    retry_assistant_run,
    run_assistant,
    test_deepseek_connection,
    update_change_draft_group_status,
    update_review_request_group_status,
    update_review_request_status,
)
from .receiving import ARRIVAL_EXCEPTION_TYPES, record_receiving, resolve_arrival_exception, search_receiving
from .spreadsheet_io import (
    ImportResult,
    export_goods_lines,
    export_import_orders,
    export_rows_xlsx,
    import_customer_purchase_list,
    import_finance_cost_upload,
    import_order_goods_upload,
    import_supplier_package_logistics,
)

APP_DB = Path("data/cargopilot.sqlite3")
SESSIONS: dict[str, int] = {}
# ponytail: local dev server state; pass request context explicitly if concurrent users matter.
CURRENT_PATH = "/dashboard"


@dataclass
class UploadedFile:
    filename: str
    content_type: str
    data: bytes


GOODS_LOGISTICS_STATUSES = [
    "not_ordered",
    "ordered",
    "domestic_shipped",
    "received_at_warehouse",
    "moved_to_port_warehouse",
    "loaded",
    "at_sea",
    "exception",
]
FIELD_LABELS = {
    "supplier_id": "供应商",
    "customer_item_no": "客户货号",
    "product_url": "1688/商品链接",
    "cn_name": "中文品名",
    "en_name": "客户英文品名",
    "customs_en_name": "报关英文品名",
    "sku_or_model": "SKU/型号",
    "category": "品类",
    "hs_code": "HS Code",
    "quantity": "数量",
    "unit": "单位",
    "packaging_method": "包装方式",
    "target_markup": "目标加价率",
    "target_margin": "目标利润率",
    "sales_unit_price": "销售单价",
    "sales_currency": "销售币种",
    "purchase_unit_price": "采购单价",
    "purchase_currency": "采购币种",
    "carton_count": "箱数",
    "units_per_carton": "每箱数量",
    "carton_length_cm": "外箱长(cm)",
    "carton_width_cm": "外箱宽(cm)",
    "carton_height_cm": "外箱高(cm)",
    "carton_gross_weight_kg": "单箱毛重(kg)",
    "gross_weight": "总毛重(kg)",
    "volume_cbm": "总体积 CBM",
    "shipping_mark": "麦头",
    "logistics_status": "货物物流状态",
    "compliance_status": "质检/合规状态",
    "consignee_document_information": "收货客户单证信息",
    "notes": "备注",
    "order_no": "订单号",
    "destination_port": "目的港",
    "trade_term": "贸易条款",
    "order_status": "订单状态",
    "expected_loading_date": "预计装柜日",
    "internal_notes": "订单备注",
}
FIELD_GROUP_LABELS = {
    "basic": "基本信息",
    "pricing": "报价利润",
    "packaging": "包装尺寸",
    "logistics": "物流状态",
    "compliance": "报关与质检",
}
ORDER_STATUS_LABELS = {
    "draft": "草稿",
    "purchasing": "采购中",
    "receiving": "收货中",
    "received": "已到仓",
    "moving_to_port": "转运港仓",
    "at_port_warehouse": "已入港仓",
    "loaded": "已装箱",
    "at_sea": "海运中",
    "arrived": "已到港",
    "completed": "已完成",
    "cancelled": "已取消",
}
LOGISTICS_POINT_LABELS = {
    "empty": "暂无货物",
    "exception": "异常",
    "supplier_side": "供应商处",
    "receiving_warehouse": "收货仓库",
    "port_warehouse": "港口仓库",
    "loaded": "已装箱",
    "at_sea": "海运中",
}
LOGISTICS_STATUS_LABELS = {
    "not_ordered": "未下单",
    "ordered": "已下单/备货中",
    "supplier_preparing": "已下单/备货中",
    "domestic_shipped": "国内运输中",
    "received_at_warehouse": "已到收货仓",
    "checked": "已到收货仓",
    "moved_to_port_warehouse": "已入港仓",
    "loaded": "已装箱",
    "at_sea": "海运中",
    "exception": "异常",
}
COMPLIANCE_STATUS_LABELS = {
    "not_required": "不需要",
    "required": "需要",
    "pending": "待处理",
    "approved": "已通过",
    "rejected": "未通过",
}
WAREHOUSE_TYPE_LABELS = {
    WAREHOUSE_RECEIVING: "收货仓库",
    WAREHOUSE_PORT: "港口仓库",
}
COMPLIANCE_FILE_CATEGORIES = {
    "certificate_origin": "产地证",
    "inspection_certificate": "检验证书",
    "quarantine": "防疫/检疫文件",
    "other_compliance": "其他合规文件",
}
ORDER_AGENT_STATUS_LABELS = {
    "draft": "草稿中",
    "waiting_for_input": "待补充",
    "draft_ready": "已生成草稿",
    "closed": "已关闭",
}


def ensure_database(path: Path | None = None) -> sqlite3.Connection:
    path = path or APP_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    initialize_database(conn)
    _ensure_demo_users(conn)
    return conn


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), CargoPilotHandler)
    print(f"CargoPilot running at http://{host}:{port}")
    server.serve_forever()


class CargoPilotHandler(BaseHTTPRequestHandler):
    server_version = "CargoPilot/0.1"

    def do_GET(self) -> None:
        global CURRENT_PATH
        parsed = urlparse(self.path)
        CURRENT_PATH = parsed.path
        if parsed.path == "/static/app.css":
            self._send(HTTPStatus.OK, CSS, "text/css; charset=utf-8")
            return
        if parsed.path == "/login":
            self._send(HTTPStatus.OK, login_page(), "text/html; charset=utf-8")
            return
        user = self._current_user()
        if user is None:
            self._redirect("/login")
            return
        if parsed.path in {"/", "/dashboard"}:
            self._send(HTTPStatus.OK, dashboard_page(user, parse_qs(parsed.query)), "text/html; charset=utf-8")
            return
        if parsed.path == "/tracking":
            self._send(HTTPStatus.OK, tracking_page(user, parse_qs(parsed.query)), "text/html; charset=utf-8")
            return
        if parsed.path == "/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            self._send(HTTPStatus.OK, search_page(user, query), "text/html; charset=utf-8")
            return
        if parsed.path == "/orders":
            self._send(HTTPStatus.OK, orders_page(user, parse_qs(parsed.query)), "text/html; charset=utf-8")
            return
        if parsed.path == "/receiving":
            self._send(HTTPStatus.OK, receiving_page(user, parse_qs(parsed.query)), "text/html; charset=utf-8")
            return
        if parsed.path == "/basic-data":
            self._admin_page(user, lambda admin: basic_data_page(admin, parse_qs(parsed.query)))
            return
        if parsed.path == "/order-agent":
            self._admin_page(user, lambda admin: order_agent_page(admin, parse_qs(parsed.query)))
            return
        if parsed.path == "/ai-intake":
            self._admin_page(user, lambda admin: ai_intake_page(admin, parse_qs(parsed.query)))
            return
        order_id = path_id(parsed.path, "/orders/")
        if order_id is not None:
            self._send(HTTPStatus.OK, order_detail_page(user, order_id), "text/html; charset=utf-8")
            return
        goods_line_edit_id = edit_path_id(parsed.path, "/goods-lines/")
        if goods_line_edit_id is not None:
            self._send(HTTPStatus.OK, goods_line_edit_page(user, goods_line_edit_id), "text/html; charset=utf-8")
            return
        if parsed.path in {"/suppliers", "/consignees", "/warehouses", "/settings"}:
            self._redirect("/basic-data")
            return
        if parsed.path == "/excel-finance":
            self._admin_page(user, lambda admin: excel_finance_page(admin, parse_qs(parsed.query)))
            return
        if parsed.path == "/shipping-docs":
            self._admin_page(user, lambda admin: shipping_docs_page(admin, parse_qs(parsed.query)))
            return
        document_download = document_download_path(parsed.path)
        if document_download is not None:
            self._admin_document_download(user, *document_download)
            return
        if parsed.path == "/exports/loading-list.xlsx":
            self._admin_loading_list_export(user, parse_qs(parsed.query))
            return
        if parsed.path in {"/exports/import-orders.xlsx", "/exports/goods-lines.xlsx", "/exports/finance-lines.xlsx"}:
            self._admin_export(user, parsed.path)
            return
        if parsed.path == "/logout":
            self._logout()
            return
        self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        form = form_data(self.rfile.read(length), self.headers.get("Content-Type", ""))
        if parsed.path != "/login":
            user = self._current_user()
            if user is None:
                self._redirect("/login")
                return
            if parsed.path == "/receiving/record":
                handle_receiving_record_post(form, user)
                self._redirect(receiving_redirect(form))
                return
            if parsed.path == "/receiving/resolve":
                handle_receiving_resolve_post(form, user)
                self._redirect(receiving_redirect(form))
                return
            if parsed.path == "/tracking/status":
                handle_tracking_status_post(form, user)
                if form.get("return_to", "").startswith("/") and not form.get("return_to", "").startswith("//"):
                    self._redirect(form["return_to"])
                    return
                suffix = f"?import_order_id={form.get('import_order_id', '')}" if form.get("import_order_id") else ""
                self._redirect(f"/tracking{suffix}")
                return
            if user["role"] != ROLE_ADMIN:
                self._send(HTTPStatus.FORBIDDEN, page("Forbidden", "<section class='panel pad'>无权访问</section>", user=user), "text/html; charset=utf-8")
                return
            if parsed.path == "/order-agent/conversations":
                conversation_id = handle_order_agent_conversation_post(form, user)
                self._redirect(f"/order-agent?conversation_id={conversation_id}")
                return
            order_agent_message_id = suffix_path_id(parsed.path, "/order-agent/conversations/", "/messages")
            if order_agent_message_id is not None:
                handle_order_agent_message_post(order_agent_message_id, form, user)
                self._redirect(f"/order-agent?conversation_id={order_agent_message_id}")
                return
            order_agent_close_id = suffix_path_id(parsed.path, "/order-agent/conversations/", "/close")
            if order_agent_close_id is not None:
                handle_order_agent_close_post(order_agent_close_id, user)
                self._redirect(f"/order-agent?conversation_id={order_agent_close_id}")
                return
            if parsed.path == "/assistant/run":
                handle_assistant_run_post(form, user)
                self._redirect(safe_local_path(form.get("return_to", "")) or f"/orders?order_id={form.get('import_order_id', '')}")
                return
            if parsed.path == "/assistant/review":
                handle_assistant_review_post(form)
                self._redirect(safe_local_path(form.get("return_to", "")) or "/orders")
                return
            if parsed.path == "/assistant/archive":
                handle_assistant_archive_post(form)
                self._redirect(safe_local_path(form.get("return_to", "")) or "/orders")
                return
            if parsed.path == "/assistant/review-group":
                handle_assistant_review_group_post(form)
                self._redirect(safe_local_path(form.get("return_to", "")) or "/orders")
                return
            if parsed.path == "/assistant/draft-group":
                handle_assistant_draft_group_post(form)
                self._redirect(safe_local_path(form.get("return_to", "")) or "/orders")
                return
            retry_run_id = suffix_path_id(parsed.path, "/assistant/runs/", "/retry")
            if retry_run_id is not None:
                handle_assistant_run_retry_post(retry_run_id, form)
                self._redirect(safe_local_path(form.get("return_to", "")) or "/orders")
                return
            draft_confirm_id = suffix_path_id(parsed.path, "/assistant/drafts/", "/confirm")
            if draft_confirm_id is not None:
                handle_assistant_draft_confirm_post(draft_confirm_id, form)
                self._redirect(safe_local_path(form.get("return_to", "")) or "/orders")
                return
            draft_reject_id = suffix_path_id(parsed.path, "/assistant/drafts/", "/reject")
            if draft_reject_id is not None:
                handle_assistant_draft_reject_post(draft_reject_id)
                self._redirect(safe_local_path(form.get("return_to", "")) or "/orders")
                return
            if parsed.path == "/suppliers":
                handle_supplier_post(form)
                self._redirect("/basic-data#suppliers")
                return
            if parsed.path == "/consignees":
                handle_consignee_post(form)
                self._redirect("/basic-data#consignees")
                return
            if parsed.path == "/warehouses":
                handle_warehouse_post(form)
                self._redirect("/basic-data#warehouses")
                return
            if parsed.path == "/basic-data/suppliers":
                handle_supplier_post(form)
                self._redirect("/basic-data#suppliers")
                return
            supplier_edit_id = suffix_path_id(parsed.path, "/basic-data/suppliers/", "/edit")
            if supplier_edit_id is not None:
                handle_supplier_edit_post(form, supplier_edit_id)
                self._redirect("/basic-data#suppliers")
                return
            supplier_delete_id = suffix_path_id(parsed.path, "/basic-data/suppliers/", "/delete")
            if supplier_delete_id is not None:
                error = handle_supplier_delete_post(supplier_delete_id)
                if error:
                    self._send(HTTPStatus.OK, basic_data_page(user, {}, errors=[error]), "text/html; charset=utf-8")
                    return
                self._redirect("/basic-data#suppliers")
                return
            if parsed.path == "/basic-data/consignees":
                handle_consignee_post(form)
                self._redirect("/basic-data#consignees")
                return
            consignee_edit_id = suffix_path_id(parsed.path, "/basic-data/consignees/", "/edit")
            if consignee_edit_id is not None:
                handle_consignee_edit_post(form, consignee_edit_id)
                self._redirect("/basic-data#consignees")
                return
            consignee_delete_id = suffix_path_id(parsed.path, "/basic-data/consignees/", "/delete")
            if consignee_delete_id is not None:
                error = handle_consignee_delete_post(consignee_delete_id)
                if error:
                    self._send(HTTPStatus.OK, basic_data_page(user, {}, errors=[error]), "text/html; charset=utf-8")
                    return
                self._redirect("/basic-data#consignees")
                return
            if parsed.path == "/basic-data/warehouses":
                handle_warehouse_post(form)
                self._redirect("/basic-data#warehouses")
                return
            warehouse_edit_id = suffix_path_id(parsed.path, "/basic-data/warehouses/", "/edit")
            if warehouse_edit_id is not None:
                handle_warehouse_edit_post(form, warehouse_edit_id)
                self._redirect("/basic-data#warehouses")
                return
            warehouse_delete_id = suffix_path_id(parsed.path, "/basic-data/warehouses/", "/delete")
            if warehouse_delete_id is not None:
                error = handle_warehouse_delete_post(warehouse_delete_id)
                if error:
                    self._send(HTTPStatus.OK, basic_data_page(user, {}, errors=[error]), "text/html; charset=utf-8")
                    return
                self._redirect("/basic-data#warehouses")
                return
            if parsed.path == "/basic-data/settings":
                handle_settings_post(form)
                self._redirect("/basic-data#company")
                return
            if parsed.path == "/basic-data/llm-settings":
                handle_llm_settings_post(form)
                self._redirect("/basic-data#llm")
                return
            if parsed.path == "/receiving/warehouses":
                warehouse_id = handle_receiving_warehouse_post(form)
                self._redirect(f"/receiving?warehouse_id={warehouse_id}")
                return
            receiving_warehouse_edit_id = suffix_path_id(parsed.path, "/receiving/warehouses/", "/edit")
            if receiving_warehouse_edit_id is not None:
                handle_receiving_warehouse_edit_post(form, receiving_warehouse_edit_id)
                self._redirect(f"/receiving?warehouse_id={receiving_warehouse_edit_id}")
                return
            receiving_warehouse_delete_id = suffix_path_id(parsed.path, "/receiving/warehouses/", "/delete")
            if receiving_warehouse_delete_id is not None:
                error = handle_receiving_warehouse_delete_post(receiving_warehouse_delete_id)
                if error:
                    query = {"warehouse_id": [str(receiving_warehouse_delete_id)]}
                    self._send(HTTPStatus.OK, receiving_page(user, query, errors=[error]), "text/html; charset=utf-8")
                    return
                self._redirect("/receiving")
                return
            if parsed.path == "/settings":
                handle_settings_post(form)
                self._redirect("/basic-data#company")
                return
            if parsed.path == "/excel/customer-import":
                result = handle_customer_import_post(form)
                self._send(HTTPStatus.OK, excel_finance_page(user, {}, "客户采购清单导入完成", result.errors), "text/html; charset=utf-8")
                return
            if parsed.path == "/excel/package-import":
                result = handle_package_import_post(form)
                self._send(HTTPStatus.OK, excel_finance_page(user, {}, "供应商包装物流导入完成", result.errors), "text/html; charset=utf-8")
                return
            if parsed.path == "/finance/line":
                handle_finance_line_post(form)
                self._redirect(finance_redirect(form))
                return
            if parsed.path == "/finance/cost-import":
                result = handle_finance_cost_import_post(form)
                query = {"import_order_id": [form.get("import_order_id", "")]}
                message = f"已导入 {result.created} 条成本"
                self._send(HTTPStatus.OK, excel_finance_page(user, query, message, result.errors), "text/html; charset=utf-8")
                return
            finance_line_edit_id = suffix_path_id(parsed.path, "/finance-lines/", "/edit")
            if finance_line_edit_id is not None:
                order_id = handle_finance_line_edit_post(form, finance_line_edit_id)
                self._redirect(f"/excel-finance?import_order_id={order_id}")
                return
            finance_line_delete_id = suffix_path_id(parsed.path, "/finance-lines/", "/delete")
            if finance_line_delete_id is not None:
                order_id = handle_finance_line_delete_post(finance_line_delete_id)
                self._redirect(f"/excel-finance?import_order_id={order_id}")
                return
            if parsed.path == "/containers":
                handle_container_post(form)
                self._redirect(shipping_docs_redirect(form))
                return
            if parsed.path == "/loading-records":
                handle_loading_record_post(form, user)
                self._redirect(shipping_docs_redirect(form))
                return
            if parsed.path == "/compliance-files":
                handle_compliance_file_post(form, user)
                self._redirect(shipping_docs_redirect(form))
                return
            if parsed.path == "/documents/generate":
                message, blockers = handle_document_generate_post(form)
                query = {"import_order_id": [form.get("import_order_id", "")]}
                self._send(HTTPStatus.OK, shipping_docs_page(user, query, message, blockers), "text/html; charset=utf-8")
                return
            if parsed.path == "/orders":
                order_id = handle_order_post(form)
                self._redirect(f"/orders?order_id={order_id}")
                return
            if parsed.path == "/orders/consignees":
                handle_order_consignee_post(form)
                self._redirect(order_return_path(form))
                return
            if parsed.path == "/orders/status":
                handle_order_status_post(form, user)
                self._redirect(f"/orders?order_id={form.get('order_id', '')}")
                return
            order_edit_id = suffix_path_id(parsed.path, "/orders/", "/edit")
            if order_edit_id is not None:
                handle_order_edit_post(form, order_edit_id)
                self._redirect(f"/orders?order_id={order_edit_id}")
                return
            order_cancel_id = suffix_path_id(parsed.path, "/orders/", "/cancel")
            if order_cancel_id is not None:
                handle_order_cancel_post(order_cancel_id)
                self._redirect(f"/orders?order_id={order_cancel_id}")
                return
            consignee_edit_id = suffix_path_id(parsed.path, "/orders/consignees/", "/edit")
            if consignee_edit_id is not None:
                handle_order_consignee_edit_post(form, consignee_edit_id)
                self._redirect(order_return_path(form))
                return
            consignee_delete_id = suffix_path_id(parsed.path, "/orders/consignees/", "/delete")
            if consignee_delete_id is not None:
                error = handle_order_consignee_delete_post(consignee_delete_id)
                if error:
                    query = {"order_id": [form.get("return_order_id", "")]}
                    self._send(HTTPStatus.OK, orders_page(user, query, errors=[error]), "text/html; charset=utf-8")
                    return
                self._redirect(order_return_path(form))
                return
            order_goods_import_id = suffix_path_id(parsed.path, "/orders/", "/goods-lines/import")
            if order_goods_import_id is not None:
                result = handle_order_goods_import_post(form, order_goods_import_id)
                message = f"已导入 {result.created} 个货物项"
                if safe_local_path(form.get("return_to", "")).startswith("/tracking"):
                    query = {"import_order_id": [str(order_goods_import_id)]}
                    self._send(HTTPStatus.OK, tracking_page(user, query, message, result.errors), "text/html; charset=utf-8")
                    return
                query = {"order_id": [str(order_goods_import_id)]}
                self._send(HTTPStatus.OK, orders_page(user, query, message, result.errors), "text/html; charset=utf-8")
                return
            order_goods_id = suffix_path_id(parsed.path, "/orders/", "/goods-lines")
            if order_goods_id is not None:
                handle_goods_line_post(form, order_goods_id)
                self._redirect(safe_local_path(form.get("return_to", "")) or f"/orders?order_id={order_goods_id}")
                return
            goods_line_delete_id = suffix_path_id(parsed.path, "/goods-lines/", "/delete")
            if goods_line_delete_id is not None:
                order_id = handle_goods_line_delete_post(goods_line_delete_id, user)
                self._redirect(f"/tracking?import_order_id={order_id}")
                return
            goods_line_edit_id = edit_path_id(parsed.path, "/goods-lines/")
            if goods_line_edit_id is not None:
                order_id = handle_goods_line_edit_post(form, goods_line_edit_id)
                self._redirect(f"/tracking?import_order_id={order_id}")
                return
            self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain; charset=utf-8")
            return
        conn = ensure_database()
        try:
            user = authenticate(conn, form.get("email", ""), form.get("password", ""))
        finally:
            conn.close()
        if user is None:
            self._send(HTTPStatus.UNAUTHORIZED, login_page("邮箱或密码错误"), "text/html; charset=utf-8")
            return
        token = secrets.token_urlsafe(24)
        SESSIONS[token] = int(user["id"])
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/dashboard")
        self.send_header("Set-Cookie", f"session={token}; HttpOnly; SameSite=Lax; Path=/")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        return

    def _current_user(self):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        token = cookie.get("session")
        if token is None or token.value not in SESSIONS:
            return None
        conn = ensure_database()
        try:
            return conn.execute("SELECT * FROM users WHERE id = ?", (SESSIONS[token.value],)).fetchone()
        finally:
            conn.close()

    def _logout(self) -> None:
        cookie = SimpleCookie(self.headers.get("Cookie"))
        token = cookie.get("session")
        if token is not None:
            SESSIONS.pop(token.value, None)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/login")
        self.send_header("Set-Cookie", "session=; Max-Age=0; Path=/")
        self.end_headers()

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _send(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _admin_page(self, user: sqlite3.Row, renderer) -> None:
        if user["role"] != ROLE_ADMIN:
            self._send(HTTPStatus.FORBIDDEN, page("Forbidden", "<section class='panel pad'>无权访问</section>", user=user), "text/html; charset=utf-8")
            return
        self._send(HTTPStatus.OK, renderer(user), "text/html; charset=utf-8")

    def _admin_export(self, user: sqlite3.Row, path: str) -> None:
        if user["role"] != ROLE_ADMIN:
            self._send(HTTPStatus.FORBIDDEN, page("Forbidden", "<section class='panel pad'>无权访问</section>", user=user), "text/html; charset=utf-8")
            return
        export_path = APP_DB.parent / "exports" / Path(path).name
        conn = ensure_database()
        try:
            if path == "/exports/import-orders.xlsx":
                export_import_orders(conn, export_path)
            elif path == "/exports/goods-lines.xlsx":
                export_goods_lines(conn, export_path)
            else:
                rows = [dict(row) for row in conn.execute("SELECT * FROM finance_lines ORDER BY created_at DESC")]
                headers = list(rows[0]) if rows else ["id", "import_order_id", "goods_line_id", "line_kind", "line_type", "amount", "currency"]
                export_rows_xlsx(export_path, headers, rows)
        finally:
            conn.close()
        self._send_bytes(HTTPStatus.OK, export_path.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def _admin_loading_list_export(self, user: sqlite3.Row, query: dict[str, list[str]]) -> None:
        if user["role"] != ROLE_ADMIN:
            self._send(HTTPStatus.FORBIDDEN, page("Forbidden", "<section class='panel pad'>无权访问</section>", user=user), "text/html; charset=utf-8")
            return
        import_order_id = int_or_none(query.get("import_order_id", [""])[0])
        if import_order_id is None:
            self._send(HTTPStatus.BAD_REQUEST, "missing import_order_id", "text/plain; charset=utf-8")
            return
        export_path = APP_DB.parent / "exports" / f"loading-list-{import_order_id}.xlsx"
        conn = ensure_database()
        try:
            export_loading_list(conn, import_order_id, export_path)
        finally:
            conn.close()
        self._send_bytes(HTTPStatus.OK, export_path.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def _admin_document_download(self, user: sqlite3.Row, document_id: int, file_type: str) -> None:
        if user["role"] != ROLE_ADMIN:
            self._send(HTTPStatus.FORBIDDEN, page("Forbidden", "<section class='panel pad'>无权访问</section>", user=user), "text/html; charset=utf-8")
            return
        conn = ensure_database()
        try:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain; charset=utf-8")
            return
        path = Path(row["xlsx_path"] if file_type == "xlsx" else row["pdf_path"])
        if not path.exists():
            self._send(HTTPStatus.NOT_FOUND, "File not found", "text/plain; charset=utf-8")
            return
        content_type = "application/pdf" if file_type == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        self._send_bytes(HTTPStatus.OK, path.read_bytes(), content_type)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def login_page(error: str = "") -> str:
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return page(
        "登录",
        f"""
        <main class="login">
          <section class="login-card">
            <div>
              <h1>CargoPilot</h1>
              <p>货运领航进口订单管理</p>
            </div>
            {error_html}
            <form method="post" action="/login">
              <label>邮箱<input name="email" type="email" value="admin@example.com" required></label>
              <label>密码<input name="password" type="password" value="admin" required></label>
              <button type="submit">登录</button>
            </form>
            <p class="hint">演示账号：admin@example.com / admin，warehouse@example.com / warehouse</p>
          </section>
        </main>
        """,
        chrome=False,
    )


def dashboard_page(user: sqlite3.Row, query: dict[str, list[str]] | None = None) -> str:
    query = query or {}
    status = query.get("status", [""])[0] or None
    conn = ensure_database()
    try:
        cards = dashboard_orders(conn, status=status)
        reminder_rows = reminders(conn)
    finally:
        conn.close()
    rows = "\n".join(_order_row(card) for card in cards) or '<tr><td colspan="9" class="empty">暂无订单</td></tr>'
    status_options = "<option value=''>全部状态</option>" + "".join(
        f"<option value='{esc(value)}'{' selected' if value == status else ''}>{esc(order_status_label(value))}</option>"
        for value in ORDER_STATUS_COLORS
    )
    reminder_html = "".join(
        f"<li><a href='{reminder_href(item)}'>{esc(item['message'])}</a></li>"
        for item in reminder_rows[:8]
    ) or "<li>暂无提醒</li>"
    return page(
        "Dashboard",
        f"""
        <section class="toolbar">
          <div>
            <h1>Dashboard</h1>
            <p>当前订单、异常和缺失资料</p>
          </div>
          <form class="search" method="get" action="/search"><input name="q" aria-label="搜索" placeholder="搜索订单、客户、物流单号、麦头"><button type="submit">查询</button></form>
        </section>
        <section class="dashboard-overview">
          <div class="metric-grid">
            <a href="/orders"><article><strong>{len(cards)}</strong><span>活跃订单</span></article></a>
            <a href="/tracking?exception_only=1"><article><strong>{sum(card['exception_count'] for card in cards)}</strong><span>异常</span></article></a>
            <a href="/orders"><article><strong>{sum(card['missing_data_count'] for card in cards)}</strong><span>缺失资料</span></article></a>
          </div>
          <section class="panel pad reminders-panel"><h2>提醒事项</h2><ul class="reminder-list">{reminder_html}</ul></section>
        </section>
        <section class="panel pad filter-panel">
          <form method="get" action="/dashboard" class="filter-bar">
            <label>订单状态<select name="status" onchange="this.form.submit()">{status_options}</select></label>
          </form>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>出口订单</h2><span>{html.escape(role_label(user['role']))}</span></div>
          <table>
            <thead>
              <tr><th>订单号</th><th>客户</th><th>目的港</th><th>状态</th><th>当前聚集点</th><th>进度</th><th>预计装柜</th><th>异常</th><th>缺失</th></tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
        """,
        user=user,
    )


def tracking_page(user: sqlite3.Row, query: dict[str, list[str]] | None = None, message: str = "", errors: list[str] | None = None) -> str:
    query = query or {}
    status = query.get("status", [""])[0] or None
    import_order_id = int_or_none(query.get("import_order_id", [""])[0])
    exception_only = query.get("exception_only", [""])[0] == "1"
    conn = ensure_database()
    try:
        orders = conn.execute("SELECT id, order_no FROM import_orders ORDER BY created_at DESC").fetchall()
        if import_order_id is None and orders and not exception_only:
            import_order_id = int(orders[0]["id"])
        suppliers = list_suppliers(conn)
        rows_data = goods_line_tracking(
            conn,
            status=status,
            import_order_id=import_order_id,
            exception_only=exception_only,
        )
        rows_data = enrich_tracking_rows(conn, rows_data)
        if import_order_id is None and status is None and not exception_only:
            rows_data = [row for row in rows_data if row["is_problem"]]
    finally:
        conn.close()
    order_options = "".join(
        f"<option value='{order['id']}'{' selected' if import_order_id == order['id'] else ''}>{esc(order['order_no'])}</option>"
        for order in orders
    )
    status_options = "<option value=''>全部状态</option>" + "".join(
        f"<option value='{esc(value)}'{' selected' if value == status else ''}>{esc(logistics_status_label(value))}</option>"
        for value in GOODS_LOGISTICS_STATUSES
    )
    return_to = f"/tracking?import_order_id={import_order_id}" if import_order_id else "/tracking"
    rows = "".join(tracking_row(row, user, return_to) for row in rows_data) or '<tr><td colspan="19" class="empty">暂无匹配货物项</td></tr>'
    actions = ""
    if user["role"] == ROLE_ADMIN and import_order_id is not None:
        actions = f"""
        <div class="action-row">
          {compact_goods_line_drawer(import_order_id, suppliers, return_to)}
          {ai_intake_link(import_order_id, "AI检查货物资料")}
        </div>
        """
    notice = f"<p class='notice'>{esc(message)}</p>" if message else ""
    error_html = "".join(f"<li>{esc(error)}</li>" for error in (errors or []))
    errors_block = f"<section class='panel pad'><h2>导入错误</h2><ul class='errors'>{error_html}</ul></section>" if error_html else ""
    return page(
        "货物详情",
        f"""
        <section class="toolbar"><div><h1>货物详情</h1><p>按订单查看和维护货物资料、供应商和物流状态</p></div>{actions}</section>
        {notice}
        {errors_block}
        <section class="panel pad">
          <form method="get" action="/tracking" class="filter-bar">
            <label>进口订单<select name="import_order_id" onchange="this.form.submit()">{order_options}</select></label>
            <label>货物物流状态<select name="status" onchange="this.form.submit()">{status_options}</select></label>
          </form>
        </section>
        <section class="panel table-scroll tracking-scroll"><table><thead><tr><th>货物项</th><th>供应商</th><th>SKU/型号</th><th>数量</th><th>箱数</th><th>每箱数量</th><th>外箱尺寸(cm)</th><th>单箱毛重(kg)</th><th>CBM</th><th>总毛重(kg)</th><th>采购单价</th><th>采购币种</th><th>目标加价率</th><th>销售单价</th><th>销售币种</th><th>麦头</th><th>国内物流单号</th><th>货物物流状态</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table></section>
        """,
        user=user,
    )


def enrich_tracking_rows(conn: sqlite3.Connection, rows: list[dict]) -> list[dict]:
    output = []
    for row in rows:
        tracking_numbers = conn.execute(
            "SELECT tracking_no FROM domestic_tracking_numbers WHERE goods_line_id = ? ORDER BY id",
            (row["id"],),
        ).fetchall()
        missing = check_goods_line_stage(conn, goods_line_id=row["id"], stage=STAGE_FINAL_DOCUMENTS).blocked
        delayed = is_delay_risk(conn, row, missing)
        output.append({
            **row,
            "tracking_numbers": ", ".join(item["tracking_no"] for item in tracking_numbers),
            "is_missing": missing,
            "is_delayed": delayed,
            "is_exception": row["logistics_status"] == "exception",
            "is_problem": delayed or row["logistics_status"] == "exception",
        })
    return output


def is_delay_risk(conn: sqlite3.Connection, row: dict, missing: bool) -> bool:
    if not row.get("expected_loading_date"):
        return False
    lead_days = int(get_setting(conn, "reminders").get("lead_days", 3))
    days = (date.fromisoformat(row["expected_loading_date"]) - date.today()).days
    not_received = row["logistics_status"] in {"not_ordered", "ordered", "supplier_preparing", "domestic_shipped"}
    return 0 <= days <= lead_days and (not_received or missing or row["logistics_status"] == "exception")


def tracking_row(row: dict, user: sqlite3.Row, return_to: str) -> str:
    delete = ""
    if user["role"] == ROLE_ADMIN:
        delete = f"""
        <form method="post" action="/goods-lines/{row['id']}/delete" class="icon-form">
          <button class="icon-button danger" type="submit" title="删除货物项" aria-label="删除货物项" onclick="return confirm('删除这个货物项？')">×</button>
        </form>
        """
    return f"""
    <tr>
      <td><a href="/goods-lines/{row['id']}/edit">{esc(row['customs_en_name'] or row['cn_name'])}</a><br><span class="hint">{esc(row['order_no'])}</span></td>
      <td>{esc(row['supplier_name'])}</td>
      <td>{esc(row['sku_or_model'])}</td>
      <td>{esc(row['quantity'])}</td>
      <td>{esc(row['carton_count'])}</td>
      <td>{esc(row['units_per_carton'])}</td>
      <td>{package_size(row)}</td>
      <td>{metric(row['carton_gross_weight_kg'])}</td>
      <td>{metric(calculate_cbm(row))}</td>
      <td>{metric(calculate_gross_weight(row))}</td>
      <td>{metric(row['purchase_unit_price'])}</td>
      <td>{esc(row['purchase_currency'])}</td>
      <td>{metric(row['target_markup'])}</td>
      <td>{metric(row['sales_unit_price'])}</td>
      <td>{esc(row['sales_currency'])}</td>
      <td>{esc(row['shipping_mark'])}</td>
      <td>{esc(row['tracking_numbers'])}</td>
      <td>{goods_status_inline(row, user, return_to)}</td>
      <td><a class="icon-button" href="/goods-lines/{row['id']}/edit" title="编辑货物项" aria-label="编辑货物项">✎</a>{delete}</td>
    </tr>
    """


def package_size(row: dict | sqlite3.Row) -> str:
    values = [row["carton_length_cm"], row["carton_width_cm"], row["carton_height_cm"]]
    return "" if any(value is None for value in values) else " x ".join(metric(value) for value in values)


def metric(value) -> str:
    return "" if value in (None, "") else f"{float(value):g}"


def search_page(user: sqlite3.Row, query: str) -> str:
    conn = ensure_database()
    try:
        results = global_search(conn, query) if query else []
    finally:
        conn.close()
    rows = "".join(
        f"<tr><td>{esc(result['type'])}</td><td><a href='{search_result_href(result)}'>{esc(result['label'])}</a></td></tr>"
        for result in results
    ) or '<tr><td colspan="2" class="empty">暂无搜索结果</td></tr>'
    return page(
        "Search",
        f"""
        <section class="toolbar">
          <div><h1>Search</h1><p>订单、客户、供应商、物流单号、麦头和柜号</p></div>
          <form class="search" method="get" action="/search"><input name="q" value="{esc(query)}" placeholder="搜索订单、客户、物流单号、麦头"><button type="submit">查询</button></form>
        </section>
        <section class="panel"><table><thead><tr><th>类型</th><th>结果</th></tr></thead><tbody>{rows}</tbody></table></section>
        """,
        user=user,
    )


def orders_page(user: sqlite3.Row, query: dict[str, list[str]] | None = None, message: str = "", errors: list[str] | None = None) -> str:
    query = query or {}
    conn = ensure_database()
    try:
        cards = sorted(dashboard_orders(conn), key=order_project_sort_key)
        consignees = conn.execute("SELECT * FROM consignees ORDER BY company_name").fetchall()
        receiving = list_warehouses(conn, WAREHOUSE_RECEIVING)
        ports = list_warehouses(conn, WAREHOUSE_PORT)
        selected_id = int_or_none(query.get("order_id", [""])[0]) or (cards[0]["id"] if cards else None)
        selected = selected_order_context(conn, selected_id) if selected_id else None
    finally:
        conn.close()
    form = "" if user["role"] != ROLE_ADMIN else f"""
      <details class="action-drawer"><summary title="新增订单" aria-label="新增订单">+</summary>{order_form("/orders", consignees, receiving, ports)}</details>
    """
    rows = "".join(
        f"<tr><td><a href='/orders?order_id={card['id']}'>{esc(card['order_no'])}</a></td><td>{esc(card['consignee'])}</td><td>{esc(card['destination_port'])}</td><td>{order_status_inline(card, user)}</td><td><progress max='100' value='{card['order_stage_progress']}'></progress> {card['order_stage_progress']}%</td><td>{esc(logistics_point_label(card['current_logistics_point']))}</td><td>{esc(card['expected_loading_date'])}</td><td><a href='/tracking?import_order_id={card['id']}&exception_only=1'>{card['exception_count']}</a></td><td><a href='/shipping-docs?import_order_id={card['id']}'>{card['missing_data_count']}</a></td></tr>"
        for card in cards
    ) or '<tr><td colspan="9" class="empty">暂无订单</td></tr>'
    order_options = "".join(
        f"<option value='{card['id']}'{' selected' if selected_id == card['id'] else ''}>{esc(card['order_no'])}</option>"
        for card in cards
    )
    summary = order_project_summary(selected, user, consignees, receiving, ports) if selected else "<section class='panel pad'>暂无订单摘要</section>"
    notice = f"<p class='notice'>{esc(message)}</p>" if message else ""
    error_html = "".join(f"<li>{esc(error)}</li>" for error in (errors or []))
    errors_block = f"<section class='panel pad'><h2>导入错误</h2><ul class='errors'>{error_html}</ul></section>" if error_html else ""
    return page("订单详情", f"""
      <section class="toolbar"><div><h1>订单详情</h1><p>订单列表和订单资料</p></div>{form}</section>
      {notice}
      {errors_block}
      <section class="panel pad"><form method="get" action="/orders" class="filter-bar"><label>当前订单<select name="order_id" onchange="this.form.submit()">{order_options}</select></label></form></section>
      <section class="panel scroll-panel"><table><thead><tr><th>订单号</th><th>收货客户</th><th>目的港</th><th>订单状态</th><th>订单进度</th><th>当前物流点</th><th>预计装柜日</th><th>异常数</th><th>缺资料数</th></tr></thead><tbody>{rows}</tbody></table></section>
      {summary}
    """, user=user)


def order_project_sort_key(card: dict) -> tuple[int, str]:
    priority = 0 if card["exception_count"] or card["missing_data_count"] else 1
    return priority, str(card["expected_loading_date"] or "9999-12-31")


def selected_order_context(conn: sqlite3.Connection, order_id: int) -> dict | None:
    order = conn.execute(
        """
        SELECT import_orders.*, consignees.company_name,
               receiving.name AS receiving_warehouse_name,
               port.name AS port_warehouse_name
        FROM import_orders
        LEFT JOIN consignees ON consignees.id = import_orders.consignee_id
        LEFT JOIN warehouses AS receiving ON receiving.id = import_orders.receiving_warehouse_id
        LEFT JOIN warehouses AS port ON port.id = import_orders.port_warehouse_id
        WHERE import_orders.id = ?
        """,
        (order_id,),
    ).fetchone()
    if order is None:
        return None
    goods = conn.execute(
        """
        SELECT goods_lines.*, suppliers.name AS supplier_name
        FROM goods_lines
        LEFT JOIN suppliers ON suppliers.id = goods_lines.supplier_id
        WHERE goods_lines.import_order_id = ?
        ORDER BY goods_lines.id
        """,
        (order_id,),
    ).fetchall()
    cards = {card["id"]: card for card in dashboard_orders(conn)}
    totals = {
        "goods_count": len(goods),
        "cartons": sum(row["carton_count"] or 0 for row in goods),
        "cbm": sum(calculate_cbm(row) or 0 for row in goods),
        "gross_weight": sum(calculate_gross_weight(row) or 0 for row in goods),
    }
    return {
        "order": order,
        "goods": goods,
        "card": cards.get(order_id, {}),
        "suppliers": list_suppliers(conn),
        "totals": totals,
    }


def order_project_summary(context: dict, user: sqlite3.Row, consignees: list[sqlite3.Row], receiving: list[sqlite3.Row], ports: list[sqlite3.Row]) -> str:
    order = context["order"]
    totals = context["totals"]
    card = context["card"]
    fields = [
        ("订单号", order["order_no"]),
        ("客户", order["company_name"]),
        ("目的港", order["destination_port"]),
        ("收货仓", order["receiving_warehouse_name"]),
        ("港口仓", order["port_warehouse_name"]),
        ("贸易条款", order["trade_term"]),
        ("预计装柜日", order["expected_loading_date"]),
        ("总货物项", totals["goods_count"]),
        ("总箱数", totals["cartons"]),
        ("总体积 CBM", money(totals["cbm"])),
        ("总毛重 kg", money(totals["gross_weight"])),
        ("订单进度", f"{card.get('order_stage_progress', 0)}%"),
    ]
    summary = "".join(f"<article><span>{esc(label)}</span><strong>{esc(value)}</strong></article>" for label, value in fields)
    actions = ""
    if user["role"] == ROLE_ADMIN:
        actions = f"""
        <div class="action-row">
          <details class="action-drawer"><summary title="编辑订单" aria-label="编辑订单">✎</summary>{order_form(f"/orders/{order['id']}/edit", consignees, receiving, ports, order)}</details>
          {ai_intake_link(order['id'], "AI资料收集箱")}
          {ai_intake_link(order['id'], "AI检查订单")}
          <form method="post" action="/orders/{order['id']}/cancel" class="icon-form">
            <button class="icon-button danger" type="submit" title="取消订单" aria-label="取消订单" onclick="return confirm('取消这个订单？')">×</button>
          </form>
          <a class="button-link" href="/excel-finance?import_order_id={order['id']}">查看成本利润</a>
        </div>
        """
    else:
        actions = f'<div class="action-row"><a class="button-link" href="/excel-finance?import_order_id={order["id"]}">查看成本利润</a></div>'
    return f"""
    <section class="panel pad">
      <div class="panel-head"><h2>订单详情</h2><span>{esc(card.get('current_logistics_point', ''))}</span></div>
      <div class="summary-grid">{summary}</div>
      {actions}
    </section>
    {assistant_link_panel(order["id"], user)}
    """


def ai_intake_link(import_order_id: int, label: str) -> str:
    return f'<a class="button-link" href="/ai-intake?import_order_id={import_order_id}#ai-intake-workspace">{esc(label)}</a>'


def assistant_link_panel(import_order_id: int, user: sqlite3.Row) -> str:
    if user["role"] != ROLE_ADMIN:
        return ""
    return f"""
    <section class="panel pad ai-intake-link-panel">
      <div class="panel-head"><h2>AI资料收集箱</h2><span>已移至独立工作区</span></div>
      <p class="hint">请进入独立工作区上传资料、查看核查请求和确认草稿。</p>
      <div class="action-row">{ai_intake_link(import_order_id, "打开 AI资料收集箱")}</div>
    </section>
    """


def assistant_drawer(import_order_id: int, task_template: str, label: str, return_to: str, *, upload: bool = False, pasted_text: bool = False) -> str:
    enctype = ' enctype="multipart/form-data"' if upload else ""
    file_input = '<label>上传资料<input name="file" type="file" accept=".xlsx,.xls,.pdf,.txt"></label>' if upload else ""
    text_input = '<label>粘贴聊天记录/说明<textarea name="pasted_text" rows="6"></textarea></label>' if pasted_text else ""
    confirm_input = '<label class="checkbox"><input name="real_data_confirmed" type="checkbox" value="1" checked>使用 DeepSeek 真实检查（会发送当前订单资料）；本地可完成的任务不会发送给模型</label>'
    return f"""
    <details class="action-drawer"><summary>{esc(label)}</summary>
      <form method="post" action="/assistant/run" class="form-grid"{enctype}>
        <input type="hidden" name="import_order_id" value="{import_order_id}">
        <input type="hidden" name="task_template" value="{esc(task_template)}">
        <input type="hidden" name="return_to" value="{esc(return_to)}">
        {file_input}
        {text_input}
        {confirm_input}
        <button type="submit">运行 {esc(label)}</button>
      </form>
    </details>
    """


def order_agent_page(user: sqlite3.Row, query: dict[str, list[str]] | None = None) -> str:
    query = query or {}
    selected_id = int_or_none(query.get("conversation_id", [""])[0])
    default_order_id = int_or_none(query.get("import_order_id", [""])[0])
    conn = ensure_database()
    try:
        orders = conn.execute("SELECT id, order_no FROM import_orders ORDER BY created_at DESC").fetchall()
        order_ids = {int(order["id"]) for order in orders}
        if default_order_id not in order_ids:
            default_order_id = None
        conversations = conn.execute(
            """
            SELECT order_agent_conversations.*, import_orders.order_no
            FROM order_agent_conversations
            LEFT JOIN import_orders ON import_orders.id = order_agent_conversations.import_order_id
            WHERE created_by_user_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (int(user["id"]),),
        ).fetchall()
    finally:
        conn.close()
    if selected_id is None and conversations:
        selected_id = int(conversations[0]["id"])
    selected = next((conversation for conversation in conversations if int(conversation["id"]) == selected_id), None)
    if selected is None and conversations:
        selected = conversations[0]
    order_options = "<option value=''>不关联进口订单</option>" + "".join(
        f"<option value='{order['id']}'{' selected' if default_order_id == order['id'] else ''}>{esc(order['order_no'])}</option>"
        for order in orders
    )
    create_form = f"""
    <section class="panel pad">
      <div class="panel-head"><h2>新建对话</h2><span>可不选择订单</span></div>
      <form method="post" action="/order-agent/conversations" class="form-grid">
        <label>关联进口订单<select name="import_order_id">{order_options}</select></label>
        <label>对话标题<input name="title" placeholder="例如：根据供应商资料创建订单"></label>
        <label>自然语言输入<textarea name="message" rows="3" placeholder="帮我根据这些资料创建一个订单"></textarea></label>
        <button type="submit">新建对话</button>
      </form>
    </section>
    """
    return page(
        "订单智能体",
        f"""
        <section class="toolbar"><div><h1>订单智能体</h1><p>面向订单业务目标的通用智能体工作台：先保留对话，后续接入任务理解、资料录入和风险提示 Agent。</p></div></section>
        {create_form}
        <section class="order-agent-layout">
          {order_agent_conversation_list(conversations, selected)}
          {order_agent_workspace(selected, orders)}
        </section>
        """,
        user=user,
    )


def order_agent_conversation_list(conversations: list[sqlite3.Row], selected: sqlite3.Row | None) -> str:
    selected_id = int(selected["id"]) if selected else None
    cards = "".join(order_agent_conversation_card(conversation, selected_id) for conversation in conversations)
    if not cards:
        cards = '<p class="empty">暂无保留对话</p>'
    return f"""
    <section class="panel order-agent-sidebar">
      <div class="panel-head"><h2>对话列表</h2><span>{len(conversations)}</span></div>
      <div class="order-agent-conversation-scroll order-agent-list-scroll">{cards}</div>
    </section>
    """


def order_agent_conversation_card(conversation: sqlite3.Row, selected_id: int | None) -> str:
    active = " active" if int(conversation["id"]) == selected_id else ""
    order_label = conversation["order_no"] or "未关联订单"
    status = ORDER_AGENT_STATUS_LABELS.get(conversation["status"], conversation["status"])
    title = conversation["title"] or "未命名对话"
    return f"""
    <a class="order-agent-card{active}" href="/order-agent?conversation_id={conversation['id']}">
      <strong>{esc(title)}</strong>
      <span>{esc(order_label)}</span>
      <small>{esc(status)} · {esc(conversation['updated_at'])}</small>
    </a>
    """


def order_agent_workspace(conversation: sqlite3.Row | None, orders: list[sqlite3.Row]) -> str:
    if conversation is None:
        return """
        <section class="panel pad order-agent-workspace-scroll">
          <div class="panel-head"><h2>当前对话</h2><span>空状态</span></div>
          <p class="empty">请先新建或打开一个订单智能体对话。</p>
          <form class="form-grid">
            <label>上传资料<input name="files" type="file" multiple disabled></label>
            <label>自然语言输入<textarea name="message" rows="4" placeholder="新建对话后即可继续补充资料或目标。" disabled></textarea></label>
          </form>
          <section class="order-agent-empty-box"><h2>处理轨迹 Agent Processing Trace</h2><p class="hint">暂无处理轨迹。</p></section>
          <section class="order-agent-empty-box"><h2>结果区</h2><p class="hint">暂无结果。</p></section>
        </section>
        """
    messages = order_agent_messages(conversation)
    message_html = "".join(
        f"<article><strong>{esc(message.get('role', 'user'))}</strong><p>{esc(message.get('content', ''))}</p><small>{esc(message.get('created_at', ''))}</small></article>"
        for message in messages
    ) or '<p class="empty">暂无消息</p>'
    order_options = "<option value=''>未关联订单</option>" + "".join(
        f"<option value='{order['id']}'{' selected' if conversation['import_order_id'] == order['id'] else ''}>{esc(order['order_no'])}</option>"
        for order in orders
    )
    closed = conversation["status"] == "closed"
    disabled = " disabled" if closed else ""
    close_action = "" if closed else f"""
      <form method="post" action="/order-agent/conversations/{conversation['id']}/close" class="icon-form">
        <button class="icon-button danger" type="submit" title="关闭对话" aria-label="关闭对话">×</button>
      </form>
    """
    return f"""
    <section class="panel pad order-agent-workspace-scroll" id="order-agent-workspace">
      <div class="panel-head"><h2>当前对话</h2><span>{esc(ORDER_AGENT_STATUS_LABELS.get(conversation['status'], conversation['status']))}</span></div>
      <div class="order-agent-workbench-head">
        <div>
          <h2>{esc(conversation['title'] or '未命名对话')}</h2>
          <p class="hint">创建时间 {esc(conversation['created_at'])}</p>
        </div>
        {close_action}
      </div>
      <form class="form-grid">
        <label>关联进口订单<select name="import_order_id" disabled>{order_options}</select></label>
      </form>
      <section class="order-agent-message-scroll">{message_html}</section>
      <form method="post" action="/order-agent/conversations/{conversation['id']}/messages" class="form-grid order-agent-input">
        <label>上传资料<input name="files" type="file" accept=".xlsx,.xls,.pdf,.txt" multiple{disabled}></label>
        <label>自然语言输入<textarea name="message" rows="4" placeholder="补充资料、目标或缺失信息；本期只保存到对话，不运行模型。"{disabled}></textarea></label>
        <button type="submit"{disabled}>保存到对话</button>
      </form>
      <section class="order-agent-empty-box"><h2>处理轨迹 Agent Processing Trace</h2><p class="hint">暂无处理轨迹。</p></section>
      <section class="order-agent-empty-box"><h2>结果区</h2><p class="hint">暂无结果。</p></section>
    </section>
    """


def handle_order_agent_conversation_post(form: dict[str, str], user: sqlite3.Row) -> int:
    import_order_id = int_or_none(form.get("import_order_id", ""))
    message = form.get("message", "").strip()
    title = form.get("title", "").strip() or (message[:28] if message else "新建订单智能体对话")
    now = utc_now()
    messages = order_agent_message_payload(message, now)
    conn = ensure_database()
    try:
        row = conn.execute("SELECT id FROM import_orders WHERE id = ?", (import_order_id,)).fetchone() if import_order_id else None
        safe_order_id = import_order_id if row else None
        cursor = conn.execute(
            """
            INSERT INTO order_agent_conversations (
                import_order_id, created_by_user_id, title, status, messages_json,
                trace_json, result_json, created_at, updated_at
            )
            VALUES (?, ?, ?, 'draft', ?, '[]', '{}', ?, ?)
            """,
            (safe_order_id, int(user["id"]), title, json.dumps(messages, ensure_ascii=False), now, now),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def handle_order_agent_message_post(conversation_id: int, form: dict[str, str], user: sqlite3.Row) -> None:
    message = form.get("message", "").strip()
    if not message:
        return
    now = utc_now()
    conn = ensure_database()
    try:
        conversation = conn.execute(
            "SELECT * FROM order_agent_conversations WHERE id = ? AND created_by_user_id = ?",
            (conversation_id, int(user["id"])),
        ).fetchone()
        if conversation is None or conversation["status"] == "closed":
            return
        messages = order_agent_messages(conversation)
        messages.extend(order_agent_message_payload(message, now))
        conn.execute(
            "UPDATE order_agent_conversations SET messages_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(messages, ensure_ascii=False), now, conversation_id),
        )
        conn.commit()
    finally:
        conn.close()


def handle_order_agent_close_post(conversation_id: int, user: sqlite3.Row) -> None:
    now = utc_now()
    conn = ensure_database()
    try:
        conn.execute(
            """
            UPDATE order_agent_conversations
            SET status = 'closed', closed_at = ?, updated_at = ?
            WHERE id = ? AND created_by_user_id = ?
            """,
            (now, now, conversation_id, int(user["id"])),
        )
        conn.commit()
    finally:
        conn.close()


def order_agent_messages(conversation: sqlite3.Row) -> list[dict]:
    try:
        messages = json.loads(conversation["messages_json"] or "[]")
    except json.JSONDecodeError:
        return []
    return messages if isinstance(messages, list) else []


def order_agent_message_payload(message: str, created_at: str) -> list[dict]:
    return [{"role": "管理员", "content": message, "created_at": created_at}] if message else []


def ai_intake_page(user: sqlite3.Row, query: dict[str, list[str]] | None = None) -> str:
    query = query or {}
    selected_order_id = int_or_none(query.get("import_order_id", [""])[0])
    conn = ensure_database()
    try:
        orders = conn.execute("SELECT id, order_no FROM import_orders ORDER BY created_at DESC").fetchall()
        order_ids = {int(order["id"]) for order in orders}
        if selected_order_id not in order_ids:
            selected_order_id = None
    finally:
        conn.close()
    order_options = "<option value=''>请选择进口订单</option>" + "".join(
        f"<option value='{order['id']}'{' selected' if selected_order_id == order['id'] else ''}>{esc(order['order_no'])}</option>"
        for order in orders
    )
    selected = selected_order_id is not None
    disabled = "" if selected else " disabled"
    order_input = f'<input type="hidden" name="import_order_id" value="{selected_order_id}">' if selected else ""
    intake_form = f"""
    <section class="panel pad" id="ai-intake-workspace">
      <div class="panel-head"><h2>资料收集</h2><span>{'选择订单后运行' if not selected else '上传或粘贴资料'}</span></div>
      <form method="get" action="/ai-intake" class="filter-bar">
        <label>进口订单<select name="import_order_id" onchange="this.form.submit()">{order_options}</select></label>
      </form>
      <form method="post" action="/assistant/run" class="form-grid ai-intake-form" enctype="multipart/form-data" onsubmit="return aiIntakeSubmit(this)">
        {order_input}
        <input type="hidden" name="task_template" value="{TASK_FILE_TEXT_INTAKE}">
        <input type="hidden" name="workflow_section" value="AI资料收集箱">
        <input type="hidden" name="return_to" value="{ai_intake_return_to(selected_order_id)}">
        <label>上传资料<input name="files" type="file" accept=".xlsx,.xls,.pdf,.txt" multiple{disabled}></label>
        <label>资料内容<textarea name="source_text" rows="8" placeholder="粘贴供应商邮件、聊天记录、仓库备注，或提单/报关单/VerifyCopy 内容；系统会自动判断资料类型。"{disabled}></textarea></label>
        <label class="checkbox"><input name="real_data_confirmed" type="checkbox" value="1" checked{disabled}>使用 DeepSeek 真实处理（会发送当前订单资料）；本地可完成的任务不会发送给模型</label>
        <button type="submit"{disabled}>AI处理资料</button>
      </form>
      <div class="ai-busy-overlay"><div class="ai-busy-modal">
        <section>
          <strong>AI 正在处理资料</strong>
          <ol class="ai-busy-steps">
            <li><b>Router 路由器</b><span>判断资料类型和要调用的 Agent。</span></li>
            <li><b>结构化录入 Agent</b><span>提取货物、费用和单证字段草稿。</span></li>
            <li><b>指令理解 Agent</b><span>如果是订单操作指令，只生成待确认操作，不直接写入系统。</span></li>
            <li><b>货物/合规/利润 Agent</b><span>检查缺失字段、单证风险和利润异常。</span></li>
            <li><b>Coordinator 汇总器</b><span>合并同类问题，生成识别数据录入。</span></li>
          </ol>
          <p class="hint"><span id="ai-busy-elapsed">已等待 0 秒</span>。如果停在这里很久，通常是外部模型超时或网络慢；页面不会自动写入系统。</p>
        </section>
        <section class="ai-busy-live">
          <strong>真实回传信息</strong>
          <div id="ai-busy-live-data" class="ai-busy-live-data">等待提交资料...</div>
          <button type="button" id="ai-busy-confirm" class="ai-busy-confirm" hidden>确认并查看结果</button>
        </section>
      </div></div>
      {ai_intake_busy_script()}
      {'' if selected else '<p class="notice">请先选择进口订单，再运行 AI处理资料。</p>'}
    </section>
    """
    assistant = assistant_panel(selected_order_id, user, ai_intake_return_to(selected_order_id), title="AI资料收集箱") if selected else ""
    return page("AI资料收集箱", f"""
      <section class="toolbar"><div><h1>AI资料收集箱</h1><p>选择一个进口订单，集中处理供应商、单证和仓库资料</p></div></section>
      {intake_form}
      {assistant}
    """, user=user)


def ai_intake_busy_script() -> str:
    return """
      <script>
      function aiIntakeSubmit(form) {
        document.body.classList.add('ai-busy');
        const live = document.getElementById('ai-busy-live-data');
        const elapsed = document.getElementById('ai-busy-elapsed');
        const confirmButton = document.getElementById('ai-busy-confirm');
        if (confirmButton) {
          confirmButton.hidden = true;
          confirmButton.textContent = '确认并查看结果';
          confirmButton.onclick = null;
        }
        let seconds = 0;
        const timer = setInterval(() => { if (elapsed) elapsed.textContent = '已等待 ' + (++seconds) + ' 秒'; }, 1000);
        const escText = (value) => String(value || '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
        const files = Array.from(form.querySelector('input[type=file]')?.files || []).map((file) => file.name);
        const pasted = (form.querySelector('textarea[name=source_text]')?.value || '').trim();
        const model = form.querySelector('input[name=real_data_confirmed]')?.checked ? 'DeepSeek 已勾选；本地可完成的资料仍走本地解析。' : 'DeepSeek 未勾选；仅使用本地解析。';
        if (live) {
          live.innerHTML = '<p><b>本次真实提交</b></p>'
            + '<p>文件：' + escText(files.join('、') || '未上传文件') + '</p>'
            + '<p>文字：' + escText(pasted ? pasted.slice(0, 160) : '未粘贴文字') + '</p>'
            + '<p>' + escText(model) + '</p>'
            + '<p class="hint">等待服务端真实返回...</p>';
        }
        if (!window.fetch || !window.FormData || !window.DOMParser) return true;
        fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin', redirect: 'follow' })
          .then((response) => response.text().then((html) => ({ response, html })))
          .then(({ response, html }) => {
            clearInterval(timer);
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const counts = Array.from(doc.querySelectorAll('.assistant-lane-head h3')).map((node) => node.textContent.trim()).join(' / ');
            const review = doc.querySelector('#assistant-reviews .group-action-card strong, #assistant-reviews .assistant-card strong')?.textContent.trim() || '暂无识别数据录入';
            const draft = doc.querySelector('#assistant-drafts .group-action-card strong, #assistant-drafts .assistant-card strong')?.textContent.trim() || '暂无待确认草稿';
            const runError = doc.querySelector('#assistant-runs .assistant-error')?.textContent.trim();
            if (live) {
              live.innerHTML = '<p><b>服务端已返回</b></p>'
                + '<p>' + escText(counts || '已完成处理') + '</p>'
                + '<p>识别数据：' + escText(review) + '</p>'
                + '<p>变更草稿：' + escText(draft) + '</p>'
                + (runError ? '<p class="error">运行错误：' + escText(runError) + '</p>' : '');
            }
            if (confirmButton) {
              confirmButton.hidden = false;
              confirmButton.onclick = () => { window.location.href = response.url || form.querySelector('input[name=return_to]')?.value || '/ai-intake'; };
            }
          })
          .catch((error) => {
            clearInterval(timer);
            if (live) live.innerHTML = '<p class="error">请求失败：' + escText(error.message || error) + '</p>';
            if (confirmButton) {
              confirmButton.textContent = '关闭';
              confirmButton.hidden = false;
              confirmButton.onclick = () => { document.body.classList.remove('ai-busy'); };
            }
          });
        return false;
      }
      </script>
    """


def assistant_panel(import_order_id: int, user: sqlite3.Row, return_to: str | None = None, title: str = "AI资料收集箱") -> str:
    if user["role"] != ROLE_ADMIN:
        return ""
    return_to = return_to or f"/orders?order_id={import_order_id}"
    conn = ensure_database()
    try:
        items = list_order_assistant_items(conn, import_order_id)
    finally:
        conn.close()
    if not any(items.values()):
        return """
        <section class="panel pad assistant-panel">
          <div class="panel-head"><h2>AI资料收集箱</h2><span>暂无 AI 运行记录</span></div>
          <p class="hint">上传 Excel/PDF/聊天记录，或从各业务区跳转到这里开始检查。</p>
        </section>
        """
    suggestions = {row["id"]: row for row in items["suggestions"]}
    run_count = len(items["runs"])
    pending_reviews = [row for row in items["review_requests"] if row["status"] == REVIEW_PENDING]
    no_data_reviews = [
        row
        for row in pending_reviews
        if suggestions.get(row["assistant_suggestion_id"], {}).get("suggestion_type") == "no_recognized_data"
    ]
    active_reviews = review_groupable_rows(pending_reviews) + no_data_reviews
    active_drafts = [row for row in items["change_drafts"] if row["status"] == "draft"]
    draft_count = len(active_drafts)
    review_group_types = grouped_draft_types(review_groupable_rows(active_reviews), REVIEW_PENDING)
    draft_group_types = grouped_draft_types(active_drafts, "draft")
    visible_reviews = [
        row
        for row in active_reviews
        if suggestions.get(row["assistant_suggestion_id"], {}).get("suggestion_type") != "no_recognized_data"
        and (row.get("draft_type") or "other") not in review_group_types
    ]
    visible_drafts = [row for row in active_drafts if (row.get("draft_type") or "other") not in draft_group_types]
    review_count = len(visible_reviews) + len(review_group_types) + (1 if no_data_reviews else 0)
    runs = "".join(assistant_run_row(row, return_to) for row in items["runs"])
    review_rows = assistant_no_data_group(no_data_reviews, suggestions) + "".join(assistant_review_row(row, suggestions.get(row["assistant_suggestion_id"]), return_to) for row in visible_reviews)
    draft_rows = "".join(assistant_draft_row(row, return_to) for row in visible_drafts)
    review_groups = review_group_actions(import_order_id, active_reviews, return_to)
    draft_groups = draft_group_actions(import_order_id, active_drafts, return_to)
    review_empty = "同类数据已合并到上方批量处理" if review_groups else "暂无识别数据录入"
    draft_empty = "同类草稿已合并到上方批量处理" if draft_groups else "暂无待确认草稿"
    history = assistant_history_modal(items)
    return f"""
    <section class="panel assistant-panel">
      <div class="panel-head"><h2>{esc(title)}</h2><span>建议 → 核查 → 草稿 → 确认</span></div>
      <div class="assistant-columns">
        <article class="assistant-lane" id="assistant-runs">{assistant_lane_head(import_order_id, "运行记录", run_count, "runs", return_to, "assistant-runs")}{history_link()}<ul class="compact-list">{runs or "<li>暂无运行</li>"}</ul></article>
        <article class="assistant-lane" id="assistant-reviews">{assistant_lane_head(import_order_id, "识别数据录入", review_count, "reviews", return_to, "assistant-reviews")}{history_link()}{review_groups}<div class="assistant-scroll">{review_rows or f"<p class='empty'>{review_empty}</p>"}</div></article>
        <article class="assistant-lane" id="assistant-drafts">{assistant_lane_head(import_order_id, "待确认变更草稿", draft_count, "drafts", return_to, "assistant-drafts")}{history_link()}{draft_groups}<div class="assistant-scroll">{draft_rows or f"<p class='empty'>{draft_empty}</p>"}</div></article>
      </div>
      {history}
    </section>
    """


def assistant_no_data_group(rows: list[dict], suggestions: dict[int, dict]) -> str:
    if not rows:
        return ""
    first = suggestions.get(rows[0]["assistant_suggestion_id"], {})
    reason = first.get("reason") or "模型返回了无法转成系统录入项的内容，本次未生成可确认数据。"
    count = len(rows)
    suffix = f"（共 {count} 次，清空可归档这些提示）" if count > 1 else ""
    return f"""
    <div class="assistant-card">
      <strong>未识别到有效数据{suffix}</strong>
      <p>建议 · 待核查</p>
      <p class="hint">{esc(reason)}</p>
    </div>
    """


def assistant_review_row(review: dict, suggestion: dict | None, return_to: str) -> str:
    row_anchor = f"review-{review['id']}"
    row_return_to = anchor_return_to(return_to, row_anchor)
    status = REVIEW_STATUS_LABELS.get(review["status"], review["status"])
    level = SUGGESTION_LEVEL_LABELS.get(suggestion["level"], suggestion["level"]) if suggestion else "需核查"
    title = suggestion["title"] if suggestion else "核查请求"
    reason = suggestion["reason"] if suggestion else ""
    draft_hint = " · 含候选草稿" if review.get("draft_candidate_json") and review["draft_candidate_json"] != "{}" else ""
    actions = ""
    if review["status"] == REVIEW_PENDING:
        approve = "" if suggestion and suggestion.get("suggestion_type") == "no_recognized_data" else f'<button name="status" value="{REVIEW_APPROVED_FOR_DRAFT}" type="submit">批准生成草稿</button>'
        actions = f"""
        <form method="post" action="/assistant/review" class="inline-actions">
          <input type="hidden" name="review_request_id" value="{review['id']}">
          <input type="hidden" name="return_to" value="{esc(row_return_to)}">
          {approve}
          <button name="status" value="{REVIEW_IGNORED}" type="submit">忽略</button>
        </form>
        """
    return f"""
    <div class="assistant-card" id="{row_anchor}">
      <strong>{esc(title)}</strong>
      <p>{esc(level)} · {esc(status)}{esc(draft_hint)}</p>
      <p class="hint">{esc(reason)}</p>
      {actions}
    </div>
    """


def assistant_run_row(row: dict, return_to: str) -> str:
    row_anchor = f"run-{row['id']}"
    row_return_to = anchor_return_to(return_to, row_anchor)
    retry = ""
    if row["status"] == "failed":
        retry = f"""
        <form method="post" action="/assistant/runs/{row['id']}/retry" class="inline-actions">
          <input type="hidden" name="return_to" value="{esc(row_return_to)}">
          <label class="checkbox"><input name="real_data_confirmed" type="checkbox" value="1" checked>确认允许外部模型重试</label>
          <button type="submit">重试</button>
        </form>
        """
    error = f"<span class='assistant-error'>{esc(row['error'])}</span>" if row["error"] else ""
    return f"""
    <li class="assistant-run" id="{row_anchor}">
      <strong>{esc(assistant_task_label(row['task_template']))}</strong>
      <span>{esc(RUN_STATUS_LABELS.get(row['status'], row['status']))} · {esc(compact_datetime(row['updated_at']))}</span>
      {error}{retry}
    </li>
    """


def assistant_draft_row(draft: dict, return_to: str) -> str:
    row_anchor = f"draft-{draft['id']}"
    row_return_to = anchor_return_to(return_to, row_anchor)
    status = CHANGE_DRAFT_STATUS_LABELS.get(draft["status"], draft["status"])
    proposed = json.loads(draft["proposed_values_json"] or "{}")
    actions = ""
    if draft["status"] == "draft":
        actions = f"""
        <form method="post" action="/assistant/drafts/{draft['id']}/confirm" class="stack">
          <input type="hidden" name="return_to" value="{esc(row_return_to)}">
          <label>管理员最终值（可空）<textarea name="final_values_json" rows="4" placeholder="可留空，按草稿确认"></textarea></label>
          <button type="submit">确认写入系统</button>
        </form>
        <form method="post" action="/assistant/drafts/{draft['id']}/reject" class="inline-actions">
          <input type="hidden" name="return_to" value="{esc(row_return_to)}">
          <button type="submit">拒绝</button>
        </form>
        """
    return f"""
    <div class="assistant-card" id="{row_anchor}">
      <strong>{esc(draft_type_label(draft["draft_type"]))}</strong>
      <p>{esc(status)} · {esc(draft["agent_name"])}</p>
      {business_draft_summary(proposed)}
      {actions}
    </div>
    """


def ai_intake_return_to(import_order_id: int | None) -> str:
    suffix = f"?import_order_id={import_order_id}" if import_order_id else ""
    return f"/ai-intake{suffix}#ai-intake-workspace"


def anchor_return_to(return_to: str, anchor: str) -> str:
    base = return_to.split("#", 1)[0]
    return f"{base}#{anchor}"


def assistant_lane_head(import_order_id: int, title: str, count: int, kind: str, return_to: str, anchor: str) -> str:
    disabled = " disabled" if count == 0 else ""
    return f"""
    <div class="assistant-lane-head">
      <h3>{esc(title)} <span class="count-badge">{count}</span></h3>
      <form method="post" action="/assistant/archive" class="inline-actions">
        <input type="hidden" name="kind" value="{esc(kind)}">
        <input type="hidden" name="import_order_id" value="{import_order_id}">
        <input type="hidden" name="return_to" value="{esc(anchor_return_to(return_to, anchor))}">
        <button type="submit"{disabled}>清空</button>
      </form>
    </div>
    """


def history_link() -> str:
    return '<a class="history-link" href="#ai-history">查看历史</a>'


def grouped_draft_types(rows: list[dict], status: str) -> set[str]:
    return {row.get("draft_type") or "other" for row in rows if row["status"] == status}


def review_groupable_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("draft_candidate_json") and row["draft_candidate_json"] != "{}" and row.get("draft_type")]


def review_group_actions(import_order_id: int, reviews: list[dict], return_to: str) -> str:
    return group_action_forms(
        import_order_id,
        review_groupable_rows(reviews),
        return_to,
        "/assistant/review-group",
        ("status", REVIEW_APPROVED_FOR_DRAFT, "批准本类生成草稿"),
        ("status", REVIEW_IGNORED, "忽略本类"),
        "assistant-reviews",
    )


def draft_group_actions(import_order_id: int, drafts: list[dict], return_to: str) -> str:
    return group_action_forms(
        import_order_id,
        drafts,
        return_to,
        "/assistant/draft-group",
        ("action", "confirm", "确认本类写入"),
        ("action", "reject", "拒绝本类"),
        "assistant-drafts",
        draft_rows=drafts,
    )


def group_action_forms(import_order_id: int, rows: list[dict], return_to: str, action: str, primary: tuple[str, str, str], secondary: tuple[str, str, str], anchor: str, draft_rows: list[dict] | None = None) -> str:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        draft_type = row.get("draft_type") or "other"
        groups.setdefault(draft_type, []).append(row)
    if not groups:
        return ""
    forms = []
    for draft_type, group_rows in sorted(groups.items(), key=lambda item: item[0]):
        details = draft_group_details(draft_type, draft_rows or [], return_to) if draft_rows is not None else ""
        forms.append(f"""
        <div class="group-action-card">
          <strong>{esc(group_title(draft_type, group_rows))}</strong>
          {group_business_summary(draft_type, group_rows)}
          <span>
            {group_button_form(action, import_order_id, draft_type, return_to, anchor, primary)}
            {group_button_form(action, import_order_id, draft_type, return_to, anchor, secondary)}
          </span>
          {details}
        </div>
        """)
    return f"<div class='group-actions'>{''.join(forms)}</div>"


def group_button_form(action: str, import_order_id: int, draft_type: str, return_to: str, anchor: str, button: tuple[str, str, str]) -> str:
    return f"""
    <form method="post" action="{action}" class="icon-form">
      <input type="hidden" name="import_order_id" value="{import_order_id}">
      <input type="hidden" name="draft_type" value="{esc(draft_type)}">
      <input type="hidden" name="return_to" value="{esc(anchor_return_to(return_to, anchor))}">
      <button name="{button[0]}" value="{esc(button[1])}" type="submit">{esc(button[2])}</button>
    </form>
    """


def group_title(draft_type: str, rows: list[dict]) -> str:
    label = "已识别货物清单" if draft_type == "goods_line" else draft_type_label(draft_type)
    return f"{label} · {len(rows)} 项"


def group_business_summary(draft_type: str, rows: list[dict]) -> str:
    values = [group_row_values(row) for row in rows]
    first = next((value for value in values if value), {})
    if draft_type == "goods_line":
        return f"<p class='hint'>第一条：{esc(goods_summary_line(first))}</p>"
    if draft_type == "safe_field_batch":
        items = [item for value in values for item in value.get("items", []) if isinstance(item, dict)]
        fields = sorted({field_label(field) for item in items for field in (item.get("fields") or {})})
        first_label = items[0].get("goods_label", "货物项") if items else "货物项"
        return f"<p class='hint'>可批量导入：{esc('、'.join(fields) or '安全字段')}；第一条：{esc(first_label)}</p>"
    if draft_type == "goods_status_batch":
        items = [item for value in values for item in value.get("items", []) if isinstance(item, dict)]
        status = first.get("status_label") or "目标状态"
        first_label = items[0].get("goods_label", "货物项") if items else "货物项"
        return f"<p class='hint'>将 {len(items)} 项货物更新为{esc(status)}；第一条：{esc(first_label)}</p>"
    if draft_type == "goods_delete_batch":
        items = [item for value in values for item in value.get("items", []) if isinstance(item, dict)]
        first_label = items[0].get("goods_label", "货物项") if items else "货物项"
        return f"<p class='hint'>将删除当前订单 {len(items)} 项货物；第一条：{esc(first_label)}</p>"
    if draft_type == "import_order_update":
        fields = [field_label(field) for value in values for field in value if field not in {"operation_name"}]
        return f"<p class='hint'>将修改当前订单字段：{esc('、'.join(fields) or '订单资料')}</p>"
    if draft_type == "import_order_delete":
        order_no = first.get("order_no") or "当前订单"
        return f"<p class='hint'>将删除订单 {esc(order_no)} 及其关联资料。</p>"
    if draft_type == "customs_goods_version":
        doc = {"waybill": "海运单", "customs_declaration": "报关单", "verified_customs_copy": "VerifyCopy"}.get(first.get("document_type"), "权威单证")
        rows_count = len(first.get("rows") or [])
        return f"<p class='hint'>识别到{esc(doc)}；可导入报关版本 {rows_count} 行。</p>"
    if draft_type == "container":
        return f"<p class='hint'>识别到海运单集装箱资料：{esc(first.get('container_number') or '待确认柜号')}</p>"
    return "<p class='hint'>识别到需要人工核对的数据。</p>"


def group_row_values(row: dict) -> dict:
    raw = row.get("proposed_values_json") or row.get("draft_candidate_json") or "{}"
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def goods_summary_line(values: dict) -> str:
    name = values.get("cn_name") or values.get("customs_en_name") or values.get("customer_item_no") or "未命名货物"
    pieces = [str(name)]
    if values.get("carton_count") not in (None, ""):
        pieces.append(f"{values['carton_count']} 箱")
    if values.get("quantity") not in (None, ""):
        pieces.append(f"数量 {values['quantity']}")
    if values.get("carton_gross_weight_kg") not in (None, ""):
        pieces.append(f"单箱毛重 {values['carton_gross_weight_kg']}kg")
    return "，".join(pieces)


def draft_group_details(draft_type: str, rows: list[dict], return_to: str) -> str:
    matched = [row for row in rows if (row.get("draft_type") or "other") == draft_type]
    if not matched:
        return ""
    cards = "".join(assistant_draft_row(row, return_to) for row in matched[:20])
    more = f"<p class='hint'>还有 {len(matched) - 20} 项，请先批量确认或分批清理。</p>" if len(matched) > 20 else ""
    return f"<details class='group-edit'><summary>逐项修改</summary>{cards}{more}</details>"


def assistant_history_modal(items: dict[str, list[dict]]) -> str:
    runs = "".join(f"<li>{esc(assistant_task_label(row['task_template']))} · {esc(RUN_STATUS_LABELS.get(row['status'], row['status']))}</li>" for row in items.get("archived_runs", [])[:30])
    reviews = "".join(f"<li>{esc(row.get('status_label', row['status']))} · {esc(row.get('draft_type', '') or '核查请求')}</li>" for row in items.get("archived_review_requests", [])[:30])
    drafts = "".join(f"<li>{esc(CHANGE_DRAFT_STATUS_LABELS.get(row['status'], row['status']))} · {esc(row['draft_type'])}</li>" for row in items.get("archived_change_drafts", [])[:30])
    return f"""
    <div id="ai-history" class="modal-overlay">
      <section class="history-modal">
        <a class="modal-close" href="#ai-intake-workspace">关闭</a>
        <h3>AI资料收集箱历史</h3>
        <div class="history-grid">
          <article><h4>运行记录</h4><ul>{runs or '<li>暂无历史</li>'}</ul></article>
          <article><h4>识别数据录入</h4><ul>{reviews or '<li>暂无历史</li>'}</ul></article>
          <article><h4>待确认变更草稿</h4><ul>{drafts or '<li>暂无历史</li>'}</ul></article>
        </div>
      </section>
    </div>
    """


def business_draft_summary(proposed: dict) -> str:
    if not proposed:
        return "<p class='hint'>暂无待展示字段</p>"
    if proposed.get("status") and proposed.get("items"):
        items = proposed.get("items") or []
        labels = [str(item.get("goods_label") or item.get("goods_line_id") or "货物项") for item in items[:4] if isinstance(item, dict)]
        more = f"等 {len(items)} 项" if len(items) > 4 else f"{len(items)} 项"
        return f"""
        <p><strong>{esc(proposed.get('operation_name') or '批量更新货物物流状态')}</strong></p>
        <p class="hint">影响 {esc(more)}：{esc('、'.join(labels) or '多个货物项')}</p>
        <p class="hint">目标状态：{esc(proposed.get('status_label') or proposed.get('status'))}</p>
        """
    if proposed.get("operation_name") and "删除" in str(proposed.get("operation_name")) and proposed.get("items"):
        items = proposed.get("items") or []
        labels = [str(item.get("goods_label") or item.get("goods_line_id") or "货物项") for item in items[:4] if isinstance(item, dict)]
        more = f"等 {len(items)} 项" if len(items) > 4 else f"{len(items)} 项"
        return f"""
        <p><strong>{esc(proposed.get('operation_name'))}</strong></p>
        <p class="hint">影响 {esc(more)}：{esc('、'.join(labels) or '多个货物项')}</p>
        """
    if proposed.get("operation_name") and "删除" in str(proposed.get("operation_name")):
        return f"<p><strong>{esc(proposed.get('operation_name'))}</strong></p><p class='hint'>确认后将删除订单 {esc(proposed.get('order_no') or '当前订单')} 及其关联资料。</p>"
    if proposed.get("operation_name") == "修改订单资料":
        fields = [field_label(key) for key in proposed if key != "operation_name"]
        return f"<p><strong>修改订单资料</strong></p><p class='hint'>字段：{esc('、'.join(fields) or '订单资料')}</p>"
    if proposed.get("items"):
        items = proposed.get("items") or []
        labels = [str(item.get("goods_label") or item.get("goods_line_id") or "货物项") for item in items[:4] if isinstance(item, dict)]
        field_names = sorted({field_label(field) for item in items if isinstance(item, dict) for field in (item.get("fields") or {})})
        more = f"等 {len(items)} 项" if len(items) > 4 else f"{len(items)} 项"
        return f"""
        <p><strong>{esc(proposed.get('operation_name') or '批量导入安全字段')}</strong></p>
        <p class="hint">影响 {esc(more)}：{esc('、'.join(labels) or '多个货物项')}</p>
        <p class="hint">字段：{esc('、'.join(field_names) or '安全字段')}</p>
        """
    if proposed.get("cn_name") or proposed.get("customs_en_name"):
        name = proposed.get("cn_name") or proposed.get("customs_en_name")
        keys = [field_label(key) for key in proposed.keys() if key not in {"cn_name", "customs_en_name"}]
        return f"<p><strong>{esc(name)}</strong></p><p class='hint'>将生成或更新货物项；包含 {esc('、'.join(keys[:6]) or '基础资料')}</p>"
    if proposed.get("rows"):
        rows = proposed.get("rows") or []
        return f"<p><strong>{esc(proposed.get('source_name') or '权威单证')}</strong></p><p class='hint'>将更新报关版本，共 {len(rows)} 行压缩申报资料。</p>"
    if proposed.get("container_number"):
        return f"<p><strong>{esc(proposed.get('container_number'))}</strong></p><p class='hint'>将导入海运单证的集装箱资料。</p>"
    rows = []
    for key, value in proposed.items():
        rows.append(f"<tr><th>{esc(field_label(key))}</th><td>{esc(business_value(value))}</td></tr>")
    return f"<table class='mini-table'><tbody>{''.join(rows)}</tbody></table>"


def draft_type_label(value: str) -> str:
    return {
        "goods_line": "货物项草稿",
        "safe_field_batch": "批量安全字段",
        "goods_status_batch": "批量货物物流状态",
        "goods_delete_batch": "批量删除货物项",
        "import_order_update": "订单资料修改",
        "import_order_delete": "订单删除",
        "customs_goods_version": "报关版本草稿",
        "container": "集装箱草稿",
        "export_document": "单证草稿",
        "finance": "成本利润草稿",
        "other": "其他草稿",
    }.get(value or "", value or "草稿")


def business_value(value) -> str:
    if isinstance(value, dict):
        pieces = [f"{field_label(str(key))}: {business_value(item)}" for key, item in value.items()]
        return "；".join(pieces)
    if isinstance(value, list):
        return "；".join(business_value(item) for item in value)
    return str(value or "")


def compact_json(value: dict) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= 420 else text[:420] + "..."


def assistant_task_label(value: str) -> str:
    return {
        TASK_FILE_TEXT_INTAKE: "资料导入",
        TASK_CHECK_ORDER: "订单检查",
        TASK_CHECK_GOODS: "货物检查",
        TASK_CHECK_DOC_BLOCKERS: "单证阻塞检查",
        TASK_DRAFT_DOCS: "单证草稿",
        TASK_CHECK_PROFIT: "利润风险检查",
    }.get(value, value)


def compact_datetime(value: str) -> str:
    text = str(value or "")
    return text.replace("T", " ")[:16] if len(text) >= 16 else text


def order_form(action: str, consignees: list[sqlite3.Row], receiving: list[sqlite3.Row], ports: list[sqlite3.Row], order: sqlite3.Row | None = None) -> str:
    return f"""
    <form method="post" action="{action}" class="form-grid">
      {select_input("consignee_id", "收货客户", consignees, "company_name", selected=order["consignee_id"] if order else None)}
      {select_input("receiving_warehouse_id", "收货仓库", receiving, "name", selected=order["receiving_warehouse_id"] if order else None)}
      {select_input("port_warehouse_id", "港口仓库", ports, "name", selected=order["port_warehouse_id"] if order else None)}
      <label>订单号(可空)<input name="order_no" value="{esc(order['order_no'] if order else '')}"></label>
      <label>贸易条款<input name="trade_term" placeholder="FOB" value="{esc(order['trade_term'] if order else '')}"></label>
      <label>目的国家<input name="destination_country" value="{esc(order['destination_country'] if order else '')}"></label>
      <label>目的港<input name="destination_port" value="{esc(order['destination_port'] if order else '')}"></label>
      <label>预计装柜日<input name="expected_loading_date" type="date" value="{esc(order['expected_loading_date'] if order else '')}"></label>
      <label>采购币种<input name="purchase_currency" value="{esc(order['purchase_currency'] if order else '')}"></label>
      <label>销售币种<input name="sales_currency" value="{esc(order['sales_currency'] if order else '')}"></label>
      <label>备注<input name="internal_notes" value="{esc(order['internal_notes'] if order else '')}"></label>
      <button type="submit">保存订单</button>
    </form>
    """


def order_consignees_panel(user: sqlite3.Row, consignees: list[sqlite3.Row], selected_order_id: int | None) -> str:
    actions = ""
    if user["role"] == ROLE_ADMIN:
        rows = "".join(consignee_row(row, selected_order_id) for row in consignees) or '<tr><td colspan="5" class="empty">暂无收货客户</td></tr>'
        actions = f"<details class='action-drawer'><summary title='新增收货客户' aria-label='新增收货客户'>+</summary>{consignee_form('/orders/consignees', selected_order_id)}</details>"
    else:
        rows = "".join(
            f"<tr><td>{esc(row['company_name'])}</td><td>{esc(row['contact_name'])}</td><td>{esc(row['phone'])}</td><td>{esc(row['email'])}</td><td></td></tr>"
            for row in consignees
        ) or '<tr><td colspan="5" class="empty">暂无收货客户</td></tr>'
    return f"""
    <section class="panel">
      <div class="panel-head"><h2>收货客户</h2>{actions}</div>
      <table><thead><tr><th>公司</th><th>联系人</th><th>电话</th><th>邮箱</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table>
    </section>
    """


def consignee_row(row: sqlite3.Row, selected_order_id: int | None) -> str:
    return f"""
    <tr>
      <td>{esc(row['company_name'])}</td>
      <td>{esc(row['contact_name'])}</td>
      <td>{esc(row['phone'])}</td>
      <td>{esc(row['email'])}</td>
      <td>
        <details class="action-drawer"><summary title="编辑收货客户" aria-label="编辑收货客户">✎</summary>{consignee_form(f"/orders/consignees/{row['id']}/edit", selected_order_id, row)}</details>
        <form method="post" action="/orders/consignees/{row['id']}/delete" class="icon-form">
          <input type="hidden" name="return_order_id" value="{esc(selected_order_id or '')}">
          <button class="icon-button danger" type="submit" title="删除收货客户" aria-label="删除收货客户" onclick="return confirm('删除这个收货客户？')">×</button>
        </form>
      </td>
    </tr>
    """


def consignee_form(action: str, selected_order_id: int | None, row: sqlite3.Row | None = None) -> str:
    return f"""
    <form method="post" action="{action}" class="form-grid">
      <input type="hidden" name="return_order_id" value="{esc(selected_order_id or '')}">
      <label>公司名称<input name="company_name" required value="{esc(row['company_name'] if row else '')}"></label>
      <label>联系人<input name="contact_name" value="{esc(row['contact_name'] if row else '')}"></label>
      <label>电话<input name="phone" value="{esc(row['phone'] if row else '')}"></label>
      <label>邮箱<input name="email" value="{esc(row['email'] if row else '')}"></label>
      <label>税号<input name="tax_id" value="{esc(row['tax_id'] if row else '')}"></label>
      <label>地址<input name="address" value="{esc(row['address'] if row else '')}"></label>
      <label>默认目的港<input name="default_destination_port" value="{esc(row['default_destination_port'] if row else '')}"></label>
      <label>默认贸易条款<input name="default_trade_term" value="{esc(row['default_trade_term'] if row else '')}"></label>
      <label>默认销售币种<input name="default_sales_currency" value="{esc(row['default_sales_currency'] if row else '')}"></label>
      <label>单证偏好<input name="document_preferences" value="{esc(row['document_preferences'] if row else '')}"></label>
      <label>备注<input name="notes" value="{esc(row['notes'] if row else '')}"></label>
      <button type="submit">保存收货客户</button>
    </form>
    """


def order_project_goods_table(context: dict, user: sqlite3.Row) -> str:
    order = context["order"]
    return_to = f"/orders?order_id={order['id']}"
    rows = "".join(order_project_goods_row(row, user, return_to) for row in context["goods"]) or '<tr><td colspan="9" class="empty">暂无货物项</td></tr>'
    form = "" if user["role"] != ROLE_ADMIN else compact_goods_line_drawer(order["id"], context["suppliers"])
    return f"""
    <section class="panel">
      <div class="panel-head"><h2>货物明细</h2>{form}</div>
      <table><thead><tr><th>货物项</th><th>供应商</th><th>数量</th><th>箱数</th><th>CBM</th><th>毛重</th><th>货物物流状态</th><th>麦头</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table>
    </section>
    """


def order_project_goods_row(row: sqlite3.Row, user: sqlite3.Row, return_to: str) -> str:
    return f"""
    <tr>
      <td><a href="/goods-lines/{row['id']}/edit">{esc(row['customs_en_name'] or row['cn_name'])}</a></td>
      <td>{esc(row['supplier_name'])}</td>
      <td>{esc(row['quantity'])}</td>
      <td>{esc(row['carton_count'])}</td>
      <td>{money(calculate_cbm(row) or 0)}</td>
      <td>{money(calculate_gross_weight(row) or 0)}</td>
      <td>{goods_status_inline(row, user, return_to)}</td>
      <td>{esc(row['shipping_mark'])}</td>
      <td><a class="icon-button" href="/goods-lines/{row['id']}/edit" title="编辑货物项" aria-label="编辑货物项">✎</a></td>
    </tr>
    """


def compact_goods_line_drawer(order_id: int, suppliers: list[sqlite3.Row], return_to: str | None = None) -> str:
    return_to = return_to or f"/orders?order_id={order_id}"
    return f"""
    <details class="action-drawer"><summary title="新增货物项" aria-label="新增货物项">+</summary>
      <div class="drawer-stack">
      <h2>手动添加货物项</h2>
      <form method="post" action="/orders/{order_id}/goods-lines" class="form-grid">
        <input type="hidden" name="return_to" value="{esc(return_to)}">
        {select_input("supplier_id", "供应商", suppliers, "name")}
        <label>1688/商品链接<input name="product_url"></label>
        <label>中文品名<input name="cn_name"></label>
        <label>报关英文品名<input name="customs_en_name"></label>
        <label>SKU/型号<input name="sku_or_model"></label>
        <label>数量<input name="quantity" type="number" step="0.01"></label>
        <label>单位<input name="unit" value="pcs"></label>
        <label>箱数<input name="carton_count" type="number"></label>
        <label>麦头<input name="shipping_mark"></label>
        <button type="submit">保存货物项</button>
      </form>
      <h2>上传 Excel 货物清单</h2>
      <form method="post" action="/orders/{order_id}/goods-lines/import" class="form-grid" enctype="multipart/form-data">
        <input type="hidden" name="return_to" value="{esc(return_to)}">
        <label>货物清单 Excel<input name="file" type="file" accept=".xlsx" required></label>
        <button type="submit">上传导入</button>
      </form>
      </div>
    </details>
    """


def order_detail_page(user: sqlite3.Row, order_id: int) -> str:
    conn = ensure_database()
    try:
        order = conn.execute(
            """
            SELECT import_orders.*, consignees.company_name
            FROM import_orders
            LEFT JOIN consignees ON consignees.id = import_orders.consignee_id
            WHERE import_orders.id = ?
            """,
            (order_id,),
        ).fetchone()
        if order is None:
            return page("Not found", "<section class='panel pad'>订单不存在</section>", user=user)
        goods = conn.execute(
            """
            SELECT goods_lines.*, suppliers.name AS supplier_name
            FROM goods_lines
            LEFT JOIN suppliers ON suppliers.id = goods_lines.supplier_id
            WHERE import_order_id = ?
            ORDER BY goods_lines.id
            """,
            (order_id,),
        ).fetchall()
        suppliers = list_suppliers(conn)
    finally:
        conn.close()
    tabs = "".join(f"<a>{esc(tab)}</a>" for tab in IMPORT_ORDER_DETAIL_TABS)
    goods_rows = "".join(
        f"<tr><td><a href='/goods-lines/{g['id']}/edit'>{g['id']}</a></td><td>{esc(g['cn_name'])}</td><td>{esc(g['supplier_name'])}</td><td>{esc(g['quantity'])}</td><td>{esc(g['carton_count'])}</td><td>{esc(g['volume_cbm'])}</td><td>{esc(g['gross_weight'])}</td><td>{esc(g['logistics_status'])}</td></tr>"
        for g in goods
    ) or '<tr><td colspan="8" class="empty">暂无商品行</td></tr>'
    form = "" if user["role"] != ROLE_ADMIN else goods_line_form(f"/orders/{order_id}/goods-lines", suppliers)
    return page(str(order["order_no"]), f"""
      <section class="toolbar"><div><h1>{esc(order['order_no'])}</h1><p>{esc(order['company_name'])} · {esc(order['destination_port'])}</p></div></section>
      <section class="tabs">{tabs}</section>
      {form}
      <section class="panel"><table><thead><tr><th>ID</th><th>商品</th><th>供应商</th><th>数量</th><th>箱数</th><th>CBM</th><th>毛重</th><th>物流状态</th></tr></thead><tbody>{goods_rows}</tbody></table></section>
    """, user=user)


def goods_line_edit_page(user: sqlite3.Row, goods_line_id: int) -> str:
    conn = ensure_database()
    try:
        goods = conn.execute("SELECT * FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        suppliers = list_suppliers(conn)
    finally:
        conn.close()
    if goods is None:
        return page("Not found", "<section class='panel pad'>商品行不存在</section>", user=user)
    delete_action = ""
    if user["role"] == ROLE_ADMIN:
        delete_action = f"""
        <form method="post" action="/goods-lines/{goods_line_id}/delete" class="icon-form">
          <button class="icon-button danger" type="submit" title="删除货物项" aria-label="删除货物项" onclick="return confirm('删除这个货物项？')">×</button>
        </form>
        """
    actions = f"""
    <div class="action-row">
      <a class="icon-button" href="/tracking?import_order_id={goods['import_order_id']}" title="返回货物详情" aria-label="返回货物详情">←</a>
      {delete_action}
    </div>
    """
    return page(
        f"货物项 {goods_line_id}",
        f"<section class='toolbar'><div><h1>货物项 {goods_line_id}</h1><p>分组编辑货物信息</p></div>{actions}</section>{goods_line_form(f'/goods-lines/{goods_line_id}/edit', suppliers, goods, disabled=user['role'] != ROLE_ADMIN)}",
        user=user,
    )


def receiving_page(user: sqlite3.Row, query: dict[str, list[str]] | None = None, message: str = "", errors: list[str] | None = None) -> str:
    query = query or {}
    warehouse_id = int_or_none(query.get("warehouse_id", [""])[0])
    status = query.get("status", ["all"])[0] or "all"
    received_date = query.get("date", [""])[0]
    keyword = query.get("q", [""])[0]
    conn = ensure_database()
    try:
        warehouses = list_warehouses(conn)
        if warehouse_id is None and warehouses:
            warehouse_id = int(warehouses[0]["id"])
        warehouse = conn.execute("SELECT * FROM warehouses WHERE id = ?", (warehouse_id,)).fetchone() if warehouse_id else None
        results = warehouse_inventory_rows(
            conn,
            actor_role=user["role"],
            warehouse=warehouse,
            status=status,
            received_date=received_date,
            keyword=keyword,
        )
    finally:
        conn.close()
    notice = f"<p class='notice'>{esc(message)}</p>" if message else ""
    error_html = "".join(f"<li>{esc(error)}</li>" for error in (errors or []))
    errors_block = f"<section class='panel pad'><h2>操作提示</h2><ul class='errors'>{error_html}</ul></section>" if error_html else ""
    if not warehouses:
        create = "" if user["role"] != ROLE_ADMIN else f"<details class='action-drawer'><summary title='新增仓库' aria-label='新增仓库'>+</summary>{warehouse_form('/receiving/warehouses')}</details>"
        return page("仓库盘点", f"<section class='toolbar'><div><h1>仓库盘点</h1><p>请先录入仓库资料</p></div>{create}</section>{notice}{errors_block}", user=user)
    warehouse_options = "".join(
        f"<option value='{row['id']}'{' selected' if warehouse_id == row['id'] else ''}>{esc(row['name'])}</option>"
        for row in warehouses
    )
    status_options = "".join(
        f"<option value='{value}'{' selected' if value == status else ''}>{label}</option>"
        for value, label in [("all", "全部"), ("pending", "待入库"), ("received", "已入库"), ("exception", "异常")]
    )
    exception_options = "<option value=''></option>" + "".join(
        f"<option value='{esc(value)}'>{esc(value)}</option>" for value in sorted(ARRIVAL_EXCEPTION_TYPES)
    )
    hidden_context = receiving_hidden_context(warehouse_id, status, received_date, keyword)
    rows = "".join(_warehouse_inventory_row(row, hidden_context, exception_options) for row in results) or '<tr><td colspan="11" class="empty">暂无匹配货物项</td></tr>'
    warehouse_summary = "".join(
        f"<article><span>{esc(label)}</span><strong>{esc(value)}</strong></article>"
        for label, value in [
            ("仓库类型", "收货仓库" if warehouse and warehouse["type"] == WAREHOUSE_RECEIVING else "港口仓库"),
            ("联系人", warehouse["contact_name"] if warehouse else ""),
            ("电话", warehouse["phone"] if warehouse else ""),
            ("地址", warehouse["address"] if warehouse else ""),
        ]
    )
    return page(
        "仓库盘点",
        f"""
        <section class="toolbar">
          <div><h1>仓库盘点</h1><p>选择仓库后查看待入库、已入库和异常货物</p></div>
        </section>
        {notice}
        {errors_block}
        <section class="panel pad">
          <form method="get" action="/receiving" class="filter-bar">
            <label>仓库<select name="warehouse_id" onchange="this.form.submit()">{warehouse_options}</select></label>
            <label>状态<select name="status" onchange="this.form.submit()">{status_options}</select></label>
            <label>入库日期<input name="date" type="date" value="{esc(received_date)}" onchange="this.form.submit()"></label>
            <label>关键词<input name="q" value="{esc(keyword)}" placeholder="订单号/物流单号/麦头"></label>
            <button type="submit">搜索</button>
          </form>
        </section>
        <section class="panel pad"><div class="panel-head"><h2>仓库信息</h2><span>{esc(warehouse['name'] if warehouse else '')}</span></div><div class="summary-grid">{warehouse_summary}</div></section>
        <section class="panel warehouse-scroll">
          <table>
            <thead><tr><th>订单号</th><th>货物项</th><th>供应商</th><th>麦头</th><th>国内物流单号</th><th>应到箱数</th><th>已收箱数</th><th>包装情况</th><th>异常</th><th>最近入库时间</th><th>操作</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
        """,
        user=user,
    )


def warehouse_inventory_rows(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    warehouse: sqlite3.Row | None,
    status: str,
    received_date: str,
    keyword: str,
) -> list[dict]:
    search_receiving(conn, actor_role=actor_role, query="")
    if warehouse is None:
        return []
    clauses = []
    params: list = []
    if warehouse["type"] == WAREHOUSE_PORT:
        clauses.append("import_orders.port_warehouse_id = ?")
        clauses.append("goods_lines.logistics_status IN ('moved_to_port_warehouse', 'loaded', 'at_sea', 'exception')")
    else:
        clauses.append("import_orders.receiving_warehouse_id = ?")
    params.append(warehouse["id"])
    if keyword:
        clauses.append("(import_orders.order_no LIKE ? OR goods_lines.shipping_mark LIKE ? OR domestic_tracking_numbers.tracking_no LIKE ?)")
        pattern = f"%{keyword}%"
        params.extend([pattern, pattern, pattern])
    if received_date:
        clauses.append("date(receiving_summary.last_receiving_at) = ?")
        params.append(received_date)
    having = ""
    if status == "pending":
        if warehouse["type"] == WAREHOUSE_PORT:
            clauses.append("goods_lines.logistics_status = 'moved_to_port_warehouse'")
        else:
            clauses.append("goods_lines.logistics_status != 'exception'")
            having = "HAVING received_cartons = 0"
    elif status == "received":
        if warehouse["type"] == WAREHOUSE_PORT:
            clauses.append("goods_lines.logistics_status IN ('loaded', 'at_sea')")
        else:
            having = "HAVING received_cartons > 0"
    elif status == "exception":
        clauses.append("(goods_lines.logistics_status = 'exception' OR receiving_summary.latest_exception != '')")
    rows = conn.execute(
        f"""
        SELECT
            goods_lines.id AS goods_line_id,
            goods_lines.cn_name,
            goods_lines.customs_en_name,
            goods_lines.shipping_mark,
            goods_lines.carton_count,
            goods_lines.logistics_status,
            suppliers.name AS supplier_name,
            import_orders.order_no,
            group_concat(DISTINCT domestic_tracking_numbers.tracking_no) AS tracking_numbers,
            COALESCE(receiving_summary.received_cartons, 0) AS received_cartons,
            COALESCE(receiving_summary.package_condition, '') AS package_condition,
            COALESCE(receiving_summary.latest_exception, '') AS latest_exception,
            COALESCE(receiving_summary.last_receiving_at, '') AS last_receiving_at
        FROM goods_lines
        JOIN import_orders ON import_orders.id = goods_lines.import_order_id
        LEFT JOIN suppliers ON suppliers.id = goods_lines.supplier_id
        LEFT JOIN domestic_tracking_numbers ON domestic_tracking_numbers.goods_line_id = goods_lines.id
        LEFT JOIN (
            SELECT
                goods_line_id,
                SUM(received_carton_count) AS received_cartons,
                MAX(package_condition) AS package_condition,
                MAX(arrival_exception_type) AS latest_exception,
                MAX(created_at) AS last_receiving_at
            FROM receiving_records
            GROUP BY goods_line_id
        ) AS receiving_summary ON receiving_summary.goods_line_id = goods_lines.id
        WHERE {' AND '.join(clauses)}
        GROUP BY goods_lines.id
        {having}
        ORDER BY import_orders.order_no, goods_lines.id
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def receiving_hidden_context(warehouse_id: int | None, status: str, received_date: str, keyword: str) -> str:
    return (
        f"<input type='hidden' name='warehouse_id' value='{esc(warehouse_id or '')}'>"
        f"<input type='hidden' name='status' value='{esc(status)}'>"
        f"<input type='hidden' name='date' value='{esc(received_date)}'>"
        f"<input type='hidden' name='query' value='{esc(keyword)}'>"
    )


def receiving_redirect(form: dict[str, str]) -> str:
    parts = [
        ("warehouse_id", form.get("warehouse_id", "")),
        ("status", form.get("status", "all")),
        ("date", form.get("date", "")),
        ("q", form.get("query", "")),
    ]
    return "/receiving?" + "&".join(f"{key}={quote(value)}" for key, value in parts if value)


def warehouse_form(action: str, warehouse: sqlite3.Row | None = None) -> str:
    type_options = "".join(
        f"<option value='{esc(value)}'{' selected' if warehouse and warehouse['type'] == value else ''}>{esc(warehouse_type_label(value))}</option>"
        for value in [WAREHOUSE_RECEIVING, WAREHOUSE_PORT]
    )
    return f"""
    <form method="post" action="{action}" class="form-grid">
      <label>类型<select name="type">{type_options}</select></label>
      <label>名称<input name="name" required value="{esc(warehouse['name'] if warehouse else '')}"></label>
      <label>联系人<input name="contact_name" value="{esc(warehouse['contact_name'] if warehouse else '')}"></label>
      <label>电话<input name="phone" value="{esc(warehouse['phone'] if warehouse else '')}"></label>
      <label>地址<input name="address" value="{esc(warehouse['address'] if warehouse else '')}"></label>
      <label>备注<input name="notes" value="{esc(warehouse['notes'] if warehouse else '')}"></label>
      <button type="submit">保存仓库</button>
    </form>
    """


def basic_data_page(user: sqlite3.Row, query: dict[str, list[str]] | None = None, errors: list[str] | None = None) -> str:
    conn = ensure_database()
    try:
        suppliers = list_suppliers(conn)
        consignees = conn.execute("SELECT * FROM consignees ORDER BY company_name").fetchall()
        warehouses = list_warehouses(conn)
        seller = get_setting(conn, "seller")
        defaults = get_setting(conn, "defaults")
        reminders = get_setting(conn, "reminders")
        deepseek = get_setting(conn, "deepseek")
    finally:
        conn.close()
    error_html = "".join(f"<li>{esc(error)}</li>" for error in (errors or []))
    errors_block = f"<section class='panel pad'><h2>操作提示</h2><ul class='errors'>{error_html}</ul></section>" if error_html else ""
    return page(
        "基础资料",
        f"""
        <section class="toolbar"><div><h1>基础资料</h1><p>供应商、客户、仓库和公司信息</p></div></section>
        {errors_block}
        {basic_data_suppliers(suppliers)}
        {basic_data_consignees(consignees)}
        {basic_data_warehouses(warehouses)}
        {basic_data_llm(deepseek)}
        {basic_data_company(seller, defaults, reminders)}
        """,
        user=user,
    )


def basic_data_suppliers(suppliers: list[sqlite3.Row]) -> str:
    rows = "".join(supplier_master_row(row) for row in suppliers) or '<tr><td colspan="7" class="empty">暂无供应商</td></tr>'
    return f"""
    <section class="panel master-data-scroll" id="suppliers">
      <div class="panel-head"><h2>供应商</h2><details class="action-drawer"><summary title="新增供应商" aria-label="新增供应商">+</summary>{supplier_form("/basic-data/suppliers")}</details></div>
      <table><thead><tr><th>名称</th><th>联系人</th><th>电话</th><th>邮箱</th><th>微信</th><th>店铺链接</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table>
    </section>
    """


def supplier_master_row(row: sqlite3.Row) -> str:
    return f"""
    <tr>
      <td>{esc(row['name'])}</td><td>{esc(row['contact_name'])}</td><td>{esc(row['phone'])}</td><td>{esc(row['email'])}</td><td>{esc(row['wechat'])}</td><td>{esc(row['store_url'])}</td>
      <td>
        <details class="action-drawer"><summary title="编辑供应商" aria-label="编辑供应商">✎</summary>{supplier_form(f"/basic-data/suppliers/{row['id']}/edit", row)}</details>
        <form method="post" action="/basic-data/suppliers/{row['id']}/delete" class="icon-form"><button class="icon-button danger" type="submit" title="删除供应商" aria-label="删除供应商" onclick="return confirm('删除这个供应商？')">×</button></form>
      </td>
    </tr>
    """


def supplier_form(action: str, row: sqlite3.Row | None = None) -> str:
    categories = supplier_categories_text(row["usual_categories"]) if row else ""
    return f"""
    <form method="post" action="{action}" class="form-grid">
      <label>名称<input name="name" required value="{esc(row['name'] if row else '')}"></label>
      <label>联系人<input name="contact_name" value="{esc(row['contact_name'] if row else '')}"></label>
      <label>电话<input name="phone" value="{esc(row['phone'] if row else '')}"></label>
      <label>邮箱<input name="email" value="{esc(row['email'] if row else '')}"></label>
      <label>微信<input name="wechat" value="{esc(row['wechat'] if row else '')}"></label>
      <label>地址<input name="address" value="{esc(row['address'] if row else '')}"></label>
      <label>注册号<input name="business_id" value="{esc(row['business_id'] if row else '')}"></label>
      <label>1688/店铺链接<input name="store_url" value="{esc(row['store_url'] if row else '')}"></label>
      <label>常用品类<input name="usual_categories" value="{esc(categories)}"></label>
      <label>备注<input name="notes" value="{esc(row['notes'] if row else '')}"></label>
      <button type="submit">保存供应商</button>
    </form>
    """


def supplier_categories_text(value: str) -> str:
    try:
        categories = json.loads(value or "[]")
    except json.JSONDecodeError:
        return value
    return ", ".join(str(item) for item in categories) if isinstance(categories, list) else str(value)


def basic_data_consignees(consignees: list[sqlite3.Row]) -> str:
    rows = "".join(consignee_master_row(row) for row in consignees) or '<tr><td colspan="7" class="empty">暂无客户</td></tr>'
    return f"""
    <section class="panel master-data-scroll" id="consignees">
      <div class="panel-head"><h2>客户</h2><details class="action-drawer"><summary title="新增客户" aria-label="新增客户">+</summary>{consignee_form("/basic-data/consignees", None)}</details></div>
      <table><thead><tr><th>公司</th><th>联系人</th><th>电话</th><th>邮箱</th><th>税号</th><th>默认目的港</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table>
    </section>
    """


def consignee_master_row(row: sqlite3.Row) -> str:
    return f"""
    <tr>
      <td>{esc(row['company_name'])}</td><td>{esc(row['contact_name'])}</td><td>{esc(row['phone'])}</td><td>{esc(row['email'])}</td><td>{esc(row['tax_id'])}</td><td>{esc(row['default_destination_port'])}</td>
      <td>
        <details class="action-drawer"><summary title="编辑客户" aria-label="编辑客户">✎</summary>{consignee_form(f"/basic-data/consignees/{row['id']}/edit", None, row)}</details>
        <form method="post" action="/basic-data/consignees/{row['id']}/delete" class="icon-form"><button class="icon-button danger" type="submit" title="删除客户" aria-label="删除客户" onclick="return confirm('删除这个客户？')">×</button></form>
      </td>
    </tr>
    """


def basic_data_warehouses(warehouses: list[sqlite3.Row]) -> str:
    rows = "".join(warehouse_master_row(row) for row in warehouses) or '<tr><td colspan="7" class="empty">暂无仓库</td></tr>'
    return f"""
    <section class="panel master-data-scroll" id="warehouses">
      <div class="panel-head"><h2>仓库</h2><details class="action-drawer"><summary title="新增仓库" aria-label="新增仓库">+</summary>{warehouse_form("/basic-data/warehouses")}</details></div>
      <table><thead><tr><th>类型</th><th>名称</th><th>联系人</th><th>电话</th><th>地址</th><th>备注</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table>
    </section>
    """


def warehouse_master_row(row: sqlite3.Row) -> str:
    return f"""
    <tr>
      <td>{esc(warehouse_type_label(row['type']))}</td><td>{esc(row['name'])}</td><td>{esc(row['contact_name'])}</td><td>{esc(row['phone'])}</td><td>{esc(row['address'])}</td><td>{esc(row['notes'])}</td>
      <td>
        <details class="action-drawer"><summary title="编辑仓库" aria-label="编辑仓库">✎</summary>{warehouse_form(f"/basic-data/warehouses/{row['id']}/edit", row)}</details>
        <form method="post" action="/basic-data/warehouses/{row['id']}/delete" class="icon-form"><button class="icon-button danger" type="submit" title="删除仓库" aria-label="删除仓库" onclick="return confirm('删除这个仓库？')">×</button></form>
      </td>
    </tr>
    """


def basic_data_company(seller: dict, defaults: dict, reminders: dict) -> str:
    fields = [
        ("seller_company_name", "卖方公司", seller.get("company_name", "")),
        ("seller_address", "卖方地址", seller.get("address", "")),
        ("seller_phone", "卖方电话", seller.get("phone", "")),
        ("seller_email", "卖方邮箱", seller.get("email", "")),
        ("seller_tax_or_business_id", "税号/注册号", seller.get("tax_or_business_id", "")),
        ("seller_bank_info", "银行信息", seller.get("bank_info", "")),
        ("origin_country", "默认起运国家", defaults.get("origin_country", "")),
        ("origin_port", "默认起运港", defaults.get("origin_port", "")),
        ("purchase_currency", "默认采购币种", defaults.get("purchase_currency", "")),
        ("sales_currency", "默认销售币种", defaults.get("sales_currency", "")),
        ("lead_days", "提醒提前天数", reminders.get("lead_days", 3)),
    ]
    body = "".join(f'<label>{label}<input name="{name}" value="{esc(value)}"></label>' for name, label, value in fields)
    return f"""
    <section class="panel pad master-data-scroll" id="company">
      <div class="panel-head"><h2>公司信息</h2></div>
      <form method="post" action="/basic-data/settings" class="form-grid">{body}<button type="submit">保存公司信息</button></form>
    </section>
    """


def basic_data_llm(deepseek: dict) -> str:
    status = llm_config_status(deepseek)
    last_status = deepseek.get("last_test_status") or "未验证"
    last_message = deepseek.get("last_test_message") or "保存配置后点击“保存并验证”确认真实可用。"
    last_at = deepseek.get("last_test_at") or ""
    return f"""
    <section class="panel pad master-data-scroll" id="llm">
      <div class="panel-head"><h2>大模型配置</h2><span>{esc(status)}</span></div>
      <div class="summary-grid">
        <article><span>配置状态</span><strong>{esc(status)}</strong></article>
        <article><span>当前模型</span><strong>{esc(deepseek.get('model', 'deepseek-chat'))}</strong></article>
        <article><span>验证状态</span><strong>{esc(last_status)}</strong></article>
        <article><span>验证时间</span><strong>{esc(last_at or '暂无')}</strong></article>
      </div>
      <p class="hint">{esc(last_message)}</p>
      <form method="post" action="/basic-data/llm-settings" class="form-grid">
        <label>DeepSeek API Key<input name="deepseek_api_key" type="password" placeholder="留空则保留已保存 Key"></label>
        <label>模型<input name="deepseek_model" value="{esc(deepseek.get('model', 'deepseek-chat'))}"></label>
        <label>API 地址<input name="deepseek_api_base" value="{esc(deepseek.get('api_base', 'https://api.deepseek.com'))}" placeholder="https://api.deepseek.com"></label>
        <label>超时秒数<input name="deepseek_timeout_seconds" type="number" min="1" value="{esc(deepseek.get('timeout_seconds', 30))}"></label>
        <label class="checkbox"><input name="clear_deepseek_api_key" type="checkbox" value="1">清除本地保存的 API Key</label>
        <button type="submit">保存配置</button>
        <button type="submit" name="validate" value="1">保存并验证</button>
      </form>
    </section>
    """


def llm_config_status(deepseek: dict) -> str:
    if os.getenv("DEEPSEEK_API_KEY"):
        return "已配置（环境变量）"
    if deepseek.get("api_key"):
        return "已配置（本地设置）"
    return "未配置"


def _warehouse_inventory_row(row: dict, hidden_context: str, exception_options: str) -> str:
    form_id = f"receive-{row['goods_line_id']}"
    resolve = ""
    if row["logistics_status"] == "exception":
        resolve = (
            f"<form method='post' action='/receiving/resolve' class='inline-form'>"
            f"<input type='hidden' name='goods_line_id' value='{row['goods_line_id']}'>"
            f"{hidden_context}"
            f"<button class='icon-button' type='submit' title='解除异常' aria-label='解除异常'>✓</button></form>"
        )
    return f"""
    <tr>
      <td>{esc(row['order_no'])}</td>
      <td><a href="/goods-lines/{row['goods_line_id']}/edit">{esc(row['customs_en_name'] or row['cn_name'])}</a></td>
      <td>{esc(row['supplier_name'])}</td>
      <td>{esc(row['shipping_mark'])}</td>
      <td>{esc(row['tracking_numbers'])}</td>
      <td>{esc(row['carton_count'])}</td>
      <td>{esc(row['received_cartons'])}</td>
      <td>{esc(row['package_condition'])}</td>
      <td><span class="status blue">{esc(logistics_status_label(normalize_logistics_status(row['logistics_status'])))}</span> {esc(row['latest_exception'])} {resolve}</td>
      <td>{esc(row['last_receiving_at'])}</td>
      <td>
        <details class="action-drawer"><summary title="登记到货" aria-label="登记到货">+</summary>
          <form id="{form_id}" method="post" action="/receiving/record" class="form-grid compact-form" enctype="multipart/form-data">
            <input type="hidden" name="goods_line_id" value="{row['goods_line_id']}">
            {hidden_context}
            <label>国内物流单号<input name="domestic_tracking_no" value="{esc(row['tracking_numbers'])}"></label>
            <label>到货箱数<input name="received_carton_count" type="number" min="0" required></label>
            <label>包装情况<input name="package_condition" placeholder="完好/破损"></label>
            <label>到货异常<select name="arrival_exception_type">{exception_options}</select></label>
            <label>到货照片<input name="receiving_photo" type="file" accept="image/*"></label>
            <label>到货照片路径(可选)<input name="receiving_photo_path" placeholder="/path/photo.jpg"></label>
            <button type="submit">保存</button>
          </form>
        </details>
      </td>
    </tr>
    """


def excel_finance_page(user: sqlite3.Row, query: dict[str, list[str]] | None = None, message: str = "", errors: list[str] | None = None) -> str:
    query = query or {}
    selected_order_id = int_or_none(query.get("import_order_id", [""])[0])
    conn = ensure_database()
    try:
        orders = conn.execute("SELECT id, order_no, sales_currency FROM import_orders ORDER BY created_at DESC").fetchall()
        if selected_order_id is None and orders:
            selected_order_id = int(orders[0]["id"])
        selected_order = conn.execute("SELECT * FROM import_orders WHERE id = ?", (selected_order_id,)).fetchone() if selected_order_id else None
        goods = conn.execute(
            """
            SELECT goods_lines.*, import_orders.order_no, suppliers.name AS supplier_name
            FROM goods_lines
            JOIN import_orders ON import_orders.id = goods_lines.import_order_id
            LEFT JOIN suppliers ON suppliers.id = goods_lines.supplier_id
            WHERE goods_lines.import_order_id = ?
            ORDER BY goods_lines.id DESC
            """,
            (selected_order_id,),
        ).fetchall()
        finance_rows = conn.execute(
            """
            SELECT finance_lines.*, import_orders.order_no, goods_lines.sku_or_model
            FROM finance_lines
            JOIN import_orders ON import_orders.id = finance_lines.import_order_id
            LEFT JOIN goods_lines ON goods_lines.id = finance_lines.goods_line_id
            WHERE finance_lines.import_order_id = ?
            ORDER BY finance_lines.created_at DESC
            """,
            (selected_order_id,),
        ).fetchall()
        default_sales_currency = get_setting(conn, "defaults").get("sales_currency", "EUR")
        base_currency = (selected_order["sales_currency"] if selected_order else "") or default_sales_currency
        summary = calculate_profit(conn, import_order_id=selected_order_id, base_currency=base_currency) if selected_order_id else None
    finally:
        conn.close()
    if not orders:
        return page("成本利润", "<section class='panel pad'>暂无进口订单</section>", user=user)
    notice = f"<p class='notice'>{esc(message)}</p>" if message else ""
    error_html = "".join(f"<li>{esc(error)}</li>" for error in (errors or []))
    errors_block = f"<section class='panel pad'><h2>导入错误</h2><ul class='errors'>{error_html}</ul></section>" if error_html else ""
    order_options = "".join(
        f"<option value='{order['id']}'{' selected' if order['id'] == selected_order_id else ''}>{esc(order['order_no'])}</option>"
        for order in orders
    )
    goods_options = "<option value=''></option>" + "".join(
        f"<option value='{line['id']}'>#{line['id']} {esc(line['sku_or_model'] or line['customs_en_name'] or line['cn_name'])}</option>"
        for line in goods
    )
    cost_options = "".join(f"<option value='{esc(kind)}'>{esc(kind)}</option>" for kind in sorted(COST_TYPES))
    charge_options = "".join(f"<option value='{esc(kind)}'>{esc(kind)}</option>" for kind in sorted(CHARGE_TYPES))
    quote_total = quote_total_by_currency(goods)
    cost_rows = finance_rows_by_kind(finance_rows, LINE_COST, goods_options, cost_options, charge_options)
    charge_rows = finance_rows_by_kind(finance_rows, LINE_CHARGE, goods_options, cost_options, charge_options)
    charge_action = f"""
    <details class="action-drawer"><summary title="新增客户收费/添加入账" aria-label="新增客户收费">+</summary>
      {finance_line_form("/finance/line", selected_order_id, goods_options, cost_options, charge_options, LINE_CHARGE)}
    </details>
    """
    finance_actions = f"""
    <section class="panel pad">
      <div class="action-row">
        <details class="action-drawer"><summary title="新增成本" aria-label="新增成本">+</summary>
          <div class="drawer-stack">
            <h2>手动添加成本</h2>
            {finance_line_form("/finance/line", selected_order_id, goods_options, cost_options, charge_options, LINE_COST)}
            <h2>上传 Excel 成本</h2>
            <form method="post" action="/finance/cost-import" class="form-grid" enctype="multipart/form-data">
              <input type="hidden" name="import_order_id" value="{selected_order_id}">
              <label>成本 Excel<input name="file" type="file" accept=".xlsx" required></label>
              <button type="submit">上传导入</button>
            </form>
          </div>
        </details>
      </div>
    </section>
    """
    summary_cards = "".join(
        f"<article><span>{esc(label)}</span><strong>{esc(value)}</strong></article>"
        for label, value in [
            ("订单号", selected_order["order_no"] if selected_order else ""),
            ("总成本", money(summary["total_cost"] if summary else 0)),
            ("客户收费", money(summary["total_charge"] if summary else 0)),
            ("货物销售总值", quote_total),
            ("利润", money(summary["profit"] if summary else 0)),
            ("基准币", summary["base_currency"] if summary else base_currency),
        ]
    )
    goods_detail_link = ""
    if selected_order_id:
        goods_detail_link = f"""
        <div class="action-row">
          <a class="button-link" href="/tracking?import_order_id={selected_order_id}">查看货物详情</a>
          {ai_intake_link(selected_order_id, "AI检查利润风险")}
        </div>
        """
    return page(
        "成本利润",
        f"""
        <section class="toolbar"><div><h1>成本利润</h1><p>固定模板导入、导出、报价和利润估算</p></div></section>
        {notice}
        {errors_block}
        <section class="panel pad">
          <form method="get" action="/excel-finance" class="filter-bar">
            <label>进口订单<select name="import_order_id" onchange="this.form.submit()">{order_options}</select></label>
          </form>
        </section>
        <section class="panel pad"><div class="panel-head"><h2>订单利润总览</h2><span>{esc(base_currency)}</span></div><div class="summary-grid">{summary_cards}</div>{goods_detail_link}</section>
        <section class="two-col">
          <section class="panel pad">
            <h2>Excel 导入</h2>
            <form method="post" action="/excel/customer-import" class="stack">
              <label>客户采购清单 .xlsx 路径<input name="path" placeholder="/Users/.../customer.xlsx" required></label>
              <button type="submit">导入客户清单</button>
            </form>
            <form method="post" action="/excel/package-import" class="stack">
              <label>供应商包装物流 .xlsx 路径<input name="path" placeholder="/Users/.../supplier.xlsx" required></label>
              <button type="submit">导入包装物流</button>
            </form>
          </section>
          <section class="panel pad">
            <h2>Excel 导出</h2>
            <div class="link-list">
              <a href="/exports/import-orders.xlsx">Import Orders</a>
              <a href="/exports/goods-lines.xlsx">Goods Lines</a>
              <a href="/exports/finance-lines.xlsx">Finance Lines</a>
            </div>
          </section>
        </section>
        {finance_actions}
        <section class="panel"><div class="panel-head"><h2>成本明细</h2><span>采购、国内物流、仓储等</span></div><table><thead><tr><th>SKU</th><th>科目</th><th>金额</th><th>币种</th><th>汇率</th><th>日期</th><th>备注</th><th>操作</th></tr></thead><tbody>{cost_rows}</tbody></table></section>
        <section class="panel"><div class="panel-head"><h2>客户收费明细</h2><span>产品销售、运费服务、入账记录</span>{charge_action}</div><table><thead><tr><th>SKU</th><th>科目</th><th>入账金额</th><th>币种</th><th>汇率</th><th>入账日期</th><th>备注</th><th>操作</th></tr></thead><tbody>{charge_rows}</tbody></table></section>
        <section class="panel pad"><h2>汇率/币种提示</h2><p>利润以当前进口订单销售币种为基准；如订单未设置销售币种，则使用系统默认销售币种。成本和收费按手动填写的折算汇率进入汇总。</p></section>
        """,
        user=user,
    )


def shipping_docs_page(user: sqlite3.Row, query: dict[str, list[str]] | None = None, message: str = "", blockers: list[dict] | None = None) -> str:
    query = query or {}
    selected_order_id = int_or_none(query.get("import_order_id", [""])[0])
    conn = ensure_database()
    try:
        orders = conn.execute("SELECT id, order_no FROM import_orders ORDER BY created_at DESC").fetchall()
        if selected_order_id is None and orders:
            selected_order_id = int(orders[0]["id"])
        containers = conn.execute(
            """
            SELECT containers.*, import_orders.order_no
            FROM containers
            JOIN import_orders ON import_orders.id = containers.import_order_id
            WHERE containers.import_order_id = ?
            ORDER BY containers.created_at DESC
            """,
            (selected_order_id,),
        ).fetchall()
        goods = conn.execute(
            """
            SELECT goods_lines.id, goods_lines.import_order_id, goods_lines.customs_en_name, goods_lines.sku_or_model, import_orders.order_no
            FROM goods_lines
            JOIN import_orders ON import_orders.id = goods_lines.import_order_id
            WHERE goods_lines.import_order_id = ?
            ORDER BY goods_lines.id DESC
            """,
            (selected_order_id,),
        ).fetchall()
        docs = conn.execute(
            """
            SELECT documents.*, import_orders.order_no
            FROM documents
            JOIN import_orders ON import_orders.id = documents.import_order_id
            WHERE documents.import_order_id = ?
            ORDER BY documents.generated_at DESC
            """,
            (selected_order_id,),
        ).fetchall()
        recommendation = recommend_container(conn, selected_order_id) if selected_order_id else None
        loading_rows = loading_list(conn, selected_order_id) if selected_order_id else []
        compliance_files = document_compliance_files(conn, selected_order_id)
        readiness = document_readiness_blockers(conn, selected_order_id) if blockers is None else blockers
    finally:
        conn.close()
    if not orders:
        return page("海运单证", "<section class='panel pad'>暂无进口订单</section>", user=user)
    selected_order = next((order for order in orders if order["id"] == selected_order_id), orders[0])
    order_options = "".join(
        f"<option value='{order['id']}'{' selected' if order['id'] == selected_order_id else ''}>{esc(order['order_no'])}</option>"
        for order in orders
    )
    container_options = "".join(
        f"<option value='{container['id']}'>{esc(container['container_number'])}</option>"
        for container in containers
    )
    goods_options = "".join(
        f"<option value='{line['id']}'>#{line['id']} {esc(line['sku_or_model'] or line['customs_en_name'])}</option>"
        for line in goods
    )
    compliance_goods_options = "<option value=''>进口订单</option>" + goods_options
    container_type_options = "".join(f"<option value='{esc(value)}'>{esc(value)}</option>" for value in CONTAINER_ORDER)
    compliance_category_options = "".join(
        f"<option value='{esc(value)}'>{esc(label)}</option>" for value, label in COMPLIANCE_FILE_CATEGORIES.items()
    )
    doc_type_options = "".join(
        f"<option value='{esc(value)}'>{esc(document_type_label(value))}</option>" for value in sorted(DOCUMENT_TYPES)
    )
    notice = f"<p class='notice'>{esc(message)}</p>" if message else ""
    blocker_html = "".join(
        f"<li>{esc(blocker.get('target'))} {esc(blocker.get('id', ''))} · {esc(field_label(str(blocker.get('field', ''))))}</li>"
        for blocker in readiness
    )
    blocker_block = f"<ul class='errors'>{blocker_html}</ul>" if blocker_html else "<p class='notice'>正式单证资料已齐备</p>"
    doc_ai_actions = f"""
    <div class="action-row">
      {ai_intake_link(selected_order_id, "AI检查单证阻塞项")}
      {ai_intake_link(selected_order_id, "AI生成单证草稿")}
    </div>
    """
    recommendation_rows = (
        f"<tr><td>{esc(selected_order['order_no'])}</td><td>{money(recommendation['total_cbm'])}</td><td>{money(recommendation['total_gross_weight'])}</td><td>{esc(recommendation['recommended_type'])}</td><td><a href='/exports/loading-list.xlsx?import_order_id={selected_order_id}'>Loading List</a></td></tr>"
        if recommendation else '<tr><td colspan="5" class="empty">暂无订单</td></tr>'
    )
    container_rows = "".join(
        f"<tr><td>{esc(row['container_type'])}</td><td>{esc(row['container_number'])}</td><td>{esc(row['seal_number'])}</td><td>{esc(row['loading_date'])}</td></tr>"
        for row in containers
    ) or '<tr><td colspan="4" class="empty">暂无集装箱</td></tr>'
    loading_html = "".join(
        f"<tr><td>{esc(row['container_number'])}</td><td>{esc(row['customs_en_name'])}</td><td>{esc(row['loaded_carton_count'])}</td><td>{money(row['cbm'])}</td><td>{money(row['gross_weight'])}</td></tr>"
        for row in loading_rows
    ) or '<tr><td colspan="5" class="empty">暂无装箱记录</td></tr>'
    invoice_rows = document_version_rows([row for row in docs if row["document_type"] == DOC_COMMERCIAL_INVOICE])
    packing_rows = document_version_rows([row for row in docs if row["document_type"] == DOC_PACKING_LIST])
    compliance_rows = "".join(
        f"<tr><td>{esc(file_owner_label(row['owner_type']))}</td><td>{esc(compliance_file_category_label(row['file_category']))}</td><td>{esc(row['file_name'])}</td><td>{esc(row['uploaded_at'])}</td></tr>"
        for row in compliance_files
    ) or '<tr><td colspan="4" class="empty">暂无合规文件。产地证、检验证书等应上传/跟踪，不由系统生成。</td></tr>'
    return page(
        "海运单证",
        f"""
        <section class="toolbar"><div><h1>海运单证</h1><p>集装箱、装箱记录、Loading List、商业发票和装箱单</p></div></section>
        {notice}
        <section class="panel pad">
          <form method="get" action="/shipping-docs" class="filter-bar">
            <label>进口订单<select name="import_order_id" onchange="this.form.submit()">{order_options}</select></label>
          </form>
        </section>
        <section class="panel pad document-blocker-scroll"><div class="panel-head"><h2>单证阻塞项</h2><span>{esc(selected_order['order_no'])}</span></div>{blocker_block}{doc_ai_actions}</section>
        <section class="panel"><div class="panel-head"><h2>柜型与 Loading List</h2><span>当前估算</span></div><table><thead><tr><th>订单号</th><th>CBM</th><th>毛重</th><th>推荐柜型</th><th>导出</th></tr></thead><tbody>{recommendation_rows}</tbody></table></section>
        <section class="panel pad">
          <div class="action-row">
            <details class="action-drawer"><summary>新增集装箱</summary>
            <form method="post" action="/containers" class="stack">
              <input type="hidden" name="import_order_id" value="{selected_order_id}">
              <label>柜型<select name="container_type">{container_type_options}</select></label>
              <label>柜号<input name="container_number" required></label>
              <label>封号<input name="seal_number" required></label>
              <label>装柜日期<input name="loading_date" type="date"></label>
              <label>海运/柜费成本<input name="sea_freight_amount" type="number" step="0.01"></label>
              <label>成本币种<input name="sea_freight_currency" value="EUR"></label>
              <label>折算到基准币汇率<input name="sea_freight_exchange_rate" type="number" step="0.0001" value="1"></label>
              <label>备注<input name="notes"></label>
              <button type="submit">创建集装箱</button>
            </form>
            </details>
            <details class="action-drawer"><summary>记录装箱</summary>
            <form method="post" action="/loading-records" class="stack" enctype="multipart/form-data">
              <input type="hidden" name="import_order_id" value="{selected_order_id}">
              <label>集装箱<select name="container_id">{container_options}</select></label>
              <label>商品行<select name="goods_line_id">{goods_options}</select></label>
              <label>装入箱数<input name="loaded_carton_count" type="number" min="0" required></label>
              <label>装箱照片<input name="loading_photo" type="file" accept="image/*"></label>
              <label>照片路径(可选)<input name="loading_photo_path" placeholder="/path/photo.jpg"></label>
              <label>备注<input name="notes"></label>
              <button type="submit">记录装箱</button>
            </form>
            </details>
          </div>
        </section>
        <section class="panel pad">
          <h2>生成单证</h2>
          <form method="post" action="/documents/generate" class="form-grid">
            <input type="hidden" name="import_order_id" value="{selected_order_id}">
            <label>单证类型<select name="document_type">{doc_type_options}</select></label>
            <label>状态<select name="status"><option value="draft">draft</option><option value="final">final</option></select></label>
            <button type="submit">生成</button>
          </form>
        </section>
        <section class="panel"><div class="panel-head"><h2>集装箱</h2><span>实际柜号</span></div><table><thead><tr><th>柜型</th><th>柜号</th><th>封号</th><th>装柜日期</th></tr></thead><tbody>{container_rows}</tbody></table></section>
        <section class="panel"><div class="panel-head"><h2>装箱记录</h2><span>装箱明细</span></div><table><thead><tr><th>柜号</th><th>货物项</th><th>箱数</th><th>CBM</th><th>毛重</th></tr></thead><tbody>{loading_html}</tbody></table></section>
        <section class="panel"><div class="panel-head"><h2>商业发票版本 (Commercial Invoice)</h2><span>历史版本</span></div><table><thead><tr><th>版本</th><th>状态</th><th>编号</th><th>下载</th></tr></thead><tbody>{invoice_rows}</tbody></table></section>
        <section class="panel"><div class="panel-head"><h2>装箱单版本 (Packing List)</h2><span>历史版本</span></div><table><thead><tr><th>版本</th><th>状态</th><th>编号</th><th>下载</th></tr></thead><tbody>{packing_rows}</tbody></table></section>
        <section class="panel">
          <div class="panel-head"><h2>合规文件列表</h2><details class="action-drawer"><summary>上传/登记合规文件</summary>
            <form method="post" action="/compliance-files" class="form-grid" enctype="multipart/form-data">
              <input type="hidden" name="import_order_id" value="{selected_order_id}">
              <label>所属对象<select name="goods_line_id">{compliance_goods_options}</select></label>
              <label>文件类型<select name="file_category">{compliance_category_options}</select></label>
              <label>上传文件<input name="file" type="file"></label>
              <label>文件路径(可选)<input name="path" placeholder="/Users/.../certificate.pdf"></label>
              <button type="submit">保存文件</button>
            </form>
          </details></div>
          <table><thead><tr><th>所属对象</th><th>文件类型</th><th>文件名</th><th>上传时间</th></tr></thead><tbody>{compliance_rows}</tbody></table>
        </section>
        """,
        user=user,
    )


def document_type_label(value: str) -> str:
    return {
        DOC_COMMERCIAL_INVOICE: "商业发票 (Commercial Invoice)",
        DOC_PACKING_LIST: "装箱单 (Packing List)",
    }.get(value, value)


def document_version_rows(rows: list[sqlite3.Row]) -> str:
    return "".join(
        f"<tr><td>V{esc(row['version'])}</td><td>{esc(row['status'])}</td><td>{esc(row['document_number'])}</td><td><a href='/downloads/document/{row['id']}/xlsx'>xlsx</a> · <a href='/downloads/document/{row['id']}/pdf'>pdf</a></td></tr>"
        for row in rows
    ) or '<tr><td colspan="4" class="empty">暂无版本</td></tr>'


def document_readiness_blockers(conn: sqlite3.Connection, import_order_id: int | None) -> list[dict]:
    if import_order_id is None:
        return []
    goods = conn.execute("SELECT id FROM goods_lines WHERE import_order_id = ? ORDER BY id", (import_order_id,)).fetchall()
    blockers = []
    for row in goods:
        check = check_goods_line_stage(conn, goods_line_id=row["id"], stage=STAGE_FINAL_DOCUMENTS)
        blockers.extend({"target": "货物项", "id": row["id"], "field": field} for field in check.blockers)
    return blockers


def document_compliance_files(conn: sqlite3.Connection, import_order_id: int | None) -> list[sqlite3.Row]:
    if import_order_id is None:
        return []
    return list(conn.execute(
        """
        SELECT files.*
        FROM files
        WHERE (owner_type = 'import_order' AND owner_id = ?)
           OR (
             owner_type = 'goods_line'
             AND owner_id IN (SELECT id FROM goods_lines WHERE import_order_id = ?)
           )
        ORDER BY uploaded_at DESC
        """,
        (import_order_id, import_order_id),
    ))


def shipping_docs_redirect(form: dict[str, str]) -> str:
    return f"/shipping-docs?import_order_id={quote(form.get('import_order_id', ''))}"


def finance_redirect(form: dict[str, str]) -> str:
    import_order_id = form.get("import_order_id", "")
    if not import_order_id and form.get("goods_line_id"):
        conn = ensure_database()
        try:
            row = conn.execute("SELECT import_order_id FROM goods_lines WHERE id = ?", (int(form["goods_line_id"]),)).fetchone()
            import_order_id = str(row["import_order_id"]) if row else ""
        finally:
            conn.close()
    return f"/excel-finance?import_order_id={quote(import_order_id)}"


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def page(title: str, body: str, *, user: sqlite3.Row | None = None, chrome: bool = True) -> str:
    if not chrome:
        shell = body
    else:
        nav = navigation(user["role"] if user else "", CURRENT_PATH)
        utilities = utility_menu(user["role"] if user else "")
        shell = f"""
        <div class="app">
          <aside>
            <div class="brand"><strong>CargoPilot</strong><span>货运领航</span></div>
            {nav}
          </aside>
          <div class="workspace">
            <header>{utilities}<span>{html.escape(user['email']) if user else ''}</span><a href="/logout">退出</a></header>
            <main>{body}</main>
          </div>
        </div>
        """
    return f"""<!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{html.escape(title)} - CargoPilot</title>
        <link rel="stylesheet" href="/static/app.css">
      </head>
      <body>{shell}<script>
      document.addEventListener("click", (event) => {{
        const drawer = event.target.closest(".action-drawer[open]");
        if (drawer && event.target === drawer) drawer.open = false;
      }});
      document.addEventListener("keydown", (event) => {{
        if (event.key === "Escape") document.querySelectorAll(".action-drawer[open]").forEach((drawer) => drawer.open = false);
      }});
      </script></body>
    </html>"""


def navigation(role: str, current_path: str = "/dashboard") -> str:
    items = [("Dashboard", "/dashboard"), ("订单详情", "/orders"), ("货物详情", "/tracking"), ("仓库盘点", "/receiving")]
    if role == ROLE_ADMIN:
        items += [("订单智能体", "/order-agent"), ("AI资料收集箱", "/ai-intake"), ("海运单证", "/shipping-docs"), ("成本利润", "/excel-finance"), ("基础资料", "/basic-data")]
    return '<nav>' + "".join(nav_link(label, href, current_path) for label, href in items) + "</nav>"


def nav_link(label: str, href: str, current_path: str) -> str:
    active = ' class="active"' if nav_active(current_path, href) else ""
    return f'<a href="{href}"{active}>{label}</a>'


def nav_active(current_path: str, href: str) -> bool:
    if href == "/dashboard":
        return current_path in {"/", "/dashboard"}
    if current_path.startswith("/goods-lines/"):
        return href == "/tracking"
    return current_path == href or current_path.startswith(f"{href}/")


def utility_menu(role: str) -> str:
    return ""


def role_label(role: str) -> str:
    return "管理员" if role == ROLE_ADMIN else "仓库员"


def order_status_inline(card: dict, user: sqlite3.Row) -> str:
    if user["role"] != ROLE_ADMIN:
        return f"<span class='status {esc(card['status_color'])}'>{esc(order_status_label(card['order_status']))}</span>"
    options = "".join(
        f"<option value='{esc(status)}'{' selected' if status == card['order_status'] else ''}>{esc(order_status_label(status))}</option>"
        for status in ORDER_STATUS_COLORS
    )
    return f"""
    <form method="post" action="/orders/status" class="inline-status">
      <input type="hidden" name="order_id" value="{card['id']}">
      <select name="order_status" onchange="this.form.submit()">{options}</select>
    </form>
    """


def goods_status_inline(row: dict | sqlite3.Row, user: sqlite3.Row, return_to: str = "") -> str:
    selected = normalize_logistics_status(row["logistics_status"])
    if user["role"] not in {ROLE_ADMIN, ROLE_WAREHOUSE}:
        return f"<span class='status blue'>{esc(logistics_status_label(selected))}</span>"
    options = "".join(
        f"<option value='{esc(status)}'{' selected' if status == selected else ''}>{esc(logistics_status_label(status))}</option>"
        for status in GOODS_LOGISTICS_STATUSES
    )
    hidden_return = f'<input type="hidden" name="return_to" value="{esc(return_to)}">' if return_to else ""
    return f"""
    <form method="post" action="/tracking/status" class="inline-status">
      <input type="hidden" name="goods_line_id" value="{row['id']}">
      <input type="hidden" name="import_order_id" value="{row['import_order_id']}">
      {hidden_return}
      <select name="logistics_status" onchange="this.form.submit()">{options}</select>
    </form>
    """


def order_status_label(status: str) -> str:
    return ORDER_STATUS_LABELS.get(status, status)


def logistics_point_label(value: str) -> str:
    return LOGISTICS_POINT_LABELS.get(value, value)


def logistics_status_label(value: str) -> str:
    return LOGISTICS_STATUS_LABELS.get(value, value)


def normalize_logistics_status(value: str) -> str:
    return {"supplier_preparing": "ordered", "checked": "received_at_warehouse"}.get(value, value)


def compliance_status_label(value: str) -> str:
    return COMPLIANCE_STATUS_LABELS.get(value, value)


def warehouse_type_label(value: str) -> str:
    return WAREHOUSE_TYPE_LABELS.get(value, value)


def compliance_file_category_label(value: str) -> str:
    return COMPLIANCE_FILE_CATEGORIES.get(value, value)


def file_owner_label(value: str) -> str:
    return {"import_order": "进口订单", "goods_line": "货物项"}.get(value, value)


def reminder_href(item: dict) -> str:
    if item.get("type") == "missing_document_fields":
        return f"/shipping-docs?import_order_id={item['import_order_id']}"
    return f"/tracking?import_order_id={item['import_order_id']}"


def _order_row(card: dict) -> str:
    return f"""
    <tr>
      <td><a href="/orders/{card['id']}">{html.escape(str(card['order_no']))}</a></td>
      <td>{html.escape(str(card['consignee']))}</td>
      <td>{html.escape(str(card['destination_port']))}</td>
      <td><span class="status {html.escape(card['status_color'])}">{html.escape(order_status_label(str(card['order_status'])))}</span></td>
      <td>{html.escape(logistics_point_label(str(card['current_logistics_point'])))}</td>
      <td><progress max="100" value="{card['order_stage_progress']}"></progress> {card['order_stage_progress']}%</td>
      <td>{html.escape(str(card['expected_loading_date'] or ''))}</td>
      <td><a href="/tracking?import_order_id={card['id']}&exception_only=1">{card['exception_count']}</a></td>
      <td><a href="/shipping-docs?import_order_id={card['id']}">{card['missing_data_count']}</a></td>
    </tr>
    """


def search_result_href(result: dict) -> str:
    if result["type"] == "import_order":
        return f"/orders/{result['id']}"
    if result["type"] == "goods_line":
        return f"/goods-lines/{result['id']}/edit"
    if result["type"] == "container":
        return "/shipping-docs"
    return "/dashboard"


def finance_rows_by_kind(rows: list[sqlite3.Row], line_kind: str, goods_options: str, cost_options: str, charge_options: str) -> str:
    filtered = [row for row in rows if row["line_kind"] == line_kind]
    if not filtered:
        return '<tr><td colspan="8" class="empty">暂无记录</td></tr>'
    total = sum(row["amount"] * row["exchange_rate_to_base"] for row in filtered)
    body = "".join(
        finance_row(row, goods_options, cost_options, charge_options)
        for row in filtered
    )
    return body + f'<tr><td colspan="2"><strong>合计</strong></td><td colspan="6"><strong>{money(total)}</strong></td></tr>'


def finance_row(row: sqlite3.Row, goods_options: str, cost_options: str, charge_options: str) -> str:
    form = finance_line_form(
        f"/finance-lines/{row['id']}/edit",
        int(row["import_order_id"]),
        options_with_selected(goods_options, str(row["goods_line_id"] or "")),
        options_with_selected(cost_options, str(row["line_type"])),
        options_with_selected(charge_options, str(row["line_type"])),
        str(row["line_kind"]),
        row,
    )
    return f"""
    <tr>
      <td>{esc(row['sku_or_model'])}</td>
      <td>{esc(row['line_type'])}</td>
      <td>{esc(row['amount'])}</td>
      <td>{esc(row['currency'])}</td>
      <td>{esc(row['exchange_rate_to_base'])}</td>
      <td>{esc(row['line_date'])}</td>
      <td>{esc(row['notes'])}</td>
      <td>
        <details class="action-drawer"><summary title="编辑" aria-label="编辑">✎</summary>{form}</details>
        <form method="post" action="/finance-lines/{row['id']}/delete" class="icon-form">
          <button class="icon-button danger" type="submit" title="删除" aria-label="删除" onclick="return confirm('删除这条记录？')">×</button>
        </form>
      </td>
    </tr>
    """


def finance_line_form(
    action: str,
    import_order_id: int,
    goods_options: str,
    cost_options: str,
    charge_options: str,
    line_kind: str,
    row: sqlite3.Row | None = None,
) -> str:
    type_select = (
        f"<label>成本科目<select name='cost_type'>{cost_options}</select></label>"
        if line_kind == LINE_COST
        else f"<label>收费科目<select name='charge_type'>{charge_options}</select></label>"
    )
    title = "保存成本" if line_kind == LINE_COST else "保存客户收费"
    amount_label = "金额" if line_kind == LINE_COST else "入账金额"
    date_label = "发生日期" if line_kind == LINE_COST else "入账日期"
    return f"""
    <form method="post" action="{action}" class="form-grid">
      <input type="hidden" name="import_order_id" value="{import_order_id}">
      <input type="hidden" name="line_kind" value="{line_kind}">
      <label>货物项(可空)<select name="goods_line_id">{goods_options}</select></label>
      {type_select}
      <label>{amount_label}<input name="amount" type="number" step="0.01" required value="{esc(row['amount'] if row else '')}"></label>
      <label>币种<input name="currency" value="{esc((row['currency'] if row else '') or 'EUR')}"></label>
      <label>折算到基准币汇率<input name="exchange_rate_to_base" type="number" step="0.0001" value="{esc((row['exchange_rate_to_base'] if row else '') or '1')}"></label>
      <label>{date_label}<input name="line_date" type="date" value="{esc(row['line_date'] if row else '')}"></label>
      <label>备注<input name="notes" value="{esc(row['notes'] if row else '')}"></label>
      <button type="submit">{title}</button>
    </form>
    """


def options_with_selected(options: str, value: str) -> str:
    if not value:
        return options
    return options.replace(f"value='{esc(value)}'", f"value='{esc(value)}' selected", 1).replace(f'value="{esc(value)}"', f'value="{esc(value)}" selected', 1)


def quote_total_by_currency(goods: list[sqlite3.Row]) -> str:
    totals: dict[str, float] = {}
    for line in goods:
        if line["sales_unit_price"] is None or line["quantity"] is None:
            continue
        currency = line["sales_currency"] or "未设币种"
        totals[currency] = totals.get(currency, 0) + line["sales_unit_price"] * line["quantity"]
    return " / ".join(f"{currency} {money(total)}" for currency, total in totals.items()) or "0.00"


def _ensure_demo_users(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM users WHERE email = 'admin@example.com'").fetchone() is None:
        create_user(conn, email="admin@example.com", name="Admin", role=ROLE_ADMIN, password="admin")
    if conn.execute("SELECT 1 FROM users WHERE email = 'warehouse@example.com'").fetchone() is None:
        create_user(conn, email="warehouse@example.com", name="Warehouse", role=ROLE_WAREHOUSE, password="warehouse")


def handle_supplier_post(form: dict[str, str]) -> None:
    conn = ensure_database()
    try:
        create_supplier(conn, actor_role=ROLE_ADMIN, **supplier_values(form))
    finally:
        conn.close()


def handle_supplier_edit_post(form: dict[str, str], supplier_id: int) -> None:
    conn = ensure_database()
    try:
        update_supplier(conn, actor_role=ROLE_ADMIN, supplier_id=supplier_id, **supplier_values(form))
    finally:
        conn.close()


def handle_supplier_delete_post(supplier_id: int) -> str:
    conn = ensure_database()
    try:
        used = conn.execute("SELECT 1 FROM goods_lines WHERE supplier_id = ? LIMIT 1", (supplier_id,)).fetchone()
        if used:
            return "该供应商已关联货物项，不能删除"
        conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
        conn.commit()
        return ""
    finally:
        conn.close()


def supplier_values(form: dict[str, str]) -> dict:
    return {
        "name": form.get("name", ""),
        "contact_name": form.get("contact_name", ""),
        "phone": form.get("phone", ""),
        "email": form.get("email", ""),
        "wechat": form.get("wechat", ""),
        "address": form.get("address", ""),
        "business_id": form.get("business_id", ""),
        "store_url": form.get("store_url", ""),
        "usual_categories": [x.strip() for x in form.get("usual_categories", "").split(",") if x.strip()],
        "notes": form.get("notes", ""),
    }


def handle_consignee_post(form: dict[str, str]) -> None:
    conn = ensure_database()
    try:
        create_consignee(conn, actor_role=ROLE_ADMIN, **consignee_values(form))
    finally:
        conn.close()


def handle_consignee_edit_post(form: dict[str, str], consignee_id: int) -> None:
    conn = ensure_database()
    try:
        update_consignee(conn, actor_role=ROLE_ADMIN, consignee_id=consignee_id, **consignee_values(form))
    finally:
        conn.close()


def handle_consignee_delete_post(consignee_id: int) -> str:
    conn = ensure_database()
    try:
        used = conn.execute("SELECT 1 FROM import_orders WHERE consignee_id = ? LIMIT 1", (consignee_id,)).fetchone()
        if used:
            return "该客户已关联订单，不能删除"
        conn.execute("DELETE FROM consignees WHERE id = ?", (consignee_id,))
        conn.commit()
        return ""
    finally:
        conn.close()


def handle_order_consignee_post(form: dict[str, str]) -> None:
    handle_consignee_post(form)


def handle_order_consignee_edit_post(form: dict[str, str], consignee_id: int) -> None:
    handle_consignee_edit_post(form, consignee_id)


def handle_order_consignee_delete_post(consignee_id: int) -> str:
    return handle_consignee_delete_post(consignee_id)


def consignee_values(form: dict[str, str]) -> dict[str, str]:
    return {k: form.get(k, "") for k in [
        "company_name", "contact_name", "email", "phone", "tax_id", "address",
        "default_destination_port", "default_trade_term", "default_sales_currency",
        "document_preferences", "notes",
    ]}


def order_return_path(form: dict[str, str]) -> str:
    order_id = form.get("return_order_id") or form.get("import_order_id") or form.get("order_id")
    return f"/orders?order_id={order_id}" if order_id else "/orders"


def safe_local_path(value: str) -> str:
    return value if value.startswith("/") and not value.startswith("//") else ""


def handle_warehouse_post(form: dict[str, str]) -> None:
    conn = ensure_database()
    try:
        create_warehouse(conn, actor_role=ROLE_ADMIN, **warehouse_values(form))
    finally:
        conn.close()


def handle_warehouse_edit_post(form: dict[str, str], warehouse_id: int) -> None:
    conn = ensure_database()
    try:
        update_warehouse(conn, actor_role=ROLE_ADMIN, warehouse_id=warehouse_id, **warehouse_values(form))
    finally:
        conn.close()


def handle_warehouse_delete_post(warehouse_id: int) -> str:
    conn = ensure_database()
    try:
        used = conn.execute(
            """
            SELECT 1 FROM import_orders
            WHERE receiving_warehouse_id = ? OR port_warehouse_id = ?
            LIMIT 1
            """,
            (warehouse_id, warehouse_id),
        ).fetchone()
        if used:
            return "该仓库已关联订单，不能删除"
        conn.execute("DELETE FROM warehouses WHERE id = ?", (warehouse_id,))
        conn.commit()
        return ""
    finally:
        conn.close()


def handle_receiving_warehouse_post(form: dict[str, str]) -> int:
    conn = ensure_database()
    try:
        return create_warehouse(conn, actor_role=ROLE_ADMIN, **warehouse_values(form))
    finally:
        conn.close()


def handle_receiving_warehouse_edit_post(form: dict[str, str], warehouse_id: int) -> None:
    handle_warehouse_edit_post(form, warehouse_id)


def handle_receiving_warehouse_delete_post(warehouse_id: int) -> str:
    return handle_warehouse_delete_post(warehouse_id)


def warehouse_values(form: dict[str, str]) -> dict[str, str]:
    return {
        "type": form.get("type", WAREHOUSE_RECEIVING) or WAREHOUSE_RECEIVING,
        "name": form.get("name", ""),
        "contact_name": form.get("contact_name", ""),
        "phone": form.get("phone", ""),
        "address": form.get("address", ""),
        "notes": form.get("notes", ""),
    }


def handle_settings_post(form: dict[str, str]) -> None:
    conn = ensure_database()
    try:
        seller = get_setting(conn, "seller")
        defaults = get_setting(conn, "defaults")
        reminders = get_setting(conn, "reminders")
        deepseek = get_setting(conn, "deepseek")
        seller.update({
            "company_name": form.get("seller_company_name", ""),
            "address": form.get("seller_address", ""),
            "phone": form.get("seller_phone", ""),
            "email": form.get("seller_email", ""),
            "tax_or_business_id": form.get("seller_tax_or_business_id", ""),
            "bank_info": form.get("seller_bank_info", ""),
        })
        defaults.update({
            "origin_country": form.get("origin_country", ""),
            "origin_port": form.get("origin_port", ""),
            "purchase_currency": form.get("purchase_currency", ""),
            "sales_currency": form.get("sales_currency", ""),
        })
        reminders["lead_days"] = int(form.get("lead_days", 3) or 3)
        set_setting(conn, "seller", seller)
        set_setting(conn, "defaults", defaults)
        set_setting(conn, "reminders", reminders)
    finally:
        conn.close()


def handle_llm_settings_post(form: dict[str, str]) -> None:
    conn = ensure_database()
    try:
        deepseek = get_setting(conn, "deepseek")
        deepseek.update({
            "model": form.get("deepseek_model", "deepseek-chat") or "deepseek-chat",
            "api_base": normalize_deepseek_api_base(form.get("deepseek_api_base", "https://api.deepseek.com") or "https://api.deepseek.com"),
            "timeout_seconds": int(form.get("deepseek_timeout_seconds", 30) or 30),
        })
        if form.get("clear_deepseek_api_key") == "1":
            deepseek["api_key"] = ""
        elif form.get("deepseek_api_key"):
            deepseek["api_key"] = form["deepseek_api_key"]
        if form.get("validate") == "1":
            result = test_deepseek_connection(llm_runtime_config(deepseek))
            deepseek["last_test_status"] = "验证成功" if result["ok"] else "验证失败"
            deepseek["last_test_message"] = result["message"]
            deepseek["last_test_at"] = utc_now()
        set_setting(conn, "deepseek", deepseek)
    finally:
        conn.close()


def llm_runtime_config(deepseek: dict) -> dict:
    return {
        "api_key": os.getenv("DEEPSEEK_API_KEY") or deepseek.get("api_key", ""),
        "model": os.getenv("DEEPSEEK_MODEL") or deepseek.get("model", "deepseek-chat"),
        "api_base": normalize_deepseek_api_base(os.getenv("DEEPSEEK_API_BASE") or deepseek.get("api_base", "https://api.deepseek.com")),
        "timeout_seconds": os.getenv("DEEPSEEK_TIMEOUT_SECONDS") or deepseek.get("timeout_seconds", 30),
    }


def handle_customer_import_post(form: dict[str, str]) -> ImportResult:
    conn = ensure_database()
    try:
        return import_customer_purchase_list(conn, actor_role=ROLE_ADMIN, path=form.get("path", ""))
    except Exception as exc:
        return ImportResult(errors=[f"导入失败: {exc}"])
    finally:
        conn.close()


def handle_package_import_post(form: dict[str, str]) -> ImportResult:
    conn = ensure_database()
    try:
        return import_supplier_package_logistics(conn, actor_role=ROLE_ADMIN, path=form.get("path", ""))
    except Exception as exc:
        return ImportResult(errors=[f"导入失败: {exc}"])
    finally:
        conn.close()


def handle_order_goods_import_post(form: dict[str, str], order_id: int) -> ImportResult:
    path = save_import_file(form.get("file") or form.get("path", ""))
    conn = ensure_database()
    try:
        return import_order_goods_upload(conn, actor_role=ROLE_ADMIN, import_order_id=order_id, path=path)
    except Exception as exc:
        return ImportResult(errors=[f"导入失败: {exc}"])
    finally:
        conn.close()


def handle_finance_cost_import_post(form: dict[str, str]) -> ImportResult:
    path = save_import_file(form.get("file") or form.get("path", ""))
    conn = ensure_database()
    try:
        return import_finance_cost_upload(conn, actor_role=ROLE_ADMIN, import_order_id=int(form["import_order_id"]), path=path)
    except Exception as exc:
        return ImportResult(errors=[f"导入失败: {exc}"])
    finally:
        conn.close()


def handle_finance_line_post(form: dict[str, str]) -> None:
    line_kind = form.get("line_kind", LINE_COST) or LINE_COST
    line_type = form.get("cost_type", "") if line_kind == LINE_COST else form.get("charge_type", "")
    conn = ensure_database()
    try:
        add_finance_line(
            conn,
            actor_role=ROLE_ADMIN,
            import_order_id=int(form["import_order_id"]),
            goods_line_id=int_or_none(form.get("goods_line_id", "")),
            line_kind=line_kind,
            line_type=line_type,
            amount=float(form.get("amount", "0") or 0),
            currency=form.get("currency", "") or "EUR",
            exchange_rate_to_base=float(form.get("exchange_rate_to_base", "1") or 1),
            line_date=form.get("line_date", ""),
            notes=form.get("notes", ""),
        )
    finally:
        conn.close()


def handle_finance_line_edit_post(form: dict[str, str], finance_line_id: int) -> int:
    line_kind = form.get("line_kind", LINE_COST) or LINE_COST
    line_type = form.get("cost_type", "") if line_kind == LINE_COST else form.get("charge_type", "")
    conn = ensure_database()
    try:
        update_finance_line(
            conn,
            actor_role=ROLE_ADMIN,
            finance_line_id=finance_line_id,
            goods_line_id=int_or_none(form.get("goods_line_id", "")),
            line_kind=line_kind,
            line_type=line_type,
            amount=float(form.get("amount", "0") or 0),
            currency=form.get("currency", "") or "EUR",
            exchange_rate_to_base=float(form.get("exchange_rate_to_base", "1") or 1),
            line_date=form.get("line_date", ""),
            notes=form.get("notes", ""),
        )
        row = conn.execute("SELECT import_order_id FROM finance_lines WHERE id = ?", (finance_line_id,)).fetchone()
        return int(row["import_order_id"]) if row else int(form.get("import_order_id", "0") or 0)
    finally:
        conn.close()


def handle_finance_line_delete_post(finance_line_id: int) -> int:
    conn = ensure_database()
    try:
        row = conn.execute("SELECT import_order_id FROM finance_lines WHERE id = ?", (finance_line_id,)).fetchone()
        order_id = int(row["import_order_id"]) if row else 0
        delete_finance_line(conn, actor_role=ROLE_ADMIN, finance_line_id=finance_line_id)
        return order_id
    finally:
        conn.close()


def handle_receiving_record_post(form: dict[str, str], user: sqlite3.Row) -> None:
    conn = ensure_database()
    try:
        record_receiving(
            conn,
            actor_role=user["role"],
            actor_user_id=int(user["id"]),
            goods_line_id=int(form["goods_line_id"]),
            received_carton_count=int(form.get("received_carton_count", "0") or 0),
            package_condition=form.get("package_condition", ""),
            domestic_tracking_no=form.get("domestic_tracking_no", ""),
            arrival_exception_type=form.get("arrival_exception_type", ""),
            notes=form.get("notes", ""),
            receiving_photo_path=save_receiving_photo(form.get("receiving_photo") or form.get("receiving_photo_path", "")),
        )
    finally:
        conn.close()


def handle_receiving_resolve_post(form: dict[str, str], user: sqlite3.Row) -> None:
    conn = ensure_database()
    try:
        resolve_arrival_exception(
            conn,
            actor_role=user["role"],
            goods_line_id=int(form["goods_line_id"]),
            resolved_status=form.get("resolved_status", "") or "received_at_warehouse",
        )
    finally:
        conn.close()


def handle_tracking_status_post(form: dict[str, str], user: sqlite3.Row) -> None:
    if user["role"] not in {ROLE_ADMIN, ROLE_WAREHOUSE}:
        raise PermissionError("无权更新货物物流状态")
    logistics_status = form.get("logistics_status", "")
    if logistics_status not in GOODS_LOGISTICS_STATUSES:
        raise ValueError("无效货物物流状态")
    goods_line_id = int(form["goods_line_id"])
    conn = ensure_database()
    try:
        row = conn.execute(
            "SELECT logistics_status FROM goods_lines WHERE id = ?",
            (goods_line_id,),
        ).fetchone()
        if row is None or row["logistics_status"] == logistics_status:
            return
        conn.execute(
            "UPDATE goods_lines SET logistics_status = ?, updated_at = ? WHERE id = ?",
            (logistics_status, utc_now(), goods_line_id),
        )
        conn.commit()
        record_audit_log(
            conn,
            actor_user_id=int(user["id"]),
            target_type="goods_line",
            target_id=goods_line_id,
            field_name="logistics_status",
            old_value=row["logistics_status"],
            new_value=logistics_status,
        )
    finally:
        conn.close()


def handle_container_post(form: dict[str, str]) -> None:
    import_order_id = int(form["import_order_id"])
    conn = ensure_database()
    try:
        create_container(
            conn,
            actor_role=ROLE_ADMIN,
            import_order_id=import_order_id,
            container_type=form.get("container_type", "20GP") or "20GP",
            container_number=form["container_number"],
            seal_number=form["seal_number"],
            loading_date=form.get("loading_date", ""),
            notes=form.get("notes", ""),
        )
        amount = float_or_none(form.get("sea_freight_amount", ""))
        if amount:
            add_finance_line(
                conn,
                actor_role=ROLE_ADMIN,
                import_order_id=import_order_id,
                line_kind=LINE_COST,
                line_type="sea_freight",
                amount=amount,
                currency=form.get("sea_freight_currency", "") or "EUR",
                exchange_rate_to_base=float(form.get("sea_freight_exchange_rate", "1") or 1),
                notes=form.get("container_number", ""),
            )
    finally:
        conn.close()


def handle_loading_record_post(form: dict[str, str], user: sqlite3.Row) -> None:
    conn = ensure_database()
    try:
        record_loading(
            conn,
            actor_role=ROLE_ADMIN,
            actor_user_id=int(user["id"]),
            container_id=int(form["container_id"]),
            goods_line_id=int(form["goods_line_id"]),
            loaded_carton_count=int(form.get("loaded_carton_count", "0") or 0),
            notes=form.get("notes", ""),
            loading_photo_path=save_loading_photo(form.get("loading_photo") or form.get("loading_photo_path", "")),
        )
    finally:
        conn.close()


def handle_compliance_file_post(form: dict[str, str], user: sqlite3.Row) -> None:
    goods_line_id = int_or_none(form.get("goods_line_id", ""))
    owner_type = "goods_line" if goods_line_id else "import_order"
    owner_id = goods_line_id or int(form["import_order_id"])
    storage_path = save_compliance_file(form.get("file") or form.get("path", ""))
    conn = ensure_database()
    try:
        record_file_metadata(
            conn,
            owner_type=owner_type,
            owner_id=owner_id,
            file_category=form.get("file_category", "other_compliance") or "other_compliance",
            file_name=Path(storage_path).name,
            file_type=Path(storage_path).suffix.lstrip(".") or "file",
            storage_path=storage_path,
            uploaded_by_user_id=int(user["id"]),
        )
    finally:
        conn.close()


def handle_document_generate_post(form: dict[str, str]) -> tuple[str, list[dict]]:
    conn = ensure_database()
    try:
        result = generate_export_document(
            conn,
            actor_role=ROLE_ADMIN,
            import_order_id=int(form["import_order_id"]),
            document_type=form.get("document_type", DOC_COMMERCIAL_INVOICE) or DOC_COMMERCIAL_INVOICE,
            output_dir=APP_DB.parent / "documents",
            final=form.get("status", "draft") == "final",
        )
        return f"已生成 {result['document_number']}", result.get("blockers", [])
    except DocumentBlockedError as exc:
        return "Export Document is blocked by missing fields", exc.blockers
    finally:
        conn.close()


def save_loading_photo(source) -> str:
    return save_upload_or_path(source, "loading")


def save_compliance_file(source) -> str:
    return save_upload_or_path(source, "compliance")


def save_receiving_photo(source) -> str:
    return save_upload_or_path(source, "receiving")


def save_import_file(source) -> str:
    return save_upload_or_path(source, "imports")


def handle_assistant_run_post(form: dict[str, str], user: sqlite3.Row) -> int:
    sources: list[Source] = []
    pasted_text = assistant_pasted_text(form)
    for upload in form_values(form, "files") + form_values(form, "file") + form_values(form, "path"):
        file_path = save_import_file(upload)
        if file_path:
            name = Path(file_path).name
            sources.append(Source(source_type=classify_assistant_source(name=name, path=file_path, text=pasted_text), path=file_path, name=name))
    if pasted_text:
        sources.append(Source(source_type=classify_assistant_source(text=pasted_text), text=pasted_text, name="粘贴资料"))
    conn = ensure_database()
    try:
        return run_assistant(
            conn,
            actor_role=ROLE_ADMIN,
            import_order_id=int(form["import_order_id"]),
            actor_user_id=int(user["id"]),
            task_template=form.get("task_template") or TASK_CHECK_ORDER,
            workflow_section=form.get("workflow_section", ""),
            action_button=form.get("task_template") or TASK_CHECK_ORDER,
            sources=sources,
            real_data_confirmed=form.get("real_data_confirmed") == "1",
        )
    finally:
        conn.close()


def assistant_pasted_text(form: dict[str, str]) -> str:
    chunks = [str(value).strip() for key in ("source_text", "pasted_text") for value in form_values(form, key)]
    return "\n\n".join(chunk for chunk in chunks if chunk)


def classify_assistant_source(*, name: str = "", path: str = "", text: str = "") -> str:
    haystack = f"{name} {path} {text}".lower()
    text_haystack = text.lower()
    suffix = Path(name or path).suffix.lower()
    if text and is_order_command_text(text):
        return "order_command"
    if "提单" in text_haystack or "海运单" in text_haystack or "waybill" in text_haystack or "bill of lading" in text_haystack:
        return "waybill"
    if "报关" in text_haystack or "放行" in text_haystack or "customs" in text_haystack:
        return "customs_declaration"
    if "verifycopy" in haystack or "verify copy" in haystack:
        return "verified_customs_copy"
    if "报关" in haystack or "放行" in haystack or "customs" in haystack:
        return "customs_declaration"
    if "提单" in haystack or "海运单" in haystack or "waybill" in haystack or "bill of lading" in haystack:
        return "waybill"
    if suffix in {".xlsx", ".xls"}:
        return "excel"
    if suffix == ".pdf":
        return "pdf"
    if "仓库" in haystack or "收货" in haystack:
        return "warehouse_notes"
    if "邮件" in haystack or "email" in haystack:
        return "supplier_email"
    return "chat"


def form_values(form: dict, key: str) -> list:
    value = form.get(key)
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def handle_assistant_review_post(form: dict[str, str]) -> int | None:
    conn = ensure_database()
    try:
        return update_review_request_status(
            conn,
            actor_role=ROLE_ADMIN,
            review_request_id=int(form["review_request_id"]),
            status=form["status"],
            admin_note=form.get("admin_note", ""),
        )
    finally:
        conn.close()


def handle_assistant_archive_post(form: dict[str, str]) -> None:
    conn = ensure_database()
    try:
        archive_assistant_items(
            conn,
            actor_role=ROLE_ADMIN,
            import_order_id=int(form["import_order_id"]),
            kind=form["kind"],
        )
    finally:
        conn.close()


def handle_assistant_review_group_post(form: dict[str, str]) -> list[int]:
    conn = ensure_database()
    try:
        return update_review_request_group_status(
            conn,
            actor_role=ROLE_ADMIN,
            import_order_id=int(form["import_order_id"]),
            draft_type=form["draft_type"],
            status=form["status"],
        )
    finally:
        conn.close()


def handle_assistant_draft_group_post(form: dict[str, str]) -> list[int | None]:
    conn = ensure_database()
    try:
        return update_change_draft_group_status(
            conn,
            actor_role=ROLE_ADMIN,
            import_order_id=int(form["import_order_id"]),
            draft_type=form["draft_type"],
            action=form["action"],
        )
    finally:
        conn.close()


def handle_assistant_run_retry_post(run_id: int, form: dict[str, str]) -> int:
    conn = ensure_database()
    try:
        return retry_assistant_run(
            conn,
            actor_role=ROLE_ADMIN,
            run_id=run_id,
            real_data_confirmed=form.get("real_data_confirmed") == "1",
        )
    finally:
        conn.close()


def handle_assistant_draft_confirm_post(change_draft_id: int, form: dict[str, str]) -> int | None:
    conn = ensure_database()
    try:
        return confirm_change_draft(
            conn,
            actor_role=ROLE_ADMIN,
            change_draft_id=change_draft_id,
            final_values=parse_final_values(form.get("final_values_json", "")),
        )
    finally:
        conn.close()


def handle_assistant_draft_reject_post(change_draft_id: int) -> None:
    conn = ensure_database()
    try:
        reject_change_draft(conn, actor_role=ROLE_ADMIN, change_draft_id=change_draft_id)
    finally:
        conn.close()


def assistant_source_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return "excel"
    if suffix == ".pdf":
        return "pdf"
    return "file"


def parse_final_values(value: str) -> dict:
    text = value.strip()
    return json.loads(text) if text else {}


def save_upload_or_path(source, folder: str) -> str:
    if not source:
        return ""
    target_dir = APP_DB.parent / "uploads" / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(source, UploadedFile):
        if not source.filename:
            return ""
        target = target_dir / Path(source.filename).name
        target.write_bytes(source.data)
        return str(target)
    source_path = Path(source)
    if not source_path.exists() or not source_path.is_file():
        return source
    target = target_dir / source_path.name
    shutil.copyfile(source_path, target)
    return str(target)


def handle_order_post(form: dict[str, str]) -> int:
    conn = ensure_database()
    try:
        return create_import_order(
            conn,
            actor_role=ROLE_ADMIN,
            **order_values(form),
        )
    finally:
        conn.close()


def handle_order_edit_post(form: dict[str, str], order_id: int) -> None:
    conn = ensure_database()
    try:
        update_import_order(conn, actor_role=ROLE_ADMIN, import_order_id=order_id, **order_values(form))
    finally:
        conn.close()


def handle_order_cancel_post(order_id: int) -> None:
    conn = ensure_database()
    try:
        update_import_order(conn, actor_role=ROLE_ADMIN, import_order_id=order_id, order_status="cancelled")
    finally:
        conn.close()


def order_values(form: dict[str, str]) -> dict:
    return {
        "order_no": form.get("order_no") or None,
        "consignee_id": int_or_none(form.get("consignee_id", "")),
        "receiving_warehouse_id": int_or_none(form.get("receiving_warehouse_id", "")),
        "port_warehouse_id": int_or_none(form.get("port_warehouse_id", "")),
        "trade_term": form.get("trade_term", ""),
        "destination_country": form.get("destination_country", ""),
        "destination_port": form.get("destination_port", ""),
        "expected_loading_date": form.get("expected_loading_date") or None,
        "purchase_currency": form.get("purchase_currency", ""),
        "sales_currency": form.get("sales_currency", ""),
        "internal_notes": form.get("internal_notes", ""),
    }


def handle_order_status_post(form: dict[str, str], user: sqlite3.Row) -> None:
    conn = ensure_database()
    try:
        order_id = int(form["order_id"])
        old = conn.execute("SELECT order_status FROM import_orders WHERE id = ?", (order_id,)).fetchone()
        new_status = form.get("order_status", "")
        if old is not None and new_status and old["order_status"] != new_status:
            update_import_order(conn, actor_role=ROLE_ADMIN, import_order_id=order_id, order_status=new_status)
            record_audit_log(
                conn,
                actor_user_id=int(user["id"]),
                target_type="import_order",
                target_id=order_id,
                field_name="order_status",
                old_value=old["order_status"],
                new_value=new_status,
            )
    finally:
        conn.close()


def handle_goods_line_post(form: dict[str, str], order_id: int) -> int:
    conn = ensure_database()
    try:
        return create_goods_line(conn, actor_role=ROLE_ADMIN, import_order_id=order_id, **goods_line_values(form))
    finally:
        conn.close()


def handle_goods_line_edit_post(form: dict[str, str], goods_line_id: int) -> int:
    conn = ensure_database()
    try:
        update_goods_line(conn, actor_role=ROLE_ADMIN, goods_line_id=goods_line_id, **goods_line_values(form))
        row = conn.execute("SELECT import_order_id FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        return int(row["import_order_id"]) if row else 0
    finally:
        conn.close()


def handle_goods_line_delete_post(goods_line_id: int, user: sqlite3.Row) -> int:
    conn = ensure_database()
    try:
        row = conn.execute(
            "SELECT import_order_id, customs_en_name, cn_name FROM goods_lines WHERE id = ?",
            (goods_line_id,),
        ).fetchone()
        if row is None:
            return 0
        conn.execute("DELETE FROM goods_lines WHERE id = ?", (goods_line_id,))
        record_audit_log(
            conn,
            actor_user_id=int(user["id"]),
            target_type="goods_line",
            target_id=goods_line_id,
            field_name="deleted",
            old_value=row["customs_en_name"] or row["cn_name"],
            new_value=None,
        )
        return int(row["import_order_id"])
    finally:
        conn.close()


def goods_line_values(form: dict[str, str]) -> dict:
    numeric = {
        "supplier_id": int_or_none,
        "quantity": float_or_none,
        "target_markup": float_or_none,
        "target_margin": float_or_none,
        "sales_unit_price": float_or_none,
        "purchase_unit_price": float_or_none,
        "carton_count": int_or_none,
        "units_per_carton": float_or_none,
        "carton_length_cm": float_or_none,
        "carton_width_cm": float_or_none,
        "carton_height_cm": float_or_none,
        "carton_gross_weight_kg": float_or_none,
        "gross_weight": float_or_none,
        "volume_cbm": float_or_none,
    }
    fields = {field for group in GOODS_LINE_FIELD_GROUPS.values() for field in group} | {"notes"}
    values = {
        field: (numeric[field](form.get(field, "")) if field in numeric else form.get(field, ""))
        for field in fields
    }
    return {key: value for key, value in values.items() if value not in ("", None)}


def goods_line_form(action: str, suppliers: list[sqlite3.Row], goods: sqlite3.Row | None = None, disabled: bool = False) -> str:
    disabled_attr = " disabled" if disabled else ""
    sections = []
    for group, fields in GOODS_LINE_FIELD_GROUPS.items():
        if group == "files":
            continue
        inputs = []
        for field in fields:
            if field == "supplier_id":
                inputs.append(select_input("supplier_id", field_label("supplier_id"), suppliers, "name", selected=goods["supplier_id"] if goods else None, disabled=disabled))
            elif field == "logistics_status":
                inputs.append(value_select("logistics_status", field_label(field), GOODS_LOGISTICS_STATUSES, normalize_logistics_status(goods[field]) if goods else "not_ordered", logistics_status_label, disabled))
            elif field == "compliance_status":
                inputs.append(value_select("compliance_status", field_label(field), COMPLIANCE_STATUS_LABELS, goods[field] if goods else "not_required", compliance_status_label, disabled))
            else:
                inputs.append(f'<label>{esc(field_label(field))}<input name="{field}" value="{esc(goods[field] if goods else "")}"{disabled_attr}></label>')
        sections.append(f"<fieldset><legend>{esc(FIELD_GROUP_LABELS.get(group, group))}</legend><div class='form-grid'>{''.join(inputs)}</div></fieldset>")
    notes = f'<label>{field_label("notes")}<input name="notes" value="{esc(goods["notes"] if goods else "")}"{disabled_attr}></label>'
    button = "" if disabled else "<button type='submit'>保存货物项</button>"
    return f"<section class='panel pad'><form method='post' action='{action}'>{''.join(sections)}<div class='form-grid'>{notes}{button}</div></form></section>"


def select_input(name: str, label: str, rows: list[sqlite3.Row], text_field: str, selected=None, disabled: bool = False) -> str:
    disabled_attr = " disabled" if disabled else ""
    options = ["<option value=''></option>"] + [
        f"<option value='{row['id']}'{' selected' if selected == row['id'] else ''}>{esc(row[text_field])}</option>"
        for row in rows
    ]
    return f"<label>{esc(label)}<select name='{name}'{disabled_attr}>{''.join(options)}</select></label>"


def value_select(name: str, label: str, values, selected: str, labeler, disabled: bool = False) -> str:
    disabled_attr = " disabled" if disabled else ""
    options = "".join(
        f"<option value='{esc(value)}'{' selected' if selected == value else ''}>{esc(labeler(value))}</option>"
        for value in values
    )
    return f"<label>{esc(label)}<select name='{name}'{disabled_attr}>{options}</select></label>"


def path_id(path: str, prefix: str) -> int | None:
    if not path.startswith(prefix):
        return None
    tail = path[len(prefix):]
    return int(tail) if tail.isdigit() else None


def suffix_path_id(path: str, prefix: str, suffix: str) -> int | None:
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    middle = path[len(prefix):-len(suffix)]
    return int(middle) if middle.isdigit() else None


def edit_path_id(path: str, prefix: str) -> int | None:
    if not path.startswith(prefix) or not path.endswith("/edit"):
        return None
    middle = path[len(prefix):-5]
    return int(middle) if middle.isdigit() else None


def document_download_path(path: str) -> tuple[int, str] | None:
    parts = path.strip("/").split("/")
    if len(parts) != 4 or parts[:2] != ["downloads", "document"]:
        return None
    if not parts[2].isdigit() or parts[3] not in {"xlsx", "pdf"}:
        return None
    return int(parts[2]), parts[3]


def int_or_none(value: str):
    return int(value) if value else None


def float_or_none(value: str):
    return float(value) if value else None


def form_data(body: bytes, content_type: str = "") -> dict:
    if content_type.startswith("multipart/form-data"):
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
        output = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename:
                _add_form_value(output, name, UploadedFile(Path(filename).name, part.get_content_type(), payload))
            else:
                _add_form_value(output, name, payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
        return output
    parsed = parse_qs(body.decode())
    return {key: values[0] if values else "" for key, values in parsed.items()}


def _add_form_value(output: dict, name: str, value) -> None:
    if name not in output:
        output[name] = value
    elif isinstance(output[name], list):
        output[name].append(value)
    else:
        output[name] = [output[name], value]


def esc(value) -> str:
    return html.escape(str(value or ""))


def money(value) -> str:
    return f"{float(value or 0):.2f}"


CSS = """
:root {
  color-scheme: light;
  --bg:#f3f6f9;
  --ink:#10243a;
  --muted:#647487;
  --line:#d7e0ea;
  --panel:#fff;
  --soft:#f8fafc;
  --accent:#087982;
  --accent-2:#0f69b5;
  --danger:#d92d20;
  --warn:#e66f00;
  --shadow:0 12px 30px rgba(16,36,58,.08);
}
* { box-sizing: border-box; }
html, body { height:100%; }
body { margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background:var(--bg); color:var(--ink); }
a { color: inherit; text-decoration: none; }
.app { height:100dvh; min-height:620px; display:grid; grid-template-columns: 220px minmax(0, 1fr); overflow:hidden; }
aside { min-height:0; background:linear-gradient(180deg, #062d4a 0%, #07375a 48%, #04243d 100%); color:#dce7ef; padding:22px 12px; display:flex; flex-direction:column; border-right:1px solid rgba(255,255,255,.08); }
.brand { min-height:54px; display:grid; gap:2px; padding:0 10px 18px; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,.12); }
.brand strong { font-size:22px; line-height:1; font-weight:800; color:#fff; }
.brand span { font-size:13px; color:#b8d6e8; }
nav { display:grid; gap:6px; }
nav a { min-height:42px; display:flex; align-items:center; padding:0 12px; border-radius:6px; color:#d1e2ee; font-size:14px; font-weight:650; }
nav a:hover, nav a.active { background:rgba(14,129,150,.8); color:white; box-shadow:inset 3px 0 0 rgba(255,255,255,.62); }
.workspace { min-width:0; min-height:0; display:flex; flex-direction:column; }
header { flex:0 0 54px; display:flex; justify-content:flex-end; align-items:center; gap:16px; padding:0 24px; background:white; border-bottom:1px solid var(--line); color:var(--muted); font-size:13px; }
header a { color:#22384e; font-weight:650; }
main { min-height:0; overflow:auto; padding:22px 24px 30px; }
.utility-menu { position:relative; }
.utility-menu summary { cursor:pointer; color:#314351; font-weight:650; list-style:none; }
.utility-menu summary::-webkit-details-marker { display:none; }
.utility-menu[open] summary { color:var(--accent); }
.utility-menu a { display:block; padding:9px 12px; white-space:nowrap; background:white; }
.utility-menu a:hover { background:#f2f6f8; color:#0f6670; }
.utility-menu[open] { z-index:5; }
.utility-menu[open]::after { content:""; position:absolute; right:0; top:28px; width:150px; height:148px; background:white; border:1px solid var(--line); border-radius:8px; box-shadow:0 12px 28px rgba(20,33,43,.12); z-index:-1; }
.toolbar { display:flex; justify-content:space-between; align-items:flex-start; gap:20px; margin-bottom:18px; }
h1, h2, p { margin:0; }
h1 { font-size:28px; line-height:1.15; letter-spacing:0; font-weight:800; }
h2 { font-size:16px; line-height:1.25; }
.toolbar p { color:var(--muted); margin-top:6px; }
.search input, label input { width:320px; height:38px; border:1px solid var(--line); border-radius:6px; padding:0 12px; font:inherit; background:white; }
.search { display:flex; align-items:center; }
.search input { box-shadow:0 1px 0 rgba(16,36,58,.03); }
.search input { border-radius:6px 0 0 6px; border-right:0; }
.search button { width:58px; height:38px; border-radius:0 6px 6px 0; }
.dashboard-overview { display:grid; grid-template-columns:minmax(0, 1fr) minmax(300px, .42fr); gap:14px; align-items:stretch; margin-bottom:18px; }
.dashboard-overview .panel { margin-bottom:0; }
.metric-grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:14px; }
.metric-grid a { display:block; }
.metric-grid article, .panel, .login-card { background:var(--panel); border:1px solid var(--line); border-radius:8px; }
.metric-grid article { min-height:112px; padding:18px; display:grid; align-content:center; gap:5px; box-shadow:0 1px 0 rgba(16,36,58,.03); }
.metric-grid strong { font-size:30px; line-height:1; color:#0c5f9f; }
.metric-grid span, .hint { color:var(--muted); font-size:13px; }
.filter-panel { padding-top:12px; padding-bottom:12px; }
.reminders-panel { min-height:112px; }
.reminders-panel .reminder-list { max-height:86px; overflow:auto; }
.summary-grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; margin-top:14px; }
.summary-grid article { border:1px solid var(--line); border-radius:6px; padding:12px; background:var(--soft); display:grid; gap:5px; }
.summary-grid span { color:var(--muted); font-size:12px; }
.summary-grid strong { font-size:16px; font-weight:750; }
.action-row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:14px; }
.icon-form { display:inline; margin:0; }
.icon-button { display:inline-flex; align-items:center; justify-content:center; width:32px; height:32px; border:1px solid var(--line); border-radius:6px; background:var(--soft); color:#1f2937; font-weight:800; text-decoration:none; cursor:pointer; }
.icon-button.danger { color:#991b1b; border-color:#fecaca; background:#fff1f2; }
.action-drawer { display:inline-block; }
.action-drawer summary, .button-link { display:inline-flex; align-items:center; justify-content:center; min-height:36px; padding:0 12px; border-radius:6px; background:var(--accent); color:white; font-size:13px; font-weight:750; cursor:pointer; border:1px solid rgba(0,0,0,.04); }
.action-drawer summary { list-style:none; }
.action-drawer summary::-webkit-details-marker { display:none; }
.action-drawer[open] { position:fixed; inset:0; z-index:20; display:grid; place-items:center; padding:24px; background:rgba(12,30,48,.46); cursor:pointer; }
.action-drawer[open] summary { position:fixed; top:18px; right:24px; min-width:78px; background:#20384f; box-shadow:0 8px 22px rgba(12,30,48,.22); cursor:pointer; }
.action-drawer[open] summary::after { content:" 关闭"; }
.action-drawer[open] form, .action-drawer[open] .drawer-stack { width:min(780px, 100%); max-height:calc(100dvh - 96px); overflow:auto; padding:18px; border:1px solid var(--line); border-radius:8px; background:white; box-shadow:0 22px 60px rgba(12,30,48,.28); cursor:auto; }
.action-drawer[open] .drawer-stack form { width:auto; max-height:none; overflow:visible; padding:0; border:0; box-shadow:none; }
.assistant-panel { max-height:calc(100dvh - 250px); min-height:260px; display:flex; flex-direction:column; }
.assistant-panel .panel-head { flex:0 0 auto; }
.assistant-panel h3 { margin:0 0 10px; color:#24384f; font-size:14px; }
.assistant-lane-head { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; }
.assistant-lane-head h3 { margin:0; }
.count-badge { display:inline-grid; min-width:22px; height:22px; place-items:center; padding:0 6px; border-radius:999px; background:#dcecf2; color:#0b5463; font-size:12px; }
.history-link { display:inline-block; margin:0 0 8px; color:#0b7285; font-size:12px; font-weight:700; text-decoration:none; }
.assistant-columns { min-height:0; flex:1; overflow:hidden; display:grid; grid-template-columns:minmax(210px, .85fr) minmax(320px, 1.3fr) minmax(240px, 1fr); gap:12px; padding:14px; }
.assistant-lane { min-width:0; min-height:0; display:flex; flex-direction:column; border:1px solid var(--line); border-radius:8px; background:#fbfdff; padding:12px; }
.assistant-scroll, .compact-list { min-height:0; flex:1; overflow:auto; }
.assistant-scroll { display:grid; gap:8px; }
.assistant-card { min-width:0; margin:0; padding:10px 12px; border:1px solid var(--line); border-radius:7px; background:white; }
.assistant-card strong { display:block; margin-bottom:4px; color:#132944; font-size:14px; line-height:1.35; }
.assistant-card p { margin:4px 0; line-height:1.35; }
.group-actions { display:grid; gap:8px; margin:0 0 10px; }
.group-action-card { display:grid; gap:7px; padding:9px 10px; border:1px dashed #b8d5dd; border-radius:8px; background:#f3fafb; }
.group-action-card strong { color:#132944; font-size:13px; }
.group-action-card span { display:flex; flex-wrap:wrap; gap:8px; }
.assistant-card pre { white-space:pre-wrap; word-break:break-word; max-height:120px; overflow:auto; padding:8px; border-radius:6px; background:#e8eef5; font-size:12px; }
.compact-list { margin:0; padding:0; list-style:none; display:grid; gap:8px; }
.assistant-run { display:grid; gap:3px; padding:9px 10px; border:1px solid var(--line); border-radius:7px; background:white; }
.assistant-run strong { color:#132944; font-size:13px; }
.assistant-run span { color:var(--muted); font-size:12px; line-height:1.3; }
.assistant-error { color:#a51d16; font-size:12px; }
.order-agent-layout { display:grid; grid-template-columns:minmax(240px, .32fr) minmax(0, 1fr); gap:16px; }
.order-agent-sidebar { min-height:0; display:flex; flex-direction:column; }
.order-agent-conversation-scroll { max-height:calc(100dvh - 330px); overflow:auto; }
.order-agent-list-scroll { min-height:260px; padding:12px; display:grid; align-content:start; gap:10px; }
.order-agent-card { display:grid; gap:4px; padding:11px 12px; border:1px solid var(--line); border-radius:8px; background:#fbfdff; }
.order-agent-card.active { border-color:#65b8c1; background:#eefafb; box-shadow:inset 3px 0 0 var(--accent); }
.order-agent-card strong { color:#132944; font-size:14px; }
.order-agent-card span, .order-agent-card small { color:var(--muted); font-size:12px; }
.panel.order-agent-workspace-scroll { max-height:calc(100dvh - 330px); min-height:360px; overflow:auto; }
.order-agent-workbench-head { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; margin-bottom:14px; }
.order-agent-message-scroll { max-height:220px; overflow:auto; display:grid; gap:10px; margin:14px 0; }
.order-agent-message-scroll article, .order-agent-empty-box { border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfdff; }
.order-agent-message-scroll p { margin-top:5px; white-space:pre-wrap; }
.order-agent-message-scroll small { color:var(--muted); font-size:12px; }
.order-agent-empty-box { margin-top:14px; }
.ai-busy-overlay { display:none; position:fixed; inset:0; z-index:20; background:rgba(9, 27, 44, .45); place-items:center; }
.ai-busy .ai-busy-overlay { display:grid; }
.ai-busy-modal { width:min(920px, calc(100vw - 32px)); padding:24px; border-radius:16px; background:white; box-shadow:0 18px 50px rgba(0,0,0,.22); color:#132944; display:grid; grid-template-columns:minmax(0, 1fr) minmax(260px, .9fr); gap:18px; }
.ai-busy-overlay strong { display:block; margin-bottom:8px; font-size:18px; }
.ai-busy-steps { margin:12px 0; padding:0; list-style:none; display:grid; gap:8px; }
.ai-busy-steps li { padding:9px 10px; border:1px solid var(--line); border-radius:8px; background:#f8fbfc; animation:agent-step 1.6s ease-in-out infinite; }
.ai-busy-steps li:nth-child(2) { animation-delay:.2s; }
.ai-busy-steps li:nth-child(3) { animation-delay:.4s; }
.ai-busy-steps li:nth-child(4) { animation-delay:.6s; }
.ai-busy-steps b { display:block; font-size:13px; color:#0b5463; }
.ai-busy-steps span { color:var(--muted); font-size:12px; }
.ai-busy-live { border-left:1px solid var(--line); padding-left:18px; min-width:0; }
.ai-busy-live-data { display:grid; gap:8px; max-height:300px; overflow:auto; font-size:13px; color:var(--muted); }
.ai-busy-live-data p { margin:0; }
.ai-busy-confirm { margin-top:12px; }
@keyframes agent-step { 50% { border-color:#78c4cd; background:#edfafb; transform:translateY(-1px); } }
.modal-overlay { display:none; position:fixed; inset:0; z-index:30; padding:56px 18px; background:rgba(9, 27, 44, .48); overflow:auto; }
.modal-overlay:target { display:block; }
.history-modal { position:relative; max-width:860px; margin:0 auto; padding:22px; border-radius:16px; background:white; box-shadow:0 18px 50px rgba(0,0,0,.22); }
.modal-close { position:absolute; top:14px; right:14px; padding:7px 12px; border-radius:999px; background:#eef5f8; color:#0b5463; font-weight:700; text-decoration:none; }
.history-grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; margin-top:14px; }
.history-grid article { min-width:0; border:1px solid var(--line); border-radius:10px; padding:12px; background:#fbfdff; }
.history-grid ul { margin:0; padding-left:18px; max-height:320px; overflow:auto; }
.inline-actions { display:inline-flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.inline-actions button { height:32px; padding:0 10px; font-size:12px; }
.checkbox { display:flex; gap:8px; align-items:flex-start; }
.panel { overflow:hidden; margin-bottom:18px; box-shadow:0 1px 0 rgba(16,36,58,.03); }
.scroll-panel { max-height:320px; overflow:auto; }
.table-scroll { overflow:auto; }
.tracking-scroll { max-height:calc(100dvh - 270px); min-height:300px; overflow:auto; }
.tracking-scroll table { min-width:2320px; }
.warehouse-scroll { max-height:440px; overflow:auto; }
.warehouse-scroll table { min-width:1280px; }
.master-data-scroll { max-height:380px; overflow:auto; }
.master-data-scroll table { min-width:920px; }
.document-blocker-scroll { max-height:260px; overflow:auto; }
.panel-head { display:flex; justify-content:space-between; align-items:center; gap:16px; padding:14px 16px; border-bottom:1px solid var(--line); color:var(--muted); }
table { width:100%; border-collapse:separate; border-spacing:0; font-size:13px; }
th, td { padding:11px 13px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; vertical-align:middle; }
th { position:sticky; top:0; z-index:1; color:#516376; font-size:12px; font-weight:750; letter-spacing:0; background:var(--soft); }
tbody tr:hover { background:#fbfdff; }
progress { width:90px; vertical-align:middle; accent-color:var(--accent); }
.status { display:inline-flex; align-items:center; min-height:24px; border-radius:999px; padding:0 9px; font-size:12px; font-weight:700; color:#24313c; background:#e8edf2; }
.status.blue { background:#d9ebff; color:#0b4d82; }
.status.orange { background:#ffe7c2; color:#885200; }
.status.green { background:#d9f4df; color:#176331; }
.status.red { background:#ffe0df; color:#8b1d18; }
.status.navy { background:#dfe7f5; color:#1e3c70; }
.status.teal, .status.cyan { background:#d7f2f1; color:#0e6264; }
.status.purple, .status.indigo { background:#e8e3ff; color:#46318a; }
.inline-status select { height:30px; border:1px solid var(--line); border-radius:999px; padding:0 9px; background:var(--soft); font:inherit; font-size:12px; font-weight:650; }
.empty { text-align:center; color:var(--muted); padding:34px; }
.login { min-height:100vh; display:grid; place-items:center; padding:24px; }
.login-card { width:min(420px, 100%); padding:28px; display:grid; gap:20px; }
.login-card form { display:grid; gap:14px; }
label { display:grid; gap:6px; color:#536270; font-size:13px; }
label input, label select, label textarea { width:100%; border:1px solid var(--line); border-radius:6px; padding:0 10px; background:white; font:inherit; }
label input, label select { height:38px; }
label textarea { min-height:84px; padding:10px; }
button { height:40px; border:0; border-radius:6px; background:var(--accent); color:white; font-weight:750; cursor:pointer; }
.pad { padding:18px; }
.form-grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:14px; align-items:end; }
.form-grid button { align-self:end; }
.filter-bar { display:flex; gap:12px; align-items:end; flex-wrap:wrap; }
.filter-bar label { min-width:190px; }
.filter-bar .check { display:flex; grid-template-columns:none; align-items:center; min-width:auto; height:38px; gap:8px; }
.check input { width:auto; height:auto; }
.two-col { display:grid; grid-template-columns: minmax(0, 1.2fr) minmax(260px, .8fr); gap:18px; margin-bottom:18px; }
.stack { display:grid; gap:10px; margin-top:14px; }
.link-list { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
.link-list a { border:1px solid var(--line); border-radius:6px; padding:9px 11px; color:#0f6670; background:var(--soft); }
.mini-input { width:112px; height:32px; border:1px solid var(--line); border-radius:6px; padding:0 8px; font:inherit; }
.notice { margin:0 0 16px; padding:10px 12px; background:#d9f4df; color:#176331; border-radius:6px; }
.errors { margin:10px 0 0; padding-left:20px; color:#a51d16; }
.reminder-list { margin:10px 0 0; padding-left:20px; color:var(--muted); }
.reminder-list li + li { margin-top:6px; }
.inline-form { margin-top:8px; }
.inline-form button { height:30px; padding:0 9px; font-size:12px; }
.tabs { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }
.tabs a { background:white; border:1px solid var(--line); border-radius:999px; padding:7px 10px; color:var(--muted); font-size:13px; }
fieldset { border:1px solid var(--line); border-radius:8px; margin:0 0 16px; padding:14px; }
legend { padding:0 8px; color:var(--muted); font-size:13px; }
.error { color:#a51d16; font-size:14px; }
@media (max-width: 760px) {
  .app { height:auto; min-height:100dvh; display:block; overflow:visible; }
  aside { position:sticky; top:0; z-index:10; min-height:0; padding:10px 12px; overflow:auto; }
  .brand { min-height:0; padding:0 0 8px; margin:0; border:0; }
  .brand strong { font-size:18px; }
  .brand span { display:none; }
  nav { display:flex; gap:8px; overflow:auto; padding-bottom:2px; }
  nav a { flex:0 0 auto; min-height:34px; padding:0 10px; font-size:13px; }
  .workspace { min-height:0; display:block; }
  header { height:48px; padding:0 16px; }
  main { overflow:visible; padding:16px; }
  .toolbar { display:grid; }
  .dashboard-overview { grid-template-columns:1fr; }
  .metric-grid { grid-template-columns:1fr; }
  .summary-grid { grid-template-columns:1fr; }
  .assistant-panel { max-height:none; }
  .assistant-columns { grid-template-columns:1fr; }
  .assistant-lane { max-height:360px; }
  .order-agent-layout { grid-template-columns:1fr; }
  .order-agent-conversation-scroll, .order-agent-workspace-scroll { max-height:none; }
  .ai-busy-modal { grid-template-columns:1fr; max-height:calc(100dvh - 32px); overflow:auto; }
  .ai-busy-live { border-left:0; border-top:1px solid var(--line); padding-left:0; padding-top:14px; }
  .two-col { grid-template-columns:1fr; }
  .form-grid { grid-template-columns:1fr; }
  .search input { width:100%; min-width:0; }
  .action-drawer[open] { align-items:end; padding:12px; }
  .action-drawer[open] summary { top:12px; right:12px; }
  .action-drawer[open] form, .action-drawer[open] .drawer-stack { max-height:calc(100dvh - 76px); }
  table { display:block; overflow:auto; }
}
"""


if __name__ == "__main__":
    run()

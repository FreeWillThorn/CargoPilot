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
    update_goods_line_quote,
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
        order_id = path_id(parsed.path, "/orders/")
        if order_id is not None:
            self._send(HTTPStatus.OK, order_detail_page(user, order_id), "text/html; charset=utf-8")
            return
        goods_line_edit_id = edit_path_id(parsed.path, "/goods-lines/")
        if goods_line_edit_id is not None:
            self._send(HTTPStatus.OK, goods_line_edit_page(user, goods_line_edit_id), "text/html; charset=utf-8")
            return
        if parsed.path == "/suppliers":
            self._admin_page(user, suppliers_page)
            return
        if parsed.path == "/consignees":
            self._admin_page(user, consignees_page)
            return
        if parsed.path == "/warehouses":
            self._admin_page(user, warehouses_page)
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
        if parsed.path == "/settings":
            self._admin_page(user, settings_page)
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
            if parsed.path == "/suppliers":
                handle_supplier_post(form)
                self._redirect("/suppliers")
                return
            if parsed.path == "/consignees":
                handle_consignee_post(form)
                self._redirect("/consignees")
                return
            if parsed.path == "/warehouses":
                handle_warehouse_post(form)
                self._redirect("/warehouses")
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
                self._redirect("/settings")
                return
            if parsed.path == "/excel/customer-import":
                result = handle_customer_import_post(form)
                self._send(HTTPStatus.OK, excel_finance_page(user, {}, "客户采购清单导入完成", result.errors), "text/html; charset=utf-8")
                return
            if parsed.path == "/excel/package-import":
                result = handle_package_import_post(form)
                self._send(HTTPStatus.OK, excel_finance_page(user, {}, "供应商包装物流导入完成", result.errors), "text/html; charset=utf-8")
                return
            if parsed.path == "/finance/quote":
                handle_quote_post(form)
                self._redirect(finance_redirect(form))
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
          <form class="search" method="get" action="/search"><input name="q" aria-label="搜索" placeholder="搜索订单、客户、物流单号、麦头"></form>
        </section>
        <section class="panel pad">
          <form method="get" action="/dashboard" class="filter-bar">
            <label>订单状态<select name="status" onchange="this.form.submit()">{status_options}</select></label>
          </form>
        </section>
        <section class="metric-grid">
          <a href="/orders"><article><strong>{len(cards)}</strong><span>活跃订单</span></article></a>
          <a href="/tracking?exception_only=1"><article><strong>{sum(card['exception_count'] for card in cards)}</strong><span>异常</span></article></a>
          <a href="/orders"><article><strong>{sum(card['missing_data_count'] for card in cards)}</strong><span>缺失资料</span></article></a>
        </section>
        <section class="panel pad"><h2>提醒事项</h2><ul class="reminder-list">{reminder_html}</ul></section>
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
    rows = "".join(tracking_row(row, user, return_to) for row in rows_data) or '<tr><td colspan="14" class="empty">暂无匹配货物项</td></tr>'
    actions = "" if user["role"] != ROLE_ADMIN or import_order_id is None else compact_goods_line_drawer(import_order_id, suppliers, return_to)
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
        <section class="panel table-scroll tracking-scroll"><table><thead><tr><th>货物项</th><th>供应商</th><th>SKU/型号</th><th>数量</th><th>箱数</th><th>每箱数量</th><th>外箱尺寸(cm)</th><th>单箱毛重(kg)</th><th>CBM</th><th>总毛重(kg)</th><th>麦头</th><th>国内物流单号</th><th>货物物流状态</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table></section>
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
          <form class="search" method="get" action="/search"><input name="q" value="{esc(query)}" placeholder="Search"></form>
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
    consignees_panel = order_consignees_panel(user, consignees, selected_id)
    notice = f"<p class='notice'>{esc(message)}</p>" if message else ""
    error_html = "".join(f"<li>{esc(error)}</li>" for error in (errors or []))
    errors_block = f"<section class='panel pad'><h2>导入错误</h2><ul class='errors'>{error_html}</ul></section>" if error_html else ""
    return page("订单详情", f"""
      <section class="toolbar"><div><h1>订单详情</h1><p>订单列表、订单资料和收货客户</p></div>{form}</section>
      {notice}
      {errors_block}
      <section class="panel pad"><form method="get" action="/orders" class="filter-bar"><label>当前订单<select name="order_id" onchange="this.form.submit()">{order_options}</select></label></form></section>
      <section class="panel scroll-panel"><table><thead><tr><th>订单号</th><th>收货客户</th><th>目的港</th><th>订单状态</th><th>订单进度</th><th>当前物流点</th><th>预计装柜日</th><th>异常数</th><th>缺资料数</th></tr></thead><tbody>{rows}</tbody></table></section>
      {summary}
      {consignees_panel}
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
    """


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
    warehouse_actions = ""
    if user["role"] == ROLE_ADMIN:
        warehouse_actions = f"""
        <div class="action-row">
          <details class="action-drawer"><summary title="新增仓库" aria-label="新增仓库">+</summary>{warehouse_form('/receiving/warehouses')}</details>
          <details class="action-drawer"><summary title="编辑仓库" aria-label="编辑仓库">✎</summary>{warehouse_form(f"/receiving/warehouses/{warehouse_id}/edit", warehouse)}</details>
          <form method="post" action="/receiving/warehouses/{warehouse_id}/delete" class="icon-form">
            <button class="icon-button danger" type="submit" title="删除仓库" aria-label="删除仓库" onclick="return confirm('删除这个仓库？')">×</button>
          </form>
        </div>
        """
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
        <section class="panel pad"><div class="panel-head"><h2>仓库信息</h2><span>{esc(warehouse['name'] if warehouse else '')}</span></div><div class="summary-grid">{warehouse_summary}</div>{warehouse_actions}</section>
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


def suppliers_page(user: sqlite3.Row) -> str:
    conn = ensure_database()
    try:
        suppliers = list_suppliers(conn)
    finally:
        conn.close()
    rows = "".join(
        f"<tr><td>{s['id']}</td><td>{esc(s['name'])}</td><td>{esc(s['contact_name'])}</td><td>{esc(s['phone'])}</td><td>{esc(s['email'])}</td><td>{esc(s['store_url'])}</td></tr>"
        for s in suppliers
    ) or '<tr><td colspan="6" class="empty">暂无供应商</td></tr>'
    return crud_page(
        user,
        "供应商",
        "/suppliers",
        [
            ("name", "名称"),
            ("contact_name", "联系人"),
            ("phone", "电话"),
            ("email", "邮箱"),
            ("wechat", "微信"),
            ("address", "地址"),
            ("business_id", "注册号"),
            ("store_url", "1688/店铺链接"),
            ("usual_categories", "常用品类"),
            ("notes", "备注"),
        ],
        ["ID", "名称", "联系人", "电话", "邮箱", "店铺链接"],
        rows,
    )


def consignees_page(user: sqlite3.Row) -> str:
    conn = ensure_database()
    try:
        rows_data = conn.execute("SELECT * FROM consignees ORDER BY company_name").fetchall()
    finally:
        conn.close()
    rows = "".join(
        f"<tr><td>{c['id']}</td><td>{esc(c['company_name'])}</td><td>{esc(c['contact_name'])}</td><td>{esc(c['email'])}</td><td>{esc(c['default_destination_port'])}</td><td>{esc(c['default_sales_currency'])}</td></tr>"
        for c in rows_data
    ) or '<tr><td colspan="6" class="empty">暂无客户</td></tr>'
    return crud_page(
        user,
        "收货客户",
        "/consignees",
        [
            ("company_name", "公司名"),
            ("contact_name", "联系人"),
            ("email", "邮箱"),
            ("phone", "电话"),
            ("tax_id", "VAT/EORI"),
            ("address", "地址"),
            ("default_destination_port", "默认目的港"),
            ("default_trade_term", "默认贸易条款"),
            ("default_sales_currency", "默认销售币种"),
            ("document_preferences", "单证偏好"),
            ("notes", "备注"),
        ],
        ["ID", "公司", "联系人", "邮箱", "默认目的港", "币种"],
        rows,
    )


def warehouses_page(user: sqlite3.Row) -> str:
    conn = ensure_database()
    try:
        warehouses = list_warehouses(conn)
    finally:
        conn.close()
    rows = "".join(
        f"<tr><td>{w['id']}</td><td>{esc(warehouse_type_label(w['type']))}</td><td>{esc(w['name'])}</td><td>{esc(w['contact_name'])}</td><td>{esc(w['phone'])}</td><td>{esc(w['address'])}</td></tr>"
        for w in warehouses
    ) or '<tr><td colspan="6" class="empty">暂无仓库</td></tr>'
    return page(
        "仓库资料",
        f"""
        <section class="toolbar"><div><h1>仓库资料</h1><p>主数据维护</p></div></section>
        <section class="panel pad">{warehouse_form('/warehouses')}</section>
        <section class="panel"><table><thead><tr><th>ID</th><th>类型</th><th>名称</th><th>联系人</th><th>电话</th><th>地址</th></tr></thead><tbody>{rows}</tbody></table></section>
        """,
        user=user,
    )


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
    quote_rows = "".join(_quote_row(line) for line in goods) or '<tr><td colspan="9" class="empty">暂无商品行</td></tr>'
    cost_rows = finance_rows_by_kind(finance_rows, LINE_COST, goods_options, cost_options, charge_options)
    charge_rows = finance_rows_by_kind(finance_rows, LINE_CHARGE, goods_options, cost_options, charge_options)
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
        <details class="action-drawer"><summary title="新增客户收费" aria-label="新增客户收费">+</summary>
          {finance_line_form("/finance/line", selected_order_id, goods_options, cost_options, charge_options, LINE_CHARGE)}
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
            ("利润", money(summary["profit"] if summary else 0)),
            ("基准币", summary["base_currency"] if summary else base_currency),
        ]
    )
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
        <section class="panel pad"><div class="panel-head"><h2>订单利润总览</h2><span>{esc(base_currency)}</span></div><div class="summary-grid">{summary_cards}</div></section>
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
        <section class="panel"><div class="panel-head"><h2>货物项报价表</h2><span>目标加价率 / 手动售价</span></div><table><thead><tr><th>订单</th><th>货物项</th><th>供应商</th><th>采购单价</th><th>采购币种</th><th>目标加价率</th><th>手动售价</th><th>销售币种</th><th></th></tr></thead><tbody>{quote_rows}</tbody></table></section>
        <section class="panel"><div class="panel-head"><h2>成本明细</h2><span>采购、国内物流、仓储等</span></div><table><thead><tr><th>SKU</th><th>科目</th><th>金额</th><th>币种</th><th>汇率</th><th>备注</th><th>操作</th></tr></thead><tbody>{cost_rows}</tbody></table></section>
        <section class="panel"><div class="panel-head"><h2>客户收费明细</h2><span>产品销售、运费服务等</span></div><table><thead><tr><th>SKU</th><th>科目</th><th>金额</th><th>币种</th><th>汇率</th><th>备注</th><th>操作</th></tr></thead><tbody>{charge_rows}</tbody></table></section>
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
        <section class="panel pad document-blocker-scroll"><div class="panel-head"><h2>单证阻塞项</h2><span>{esc(selected_order['order_no'])}</span></div>{blocker_block}</section>
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


def settings_page(user: sqlite3.Row) -> str:
    conn = ensure_database()
    try:
        seller = get_setting(conn, "seller")
        defaults = get_setting(conn, "defaults")
        reminders = get_setting(conn, "reminders")
    finally:
        conn.close()
    fields = [
        ("seller_company_name", "卖方公司", seller.get("company_name", "")),
        ("seller_address", "卖方地址", seller.get("address", "")),
        ("seller_phone", "卖方电话", seller.get("phone", "")),
        ("seller_email", "卖方邮箱", seller.get("email", "")),
        ("origin_country", "默认起运国家", defaults.get("origin_country", "")),
        ("origin_port", "默认起运港", defaults.get("origin_port", "")),
        ("purchase_currency", "默认采购币种", defaults.get("purchase_currency", "")),
        ("sales_currency", "默认销售币种", defaults.get("sales_currency", "")),
        ("lead_days", "提醒提前天数", reminders.get("lead_days", 3)),
    ]
    body = "".join(f'<label>{label}<input name="{name}" value="{esc(value)}"></label>' for name, label, value in fields)
    return page(
        "系统设置",
        f"""
        <section class="toolbar"><div><h1>系统设置</h1><p>系统默认值和卖方信息</p></div></section>
        <section class="panel pad"><form method="post" action="/settings" class="form-grid">{body}<button type="submit">保存</button></form></section>
        """,
        user=user,
    )


def crud_page(user: sqlite3.Row, title: str, action: str, fields: list[tuple[str, str]], headers: list[str], rows: str) -> str:
    inputs = "".join(f'<label>{label}<input name="{name}"></label>' for name, label in fields)
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    return page(
        title,
        f"""
        <section class="toolbar"><div><h1>{esc(title)}</h1><p>主数据维护</p></div></section>
        <section class="panel pad"><form method="post" action="{action}" class="form-grid">{inputs}<button type="submit">新增</button></form></section>
        <section class="panel"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></section>
        """,
        user=user,
    )


def page(title: str, body: str, *, user: sqlite3.Row | None = None, chrome: bool = True) -> str:
    if not chrome:
        shell = body
    else:
        nav = navigation(user["role"] if user else "", CURRENT_PATH)
        utilities = utility_menu(user["role"] if user else "")
        shell = f"""
        <div class="app">
          <aside>
            <div class="brand">CargoPilot</div>
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
      <body>{shell}</body>
    </html>"""


def navigation(role: str, current_path: str = "/dashboard") -> str:
    items = [("Dashboard", "/dashboard"), ("订单详情", "/orders"), ("货物详情", "/tracking"), ("仓库盘点", "/receiving")]
    if role == ROLE_ADMIN:
        items += [("海运单证", "/shipping-docs"), ("成本利润", "/excel-finance")]
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
    if role != ROLE_ADMIN:
        return ""
    links = [
        ("供应商", "/suppliers"),
        ("系统设置", "/settings"),
    ]
    return (
        "<details class='utility-menu'><summary>管理/设置</summary>"
        + "".join(f'<a href="{href}">{label}</a>' for label, href in links)
        + "</details>"
    )


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
    return "".join(
        finance_row(row, goods_options, cost_options, charge_options)
        for row in filtered
    ) or '<tr><td colspan="7" class="empty">暂无记录</td></tr>'


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
    return f"""
    <form method="post" action="{action}" class="form-grid">
      <input type="hidden" name="import_order_id" value="{import_order_id}">
      <input type="hidden" name="line_kind" value="{line_kind}">
      <label>货物项(可空)<select name="goods_line_id">{goods_options}</select></label>
      {type_select}
      <label>金额<input name="amount" type="number" step="0.01" required value="{esc(row['amount'] if row else '')}"></label>
      <label>币种<input name="currency" value="{esc((row['currency'] if row else '') or 'EUR')}"></label>
      <label>折算到基准币汇率<input name="exchange_rate_to_base" type="number" step="0.0001" value="{esc((row['exchange_rate_to_base'] if row else '') or '1')}"></label>
      <label>备注<input name="notes" value="{esc(row['notes'] if row else '')}"></label>
      <button type="submit">{title}</button>
    </form>
    """


def options_with_selected(options: str, value: str) -> str:
    if not value:
        return options
    return options.replace(f"value='{esc(value)}'", f"value='{esc(value)}' selected", 1).replace(f'value="{esc(value)}"', f'value="{esc(value)}" selected', 1)


def _quote_row(line: sqlite3.Row) -> str:
    form_id = f"quote-{line['id']}"
    return f"""
    <tr>
      <td>{esc(line['order_no'])}</td>
      <td><a href="/goods-lines/{line['id']}/edit">{esc(line['sku_or_model'] or line['customs_en_name'] or line['cn_name'])}</a></td>
      <td>{esc(line['supplier_name'])}</td>
      <td><input class="mini-input" form="{form_id}" name="purchase_unit_price" type="number" step="0.01" value="{esc(line['purchase_unit_price'])}"></td>
      <td><input class="mini-input" form="{form_id}" name="purchase_currency" value="{esc(line['purchase_currency'] or 'CNY')}"></td>
      <td><input class="mini-input" form="{form_id}" name="target_markup" type="number" step="0.01" value="{esc(line['target_markup'])}"></td>
      <td><input class="mini-input" form="{form_id}" name="manual_sales_unit_price" type="number" step="0.01" value="{esc(line['sales_unit_price'])}"></td>
      <td><input class="mini-input" form="{form_id}" name="sales_currency" value="{esc(line['sales_currency'] or 'EUR')}"></td>
      <td><form id="{form_id}" method="post" action="/finance/quote"><input type="hidden" name="goods_line_id" value="{line['id']}"><input type="hidden" name="import_order_id" value="{line['import_order_id']}"><button type="submit">保存</button></form></td>
    </tr>
    """


def _ensure_demo_users(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM users WHERE email = 'admin@example.com'").fetchone() is None:
        create_user(conn, email="admin@example.com", name="Admin", role=ROLE_ADMIN, password="admin")
    if conn.execute("SELECT 1 FROM users WHERE email = 'warehouse@example.com'").fetchone() is None:
        create_user(conn, email="warehouse@example.com", name="Warehouse", role=ROLE_WAREHOUSE, password="warehouse")


def handle_supplier_post(form: dict[str, str]) -> None:
    conn = ensure_database()
    try:
        create_supplier(
            conn,
            actor_role=ROLE_ADMIN,
            name=form["name"],
            contact_name=form.get("contact_name", ""),
            phone=form.get("phone", ""),
            email=form.get("email", ""),
            wechat=form.get("wechat", ""),
            address=form.get("address", ""),
            business_id=form.get("business_id", ""),
            store_url=form.get("store_url", ""),
            usual_categories=[x.strip() for x in form.get("usual_categories", "").split(",") if x.strip()],
            notes=form.get("notes", ""),
        )
    finally:
        conn.close()


def handle_consignee_post(form: dict[str, str]) -> None:
    conn = ensure_database()
    try:
        create_consignee(conn, actor_role=ROLE_ADMIN, **consignee_values(form))
    finally:
        conn.close()


def handle_order_consignee_post(form: dict[str, str]) -> None:
    handle_consignee_post(form)


def handle_order_consignee_edit_post(form: dict[str, str], consignee_id: int) -> None:
    conn = ensure_database()
    try:
        update_consignee(conn, actor_role=ROLE_ADMIN, consignee_id=consignee_id, **consignee_values(form))
    finally:
        conn.close()


def handle_order_consignee_delete_post(consignee_id: int) -> str:
    conn = ensure_database()
    try:
        used = conn.execute("SELECT 1 FROM import_orders WHERE consignee_id = ? LIMIT 1", (consignee_id,)).fetchone()
        if used:
            return "该收货客户已关联订单，不能删除"
        conn.execute("DELETE FROM consignees WHERE id = ?", (consignee_id,))
        conn.commit()
        return ""
    finally:
        conn.close()


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


def handle_receiving_warehouse_post(form: dict[str, str]) -> int:
    conn = ensure_database()
    try:
        return create_warehouse(conn, actor_role=ROLE_ADMIN, **warehouse_values(form))
    finally:
        conn.close()


def handle_receiving_warehouse_edit_post(form: dict[str, str], warehouse_id: int) -> None:
    conn = ensure_database()
    try:
        update_warehouse(conn, actor_role=ROLE_ADMIN, warehouse_id=warehouse_id, **warehouse_values(form))
    finally:
        conn.close()


def handle_receiving_warehouse_delete_post(warehouse_id: int) -> str:
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
        seller.update({
            "company_name": form.get("seller_company_name", ""),
            "address": form.get("seller_address", ""),
            "phone": form.get("seller_phone", ""),
            "email": form.get("seller_email", ""),
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


def handle_quote_post(form: dict[str, str]) -> None:
    conn = ensure_database()
    try:
        update_goods_line_quote(
            conn,
            actor_role=ROLE_ADMIN,
            goods_line_id=int(form["goods_line_id"]),
            purchase_unit_price=float_or_none(form.get("purchase_unit_price", "")) or 0,
            purchase_currency=form.get("purchase_currency", "") or "CNY",
            sales_currency=form.get("sales_currency", "") or "EUR",
            target_markup=float_or_none(form.get("target_markup", "")),
            manual_sales_unit_price=float_or_none(form.get("manual_sales_unit_price", "")),
        )
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
                output[name] = UploadedFile(Path(filename).name, part.get_content_type(), payload)
            else:
                output[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return output
    parsed = parse_qs(body.decode())
    return {key: values[0] if values else "" for key, values in parsed.items()}


def esc(value) -> str:
    return html.escape(str(value or ""))


def money(value) -> str:
    return f"{float(value or 0):.2f}"


CSS = """
:root { color-scheme: light; --bg:#f5f7fa; --ink:#16202a; --muted:#697785; --line:#dce3ea; --panel:#fff; --accent:#0f7c86; }
* { box-sizing: border-box; }
body { margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--ink); }
a { color: inherit; text-decoration: none; }
.app { min-height:100vh; display:grid; grid-template-columns: 232px 1fr; }
aside { background:#14212b; color:#dce7ef; padding:22px 16px; }
.brand { font-size:20px; font-weight:750; margin-bottom:28px; }
nav { display:grid; gap:6px; }
nav a { padding:10px 12px; border-radius:6px; color:#b8c7d3; font-size:14px; }
nav a:hover, nav a.active { background:#20313d; color:white; }
.workspace { min-width:0; }
header { height:56px; display:flex; justify-content:flex-end; align-items:center; gap:18px; padding:0 28px; background:white; border-bottom:1px solid var(--line); color:var(--muted); font-size:14px; }
main { padding:26px 28px; }
.utility-menu { position:relative; }
.utility-menu summary { cursor:pointer; color:#314351; font-weight:650; list-style:none; }
.utility-menu summary::-webkit-details-marker { display:none; }
.utility-menu[open] summary { color:var(--accent); }
.utility-menu a { display:block; padding:9px 12px; white-space:nowrap; background:white; }
.utility-menu a:hover { background:#f2f6f8; color:#0f6670; }
.utility-menu[open] { z-index:5; }
.utility-menu[open]::after { content:""; position:absolute; right:0; top:28px; width:150px; height:148px; background:white; border:1px solid var(--line); border-radius:8px; box-shadow:0 12px 28px rgba(20,33,43,.12); z-index:-1; }
.toolbar { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; margin-bottom:20px; }
h1, h2, p { margin:0; }
h1 { font-size:28px; line-height:1.2; letter-spacing:0; }
h2 { font-size:16px; }
.toolbar p { color:var(--muted); margin-top:6px; }
.search input, label input { width:320px; height:38px; border:1px solid var(--line); border-radius:6px; padding:0 12px; font:inherit; background:white; }
.metric-grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:14px; margin-bottom:18px; }
.metric-grid a { display:block; }
.metric-grid article, .panel, .login-card { background:var(--panel); border:1px solid var(--line); border-radius:8px; }
.metric-grid article { padding:16px; display:grid; gap:4px; }
.metric-grid strong { font-size:26px; }
.metric-grid span, .hint { color:var(--muted); font-size:13px; }
.summary-grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; margin-top:14px; }
.summary-grid article { border:1px solid var(--line); border-radius:6px; padding:12px; background:#f8fafc; display:grid; gap:5px; }
.summary-grid span { color:var(--muted); font-size:12px; }
.summary-grid strong { font-size:16px; font-weight:750; }
.action-row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:14px; }
.icon-form { display:inline; margin:0; }
.icon-button { display:inline-flex; align-items:center; justify-content:center; width:32px; height:32px; border:1px solid var(--line); border-radius:6px; background:#f8fafc; color:#1f2937; font-weight:800; text-decoration:none; cursor:pointer; }
.icon-button.danger { color:#991b1b; border-color:#fecaca; background:#fff1f2; }
.action-drawer { display:inline-block; }
.action-drawer summary, .button-link { display:inline-flex; align-items:center; justify-content:center; min-height:36px; padding:0 12px; border-radius:6px; background:var(--accent); color:white; font-weight:700; cursor:pointer; }
.action-drawer summary { list-style:none; }
.action-drawer summary::-webkit-details-marker { display:none; }
.action-drawer[open] { position:fixed; inset:0; z-index:20; display:grid; place-items:center; padding:24px; background:rgba(15,23,42,.32); }
.action-drawer[open] summary { position:fixed; top:18px; right:24px; background:#334155; }
.action-drawer[open] summary::after { content:" / 返回关闭"; }
.action-drawer[open] form, .action-drawer[open] .drawer-stack { width:min(760px, 100%); max-height:calc(100vh - 100px); overflow:auto; padding:14px; border:1px solid var(--line); border-radius:8px; background:#f8fafc; box-shadow:0 18px 48px rgba(15,23,42,.24); }
.action-drawer[open] .drawer-stack form { width:auto; max-height:none; overflow:visible; padding:0; border:0; box-shadow:none; }
.panel { overflow:hidden; }
.scroll-panel { max-height:248px; overflow:auto; }
.table-scroll { overflow-x:auto; }
.tracking-scroll { max-height:calc(100vh - 300px); min-height:260px; overflow:scroll; }
.tracking-scroll table { min-width:1760px; }
.warehouse-scroll { max-height:420px; overflow:scroll; }
.warehouse-scroll table { min-width:1280px; }
.document-blocker-scroll { max-height:260px; overflow:auto; }
.panel-head { display:flex; justify-content:space-between; padding:16px 18px; border-bottom:1px solid var(--line); color:var(--muted); }
table { width:100%; border-collapse:collapse; font-size:14px; }
th, td { padding:12px 14px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }
th { color:#536270; font-size:12px; text-transform:uppercase; letter-spacing:.04em; background:#f8fafc; }
progress { width:90px; vertical-align:middle; accent-color:var(--accent); }
.status { display:inline-flex; align-items:center; min-height:24px; border-radius:999px; padding:0 9px; font-size:12px; font-weight:650; color:#24313c; background:#e8edf2; }
.status.blue { background:#d9ebff; color:#0b4d82; }
.status.orange { background:#ffe7c2; color:#885200; }
.status.green { background:#d9f4df; color:#176331; }
.status.red { background:#ffe0df; color:#8b1d18; }
.status.navy { background:#dfe7f5; color:#1e3c70; }
.status.teal, .status.cyan { background:#d7f2f1; color:#0e6264; }
.status.purple, .status.indigo { background:#e8e3ff; color:#46318a; }
.inline-status select { height:30px; border:1px solid var(--line); border-radius:999px; padding:0 9px; background:#f8fafc; font:inherit; font-size:12px; font-weight:650; }
.empty { text-align:center; color:var(--muted); padding:34px; }
.login { min-height:100vh; display:grid; place-items:center; padding:24px; }
.login-card { width:min(420px, 100%); padding:28px; display:grid; gap:20px; }
.login-card form { display:grid; gap:14px; }
label { display:grid; gap:6px; color:#536270; font-size:13px; }
label input, label select { width:100%; height:38px; border:1px solid var(--line); border-radius:6px; padding:0 10px; background:white; font:inherit; }
button { height:40px; border:0; border-radius:6px; background:var(--accent); color:white; font-weight:700; cursor:pointer; }
.pad { padding:18px; margin-bottom:18px; }
.form-grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:14px; align-items:end; }
.form-grid button { align-self:end; }
.filter-bar { display:flex; gap:12px; align-items:end; flex-wrap:wrap; }
.filter-bar label { min-width:190px; }
.filter-bar .check { display:flex; grid-template-columns:none; align-items:center; min-width:auto; height:38px; gap:8px; }
.check input { width:auto; height:auto; }
.two-col { display:grid; grid-template-columns: minmax(0, 1.2fr) minmax(260px, .8fr); gap:18px; margin-bottom:18px; }
.stack { display:grid; gap:10px; margin-top:14px; }
.link-list { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
.link-list a { border:1px solid var(--line); border-radius:6px; padding:9px 11px; color:#0f6670; background:#f8fafc; }
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
  .app { grid-template-columns: 1fr; }
  aside { display:none; }
  .toolbar { display:grid; }
  .metric-grid { grid-template-columns:1fr; }
  .summary-grid { grid-template-columns:1fr; }
  .two-col { grid-template-columns:1fr; }
  .form-grid { grid-template-columns:1fr; }
  table { display:block; overflow:auto; }
}
"""


if __name__ == "__main__":
    run()

from __future__ import annotations

from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import html
import shutil
import secrets
import sqlite3
from urllib.parse import parse_qs, quote, urlparse

from .dashboard import dashboard_orders
from .finance import (
    CHARGE_TYPES,
    COST_TYPES,
    LINE_CHARGE,
    LINE_COST,
    add_finance_line,
    calculate_profit,
    update_goods_line_quote,
)
from .foundation import ROLE_ADMIN, ROLE_WAREHOUSE, authenticate, connect, create_user, get_setting, initialize_database, set_setting
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
    update_goods_line,
)
from .receiving import ARRIVAL_EXCEPTION_TYPES, record_receiving, resolve_arrival_exception, search_receiving
from .spreadsheet_io import (
    ImportResult,
    export_goods_lines,
    export_import_orders,
    export_rows_xlsx,
    import_customer_purchase_list,
    import_supplier_package_logistics,
)

APP_DB = Path("data/cargopilot.sqlite3")
SESSIONS: dict[str, int] = {}


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
        parsed = urlparse(self.path)
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
            self._send(HTTPStatus.OK, dashboard_page(user), "text/html; charset=utf-8")
            return
        if parsed.path == "/orders":
            self._send(HTTPStatus.OK, orders_page(user), "text/html; charset=utf-8")
            return
        if parsed.path == "/receiving":
            query = parse_qs(parsed.query).get("q", [""])[0]
            self._send(HTTPStatus.OK, receiving_page(user, query), "text/html; charset=utf-8")
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
            self._admin_page(user, excel_finance_page)
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
        form = form_data(self.rfile.read(length).decode())
        if parsed.path != "/login":
            user = self._current_user()
            if user is None:
                self._redirect("/login")
                return
            if parsed.path == "/receiving/record":
                handle_receiving_record_post(form, user)
                self._redirect(f"/receiving?q={quote(form.get('query', ''))}")
                return
            if parsed.path == "/receiving/resolve":
                handle_receiving_resolve_post(form, user)
                self._redirect(f"/receiving?q={quote(form.get('query', ''))}")
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
            if parsed.path == "/settings":
                handle_settings_post(form)
                self._redirect("/settings")
                return
            if parsed.path == "/excel/customer-import":
                result = handle_customer_import_post(form)
                self._send(HTTPStatus.OK, excel_finance_page(user, "客户采购清单导入完成", result.errors), "text/html; charset=utf-8")
                return
            if parsed.path == "/excel/package-import":
                result = handle_package_import_post(form)
                self._send(HTTPStatus.OK, excel_finance_page(user, "供应商包装物流导入完成", result.errors), "text/html; charset=utf-8")
                return
            if parsed.path == "/finance/quote":
                handle_quote_post(form)
                self._redirect("/excel-finance")
                return
            if parsed.path == "/finance/line":
                handle_finance_line_post(form)
                self._redirect("/excel-finance")
                return
            if parsed.path == "/orders":
                order_id = handle_order_post(form)
                self._redirect(f"/orders/{order_id}")
                return
            order_goods_id = suffix_path_id(parsed.path, "/orders/", "/goods-lines")
            if order_goods_id is not None:
                goods_line_id = handle_goods_line_post(form, order_goods_id)
                self._redirect(f"/goods-lines/{goods_line_id}/edit")
                return
            goods_line_edit_id = edit_path_id(parsed.path, "/goods-lines/")
            if goods_line_edit_id is not None:
                handle_goods_line_edit_post(form, goods_line_edit_id)
                self._redirect(f"/goods-lines/{goods_line_edit_id}/edit")
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


def dashboard_page(user: sqlite3.Row) -> str:
    conn = ensure_database()
    try:
        cards = dashboard_orders(conn)
    finally:
        conn.close()
    rows = "\n".join(_order_row(card) for card in cards) or '<tr><td colspan="8" class="empty">暂无订单</td></tr>'
    return page(
        "Dashboard",
        f"""
        <section class="toolbar">
          <div>
            <h1>Dashboard</h1>
            <p>当前订单、异常和缺失资料</p>
          </div>
          <form class="search"><input aria-label="搜索" placeholder="搜索订单、客户、物流单号、麦头"></form>
        </section>
        <section class="metric-grid">
          <article><strong>{len(cards)}</strong><span>活跃订单</span></article>
          <article><strong>{sum(card['exception_count'] for card in cards)}</strong><span>异常</span></article>
          <article><strong>{sum(card['missing_data_count'] for card in cards)}</strong><span>缺失资料</span></article>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Import Orders</h2><span>{html.escape(role_label(user['role']))}</span></div>
          <table>
            <thead>
              <tr><th>订单号</th><th>客户</th><th>目的港</th><th>状态</th><th>进度</th><th>预计装柜</th><th>异常</th><th>缺失</th></tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
        """,
        user=user,
    )


def orders_page(user: sqlite3.Row) -> str:
    conn = ensure_database()
    try:
        orders = conn.execute(
            """
            SELECT import_orders.*, consignees.company_name
            FROM import_orders
            LEFT JOIN consignees ON consignees.id = import_orders.consignee_id
            ORDER BY import_orders.created_at DESC
            """
        ).fetchall()
        consignees = conn.execute("SELECT id, company_name FROM consignees ORDER BY company_name").fetchall()
        receiving = list_warehouses(conn, WAREHOUSE_RECEIVING)
        ports = list_warehouses(conn, WAREHOUSE_PORT)
    finally:
        conn.close()
    form = "" if user["role"] != ROLE_ADMIN else f"""
      <section class="panel pad"><form method="post" action="/orders" class="form-grid">
        {select_input("consignee_id", "客户", consignees, "company_name")}
        {select_input("receiving_warehouse_id", "收货仓", receiving, "name")}
        {select_input("port_warehouse_id", "港口仓", ports, "name")}
        <label>订单号(可空)<input name="order_no"></label>
        <label>贸易条款<input name="trade_term" placeholder="FOB"></label>
        <label>目的国家<input name="destination_country"></label>
        <label>目的港<input name="destination_port"></label>
        <label>预计装柜日<input name="expected_loading_date" type="date"></label>
        <label>备注<input name="internal_notes"></label>
        <button type="submit">新增订单</button>
      </form></section>
    """
    rows = "".join(
        f"<tr><td><a href='/orders/{o['id']}'>{esc(o['order_no'])}</a></td><td>{esc(o['company_name'])}</td><td>{esc(o['destination_port'])}</td><td><span class='status blue'>{esc(o['order_status'])}</span></td><td>{esc(o['expected_loading_date'])}</td></tr>"
        for o in orders
    ) or '<tr><td colspan="5" class="empty">暂无订单</td></tr>'
    return page("Import Orders", f"""
      <section class="toolbar"><div><h1>Import Orders</h1><p>订单列表和创建</p></div></section>
      {form}
      <section class="panel"><table><thead><tr><th>订单号</th><th>客户</th><th>目的港</th><th>状态</th><th>预计装柜</th></tr></thead><tbody>{rows}</tbody></table></section>
    """, user=user)


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
    return page(
        f"Goods Line {goods_line_id}",
        f"<section class='toolbar'><div><h1>Goods Line {goods_line_id}</h1><p>分组编辑商品信息</p></div></section>{goods_line_form(f'/goods-lines/{goods_line_id}/edit', suppliers, goods, disabled=user['role'] != ROLE_ADMIN)}",
        user=user,
    )


def receiving_page(user: sqlite3.Row, query: str = "") -> str:
    conn = ensure_database()
    try:
        results = search_receiving(conn, actor_role=user["role"], query=query)
    finally:
        conn.close()
    exception_options = "<option value=''></option>" + "".join(
        f"<option value='{esc(value)}'>{esc(value)}</option>" for value in sorted(ARRIVAL_EXCEPTION_TYPES)
    )
    rows = "".join(_receiving_row(row, query, exception_options) for row in results) or '<tr><td colspan="10" class="empty">暂无匹配商品行</td></tr>'
    return page(
        "Warehouse Receiving",
        f"""
        <section class="toolbar">
          <div><h1>Warehouse Receiving</h1><p>按订单号、国内物流单号或麦头搜索并登记到货</p></div>
          <form class="search" method="get" action="/receiving"><input name="q" value="{esc(query)}" placeholder="CP-2026 / YT123 / shipping mark"></form>
        </section>
        <section class="panel">
          <table>
            <thead><tr><th>订单</th><th>商品</th><th>麦头</th><th>物流单号</th><th>状态</th><th>到货箱数</th><th>包装</th><th>异常</th><th>照片路径</th><th></th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
        """,
        user=user,
    )


def _receiving_row(row: dict, query: str, exception_options: str) -> str:
    form_id = f"receive-{row['goods_line_id']}"
    resolve = ""
    if row["logistics_status"] == "exception":
        resolve = (
            f"<form method='post' action='/receiving/resolve' class='inline-form'>"
            f"<input type='hidden' name='goods_line_id' value='{row['goods_line_id']}'>"
            f"<input type='hidden' name='query' value='{esc(query)}'>"
            f"<button type='submit'>解除异常</button></form>"
        )
    return f"""
    <tr>
      <td>{esc(row['order_no'])}</td>
      <td><a href="/goods-lines/{row['goods_line_id']}/edit">{esc(row['customs_en_name'] or row['cn_name'])}</a></td>
      <td>{esc(row['shipping_mark'])}</td>
      <td><input class="mini-input" form="{form_id}" name="domestic_tracking_no" value="{esc(row['tracking_numbers'])}"></td>
      <td><span class="status blue">{esc(row['logistics_status'])}</span>{resolve}</td>
      <td><input class="mini-input" form="{form_id}" name="received_carton_count" type="number" min="0" required></td>
      <td><input class="mini-input" form="{form_id}" name="package_condition" placeholder="ok/damaged"></td>
      <td><select class="mini-input" form="{form_id}" name="arrival_exception_type">{exception_options}</select></td>
      <td><input class="mini-input" form="{form_id}" name="receiving_photo_path" placeholder="/path/photo.jpg"></td>
      <td>
        <form id="{form_id}" method="post" action="/receiving/record">
          <input type="hidden" name="goods_line_id" value="{row['goods_line_id']}">
          <input type="hidden" name="query" value="{esc(query)}">
          <button type="submit">登记</button>
        </form>
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
        "Suppliers",
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
        "Consignees",
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
        f"<tr><td>{w['id']}</td><td>{esc(w['type'])}</td><td>{esc(w['name'])}</td><td>{esc(w['contact_name'])}</td><td>{esc(w['phone'])}</td><td>{esc(w['address'])}</td></tr>"
        for w in warehouses
    ) or '<tr><td colspan="6" class="empty">暂无仓库</td></tr>'
    return crud_page(
        user,
        "Warehouses",
        "/warehouses",
        [
            ("type", "类型 receiving/port"),
            ("name", "名称"),
            ("contact_name", "联系人"),
            ("phone", "电话"),
            ("address", "地址"),
            ("notes", "备注"),
        ],
        ["ID", "类型", "名称", "联系人", "电话", "地址"],
        rows,
    )


def excel_finance_page(user: sqlite3.Row, message: str = "", errors: list[str] | None = None) -> str:
    conn = ensure_database()
    try:
        orders = conn.execute("SELECT id, order_no, sales_currency FROM import_orders ORDER BY created_at DESC").fetchall()
        goods = conn.execute(
            """
            SELECT goods_lines.*, import_orders.order_no, suppliers.name AS supplier_name
            FROM goods_lines
            JOIN import_orders ON import_orders.id = goods_lines.import_order_id
            LEFT JOIN suppliers ON suppliers.id = goods_lines.supplier_id
            ORDER BY goods_lines.id DESC
            """
        ).fetchall()
        finance_rows = conn.execute(
            """
            SELECT finance_lines.*, import_orders.order_no, goods_lines.sku_or_model
            FROM finance_lines
            JOIN import_orders ON import_orders.id = finance_lines.import_order_id
            LEFT JOIN goods_lines ON goods_lines.id = finance_lines.goods_line_id
            ORDER BY finance_lines.created_at DESC
            LIMIT 30
            """
        ).fetchall()
        summaries = [(order, calculate_profit(conn, import_order_id=order["id"], base_currency=order["sales_currency"] or "EUR")) for order in orders]
    finally:
        conn.close()
    notice = f"<p class='notice'>{esc(message)}</p>" if message else ""
    error_html = "".join(f"<li>{esc(error)}</li>" for error in (errors or []))
    errors_block = f"<section class='panel pad'><h2>导入错误</h2><ul class='errors'>{error_html}</ul></section>" if error_html else ""
    order_options = "".join(f"<option value='{order['id']}'>{esc(order['order_no'])}</option>" for order in orders)
    goods_options = "<option value=''></option>" + "".join(
        f"<option value='{line['id']}'>{esc(line['order_no'])} · #{line['id']} {esc(line['sku_or_model'] or line['customs_en_name'] or line['cn_name'])}</option>"
        for line in goods
    )
    cost_options = "".join(f"<option value='{esc(kind)}'>{esc(kind)}</option>" for kind in sorted(COST_TYPES))
    charge_options = "".join(f"<option value='{esc(kind)}'>{esc(kind)}</option>" for kind in sorted(CHARGE_TYPES))
    quote_rows = "".join(_quote_row(line) for line in goods) or '<tr><td colspan="9" class="empty">暂无商品行</td></tr>'
    finance_table = "".join(
        f"<tr><td>{esc(row['order_no'])}</td><td>{esc(row['sku_or_model'])}</td><td>{esc(row['line_kind'])}</td><td>{esc(row['line_type'])}</td><td>{esc(row['amount'])}</td><td>{esc(row['currency'])}</td><td>{esc(row['exchange_rate_to_base'])}</td><td>{esc(row['notes'])}</td></tr>"
        for row in finance_rows
    ) or '<tr><td colspan="8" class="empty">暂无成本/收费</td></tr>'
    summary_rows = "".join(
        f"<tr><td>{esc(order['order_no'])}</td><td>{money(summary['total_cost'])}</td><td>{money(summary['total_charge'])}</td><td>{money(summary['profit'])}</td><td>{esc(summary['base_currency'])}</td></tr>"
        for order, summary in summaries
    ) or '<tr><td colspan="5" class="empty">暂无利润汇总</td></tr>'
    return page(
        "Excel & Finance",
        f"""
        <section class="toolbar"><div><h1>Excel & Finance</h1><p>固定模板导入、导出、报价和利润估算</p></div></section>
        {notice}
        {errors_block}
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
        <section class="panel pad">
          <h2>新增成本/收费</h2>
          <form method="post" action="/finance/line" class="form-grid">
            <label>订单<select name="import_order_id" required>{order_options}</select></label>
            <label>商品行(可空)<select name="goods_line_id">{goods_options}</select></label>
            <label>类型<select name="line_kind"><option value="{LINE_COST}">cost</option><option value="{LINE_CHARGE}">charge</option></select></label>
            <label>成本科目<select name="cost_type">{cost_options}</select></label>
            <label>收费科目<select name="charge_type">{charge_options}</select></label>
            <label>金额<input name="amount" type="number" step="0.01" required></label>
            <label>币种<input name="currency" value="EUR"></label>
            <label>折算到基准币汇率<input name="exchange_rate_to_base" type="number" step="0.0001" value="1"></label>
            <label>备注<input name="notes"></label>
            <button type="submit">新增记录</button>
          </form>
        </section>
        <section class="panel"><div class="panel-head"><h2>报价调整</h2><span>Target Markup / Manual Price</span></div><table><thead><tr><th>订单</th><th>商品</th><th>供应商</th><th>采购单价</th><th>采购币种</th><th>加价率</th><th>手动售价</th><th>销售币种</th><th></th></tr></thead><tbody>{quote_rows}</tbody></table></section>
        <section class="panel"><div class="panel-head"><h2>利润汇总</h2><span>手动汇率折算</span></div><table><thead><tr><th>订单</th><th>总成本</th><th>总收费</th><th>利润</th><th>基准币</th></tr></thead><tbody>{summary_rows}</tbody></table></section>
        <section class="panel"><div class="panel-head"><h2>成本/收费明细</h2><span>最近 30 条</span></div><table><thead><tr><th>订单</th><th>SKU</th><th>Kind</th><th>Type</th><th>金额</th><th>币种</th><th>汇率</th><th>备注</th></tr></thead><tbody>{finance_table}</tbody></table></section>
        """,
        user=user,
    )


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
        "Settings",
        f"""
        <section class="toolbar"><div><h1>Settings</h1><p>系统默认值和卖方信息</p></div></section>
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
        nav = navigation(user["role"] if user else "")
        shell = f"""
        <div class="app">
          <aside>
            <div class="brand">CargoPilot</div>
            {nav}
          </aside>
          <div class="workspace">
            <header><span>{html.escape(user['email']) if user else ''}</span><a href="/logout">退出</a></header>
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


def navigation(role: str) -> str:
    items = [("Dashboard", "/dashboard"), ("Import Orders", "/orders"), ("Goods Lines", "/orders"), ("Warehouse Receiving", "/receiving")]
    if role == ROLE_ADMIN:
        items += [("Excel & Finance", "/excel-finance"), ("Suppliers", "/suppliers"), ("Consignees", "/consignees"), ("Warehouses", "/warehouses"), ("Documents", "#"), ("Settings", "/settings")]
    return '<nav>' + "".join(f'<a href="{href}">{label}</a>' for label, href in items) + "</nav>"


def role_label(role: str) -> str:
    return "管理员" if role == ROLE_ADMIN else "仓库员"


def _order_row(card: dict) -> str:
    return f"""
    <tr>
      <td>{html.escape(str(card['order_no']))}</td>
      <td>{html.escape(str(card['consignee']))}</td>
      <td>{html.escape(str(card['destination_port']))}</td>
      <td><span class="status {html.escape(card['status_color'])}">{html.escape(str(card['order_status']))}</span></td>
      <td><progress max="100" value="{card['order_stage_progress']}"></progress> {card['order_stage_progress']}%</td>
      <td>{html.escape(str(card['expected_loading_date'] or ''))}</td>
      <td><a href="#">{card['exception_count']}</a></td>
      <td><a href="#">{card['missing_data_count']}</a></td>
    </tr>
    """


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
      <td><form id="{form_id}" method="post" action="/finance/quote"><input type="hidden" name="goods_line_id" value="{line['id']}"><button type="submit">保存</button></form></td>
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
        create_consignee(conn, actor_role=ROLE_ADMIN, **{k: form.get(k, "") for k in [
            "company_name", "contact_name", "email", "phone", "tax_id", "address",
            "default_destination_port", "default_trade_term", "default_sales_currency",
            "document_preferences", "notes",
        ]})
    finally:
        conn.close()


def handle_warehouse_post(form: dict[str, str]) -> None:
    conn = ensure_database()
    try:
        create_warehouse(
            conn,
            actor_role=ROLE_ADMIN,
            type=form.get("type", WAREHOUSE_RECEIVING) or WAREHOUSE_RECEIVING,
            name=form["name"],
            contact_name=form.get("contact_name", ""),
            phone=form.get("phone", ""),
            address=form.get("address", ""),
            notes=form.get("notes", ""),
        )
    finally:
        conn.close()


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
            receiving_photo_path=save_receiving_photo(form.get("receiving_photo_path", "")),
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


def save_receiving_photo(source: str) -> str:
    if not source:
        return ""
    source_path = Path(source)
    if not source_path.exists() or not source_path.is_file():
        return source
    target_dir = APP_DB.parent / "uploads" / "receiving"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source_path.name
    shutil.copyfile(source_path, target)
    return str(target)


def handle_order_post(form: dict[str, str]) -> int:
    conn = ensure_database()
    try:
        return create_import_order(
            conn,
            actor_role=ROLE_ADMIN,
            order_no=form.get("order_no") or None,
            consignee_id=int_or_none(form.get("consignee_id", "")),
            receiving_warehouse_id=int_or_none(form.get("receiving_warehouse_id", "")),
            port_warehouse_id=int_or_none(form.get("port_warehouse_id", "")),
            trade_term=form.get("trade_term", ""),
            destination_country=form.get("destination_country", ""),
            destination_port=form.get("destination_port", ""),
            expected_loading_date=form.get("expected_loading_date") or None,
            internal_notes=form.get("internal_notes", ""),
        )
    finally:
        conn.close()


def handle_goods_line_post(form: dict[str, str], order_id: int) -> int:
    conn = ensure_database()
    try:
        return create_goods_line(conn, actor_role=ROLE_ADMIN, import_order_id=order_id, **goods_line_values(form))
    finally:
        conn.close()


def handle_goods_line_edit_post(form: dict[str, str], goods_line_id: int) -> None:
    conn = ensure_database()
    try:
        update_goods_line(conn, actor_role=ROLE_ADMIN, goods_line_id=goods_line_id, **goods_line_values(form))
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
                inputs.append(select_input("supplier_id", "supplier", suppliers, "name", selected=goods["supplier_id"] if goods else None, disabled=disabled))
            else:
                inputs.append(f'<label>{esc(field)}<input name="{field}" value="{esc(goods[field] if goods else "")}"{disabled_attr}></label>')
        sections.append(f"<fieldset><legend>{esc(group)}</legend><div class='form-grid'>{''.join(inputs)}</div></fieldset>")
    notes = f'<label>notes<input name="notes" value="{esc(goods["notes"] if goods else "")}"{disabled_attr}></label>'
    button = "" if disabled else "<button type='submit'>保存商品行</button>"
    return f"<section class='panel pad'><form method='post' action='{action}'>{''.join(sections)}<div class='form-grid'>{notes}{button}</div></form></section>"


def select_input(name: str, label: str, rows: list[sqlite3.Row], text_field: str, selected=None, disabled: bool = False) -> str:
    disabled_attr = " disabled" if disabled else ""
    options = ["<option value=''></option>"] + [
        f"<option value='{row['id']}'{' selected' if selected == row['id'] else ''}>{esc(row[text_field])}</option>"
        for row in rows
    ]
    return f"<label>{esc(label)}<select name='{name}'{disabled_attr}>{''.join(options)}</select></label>"


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


def int_or_none(value: str):
    return int(value) if value else None


def float_or_none(value: str):
    return float(value) if value else None


def form_data(body: str) -> dict[str, str]:
    parsed = parse_qs(body)
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
nav a:hover, nav a:first-child { background:#20313d; color:white; }
.workspace { min-width:0; }
header { height:56px; display:flex; justify-content:flex-end; align-items:center; gap:18px; padding:0 28px; background:white; border-bottom:1px solid var(--line); color:var(--muted); font-size:14px; }
main { padding:26px 28px; }
.toolbar { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; margin-bottom:20px; }
h1, h2, p { margin:0; }
h1 { font-size:28px; line-height:1.2; letter-spacing:0; }
h2 { font-size:16px; }
.toolbar p { color:var(--muted); margin-top:6px; }
.search input, label input { width:320px; height:38px; border:1px solid var(--line); border-radius:6px; padding:0 12px; font:inherit; background:white; }
.metric-grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:14px; margin-bottom:18px; }
.metric-grid article, .panel, .login-card { background:var(--panel); border:1px solid var(--line); border-radius:8px; }
.metric-grid article { padding:16px; display:grid; gap:4px; }
.metric-grid strong { font-size:26px; }
.metric-grid span, .hint { color:var(--muted); font-size:13px; }
.panel { overflow:hidden; }
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
.two-col { display:grid; grid-template-columns: minmax(0, 1.2fr) minmax(260px, .8fr); gap:18px; margin-bottom:18px; }
.stack { display:grid; gap:10px; margin-top:14px; }
.link-list { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
.link-list a { border:1px solid var(--line); border-radius:6px; padding:9px 11px; color:#0f6670; background:#f8fafc; }
.mini-input { width:112px; height:32px; border:1px solid var(--line); border-radius:6px; padding:0 8px; font:inherit; }
.notice { margin:0 0 16px; padding:10px 12px; background:#d9f4df; color:#176331; border-radius:6px; }
.errors { margin:10px 0 0; padding-left:20px; color:#a51d16; }
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
  .two-col { grid-template-columns:1fr; }
  .form-grid { grid-template-columns:1fr; }
  table { display:block; overflow:auto; }
}
"""


if __name__ == "__main__":
    run()

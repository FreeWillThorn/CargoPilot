from __future__ import annotations

from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import html
import secrets
import sqlite3
from urllib.parse import parse_qs, urlparse

from .dashboard import dashboard_orders
from .foundation import ROLE_ADMIN, ROLE_WAREHOUSE, authenticate, connect, create_user, initialize_database

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
        if parsed.path == "/logout":
            self._logout()
            return
        self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/login":
            self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode())
        conn = ensure_database()
        try:
            user = authenticate(conn, form.get("email", [""])[0], form.get("password", [""])[0])
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
    items = [("Dashboard", "/dashboard"), ("Import Orders", "#"), ("Goods Lines", "#"), ("Warehouse Receiving", "#")]
    if role == ROLE_ADMIN:
        items += [("Documents", "#"), ("Settings", "#")]
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


def _ensure_demo_users(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM users WHERE email = 'admin@example.com'").fetchone() is None:
        create_user(conn, email="admin@example.com", name="Admin", role=ROLE_ADMIN, password="admin")
    if conn.execute("SELECT 1 FROM users WHERE email = 'warehouse@example.com'").fetchone() is None:
        create_user(conn, email="warehouse@example.com", name="Warehouse", role=ROLE_WAREHOUSE, password="warehouse")


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
label input { width:100%; }
button { height:40px; border:0; border-radius:6px; background:var(--accent); color:white; font-weight:700; cursor:pointer; }
.error { color:#a51d16; font-size:14px; }
@media (max-width: 760px) {
  .app { grid-template-columns: 1fr; }
  aside { display:none; }
  .toolbar { display:grid; }
  .metric-grid { grid-template-columns:1fr; }
  table { display:block; overflow:auto; }
}
"""


if __name__ == "__main__":
    run()

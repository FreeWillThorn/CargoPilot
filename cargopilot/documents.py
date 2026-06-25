from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from .calculations import STAGE_FINAL_DOCUMENTS, calculate_cbm, calculate_gross_weight, check_goods_line_stage
from .foundation import get_setting, utc_now
from .master_data import require_admin
from .spreadsheet_io import export_rows_xlsx

DOC_COMMERCIAL_INVOICE = "commercial_invoice"
DOC_PACKING_LIST = "packing_list"
DOCUMENT_TYPES = {DOC_COMMERCIAL_INVOICE, DOC_PACKING_LIST}


class DocumentBlockedError(ValueError):
    def __init__(self, blockers: list[dict[str, Any]]):
        super().__init__("Export Document is blocked by missing fields")
        self.blockers = blockers


def generate_export_document(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    import_order_id: int,
    document_type: str,
    output_dir: str | Path,
    final: bool = True,
) -> dict[str, Any]:
    require_admin(actor_role)
    if document_type not in DOCUMENT_TYPES:
        raise ValueError(f"unknown document type: {document_type}")
    blockers = _document_blockers(conn, import_order_id)
    if final and blockers:
        raise DocumentBlockedError(blockers)

    version = _next_version(conn, import_order_id, document_type)
    data = build_document_data(conn, import_order_id=import_order_id, document_type=document_type, version=version)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = data["document_number"]
    xlsx_path = output_dir / f"{base}.xlsx"
    pdf_path = output_dir / f"{base}.pdf"
    _write_document_xlsx(xlsx_path, data)
    _write_document_pdf(pdf_path, data)
    status = "final" if final else "draft"
    cursor = conn.execute(
        """
        INSERT INTO documents (
            import_order_id, document_type, version, document_number,
            status, xlsx_path, pdf_path, generated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (import_order_id, document_type, version, data["document_number"], status, str(xlsx_path), str(pdf_path), utc_now()),
    )
    conn.commit()
    return {
        "id": int(cursor.lastrowid),
        "document_number": data["document_number"],
        "version": version,
        "status": status,
        "xlsx_path": str(xlsx_path),
        "pdf_path": str(pdf_path),
        "blockers": blockers,
    }


def build_document_data(
    conn: sqlite3.Connection,
    *,
    import_order_id: int,
    document_type: str,
    version: int,
) -> dict[str, Any]:
    order = conn.execute(
        """
        SELECT import_orders.*, consignees.company_name, consignees.address, consignees.tax_id
        FROM import_orders
        LEFT JOIN consignees ON consignees.id = import_orders.consignee_id
        WHERE import_orders.id = ?
        """,
        (import_order_id,),
    ).fetchone()
    if order is None:
        raise KeyError(import_order_id)
    seller = get_setting(conn, "seller")
    suffix = "INV" if document_type == DOC_COMMERCIAL_INVOICE else "PL"
    lines = _invoice_lines(conn, import_order_id) if document_type == DOC_COMMERCIAL_INVOICE else _packing_lines(conn, import_order_id)
    return {
        "document_type": document_type,
        "document_number": f"{order['order_no']}-{suffix}-V{version}",
        "version": version,
        "date": utc_now()[:10],
        "seller": seller,
        "buyer": {
            "company_name": order["company_name"] or "",
            "address": order["address"] or "",
            "tax_id": order["tax_id"] or "",
        },
        "trade_term": order["trade_term"],
        "origin_port": order["origin_port"],
        "destination_port": order["destination_port"],
        "currency": _first_currency(lines),
        "lines": lines,
        "totals": _totals(lines, document_type),
    }


def _document_blockers(conn: sqlite3.Connection, import_order_id: int) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    order = conn.execute("SELECT destination_port FROM import_orders WHERE id = ?", (import_order_id,)).fetchone()
    if order is None:
        raise KeyError(import_order_id)
    if not order["destination_port"]:
        blockers.append({"target": "import_order", "field": "destination_port"})
    for row in conn.execute("SELECT id FROM goods_lines WHERE import_order_id = ?", (import_order_id,)):
        check = check_goods_line_stage(conn, goods_line_id=row["id"], stage=STAGE_FINAL_DOCUMENTS)
        blockers.extend({"target": "goods_line", "id": row["id"], "field": field} for field in check.blockers)
    return blockers


def _invoice_lines(conn: sqlite3.Connection, import_order_id: int) -> list[dict[str, Any]]:
    lines = []
    for row in conn.execute("SELECT * FROM goods_lines WHERE import_order_id = ? ORDER BY id", (import_order_id,)):
        quantity = row["quantity"] or 0
        unit_price = row["sales_unit_price"] or 0
        lines.append(
            {
                "customs_en_name": row["customs_en_name"],
                "quantity": quantity,
                "unit": row["unit"],
                "sales_unit_price": unit_price,
                "currency": row["sales_currency"],
                "line_amount": quantity * unit_price,
            }
        )
    return lines


def _packing_lines(conn: sqlite3.Connection, import_order_id: int) -> list[dict[str, Any]]:
    lines = []
    for row in conn.execute("SELECT * FROM goods_lines WHERE import_order_id = ? ORDER BY id", (import_order_id,)):
        lines.append(
            {
                "customs_en_name": row["customs_en_name"],
                "carton_count": row["carton_count"] or 0,
                "quantity": row["quantity"] or 0,
                "gross_weight": calculate_gross_weight(row) or 0,
                "cbm": calculate_cbm(row) or 0,
                "shipping_mark": row["shipping_mark"],
            }
        )
    return lines


def _next_version(conn: sqlite3.Connection, import_order_id: int, document_type: str) -> int:
    row = conn.execute(
        """
        SELECT max(version) AS version
        FROM documents
        WHERE import_order_id = ? AND document_type = ?
        """,
        (import_order_id, document_type),
    ).fetchone()
    return int(row["version"] or 0) + 1


def _write_document_xlsx(path: Path, data: dict[str, Any]) -> None:
    if data["document_type"] == DOC_COMMERCIAL_INVOICE:
        headers = ["customs_en_name", "quantity", "unit", "sales_unit_price", "currency", "line_amount"]
    else:
        headers = ["customs_en_name", "carton_count", "quantity", "gross_weight", "cbm", "shipping_mark"]
    rows = [
        {"customs_en_name": data["document_number"]},
        {"customs_en_name": f"Seller: {data['seller'].get('company_name', '')}"},
        {"customs_en_name": f"Buyer: {data['buyer'].get('company_name', '')}"},
    ] + data["lines"] + [{"customs_en_name": "TOTAL", **data["totals"]}]
    export_rows_xlsx(path, headers, rows)


def _write_document_pdf(path: Path, data: dict[str, Any]) -> None:
    lines = [
        data["document_number"],
        f"Seller: {data['seller'].get('company_name', '')}",
        f"Buyer: {data['buyer'].get('company_name', '')}",
        f"Origin: {data['origin_port']}  Destination: {data['destination_port']}",
        "",
    ]
    for line in data["lines"]:
        lines.append(" | ".join(f"{key}: {value}" for key, value in line.items()))
    lines.append("")
    lines.append("Totals: " + ", ".join(f"{key}: {value}" for key, value in data["totals"].items()))
    _write_simple_pdf(path, lines)


def _totals(lines: list[dict[str, Any]], document_type: str) -> dict[str, Any]:
    if document_type == DOC_COMMERCIAL_INVOICE:
        return {"line_amount": sum(line["line_amount"] for line in lines)}
    return {
        "carton_count": sum(line["carton_count"] for line in lines),
        "quantity": sum(line["quantity"] for line in lines),
        "gross_weight": sum(line["gross_weight"] for line in lines),
        "cbm": sum(line["cbm"] for line in lines),
    }


def _first_currency(lines: list[dict[str, Any]]) -> str:
    for line in lines:
        if line.get("currency"):
            return line["currency"]
    return ""


def _write_simple_pdf(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ["BT", "/F1 10 Tf", "50 780 Td"]
    for index, line in enumerate(lines):
        if index:
            text.append("0 -16 Td")
        text.append(f"({_pdf_escape(line)}) Tj")
    text.append("ET")
    stream = "\n".join(text).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    content = [b"%PDF-1.4\n"]
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in content))
        content.append(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = sum(len(part) for part in content)
    content.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    content.extend(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    content.append(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    path.write_bytes(b"".join(content))


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

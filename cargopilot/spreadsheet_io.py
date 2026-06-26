from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from .master_data import create_supplier
from .orders import create_goods_line, update_goods_line

CUSTOMER_PURCHASE_HEADERS = [
    "order_no",
    "supplier_name",
    "customer_item_no",
    "product_url",
    "cn_name",
    "en_name",
    "customs_en_name",
    "sku_or_model",
    "category",
    "hs_code",
    "quantity",
    "unit",
    "target_markup",
    "sales_unit_price",
    "sales_currency",
    "notes",
]

SUPPLIER_PACKAGE_HEADERS = [
    "order_no",
    "supplier_name",
    "sku_or_model",
    "customs_en_name",
    "carton_count",
    "units_per_carton",
    "carton_length_cm",
    "carton_width_cm",
    "carton_height_cm",
    "carton_gross_weight_kg",
    "domestic_tracking_no",
    "shipping_mark",
    "purchase_unit_price",
    "purchase_currency",
    "supplier_invoice_no",
    "notes",
]

ORDER_GOODS_UPLOAD_HEADERS = ["产品名称", "数量（非包裹数）", "实际付款", "链接", "厂家名称"]


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        self.errors = self.errors or []


def import_customer_purchase_list(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    path: str | Path,
) -> ImportResult:
    rows = _read_table(path)
    header_errors = _header_errors(rows, CUSTOMER_PURCHASE_HEADERS)
    if header_errors:
        return ImportResult(errors=header_errors)

    result = ImportResult()
    for row_number, row in enumerate(_dict_rows(rows), start=2):
        order = _order_by_no(conn, row["order_no"])
        if order is None:
            result.errors.append(f"Row {row_number}: unknown order_no {row['order_no']}")
            continue
        supplier_id = _supplier_id(conn, row["supplier_name"])
        if supplier_id is None and row["supplier_name"]:
            supplier_id, _ = create_supplier(conn, actor_role=actor_role, name=row["supplier_name"])
        create_goods_line(
            conn,
            actor_role=actor_role,
            import_order_id=order["id"],
            supplier_id=supplier_id,
            customer_item_no=row["customer_item_no"],
            product_url=row["product_url"],
            cn_name=row["cn_name"],
            en_name=row["en_name"],
            customs_en_name=row["customs_en_name"],
            sku_or_model=row["sku_or_model"],
            category=row["category"],
            hs_code=row["hs_code"],
            quantity=_number(row["quantity"]),
            unit=row["unit"],
            target_markup=_number(row["target_markup"]),
            sales_unit_price=_number(row["sales_unit_price"]),
            sales_currency=row["sales_currency"],
            notes=row["notes"],
        )
        result.created += 1
    return result


def import_supplier_package_logistics(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    path: str | Path,
) -> ImportResult:
    rows = _read_table(path)
    header_errors = _header_errors(rows, SUPPLIER_PACKAGE_HEADERS)
    if header_errors:
        return ImportResult(errors=header_errors)

    result = ImportResult()
    for row_number, row in enumerate(_dict_rows(rows), start=2):
        order = _order_by_no(conn, row["order_no"])
        supplier_id = _supplier_id(conn, row["supplier_name"])
        if order is None or supplier_id is None:
            result.errors.append(f"Row {row_number}: unknown order or supplier")
            continue
        goods_line = conn.execute(
            """
            SELECT * FROM goods_lines
            WHERE import_order_id = ?
              AND supplier_id = ?
              AND sku_or_model = ?
              AND customs_en_name = ?
            ORDER BY id
            LIMIT 1
            """,
            (order["id"], supplier_id, row["sku_or_model"], row["customs_en_name"]),
        ).fetchone()
        if goods_line is None:
            result.errors.append(f"Row {row_number}: no matching Goods Line")
            continue
        updates = {
            "carton_count": _number(row["carton_count"], int),
            "units_per_carton": _number(row["units_per_carton"]),
            "carton_length_cm": _number(row["carton_length_cm"]),
            "carton_width_cm": _number(row["carton_width_cm"]),
            "carton_height_cm": _number(row["carton_height_cm"]),
            "carton_gross_weight_kg": _number(row["carton_gross_weight_kg"]),
            "shipping_mark": row["shipping_mark"],
            "purchase_unit_price": _number(row["purchase_unit_price"]),
            "purchase_currency": row["purchase_currency"],
            "notes": row["notes"],
        }
        update_goods_line(
            conn,
            actor_role=actor_role,
            goods_line_id=goods_line["id"],
            **{key: value for key, value in updates.items() if value not in ("", None)},
        )
        if row["domestic_tracking_no"]:
            conn.execute(
                """
                INSERT INTO domestic_tracking_numbers (goods_line_id, tracking_no, notes, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (goods_line["id"], row["domestic_tracking_no"], row["supplier_invoice_no"]),
            )
            conn.commit()
        result.updated += 1
    return result


def import_order_goods_upload(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    import_order_id: int,
    path: str | Path,
) -> ImportResult:
    rows = _read_table(path)
    header_errors = _header_errors(rows, ORDER_GOODS_UPLOAD_HEADERS)
    if header_errors:
        return ImportResult(errors=header_errors)

    result = ImportResult()
    for row_number, row in enumerate(_dict_rows(rows), start=2):
        name = row["产品名称"]
        quantity = _number_or_error(row["数量（非包裹数）"])
        if not name:
            result.errors.append(f"Row {row_number}: 产品名称不能为空")
            continue
        if quantity is None or quantity <= 0:
            result.errors.append(f"Row {row_number}: 数量无效")
            continue
        supplier_id = _supplier_id(conn, row["厂家名称"])
        if supplier_id is None and row["厂家名称"]:
            supplier_id, _ = create_supplier(conn, actor_role=actor_role, name=row["厂家名称"])
        paid = _optional_money(row["实际付款"])
        purchase_unit_price = (paid / quantity) if paid is not None else None
        create_goods_line(
            conn,
            actor_role=actor_role,
            import_order_id=import_order_id,
            supplier_id=supplier_id,
            product_url=row["链接"],
            cn_name=name,
            quantity=quantity,
            unit="pcs",
            purchase_unit_price=purchase_unit_price,
            purchase_currency="CNY" if purchase_unit_price is not None else "",
        )
        result.created += 1
    return result


def export_import_orders(conn: sqlite3.Connection, path: str | Path) -> None:
    rows = [dict(row) for row in conn.execute("SELECT * FROM import_orders ORDER BY created_at DESC")]
    headers = list(rows[0]) if rows else ["id", "order_no", "order_status"]
    export_rows_xlsx(path, headers, rows)


def export_goods_lines(conn: sqlite3.Connection, path: str | Path) -> None:
    rows = [dict(row) for row in conn.execute("SELECT * FROM goods_lines ORDER BY id")]
    headers = list(rows[0]) if rows else ["id", "import_order_id", "cn_name", "customs_en_name"]
    export_rows_xlsx(path, headers, rows)


def export_rows_xlsx(path: str | Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    values = [headers] + [[row.get(header, "") for header in headers] for row in rows]
    _write_xlsx(path, values)


def read_xlsx_rows(path: str | Path) -> list[list[str]]:
    with ZipFile(path) as xlsx:
        shared_strings = _shared_strings(xlsx)
        sheet = ET.fromstring(xlsx.read("xl/worksheets/sheet1.xml"))
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    parsed_rows: list[list[str]] = []
    for row in sheet.findall(".//a:sheetData/a:row", ns):
        values: list[str] = []
        for cell in row.findall("a:c", ns):
            col = _column_index(cell.attrib.get("r", "A1"))
            while len(values) < col:
                values.append("")
            values.append(_cell_value(cell, shared_strings))
        parsed_rows.append(values)
    return parsed_rows


def _read_table(path: str | Path) -> list[list[str]]:
    return [[str(value).strip() for value in row] for row in read_xlsx_rows(path) if any(row)]


def _header_errors(rows: list[list[str]], expected: list[str]) -> list[str]:
    actual = rows[0] if rows else []
    if actual == expected:
        return []
    return [f"Invalid headers. Expected: {expected}. Got: {actual}."]


def _dict_rows(rows: list[list[str]]) -> list[dict[str, str]]:
    headers = rows[0]
    return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in rows[1:]]


def _order_by_no(conn: sqlite3.Connection, order_no: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM import_orders WHERE order_no = ?", (order_no,)).fetchone()


def _supplier_id(conn: sqlite3.Connection, name: str) -> int | None:
    if not name:
        return None
    row = conn.execute("SELECT id FROM suppliers WHERE lower(name) = ?", (name.lower(),)).fetchone()
    return int(row["id"]) if row else None


def _number(value: str, kind=float):
    if value == "":
        return None
    number = float(value)
    return kind(number)


def _number_or_error(value: str) -> float | None:
    try:
        return _number(value)
    except ValueError:
        return None


def _optional_money(value: str) -> float | None:
    value = value.strip()
    if not value or value == "-":
        return None
    return float(value)


def _shared_strings(xlsx: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in xlsx.namelist():
        return []
    root = ET.fromstring(xlsx.read("xl/sharedStrings.xml"))
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return ["".join(node.itertext()) for node in root.findall("a:si", ns)]


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find("a:is", ns)
        return "" if inline is None else "".join(inline.itertext())
    value = cell.find("a:v", ns)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        return shared_strings[int(value.text)]
    return value.text


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    total = 0
    for ch in letters:
        total = total * 26 + ord(ch.upper()) - ord("A") + 1
    return total - 1


def _write_xlsx(path: str | Path, rows: list[list[Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as xlsx:
        xlsx.writestr("[Content_Types].xml", _CONTENT_TYPES)
        xlsx.writestr("_rels/.rels", _ROOT_RELS)
        xlsx.writestr("xl/workbook.xml", _WORKBOOK)
        xlsx.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        xlsx.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows))


def _sheet_xml(rows: list[list[Any]]) -> str:
    body = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            ref = f"{_column_name(col_index)}{row_index}"
            cells.append(_cell_xml(ref, value))
        body.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(body)}</sheetData>"
        "</worksheet>"
    )


def _cell_xml(ref: str, value: Any) -> str:
    if value is None:
        value = ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t>{_escape(str(value))}</t></is></c>'


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_WORKBOOK = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""

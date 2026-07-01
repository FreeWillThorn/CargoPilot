from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from typing import Any
from urllib import error, request

from .calculations import STAGE_FINAL_DOCUMENTS, check_goods_line_stage
from .containers import create_container
from .documents import DOC_COMMERCIAL_INVOICE, DOC_PACKING_LIST, build_document_data
from .finance import LINE_CHARGE, LINE_COST
from .foundation import ROLE_ADMIN, get_setting, utc_now
from .master_data import require_admin
from .orders import IMPORT_ORDER_FIELDS, create_goods_line, update_goods_line, update_import_order
from .spreadsheet_io import read_xlsx_rows

RUN_QUEUED = "queued"
RUN_RUNNING = "running"
RUN_SUCCEEDED = "succeeded"
RUN_FAILED = "failed"
RUN_STATUS_LABELS = {
    RUN_QUEUED: "排队中",
    RUN_RUNNING: "运行中",
    RUN_SUCCEEDED: "已完成",
    RUN_FAILED: "失败",
}

LEVEL_SUGGESTION = "suggestion"
LEVEL_REVIEW_NEEDED = "review-needed"
LEVEL_BLOCKING_RISK = "blocking-risk"
SUGGESTION_LEVEL_LABELS = {
    LEVEL_SUGGESTION: "建议",
    LEVEL_REVIEW_NEEDED: "需核查",
    LEVEL_BLOCKING_RISK: "阻塞风险",
}

REVIEW_PENDING = "pending_review"
REVIEW_APPROVED_FOR_DRAFT = "approved_for_draft"
REVIEW_IGNORED = "ignored"
REVIEW_NEEDS_FOLLOWUP = "needs_followup"
REVIEW_STATUS_LABELS = {
    REVIEW_PENDING: "待核查",
    REVIEW_APPROVED_FOR_DRAFT: "已批准生成草稿",
    REVIEW_IGNORED: "已忽略",
}

DRAFT_DRAFT = "draft"
DRAFT_CONFIRMED = "confirmed"
DRAFT_REJECTED = "rejected"
DRAFT_FAILED = "failed"
CHANGE_DRAFT_STATUS_LABELS = {
    DRAFT_DRAFT: "待确认草稿",
    DRAFT_CONFIRMED: "已确认",
    DRAFT_REJECTED: "已拒绝",
    DRAFT_FAILED: "应用失败",
}

AGENT_STRUCTURED_INTAKE = "structured_intake"
AGENT_ORDER_REVIEW = "order_review"
AGENT_GOODS_REVIEW = "goods_review"
AGENT_COMPLIANCE_RISK = "compliance_risk"
AGENT_DOCUMENT_DRAFT = "document_draft"
AGENT_PROFIT_RISK = "profit_risk"
AGENT_AUTHORITATIVE_DOCUMENT = "authoritative_document"
AGENT_COMMAND_INTENT = "command_intent"
AGENT_COORDINATOR = "coordinator"

TASK_CHECK_ORDER = "AI检查订单"
TASK_CHECK_GOODS = "AI检查货物资料"
TASK_CHECK_DOC_BLOCKERS = "AI检查单证阻塞项"
TASK_DRAFT_DOCS = "AI生成单证草稿"
TASK_CHECK_PROFIT = "AI检查利润风险"
TASK_FILE_TEXT_INTAKE = "file_text_intake"

WORKING_SOURCE_TYPES = {"excel", "supplier_excel", "supplier_email", "chat", "pdf", "warehouse_notes"}
AUTHORITATIVE_SOURCE_TYPES = {"waybill", "customs_declaration", "verified_customs_copy"}
COMMAND_SOURCE_TYPES = {"order_command"}
TEXT_SOURCE_TYPES = WORKING_SOURCE_TYPES | AUTHORITATIVE_SOURCE_TYPES | COMMAND_SOURCE_TYPES
GOODS_LOGISTICS_STATUS_LABELS = {
    "not_ordered": "未下单",
    "ordered": "已下单/备货中",
    "domestic_shipped": "国内运输中",
    "received_at_warehouse": "已到收货仓",
    "moved_to_port_warehouse": "已入港仓",
    "loaded": "已装箱",
    "at_sea": "海运中",
    "exception": "异常",
}
GOODS_STATUS_ALIASES = {
    "received_at_warehouse": ("已到货", "已到仓", "已到收货仓", "到货状态", "到仓"),
    "domestic_shipped": ("国内运输中", "运输中", "已发货", "已揽收"),
    "ordered": ("已下单", "备货中"),
    "moved_to_port_warehouse": ("已入港仓", "港仓"),
    "loaded": ("已装箱", "已装柜"),
    "at_sea": ("海运中", "已开船"),
    "exception": ("异常",),
    "not_ordered": ("未下单",),
}
GOODS_COMMAND_TARGET_WORDS = ("全部", "所有")
GOODS_COMMAND_ACTION_WORDS = ("改成", "改为", "设置成", "设置为", "标记为")
GOODS_DELETE_WORDS = ("删除", "删掉", "移除", "清空")
ORDER_STATUS_ALIASES = {
    "draft": ("草稿",),
    "purchasing": ("采购中",),
    "receiving": ("收货中",),
    "received": ("已到仓", "已收货"),
    "moving_to_port": ("转运港仓",),
    "at_port_warehouse": ("已入港仓",),
    "loaded": ("已装箱", "已装柜"),
    "at_sea": ("海运中",),
    "arrived": ("已到港",),
    "completed": ("已完成",),
    "cancelled": ("已取消", "取消"),
}
ORDER_FIELD_ALIASES = {
    "订单号": "order_no",
    "目的港": "destination_port",
    "贸易条款": "trade_term",
    "订单状态": "order_status",
    "预计装柜日": "expected_loading_date",
    "备注": "internal_notes",
}
SAFE_WORKING_FIELDS = {
    "carton_length_cm",
    "carton_width_cm",
    "carton_height_cm",
    "carton_gross_weight_kg",
    "volume_cbm",
    "shipping_mark",
    "domestic_tracking_no",
    "notes",
}
UNSAFE_WORKING_FIELDS = {
    "carton_count",
    "quantity",
    "units_per_carton",
    "hs_code",
    "customs_en_name",
    "purchase_unit_price",
    "purchase_currency",
    "logistics_status_source",
}

ALLOWED_TOOL_TYPES = {
    "selected_order_read",
    "source_extraction",
    "calculation_helpers",
    "document_helpers",
    "deepseek_json",
    "code_constants",
}

COMPLIANCE_KEYWORDS = {
    "wood": ("木", "竹", "wood", "bamboo"),
    "food_contact": ("餐具", "茶具", "杯", "食品接触", "food", "tableware", "cup"),
    "animal_plant": ("动植物", "种子", "皮革", "羽毛", "leather", "seed", "plant", "animal"),
    "children": ("儿童", "玩具", "婴儿", "child", "toy", "baby"),
    "textile": ("纺织", "布", "服装", "textile", "fabric", "clothing"),
}

CHINESE_GOODS_HEADERS = [
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
]


@dataclass(frozen=True)
class Source:
    source_type: str
    path: str | None = None
    text: str = ""
    name: str = ""


def create_assistant_run(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    import_order_id: int,
    task_template: str,
    workflow_section: str = "",
    action_button: str = "",
    actor_user_id: int | None = None,
    prompt_version: str = "order-assistant-mvp-v1",
    sources: list[dict[str, Any]] | None = None,
) -> int:
    require_admin(actor_role)
    _require_order(conn, import_order_id)
    now = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO assistant_runs (
            import_order_id, actor_user_id, task_template, workflow_section,
            action_button, status, prompt_version, source_summary_json,
            allowed_tools_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_order_id,
            actor_user_id,
            task_template,
            workflow_section,
            action_button,
            RUN_QUEUED,
            prompt_version,
            _json(sources or []),
            _json(sorted(ALLOWED_TOOL_TYPES)),
            now,
            now,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def set_run_status(conn: sqlite3.Connection, run_id: int, status: str, *, error: str = "") -> None:
    if status not in {RUN_QUEUED, RUN_RUNNING, RUN_SUCCEEDED, RUN_FAILED}:
        raise ValueError(f"unknown assistant run status: {status}")
    conn.execute(
        "UPDATE assistant_runs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
        (status, error, utc_now(), run_id),
    )
    conn.commit()


def retry_assistant_run(conn: sqlite3.Connection, *, actor_role: str, run_id: int, real_data_confirmed: bool = False) -> int:
    require_admin(actor_role)
    run = _run(conn, run_id)
    if run["status"] != RUN_FAILED:
        raise ValueError("only failed assistant runs can be retried")
    source_dicts = json.loads(run["source_summary_json"])
    sources = [Source(**source) for source in source_dicts]
    return run_assistant(
        conn,
        actor_role=actor_role,
        import_order_id=run["import_order_id"],
        task_template=run["task_template"],
        workflow_section=run["workflow_section"],
        action_button=run["action_button"],
        actor_user_id=run["actor_user_id"],
        prompt_version=run["prompt_version"],
        sources=sources,
        real_data_confirmed=real_data_confirmed,
    )


def route_agents(task_template: str, sources: list[Source] | None = None) -> list[str]:
    agents: list[str] = []
    if task_template == TASK_CHECK_ORDER:
        agents.extend([AGENT_ORDER_REVIEW, AGENT_GOODS_REVIEW, AGENT_COMPLIANCE_RISK])
    elif task_template == TASK_CHECK_GOODS:
        agents.extend([AGENT_GOODS_REVIEW, AGENT_COMPLIANCE_RISK])
    elif task_template == TASK_CHECK_DOC_BLOCKERS:
        agents.extend([AGENT_COMPLIANCE_RISK, AGENT_DOCUMENT_DRAFT])
    elif task_template == TASK_DRAFT_DOCS:
        agents.append(AGENT_DOCUMENT_DRAFT)
    elif task_template == TASK_CHECK_PROFIT:
        agents.append(AGENT_PROFIT_RISK)
    elif task_template == TASK_FILE_TEXT_INTAKE and (not sources or any(source.source_type not in COMMAND_SOURCE_TYPES for source in sources)):
        agents.append(AGENT_STRUCTURED_INTAKE)

    for source in sources or []:
        if source.source_type in COMMAND_SOURCE_TYPES:
            _append_once(agents, AGENT_COMMAND_INTENT)
        if source.source_type in WORKING_SOURCE_TYPES:
            _append_once(agents, AGENT_STRUCTURED_INTAKE)
        if source.source_type in AUTHORITATIVE_SOURCE_TYPES:
            _append_once(agents, AGENT_AUTHORITATIVE_DOCUMENT)
        haystack = f"{source.name} {source.text}".lower()
        if source.source_type in TEXT_SOURCE_TYPES and _has_product_or_certificate_text(haystack):
            _append_once(agents, AGENT_COMPLIANCE_RISK)
        if _has_finance_text(haystack):
            _append_once(agents, AGENT_PROFIT_RISK)
        if _has_document_text(haystack):
            _append_once(agents, AGENT_DOCUMENT_DRAFT)
    return agents


def run_assistant(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    import_order_id: int,
    task_template: str,
    workflow_section: str = "",
    action_button: str = "",
    actor_user_id: int | None = None,
    sources: list[Source] | None = None,
    prompt_version: str = "order-assistant-mvp-v1",
    real_data_confirmed: bool = False,
) -> int:
    require_admin(actor_role)
    source_summary = [source.__dict__ for source in (sources or [])]
    run_id = create_assistant_run(
        conn,
        actor_role=actor_role,
        import_order_id=import_order_id,
        task_template=task_template,
        workflow_section=workflow_section,
        action_button=action_button or task_template,
        actor_user_id=actor_user_id,
        prompt_version=prompt_version,
        sources=source_summary,
    )
    set_run_status(conn, run_id, RUN_RUNNING)
    started = time.monotonic()
    try:
        outputs = []
        for agent_name in route_agents(task_template, sources):
            agent_started = time.monotonic()
            output = _run_agent(conn, agent_name, import_order_id, sources or [], prompt_version, real_data_confirmed)
            outputs.append(output)
            _record_usage_from_response(conn, run_id, agent_name, output["usage"], prompt_version, agent_started)
        coordinator = coordinator_agent(outputs, conn=conn, import_order_id=import_order_id, sources=sources or [])
        validate_agent_response(coordinator)
        _persist_agent_response(conn, run_id, import_order_id, AGENT_COORDINATOR, coordinator)
        _record_usage_from_response(conn, run_id, AGENT_COORDINATOR, coordinator["usage"], prompt_version, started)
        set_run_status(conn, run_id, RUN_SUCCEEDED)
    except Exception as exc:
        set_run_status(conn, run_id, RUN_FAILED, error=str(exc))
    return run_id


def validate_agent_response(response: dict[str, Any]) -> None:
    required = {"suggestions", "drafts", "reviewNeededFields", "usage"}
    if set(response) != required:
        raise ValueError(f"invalid agent response keys: {sorted(response)}")
    if not all(isinstance(response[key], list) for key in ["suggestions", "drafts", "reviewNeededFields"]):
        raise ValueError("agent response lists are required")
    if not isinstance(response["usage"], dict):
        raise ValueError("usage must be an object")
    for key in ["suggestions", "drafts", "reviewNeededFields"]:
        for index, item in enumerate(response[key]):
            if not isinstance(item, dict):
                raise ValueError(f"agent response {key}[{index}] must be an object")
    for suggestion in response["suggestions"]:
        for field in ["level", "targetType", "suggestionType", "title"]:
            if field not in suggestion:
                raise ValueError(f"suggestion {field} is required")
        if suggestion.get("level") not in SUGGESTION_LEVEL_LABELS:
            raise ValueError("invalid suggestion level")
        if suggestion.get("level") == LEVEL_BLOCKING_RISK and not suggestion.get("sourceReferences"):
            raise ValueError("blocking-risk requires source references")
    for draft in response["drafts"]:
        for field in ["draftType", "targetType", "proposedValues"]:
            if field not in draft:
                raise ValueError(f"draft {field} is required")
        if not isinstance(draft.get("proposedValues", {}), dict):
            raise ValueError("draft proposedValues must be an object")
        if not isinstance(draft.get("originalValues", {}), dict):
            raise ValueError("draft originalValues must be an object")
        if draft.get("targetType") in {"supplier", "consignee", "warehouse", "system_settings"}:
            raise ValueError("master-data drafts are forbidden")
        if draft.get("targetType") in {"order_status", "receiving_record", "loading_record"}:
            raise ValueError("protected target draft is forbidden")
    for field in response["reviewNeededFields"]:
        for required in ["targetType", "fieldName"]:
            if required not in field:
                raise ValueError(f"review field {required} is required")


def structured_intake_agent(sources: list[Source], *, prompt_version: str = "order-assistant-mvp-v1") -> dict[str, Any]:
    drafts: list[dict[str, Any]] = []
    review_needed: list[dict[str, Any]] = []
    for source in sources:
        if source.source_type in AUTHORITATIVE_SOURCE_TYPES:
            continue
        if source.source_type in {"excel", "supplier_excel"} and source.path:
            rows = [[str(value).strip() for value in row] for row in read_xlsx_rows(source.path) if any(row)]
            if not rows or rows[0] != CHINESE_GOODS_HEADERS:
                continue
            for row_number, row in enumerate(_dict_rows(rows), start=2):
                values, quantity_review = _values_from_chinese_excel_row(row)
                source_ref = _source_ref(source, row_number=row_number)
                if values.get("cn_name"):
                    drafts.append(_goods_line_draft(values, source_ref, 0.85))
                if quantity_review:
                    review_needed.append(_review_field("goods_line", None, "quantity", row["数量（非包裹数）"], quantity_review, source_ref))
                for field, header in [
                    ("supplier_name_reference", "厂家名称"),
                    ("carton_length_cm", "外箱尺寸(cm)"),
                    ("carton_gross_weight_kg", "单箱毛重(kg)"),
                    ("volume_cbm", "CBM"),
                    ("gross_weight", "总毛重(kg)"),
                    ("shipping_mark", "麦头"),
                    ("domestic_tracking_no", "国内物流单号"),
                    ("logistics_status_source", "货物物流状态"),
                ]:
                    if not values.get(field):
                        review_needed.append(_review_field("goods_line", None, field, row[header], "缺少或无法安全解析", source_ref))
            continue

        text, parse_error = _source_text(source)
        if parse_error:
            review_needed.append(_review_field("import_order", None, "source_parse_error", source.name, parse_error, _source_ref(source)))
            continue
        for line_number, values in _parse_text_goods_rows(text):
            drafts.append(_goods_line_draft(values, _source_ref(source, row_number=line_number), 0.75))
    return _envelope(drafts=drafts, review_needed=review_needed, prompt_version=prompt_version)


def authoritative_document_agent(conn: sqlite3.Connection, import_order_id: int, sources: list[Source], *, prompt_version: str = "order-assistant-mvp-v1") -> dict[str, Any]:
    drafts: list[dict[str, Any]] = []
    review_needed: list[dict[str, Any]] = []
    for source in sources:
        if source.source_type not in AUTHORITATIVE_SOURCE_TYPES:
            continue
        text, parse_error = _source_text(source)
        source_ref = _source_ref(source)
        if parse_error:
            review_needed.append(_review_field("import_order", import_order_id, "source_parse_error", source.name, parse_error, source_ref))
            continue
        rows = [values for _, values in _parse_text_goods_rows(text)]
        container = _parse_container_data(text)
        if container:
            drafts.append(_container_draft(container, source_ref, 0.86))
        if not rows and not container:
            review_needed.append(_review_field("customs_goods_version", None, "document_rows", source.name, "权威单证没有解析到可导入报关行", source_ref))
            continue
        if rows:
            drafts.append(
                {
                    "draftType": "customs_goods_version",
                    "targetType": "customs_goods_version",
                    "targetId": None,
                    "proposedValues": {
                        "document_type": source.source_type,
                        "source_name": source.name or (Path(source.path).name if source.path else "pasted text"),
                        "rows": rows,
                        "totals": _customs_totals(rows),
                        "document_data": _parse_document_data(text),
                        "discrepancies": _customs_discrepancies(conn, import_order_id, rows),
                    },
                    "originalValues": {},
                    "sourceReferences": [source_ref],
                    "confidence": 0.82,
                }
            )
    return _envelope(drafts=drafts, review_needed=review_needed, prompt_version=prompt_version)


def command_intent_agent(conn: sqlite3.Connection, import_order_id: int, sources: list[Source], *, prompt_version: str = "order-assistant-mvp-v1") -> dict[str, Any]:
    drafts: list[dict[str, Any]] = []
    review_needed: list[dict[str, Any]] = []
    order = _require_order(conn, import_order_id)
    for source in sources:
        if source.source_type not in COMMAND_SOURCE_TYPES:
            continue
        text, parse_error = _source_text(source)
        source_ref = _source_ref(source)
        if parse_error:
            review_needed.append(_review_field("import_order", import_order_id, "command_parse_error", source.name, parse_error, source_ref))
            continue
        mentioned_orders = set(re.findall(r"\bCP-\d{4}-\d{4}\b", text, re.I))
        if mentioned_orders and order["order_no"] not in mentioned_orders:
            review_needed.append(_review_field("import_order", import_order_id, "command_order_mismatch", text[:120], "指令提到的订单号不是当前选中的订单", source_ref))
            continue
        if _parse_order_delete_command(text):
            drafts.append(_import_order_delete_draft(conn, import_order_id, source_ref))
            continue
        if _parse_goods_delete_command(text):
            drafts.append(_goods_delete_batch_draft(conn, import_order_id, source_ref))
            continue
        if status := _parse_goods_status_command(text):
            drafts.append(_goods_status_batch_draft(conn, import_order_id, status, source_ref))
        else:
            review_needed.append(_review_field("import_order", import_order_id, "unsupported_command", text[:120], "MVP 只支持批量修改货物物流状态或删除当前订单全部货物项", source_ref))
    return _envelope(drafts=drafts, review_needed=review_needed, prompt_version=prompt_version)


def order_review_agent(conn: sqlite3.Connection, import_order_id: int, *, prompt_version: str = "order-assistant-mvp-v1") -> dict[str, Any]:
    order = _require_order(conn, import_order_id)
    suggestions = []
    for field, label in [
        ("consignee_id", "收货客户"),
        ("destination_port", "目的港"),
        ("trade_term", "贸易条款"),
        ("expected_loading_date", "预计装柜日"),
    ]:
        if order[field] in (None, ""):
            suggestions.append(_suggestion(AGENT_ORDER_REVIEW, LEVEL_REVIEW_NEEDED, "import_order", import_order_id, "missing_order_field", f"订单缺少{label}", f"{label}缺失会影响订单推进。"))
    return _envelope(suggestions=suggestions, prompt_version=prompt_version)


def goods_review_agent(conn: sqlite3.Connection, import_order_id: int, *, prompt_version: str = "order-assistant-mvp-v1") -> dict[str, Any]:
    suggestions = []
    review_needed = []
    for row in _goods_lines(conn, import_order_id):
        for field, label in [
            ("customs_en_name", "报关英文品名"),
            ("hs_code", "HS Code"),
            ("carton_count", "箱数"),
            ("carton_gross_weight_kg", "单箱毛重"),
            ("shipping_mark", "麦头"),
        ]:
            if row[field] in (None, ""):
                suggestions.append(_suggestion(AGENT_GOODS_REVIEW, LEVEL_REVIEW_NEEDED, "goods_line", row["id"], "missing_goods_field", f"货物项缺少{label}", f"{label}缺失会影响收货、装柜或单证。"))
        if not _has_tracking(conn, row["id"]):
            suggestions.append(_suggestion(AGENT_GOODS_REVIEW, LEVEL_REVIEW_NEEDED, "goods_line", row["id"], "missing_tracking", "货物项缺少国内物流单号", "国内物流单号缺失会影响到货跟踪。"))
        for check_field, label in [("gross_weight", "总毛重"), ("volume_cbm", "CBM")]:
            if row[check_field] is None:
                review_needed.append(_review_field("goods_line", row["id"], check_field, "", f"{label}需要核查或计算", _system_ref(row["id"], check_field)))
    return _envelope(suggestions=suggestions, review_needed=review_needed, prompt_version=prompt_version)


def compliance_risk_agent(conn: sqlite3.Connection, import_order_id: int, sources: list[Source] | None = None, *, prompt_version: str = "order-assistant-mvp-v1") -> dict[str, Any]:
    suggestions = []
    for row in _goods_lines(conn, import_order_id):
        text = " ".join(str(row[field] or "") for field in ["cn_name", "en_name", "customs_en_name", "category", "notes"])
        for risk_type, keywords in COMPLIANCE_KEYWORDS.items():
            if any(keyword.lower() in text.lower() for keyword in keywords):
                suggestions.append(_suggestion(AGENT_COMPLIANCE_RISK, LEVEL_REVIEW_NEEDED, "goods_line", row["id"], f"compliance_{risk_type}", "可能需要额外合规文件", f"产品名称或类别命中 {risk_type} 风险提示，请管理员核查是否需要合规文件。"))
    for source in sources or []:
        if source.text and _has_product_or_certificate_text(source.text.lower()):
            suggestions.append(_suggestion(AGENT_COMPLIANCE_RISK, LEVEL_SUGGESTION, "import_order", import_order_id, "source_compliance_hint", "上传/粘贴资料包含合规线索", "来源资料中出现产品或证书相关内容，请核查是否需要合规文件。", [_source_ref(source)]))
    return _envelope(suggestions=suggestions, prompt_version=prompt_version)


def document_draft_agent(conn: sqlite3.Connection, import_order_id: int, *, prompt_version: str = "order-assistant-mvp-v1") -> dict[str, Any]:
    suggestions = []
    drafts = []
    for row in conn.execute("SELECT id FROM goods_lines WHERE import_order_id = ?", (import_order_id,)):
        check = check_goods_line_stage(conn, goods_line_id=row["id"], stage=STAGE_FINAL_DOCUMENTS)
        for field in check.blockers:
            suggestions.append(_suggestion(AGENT_DOCUMENT_DRAFT, LEVEL_REVIEW_NEEDED, "goods_line", row["id"], "document_blocker", f"单证缺少 {field}", "正式商业发票或装箱单生成前需要补齐该字段。"))
    order = _require_order(conn, import_order_id)
    if not order["destination_port"]:
        suggestions.append(_suggestion(AGENT_DOCUMENT_DRAFT, LEVEL_REVIEW_NEEDED, "import_order", import_order_id, "document_blocker", "单证缺少目的港", "正式单证需要目的港。"))
    if not suggestions:
        for document_type in [DOC_COMMERCIAL_INVOICE, DOC_PACKING_LIST]:
            data = build_document_data(conn, import_order_id=import_order_id, document_type=document_type, version=1)
            drafts.append(
                {
                    "draftType": "export_document",
                    "targetType": "document",
                    "targetId": None,
                    "proposedValues": {"document_type": document_type, "document_number": data["document_number"], "lines": data["lines"], "totals": data["totals"]},
                    "originalValues": {},
                    "sourceReferences": [_system_ref(import_order_id, "document_data")],
                    "confidence": 0.9,
                }
            )
    return _envelope(suggestions=suggestions, drafts=drafts, prompt_version=prompt_version)


def profit_risk_agent(conn: sqlite3.Connection, import_order_id: int, *, prompt_version: str = "order-assistant-mvp-v1") -> dict[str, Any]:
    suggestions = []
    rows = conn.execute("SELECT * FROM finance_lines WHERE import_order_id = ?", (import_order_id,)).fetchall()
    costs = [row for row in rows if row["line_kind"] == LINE_COST]
    charges = [row for row in rows if row["line_kind"] == LINE_CHARGE]
    if costs and not charges:
        suggestions.append(_suggestion(AGENT_PROFIT_RISK, LEVEL_BLOCKING_RISK, "import_order", import_order_id, "costs_without_charges", "已有成本但没有客户收费", "该订单可能无法正确评估利润。", [_system_ref(import_order_id, "finance_lines")]))
    cost_types = {row["line_type"] for row in costs}
    for line_type, label in [("sea_freight", "海运费"), ("warehouse", "仓库费"), ("document_customs", "单证/报关费")]:
        if line_type not in cost_types:
            suggestions.append(_suggestion(AGENT_PROFIT_RISK, LEVEL_REVIEW_NEEDED, "import_order", import_order_id, "missing_common_fee", f"可能缺少{label}", "MVP 固定利润检查要求核查常见费用是否完整。"))
    total_cost = sum(row["amount"] * row["exchange_rate_to_base"] for row in costs)
    total_charge = sum(row["amount"] * row["exchange_rate_to_base"] for row in charges)
    if total_charge and total_cost and (total_charge - total_cost) / total_charge < 0.1:
        suggestions.append(_suggestion(AGENT_PROFIT_RISK, LEVEL_REVIEW_NEEDED, "import_order", import_order_id, "low_margin", "利润率低于目标", "当前估算毛利率低于 MVP 固定阈值 10%。"))
    if any(row["exchange_rate_to_base"] in (None, 0) for row in rows):
        suggestions.append(_suggestion(AGENT_PROFIT_RISK, LEVEL_REVIEW_NEEDED, "import_order", import_order_id, "missing_exchange_rate", "缺少汇率", "缺少汇率会导致利润估算不准确。"))
    return _envelope(suggestions=suggestions, prompt_version=prompt_version)


def coordinator_agent(
    agent_outputs: list[dict[str, Any]],
    *,
    prompt_version: str = "order-assistant-mvp-v1",
    conn: sqlite3.Connection | None = None,
    import_order_id: int | None = None,
    sources: list[Source] | None = None,
) -> dict[str, Any]:
    suggestions: list[dict[str, Any]] = []
    drafts: list[dict[str, Any]] = []
    review_needed: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for output in agent_outputs:
        validate_agent_response(output)
        drafts.extend(output["drafts"])
        review_needed.extend(output["reviewNeededFields"])
        for suggestion in output["suggestions"]:
            if suggestion["level"] == LEVEL_BLOCKING_RISK and not suggestion.get("sourceReferences"):
                suggestion = {**suggestion, "level": LEVEL_REVIEW_NEEDED}
            key = (suggestion.get("targetType"), suggestion.get("targetId"), suggestion.get("suggestionType"), suggestion.get("title"))
            if key in seen:
                continue
            seen.add(key)
            suggestions.append(suggestion)
    if conn is not None and import_order_id is not None:
        drafts = _match_goods_drafts(conn, import_order_id, drafts, suggestions, review_needed)
    if not suggestions and not drafts and sources:
        if review_needed:
            reasons = []
            for field in review_needed:
                reason = str(field.get("reason") or field.get("sourceValue") or "").strip()
                if reason and reason not in reasons:
                    reasons.append(reason)
            suggestions.append(_no_recognized_data_suggestion(import_order_id, sources, reason="；".join(reasons[:2]) or "本次资料需要人工补充后才能识别。"))
        else:
            suggestions.append(_no_recognized_data_suggestion(import_order_id, sources))
    return _envelope(suggestions=suggestions, drafts=drafts, review_needed=review_needed, prompt_version=prompt_version)


def update_review_request_status(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    review_request_id: int,
    status: str,
    admin_note: str = "",
) -> int | None:
    require_admin(actor_role)
    if status not in {REVIEW_PENDING, REVIEW_APPROVED_FOR_DRAFT, REVIEW_IGNORED}:
        raise ValueError(f"unknown review status: {status}")
    draft_id: int | None = None
    if status == REVIEW_APPROVED_FOR_DRAFT:
        draft_id = _create_change_draft_from_review(conn, review_request_id)
    conn.execute(
        "UPDATE review_requests SET status = ?, admin_note = ?, updated_at = ? WHERE id = ?",
        (status, admin_note, utc_now(), review_request_id),
    )
    conn.commit()
    return draft_id


def update_review_request_group_status(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    import_order_id: int,
    draft_type: str,
    status: str,
) -> list[int]:
    require_admin(actor_role)
    rows = conn.execute(
        """
        SELECT id FROM review_requests
        WHERE import_order_id = ? AND draft_type = ? AND status = ? AND archived_at IS NULL
        ORDER BY id
        """,
        (import_order_id, draft_type, REVIEW_PENDING),
    ).fetchall()
    return [
        draft_id
        for row in rows
        if (draft_id := update_review_request_status(conn, actor_role=actor_role, review_request_id=int(row["id"]), status=status)) is not None
    ]


def confirm_change_draft(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    change_draft_id: int,
    final_values: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
) -> int | None:
    require_admin(actor_role)
    draft = _draft(conn, change_draft_id)
    values = {**json.loads(draft["proposed_values_json"]), **(final_values or {})}
    try:
        target_id: int | None = None
        if draft["draft_type"] == "goods_line" and draft["target_id"] is None:
            target_id = create_goods_line(
                conn,
                actor_role=actor_role,
                import_order_id=draft["import_order_id"],
                **_goods_line_values(values),
            )
        elif draft["target_type"] == "goods_line" and draft["target_id"] is not None:
            target_id = int(draft["target_id"])
            update_goods_line(conn, actor_role=actor_role, goods_line_id=target_id, **_goods_line_values(values))
        elif draft["draft_type"] in {"export_document", "finance"}:
            target_id = draft["target_id"]
        elif draft["draft_type"] == "safe_field_batch":
            _apply_safe_field_batch(conn, actor_role, draft["import_order_id"], values)
        elif draft["draft_type"] == "goods_status_batch":
            _apply_goods_status_batch(conn, actor_role, draft["import_order_id"], values)
        elif draft["draft_type"] == "goods_delete_batch":
            _apply_goods_delete_batch(conn, draft["import_order_id"], values)
        elif draft["draft_type"] == "import_order_update":
            update_import_order(conn, actor_role=actor_role, import_order_id=draft["import_order_id"], **_import_order_update_values(values))
        elif draft["draft_type"] == "import_order_delete":
            _apply_import_order_delete(conn, draft["import_order_id"])
        elif draft["draft_type"] == "customs_goods_version":
            target_id = _store_customs_goods_version(conn, draft, values, actor_user_id)
        elif draft["draft_type"] == "container":
            target_id = _apply_container_draft(conn, actor_role, draft["import_order_id"], values)
        else:
            raise ValueError(f"unsupported draft type: {draft['draft_type']}")
        conn.execute(
            """
            UPDATE change_drafts
            SET status = ?, target_id = COALESCE(?, target_id), admin_final_values_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (DRAFT_CONFIRMED, target_id, _json(values), utc_now(), change_draft_id),
        )
        conn.commit()
        return target_id
    except Exception as exc:
        conn.execute(
            "UPDATE change_drafts SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (DRAFT_FAILED, str(exc), utc_now(), change_draft_id),
        )
        conn.commit()
        raise


def reject_change_draft(conn: sqlite3.Connection, *, actor_role: str, change_draft_id: int) -> None:
    require_admin(actor_role)
    conn.execute("UPDATE change_drafts SET status = ?, updated_at = ? WHERE id = ?", (DRAFT_REJECTED, utc_now(), change_draft_id))
    conn.commit()


def update_change_draft_group_status(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    import_order_id: int,
    draft_type: str,
    action: str,
) -> list[int | None]:
    require_admin(actor_role)
    rows = conn.execute(
        """
        SELECT id FROM change_drafts
        WHERE import_order_id = ? AND draft_type = ? AND status = ? AND archived_at IS NULL
        ORDER BY id
        """,
        (import_order_id, draft_type, DRAFT_DRAFT),
    ).fetchall()
    if action == "confirm":
        return [confirm_change_draft(conn, actor_role=actor_role, change_draft_id=int(row["id"])) for row in rows]
    if action == "reject":
        for row in rows:
            reject_change_draft(conn, actor_role=actor_role, change_draft_id=int(row["id"]))
        return [None for _ in rows]
    raise ValueError(f"unknown draft group action: {action}")


def list_order_assistant_items(conn: sqlite3.Connection, import_order_id: int) -> dict[str, list[dict[str, Any]]]:
    suggestions = [dict(row) for row in conn.execute("SELECT * FROM assistant_suggestions WHERE import_order_id = ? ORDER BY id DESC", (import_order_id,))]
    reviews = [dict(row) for row in conn.execute("SELECT * FROM review_requests WHERE import_order_id = ? AND archived_at IS NULL ORDER BY id DESC", (import_order_id,))]
    drafts = [dict(row) for row in conn.execute("SELECT * FROM change_drafts WHERE import_order_id = ? AND archived_at IS NULL ORDER BY id DESC", (import_order_id,))]
    runs = [dict(row) for row in conn.execute("SELECT * FROM assistant_runs WHERE import_order_id = ? AND archived_at IS NULL ORDER BY id DESC", (import_order_id,))]
    customs_versions = [dict(row) for row in conn.execute("SELECT * FROM customs_goods_versions WHERE import_order_id = ? ORDER BY id DESC", (import_order_id,))]
    archived_runs = [dict(row) for row in conn.execute("SELECT * FROM assistant_runs WHERE import_order_id = ? AND archived_at IS NOT NULL ORDER BY archived_at DESC, id DESC", (import_order_id,))]
    archived_reviews = [dict(row) for row in conn.execute("SELECT * FROM review_requests WHERE import_order_id = ? AND archived_at IS NOT NULL ORDER BY archived_at DESC, id DESC", (import_order_id,))]
    archived_drafts = [dict(row) for row in conn.execute("SELECT * FROM change_drafts WHERE import_order_id = ? AND archived_at IS NOT NULL ORDER BY archived_at DESC, id DESC", (import_order_id,))]
    for review in reviews:
        review["status_label"] = REVIEW_STATUS_LABELS.get(review["status"], "历史跟进")
    for review in archived_reviews:
        review["status_label"] = REVIEW_STATUS_LABELS.get(review["status"], "历史跟进")
    return {
        "runs": runs,
        "suggestions": suggestions,
        "review_requests": reviews,
        "change_drafts": drafts,
        "customs_goods_versions": customs_versions,
        "archived_runs": archived_runs,
        "archived_review_requests": archived_reviews,
        "archived_change_drafts": archived_drafts,
    }


def archive_assistant_items(conn: sqlite3.Connection, *, actor_role: str, import_order_id: int, kind: str) -> None:
    require_admin(actor_role)
    now = utc_now()
    tables = {
        "runs": "assistant_runs",
        "reviews": "review_requests",
        "drafts": "change_drafts",
    }
    table = tables.get(kind)
    if table is None:
        raise ValueError(f"unknown archive kind: {kind}")
    conn.execute(f"UPDATE {table} SET archived_at = ? WHERE import_order_id = ? AND archived_at IS NULL", (now, import_order_id))
    conn.commit()


def list_current_customs_goods_version(conn: sqlite3.Connection, import_order_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM customs_goods_versions
        WHERE import_order_id = ? AND is_current = 1
        ORDER BY id DESC
        LIMIT 1
        """,
        (import_order_id,),
    ).fetchone()
    return dict(row) if row else None


def build_intake_result_summary(conn: sqlite3.Connection, import_order_id: int, assistant_run_id: int | None = None) -> dict[str, Any]:
    run = _run(conn, assistant_run_id) if assistant_run_id else conn.execute(
        "SELECT * FROM assistant_runs WHERE import_order_id = ? ORDER BY id DESC LIMIT 1",
        (import_order_id,),
    ).fetchone()
    if run is None:
        return {"识别结果": [], "提取到的货物": [], "系统匹配": [], "发现问题": [], "建议操作": []}
    suggestions = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM assistant_suggestions WHERE assistant_run_id = ? ORDER BY id",
            (run["id"],),
        )
    ]
    drafts = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM change_drafts WHERE assistant_run_id = ? ORDER BY id",
            (run["id"],),
        )
    ]
    reviews = [
        dict(row)
        for row in conn.execute(
            """
            SELECT review_requests.*, assistant_suggestions.title, assistant_suggestions.reason
            FROM review_requests
            JOIN assistant_suggestions ON assistant_suggestions.id = review_requests.assistant_suggestion_id
            WHERE assistant_suggestions.assistant_run_id = ?
            ORDER BY review_requests.id
            """,
            (run["id"],),
        )
    ]
    return {
        "识别结果": [_source_summary_label(item) for item in json.loads(run["source_summary_json"])],
        "提取到的货物": [_draft_candidate_title({"draftType": row["draft_type"], "proposedValues": json.loads(row["draft_candidate_json"] or "{}")}) for row in reviews if row["draft_candidate_json"] and row["draft_candidate_json"] != "{}"],
        "系统匹配": [row["title"] for row in suggestions if row["suggestion_type"] in {"source_row_matched", "missing_existing_line"}],
        "发现问题": [row["title"] for row in suggestions if row["suggestion_type"] not in {"source_row_matched", "missing_existing_line", "draft_candidate"}],
        "建议操作": [_draft_operation_name(row) for row in drafts],
    }


def _source_summary_label(item: Any) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return str(item)
    return f"{item.get('source_type') or item.get('sourceType')}: {item.get('name') or item.get('path') or 'pasted text'}"


def _run_agent(conn: sqlite3.Connection, agent_name: str, import_order_id: int, sources: list[Source], prompt_version: str, real_data_confirmed: bool) -> dict[str, Any]:
    deepseek_config = _deepseek_config(conn)
    if agent_name == AGENT_STRUCTURED_INTAKE:
        return structured_intake_agent(sources, prompt_version=prompt_version)
    if agent_name == AGENT_AUTHORITATIVE_DOCUMENT:
        return authoritative_document_agent(conn, import_order_id, sources, prompt_version=prompt_version)
    if agent_name == AGENT_COMMAND_INTENT:
        if deepseek_config["api_key"] and real_data_confirmed:
            return deepseek_command_intent_agent(conn, import_order_id, sources, prompt_version=prompt_version, deepseek_config=deepseek_config)
        return command_intent_agent(conn, import_order_id, sources, prompt_version=prompt_version)
    if deepseek_config["api_key"] and real_data_confirmed:
        return deepseek_agent(conn, agent_name, import_order_id, sources, prompt_version=prompt_version, deepseek_config=deepseek_config)
    if agent_name == AGENT_ORDER_REVIEW:
        return order_review_agent(conn, import_order_id, prompt_version=prompt_version)
    if agent_name == AGENT_GOODS_REVIEW:
        return goods_review_agent(conn, import_order_id, prompt_version=prompt_version)
    if agent_name == AGENT_COMPLIANCE_RISK:
        return compliance_risk_agent(conn, import_order_id, sources, prompt_version=prompt_version)
    if agent_name == AGENT_DOCUMENT_DRAFT:
        return document_draft_agent(conn, import_order_id, prompt_version=prompt_version)
    if agent_name == AGENT_PROFIT_RISK:
        return profit_risk_agent(conn, import_order_id, prompt_version=prompt_version)
    raise ValueError(f"unknown agent: {agent_name}")


def deepseek_agent(
    conn: sqlite3.Connection,
    agent_name: str,
    import_order_id: int,
    sources: list[Source],
    *,
    prompt_version: str = "order-assistant-mvp-v1",
    deepseek_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "agentName": agent_name,
        "promptVersion": prompt_version,
        "selectedImportOrder": _order_context(conn, import_order_id),
        "sources": [_source_context(source) for source in sources],
        "allowedOutput": {
            "suggestions": "array",
            "drafts": "array",
            "reviewNeededFields": "array",
            "usage": "object",
        },
        "forbiddenActions": [
            "Do not change order status.",
            "Do not create receiving records.",
            "Do not create loading records.",
            "Do not create or update master data.",
            "Return JSON only.",
        ],
    }
    response = call_deepseek_json(agent_name, payload, prompt_version=prompt_version, deepseek_config=deepseek_config or _deepseek_config(conn), validate_response=False)
    response = _coerce_agent_response(response, import_order_id=import_order_id, sources=sources, prompt_version=prompt_version)
    validate_agent_response(response)
    return response


def deepseek_command_intent_agent(
    conn: sqlite3.Connection,
    import_order_id: int,
    sources: list[Source],
    *,
    prompt_version: str = "order-assistant-mvp-v1",
    deepseek_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    command_sources = [source for source in sources if source.source_type in COMMAND_SOURCE_TYPES]
    payload = {
        "agentName": AGENT_COMMAND_INTENT,
        "promptVersion": prompt_version,
        "selectedImportOrder": _order_context(conn, import_order_id),
        "sources": [_source_context(source) for source in command_sources],
        "allowedCommands": [
            {
                "action": "update_goods_logistics_status",
                "scope": "all selected-order goods lines only",
                "allowedStatuses": GOODS_LOGISTICS_STATUS_LABELS,
                "outputDraftType": "goods_status_batch",
            },
            {
                "action": "delete_goods_lines",
                "scope": "all selected-order goods lines only",
                "outputDraftType": "goods_delete_batch",
            },
            {
                "action": "update_import_order",
                "scope": "selected Import Order only",
                "allowedFields": sorted(IMPORT_ORDER_FIELDS),
                "outputDraftType": "import_order_update",
            },
            {
                "action": "delete_import_order",
                "scope": "selected Import Order only",
                "outputDraftType": "import_order_delete",
            }
        ],
        "instructions": [
            "Parse the user's natural-language order operation.",
            "Return JSON only.",
            "Prefer the standard CargoPilot agent envelope with suggestions, drafts, reviewNeededFields, and usage.",
            "If the command is supported, return one draft with draftType goods_status_batch, goods_delete_batch, import_order_update, or import_order_delete.",
            "Do not invent goods outside selectedImportOrder. Do not write data directly.",
            "If unsupported or ambiguous, return reviewNeededFields instead of a draft.",
        ],
    }
    response = call_deepseek_json(AGENT_COMMAND_INTENT, payload, prompt_version=prompt_version, deepseek_config=deepseek_config or _deepseek_config(conn), validate_response=False)
    return _hydrate_command_drafts(conn, import_order_id, command_sources, response, prompt_version)


def call_deepseek_json(
    agent_name: str,
    payload: dict[str, Any],
    *,
    prompt_version: str,
    deepseek_config: dict[str, Any] | None = None,
    validate_response: bool = True,
    system_content: str | None = None,
) -> dict[str, Any]:
    config = deepseek_config or {}
    api_key = config.get("api_key") or os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for DeepSeek calls")
    model = config.get("model") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    endpoint = normalize_deepseek_api_base(config.get("api_base") or os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com"))
    body = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": system_content or (
                    "You are one CargoPilot specialist agent. Return only a JSON object with exactly "
                    "suggestions, drafts, reviewNeededFields, and usage. Do not include reasoning text."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
        ],
    }
    req = request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    with request.urlopen(req, timeout=float(config.get("timeout_seconds") or os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "30"))) as response:
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw)
    content = parsed["choices"][0]["message"]["content"]
    output = json.loads(_strip_json_fence(content))
    usage = parsed.get("usage", {})
    if not isinstance(output, dict):
        if validate_response:
            raise ValueError("model output must be a JSON object")
        output = {"suggestions": [], "drafts": [output], "reviewNeededFields": [], "usage": {}}
    output["usage"] = {
        "model": model,
        "promptVersion": prompt_version,
        "inputTokens": int(usage.get("prompt_tokens", output.get("usage", {}).get("inputTokens", 0)) or 0),
        "outputTokens": int(usage.get("completion_tokens", output.get("usage", {}).get("outputTokens", 0)) or 0),
        "runtimeMs": int((time.monotonic() - started) * 1000),
    }
    if validate_response:
        validate_agent_response(output)
    return output


def test_deepseek_connection(deepseek_config: dict[str, Any]) -> dict[str, Any]:
    api_key = deepseek_config.get("api_key", "")
    if not api_key:
        return {"ok": False, "message": "缺少 API Key"}
    model = deepseek_config.get("model") or "deepseek-chat"
    endpoint = normalize_deepseek_api_base(deepseek_config.get("api_base") or "https://api.deepseek.com")
    body = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "Return exactly {\"ok\": true}."},
        ],
    }
    started = time.monotonic()
    req = request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=float(deepseek_config.get("timeout_seconds") or 30)) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw)
        content = parsed["choices"][0]["message"]["content"]
        ok = bool(json.loads(_strip_json_fence(content)).get("ok"))
        return {"ok": ok, "message": "连接验证成功" if ok else "模型返回内容不符合验证格式", "model": model, "runtimeMs": int((time.monotonic() - started) * 1000)}
    except Exception as exc:
        return {"ok": False, "message": deepseek_error_message(exc), "model": model, "runtimeMs": int((time.monotonic() - started) * 1000)}


def normalize_deepseek_api_base(value: str) -> str:
    base = (value or "https://api.deepseek.com").strip().rstrip("/")
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def deepseek_error_message(exc: Exception) -> str:
    message = str(exc)
    if "CERTIFICATE_VERIFY_FAILED" in message or "self-signed certificate" in message:
        return "连接验证失败：本机 Python 无法信任当前 HTTPS 证书链。请安装系统/代理 CA 证书，或设置 SSL_CERT_FILE 指向可信 CA bundle；不要关闭证书校验。"
    if isinstance(exc, error.HTTPError):
        return f"连接验证失败：DeepSeek 返回 HTTP {exc.code}，请检查 API Key、模型和额度。"
    return f"连接验证失败: {exc}"


def _persist_agent_response(conn: sqlite3.Connection, run_id: int, import_order_id: int, agent_name: str, response: dict[str, Any]) -> None:
    now = utc_now()
    for suggestion in response["suggestions"]:
        cursor = conn.execute(
            """
            INSERT INTO assistant_suggestions (
                assistant_run_id, import_order_id, agent_name, level, target_type,
                target_id, suggestion_type, title, reason, source_references_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                import_order_id,
                suggestion.get("agentName", agent_name),
                suggestion["level"],
                suggestion["targetType"],
                suggestion.get("targetId"),
                suggestion["suggestionType"],
                suggestion["title"],
                suggestion.get("reason", ""),
                _json(suggestion.get("sourceReferences", [])),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO review_requests (
                assistant_suggestion_id, import_order_id, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(cursor.lastrowid), import_order_id, REVIEW_PENDING, now, now),
        )
    for draft in response["drafts"]:
        cursor = conn.execute(
            """
            INSERT INTO assistant_suggestions (
                assistant_run_id, import_order_id, agent_name, level, target_type,
                target_id, suggestion_type, title, reason, source_references_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                import_order_id,
                draft.get("agentName", agent_name),
                LEVEL_REVIEW_NEEDED,
                draft["targetType"],
                draft.get("targetId"),
                "draft_candidate",
                _draft_candidate_title(draft),
                "AI 已准备候选变更，需管理员先核查，批准后才会生成待确认系统变更草稿。",
                _json(draft.get("sourceReferences", [])),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO review_requests (
                assistant_suggestion_id, import_order_id, status, draft_candidate_json,
                agent_name, draft_type, target_type, target_id, original_values_json,
                source_references_json, confidence, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(cursor.lastrowid),
                import_order_id,
                REVIEW_PENDING,
                _json(draft.get("proposedValues", {})),
                draft.get("agentName", agent_name),
                draft["draftType"],
                draft["targetType"],
                draft.get("targetId"),
                _json(draft.get("originalValues", {})),
                _json(draft.get("sourceReferences", [])),
                draft.get("confidence"),
                now,
                now,
            ),
        )
    for field in response["reviewNeededFields"]:
        conn.execute(
            """
            INSERT INTO assistant_review_needed_fields (
                assistant_run_id, import_order_id, agent_name, target_type, target_id,
                field_name, source_value, reason, source_references_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                import_order_id,
                field.get("agentName", agent_name),
                field["targetType"],
                field.get("targetId"),
                field["fieldName"],
                field.get("sourceValue"),
                field.get("reason", ""),
                _json(field.get("sourceReferences", [])),
                now,
            ),
        )
    conn.commit()


def _create_change_draft_from_review(conn: sqlite3.Connection, review_request_id: int) -> int | None:
    review = conn.execute(
        """
        SELECT review_requests.*, assistant_suggestions.assistant_run_id
        FROM review_requests
        JOIN assistant_suggestions ON assistant_suggestions.id = review_requests.assistant_suggestion_id
        WHERE review_requests.id = ?
        """,
        (review_request_id,),
    ).fetchone()
    if review is None:
        raise KeyError(review_request_id)
    if not review["draft_candidate_json"] or review["draft_candidate_json"] == "{}":
        return None
    existing = conn.execute("SELECT id FROM change_drafts WHERE review_request_id = ?", (review_request_id,)).fetchone()
    if existing is not None:
        return int(existing["id"])
    now = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO change_drafts (
            assistant_run_id, review_request_id, import_order_id, agent_name, draft_type,
            target_type, target_id, proposed_values_json, original_values_json,
            source_references_json, confidence, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review["assistant_run_id"],
            review_request_id,
            review["import_order_id"],
            review["agent_name"],
            review["draft_type"],
            review["target_type"],
            review["target_id"],
            review["draft_candidate_json"],
            review["original_values_json"],
            review["source_references_json"],
            review["confidence"],
            DRAFT_DRAFT,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def _draft_candidate_title(draft: dict[str, Any]) -> str:
    proposed = draft.get("proposedValues", {})
    if not isinstance(proposed, dict):
        proposed = {}
    if draft.get("draftType") == "goods_line":
        return f"候选货物项草稿：{proposed.get('cn_name') or proposed.get('customs_en_name') or '未命名货物'}"
    if draft.get("draftType") == "safe_field_batch":
        return proposed.get("operation_name", "批量导入安全字段")
    if draft.get("draftType") == "goods_status_batch":
        return proposed.get("operation_name", "批量更新货物物流状态")
    if draft.get("draftType") == "goods_delete_batch":
        return proposed.get("operation_name", "批量删除货物项")
    if draft.get("draftType") == "import_order_update":
        return proposed.get("operation_name", "修改订单资料")
    if draft.get("draftType") == "import_order_delete":
        return proposed.get("operation_name", "删除当前订单")
    if draft.get("draftType") == "customs_goods_version":
        return f"候选报关版本：{proposed.get('source_name') or proposed.get('document_type', '权威单证')}"
    if draft.get("draftType") == "container":
        return f"候选集装箱：{proposed.get('container_number') or '待确认柜号'}"
    if draft.get("draftType") == "export_document":
        return f"候选单证草稿：{proposed.get('document_type', 'document')}"
    return f"候选变更草稿：{draft.get('draftType', 'unknown')}"


def _draft_operation_name(row: dict[str, Any]) -> str:
    values = json.loads(row["proposed_values_json"])
    if row["draft_type"] == "safe_field_batch":
        return values.get("operation_name", "批量导入安全字段")
    if row["draft_type"] == "goods_status_batch":
        return values.get("operation_name", "批量更新货物物流状态")
    if row["draft_type"] == "goods_delete_batch":
        return values.get("operation_name", "批量删除货物项")
    if row["draft_type"] == "import_order_update":
        return values.get("operation_name", "修改订单资料")
    if row["draft_type"] == "import_order_delete":
        return values.get("operation_name", "删除当前订单")
    if row["draft_type"] == "customs_goods_version":
        return "导入报关版本"
    if row["draft_type"] == "container":
        return "导入集装箱资料"
    return _draft_candidate_title({"draftType": row["draft_type"], "proposedValues": values})


def _values_from_chinese_excel_row(row: dict[str, str]) -> tuple[dict[str, Any], str]:
    product_name = row["产品名称"]
    quantity, quantity_review = _parse_quantity(row["数量（非包裹数）"])
    values: dict[str, Any] = {
        "cn_name": product_name,
        "quantity": quantity,
        "unit": "pcs" if quantity is not None else "",
        "carton_count": _int_or_none(row["箱数量"]),
        "product_url": row["链接"],
        "supplier_name_reference": row["厂家名称"],
        "carton_gross_weight_kg": _float_or_none(row["单箱毛重(kg)"]),
        "volume_cbm": _float_or_none(row["CBM"]),
        "gross_weight": _float_or_none(row["总毛重(kg)"]),
        "shipping_mark": row["麦头"],
        "domestic_tracking_no": row["国内物流单号"],
        "logistics_status_source": row["货物物流状态"],
    }
    values.update(_parse_dimensions(row["外箱尺寸(cm)"]))
    paid = _money_or_none(row["实际付款"])
    if paid is not None and quantity:
        values["purchase_unit_price"] = paid / quantity
        values["purchase_currency"] = "CNY"
    return values, quantity_review


def _goods_line_draft(values: dict[str, Any], source_ref: dict[str, Any], confidence: float) -> dict[str, Any]:
    return {
        "draftType": "goods_line",
        "targetType": "goods_line",
        "targetId": None,
        "proposedValues": {key: value for key, value in values.items() if value not in (None, "")},
        "originalValues": {},
        "sourceReferences": [source_ref],
        "confidence": confidence,
    }


def _source_text(source: Source) -> tuple[str, str]:
    if source.text:
        return source.text, ""
    if not source.path:
        return "", ""
    path = Path(source.path)
    if path.suffix.lower() != ".pdf":
        try:
            return path.read_text(encoding="utf-8"), ""
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="ignore"), ""
    text, parse_error = _pdf_text_with_pypdf(path)
    if text:
        return text, ""
    ocr_text, ocr_error = _ocr_pdf_text(path)
    if ocr_text:
        return ocr_text, ""
    if parse_error and ocr_error:
        return "", f"{parse_error}；{ocr_error}"
    return "", ocr_error or parse_error or "无法解析 PDF 文本：文件可能是扫描件且 OCR 未提取到文字"


def _pdf_text_with_pypdf(path: Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return "", "无法解析 PDF 文本：当前环境缺少 pypdf"
    try:
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:
        return "", f"无法解析 PDF 文本：{exc}"
    return (text, "") if text else ("", "PDF 未包含可直接提取的文字")


def _ocr_pdf_text(path: Path) -> tuple[str, str]:
    pdftoppm = shutil.which(os.getenv("CARGOPILOT_PDFTOPPM", "pdftoppm"))
    tesseract = shutil.which(os.getenv("CARGOPILOT_TESSERACT", "tesseract"))
    if not pdftoppm or not tesseract:
        return "", "无法解析 PDF 文本：扫描件 OCR 需要安装 poppler(pdftoppm) 和 tesseract"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "page"
            rendered = subprocess.run([pdftoppm, "-r", "200", "-png", str(path), str(prefix)], capture_output=True, text=True, check=False)
            if rendered.returncode != 0:
                return "", f"无法解析 PDF 文本：OCR 渲染失败 {rendered.stderr.strip()}"
            pages = sorted(Path(tmp).glob("page-*.png"))
            if not pages:
                return "", "无法解析 PDF 文本：OCR 没有生成页面图片"
            chunks = []
            for page in pages:
                text, error = _ocr_image_text(tesseract, page)
                if text:
                    chunks.append(text)
                elif error:
                    return "", error
            text = "\n".join(chunks).strip()
            return (text, "") if text else ("", "无法解析 PDF 文本：OCR 未提取到文字")
    except Exception as exc:
        return "", f"无法解析 PDF 文本：OCR 失败 {exc}"


def _ocr_image_text(tesseract: str, image_path: Path) -> tuple[str, str]:
    languages = [os.getenv("CARGOPILOT_OCR_LANG", "eng+chi_sim"), "eng"]
    last_error = ""
    for language in dict.fromkeys(languages):
        result = subprocess.run([tesseract, str(image_path), "stdout", "-l", language, "--psm", "6"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout.strip(), ""
        last_error = result.stderr.strip()
    return "", f"无法解析 PDF 文本：OCR 识别失败 {last_error}"


def _parse_text_goods_rows(text: str) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        values = _parse_text_goods_line(line)
        if values:
            rows.append((line_number, values))
    if not rows:
        values = _parse_text_goods_line(text)
        if values:
            rows.append((1, values))
    return rows


def _parse_text_goods_line(line: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, patterns in {
        "customer_item_no": [r"(?:货号|款号|item(?:\s*no)?)[：:\s]+([A-Za-z0-9_-]+)"],
        "sku_or_model": [r"(?:SKU|型号|model)[：:\s]+([A-Za-z0-9_-]+)"],
        "cn_name": [r"(?:产品|品名|货物名称)[：:\s]+([^,，;；\n]+)"],
        "customs_en_name": [r"(?:报关英文品名|英文品名|customs(?:\s+english)?\s+name)[：:\s]+([^,，;；\n]+)"],
        "hs_code": [r"(?:HS(?:\s*Code)?|海关编码)[：:\s]+([0-9.]+)"],
        "shipping_mark": [r"(?:麦头|shipping\s*mark)[：:\s]+([^,，;；\n]+)"],
        "domestic_tracking_no": [r"(?:国内物流单号|运单号|tracking(?:\s*no)?)[：:\s]+([A-Za-z0-9_-]+)"],
    }.items():
        match = next((re.search(pattern, line, re.I) for pattern in patterns if re.search(pattern, line, re.I)), None)
        if match:
            values[field] = match.group(1).strip()
    if url := re.search(r"https?://\S+", line):
        values["product_url"] = url.group(0).rstrip("。,;；")
    for field, pattern in {
        "carton_count": r"(?:箱数|箱数量|cartons?)[：:\s]*(\d+)",
        "quantity": r"(?:数量|qty)[：:\s]*(\d+(?:\.\d+)?)",
        "units_per_carton": r"(?:每箱|每箱数量|pcs/ctn)[：:\s]*(\d+(?:\.\d+)?)",
        "carton_gross_weight_kg": r"(?:单箱毛重|每箱毛重|carton\s*gw)[：:\s]*(\d+(?:\.\d+)?)",
        "gross_weight": r"(?:总毛重|gross\s*weight)[：:\s]*(\d+(?:\.\d+)?)",
        "volume_cbm": r"(?:CBM|体积)[：:\s]*(\d+(?:\.\d+)?)",
    }.items():
        if match := re.search(pattern, line, re.I):
            values[field] = _int_or_none(match.group(1)) if field == "carton_count" else _float_or_none(match.group(1))
    if match := re.search(r"(\d+(?:\.\d+)?)\s*[*xX×]\s*(\d+(?:\.\d+)?)\s*[*xX×]\s*(\d+(?:\.\d+)?)\s*(?:cm|厘米)?", line, re.I):
        values.update({"carton_length_cm": float(match.group(1)), "carton_width_cm": float(match.group(2)), "carton_height_cm": float(match.group(3))})
    return values if any(key in values for key in ["customer_item_no", "sku_or_model", "cn_name", "customs_en_name", "hs_code"]) else {}


def _parse_document_data(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field, pattern in {
        "shipper": r"(?:shipper|发货人)[：:\s]+([^;\n]+)",
        "consignee": r"(?:consignee|收货人)[：:\s]+([^;\n]+)",
        "vessel": r"(?:vessel|船名)[：:\s]+([^;\n]+)",
        "voyage": r"(?:voyage|航次)[：:\s]+([^;\n]+)",
    }.items():
        if match := re.search(pattern, text, re.I):
            data[field] = match.group(1).strip()
    return data


def _parse_container_data(text: str) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\bDR\s+Y\b", "DRY", text, flags=re.I)
    data: dict[str, Any] = {}
    for field, pattern in {
        "container_number": r"(?:container\s*(?:no\.?|number)|柜号|箱号)[：:\s]+([A-Z]{3,4}\d{6,7})",
        "seal_number": r"(?:seal\s*(?:no\.?|number)|封号|铅封号)[：:\s]+([A-Za-z0-9_-]+)",
        "container_type": r"(?:container\s*type|柜型|箱型)[：:\s]+(20GP|40GP|40HQ|40HC)",
        "loading_date": r"(?:loading\s*date|装柜日期|装箱日期)[：:\s]+(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
    }.items():
        if match := re.search(pattern, text, re.I):
            data[field] = match.group(1).strip().replace("/", "-")
    if data.get("container_type") == "40HC":
        data["container_type"] = "40HQ"
    if not data.get("container_number"):
        if match := re.search(r"\b([A-Z]{4}\d{7})\s+([A-Z0-9-]{6,20})\s+(20|40)\s*(DRY|GP|HQ|HC)?", text, re.I):
            data["container_number"] = match.group(1).strip()
            data["seal_number"] = match.group(2).strip()
            size = match.group(3)
            kind = (match.group(4) or "GP").upper()
            data["container_type"] = f"{size}HQ" if kind in {"HQ", "HC"} else f"{size}GP"
    if data.get("container_number"):
        if match := re.search(r"(\d+)\s*BAGS?\s+(\d+(?:\.\d+)?)\s*KGS?\s+(\d+(?:\.\d+)?)\s*CBM", text, re.I):
            data["package_count"] = int(match.group(1))
            data["gross_weight"] = float(match.group(2))
            data["volume_cbm"] = float(match.group(3))
            data["notes"] = f"{data['package_count']} BAGS; {data['gross_weight']} KGS; {data['volume_cbm']} CBM"
    return data if data.get("container_number") else {}


def _parse_goods_status_command(text: str) -> str:
    if not is_order_command_text(text):
        return ""
    return _normalize_goods_status(text)


def is_order_command_text(text: str) -> bool:
    has_goods_scope = (
        "货物" in text
        and any(word in text for word in GOODS_COMMAND_TARGET_WORDS)
    )
    has_order_scope = "订单" in text
    return (has_goods_scope and (
        any(word in text for word in GOODS_DELETE_WORDS)
        or (
            any(word in text for word in GOODS_COMMAND_ACTION_WORDS)
            and any(alias in text for aliases in GOODS_STATUS_ALIASES.values() for alias in aliases)
        )
    )) or (
        has_order_scope
        and (
            any(word in text for word in GOODS_DELETE_WORDS)
            or any(word in text for word in GOODS_COMMAND_ACTION_WORDS)
        )
    )


def _parse_goods_delete_command(text: str) -> bool:
    return "货物" in text and any(word in text for word in GOODS_COMMAND_TARGET_WORDS) and any(word in text for word in GOODS_DELETE_WORDS)


def _parse_order_delete_command(text: str) -> bool:
    return "订单" in text and "货物" not in text and any(word in text for word in GOODS_DELETE_WORDS)


def _hydrate_command_drafts(
    conn: sqlite3.Connection,
    import_order_id: int,
    sources: list[Source],
    response: dict[str, Any],
    prompt_version: str,
) -> dict[str, Any]:
    drafts: list[dict[str, Any]] = []
    if not isinstance(response, dict):
        response = {"drafts": [response], "reviewNeededFields": [], "suggestions": [], "usage": {}}
    review_needed = [item for item in response.get("reviewNeededFields", []) if isinstance(item, dict)]
    source_ref = _source_ref(sources[0]) if sources else _system_ref(import_order_id, "order_command")
    raw_drafts = response.get("drafts", [])
    if not raw_drafts and any(key in response for key in ["action", "operation", "draftType", "draft_type", "status", "logistics_status"]):
        raw_drafts = [response]
    if isinstance(raw_drafts, dict):
        raw_drafts = [raw_drafts]
    for draft in raw_drafts if isinstance(raw_drafts, list) else [raw_drafts]:
        draft_type, proposed = _command_draft_parts(draft)
        if draft_type == "goods_delete_batch":
            drafts.append(_goods_delete_batch_draft(conn, import_order_id, source_ref))
            continue
        if draft_type == "import_order_delete":
            drafts.append(_import_order_delete_draft(conn, import_order_id, source_ref))
            continue
        if draft_type == "import_order_update":
            values = _import_order_update_values(proposed)
            if values:
                drafts.append(_import_order_update_draft(conn, import_order_id, values, source_ref))
            else:
                review_needed.append(_review_field("import_order", import_order_id, "unsupported_order_update", str(proposed)[:120], "模型没有返回可更新的订单字段", source_ref))
            continue
        if draft_type != "goods_status_batch":
            review_needed.append(_review_field("import_order", import_order_id, "unsupported_command", str(draft_type or draft)[:120], "模型识别到的操作不在 MVP 允许范围内", source_ref))
            continue
        status = _normalize_goods_status(str(proposed.get("status") or proposed.get("logistics_status") or proposed.get("to_status") or proposed.get("status_label") or ""))
        if not status:
            review_needed.append(_review_field("import_order", import_order_id, "unsupported_command_status", str(proposed)[:120], "模型没有返回可识别的货物物流状态", source_ref))
            continue
        drafts.append(_goods_status_batch_draft(conn, import_order_id, status, source_ref))
    if not drafts and not review_needed:
        review_needed.append(_review_field("import_order", import_order_id, "unsupported_command", str(response)[:120], "模型没有返回可执行的订单操作", source_ref))
    usage = response.get("usage", {}) if isinstance(response.get("usage", {}), dict) else {}
    suggestions = [item for item in response.get("suggestions", []) if isinstance(item, dict)]
    return {"suggestions": suggestions, "drafts": drafts, "reviewNeededFields": review_needed, "usage": usage or {"model": "demo", "promptVersion": prompt_version, "inputTokens": 0, "outputTokens": 0, "runtimeMs": 0}}


def _command_draft_parts(draft: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(draft, dict):
        text = str(draft)
        if _parse_goods_delete_command(text):
            return "goods_delete_batch", {}
        return ("goods_status_batch", {"status": status}) if (status := _normalize_goods_status(text)) else ("", {})
    draft_type = str(draft.get("draftType") or draft.get("draft_type") or draft.get("action") or draft.get("operation") or "")
    proposed = draft.get("proposedValues") or draft.get("proposed_values") or draft
    proposed = proposed if isinstance(proposed, dict) else {"status": str(proposed)}
    action_text = f"{draft_type} {proposed}"
    if draft_type in {"delete_goods_lines", "delete_goods_line", "goods_delete_batch"} or _parse_goods_delete_command(action_text):
        return "goods_delete_batch", proposed
    if draft_type in {"delete_import_order", "import_order_delete"} or _parse_order_delete_command(action_text):
        return "import_order_delete", proposed
    if draft_type in {"update_import_order", "update_order", "modify_import_order", "import_order_update"}:
        return "import_order_update", proposed
    if draft_type in {"update_goods_logistics_status", "goods_status_batch"} or _normalize_goods_status(action_text):
        return "goods_status_batch", proposed
    return draft_type, proposed


def _normalize_goods_status(text: str) -> str:
    if text in GOODS_LOGISTICS_STATUS_LABELS:
        return text
    for status, aliases in GOODS_STATUS_ALIASES.items():
        if GOODS_LOGISTICS_STATUS_LABELS[status] in text or any(alias in text for alias in aliases):
            return status
    return ""


def _goods_status_batch_draft(conn: sqlite3.Connection, import_order_id: int, status: str, source_ref: dict[str, Any]) -> dict[str, Any]:
    items = [
        {
            "goods_line_id": row["id"],
            "goods_label": _goods_label(row),
            "from_status": row["logistics_status"],
            "to_status": status,
            "to_status_label": GOODS_LOGISTICS_STATUS_LABELS.get(status, status),
        }
        for row in _goods_lines(conn, import_order_id)
        if row["logistics_status"] != status
    ]
    return {
        "draftType": "goods_status_batch",
        "targetType": "goods_status_batch",
        "targetId": None,
        "proposedValues": {
            "operation_name": f"批量更新货物物流状态为{GOODS_LOGISTICS_STATUS_LABELS.get(status, status)}",
            "status": status,
            "status_label": GOODS_LOGISTICS_STATUS_LABELS.get(status, status),
            "items": items,
        },
        "originalValues": {"items": [{"goods_line_id": item["goods_line_id"], "logistics_status": item["from_status"]} for item in items]},
        "sourceReferences": [source_ref],
        "confidence": 0.78,
    }


def _goods_delete_batch_draft(conn: sqlite3.Connection, import_order_id: int, source_ref: dict[str, Any]) -> dict[str, Any]:
    items = [{"goods_line_id": row["id"], "goods_label": _goods_label(row)} for row in _goods_lines(conn, import_order_id)]
    return {
        "draftType": "goods_delete_batch",
        "targetType": "goods_delete_batch",
        "targetId": None,
        "proposedValues": {
            "operation_name": "批量删除当前订单货物项",
            "items": items,
        },
        "originalValues": {"items": items},
        "sourceReferences": [source_ref],
        "confidence": 0.72,
    }


def _import_order_update_draft(conn: sqlite3.Connection, import_order_id: int, values: dict[str, Any], source_ref: dict[str, Any]) -> dict[str, Any]:
    order = _require_order(conn, import_order_id)
    original = {field: order[field] for field in values if field in order.keys()}
    return {
        "draftType": "import_order_update",
        "targetType": "import_order",
        "targetId": import_order_id,
        "proposedValues": {"operation_name": "修改订单资料", **values},
        "originalValues": original,
        "sourceReferences": [source_ref],
        "confidence": 0.74,
    }


def _import_order_delete_draft(conn: sqlite3.Connection, import_order_id: int, source_ref: dict[str, Any]) -> dict[str, Any]:
    order = _require_order(conn, import_order_id)
    return {
        "draftType": "import_order_delete",
        "targetType": "import_order",
        "targetId": import_order_id,
        "proposedValues": {
            "operation_name": "删除当前订单",
            "order_no": order["order_no"],
        },
        "originalValues": dict(order),
        "sourceReferences": [source_ref],
        "confidence": 0.7,
    }


def _container_draft(values: dict[str, Any], source_ref: dict[str, Any], confidence: float) -> dict[str, Any]:
    return {
        "draftType": "container",
        "targetType": "container",
        "targetId": None,
        "proposedValues": values,
        "originalValues": {},
        "sourceReferences": [source_ref],
        "confidence": confidence,
    }


def _match_goods_drafts(
    conn: sqlite3.Connection,
    import_order_id: int,
    drafts: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    review_needed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    goods = _goods_lines(conn, import_order_id)
    matched_ids: set[int] = set()
    safe_items: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for draft in drafts:
        if draft.get("draftType") != "goods_line" or draft.get("targetType") != "goods_line":
            remaining.append(draft)
            continue
        proposed = draft.get("proposedValues", {})
        match, score = _best_goods_match(goods, proposed)
        if match is None:
            remaining.append(draft)
            continue
        source_ref = (draft.get("sourceReferences") or [_system_ref(match["id"], "source_match")])[0]
        if score < 0.8:
            review_needed.append(_review_field("goods_line", match["id"], "source_match", _goods_label(proposed), "匹配置信度较低，不能批量导入", source_ref))
            continue
        matched_ids.add(int(match["id"]))
        suggestions.append(_suggestion(AGENT_COORDINATOR, LEVEL_SUGGESTION, "goods_line", match["id"], "source_row_matched", f"{_goods_label(proposed)} 已匹配系统货物项", "匹配置信度足够，可按字段安全级别处理。", draft.get("sourceReferences", [])))
        safe_fields, original = _safe_update_fields(conn, match, proposed, review_needed, source_ref)
        if safe_fields:
            safe_items.append({"goods_line_id": match["id"], "goods_label": _goods_label(match), "fields": safe_fields, "original": original})
    if safe_items:
        remaining.append(
            {
                "draftType": "safe_field_batch",
                "targetType": "safe_field_batch",
                "targetId": None,
                "proposedValues": {"operation_name": "导入箱规/麦头/物流单号", "items": safe_items},
                "originalValues": {"items": [{"goods_line_id": item["goods_line_id"], "fields": item["original"]} for item in safe_items]},
                "sourceReferences": [],
                "confidence": 0.9,
            }
        )
    if drafts and matched_ids:
        for row in goods:
            if int(row["id"]) not in matched_ids:
                suggestions.append(_suggestion(AGENT_COORDINATOR, LEVEL_REVIEW_NEEDED, "goods_line", row["id"], "missing_existing_line", f"{_goods_label(row)} 系统中存在，但本次资料没有出现", "请确认供应商资料是否漏掉该货物项。"))
    return remaining


def _best_goods_match(goods: list[sqlite3.Row], proposed: dict[str, Any]) -> tuple[sqlite3.Row | None, float]:
    best: tuple[sqlite3.Row | None, float] = (None, 0.0)
    for row in goods:
        score = 0.0
        for field, weight in [("customer_item_no", 1.0), ("sku_or_model", 0.95), ("product_url", 0.9), ("cn_name", 0.85), ("customs_en_name", 0.82), ("en_name", 0.8)]:
            if proposed.get(field) and row[field] and _norm(proposed[field]) == _norm(row[field]):
                score = max(score, weight)
        if proposed.get("cn_name") and row["notes"] and _norm(proposed["cn_name"]) in _norm(row["notes"]):
            score = max(score, 0.65)
        if score > best[1]:
            best = (row, score)
    return best


def _safe_update_fields(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    proposed: dict[str, Any],
    review_needed: list[dict[str, Any]],
    source_ref: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    safe: dict[str, Any] = {}
    original: dict[str, Any] = {}
    tracking_numbers = _tracking_numbers(conn, row["id"])
    for field, value in proposed.items():
        if value in (None, ""):
            continue
        if field == "domestic_tracking_no":
            if not tracking_numbers or value in tracking_numbers:
                safe[field] = value
                original[field] = ", ".join(tracking_numbers)
            else:
                review_needed.append(_review_field("goods_line", row["id"], field, value, "国内物流单号与系统已有记录不同，需管理员确认", source_ref))
            continue
        if field in SAFE_WORKING_FIELDS:
            old = row[field]
            if old in (None, "") or _norm(old) == _norm(value):
                safe[field] = value
                original[field] = old
            else:
                review_needed.append(_review_field("goods_line", row["id"], field, value, "安全字段与系统值不一致，需管理员确认", source_ref))
        elif field in UNSAFE_WORKING_FIELDS and _norm(row[field] if field in row.keys() else "") != _norm(value):
            review_needed.append(_review_field("goods_line", row["id"], field, value, "该字段不允许从工作来源批量导入", source_ref))
    return safe, original


def _apply_safe_field_batch(conn: sqlite3.Connection, actor_role: str, import_order_id: int, values: dict[str, Any]) -> None:
    for item in values.get("items", []):
        goods_line_id = int(item["goods_line_id"])
        row = conn.execute("SELECT import_order_id FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        if row is None or int(row["import_order_id"]) != int(import_order_id):
            raise ValueError("safe batch goods line is outside selected Import Order")
        fields = {key: value for key, value in item.get("fields", {}).items() if key in SAFE_WORKING_FIELDS and value not in (None, "")}
        tracking_no = fields.pop("domestic_tracking_no", "")
        if fields:
            update_goods_line(conn, actor_role=actor_role, goods_line_id=goods_line_id, **fields)
        if tracking_no:
            _add_tracking_number(conn, goods_line_id, str(tracking_no), "AI资料收集箱安全批量导入")


def _apply_goods_status_batch(conn: sqlite3.Connection, actor_role: str, import_order_id: int, values: dict[str, Any]) -> None:
    status = values.get("status")
    if status not in GOODS_LOGISTICS_STATUS_LABELS:
        raise ValueError("unsupported goods logistics status")
    for item in values.get("items", []):
        goods_line_id = int(item["goods_line_id"])
        row = conn.execute("SELECT import_order_id FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        if row is None or int(row["import_order_id"]) != int(import_order_id):
            raise ValueError("goods status batch item is outside selected Import Order")
        update_goods_line(conn, actor_role=actor_role, goods_line_id=goods_line_id, logistics_status=status)


def _apply_goods_delete_batch(conn: sqlite3.Connection, import_order_id: int, values: dict[str, Any]) -> None:
    for item in values.get("items", []):
        goods_line_id = int(item["goods_line_id"])
        row = conn.execute("SELECT import_order_id FROM goods_lines WHERE id = ?", (goods_line_id,)).fetchone()
        if row is None:
            continue
        if int(row["import_order_id"]) != int(import_order_id):
            raise ValueError("goods delete batch item is outside selected Import Order")
        conn.execute("DELETE FROM goods_lines WHERE id = ?", (goods_line_id,))


def _apply_container_draft(conn: sqlite3.Connection, actor_role: str, import_order_id: int, values: dict[str, Any]) -> int:
    return create_container(
        conn,
        actor_role=actor_role,
        import_order_id=import_order_id,
        container_type=str(values.get("container_type") or "40HQ"),
        container_number=str(values["container_number"]),
        seal_number=str(values.get("seal_number") or ""),
        loading_date=str(values.get("loading_date") or ""),
        notes=str(values.get("notes") or "AI资料收集箱从海运单提取"),
    )


def _apply_import_order_delete(conn: sqlite3.Connection, import_order_id: int) -> None:
    conn.execute("DELETE FROM import_orders WHERE id = ?", (import_order_id,))


def _import_order_update_values(values: dict[str, Any]) -> dict[str, Any]:
    raw = values.get("fields") or values.get("changes") or values.get("proposedValues") or values
    if not isinstance(raw, dict):
        return {}
    if raw.get("field") and "value" in raw:
        raw = {raw["field"]: raw["value"]}
    changes: dict[str, Any] = {}
    for key, value in raw.items():
        field = ORDER_FIELD_ALIASES.get(str(key), str(key))
        if field == "operation_name" or field not in IMPORT_ORDER_FIELDS:
            continue
        changes[field] = _normalize_order_status(value) if field == "order_status" else value
    return {key: value for key, value in changes.items() if value not in (None, "")}


def _normalize_order_status(value: Any) -> str:
    text = str(value or "")
    if text in ORDER_STATUS_ALIASES:
        return text
    for status, aliases in ORDER_STATUS_ALIASES.items():
        if any(alias in text for alias in aliases):
            return status
    return text


def _store_customs_goods_version(conn: sqlite3.Connection, draft: sqlite3.Row, values: dict[str, Any], actor_user_id: int | None) -> int:
    now = utc_now()
    conn.execute("UPDATE customs_goods_versions SET is_current = 0, updated_at = ? WHERE import_order_id = ?", (now, draft["import_order_id"]))
    cursor = conn.execute(
        """
        INSERT INTO customs_goods_versions (
            import_order_id, assistant_run_id, change_draft_id, source_document_type,
            source_name, rows_json, totals_json, document_data_json, discrepancy_notes_json,
            confirmation_status, is_current, confirmed_by_user_id, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            draft["import_order_id"],
            draft["assistant_run_id"],
            draft["id"],
            values.get("document_type", ""),
            values.get("source_name", ""),
            _json(values.get("rows", [])),
            _json(values.get("totals", {})),
            _json(values.get("document_data", {})),
            _json(values.get("discrepancies", [])),
            "confirmed",
            actor_user_id,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def _customs_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, Any] = {}
    for field in ["carton_count", "quantity", "gross_weight", "volume_cbm"]:
        value = sum(float(row.get(field) or 0) for row in rows)
        if value:
            totals[field] = value
    return totals


def _customs_discrepancies(conn: sqlite3.Connection, import_order_id: int, rows: list[dict[str, Any]]) -> list[str]:
    entered = _goods_lines(conn, import_order_id)
    entered_cartons = sum(row["carton_count"] or 0 for row in entered)
    customs_cartons = sum(row.get("carton_count") or 0 for row in rows)
    notes = []
    if customs_cartons and entered_cartons and customs_cartons != entered_cartons:
        notes.append(f"报关箱数 {customs_cartons:g} 与录入版本箱数 {entered_cartons:g} 不一致")
    if len(rows) < len(entered):
        notes.append("报关版本行数少于录入货物项，可能是合并申报")
    return notes


def _tracking_numbers(conn: sqlite3.Connection, goods_line_id: int) -> list[str]:
    return [row["tracking_no"] for row in conn.execute("SELECT tracking_no FROM domestic_tracking_numbers WHERE goods_line_id = ? ORDER BY id", (goods_line_id,))]


def _add_tracking_number(conn: sqlite3.Connection, goods_line_id: int, tracking_no: str, notes: str) -> None:
    if tracking_no in _tracking_numbers(conn, goods_line_id):
        return
    conn.execute(
        "INSERT INTO domestic_tracking_numbers (goods_line_id, tracking_no, notes, created_at) VALUES (?, ?, ?, ?)",
        (goods_line_id, tracking_no, notes, utc_now()),
    )


def _goods_label(row: sqlite3.Row | dict[str, Any]) -> str:
    if isinstance(row, sqlite3.Row):
        return str(row["customer_item_no"] or row["sku_or_model"] or row["cn_name"] or row["customs_en_name"] or row["id"])
    return str(row.get("customer_item_no") or row.get("sku_or_model") or row.get("cn_name") or row.get("customs_en_name") or "未命名货物")


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _record_usage(conn: sqlite3.Connection, run_id: int, agent_name: str, model_name: str, prompt_version: str, started: float) -> None:
    conn.execute(
        """
        INSERT INTO assistant_model_usage (
            assistant_run_id, agent_name, model_name, prompt_version,
            input_tokens, output_tokens, runtime_ms, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, agent_name, model_name, prompt_version, 0, 0, int((time.monotonic() - started) * 1000), utc_now()),
    )
    conn.commit()


def _record_usage_from_response(conn: sqlite3.Connection, run_id: int, agent_name: str, usage: dict[str, Any], prompt_version: str, started: float) -> None:
    conn.execute(
        """
        INSERT INTO assistant_model_usage (
            assistant_run_id, agent_name, model_name, prompt_version,
            input_tokens, output_tokens, runtime_ms, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            agent_name,
            usage.get("model") or ("demo" if not os.getenv("DEEPSEEK_API_KEY") else os.getenv("DEEPSEEK_MODEL", "deepseek-chat")),
            usage.get("promptVersion") or prompt_version,
            int(usage.get("inputTokens", 0) or 0),
            int(usage.get("outputTokens", 0) or 0),
            int(usage.get("runtimeMs", int((time.monotonic() - started) * 1000)) or 0),
            utc_now(),
        ),
    )
    conn.commit()


def _envelope(
    *,
    suggestions: list[dict[str, Any]] | None = None,
    drafts: list[dict[str, Any]] | None = None,
    review_needed: list[dict[str, Any]] | None = None,
    prompt_version: str,
) -> dict[str, Any]:
    return {
        "suggestions": suggestions or [],
        "drafts": drafts or [],
        "reviewNeededFields": review_needed or [],
        "usage": {"model": "demo", "promptVersion": prompt_version, "inputTokens": 0, "outputTokens": 0, "runtimeMs": 0},
    }


def _coerce_agent_response(response: Any, *, import_order_id: int, sources: list[Source], prompt_version: str) -> dict[str, Any]:
    if not isinstance(response, dict):
        return _envelope(
            suggestions=[
                _no_recognized_data_suggestion(
                    import_order_id,
                    sources,
                    reason=f"模型返回内容无法转成系统录入项：{str(response)[:120]}",
                )
            ],
            prompt_version=prompt_version,
        )
    suggestions, dropped_suggestions = _coerce_dict_list(response.get("suggestions", []))
    raw_drafts, dropped_drafts = _coerce_dict_list(response.get("drafts", []))
    drafts = [_coerce_model_draft(draft) for draft in raw_drafts]
    dropped_drafts += sum(1 for draft in drafts if not draft)
    drafts = [draft for draft in drafts if draft]
    review_needed, dropped_review_needed = _coerce_dict_list(response.get("reviewNeededFields", []))
    dropped = dropped_suggestions + dropped_drafts + dropped_review_needed
    if dropped and not suggestions and not drafts and not review_needed:
        suggestions.append(
            _no_recognized_data_suggestion(
                import_order_id,
                sources,
                reason="模型返回了无法转成系统录入项的内容，本次未生成可确认数据。",
            )
        )
    usage = response.get("usage", {}) if isinstance(response.get("usage", {}), dict) else {}
    candidate = {
        "suggestions": suggestions,
        "drafts": drafts,
        "reviewNeededFields": review_needed,
        "usage": usage
        or {"model": "demo", "promptVersion": prompt_version, "inputTokens": 0, "outputTokens": 0, "runtimeMs": 0},
    }
    try:
        validate_agent_response(candidate)
    except ValueError as exc:
        return _envelope(
            suggestions=[
                _no_recognized_data_suggestion(
                    import_order_id,
                    sources,
                    reason=f"模型返回格式无法转成系统录入项：{exc}",
                )
            ],
            prompt_version=prompt_version,
        )
    return candidate


def _coerce_dict_list(value: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(value, list):
        return [], 1 if value not in (None, []) else 0
    valid = [item for item in value if isinstance(item, dict)]
    return valid, len(value) - len(valid)


def _coerce_model_draft(draft: dict[str, Any]) -> dict[str, Any] | None:
    proposed = draft.get("proposedValues") or draft.get("proposed_values") or {}
    if not isinstance(proposed, dict):
        proposed = {}
    for key in ["container_number", "seal_number", "container_type", "loading_date", "rows", "document_type", "source_name"]:
        if key in draft and key not in proposed:
            proposed[key] = draft[key]
    draft_type = str(draft.get("draftType") or draft.get("draft_type") or draft.get("targetType") or draft.get("target_type") or draft.get("type") or "")
    if not draft_type and proposed.get("container_number"):
        draft_type = "container"
    if not draft_type and proposed.get("rows"):
        draft_type = "customs_goods_version"
    target_type = str(draft.get("targetType") or draft.get("target_type") or draft_type)
    if not draft_type or not target_type or not proposed:
        return None
    return {
        **draft,
        "draftType": draft_type,
        "targetType": target_type,
        "targetId": draft.get("targetId") or draft.get("target_id"),
        "proposedValues": proposed,
        "originalValues": draft.get("originalValues") if isinstance(draft.get("originalValues"), dict) else {},
        "sourceReferences": draft.get("sourceReferences") if isinstance(draft.get("sourceReferences"), list) else [],
    }


def _no_recognized_data_suggestion(
    import_order_id: int | None,
    sources: list[Source],
    *,
    reason: str = "AI/本地解析没有从本次资料中提取到可录入或需核查的业务数据。",
) -> dict[str, Any]:
    return _suggestion(
        AGENT_COORDINATOR,
        LEVEL_SUGGESTION,
        "import_order",
        import_order_id,
        "no_recognized_data",
        "未识别到有效数据",
        reason,
        [_source_ref(source) for source in sources] or [_system_ref(import_order_id, "no_recognized_data")],
    )


def _suggestion(agent_name: str, level: str, target_type: str, target_id: int | None, suggestion_type: str, title: str, reason: str, source_refs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "agentName": agent_name,
        "level": level,
        "targetType": target_type,
        "targetId": target_id,
        "suggestionType": suggestion_type,
        "title": title,
        "reason": reason,
        "sourceReferences": source_refs or [_system_ref(target_id, suggestion_type)],
    }


def _review_field(target_type: str, target_id: int | None, field_name: str, source_value: Any, reason: str, source_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "targetType": target_type,
        "targetId": target_id,
        "fieldName": field_name,
        "sourceValue": "" if source_value is None else str(source_value),
        "reason": reason,
        "sourceReferences": [source_ref],
    }


def _source_ref(source: Source, *, row_number: int | None = None, column: str | None = None) -> dict[str, Any]:
    ref = {"sourceType": source.source_type, "name": source.name or (Path(source.path).name if source.path else "pasted text")}
    if row_number is not None:
        ref["row"] = row_number
    if column:
        ref["column"] = column
    return ref


def _system_ref(target_id: int | None, field: str) -> dict[str, Any]:
    return {"sourceType": "system", "targetId": target_id, "field": field}


def _require_order(conn: sqlite3.Connection, import_order_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM import_orders WHERE id = ?", (import_order_id,)).fetchone()
    if row is None:
        raise KeyError(import_order_id)
    return row


def _order_context(conn: sqlite3.Connection, import_order_id: int) -> dict[str, Any]:
    order = dict(_require_order(conn, import_order_id))
    goods = [dict(row) for row in _goods_lines(conn, import_order_id)]
    finance_rows = [dict(row) for row in conn.execute("SELECT * FROM finance_lines WHERE import_order_id = ? ORDER BY id", (import_order_id,))]
    return {"order": order, "goodsLines": goods, "financeLines": finance_rows}


def _deepseek_config(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        setting = get_setting(conn, "deepseek")
    except KeyError:
        setting = {}
    return {
        "api_key": os.getenv("DEEPSEEK_API_KEY") or setting.get("api_key", ""),
        "model": os.getenv("DEEPSEEK_MODEL") or setting.get("model", "deepseek-chat"),
        "api_base": normalize_deepseek_api_base(os.getenv("DEEPSEEK_API_BASE") or setting.get("api_base", "https://api.deepseek.com")),
        "timeout_seconds": os.getenv("DEEPSEEK_TIMEOUT_SECONDS") or setting.get("timeout_seconds", 30),
    }


def _source_context(source: Source) -> dict[str, Any]:
    context = source.__dict__.copy()
    if source.source_type == "excel" and source.path:
        context["rows"] = read_xlsx_rows(source.path)[:80]
    if source.source_type in TEXT_SOURCE_TYPES:
        text, parse_error = _source_text(source)
        context["text"] = text[:12000]
        if parse_error:
            context["parse_error"] = parse_error
    return context


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM assistant_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise KeyError(run_id)
    return row


def _draft(conn: sqlite3.Connection, change_draft_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM change_drafts WHERE id = ?", (change_draft_id,)).fetchone()
    if row is None:
        raise KeyError(change_draft_id)
    return row


def _goods_lines(conn: sqlite3.Connection, import_order_id: int) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM goods_lines WHERE import_order_id = ? ORDER BY id", (import_order_id,)))


def _has_tracking(conn: sqlite3.Connection, goods_line_id: int) -> bool:
    return conn.execute("SELECT 1 FROM domestic_tracking_numbers WHERE goods_line_id = ? LIMIT 1", (goods_line_id,)).fetchone() is not None


def _dict_rows(rows: list[list[str]]) -> list[dict[str, str]]:
    headers = rows[0]
    return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in rows[1:]]


def _parse_quantity(value: str) -> tuple[float | None, str]:
    try:
        return float(value), ""
    except (TypeError, ValueError):
        return None, "数量包含单位或无法安全解析"


def _parse_dimensions(value: str) -> dict[str, float | None]:
    parts = re.split(r"[*xX×]", value or "")
    if len(parts) != 3:
        return {"carton_length_cm": None, "carton_width_cm": None, "carton_height_cm": None}
    numbers = [_float_or_none(part) for part in parts]
    if any(number is None for number in numbers):
        return {"carton_length_cm": None, "carton_width_cm": None, "carton_height_cm": None}
    return {"carton_length_cm": numbers[0], "carton_width_cm": numbers[1], "carton_height_cm": numbers[2]}


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, "", "-"):
            return None
        return float(value)
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    number = _float_or_none(value)
    return int(number) if number is not None else None


def _money_or_none(value: Any) -> float | None:
    return _float_or_none(value)


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _has_product_or_certificate_text(value: str) -> bool:
    return any(word in value for word in ["产品", "证书", "certificate", "wood", "食品", "儿童", "纺织", "皮革"])


def _has_finance_text(value: str) -> bool:
    return any(word in value for word in ["amount", "quote", "cost", "price", "付款", "报价", "费用", "利润", "汇率"])


def _has_document_text(value: str) -> bool:
    return any(word in value for word in ["invoice", "packing", "商业发票", "装箱单", "单证"])


def _goods_line_values(values: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "supplier_id",
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
        "packaging_method",
        "carton_count",
        "units_per_carton",
        "carton_gross_weight_kg",
        "gross_weight",
        "carton_length_cm",
        "carton_width_cm",
        "carton_height_cm",
        "volume_cbm",
        "shipping_mark",
        "target_markup",
        "target_margin",
        "sales_unit_price",
        "sales_currency",
        "purchase_unit_price",
        "purchase_currency",
        "notes",
    }
    return {key: value for key, value in values.items() if key in allowed and value not in (None, "")}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

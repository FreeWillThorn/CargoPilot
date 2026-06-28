from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any
from urllib import request

from .calculations import STAGE_FINAL_DOCUMENTS, check_goods_line_stage
from .documents import DOC_COMMERCIAL_INVOICE, DOC_PACKING_LIST, build_document_data
from .finance import LINE_CHARGE, LINE_COST
from .foundation import ROLE_ADMIN, get_setting, utc_now
from .master_data import require_admin
from .orders import create_goods_line, update_goods_line
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
    REVIEW_NEEDS_FOLLOWUP: "需跟进",
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
AGENT_COORDINATOR = "coordinator"

TASK_CHECK_ORDER = "AI检查订单"
TASK_CHECK_GOODS = "AI检查货物资料"
TASK_CHECK_DOC_BLOCKERS = "AI检查单证阻塞项"
TASK_DRAFT_DOCS = "AI生成单证草稿"
TASK_CHECK_PROFIT = "AI检查利润风险"
TASK_FILE_TEXT_INTAKE = "file_text_intake"

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
    elif task_template == TASK_FILE_TEXT_INTAKE:
        agents.append(AGENT_STRUCTURED_INTAKE)

    for source in sources or []:
        if source.source_type in {"excel", "pdf", "chat"}:
            _append_once(agents, AGENT_STRUCTURED_INTAKE)
        haystack = f"{source.name} {source.text}".lower()
        if source.source_type in {"pdf", "chat"} and _has_product_or_certificate_text(haystack):
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
        coordinator = coordinator_agent(outputs)
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
    for suggestion in response["suggestions"]:
        if suggestion.get("level") not in SUGGESTION_LEVEL_LABELS:
            raise ValueError("invalid suggestion level")
        if suggestion.get("level") == LEVEL_BLOCKING_RISK and not suggestion.get("sourceReferences"):
            raise ValueError("blocking-risk requires source references")
    for draft in response["drafts"]:
        if draft.get("targetType") in {"supplier", "consignee", "warehouse", "system_settings"}:
            raise ValueError("master-data drafts are forbidden")
        if draft.get("targetType") in {"order_status", "receiving_record", "loading_record"}:
            raise ValueError("protected target draft is forbidden")


def structured_intake_agent(sources: list[Source], *, prompt_version: str = "order-assistant-mvp-v1") -> dict[str, Any]:
    drafts: list[dict[str, Any]] = []
    review_needed: list[dict[str, Any]] = []
    for source in sources:
        if source.source_type != "excel" or not source.path:
            continue
        rows = [[str(value).strip() for value in row] for row in read_xlsx_rows(source.path) if any(row)]
        if not rows or rows[0] != CHINESE_GOODS_HEADERS:
            continue
        for row_number, row in enumerate(_dict_rows(rows), start=2):
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
            dims = _parse_dimensions(row["外箱尺寸(cm)"])
            values.update(dims)
            paid = _money_or_none(row["实际付款"])
            if paid is not None and quantity:
                values["purchase_unit_price"] = paid / quantity
                values["purchase_currency"] = "CNY"
            source_ref = _source_ref(source, row_number=row_number)
            if product_name:
                drafts.append(
                    {
                        "draftType": "goods_line",
                        "targetType": "goods_line",
                        "targetId": None,
                        "proposedValues": {key: value for key, value in values.items() if value not in (None, "")},
                        "originalValues": {},
                        "sourceReferences": [source_ref],
                        "confidence": 0.85,
                    }
                )
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


def coordinator_agent(agent_outputs: list[dict[str, Any]], *, prompt_version: str = "order-assistant-mvp-v1") -> dict[str, Any]:
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
    if status not in REVIEW_STATUS_LABELS:
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


def confirm_change_draft(
    conn: sqlite3.Connection,
    *,
    actor_role: str,
    change_draft_id: int,
    final_values: dict[str, Any] | None = None,
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


def list_order_assistant_items(conn: sqlite3.Connection, import_order_id: int) -> dict[str, list[dict[str, Any]]]:
    suggestions = [dict(row) for row in conn.execute("SELECT * FROM assistant_suggestions WHERE import_order_id = ? ORDER BY id DESC", (import_order_id,))]
    reviews = [dict(row) for row in conn.execute("SELECT * FROM review_requests WHERE import_order_id = ? ORDER BY id DESC", (import_order_id,))]
    drafts = [dict(row) for row in conn.execute("SELECT * FROM change_drafts WHERE import_order_id = ? ORDER BY id DESC", (import_order_id,))]
    runs = [dict(row) for row in conn.execute("SELECT * FROM assistant_runs WHERE import_order_id = ? ORDER BY id DESC", (import_order_id,))]
    return {"runs": runs, "suggestions": suggestions, "review_requests": reviews, "change_drafts": drafts}


def _run_agent(conn: sqlite3.Connection, agent_name: str, import_order_id: int, sources: list[Source], prompt_version: str, real_data_confirmed: bool) -> dict[str, Any]:
    deepseek_config = _deepseek_config(conn)
    if deepseek_config["api_key"] and not real_data_confirmed:
        raise PermissionError("external model send requires administrator confirmation")
    if deepseek_config["api_key"] and real_data_confirmed:
        return deepseek_agent(conn, agent_name, import_order_id, sources, prompt_version=prompt_version, deepseek_config=deepseek_config)
    if agent_name == AGENT_STRUCTURED_INTAKE:
        return structured_intake_agent(sources, prompt_version=prompt_version)
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
    response = call_deepseek_json(agent_name, payload, prompt_version=prompt_version, deepseek_config=deepseek_config or _deepseek_config(conn))
    validate_agent_response(response)
    return response


def call_deepseek_json(agent_name: str, payload: dict[str, Any], *, prompt_version: str, deepseek_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = deepseek_config or {}
    api_key = config.get("api_key") or os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for DeepSeek calls")
    model = config.get("model") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    endpoint = config.get("api_base") or os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/chat/completions")
    body = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
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
    output["usage"] = {
        "model": model,
        "promptVersion": prompt_version,
        "inputTokens": int(usage.get("prompt_tokens", output.get("usage", {}).get("inputTokens", 0)) or 0),
        "outputTokens": int(usage.get("completion_tokens", output.get("usage", {}).get("outputTokens", 0)) or 0),
        "runtimeMs": int((time.monotonic() - started) * 1000),
    }
    validate_agent_response(output)
    return output


def test_deepseek_connection(deepseek_config: dict[str, Any]) -> dict[str, Any]:
    api_key = deepseek_config.get("api_key", "")
    if not api_key:
        return {"ok": False, "message": "缺少 API Key"}
    model = deepseek_config.get("model") or "deepseek-chat"
    endpoint = deepseek_config.get("api_base") or "https://api.deepseek.com/chat/completions"
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
        return {"ok": False, "message": f"连接验证失败: {exc}", "model": model, "runtimeMs": int((time.monotonic() - started) * 1000)}


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
    if draft.get("draftType") == "goods_line":
        return f"候选货物项草稿：{proposed.get('cn_name') or proposed.get('customs_en_name') or '未命名货物'}"
    if draft.get("draftType") == "export_document":
        return f"候选单证草稿：{proposed.get('document_type', 'document')}"
    return f"候选变更草稿：{draft.get('draftType', 'unknown')}"


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
        "api_base": os.getenv("DEEPSEEK_API_BASE") or setting.get("api_base", "https://api.deepseek.com/chat/completions"),
        "timeout_seconds": os.getenv("DEEPSEEK_TIMEOUT_SECONDS") or setting.get("timeout_seconds", 30),
    }


def _source_context(source: Source) -> dict[str, Any]:
    context = source.__dict__.copy()
    if source.source_type == "excel" and source.path:
        context["rows"] = read_xlsx_rows(source.path)[:80]
    if source.source_type == "chat":
        context["text"] = source.text[:12000]
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

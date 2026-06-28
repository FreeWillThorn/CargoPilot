# Order Assistant MVP Module

## Scope

Provide one order-centered AI assistant for Admin Users. Every assistant task starts from a selected Import Order and may inspect that order's goods, files, document readiness, compliance risks, costs, and pasted business messages.

## Workflow

1. Admin User opens an Import Order or clicks a contextual AI button in a workflow section.
2. The system starts a background Assistant Run and keeps the current workflow page usable.
3. Router selects one or more specialist agents for the run.
4. Specialist agents return structured findings and draft candidates.
5. Coordinator merges, deduplicates, and turns useful findings into Assistant Suggestions and Review Requests.
6. Suggestions appear in the current section drawer and in the Order Assistant entry.
7. Admin User marks a suggestion as ignored, needs follow-up, or approved for draft creation.
8. Approved suggestions create Change Drafts.
9. Admin User confirms each Change Draft before it changes system data or turns a document draft into an official version.

## Entry Points

The main Order Assistant entry lives in the selected Import Order detail in `订单详情`. MVP should not add a separate left-navigation section for the assistant.

Contextual AI Action Buttons open a right-side drawer inside the current Workflow Section and save the same result back to the selected Import Order's Order Assistant entry.

## Assistant Runs

Each click starts a new Assistant Run for the selected Import Order and task type. The drawer should show an in-progress state until the run completes. Run statuses are queued, running, succeeded, and failed.

Repeated runs should not overwrite unresolved older suggestions. If a new run finds the same risk for the same Suggestion Target, merge it into the existing unresolved suggestion instead of showing duplicates.

If DeepSeek or another model call fails, mark the Assistant Run as failed and allow retry. Failed runs must not create partial suggestions or change existing order data.

If one Specialist Agent fails, the Coordinator may still summarize successful agents and show the failed agent in the run result. Router or Coordinator failure marks the whole Assistant Run as failed.

## Multi-Agent Workflow

MVP uses a fixed multi-agent workflow, not a general agent platform.

**Router**:
路由器. Reads the selected Workflow Section, AI Action Button, supplied files/text, and selected Import Order summary, then chooses the specialist agents needed for that run.

**Structured Intake Agent**:
结构化录入 Agent. Extracts proposed order, goods, package, cost, document, or message-derived data from uploaded Excel/PDF files and pasted chat records into goods-line drafts, finance drafts, or document-data drafts.

**Order Review Agent**:
订单检查 Agent. Checks order-level completeness and consistency in `订单详情`, including customer details, destination port, trade term, dates, and stage blockers.

**Goods Review Agent**:
货物资料检查 Agent. Checks Goods Lines in `货物详情` for missing or conflicting Customs English Name, HS Code, carton count, gross weight, CBM, Shipping Mark, Domestic Tracking Number, product, supplier, quantity, and package information.

**Compliance Risk Agent**:
合规/单证风险 Agent. Flags likely Compliance Requirements from product names, materials, categories, and provided documents, including wood products, food-contact goods, animal/plant-related goods, children's goods, and textiles.

**Document Draft Agent**:
单证草稿 Agent. Checks whether `海运单证` can generate Commercial Invoice and Packing List, then prepares drafts from confirmed data.

**Profit Risk Agent**:
利润风险 Agent. Checks `成本利润` for abnormal margin, missing fee categories, low quote, and missing exchange rate.

**Coordinator**:
汇总器. Combines specialist outputs into Assistant Suggestions, merges duplicate risks, rejects unsupported blocking risks, and prepares Review Requests. The Coordinator does not apply changes.

The Router may call multiple specialist agents in one Assistant Run. For example, an upload containing an Excel file plus pasted chat records may route to Structured Intake, Compliance Risk, and Profit Risk, then Coordinator summarizes the result.

MVP routing uses task templates plus source rules. Task templates come from the clicked AI Action Button and current Workflow Section; source rules come from supplied Excel, PDF, pasted chat records, or existing selected-order data. The routing table stays in code for MVP.

Default task templates:

- `AI检查订单`: Order Review Agent, Goods Review Agent, and Compliance Risk Agent.
- `AI检查货物资料`: Goods Review Agent and Compliance Risk Agent.
- `AI检查单证阻塞项`: Compliance Risk Agent and Document Draft Agent.
- `AI生成单证草稿`: Document Draft Agent.
- `AI检查利润风险`: Profit Risk Agent.
- File/text intake from the Order Assistant drawer: Structured Intake Agent plus any risk agents selected by source rules.

Default source rules:

- Excel source: add Structured Intake Agent.
- PDF source: add Structured Intake Agent and Compliance Risk Agent when product or certificate text is present.
- Pasted chat records: add Structured Intake Agent and Compliance Risk Agent.
- Finance-like amounts or quote terms in any source: add Profit Risk Agent.
- Document-like fields in any source: add Document Draft Agent.

## Agent Contracts

All agents receive the same run envelope: selected Import Order summary, allowed Assistant Source Scope, source references, task template, prompt version, and current user role. Agents must return structured JSON only.

## Agent Isolation Standard

Agents exist to enforce isolation, not to create a generic AI platform:

- Complex-task decomposition: Router splits a user action into the smallest useful specialist agents, and Coordinator recombines only their outputs.
- Permission isolation: every agent runs under the current Admin User's assistant permission and may not elevate access, bypass confirmation, or expose Warehouse User access.
- Context isolation: every agent receives only the selected Import Order context and the files/text supplied to the current Assistant Run.
- Tool isolation: each agent may use only the tool types listed in its contract; Router and Coordinator do not call DeepSeek.
- Output format isolation: each specialist agent returns only the shared structured JSON envelope; UI and downstream code never parse free-form prose for business actions.
- Responsibility boundary isolation: each agent owns one business concern and must not perform another agent's job or apply Change Drafts.

Shared output envelope:

- `suggestions[]`: Assistant Suggestions with level, target, source references, and reason.
- `drafts[]`: Change Draft candidates with draft type, target, proposed values, source references, and confidence.
- `reviewNeededFields[]`: low-confidence or missing fields that need administrator checking.
- `usage`: model name, prompt version, input token count, output token count, and runtime.

Allowed tool types:

- Existing CargoPilot read functions for the selected Import Order and its child business data.
- Existing Excel/PDF/text extraction helpers for files supplied to the current Assistant Run.
- Existing calculation and document helpers for validation and draft preparation.
- DeepSeek JSON model call after required external-send confirmation.
- Code constants for MVP compliance keywords and fixed profit rules.

Forbidden for every agent:

- Reading unrelated Import Orders or global files outside Assistant Source Scope.
- Applying system changes directly.
- Creating Supplier, Customer/Consignee, Warehouse, or Company/System master data.
- Changing Order Status, warehouse receiving results, or loading records.
- Returning business actions as free-form prose that the UI must parse.

**Router / 路由器**:
Uses task templates and source rules only. It may inspect source metadata, selected Workflow Section, clicked AI Action Button, and selected Import Order summary. It outputs the selected agent list and routing reason. It must not call the model or create suggestions.
Business goal: run the smallest useful agent set for the user's current order task so the assistant is fast, relevant, and not noisy.

**Structured Intake Agent / 结构化录入 Agent**:
Uses Excel/PDF/text extraction tools and optional DeepSeek JSON extraction. It outputs goods-line, finance, and document-data draft candidates plus Review-Needed Fields. It must not apply imports or create master data.
Business goal: turn messy supplier/customer materials into reviewable system drafts without forcing the Admin User to retype complete goods, cost, or document data.

**Order Review Agent / 订单检查 Agent**:
Uses selected Import Order data and stage blocker rules. It outputs order-level suggestions and Review Requests. It must not inspect unrelated orders, change Order Status, or create Goods Line drafts.
Business goal: help the Admin User see whether the selected Import Order has enough order-level information to keep the shipment workflow moving.

**Goods Review Agent / 货物资料检查 Agent**:
Uses Goods Lines under the selected Import Order and package/calculation helpers. It outputs Goods-Line-targeted suggestions and Review-Needed Fields for product, package, logistics, and customs-facing data. It must not create receiving records or final logistics updates.
Business goal: catch missing or inconsistent Goods Line data before it breaks receiving, container planning, customs-facing documents, or shipment review.

**Compliance Risk Agent / 合规/单证风险 Agent**:
Uses Goods Lines, provided product/category/material text, uploaded files, and MVP compliance keyword constants. It outputs Compliance Requirement suggestions only. It must not generate certificates, claim legal certainty, or mark compliance files approved.
Business goal: surface likely certificate or compliance-document risks early enough for the Admin User to request files before customs or shipment deadlines.

**Document Draft Agent / 单证草稿 Agent**:
Uses confirmed selected-order data and existing document-generation/readiness helpers. It outputs Commercial Invoice and Packing List draft candidates plus document blocker suggestions. It must not create official documents or overwrite Customs English Name without Admin User confirmation.
Business goal: reduce manual invoice and packing-list preparation while making missing final-document data visible before the Admin User generates official versions.

**Profit Risk Agent / 利润风险 Agent**:
Uses selected-order finance data, cost lines, customer charges, sales values, exchange rates, and fixed MVP profit rules. It outputs profit-risk suggestions and optional finance draft candidates. It must not create accounting entries, payment records, or configurable threshold changes.
Business goal: catch underpriced orders, missing common fees, and margin problems before the Admin User quotes, confirms, or ships at an unexpected loss.

**Coordinator / 汇总器**:
Uses specialist outputs only. It deduplicates, merges by risk type, rejects unsupported blocking risks, creates Review Requests, and records failed specialist agents. It must not invent new findings beyond agent outputs or apply Change Drafts.
Business goal: turn multiple specialist findings into a short, actionable Review Request list that an Admin User can approve, ignore, or follow up without reading raw agent output.

## Suggestion Levels

- `suggestion`: helpful improvement or missing information hint.
- `review-needed`: likely issue that requires administrator checking.
- `blocking-risk`: likely blocker for shipment, customs clearance, documents, or profit review.

UI labels:

- `suggestion`: 建议
- `review-needed`: 需核查
- `blocking-risk`: 阻塞风险

## Review And Draft Statuses

Review Request statuses:

- `pending_review`: 待核查
- `approved_for_draft`: 已批准生成草稿
- `ignored`: 已忽略
- `needs_followup`: 需跟进

Change Draft statuses:

- `draft`: 待确认草稿
- `confirmed`: 已确认
- `rejected`: 已拒绝
- `failed`: 应用失败

The confirmation UI should show original value, AI suggested value, and administrator final value. Admin Users may edit the final value before confirming.

## Suggestion Targets

An Assistant Suggestion may target the whole selected Import Order or one or more Goods Lines under that order. Goods-level risks such as likely quarantine requirements, missing HS Code, package mismatch, or questionable Customs English Name should point to the affected Goods Lines.

The default assistant view shows unresolved suggestions first, then recently handled suggestions from the last 30 days. Full history remains available through audit records.

Every Assistant Suggestion should show a source reference such as the affected Goods Line, uploaded file, pasted chat excerpt, or system-data summary. A suggestion without a source reference cannot be marked as `blocking-risk`.

Administrator handling notes are optional on suggestions and Change Drafts, not required.

## Change Draft Scope

Allowed in MVP:

- Fill or correct order and goods information.
- Create proposed Compliance Requirements.
- Create Commercial Invoice and Packing List drafts.
- Create proposed costs, customer charges, or finance-risk notes.

Not allowed in MVP:

- Change Order Status.
- Change warehouse receiving results.
- Change loading records.
- Apply any draft without Admin User confirmation.

If a Change Draft is rejected or cannot be applied, keep the audit record permanently. The normal Order Assistant entry only needs to show unresolved items and handled items from the last 30 days.

## Source Scope

The assistant may read only the selected Import Order's linked data plus files or text supplied in the current assistant task. It does not scan unrelated orders or all system files in the MVP.

For demo usage, prefer masked sample data. If an Admin User sends real customer, supplier, pricing, or document data to DeepSeek or another external model API, the UI must show a confirmation step and audit that confirmation.

## Assistant Tasks

**Order Check**:
Reviews the selected Import Order for missing dates, missing customer details, inconsistent destination/trade information, and workflow blockers.

**Goods Information Check**:
Reviews Goods Lines in `货物详情` for missing Customs English Name, HS Code, package data, Shipping Mark, Domestic Tracking Number, suspicious product category, or inconsistent carton/weight/CBM values.

Low-confidence extracted fields should not become proposed field values automatically. They should be grouped as review-needed fields for Admin Users to confirm or enter manually.

**Compliance Risk Check**:
Flags likely Compliance Requirements from product names or categories, such as quarantine/animal-plant inspection, food-contact documents, wood packaging concerns, children's goods, textiles, leather, or customer-specific requirements. The MVP uses model judgment plus a small keyword hint list; Admin Users decide.

**Document Drafting**:
Prepares Commercial Invoice and Packing List drafts from confirmed order and goods data. AI output never becomes an official document until an Admin User confirms it.

The assistant may suggest changes to Customs English Name, but it must not overwrite the existing value. An Admin User must confirm the suggestion before the value becomes the Goods Line's Customs English Name and before official documents use it.

**Profit Risk Check**:
Reviews `成本利润` for abnormal margin, missing cost categories, missing customer charge lines, quote below expected cost, and exchange-rate gaps.

MVP profit risk rules are fixed: gross margin below target, costs exist with no customer charges, and missing common fee categories for sea freight, warehouse, or document/compliance fees. Configurable thresholds belong to Phase 2.

**Structured Intake**:
Extracts proposed order, goods, package, cost, or document data from uploaded Excel/PDF files and pasted chat records into Change Drafts tied to the selected Import Order.

Structured Intake must not create Supplier, Customer/Consignee, Warehouse, or Company/System master-data drafts in the MVP. If source material refers to missing master data, the assistant should suggest that an Admin User add or select it in `基础资料`.

Structured Intake may create multiple proposed Goods Line drafts from one source, but each line remains a Change Draft that an Admin User confirms before it appears in `货物详情`.

## Review Request Grouping

Coordinator groups Review Requests by risk type by default, with affected Goods Lines listed inside each group. This keeps the administrator focused on the issue first while still making the affected goods clear.

## Upload And Text Entry

Excel, PDF, and pasted chat-record intake lives in the Order Assistant drawer and the selected Import Order's Order Assistant entry in `订单详情`. Contextual AI Action Buttons may attach files or text from the current Workflow Section, but every source remains bound to the selected Import Order.

## Model Output

Model calls must return structured JSON that the backend validates before creating Assistant Suggestions, Review Requests, or Change Drafts. The UI must not parse natural-language paragraphs to decide business actions.

Use a small shared response envelope across agents: `suggestions[]`, `drafts[]`, `reviewNeededFields[]`, and `usage`. Agent-specific data is distinguished by draft type and suggestion type.

Issue 53 defines the shared response envelope. Issue 55 defines Router, specialist agent, and Coordinator contract tests.

Prompts live in code or configuration in the MVP. Store the prompt version on the Assistant Run; do not build a prompt management UI.

The first compliance keyword hint list lives as code constants in the MVP.

DeepSeek configuration uses environment variables: `DEEPSEEK_API_KEY` and `DEEPSEEK_MODEL`.

If no model key is configured, the assistant may run in demo mode with fixed sample results for UI development and demos.

## Audit

Store the assistant task type, selected Import Order, input summary, source file/message references, output suggestions, administrator decision, and resulting Change Draft status. Do not store full model reasoning text.

Store model usage for each external call: model name, run time, input token count, output token count, and selected Import Order. MVP does not need an AI cost dashboard.

## Permissions

Only Admin Users can run Order Assistant tasks, approve Review Requests, create Change Drafts, or confirm AI-generated document drafts. Warehouse Users do not access the assistant in the MVP.

## Test Focus

- Assistant task always requires a selected Import Order.
- Contextual AI buttons create suggestions for the correct Import Order.
- Suggestion levels render correctly.
- Review Request approval creates Change Drafts without applying them.
- Confirmed Change Drafts update the intended workflow section data.
- AI-generated document drafts cannot become official without Admin User confirmation.

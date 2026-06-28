# AI资料收集箱 MVP Module

## Scope

`AI资料收集箱` is a dedicated Admin-only Workflow Section for collecting messy order-related materials and turning them into reviewable, order-bound actions.

Every run is still tied to one selected Import Order. The section is separate from `订单详情`; it does not live inside the selected order summary.

## Workflow

1. Admin User opens `AI资料收集箱`.
2. Admin User selects an Import Order from the section dropdown.
3. Admin User uploads or pastes one or more sources:
   - Supplier Excel
   - Supplier email body
   - Chat records
   - PDF documents
   - Waybills
   - customs declarations
   - verified customs copies
   - Warehouse receiving notes
4. Admin User clicks `AI处理资料`.
5. Router selects intake and risk agents based on source types.
6. Specialist agents extract structured candidates and findings.
7. Coordinator matches extracted goods to existing Goods Lines under the selected Import Order.
8. UI shows source recognition, extracted goods, system matching, problems, suggested operations, and supplier message draft.
9. Admin User chooses:
   - `确认导入`
   - `生成供应商消息`
   - `忽略`
10. Confirmed working-source fields are imported in grouped batches by operation type.
11. Authoritative final document fields create document-data import applications after confirmation.
12. Conflicts and low-confidence matches remain as Review Requests.

## Entry Points

MVP has one primary entry point: the left-navigation Workflow Section `AI资料收集箱`.

Contextual AI buttons inside `订单详情`, `货物详情`, `海运单证`, and `成本利润` are no longer the primary MVP workflow. They may be removed or reduced to links into `AI资料收集箱` with the current Import Order preselected.

## Page Layout

Top controls:

- Import Order selector
- source upload controls
- text areas for supplier email, chat records, and warehouse receiving notes
- `AI处理资料` button

Result cards:

- `识别结果`
- `提取到的货物`
- `系统匹配`
- `发现问题`
- `建议操作`
- `供应商消息草稿`

Decision area:

- `确认导入`
- `生成供应商消息`
- `忽略`

Operational history:

- Run history
- Review Requests
- grouped Change Drafts

The UI must preserve the current anchor/scroll position after any form submission or button action.

## Assistant Runs

Each `AI处理资料` click creates an Assistant Run for the selected Import Order and source bundle.

Run statuses remain:

- queued / 排队中
- running / 运行中
- succeeded / 已完成
- failed / 失败

If DeepSeek is not explicitly selected for a run, the system may run demo/local deterministic extraction. Configured model credentials alone must not make an unconfirmed run fail.

Failed runs may be retried. Retry should preserve the current page anchor.

## Review Requests

Review Requests represent conflicts, missing important data, low-confidence matching, or working-source fields that need Admin User judgment.

MVP statuses:

- `pending_review`: 待核查
- `approved_for_draft`: 已批准生成草稿
- `ignored`: 已忽略

Remove `needs_followup` and the `需跟进` UI action from this workflow.

Review Request UI actions:

- approve for draft or grouped import
- ignore

If follow-up is needed, the assistant should express it through the Supplier Message Draft instead of a separate Review Request status.

## Grouped Change Drafts

Same-category data items should be grouped and confirmed in one action.

Examples:

- Import working-source package fields for `A001` and `A002`.
- Import authoritative customs declaration rows into document-data drafts.
- Import domestic tracking numbers for all matched Goods Lines in the source.
- Prepare one supplier message draft for all missing HS Code / Customs English Name questions.

Do not require one confirmation per Goods Line when the operation type, source, and risk level are the same.

## Business-Language Draft Display

Normal UI must not show raw JSON.

Each draft should show:

- operation name, such as `导入箱规和毛重`
- affected Goods Lines
- current system value
- extracted source value
- source reference
- safe/unsafe reason
- result after confirmation

Raw JSON may remain available only for developer diagnostics, not as the default Admin User view.

## Multi-Agent Workflow

MVP keeps fixed multi-agent routing. This is still not a general agent platform.

**Router / 路由器**:
Uses selected Import Order, source types, and action `AI处理资料` to select agents.

**Structured Intake Agent / 结构化录入 Agent**:
Extracts goods, package, tracking, document, cost, and message data from supplied sources.

**Goods Review Agent / 货物资料检查 Agent**:
Compares extracted values against existing Goods Lines under the selected Import Order.

**Compliance Risk Agent / 合规/单证风险 Agent**:
Flags product or document risks from source text and matched goods.

**Document Draft Agent / 单证草稿 Agent**:
Identifies document data that can help Commercial Invoice or Packing List preparation, but does not create official documents.

**Authoritative Document Agent / 权威单证 Agent**:
Extracts final document-facing data from Waybill, customs declaration, verified customs copy, carrier documents, or freight forwarder documents. It prepares first-class grouped Document Data Drafts after Admin User confirmation. It must not assume customs rows map one-to-one to purchase Goods Lines.

**Profit Risk Agent / 利润风险 Agent**:
Runs only when sources contain pricing, cost, quote, or payment signals.

**Supplier Message Agent / 供应商消息 Agent**:
Prepares a business-language supplier message draft from missing fields, conflicts, and requested confirmations.

**Coordinator / 汇总器**:
Merges extracted data, matches it to system Goods Lines, groups safe updates, creates Review Requests, and prepares supplier message drafts.

## Matching Rules

The system should match source rows to existing Goods Lines using the best available business identifiers:

- customer item number
- SKU/model
- product name
- product URL
- supplier reference
- existing Goods Line notes

Low-confidence matches must not be batch imported. They become Review Requests.

## Source Authority Policy

Every recognized field should be extracted and shown. Import behavior depends on source authority.

Working-source batch import is allowed only when:

- selected Import Order is explicit
- Goods Line match is confident
- source value is clear
- field is low-risk
- no material conflict exists

Working-source batch fields:

- carton dimensions
- carton gross weight
- CBM
- shipping mark
- domestic tracking number
- package notes

Working-source review fields:

- conflicting carton count
- ambiguous quantity
- HS Code
- Customs English Name
- product identity
- supplier identity
- prices/costs/charges
- compliance status
- order/logistics/receiving/loading status

Authoritative final documents create document-data import applications after Admin User confirmation. They do not directly overwrite purchase Goods Lines. Examples:

- Waybill
- customs declaration
- verified customs copy
- carrier or freight forwarder final document

Authoritative final document fields may include:

- HS Code
- Customs English Name
- carton count
- quantity
- gross weight
- net weight
- CBM or package volume
- package count and package type
- shipping marks
- document-facing shipper/consignee data

If authoritative final documents conflict with current purchase Goods Lines or estimates, show a discrepancy report. The confirmed import should create document-facing data for future intelligent document generation, while Goods Line discrepancies remain checks or Review Requests.

## Document Data Drafts

AI资料收集箱 owns the first implementation of Document Data Drafts.

Document Data Drafts should store:

- selected Import Order
- source document type and file reference
- document-facing rows from authoritative documents
- totals such as package count, gross weight, net weight, CBM, and quantity
- HS Code and Customs English Name when present
- shipper, consignee, vessel, voyage, and transport identifiers when present
- source confidence and discrepancy notes
- confirmation status and Admin User decision

Confirmed Document Data Drafts are reusable inputs for the future intelligent document generation module. The MVP does not generate the final invoice or packing list from them yet.

## Permissions

Only Admin Users can use `AI资料收集箱`, run AI processing, confirm safe imports, generate supplier message drafts, or ignore findings.

Warehouse Users may provide receiving notes elsewhere, but they do not access this assistant MVP.

## Audit

Store:

- selected Import Order
- source types and source names
- Assistant Run status
- model usage
- extracted summary
- matching result
- Review Requests
- grouped Change Draft decisions
- supplier message draft generation
- Admin User decisions

Do not store full model reasoning text.

## Test Focus

- Page is a dedicated Workflow Section, not embedded in `订单详情`.
- Import Order selector is required.
- Mixed source submission creates one Assistant Run.
- Extracted goods are matched to selected-order Goods Lines only.
- Working-source same-category updates can be confirmed as a batch.
- Authoritative final document fields create document-data import applications after confirmation.
- Conflicts and low-confidence matches become Review Requests.
- `需跟进` is not shown.
- Change Drafts render in business language, not raw JSON.
- Button actions preserve anchor/scroll position.

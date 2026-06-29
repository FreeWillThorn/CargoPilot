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
   - natural-language order operation commands
4. Admin User clicks `AI处理资料`.
5. Router selects intake and risk agents based on source types.
6. Specialist agents extract structured candidates and findings.
7. Coordinator matches extracted goods to existing Goods Lines under the selected Import Order.
8. UI shows source recognition, extracted goods or recognized order operations, system matching, problems, and suggested operations.
9. Admin User chooses:
   - `确认导入`
   - `忽略`
10. Confirmed working-source fields are imported in grouped batches by operation type.
11. Authoritative final document fields can update the Customs Goods Version after confirmation.
12. Natural-language order operations enter the same `识别数据录入` lane first; approving them creates grouped Change Drafts.
13. Conflicts and low-confidence matches remain as Review Requests.

## Entry Points

MVP has one primary entry point: the left-navigation Workflow Section `AI资料收集箱`.

Contextual AI buttons inside `订单详情`, `货物详情`, `海运单证`, and `成本利润` are no longer the primary MVP workflow. They may be removed or reduced to links into `AI资料收集箱` with the current Import Order preselected.

## Page Layout

Top controls:

- Import Order selector
- source upload controls
- one text area for supplier email, chat records, warehouse receiving notes, document text, or natural-language order operation commands
- `AI处理资料` button

Operational lanes:

- `运行记录`
- `识别数据录入`
- `待确认变更草稿`

Decision area:

- `确认导入`
- `忽略`

Operational history:

- Run history
- recognized data entry / Review Requests
- grouped Change Drafts

The UI must preserve the current anchor/scroll position after any form submission or button action.

## Assistant Runs

Each `AI处理资料` click creates an Assistant Run for the selected Import Order and source bundle.

Run statuses remain:

- queued / 排队中
- running / 运行中
- succeeded / 已完成
- failed / 失败

DeepSeek is selected by default for AI资料收集箱 runs, but deterministic local tasks still run locally. For example, fixed-template Excel parsing must not be sent to DeepSeek just because the checkbox is selected. If the Admin User unchecks DeepSeek, the system uses local/demo handling where available.

PDF parsing first tries embedded text extraction. If a PDF is image-only, the system falls back to local OCR using Poppler `pdftoppm` and `tesseract`; missing OCR tools should produce a clear parse failure instead of a silent success.

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

If follow-up is needed, the assistant should express it as business-language review text, not a separate Review Request status.

## Grouped Change Drafts

Same-category data items should be grouped and confirmed in one action.

Examples:

- Import working-source package fields for `A001` and `A002`.
- Import authoritative customs declaration rows into the Customs Goods Version.
- Import domestic tracking numbers for all matched Goods Lines in the source.
- Update all selected-order Goods Lines to one logistics status from a natural-language command.

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

**Command Intent Agent / 指令理解 Agent**:
Recognizes a supported natural-language order operation and turns it into a grouped draft candidate. MVP supports selected-order Goods Line logistics-status batch updates, selected-order full Goods Line deletion, selected-order field updates, and selected-order deletion. Examples: `把这个订单里的货物全部改成已到货状态`, `把订单中的货物信息全部删除`, `把订单目的港改成 Rotterdam`, and `删除这个订单`. It must not directly write system data.

**Goods Review Agent / 货物资料检查 Agent**:
Compares extracted values against existing Goods Lines under the selected Import Order.

**Compliance Risk Agent / 合规/单证风险 Agent**:
Flags product or document risks from source text and matched goods.

**Document Draft Agent / 单证草稿 Agent**:
Identifies document data that can help Commercial Invoice or Packing List preparation, but does not create official documents.

**Authoritative Document Agent / 权威单证 Agent**:
Extracts final document-facing data from Waybill, customs declaration, verified customs copy, carrier documents, or freight forwarder documents. It prepares grouped import applications for the Customs Goods Version after Admin User confirmation. It must not assume customs rows map one-to-one to purchase Goods Lines.

**Profit Risk Agent / 利润风险 Agent**:
Runs only when sources contain pricing, cost, quote, or payment signals.

**Coordinator / 汇总器**:
Merges extracted data and recognized commands, matches them to system Goods Lines, groups safe updates, and creates Review Requests / grouped Change Draft candidates.

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

Authoritative final documents can update the Customs Goods Version after Admin User confirmation. They do not directly overwrite purchase Goods Lines. Examples:

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

If authoritative final documents conflict with current purchase Goods Lines or estimates, show a discrepancy report. The confirmed import should update the Customs Goods Version, while Goods Line discrepancies remain checks or Review Requests.

## Goods Data Versions

AI资料收集箱 owns the first implementation of two goods-data versions for one selected Import Order.

**Entered Goods Version / 录入版本**:

- the real purchase and operations data already represented by Goods Lines
- detailed rows such as white cups and black cups
- used for purchasing, warehouse receiving, cost tracking, and operational checks

**Customs Goods Version / 报关版本**:

- selected Import Order
- source document type and file reference
- compressed customs/document-facing rows from authoritative documents
- totals such as package count, gross weight, net weight, CBM, and quantity
- HS Code and Customs English Name when present
- shipper, consignee, vessel, voyage, and transport identifiers when present
- source confidence and discrepancy notes
- confirmation status and Admin User decision

The Customs Goods Version is reusable input for the future intelligent document generation module. The MVP does not generate the final invoice or packing list from it yet.

## Permissions

Only Admin Users can use `AI资料收集箱`, run AI processing, confirm safe imports, approve recognized order operations, or ignore findings.

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
- Admin User decisions

Do not store full model reasoning text.

## Test Focus

- Page is a dedicated Workflow Section, not embedded in `订单详情`.
- Import Order selector is required.
- Mixed source submission creates one Assistant Run.
- Extracted goods are matched to selected-order Goods Lines only.
- Working-source same-category updates can be confirmed as a batch.
- Authoritative final document fields can update the Customs Goods Version after confirmation.
- Conflicts and low-confidence matches become Review Requests.
- `需跟进` is not shown.
- Change Drafts render in business language, not raw JSON.
- Button actions preserve anchor/scroll position.

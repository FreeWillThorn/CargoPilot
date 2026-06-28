# CargoPilot AI资料收集箱 PRD

## Goal

Add a dedicated **AI资料收集箱** Workflow Section where Admin Users collect supplier, chat, PDF, and warehouse notes for one selected Import Order, ask AI to structure the material, review matches and risks, then apply only safe grouped updates after confirmation.

This replaces the previous embedded `订单助手` entry inside `订单详情`. The assistant is no longer primarily an order-review panel; it is an order-bound intake inbox for messy business materials.

## Product Shape

The MVP adds a left-navigation Workflow Section named `AI资料收集箱`.

The section always starts with an Import Order selector. Nothing runs without a selected Import Order.

Primary inputs:

- Supplier Excel / `供应商 Excel`
- Supplier email body / `供应商邮件正文`
- Chat records / `聊天记录`
- PDF documents / `PDF 单证`
- Warehouse receiving notes / `仓库收货备注`

Primary action:

- `AI处理资料`

Primary result areas:

- Source recognition: what the material appears to be and which Import Order it likely belongs to.
- Extracted goods and document data.
- System matching against existing Goods Lines under the selected Import Order.
- Problems and conflicts.
- Suggested operations.
- Supplier message draft.
- Assistant run history.
- Review Requests.
- grouped Change Drafts shown in business language.

Primary decision buttons:

- `确认导入安全字段`
- `生成供应商消息`
- `忽略`

Do not show raw JSON in the normal business UI.

## Example Result

After an Admin User selects order `CP-2026-001`, uploads supplier Excel, and pastes supplier email text, the result may say:

> 这是供应商 ABC 发来的装箱资料，可能对应订单 CP-2026-001。

Extracted goods:

1. `A001`, 100 cartons, 12 units per carton, carton size `50*40*30cm`, carton gross weight `18kg`
2. `A002`, 80 cartons, 6 units per carton, carton size `60*45*35cm`, carton gross weight `22kg`

System matching:

- `A001` exists and can update safe package fields.
- `A002` exists and can update safe package fields.
- `A003` exists in the system but does not appear in this source.

Problems:

- `A001` carton count differs: system says 120 cartons, source says 100 cartons.
- `A002` is missing HS Code.
- Customs English Name is not provided.

Suggested operations:

1. Do not directly update `A001` carton count; ask an Admin User to confirm.
2. Import safe package fields for `A001` and `A002`.
3. Ask supplier for HS Code and Customs English Name.

Supplier message draft:

> 您好，资料已收到。请再确认 A001 的最终箱数，并补充 A002 的 HS Code 和英文报关品名，谢谢。

## MVP Boundary

Build first:

- Dedicated `AI资料收集箱` Workflow Section.
- Import Order selector at the top of the section.
- Upload/paste intake for supplier Excel, supplier email body, chat records, PDF documents, and warehouse receiving notes.
- `AI处理资料` run lifecycle with run history.
- Structured intake and matching against existing Goods Lines in the selected Import Order.
- Review Requests without the `需跟进` action.
- Grouped Change Drafts by business operation type.
- Batch confirmation for same-category low-risk updates, especially safe package fields.
- Supplier message draft generation from the identified issues.
- Business-language draft display showing affected goods, old values, proposed values, source, and risk label.
- Anchor/scroll preservation after every button or form action.
- DeepSeek-backed extraction after explicit external-send confirmation, with demo mode still available.

Skip for MVP:

- Direct AI application of unsafe or conflicting fields.
- Raw JSON display as the normal confirmation UI.
- Per-Goods-Line confirmation for same-category safe field batches.
- Supplier/customer-facing message sending; only generate copyable message drafts.
- AI changes to Order Status, warehouse receiving results, loading records, master data, or official documents.
- General-purpose chat assistant behavior.

## Safe Field Policy

Safe fields are low-risk factual fields that can be batch imported after Admin User confirmation when the source is clear and the Goods Line match is confident.

MVP safe fields:

- carton dimensions
- carton gross weight
- calculated or supplied CBM
- shipping mark
- domestic tracking number
- package notes

Unsafe fields require Review Request handling and must not be included in safe batch import:

- carton count when it conflicts with system data
- quantity and units per carton when ambiguous or conflicting
- HS Code
- Customs English Name
- product identity
- supplier identity
- prices, costs, and charges
- compliance status
- order status and logistics/receiving status

## Module Index

- [AI资料收集箱 MVP](./modules/order-assistant.md)
- [AI资料收集箱 Phase 2](./modules/order-assistant-phase-2.md)
- [AI资料收集箱 Development Plan](./order-assistant-development-plan.md)

## Phase Signal

MVP is complete when an Admin User can select one Import Order, submit mixed source materials, receive matched extracted results, batch confirm safe updates, generate a supplier message draft, and keep unresolved conflicts as Review Requests.

Phase 2 starts after real usage shows repeated intake patterns that need better source parsers, richer supplier-message workflows, or wider safe-field automation.

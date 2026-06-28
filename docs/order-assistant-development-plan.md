# AI资料收集箱 Development Plan

## Goal

Refactor the current embedded Order Assistant into a dedicated `AI资料收集箱` Workflow Section for order-bound document and message intake.

The previous 53-62 issues delivered the first assistant foundation. The next work should not keep polishing the embedded `订单详情` panel; it should move the product shape to the new section and reuse only the useful data contract, run lifecycle, DeepSeek validation, and agent helpers.

## Context Pack For All New Issues

- `docs/prd.md`
- `docs/prd-order-assistant.md`
- `docs/modules/order-assistant.md`
- `docs/modules/user-interface.md`
- `CONTEXT.md`
- `docs/adr/0003-fixed-multi-agent-order-assistant.md`

## Phase 1 Refactor Modules

- Dedicated `AI资料收集箱` Workflow Section.
- Import Order selector.
- Source intake form for Supplier Excel, supplier email body, chat records, PDF documents, Waybills, customs declarations, verified customs copies, and warehouse receiving notes.
- `AI处理资料` run action.
- Source recognition result.
- extracted goods result.
- system matching result.
- problems and suggested operations.
- supplier message draft.
- run history.
- Review Requests without `需跟进`.
- grouped safe-field Change Drafts.
- first-class Document Data Draft storage, confirmation, and audit.
- business-language draft display.
- anchor/scroll preservation after every form action.

## Refactor Issues

1. **AI资料收集箱 Section Shell**
   Add the dedicated navigation section, selected Import Order dropdown, source-input form, and `AI处理资料` action. Remove the embedded Order Assistant panel from `订单详情` or replace it with a link to the new section with the order preselected.

2. **Source Bundle Intake**
   Store one source bundle per Assistant Run with source type labels for supplier Excel, supplier email body, chat records, PDF documents, Waybills, customs declarations, verified customs copies, and warehouse receiving notes. Keep all sources bound to the selected Import Order.

3. **Intake Result Summary**
   Render source recognition, extracted goods, system matching, problems, suggested operations, and supplier message draft as business-language cards.

4. **Goods Matching And Missing Existing Lines**
   Match extracted rows to existing Goods Lines and explicitly surface existing system Goods Lines that were not present in the source, such as `A003 系统中存在，但本次资料没有出现`.

5. **Safe Batch Import**
   Group same-category safe field updates into one confirm action. Safe batch import should update fields such as carton dimensions, carton gross weight, CBM, shipping mark, domestic tracking number, and package notes when matches are confident and values do not conflict.

6. **Authoritative Final Document Intake**
   Parse Waybill, customs declaration, and verified customs copy sources as authoritative final documents. Extract all document-facing fields, show discrepancies against purchase Goods Lines and estimates, and allow one grouped confirmation to create Document Data Drafts. Do not overwrite Goods Lines.

7. **Document Data Draft Storage**
   Add first-class storage and UI for Document Data Drafts, including document type, source file, document-facing rows, totals, HS Code, Customs English Name, shipper/consignee data, transport identifiers, confirmation status, and audit trail. Reserve these records as inputs for the future intelligent document generation module.

8. **Unsafe Field Review Requests**
   Route conflicts and unsafe fields to Review Requests. Remove the `需跟进` button and related `needs_followup` UI path. Use supplier message draft for follow-up wording.

9. **Business-Language Draft Display**
   Replace raw JSON draft display with operation names, affected goods, old values, proposed values, source references, and risk labels.

10. **Supplier Message Draft**
   Generate one supplier message draft from missing fields and conflicts. The MVP creates a copyable message; it does not send email, SMS, or chat messages.

11. **Anchor Preservation**
   Ensure every button action returns to the same section anchor and does not jump the browser back to the top or initial anchor.

12. **Regression Cleanup**
    Update tests and docs to remove the old embedded-order-assistant assumptions and verify `AI资料收集箱` as the primary workflow.

## Keep From Existing Foundation

- Assistant Run lifecycle.
- selected Import Order scoping.
- DeepSeek configuration and validation.
- demo/local fallback.
- Specialist Agent isolation standard.
- Review Request and Change Draft audit tables, with status cleanup.

## Remove Or Downgrade

- Embedded `订单详情` Order Assistant panel.
- `需跟进` Review Request button and related active workflow.
- Raw JSON draft cards in normal UI.
- Per-line confirmation for same-category safe field batches.

## Development Rule

Keep each refactor issue small. Do not rebuild a generic AI workspace. The new section is an intake inbox for one selected Import Order, not an open-ended chat system.

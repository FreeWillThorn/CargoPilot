# Issue 05: Fixed-Header Excel Import and Export

## Context Pack

- `docs/prd.md`
- `docs/modules/excel.md`
- `docs/modules/orders-goods.md`
- `docs/modules/finance.md`

## Goal

Implement fixed-header Excel import and useful Excel exports.

## Scope

- Customer purchase-list import.
- Supplier package/logistics import.
- Import validation and row errors.
- Export Import Orders, Goods Lines, dashboard filtered results, cost/profit reports, warehouse receiving lists, and loading lists.

## Acceptance Criteria

- Customer purchase-list template accepts the documented fixed headers.
- Supplier package/logistics template accepts the documented fixed headers.
- Invalid headers or rows produce clear errors.
- Supplier package/logistics import can update existing Goods Lines.
- Exports produce usable Excel files.
- Small runnable checks cover header validation, import row mapping, update behavior, and export shape.

## Out of Scope

- Smart arbitrary spreadsheet recognition.
- OCR.

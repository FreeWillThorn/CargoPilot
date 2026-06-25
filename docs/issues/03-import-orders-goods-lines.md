# Issue 03: Import Orders and Goods Lines

## Context Pack

- `docs/prd.md`
- `docs/modules/orders-goods.md`
- `docs/modules/master-data.md`
- `CONTEXT.md`
- `docs/adr/0001-import-order-as-system-center.md`

## Goal

Implement Import Order and Goods Line creation/editing.

## Scope

- System-generated editable order number.
- Import Order fields and links to Consignee, Receiving Warehouse, and Port Warehouse.
- Goods Line fields.
- Incomplete Goods Line creation.
- Goods Line split rule support.
- Basic list/detail UI with tabs and grouped forms.

## Acceptance Criteria

- Admin User can create and edit Import Orders.
- Admin User can add incomplete Goods Lines.
- Goods Lines include product URL, customer item number, Customs English Name, HS code, package placeholders, pricing placeholders, and statuses.
- Import Order list shows only decision fields, not every column.
- Import Order detail uses tabs.
- Goods Line edit UI groups fields by basic information, pricing, packaging, logistics, compliance, and files.
- Small runnable checks cover order number generation and incomplete Goods Line creation.

## Out of Scope

- Excel import.
- Warehouse receiving workflow.
- Document generation.

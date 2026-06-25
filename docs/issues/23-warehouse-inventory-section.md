# Issue 23: Warehouse Inventory Section

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/warehouse-receiving.md`

## Goal

Build 仓库盘点 as a Warehouse-selected page for inbound and received goods.

## Scope

- Top Context Selector chooses a Warehouse.
- Show selected Warehouse contact/address/notes.
- Show all inbound or received Goods Lines for that Warehouse, including owning Import Order, Domestic Tracking Number, Shipping Mark, received cartons, package condition, and Arrival Exception.
- Receiving, photo metadata, exception, and exception-resolution actions open in modal or side drawer.
- Warehouse User can perform receiving workflow here.

## Acceptance Criteria

- Warehouse User can select a Warehouse and record receiving without seeing finance, customer pricing, documents, Supplier management, Consignee management, or settings.
- Rows clearly show which Import Order each received/inbound Goods Line belongs to.
- Receiving records update Goods Logistics Status.
- UI labels are Chinese-first.

## Out of Scope

- Barcode/QR scanning.
- Mobile native app.

# Issue 23: Warehouse Inventory Section

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/warehouse-receiving.md`

## Goal

Build 仓库盘点 as a Warehouse-selected page for inbound and received goods.

## Scope

- Top Context Selector chooses a Warehouse.
- Warehouse is required; status and date are secondary filters.
- Status filters are 待入库, 已入库, 异常, and 全部.
- Show selected Warehouse contact/address/notes.
- Show all inbound or received Goods Lines for that Warehouse, including owning Import Order, Domestic Tracking Number, Shipping Mark, received cartons, package condition, and Arrival Exception.
- 待入库 includes Goods Lines assigned to the selected Receiving Warehouse even before Receiving Records exist.
- Receiving, photo metadata, exception, and exception-resolution actions open in modal or side drawer.
- Warehouse User can perform receiving workflow here.

## Acceptance Criteria

- Warehouse User can select a Warehouse and record receiving without seeing finance, customer pricing, documents, Supplier management, Consignee management, or settings.
- Warehouse inventory can be narrowed by status and date without changing the selected Warehouse context.
- 待入库 rows can come from the Import Order's assigned Receiving Warehouse plus Domestic Tracking Number and Shipping Mark data.
- Rows clearly show which Import Order each received/inbound Goods Line belongs to.
- Receiving records update Goods Logistics Status.
- UI labels are Chinese-first.

## Out of Scope

- Barcode/QR scanning.
- Mobile native app.

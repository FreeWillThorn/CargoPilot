# Import Orders and Goods Lines Module

## Scope

Create Import Orders and Goods Lines, support incomplete data, and keep product/package/source fields structured.

## Browser Organization

The browser UI exposes an **订单详情** Workflow Section. This section lists all Import Orders with their current Order Status, progress, Consignee, destination port, current logistics point, blockers, and key dates.

Selecting one Import Order shows that order's detail and order-level actions. Goods Lines are managed from **货物详情** using the selected Import Order context, not from 订单详情.

The 订单详情 section owns:

- New/edit/cancel Import Order actions.
- Manual Order Status changes by Admin Users.
- 收货客户 CRUD needed for order editing.
- Basic order review.

The 货物详情 section owns Goods Line creation, editing, deletion, logistics status updates, and Goods Line Excel import.

Add/edit actions for Import Orders and Goods Lines should open as a modal or side drawer from their owning workflow section.

Order lists sort by created/updated time descending, with exceptions and near-loading orders pinned above normal orders.

The system may suggest Order Status and Order Stage Progress from Goods Line states, but Admin Users can manually update Order Status. Manual status changes must be recorded in modification history.

## Import Order

Fields: system-generated order number, Consignee, Receiving Warehouse, Port Warehouse, trade term, origin country/port, destination country/port, status, expected/actual received/loading/departure/arrival dates, purchase currency, sales currency, internal notes.

Rules:
- System generates order numbers such as `CP-2026-0001`; Admin Users can edit them.
- No customer order/reference number in the MVP.

## Goods Line

Split rule: Supplier + product model/specification + Customs English Name + packaging method.

Fields include customer item number, product URL, Chinese name, customer English name, Customs English Name, SKU/model, category, HS code, quantity, unit, package data, Shipping Mark, logistics/compliance status, target markup, sales price/currency, purchase price/currency, notes.

Rules:
- Goods Lines may start incomplete.
- One Goods Line can have multiple Domestic Tracking Numbers.
- One Goods Line can be split across multiple Containers.
- Browser tables show Goods Line summary columns only. Dense Goods Line fields are grouped in forms using Chinese operational labels, not raw database field names.

## Test Focus

- Order number generation.
- Goods Line split rule behavior.
- Incomplete Goods Line creation.
- Permission boundary for Warehouse User edits.
- Browser tests should prove Goods Lines are managed from 货物详情 under a selected Import Order and not as a peer top-level navigation module.

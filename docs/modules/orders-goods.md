# Import Orders and Goods Lines Module

## Scope

Create Import Orders and Goods Lines, support incomplete data, and keep product/package/source fields structured.

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

## Test Focus

- Order number generation.
- Goods Line split rule behavior.
- Incomplete Goods Line creation.
- Permission boundary for Warehouse User edits.

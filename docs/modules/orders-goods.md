# Import Orders and Goods Lines Module

## Scope

Create Import Orders and Goods Lines, support incomplete data, and keep product/package/source fields structured.

## Browser Organization

The browser UI starts from **订单管理**. This page lists all Import Orders with their current Order Status, progress, Consignee, destination port, current logistics point, blockers, and key dates.

Opening one Import Order shows that order's child work. Goods Lines are managed from the Import Order detail page, not from a top-level Goods Line CRUD page.

Import Order detail tabs:

1. 订单概览
2. 货物明细
3. 采购与Excel
4. 报价利润
5. 仓库收货
6. 装柜运输
7. 单证文件
8. 修改历史

Add/edit actions for Import Orders and Goods Lines should open as a modal or side drawer from the current page.

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
- Browser tests should prove Goods Lines are nested under Import Orders and not exposed as a peer CRUD module.

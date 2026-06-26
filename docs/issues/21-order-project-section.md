# Issue 21: Order Details Section

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/orders-goods.md`
- `docs/adr/0001-import-order-as-system-center.md`

## Goal

Build 订单详情 as the main place to manage Import Orders and 收货客户.

## Scope

- Show all Import Orders with status, progress, Consignee, destination port, current logistics point, blockers, and key dates.
- Default order-list columns are 订单号, 收货客户, 目的港, 订单状态, 订单进度, 当前物流点, 预计装柜日, 异常数, 缺资料数.
- Sort by created/updated time descending, with exceptions and near-loading orders pinned above normal orders.
- Default view shows all Import Orders plus the most recent Import Order summary below the list.
- When an Import Order is selected, the summary switches to that selected order.
- Order summary fields are 订单号, 客户, 目的港, 收货仓, 港口仓, 贸易条款, 预计装柜日, 总货物项, 总箱数, 总体积, 总毛重, and 成本利润入口.
- Selecting an Import Order shows that order's detail and Goods Line table.
- Add/edit/cancel Import Order actions open in modal or side drawer.
- Admin can manually update Order Status; system-suggested status/progress remains visible.
- Add/edit/delete Goods Line actions open in modal or side drawer under the selected Import Order.
- Customer purchase-list import and supplier package/logistics import are launched from the selected Import Order context.
- Use Chinese labels and summary columns only.

## Acceptance Criteria

- Goods Lines are not a top-level destination.
- Opening 订单详情 does not automatically enter edit mode.
- Admin can create and edit Import Orders from 订单详情.
- Admin can select an Import Order and see only that order's Goods Lines.
- Dense fields are edited in grouped forms, not displayed as raw database columns.
- Warehouse User can view order and goods status but cannot edit prices, profit, suppliers, consignees, or system settings.
- Manual Order Status changes are recorded in modification history.

## Out of Scope

- Visual redesign polish.
- Browser-native file upload.

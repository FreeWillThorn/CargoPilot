# Issue 21: Order Project Section

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/orders-goods.md`
- `docs/adr/0001-import-order-as-system-center.md`

## Goal

Build 订单项目 as the main place to manage Import Orders and their Goods Lines.

## Scope

- Show all Import Orders with status, progress, Consignee, destination port, current logistics point, blockers, and key dates.
- Selecting an Import Order shows that order's detail and Goods Line table.
- Add/edit/cancel Import Order actions open in modal or side drawer.
- Add/edit/delete Goods Line actions open in modal or side drawer under the selected Import Order.
- Customer purchase-list import and supplier package/logistics import are launched from the selected Import Order context.
- Use Chinese labels and summary columns only.

## Acceptance Criteria

- Goods Lines are not a top-level destination.
- Admin can create an Import Order and Goods Lines from 订单项目.
- Admin can select an Import Order and see only that order's Goods Lines.
- Dense fields are edited in grouped forms, not displayed as raw database columns.
- Warehouse User can view order and goods status but cannot edit prices, profit, suppliers, consignees, or system settings.

## Out of Scope

- Visual redesign polish.
- Browser-native file upload.

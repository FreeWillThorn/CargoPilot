# Issue 42: Order Progress Logic

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/dashboard.md`
- `docs/modules/orders-goods.md`
- `docs/issues/38-simplify-goods-logistics-statuses.md`

## Category

Bug.

## Goal

Rework order progress percentage so it reflects Goods Line logistics progress clearly and consistently.

## Scope

- Use the simplified Goods Logistics Status rank from Issue 38.
- MVP formula:
  - Assign each Goods Line a rank from 0 to 7.
  - Order progress = average goods-line rank / max rank * 100.
  - Exception rows count at their previous known rank if available; otherwise count as current rank 0 and add exception indicator.
- Suggested rank:
  - 未下单 0
  - 已下单/备货中 1
  - 国内运输中 2
  - 已到收货仓 3
  - 已入港仓 4
  - 已装箱 5
  - 海运中 6
  - 已完成/到港完成 7, if implemented; otherwise cap at 海运中 and mark order status separately.
- Display should remain a single percentage in Dashboard and 订单项目.
- Manual Order Status remains editable but does not override the computed Goods Line progress.

## Acceptance Criteria

- Progress changes predictably when Goods Line statuses change.
- An order with all Goods Lines at the same status shows that status's rank percentage.
- Mixed Goods Lines show the average percentage.
- Tests cover empty order, single Goods Line, and mixed Goods Lines.

## Out of Scope

- Weighted progress by cartons/CBM.

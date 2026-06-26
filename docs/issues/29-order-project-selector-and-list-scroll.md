# Issue 29: Order Project Selector and List Scroll

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/orders-goods.md`
- `docs/issues/21-order-project-section.md`

## Category

Bug.

## Goal

订单项目 should use an Import Order selector for the current order summary and keep the order table compact when many orders exist.

## Scope

- Add an Import Order dropdown at the top of 订单项目.
- Changing the dropdown selects the order and refreshes:
  - 订单摘要
  - 货物明细
  - order-level actions
- Keep the full order table as a list of orders, but cap its visible height to about four rows with vertical scrolling.
- Preserve existing order row links as a secondary way to select an order.

## Acceptance Criteria

- No selected order means default to the latest/highest-priority order.
- Selecting an order from the dropdown updates the summary and goods table.
- The order table does not grow endlessly; more than four rows scroll inside the table area.
- Tests cover dropdown selection for a specific order.

## Out of Scope

- Pagination.
- Full order table redesign.

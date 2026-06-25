# Issue 25: Cost Profit Section

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/finance.md`
- `docs/modules/orders-goods.md`

## Goal

Build 成本利润 as an Import Order-selected quote, cost, charge, and profit workflow.

## Scope

- Top Context Selector chooses an Import Order.
- Show Goods Line quote fields, Target Markup, sales unit price, purchase unit price, and currencies for the selected Import Order.
- Show order-level and Goods-Line-level cost and charge lines.
- Add/edit cost and charge lines from modal or side drawer actions.
- Show profit summary for the selected Import Order.
- Export cost/profit report.

## Acceptance Criteria

- Admin can select an Import Order and see only that order's quote/profit information.
- Admin can adjust Target Markup and sales price for Goods Lines under the selected Import Order.
- Admin can add order-level and Goods-Line-level costs/charges.
- Warehouse User cannot access 成本利润.
- UI labels are Chinese-first.

## Out of Scope

- Payment tracking.
- Tax invoices.
- Full accounting ledger.

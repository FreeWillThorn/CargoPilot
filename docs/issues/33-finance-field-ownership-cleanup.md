# Issue 33: Finance Field Ownership Cleanup

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/finance.md`
- `docs/modules/orders-goods.md`
- `docs/modules/containers.md`
- `docs/issues/25-cost-profit-section.md`

## Category

Bug.

## Goal

Move price entry to the workflow where the price naturally belongs, and keep 成本利润 focused on review and adjustment.

## Scope

- Product purchase/sales price belongs with 新增货物项 / 编辑货物项.
- Container/ocean freight price belongs with 新增集装箱 in 海运单证.
- 成本利润 should still allow review and adjustment, but it should not be the first place users enter these prices.
- Minimal implementation:
  - Ensure Goods Line create/edit includes product price fields with Chinese labels.
  - Add container/ocean cost input to container creation if supported by existing finance model.
  - If no existing container-cost field exists, create a finance line tied to the Import Order when container price is submitted.

## Acceptance Criteria

- Adding/editing a Goods Line can capture product purchase price, sales price, and currency.
- Adding a Container can capture ocean/container cost and create a corresponding cost record.
- 成本利润 shows the resulting costs/prices in the selected order summary.
- Tests cover one container cost flowing into 成本利润.

## Out of Scope

- Supplier/customer payment tracking.
- Full accounting ledger.

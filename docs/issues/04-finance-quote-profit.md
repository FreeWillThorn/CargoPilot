# Issue 04: Finance, Quote, Target Markup, Profit

## Context Pack

- `docs/prd.md`
- `docs/modules/finance.md`
- `docs/modules/orders-goods.md`
- `CONTEXT.md`

## Goal

Implement internal cost, quote, markup, and profit estimation.

## Scope

- Cost lines attached to Import Orders or Goods Lines.
- Customer charge lines.
- Target Markup or target margin on Goods Lines.
- Manual exchange rate entry.
- Profit totals.

## Acceptance Criteria

- Admin User can add purchase costs, domestic logistics, warehouse fees, inspection/certificate fees, document/customs fees, sea freight, and other fees.
- Admin User can add customer product sales, freight/service charges, and other charges.
- Goods Line quote can use Target Markup and can be manually adjusted.
- Profit calculation converts costs/charges using recorded currency and exchange rate.
- Small runnable checks cover markup calculation, manual adjustment, and total profit.

## Out of Scope

- Accounting ledger.
- Payment collection.
- Supplier payment status.
- Tax invoice workflow.

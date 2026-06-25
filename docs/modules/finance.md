# Finance Module

## Scope

Track internal costs, customer charges, target markup, quote adjustments, and estimated profit.

## Decisions

- This is not an accounting system.
- No supplier payment tracking.
- No customer payment or credit tracking.
- Costs attach to Import Orders or Goods Lines.
- Customer charges include product sales, freight/service charges, and other pass-through charges.
- Goods Lines support Target Markup or target margin.
- Purchase currency, sales currency, and exchange rate are recorded manually.

## Test Focus

- Profit totals from converted costs and charges.
- Order-level versus Goods-Line-level costs.
- Manual adjustment lines.
- Target Markup quote calculation.

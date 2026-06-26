# Finance Module

## Scope

Track internal costs, customer charges, target markup, quote adjustments, and estimated profit.

## Decisions

- This is not an accounting system.
- No supplier payment tracking.
- No customer payment or credit tracking.
- Costs attach to Import Orders or Goods Lines.
- Customer charges include product sales, freight/service charges, and other pass-through charges.
- Customer received/charged entries record 入账金额 and 入账日期 as lightweight finance lines, not a full accounting ledger.
- Goods Lines support Target Markup or target margin.
- Purchase currency, sales currency, and exchange rate are recorded manually.
- Profit base currency is the Import Order customer sales currency; if missing, use the system default sales currency.

## Test Focus

- Profit totals from converted costs and charges.
- Display totals in 成本明细 and 客户收费明细.
- Display the selected order's summed Goods Line sales value in 货物项报价表.
- Order-level versus Goods-Line-level costs.
- Manual adjustment lines.
- Target Markup quote calculation.

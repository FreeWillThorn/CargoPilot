# Calculations and Blockers Module

## Scope

Calculate package totals and enforce stage-specific missing-field warnings/blockers.

## Calculations

- CBM = carton length cm * carton width cm * carton height cm / 1,000,000 * carton count.
- Gross weight = carton gross weight kg * carton count.
- Both can be manually overridden.

## Stage Requirements

Purchasing: Supplier, Chinese product name, quantity, and purchase/sales price or Target Markup.

Container estimate: carton count, units per carton, carton length/width/height, carton gross weight.

Receiving: Domestic Tracking Number, Shipping Mark, received carton count. Photos recommended but not mandatory.

Final documents: Customs English Name, HS code, quantity, carton count, gross weight, CBM, sales unit price, currency, Consignee document information.

Loading complete: container type, container number, seal number, loading date. Photos recommended but not mandatory.

## Test Focus

- CBM and gross-weight calculations.
- Manual overrides.
- Warning versus blocker behavior by stage.

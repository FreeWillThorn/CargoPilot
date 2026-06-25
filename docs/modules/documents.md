# Export Documents Module

## Scope

Generate English Commercial Invoice and Packing List from confirmed Import Order and Goods Line data.

## Decisions

- Generate Commercial Invoice and Packing List only.
- Certificates of origin, inspection certificates, test reports, and similar compliance files are uploaded and tracked, not generated.
- Use Customs English Name.
- Final generation requires Consignee, destination port, Customs English Name, HS code, quantity, carton count, gross weight, CBM, sales unit price, and currency.
- Generated documents are versioned V1, V2, V3.
- Invoice uses customer sales price, not Supplier purchase price.
- Packing List summarizes by Goods Line in MVP, not Domestic Tracking Number.
- Seller information comes from System Settings.
- Numbers default from Import Order number and version, such as `CP-2026-0001-INV-V1`.
- Export Excel and PDF. Word export is out of scope.

## Commercial Invoice Content

Seller, buyer/Consignee, invoice number, date, trade term, origin port, destination port, Customs English Name, quantity, unit, sales unit price, line amount, currency, total amount.

## Packing List Content

Seller, buyer/Consignee, packing list number, date, origin port, destination port, Customs English Name, carton count, quantity, gross weight, CBM, Shipping Mark, totals.

## Test Focus

- Required-field blocker.
- Document numbering.
- Version creation.
- Invoice totals.
- Packing List totals.
- Excel/PDF output smoke checks.

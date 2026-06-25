# Warehouse Receiving Module

## Scope

Allow Warehouse Users to record arrivals, package condition, photos, notes, exceptions, and logistics status updates.

## Decisions

- Warehouse page supports search by Import Order, Domestic Tracking Number, or Shipping Mark.
- 仓库盘点 has separate Receiving Warehouse and Port Warehouse views.
- Receiving Warehouse view focuses on supplier arrivals.
- Port Warehouse view focuses on goods moved to port and waiting for container loading.
- One Goods Line can have multiple Domestic Tracking Numbers.
- Each Domestic Tracking Number can produce one or more Receiving Records.
- Receiving Record stores received carton count, package condition, photos, notes, and Arrival Exception Type.
- Arrival Exception types: missing cartons, extra cartons, damaged cartons, unclear Shipping Mark, wrong goods, dimension/weight mismatch.
- Arrival Exception is not terminal; after resolution the Goods Line returns to the correct logistics status.
- Barcode/QR scanning is out of scope for MVP.

## Test Focus

- Partial arrivals.
- Exception creation and resolution.
- Warehouse User permission limits.
- Receiving photo/file attachment metadata.

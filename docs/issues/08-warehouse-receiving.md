# Issue 08: Warehouse Receiving and Exceptions

## Context Pack

- `docs/prd.md`
- `docs/modules/warehouse-receiving.md`
- `docs/modules/orders-goods.md`
- `docs/modules/foundation.md`

## Goal

Implement warehouse receiving for Warehouse Users.

## Scope

- Search by Import Order, Domestic Tracking Number, or Shipping Mark.
- Receiving Records.
- Partial arrivals.
- Arrival Exceptions.
- Receiving photos/files.
- Warehouse User permission restrictions.

## Acceptance Criteria

- Warehouse User can view Import Orders and Goods Lines needed for receiving.
- Warehouse User can record received carton count, package condition, notes, photos, Arrival Exception Type, and Goods Logistics Status.
- Warehouse User cannot edit prices, profit, Consignee, Supplier, Export Documents, or system settings.
- A Goods Line can receive multiple Domestic Tracking Numbers and Receiving Records.
- Arrival Exception can be resolved and Goods Line returned to a normal logistics status.
- Small runnable checks cover partial receiving, exception behavior, and permissions.

## Out of Scope

- Barcode/QR scanning.
- Mobile native app.

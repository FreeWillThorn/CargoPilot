# Issue 02: Master Data

## Context Pack

- `docs/prd.md`
- `docs/modules/master-data.md`
- `docs/issues/01-foundation.md`
- `CONTEXT.md`

## Goal

Implement Supplier, Consignee, and Warehouse management.

## Scope

- Supplier CRUD with store URL and duplicate-name warning.
- Consignee CRUD with one address and default order values.
- Warehouse CRUD with Receiving Warehouse and Port Warehouse types.
- Admin-only management screens.

## Acceptance Criteria

- Suppliers store one primary contact, store URL, usual categories, and notes.
- Consignees store one primary contact, one address, tax ID, default destination port, default trade term, and default sales currency.
- Warehouses are typed as Receiving Warehouse or Port Warehouse.
- Duplicate Supplier names warn but do not block.
- Small runnable checks cover creation, update, and default Consignee values.

## Out of Scope

- Supplier scoring.
- Supplier payment status.
- Customer credit/payment status.
- Multiple contacts.

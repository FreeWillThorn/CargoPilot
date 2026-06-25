# Issue 16: Warehouse Receiving Screen

## Context Pack

- `docs/prd.md`
- `docs/modules/warehouse-receiving.md`
- `docs/issues/08-warehouse-receiving.md`
- `docs/issues/12-web-app-shell.md`

## Goal

Build the restricted warehouse receiving workflow.

## Scope

- Search by Import Order, Domestic Tracking Number, or Shipping Mark.
- Receiving form.
- Arrival Exception selection.
- Exception resolution.
- Receiving photo upload metadata and local file save.

## Acceptance Criteria

- Warehouse User can perform receiving workflow in the browser.
- Warehouse User cannot access price, profit, customer, supplier, document, or settings screens.
- Receiving records update Goods Logistics Status.
- Tests cover search, record creation, exception, and restricted navigation.

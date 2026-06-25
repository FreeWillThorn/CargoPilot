# Issue 22: Goods Tracking Section

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/dashboard.md`
- `docs/modules/warehouse-receiving.md`

## Goal

Build 货物跟踪 as an Import Order-selected tracking page for Goods Lines.

## Scope

- Top Context Selector chooses an Import Order.
- Show all Goods Lines under the selected Import Order with logistics status, Supplier, Domestic Tracking Numbers, Shipping Mark, blockers, and Arrival Exception.
- Support filters for Goods Logistics Status, exception-only, and missing-data-only.
- Status update and exception actions open in modal or side drawer.
- Dashboard blocker links open 货物跟踪 with the relevant Import Order preselected.

## Acceptance Criteria

- Normal 货物跟踪 view is scoped to one selected Import Order.
- Cross-order exception filters are allowed only as triage shortcuts and must still show the owning Import Order.
- Editing a Goods Line keeps or restores the selected Import Order context.
- UI labels are Chinese-first.

## Out of Scope

- Carrier API integrations.
- BI charts.

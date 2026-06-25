# Issue 07: Simple Dashboard

## Context Pack

- `docs/prd.md`
- `docs/modules/dashboard.md`
- `docs/modules/calculations-blockers.md`
- `docs/modules/orders-goods.md`

## Goal

Build the first dashboard for active Import Orders and blockers.

## Scope

- Import Order list with decision fields.
- Order Status colors.
- Order Stage Progress by Goods Line count.
- Exception badge.
- Missing-data and exception counts.
- Basic filters.

## Acceptance Criteria

- Dashboard shows active Import Orders with order number, Consignee, destination port, status, progress, expected loading date, exception count, and missing-data count.
- Progress uses Goods Line count.
- Status colors match the PRD.
- Exception badge appears when any Goods Line has an Arrival Exception.
- Missing-data and exception counts open relevant filtered lists.
- Small runnable checks cover progress and status display data.

## Out of Scope

- Advanced analytics.
- Goods Line global tracking dashboard.
- External notifications.

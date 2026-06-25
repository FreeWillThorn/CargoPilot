# Issue 09: Full Dashboard and Goods Logistics Tracking

## Context Pack

- `docs/prd.md`
- `docs/modules/dashboard.md`
- `docs/modules/warehouse-receiving.md`
- `docs/issues/07-simple-dashboard.md`

## Goal

Expand the dashboard and add the Goods Logistics Tracking dashboard.

## Scope

- Current logistics concentration point.
- Global search.
- Goods Line tracking dashboard across all Import Orders.
- In-app reminder list/badges.
- Filters for status, supplier, consignee, order, exception type, missing fields, and expected loading date.

## Acceptance Criteria

- Global search finds order number, Consignee, Supplier, product name, Domestic Tracking Number, Shipping Mark, and container number.
- Goods Line tracking dashboard shows delayed, incomplete, or blocked goods across Import Orders.
- In-app reminders include goods not fully received 3 days before expected loading date, missing document fields, and missing/unapproved compliance.
- Small runnable checks cover search/filter data and reminder generation.

## Out of Scope

- BI charts.
- Email/SMS/WeChat notifications.

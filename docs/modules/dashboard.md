# Dashboard Module

## Scope

Show active Import Orders, progress, risks, search, filters, and Goods Line tracking.

Dashboard and Tracking are triage screens, not primary CRUD modules. When a user clicks an Import Order, blocker count, exception, or Goods Line result, the destination should keep or restore the relevant Import Order context.

## Decisions

- Import Order list shows order number, Consignee, destination port, Order Status, Order Stage Progress, expected loading date, exception count, and missing-data count.
- Current logistics concentration point is calculated from Goods Line statuses.
- Order Stage Progress is calculated by Goods Line count.
- Exception is a badge, not an Order Status.
- Status colors: Draft gray, Purchasing blue, Receiving orange, Received cyan, Moving to port purple, At port warehouse indigo, Loaded green, At sea navy, Arrived teal, Completed dark gray, Cancelled red.
- Dashboard blocker counts are clickable.
- Goods Line tracking may list Goods Lines across orders for exception and delay triage, but edit actions return users to the owning Import Order detail page.
- Global search supports order number, Consignee, Supplier, product name, Domestic Tracking Number, Shipping Mark, and container number.
- In-app reminders only; no email/SMS/WeChat in MVP.

## Test Focus

- Progress calculation.
- Status colors.
- Search and filters.
- Clickable blocker counts.
- Reminder list content.

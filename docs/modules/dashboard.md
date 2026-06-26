# Dashboard Module

## Scope

Show active Import Orders, progress, risks, search, filters, and Goods Line tracking.

Dashboard is the overview section. 货物详情 is a Workflow Section with an Import Order Context Selector. When a user clicks an Import Order, blocker count, exception, or Goods Line result, the destination should open the relevant Workflow Section with the owning Import Order preselected.

## Decisions

- Import Order list shows order number, Consignee, destination port, Order Status, Order Stage Progress, expected loading date, exception count, and missing-data count.
- Current logistics concentration point is calculated from Goods Line statuses.
- Order Stage Progress is calculated by Goods Line count.
- Exception is a badge, not an Order Status.
- Status colors: Draft gray, Purchasing blue, Receiving orange, Received cyan, Moving to port purple, At port warehouse indigo, Loaded green, At sea navy, Arrived teal, Completed dark gray, Cancelled red.
- Dashboard blocker counts are clickable.
- 货物详情 normally shows an Import Order selector plus the Goods Lines under that selected Import Order. Arrival exception workflows belong to 仓库盘点.
- MVP delay risk means expected loading date is within the reminder lead window and the Goods Line is not yet at the Receiving Warehouse, has missing required data, or has an Arrival Exception.
- Global search supports order number, Consignee, Supplier, product name, Domestic Tracking Number, Shipping Mark, and container number.
- In-app reminders only; no email/SMS/WeChat in MVP.

## Test Focus

- Progress calculation.
- Status colors.
- Search and filters.
- Clickable blocker counts.
- Reminder list content.

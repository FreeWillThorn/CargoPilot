# Issue 28: Dashboard Localization and Drilldowns

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/dashboard.md`

## Category

Bug.

## Goal

Dashboard text must be Chinese-first and key summary cards must help users jump to the affected orders.

## Scope

- Translate visible Order Status values on Dashboard to Chinese.
- Translate reminder messages and missing/exception labels to Chinese.
- Make Dashboard summary cards actionable:
  - 活跃订单 opens the order list with active/default context.
  - 异常 opens 货物跟踪 with cross-order exception filter.
  - 缺少资料 opens 货物跟踪 with cross-order missing-data filter.
- Keep existing Dashboard table links to selected-order tracking.

## Acceptance Criteria

- Dashboard no longer shows raw statuses like `purchasing`, `receiving`, `loaded`.
- Reminders are readable Chinese business text.
- 活跃订单, 异常, 缺少资料 are clickable or contain clear links that navigate to the relevant section.
- Tests cover Chinese status rendering and one summary-card drilldown URL.

## Out of Scope

- Dashboard chart redesign.

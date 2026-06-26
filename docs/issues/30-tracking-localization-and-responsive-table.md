# Issue 30: Tracking Localization and Responsive Table

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/dashboard.md`
- `docs/issues/22-goods-tracking-section.md`

## Category

Bug.

## Goal

货物跟踪 should show Chinese logistics statuses and fit smaller browser widths without breaking the page.

## Scope

- Translate Goods Logistics Status values in filters and rows.
- Keep submitted form values as internal enum values.
- Add a minimal responsive wrapper for the tracking table so wide columns scroll horizontally instead of overflowing.
- Use the same status-label helper where Dashboard/order pages also display Goods Logistics Status if touched.

## Acceptance Criteria

- Users see labels such as 未下单, 已下单, 国内运输中, 已入仓, 异常.
- Status filters still submit the correct internal value.
- The 货物跟踪 table remains usable on narrow widths via horizontal scrolling.
- Tests cover one Chinese logistics status label.

## Out of Scope

- Carrier API integration.
- Mobile-native layout.

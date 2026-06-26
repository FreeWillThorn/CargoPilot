# Issue 39: Remove Missing Data From Tracking

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/dashboard.md`
- `docs/issues/22-goods-tracking-section.md`

## Category

Bug.

## Goal

货物跟踪 should no longer show missing-document-data controls or columns.

## Scope

- Remove 缺资料 column from 货物跟踪.
- Remove 只看缺失资料 filter from 货物跟踪.
- Remove missing-data-only behavior from `/tracking?missing_fields=1`.
- Dashboard may still show 缺少资料, but its links should go to the relevant order/document area instead of relying on tracking missing-data UI.
- Keep exception and delay triage in 货物跟踪.

## Acceptance Criteria

- 货物跟踪 page has no 缺资料 column or missing-data checkbox/filter.
- `/tracking?missing_fields=1` does not show a special missing-data-only view.
- Dashboard missing-data links still navigate somewhere useful, preferably 订单项目 or 海运单证 with the order selected.
- Tests cover absence of 缺资料 on 货物跟踪.

## Out of Scope

- Removing missing-data calculations from Dashboard.

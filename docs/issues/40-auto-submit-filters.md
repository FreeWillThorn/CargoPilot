# Issue 40: Auto Submit Filters

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/issues/20-section-navigation-shell.md`

## Category

Bug.

## Goal

Filter buttons should be removed; selecting a dropdown/filter value should refresh the section immediately.

## Scope

- Remove visible 筛选 / 查看 / 切换订单 buttons from filter bars.
- Add `onchange="this.form.submit()"` to section context selectors and filter selects.
- Keep text search inputs as explicit submit/search where appropriate.
- Apply to:
  - Dashboard status filter
  - 订单项目 current order selector
  - 货物跟踪 order/status filters
  - 仓库盘点 warehouse/status/date where practical
  - 海运单证 order selector
  - 成本利润 order selector
- Do not add a frontend framework.

## Acceptance Criteria

- Dropdown change submits the form immediately.
- No standalone 筛选/查看/切换订单 buttons remain for dropdown-only filter bars.
- Text search still works.
- Tests cover one auto-submit selector and absence of one removed filter button.

## Out of Scope

- Debounced live search.

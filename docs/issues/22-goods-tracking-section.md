# Issue 22: Goods Details Section

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/dashboard.md`
- `docs/modules/warehouse-receiving.md`

## Goal

Build 货物详情 as an Import Order-selected detail page for Goods Lines.

## Scope

- Top Context Selector chooses an Import Order.
- Context Selector includes 全部订单 for cross-order exception and delay triage.
- 全部订单 shows only exception, delayed, or missing-data Goods Lines.
- Show all Goods Lines under the selected Import Order with logistics status, Supplier, Domestic Tracking Numbers, Shipping Mark, blockers, and Arrival Exception.
- Default columns are 货物项, 供应商, SKU/型号, 数量, 箱数, 麦头, 国内物流单号, 货物物流状态, 异常, 缺资料.
- Support filters for Goods Logistics Status, exception-only, and missing-data-only.
- Delay risk uses the MVP rule: expected loading date within reminder lead window plus not received, missing required data, or Arrival Exception.
- Status update and exception actions open in modal or side drawer.
- Dashboard blocker links open 货物详情 with the relevant Import Order preselected.

## Acceptance Criteria

- Normal 货物详情 view is scoped to one selected Import Order.
- Cross-order exception filters and 全部订单 are allowed only as triage shortcuts and must still show the owning Import Order.
- 全部订单 does not show every normal Goods Line.
- Delay-risk rows are included in 全部订单 triage.
- Editing a Goods Line keeps or restores the selected Import Order context.
- UI labels are Chinese-first.

## Out of Scope

- Carrier API integrations.
- BI charts.

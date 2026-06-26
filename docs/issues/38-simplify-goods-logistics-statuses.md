# Issue 38: Simplify Goods Logistics Statuses

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/orders-goods.md`
- `docs/modules/warehouse-receiving.md`
- `docs/issues/30-tracking-localization-and-responsive-table.md`

## Category

Enhancement.

## Goal

Reduce Goods Logistics Status choices to a smaller operational set.

## Scope

- Replace the UI-facing Goods Logistics Status choices with:
  - 未下单 (`not_ordered`)
  - 已下单/备货中 (`ordered`)
  - 国内运输中 (`domestic_shipped`)
  - 已到收货仓 (`received_at_warehouse`)
  - 已入港仓 (`moved_to_port_warehouse`)
  - 已装箱 (`loaded`)
  - 海运中 (`at_sea`)
  - 异常 (`exception`)
- Map legacy/internal statuses in display:
  - `supplier_preparing` displays/submits as `ordered`.
  - `checked` displays/submits as `received_at_warehouse`.
- New dropdowns should not offer the removed statuses.
- Existing data with removed statuses should remain readable and be normalized on next status update.

## Acceptance Criteria

- Goods Logistics Status dropdowns show only the simplified set.
- Existing `supplier_preparing` rows display as 已下单/备货中.
- Existing `checked` rows display as 已到收货仓.
- Updating either legacy status stores one of the simplified values.
- Tests cover removed statuses not appearing in the dropdown.

## Out of Scope

- Database migration for historical values.

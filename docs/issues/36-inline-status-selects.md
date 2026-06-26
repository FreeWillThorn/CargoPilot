# Issue 36: Inline Status Selects

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/orders-goods.md`
- `docs/issues/29-order-project-selector-and-list-scroll.md`
- `docs/issues/30-tracking-localization-and-responsive-table.md`

## Category

Bug.

## Goal

Order Status and Goods Logistics Status should be editable directly where the status is displayed, not through a separate 更新 button.

## Scope

- Replace visible Order Status badges in 订单项目 with inline `<select>` controls for Admin Users.
- Replace visible Goods Logistics Status badges in 货物跟踪 and 订单项目货物明细 with inline `<select>` controls where the user can edit.
- Selecting a new value submits immediately and keeps the current section/context.
- Warehouse User may update Goods Logistics Status where currently allowed, but cannot update Order Status.
- Keep the Chinese display labels while submitting internal enum values.
- Remove redundant separate 更新订单状态 / 更新货物物流状态 action buttons after inline editing exists.

## Acceptance Criteria

- Admin can change an Import Order status from the displayed status field.
- Warehouse User can change Goods Logistics Status from the displayed status field.
- Status change redirects back to the same selected Import Order or tracking context.
- Existing audit logging still records status changes.
- Tests cover one inline Order Status update and one inline Goods Logistics Status update.

## Out of Scope

- Full visual redesign of status controls.

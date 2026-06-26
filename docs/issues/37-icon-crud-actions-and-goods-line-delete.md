# Issue 37: Icon CRUD Actions and Goods Line Delete

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/orders-goods.md`
- `docs/issues/26-chinese-labels-and-modal-actions.md`
- `docs/issues/31-modal-drawer-close-behavior.md`

## Category

Bug.

## Goal

Editable objects need visible single-icon CRUD actions, and Goods Line edit must support returning and deleting.

## Scope

- Add a small shared icon-action style using text symbols or existing native characters; do not add an icon dependency.
- Add current-object actions where applicable:
  - view/detail
  - edit
  - delete/cancel
  - back/return
- Goods Line edit page must include:
  - 返回订单项目
  - 删除货物项
- Delete Goods Line should remove the row and return to the selected Import Order.
- Deleting should be available only to Admin Users.
- Use centered confirmation or native form confirmation only if already simple; keep it minimal.

## Acceptance Criteria

- Goods Line edit page has a visible return action.
- Admin can delete a Goods Line and return to `/orders?order_id=...`.
- Warehouse User cannot delete Goods Lines.
- Tables show compact icon actions instead of long text buttons where actions exist.
- Tests cover Goods Line delete and return link.

## Out of Scope

- A custom icon library.
- Undo/restore.

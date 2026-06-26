# Issue 27: Active Navigation State

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/issues/20-section-navigation-shell.md`

## Category

Bug.

## Goal

The left navigation active indicator must follow the current Workflow Section instead of always highlighting Dashboard.

## Scope

- Detect the current request path in the web shell.
- Mark the matching left-nav item active for:
  - `/dashboard`
  - `/orders`
  - `/tracking`
  - `/receiving`
  - `/shipping-docs`
  - `/excel-finance`
- Child/action pages should map back to their parent section where practical:
  - `/goods-lines/...` maps to 订单项目.
  - document/download/export pages do not need persistent active styling unless already simple.

## Acceptance Criteria

- Clicking each primary section visibly moves the active indicator to that section.
- Dashboard is active only on Dashboard.
- Warehouse User navigation still hides Admin-only sections.
- Add a small web test for at least two non-dashboard active states.

## Out of Scope

- Visual redesign of the sidebar.

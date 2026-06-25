# Issue 20: Section Navigation Shell

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/adr/0002-order-workflow-navigation.md`

## Goal

Replace the current left navigation with the agreed Workflow Section model.

## Scope

- Left navigation sections: Dashboard, 订单项目, 货物跟踪, 仓库盘点, 单证生成, 成本利润.
- Remove Goods Lines, Suppliers, Consignees, Warehouses, Documents, Excel & Finance, and Settings as primary left-navigation items.
- Keep master data and system settings available only as Admin utility actions outside the primary left nav.
- Apply Chinese-first labels in navigation and page titles.
- Add a reusable page pattern: section title, top Context Selector area, summary area, table area, action buttons that open modal/drawer placeholders.

## Acceptance Criteria

- Admin sees exactly the six primary Workflow Sections in the left navigation.
- Warehouse User sees only Dashboard, 订单项目, 货物跟踪, 仓库盘点.
- No raw route/module names such as Goods Lines, Excel & Finance, or Shipping & Documents appear in primary navigation.
- Existing tests for role navigation are updated to the new labels.

## Out of Scope

- Full visual redesign.
- Rebuilding each section's complete workflow.

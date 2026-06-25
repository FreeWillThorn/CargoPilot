# Issue 20: Navigation and UI Structure Rework

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/orders-goods.md`
- `docs/modules/dashboard.md`
- `docs/adr/0001-import-order-as-system-center.md`
- `docs/adr/0002-order-workflow-navigation.md`

## Goal

Rework the browser UI so it matches the normal workflow of an import/order-management system.

## Problem

The current MVP UI exposes Import Orders and Goods Lines as parallel navigation items and places Excel, finance, loading, and documents in broad pages. This contradicts the domain model: Goods Lines and most operational work belong under a selected Import Order.

The current MVP also leaks raw database field names into forms. The UI should use Chinese logistics/business labels and show only operational summary fields in tables.

## Scope

- Replace top-level Goods Lines CRUD navigation with Order Management.
- Make `/orders` the order-management entry point showing all Import Orders and their status.
- Make Import Order detail the parent page for Goods Lines, Excel import, quote/profit, receiving, container/loading, documents/files, and history.
- Keep cross-order pages only for Dashboard, Warehouse Receiving, Tracking, Master Data, and Settings.
- Convert visible labels from raw database/internal field names to Chinese industry labels.
- Use modal or side drawer actions for create/edit/delete/upload/generate/status changes on the current object.
- Keep Warehouse User navigation restricted to Dashboard, Order Management view, and Warehouse Receiving.

## Acceptance Criteria

- Main navigation no longer shows Goods Lines as a peer CRUD module beside Import Orders.
- Admin can open Order Management, select an Import Order, and manage that order's Goods Lines from the order detail page.
- Admin can reach quote/profit, Excel import, loading, and document actions from the selected Import Order context.
- Dashboard and Tracking links route back to the owning Import Order or a filtered triage view without creating a separate Goods Line CRUD workflow.
- Visible UI labels are Chinese-first and do not show raw database names such as `customs_en_name`, `target_markup`, or `carton_gross_weight_kg`.
- Tables show summary columns only; dense fields appear in grouped forms, modal dialogs, or side drawers.
- Warehouse User cannot see finance, pricing, Supplier/Consignee management, Export Documents, or Settings navigation.

## Out of Scope

- Full visual redesign.
- 3D container loading optimization.
- Dashboard chart redesign.
- Browser-native file upload replacement for local path inputs.

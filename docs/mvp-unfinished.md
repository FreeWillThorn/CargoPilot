# MVP Unfinished Work

The first backend/data-layer MVP is implemented. The remaining first-version MVP work is the usable web product around it.

## Remaining MVP Items

1. Web app shell and local server: login screen, role-aware navigation, dashboard route, static assets, and persistent SQLite database file.
2. Master data screens: Suppliers, Consignees, Warehouses, and System Settings CRUD.
3. Import Order and Goods Line screens: list, detail tabs, grouped forms, and incomplete Goods Line editing.
4. Excel import/export screens: upload fixed templates, show row errors, download exports.
5. Cost and quote screens: Goods Line Target Markup, sales price, cost/charge lines, and profit summary.
6. Warehouse receiving screen: search by order/tracking/Shipping Mark, record arrivals, photos, exceptions, and resolutions.
7. Dashboard and tracking screens: Import Order dashboard, Goods Line tracking, filters, clickable blockers, and reminders.
8. Container loading screens: container plan, loading records, split Goods Lines across Containers, and loading list export.
9. Export document screens: blockers, draft/final generation, version history, Excel/PDF download.
10. File storage workflow: save uploaded file bytes under a local uploads directory and store metadata in the database.
11. Seed/demo data: one command to initialize a useful local demo dataset.
12. Release workflow: smoke test command, first MVP tag, and release notes.

## Priority

Build in the order above. Keep each item independently testable and committed.

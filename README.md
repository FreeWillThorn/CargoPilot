# CargoPilot

CargoPilot is a web MVP for managing China-to-Europe import orders: goods lines, suppliers, warehouses, receiving, Excel templates, quote/profit estimates, container loading, and export documents.

## Quickstart

Requires Python 3.11+. Scanned PDF OCR also needs Poppler `pdftoppm` and `tesseract` on `PATH`.

```sh
make seed
make serve
```

Open `http://127.0.0.1:8000`.

Demo logins:

- Admin: `admin@example.com` / `admin`
- Warehouse: `warehouse@example.com` / `warehouse`

The local SQLite database is created at `data/cargopilot.sqlite3`. Generated exports, uploaded-path copies, and generated documents are stored under `data/`.

## Development

Run tests:

```sh
make test
```

Run the release smoke check:

```sh
make smoke
```

Issue workflow:

- Keep one focused commit per issue.
- Run `make test` before each commit.
- Run `make smoke` before release tags.
- Tag releases from a green main branch.
- Prefer `git revert` for production regressions, then forward-fix.

## MVP Screens

- Dashboard, reminders, global search, and Goods Line tracking.
- Import Orders and grouped Goods Line editing.
- Suppliers, Consignees, Warehouses, and Settings.
- Excel fixed-header imports and xlsx exports.
- Quote, Target Markup, cost/charge lines, and profit summary.
- Warehouse receiving, arrival exceptions, and photo metadata.
- Container creation, loading records, loading list export.
- Commercial Invoice and Packing List generation with versioned xlsx/pdf downloads.

## Known Later Enhancements

- Browser-native file upload instead of local file path inputs.
- Visual container loading diagram and later 3D loading optimization.
- Richer dashboard charts and operational drilldowns.
- Customer portal, payment tracking, and arbitrary Excel recognition are intentionally outside the first MVP.

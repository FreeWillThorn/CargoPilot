# Issue 12: Web App Shell and Local Server

## Context Pack

- `docs/prd.md`
- `docs/mvp-unfinished.md`
- `docs/modules/foundation.md`
- `docs/modules/dashboard.md`
- `docs/issues/01-foundation.md`
- `docs/issues/07-simple-dashboard.md`

## Goal

Create the first usable web shell for CargoPilot.

## Scope

- Standard local server entrypoint.
- Persistent SQLite database file.
- Login screen.
- Role-aware session cookie.
- Admin navigation shell.
- Warehouse navigation shell.
- Dashboard route using existing dashboard data.
- Minimal CSS design system.

## Acceptance Criteria

- `make serve` starts a local web server.
- Visiting `/` redirects to login when not authenticated.
- Admin User can log in and see dashboard navigation.
- Warehouse User can log in and see restricted navigation.
- Dashboard route renders Import Order cards from the database.
- Tests cover login, role navigation, and dashboard rendering.

## Out of Scope

- Full CRUD screens.
- File upload bytes.
- JavaScript-heavy interactions.
- React/Vite setup.

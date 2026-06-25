# Issue 01: Foundation, Roles, Files, Audit Logs

## Context Pack

- `docs/prd.md`
- `docs/modules/foundation.md`
- `CONTEXT.md`
- `docs/adr/0001-import-order-as-system-center.md`

## Goal

Create the app foundation for the CargoPilot MVP.

## Scope

- Project skeleton.
- Database foundation.
- Admin User and Warehouse User roles.
- Login/auth boundary.
- File metadata model.
- Audit log model.
- System settings model.

## Acceptance Criteria

- Admin User has full access.
- Warehouse User is represented as a restricted role.
- File records store metadata/path, not file bytes.
- Audit logs can record actor, target, field, old value, new value, and timestamp.
- System settings can store seller information, defaults, container reference limits, and reminder lead days.
- Small runnable checks cover role permissions, audit log creation, and settings defaults.

## Out of Scope

- Business screens.
- GitHub publishing.
- Live exchange-rate API.

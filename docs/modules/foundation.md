# Foundation Module

## Scope

Set up the app foundation: database schema, user login, two roles, file metadata, audit logs, system settings, and Git-friendly project structure.

## Decisions

- Roles: Admin User and Warehouse User.
- Admin User has full access.
- Warehouse User can view Import Orders and update Goods Line receiving/logistics information only.
- Files are stored outside the database; database stores metadata and paths.
- `audit_logs` records actor, time, target object, field, old value, and new value.
- System settings store seller information, default origin country/port, default currencies, container reference limits, and reminder lead days.
- Live exchange-rate API is out of scope.

## Test Focus

- Role access.
- File metadata creation.
- Audit log writes for key changes.
- System settings defaults.

# Master Data Module

## Scope

Manage Suppliers, Consignees/Customers, Warehouses, and Company/System profile information from the Admin-only 基础资料 section.

基础资料 is the single editing home for these objects. Other workflow sections may select or display existing master data, but they should not expose create/edit/delete entry points for Suppliers, Customers/Consignees, Warehouses, or Company/System profile fields.

## Supplier

Fields: name, primary contact, phone, email, WeChat, address, business ID, store URL, usual categories, notes.

Rules:
- One primary contact in the MVP.
- No supplier payment status.
- Goods Line entry means purchase/payment happened outside CargoPilot.
- No supplier scoring.
- Warn on duplicate Supplier names.

## Consignee

Fields: company name, primary contact, email, phone, VAT/EORI/tax ID, one address, default destination port, default trade term, default sales currency, document preferences, notes.

Rules:
- One address only.
- No separate billing/delivery/document-header addresses in the MVP.
- No customer credit or payment status.

## Warehouse

Types: Receiving Warehouse and Port Warehouse.

Fields: type, name, contact, phone, address, notes.

## Company Information

Company/System profile fields include seller company name, address, phone, email, tax/business registration number, bank information, default origin country/port, default currencies, container reference limits, and reminder lead days.

Rules:
- Company information is edited from 基础资料.
- Company information feeds document generation and default values.
- This is not a full organization/account-management module.

## Test Focus

- CRUD for master data.
- Company/System profile edit visibility and persistence.
- Duplicate Supplier name warning.
- Default Consignee values applied to new Import Orders.
- Workflow pages no longer expose scattered master-data create/edit/delete entry points.

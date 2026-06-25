# Master Data Module

## Scope

Manage Suppliers, Consignees, and Warehouses.

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

## Test Focus

- CRUD for master data.
- Duplicate Supplier name warning.
- Default Consignee values applied to new Import Orders.

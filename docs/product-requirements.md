# CargoPilot Requirements Draft

## Goal

Replace spreadsheet-based import-order tracking with a web system that records supplier purchasing, package details, warehouse receiving, container planning, shipment progress, costs, profit, and export documents for China-to-Europe customer orders.

## Core Workflow

1. Create an Import Order for a Consignee.
2. Add Goods Lines from the customer's purchase list.
3. Record Supplier details, purchase price, quantity, domestic tracking number, invoice, package count, weight, dimensions, volume, and Shipping Mark.
4. Estimate total package count, gross weight, volume, and Container Plan.
5. Track supplier deliveries into the Receiving Warehouse.
6. Warehouse staff count received packages against each Goods Line.
7. Move checked goods to the Port Warehouse.
8. Confirm loading into container.
9. Track sea freight status.
10. Generate Export Documents in English.

## Modules

**Dashboard**:
Shows active Import Orders, latest order status, current logistics concentration point, delayed Goods Lines, missing package data, missing documents, and upcoming container/loading milestones.

The dashboard lists Import Orders with order number, Consignee, destination port, current Order Status, Order Stage Progress, total cartons, total CBM, total gross weight, expected loading date, Arrival Exception count, and missing-data count.

Each Import Order shows a current logistics concentration point such as supplier side, Receiving Warehouse, Port Warehouse, loaded, or at sea. This is calculated from Goods Line logistics states.

Order Stage Progress is calculated from Goods Line completion within the current stage. When all relevant Goods Lines complete the current stage, the Import Order moves to the next Order Status and starts showing that stage's percentage.

Each Order Status has a distinct dashboard color.

Order Status colors are: Draft gray, Purchasing blue, Receiving orange, Received cyan, Moving to port purple, At port warehouse indigo, Loaded green, At sea navy, Arrived teal, Completed dark gray, Cancelled red.

Order Stage Progress is calculated by Goods Line count in the MVP, not weighted by cartons, CBM, or value.

If any Goods Line has an Arrival Exception, the Import Order shows an exception badge but does not change its main Order Status to exception.

For example, if 80% of Goods Lines have reached the Receiving Warehouse and 20% are still in transit, the Import Order remains in receiving with 80% progress.

At sea is manually confirmed by an Admin User because sailing status comes from shipping information, not warehouse events.

The dashboard prioritizes risks such as missing dimensions, missing Customs English Name, missing cartons, damaged cartons, missing Supporting Compliance Files, and goods not received before expected loading date.

Dashboard filters include Consignee, Order Status, expected loading date, destination port, and exception status.

Dashboard exception and missing-data counts should be clickable and open the relevant filtered list.

Global search supports Import Order number, Consignee name, Supplier name, product name, Domestic Tracking Number, Shipping Mark, and container number.

Goods Line filters include Goods Logistics Status, Supplier, Consignee, Import Order, Arrival Exception Type, missing-field status, and expected loading date.

System reminders are shown as in-app badges and lists in the MVP, not email, SMS, or WeChat notifications.

Default reminders include goods not fully received 3 days before expected loading date, missing Export Document required fields, and missing or unapproved Compliance Requirements.

**Workflow Sections**:
The browser left navigation is Dashboard, 订单项目, 货物跟踪, 仓库盘点, 单证生成, and 成本利润. These are business workflows, not database modules.

Each Workflow Section has a top Context Selector, usually Import Order or Warehouse. The selected context controls the detail panels, tables, and action buttons below it.

**订单项目**:
Owns Import Order creation, Consignee, destination, expected shipment date, current Order Status, Goods Lines, and notes.

**货物跟踪**:
Selects an Import Order and tracks each Goods Line through supplier preparation, domestic shipped, received, checked, moved to port, loaded, and shipped.

**Goods Information**:
Stores product name, English name, HS code if known, material/category, quantity, unit/package dimensions, unit weight, cartons, gross weight, volume, Shipping Mark, photos/files, and optional loading sketch.

**成本利润**:
Selects an Import Order and tracks purchase cost, domestic logistics, warehouse fees, inspection/document fees, sea freight, other fees, customer charge, currency, exchange rate, margin, and profit.

Costs include purchase cost, domestic logistics, warehouse fees, inspection/certificate fees, customs/document fees, sea freight, and other fees.

Costs can be attached to either Import Orders or Goods Lines. Order-level costs include shared costs such as sea freight; Goods Line costs include item-specific costs such as product purchase or a certificate for one product.

The finance module records purchase currency, customer quote currency, and exchange rate. Profit is calculated from customer charges minus all converted costs, with manual adjustment lines allowed.

Customer charges include product sales, freight/service charges, and other pass-through charges.

Each Goods Line can store Target Markup or target margin so unusually high calculated prices can be manually adjusted before quoting.

The MVP is an internal profit-estimation module, not an accounting system. It does not manage payment collection, supplier payment, tax invoices, or full ledger workflows.

**Warehouse Address Book**:
Stores Receiving Warehouses and Port Warehouses with contacts, phone, address, operating notes, and default assignment rules.

Warehouses are either Receiving Warehouse or Port Warehouse.

Each Import Order can assign one default Receiving Warehouse and one default Port Warehouse.

**单证生成**:
Selects an Import Order and generates English invoice, packing list, and supporting exports from confirmed Goods Line data. Blocks final documents when required fields are missing.

The MVP generates Commercial Invoice and Packing List only. Certificates of origin, inspection certificates, test reports, and similar compliance documents are uploaded and tracked as Supporting Compliance Files, not generated by the system.

Commercial Invoice includes seller information, buyer/Consignee, invoice number, date, trade term, origin port, destination port, Customs English Name, quantity, unit, sales unit price, line amount, currency, and total amount.

Packing List includes seller information, buyer/Consignee, packing list number, date, origin port, destination port, Customs English Name, carton count, quantity, gross weight, CBM, Shipping Mark, and totals.

Seller information is stored in system settings.

Invoice and Packing List numbers default from Import Order number and version, such as `CP-2026-0001-INV-V1`.

The MVP exports Commercial Invoice and Packing List as Excel and PDF. Word export is not included.

Invoice and Packing List use Customs English Name. Final document generation requires Consignee, destination port, Customs English Name, quantity, carton count, gross weight, CBM, sales unit price, and currency. If required data is missing, the system can generate a draft or block the final version.

Export Documents are versioned. Each generated document is saved as V1, V2, V3, and so on.

Commercial Invoice uses customer sales price, not Supplier purchase price. Purchase price is internal finance data.

Packing List is summarized by Goods Line in the MVP, not expanded by Domestic Tracking Number.

Consignee records store company name, one address, tax number, default destination port, default trade term, default sales currency, and template preferences. The MVP does not split billing address, delivery address, or separate document header address.

**Supplier Management**:
Stores Supplier company/contact details, store URL, usual categories, and historical Goods Lines.

Supplier Management stores one primary contact in the MVP, with extra contact details placed in notes if needed.

The MVP does not track supplier payment status. A Goods Line being entered in the system means supplier purchase/payment is already handled outside CargoPilot.

The MVP does not include Supplier scoring or reliability ratings.

Supplier records include usual product categories and optional 1688/store URL. The system should warn on duplicate Supplier names.

**Consignee Management**:
Stores European customer company/contact details, one address, VAT/EORI/tax ID, default destination port, default trade term, default sales currency, document preferences, and historical Import Orders.

Consignee Management stores one primary contact in the MVP, with extra contact details placed in notes if needed.

The MVP does not track customer credit or payment status.

**Compliance Management**:
Tracks per-Goods Line or per-Import Order requirements such as certificate of origin, quarantine inspection, test report, declaration, or customer-specific documents.

Compliance Requirements attach mainly to Goods Lines, and can also attach to an Import Order when the requirement applies to the whole order.

Built-in compliance types include certificate of origin, inspection certificate, test report, quarantine/animal-plant inspection, and customer-specified file.

Compliance status uses: not required, required, requested, uploaded, approved, blocked.

The MVP supports simple product-category reminders for likely requirements, such as wood products, food-contact goods, textiles, or customer-specific categories. Admin Users can manually disable or override these reminders.

Incomplete Compliance Requirements are blockers for final Export Documents and shipment confirmation, but draft documents can still be generated.

Supporting Compliance Files do not track expiry dates in the MVP.

**Users and Permissions**:
The MVP has two roles: Admin User and Warehouse User. Admin Users have full access. Warehouse Users can view Import Orders and update related Goods Line receiving/logistics information, but cannot access finance, profit, customer pricing, document settings, or system settings.

Warehouse Users can edit received carton count, package condition, Arrival Exception Type, receiving notes, receiving photos, and Goods Logistics Status. They cannot edit pricing, profit, Consignee records, Supplier records, or Export Documents.

Customer login portal is not included in the MVP.

The system records modification history for key changes, including status, price, carton count, weight, dimensions, document generation, and file changes.

**System Settings**:
System settings store seller company information, including company name, address, phone, email, tax/business registration number, and bank information.

System settings store default origin country, default origin port, default currencies, container reference capacity/weight limits for 20GP, 40GP, and 40HQ, and reminder lead days defaulting to 3.

Exchange rates are manually recorded on Import Orders or cost/charge records. The MVP does not use a live exchange-rate API.

Document templates are fixed in the MVP except for seller information. Custom template styling is a later feature.

## Status Model

**Order Status**:
Draft, purchasing, receiving, received, moving to port, at port warehouse, loaded, at sea, arrived, completed, cancelled.

**Goods Logistics Status**:
Not ordered, ordered, supplier preparing, domestic shipped, received at warehouse, checked, exception, moved to port warehouse, loaded, at sea.

Order Status should be semi-automatic. The system suggests the Import Order status from the Goods Lines beneath it, while key milestones such as loaded and at sea can be manually confirmed.

Arrival Exception is not a terminal Goods Logistics Status. After the issue is resolved, the Goods Line returns to the correct logistics status.

**Compliance Status**:
Not required, required, requested, received, approved, blocked.

**Arrival Exception Type**:
Missing cartons, extra cartons, damaged cartons, unclear Shipping Mark, wrong goods, dimension/weight mismatch.

## Data Model Draft

Use a relational database centered on `import_orders -> goods_lines`. Postgres or MySQL are both acceptable; final selection can happen during implementation planning.

Files are stored outside the database, with only metadata and storage paths stored in database records.

Use a general `audit_logs` table for modification history, recording actor, time, target object, changed field, old value, and new value.

**import_orders**:
id, order_no, consignee_id, receiving_warehouse_id, port_warehouse_id, trade_term, origin_country, origin_port, destination_country, destination_port, order_status, container_plan_id, expected_received_date, expected_loading_date, expected_departure_date, expected_arrival_date, actual_received_date, actual_loading_date, actual_departure_date, actual_arrival_date, purchase_currency, sales_currency, internal_notes, created_at, updated_at.

**goods_lines**:
id, import_order_id, supplier_id, customer_item_no, sku_or_model, product_url, cn_name, en_name, customs_en_name, category, hs_code, quantity, unit, carton_count, units_per_carton, carton_gross_weight_kg, gross_weight, carton_length_cm, carton_width_cm, carton_height_cm, volume_cbm, shipping_mark, logistics_status, compliance_status, target_markup, sales_unit_price, sales_currency, purchase_unit_price, purchase_currency, notes.

**suppliers**:
id, name, contact_name, phone, email, wechat, address, business_id, store_url, usual_categories, notes.

**consignees**:
id, company_name, contact_name, email, phone, tax_id, address, default_destination_port, default_trade_term, default_sales_currency, document_preferences, notes.

**warehouses**:
id, type, name, contact_name, phone, address, notes.

**tracking_events**:
id, goods_line_id, status, event_time, location, domestic_tracking_no, package_count, weight, volume_cbm, operator, notes.

**cost_lines**:
id, import_order_id, goods_line_id, cost_type, amount, currency, exchange_rate, charge_to_customer, notes.

**compliance_requirements**:
id, import_order_id, goods_line_id, requirement_type, status, due_date, file_id, notes.

**documents**:
id, import_order_id, document_type, status, generated_at, file_id, version, notes.

**files**:
id, owner_type, owner_id, file_category, file_name, file_type, storage_path, uploaded_by_user_id, uploaded_at.

**audit_logs**:
id, actor_user_id, target_type, target_id, field_name, old_value, new_value, created_at.

## MVP Boundary

Build first:
- Manual entry and fixed-header Excel import for Import Orders, Goods Lines, Suppliers, Consignees, Warehouses, and package data.
- Dashboard for active Import Orders and per-Goods Line logistics status.
- Basic CBM/gross-weight/container estimate.
- English invoice and packing list generation.
- File uploads for supplier invoices, photos, and certificates.

Skip for now:
- Automatic 1688 scraping.
- Real carrier API integrations.
- Advanced 3D container optimization.
- Accounting-grade finance.
- Mobile warehouse app.

Add later when needed:
- Barcode/QR scan receiving.
- Role-based warehouse login.
- OCR from supplier invoices.
- Container loading optimizer.
- Customer portal.

## Confirmed Decisions

The system uses **Import Order** as the center of the product. One Import Order represents one European customer import need and can contain many Goods Lines, Suppliers, domestic tracking numbers, files, costs, compliance requirements, and logistics events.

A **Goods Line** is defined by the combination of Supplier, product model/specification, English customs name, and packaging method. If any of those differ, the goods should be split into separate Goods Lines.

Goods Lines can be created with incomplete data and completed over time. The system should track missing required fields and show blockers instead of forcing customer list, supplier invoice, package dimensions, tracking numbers, receiving data, costs, and compliance files to be entered at the same time.

Missing fields are evaluated by stage. The system distinguishes warnings, which allow work to continue, from blockers, which prevent the next key milestone.

Purchasing-stage required fields: Supplier, Chinese product name, quantity, and either purchase/sales price or Target Markup.

Container-estimation required fields: carton count, units per carton, carton length/width/height, and carton gross weight.

Receiving-stage required fields: Domestic Tracking Number, Shipping Mark, and received carton count. Receiving photos are recommended but not mandatory.

Final Export Document required fields: Customs English Name, HS code, quantity, carton count, gross weight, CBM, sales unit price, currency, and Consignee document information.

Loading-completion required fields: container type, container number, seal number, and loading date. Loading photos are recommended but not mandatory.

Import Order numbers are generated by the system, such as `CP-2026-0001`, and Admin Users can manually edit them. Customer order/reference numbers are not included in the MVP.

Import Orders store trade term, origin port, destination country, destination port, expected received/loading/departure/arrival dates, actual received/loading/departure/arrival dates, default purchase currency, default sales currency, and internal notes. The MVP only needs internal notes because there is no customer portal.

Excel import should support at least two fixed-header templates: a customer purchase-list template for early product and quantity entry, and a supplier package/logistics template for later invoice, carton, weight, dimension, and domestic tracking updates.

Excel import uses fixed headers only in the MVP. Smart recognition of arbitrary spreadsheets is not included.

Customer purchase-list template headers: order_no, supplier_name, customer_item_no, product_url, cn_name, en_name, customs_en_name, sku_or_model, category, hs_code, quantity, unit, target_markup, sales_unit_price, sales_currency, notes.

Supplier package/logistics template headers: order_no, supplier_name, sku_or_model, customs_en_name, carton_count, units_per_carton, carton_length_cm, carton_width_cm, carton_height_cm, carton_gross_weight_kg, domestic_tracking_no, shipping_mark, purchase_unit_price, purchase_currency, supplier_invoice_no, notes.

Goods Lines store Chinese product name, customer-facing English name, Customs English Name, and optional HS code. HS code can be empty during early entry but becomes a blocker before final Export Documents.

Packaging should be recorded as carton count, units per carton, carton length/width/height, and carton gross weight. The system calculates total quantity, total gross weight, and CBM from these fields.

One Goods Line can have multiple Domestic Tracking Numbers because suppliers may ship one product in multiple batches.

Files can attach to either Import Orders or Goods Lines. Order-level files include contracts or whole-order records; Goods Line files include supplier invoices, product photos, package photos, certificates, and inspection files.

Files can attach to Import Orders, Goods Lines, Suppliers, Consignees, Receiving Records, and Loading Records.

File categories include supplier invoice, product photo, package photo, receiving photo, loading photo, compliance file, customer file, and other.

The MVP supports PDF, image, Excel, and Word uploads. PDF and image files should have basic preview; other files can be downloaded.

Only generated Export Documents are versioned. Uploaded files are not versioned in the MVP; repeated uploads are stored as separate files.

## Requirements Capture Plan

Use this order for the remaining grilling so details do not get lost:

1. Confirm the Import Order boundary.
2. Define Goods Line fields and Excel import headers.
3. Define package, weight, volume, and CBM calculation rules.
4. Define Order Status and Goods Logistics Status transitions.
5. Define warehouse receiving and exception handling.
6. Define container planning and loading records.
7. Define Export Document required fields and templates.
8. Define cost, charge, margin, currency, and exchange-rate rules.
9. Define compliance requirements by product/category/customer.
10. Define dashboard views, filters, alerts, and user roles.

## Development Module Breakdown

Recommended MVP build order:

1. Foundation: login, Admin/Warehouse roles, database schema, file upload, audit logs.
2. Master Data: Suppliers, Consignees, Warehouses, and System Settings.
3. Import Orders and Goods Lines with manual entry.
4. Cost, quote, Target Markup, and profit estimation.
5. Fixed-header Excel import and Excel export.
6. Packaging data, CBM/gross-weight calculation, and missing-field checks.
7. Simple Dashboard for active Import Orders and blockers.
8. Warehouse receiving page, Arrival Exceptions, and Goods Logistics Status updates.
9. Full Dashboard and Goods Logistics Tracking dashboard.
10. Container Plan and Loading Records.
11. Commercial Invoice and Packing List generation.

**Foundation**:
Database schema, file storage, user login, permissions, shared status lists, and audit timestamps.

Permissions only need Admin User and Warehouse User roles in the MVP.

The web MVP prioritizes desktop admin screens. Warehouse receiving pages should also work on mobile browsers.

The interface is Chinese in the MVP, while generated Export Documents are English.

**Import Orders**:
Create and edit Import Orders, assign Consignee, destination, warehouses, dates, status, and notes.

Import Order list pages should not display every field. Lists show only decision fields such as order number, Consignee, destination port, Order Status, Order Stage Progress, expected loading date, exception count, and missing-data count. Dense fields belong in the detail page, grouped by tabs or sections.

Import Order detail is reached inside Workflow Sections. In 订单项目 it shows order overview and Goods Lines; in 货物跟踪 it shows the selected order's logistics table; in 单证生成 it shows document readiness and versions; in 成本利润 it shows quote/profit data.

**Goods Lines and Excel Import**:
Manual entry plus fixed-header spreadsheet import for products, suppliers, quantities, package data, tracking numbers, costs, and compliance flags.

Goods Line tables show only core columns by default: product name, Supplier, quantity, carton count, CBM, gross weight, Goods Logistics Status, Arrival Exception, and missing-data indicators. Full fields are edited in a side panel or detail dialog.

Goods Line editing forms group fields into basic information, pricing, packaging, logistics, compliance, and files.

The MVP may include a simple column visibility setting for Goods Line tables, but fixed sensible default columns are acceptable first.

**仓库盘点**:
Record package arrivals, count mismatches, damaged goods, missing labels, photos, and receiving notes.

Warehouse receiving must support partial arrivals. One Goods Line can have multiple Domestic Tracking Numbers, and each Domestic Tracking Number can produce one or more Receiving Records.

Each Receiving Record stores received carton count, package condition, photos, receiving notes, and any Arrival Exception Type.

The warehouse section selects a Warehouse at the top, then shows inbound/received Goods Lines for that Warehouse and their owning Import Orders. Search by Import Order, Domestic Tracking Number, or Shipping Mark remains available for fast lookup.

**Logistics Tracking**:
Maintain per-Goods Line tracking events and calculate Import Order progress from the goods beneath it.

**Container Planning**:
Summarize cartons, gross weight, volume, and suggested container type; store final container number and loading result.

CBM is calculated as carton length cm * carton width cm * carton height cm / 1,000,000 * carton count. Gross weight is calculated as carton gross weight * carton count. Both calculated values can be manually overridden because supplier package data may be inaccurate.

The MVP recommends 20GP, 40GP, or 40HQ from total CBM and gross weight. It does not implement advanced container loading optimization.

Container planning stores both estimated plan data and actual loading result data. Estimated data supports booking; actual data supports final Export Documents and review.

Loading Records include container type, container number, seal number, loading date, loaded Goods Lines, and loading photos.

One Import Order can use multiple Containers. A Container cannot mix multiple Import Orders in the MVP.

Loading Records store the actual carton count loaded per Goods Line. The same Goods Line can be split across multiple Containers.

The MVP can generate a simple loading list showing container number, seal number, loaded Goods Lines, loaded cartons, CBM, and gross weight.

The MVP stores loading photos and notes but does not implement visual loading diagrams, 3D loading simulation, or container optimization. Those are later features.

**单证生成**:
Select an Import Order, then generate invoice and packing list from confirmed Import Order and Goods Line data, with versioned output files.

**成本利润**:
Select an Import Order, then track purchase costs, freight, fees, customer charges, exchange rates, margin, and profit.

**Master Data**:
Manage Suppliers, Consignees, Receiving Warehouses, Port Warehouses, product categories, and document preferences as admin utilities, not primary left-navigation sections.

**Dashboard**:
Show active orders, current concentration point, delayed goods, missing data, upcoming loading, and document blockers.

Each Workflow Section keeps a top context selector and opens create/edit/upload/generate actions in a modal or side drawer.

货物跟踪 normally shows Goods Lines under the selected Import Order. Cross-order exception or delay filters are allowed for triage, but rows must clearly show the owning Import Order.

**Exports and Reports**:
Admin Users can export Import Orders, Goods Lines, dashboard filtered results, cost/profit reports, warehouse receiving lists, and loading lists to Excel.

The MVP does not include complex BI charts. Lists, filters, and Excel exports are enough.

## Later Enhancements

These are intentionally outside the MVP but should not be forgotten:

- Visual loading diagram and 3D container optimization.
- More advanced Dashboard analytics, trend charts, and management summaries.
- Barcode/QR scan receiving.
- OCR extraction from supplier invoices and package documents.
- Customer portal.
- External carrier/shipping API integrations.
- Email, SMS, or WeChat notifications.
- Custom document template styling.
- Supplier multi-contact management.
- Customer multi-contact management.
- Column presets and advanced table personalization.

## Development Workflow

Code is managed with Git. Each MVP issue should be developed and tested as independently as practical, then committed when complete.

Every release gets a Git tag.

Production incidents should prefer `git revert` to restore stable behavior before attempting a new fix.

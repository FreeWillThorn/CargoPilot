# CargoPilot MVP PRD

## Problem Statement

The business currently runs China-to-Europe import orders through Excel. One customer import need can contain many suppliers, products, domestic tracking numbers, package details, warehouse receiving events, container loading records, costs, compliance files, and export documents. Excel makes it hard to see order progress, missing data, exceptions, container readiness, profit, and document blockers in one place.

## Solution

CargoPilot is a web system centered on **Import Order**. It lets Admin Users create orders, add Goods Lines, import fixed Excel templates, track supplier logistics and warehouse receiving, calculate CBM/gross weight, plan containers, manage files and compliance blockers, estimate cost/profit, and generate English Commercial Invoice and Packing List files. Warehouse Users get a restricted view for receiving and logistics updates.

## User Stories

1. As an Admin User, I want to create an Import Order, so that I can manage one European customer import need from purchase through shipment.
2. As an Admin User, I want one Import Order to contain many Goods Lines, so that multiple suppliers and products can be tracked under one customer shipment.
3. As an Admin User, I want Goods Lines split by Supplier, model/specification, Customs English Name, and packaging method, so that documents and package calculations stay correct.
4. As an Admin User, I want to create incomplete Goods Lines, so that I can start tracking before suppliers provide all package details.
5. As an Admin User, I want missing fields shown by stage, so that I know what blocks purchase, container estimate, receiving, loading, and final documents.
6. As an Admin User, I want fixed-header Excel imports, so that customer lists and supplier package data can enter the system without custom parsing.
7. As an Admin User, I want 1688/product links on Goods Lines and store URLs on Suppliers, so that sourcing context is easy to recover.
8. As an Admin User, I want Supplier and Consignee master data, so that repeated orders reuse contacts, addresses, ports, currencies, and preferences.
9. As an Admin User, I want target markup and sales prices on Goods Lines, so that I can adjust quotes when markup is too high or too low.
10. As an Admin User, I want cost and customer charge lines, so that profit can be estimated by order and by product.
11. As an Admin User, I want CBM and gross weight calculated from carton data, so that container planning does not rely on manual spreadsheets.
12. As an Admin User, I want manual overrides for calculated package values, so that supplier data errors can be corrected.
13. As a Warehouse User, I want to search by order, domestic tracking number, or Shipping Mark, so that I can quickly record arrivals.
14. As a Warehouse User, I want to record received cartons, package condition, photos, notes, and exceptions, so that receiving evidence is preserved.
15. As an Admin User, I want partial arrivals and multiple domestic tracking numbers per Goods Line, so that split supplier shipments are handled naturally.
16. As an Admin User, I want Order Status and Order Stage Progress, so that I can see current progress without manually checking each product.
17. As an Admin User, I want Goods Line status percentages to drive Import Order progress, so that dashboard progress reflects the goods beneath the order.
18. As an Admin User, I want exception badges, so that problems stand out without replacing the main order status.
19. As an Admin User, I want Dashboard filters and clickable blocker counts, so that I can jump directly to delayed or incomplete work.
20. As an Admin User, I want one Import Order to support multiple Containers, so that large orders can split across cabinets.
21. As an Admin User, I want a Container to belong to one Import Order in the MVP, so that mixed-order complexity is avoided.
22. As an Admin User, I want Loading Records with container number, seal number, loaded Goods Lines, carton counts, photos, and notes, so that actual loading is traceable.
23. As an Admin User, I want Commercial Invoice and Packing List generated from confirmed data, so that English export documents are consistent.
24. As an Admin User, I want generated documents versioned, so that corrected documents do not overwrite history.
25. As an Admin User, I want compliance files uploaded and tracked, so that certificates and inspection files are visible without pretending the system creates them.
26. As an Admin User, I want key changes audited, so that price, package, status, document, and file modifications are traceable.
27. As an Admin User, I want Excel exports, so that filtered data and reports can still be shared outside the system.
28. As a Warehouse User, I want limited permissions, so that I can update receiving without seeing profit, pricing, customers, suppliers, or document settings.

## Implementation Decisions

- Use **Import Order** as the system center. It owns Goods Lines, costs, logistics, compliance, files, containers, and Export Documents.
- Left navigation uses business Workflow Sections: Dashboard, 订单项目, 货物跟踪, 仓库盘点, 单证生成, and 成本利润.
- Each Workflow Section has a top Context Selector, usually Import Order or Warehouse, then shows the tables and actions relevant to that selected context.
- Goods Lines are never a top-level CRUD destination. They appear under 订单项目 and 货物跟踪 as child rows of the selected Import Order.
- Master data and system settings are admin utilities, not primary left-navigation sections.
- Current-object actions such as add, edit, delete, upload, generate, and status changes should open from the current page as a modal or side drawer.
- The browser UI is Chinese-first. Internal database field names must not be shown directly; use Chinese logistics/business labels, with English kept only for industry-standard trade terms, document names, abbreviations, and codes such as FOB, HS Code, SKU, CBM, Commercial Invoice, and Packing List.
- Use a relational database centered on `import_orders -> goods_lines`.
- Store files outside the database; database rows store metadata and paths.
- Use two MVP roles: Admin User and Warehouse User.
- Use fixed-header Excel templates only. Smart recognition of arbitrary spreadsheets is out of scope.
- Track stage-specific required fields as warnings or blockers.
- Calculate CBM as `carton_length_cm * carton_width_cm * carton_height_cm / 1,000,000 * carton_count`.
- Calculate gross weight as `carton_gross_weight_kg * carton_count`.
- Allow manual overrides for package calculations.
- Calculate Order Stage Progress by Goods Line count in the MVP.
- Use in-app badges/lists for reminders; no external notifications in the MVP.
- Generate Commercial Invoice and Packing List only. Supporting compliance files are uploaded.
- Export generated documents as Excel and PDF. Word export is out of scope.
- Use Git for development. Each issue should be independently developed, tested, and committed. Releases get tags; production incidents prefer `git revert`.

## Testing Decisions

- Test external behavior rather than implementation details.
- Core calculation tests cover CBM, gross weight, order stage progress, missing-field blocker rules, and profit totals.
- Excel tests cover fixed-header import validation and exported sheet shape.
- Permission tests cover Admin User versus Warehouse User access.
- Warehouse receiving tests cover partial arrivals, exceptions, and status updates.
- Document tests cover required-field blocking, invoice/packing-list data, numbering, and version creation.
- Dashboard tests cover status color, progress, filters, blocker counts, and clickable risk links.
- Each issue should include the smallest runnable checks needed for its behavior.

## Out of Scope

- Automatic 1688 scraping.
- Smart arbitrary Excel parsing.
- Real carrier/shipping API integrations.
- Advanced BI dashboards.
- Visual loading diagrams and 3D container optimization.
- Barcode/QR receiving.
- OCR extraction.
- Customer portal.
- External email/SMS/WeChat notifications.
- Custom document template styling.
- Full accounting, payment collection, supplier payment, tax invoices, or ledger workflows.
- Supplier scoring.
- Customer credit management.
- Mixed Import Orders in one Container.

## Further Notes

Development should happen in MVP priority order. To avoid context bloat, each issue lists a **Context Pack**. Future implementation sessions should read only the PRD, the relevant module document, the issue, and any directly referenced ADR/glossary entries.

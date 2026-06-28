# CargoPilot

CargoPilot manages China-sourced export orders for European customers, from supplier purchasing through warehouse receiving, container loading, sea freight, and export document generation.

## Language

English domain terms are canonical for code and technical documents. Browser UI labels are Chinese-first and are mapped in `docs/modules/user-interface.md`.

**Workflow Section**:
A primary browser work area such as 订单详情, 货物详情, 仓库盘点, 海运单证, 成本利润, or 基础资料. A Workflow Section groups actions by the operator's task rather than by database table.
_Avoid_: database module, table module

**Context Selector**:
The section-level selector that chooses the current Import Order, Warehouse, or filter context for the tables and actions below it.
_Avoid_: global filter, unrelated dropdown

**Order Assistant**:
An AI workflow that starts from one Import Order and reviews that order's Goods Lines, files, messages, costs, and document readiness to produce business suggestions.
_Avoid_: generic chat bot, free-floating agent

**Order Assistant Entry**:
The single order-level AI entry point that lets an Admin User review all assistant suggestions for the selected Import Order across goods, warehouse, documents, compliance, and finance.
_Avoid_: separate agent apps, standalone AI workspace

**AI Action Button**:
A section-level button that starts an Order Assistant task from the user's current Workflow Section and selected Import Order, such as checking order details, checking goods information, or generating document suggestions.
_Avoid_: detached chat shortcut, global magic button

**Assistant Source Scope**:
The selected Import Order data plus files or text supplied for the current assistant task.
_Avoid_: all system files, unrelated orders

**Assistant Run**:
One background execution of an Order Assistant task for a selected Import Order.
_Avoid_: synchronous page action, overwritten check

**Router**:
The Order Assistant component that chooses which specialist agents should run for the selected Import Order task.
_Avoid_: user-facing agent picker, generic workflow engine

**Task Template**:
The fixed routing pattern for an AI Action Button and Workflow Section, such as AI检查订单 or AI检查利润风险.
_Avoid_: configurable workflow, free-form route

**Source Rule**:
The fixed routing hint from supplied Excel, PDF, pasted chat records, or selected-order data.
_Avoid_: global file scan, user-defined rule engine

**Specialist Agent**:
An internal Order Assistant worker focused on one business concern, such as structured intake, goods review, compliance risk, document drafting, or profit risk.
_Avoid_: standalone app, separate workflow section

**Structured Intake Agent**:
结构化录入 Agent. The Specialist Agent that extracts proposed order, goods, package, cost, or document data from Excel, PDF, or pasted chat records.
_Avoid_: master-data creator, direct importer

**Order Review Agent**:
订单检查 Agent. The Specialist Agent that checks order-level information in 订单详情.
_Avoid_: goods checker, status updater

**Goods Review Agent**:
货物资料检查 Agent. The Specialist Agent that checks Goods Line information in 货物详情.
_Avoid_: warehouse receiving checker, generic product agent

**Compliance Risk Agent**:
合规/单证风险 Agent. The Specialist Agent that flags likely Compliance Requirements from product name, material, category, or provided files.
_Avoid_: certificate generator, customs authority

**Document Draft Agent**:
单证草稿 Agent. The Specialist Agent that checks 海运单证 readiness and prepares Commercial Invoice or Packing List drafts.
_Avoid_: official document generator

**Profit Risk Agent**:
利润风险 Agent. The Specialist Agent that checks 成本利润 for margin, missing fee, low quote, and exchange-rate risks.
_Avoid_: accounting agent, payment tracker

**Coordinator**:
The Order Assistant component that merges specialist agent outputs into Assistant Suggestions and Review Requests.
_Avoid_: auto-approver, change applier

**Assistant Suggestion**:
An Order Assistant finding shown to an Admin User as suggestion, review-needed, or blocking-risk before any Change Draft is prepared.
_Avoid_: AI decision, automatic judgment

**Suggestion Target**:
The Import Order or affected Goods Lines that an Assistant Suggestion refers to.
_Avoid_: raw table reference, detached warning

**Source Reference**:
The order data, Goods Line, uploaded file, pasted message excerpt, or system summary that supports an Assistant Suggestion.
_Avoid_: unsupported claim, hidden evidence

**Review-Needed Field**:
A low-confidence extracted value that needs administrator confirmation before it can become part of a Change Draft.
_Avoid_: uncertain auto-fill, guessed value

**Review Request**:
An administrator-facing check step created from an Order Assistant suggestion before the system prepares any follow-up change.
_Avoid_: auto-apply, silent approval

**Change Draft**:
A not-yet-applied system update proposed after a Review Request is accepted, such as field fills, risk flags, compliance reminders, or document data corrections tied to one Import Order.
_Avoid_: direct write, automatic update

**Confirmed AI Output**:
An AI-generated draft that has been reviewed and confirmed by an Admin User before becoming an official system record, generated document, or applied order change.
_Avoid_: AI final output, autonomous document

**Order Details Section**:
The Workflow Section for finding, creating, reviewing, and editing Import Orders.
_Avoid_: order table module, goods workspace

**Goods Details Section**:
The Workflow Section for managing Goods Lines under the selected Import Order, including product details, supplier selection, package data, and logistics status.
_Avoid_: standalone goods module, order detail subtable

**Order Detail**:
The selected Import Order context inside a Workflow Section, showing details and child objects relevant to that section.
_Avoid_: standalone Goods Line workspace

**Import Order**:
A customer-facing shipment project that groups all goods being sourced, received, packed, shipped, and documented together for one European customer need.
_Avoid_: 单, generic order, shipment, project

**Goods Line**:
One product entry inside an Import Order. A Goods Line is split when supplier, product model/specification, English customs name, or packaging method differs.
_Avoid_: 商品, product row, item

**Supplier**:
The Chinese seller or manufacturer that provides goods, invoices, package details, and domestic tracking numbers.
_Avoid_: 商家, vendor, factory

**Consignee**:
The European receiving customer or company named on shipping and commercial documents.
_Avoid_: 客户, receiver, buyer

**Shipping Mark**:
The mark printed or attached to packages so warehouse staff can identify which Import Order and Goods Line they belong to.
_Avoid_: mark

**Receiving Warehouse**:
The warehouse that receives domestic deliveries from suppliers and checks arrival status against the Import Order.
_Avoid_: 指定仓库, 仓库地址

**Port Warehouse**:
The warehouse near the port where received goods wait before container loading.
_Avoid_: 港口仓库

**Container Plan**:
The estimated or confirmed container requirement for an Import Order, such as 20 ft, 40 ft, or 40 ft high cube.
_Avoid_: 订柜, container estimate

**Container**:
A physical shipping container assigned to one Import Order. One Import Order may use multiple Containers, but Containers do not mix multiple Import Orders in the MVP.
_Avoid_: 柜, 集装箱

**Loading Record**:
The confirmed record of goods loaded into a Container, including container type, container number, seal number, loading date, loaded Goods Lines, and photos.
_Avoid_: 装柜记录

**Order Status**:
The top-level progress state of an Import Order, such as receiving, loaded, at sea, or completed.
_Avoid_: 状态, progress

**Order Stage Progress**:
The percentage completion of the current Import Order status, calculated from the Goods Lines that have reached the relevant logistics state.
_Avoid_: 订单进度, status percent

**Admin User**:
An internal user with full access to Import Orders, Goods Lines, Suppliers, Consignees, warehouses, finance, documents, files, and settings.
_Avoid_: 管理员, business operator

**Warehouse User**:
An internal warehouse user who can view Import Orders and update Goods Line receiving/logistics information, but cannot access finance, customer pricing, document settings, or system settings.
_Avoid_: 仓库员, warehouse admin

**Goods Logistics Status**:
The per-Goods Line logistics state, such as not shipped, domestic shipped, received, moved to port warehouse, or loaded.
_Avoid_: 物流状态, arrival status

**Compliance Requirement**:
A required certificate, inspection, or declaration tied to a Goods Line or Import Order, such as certificate of origin or quarantine inspection.
_Avoid_: 质检要求, inspection

**Export Documents**:
The generated commercial and shipping document set for an Import Order, including invoice and packing list.
_Avoid_: 单证, docs

**Supporting Compliance File**:
An uploaded external certificate, inspection report, or declaration file required for a Goods Line or Import Order. CargoPilot tracks these files but does not generate them in the MVP.
_Avoid_: 产地证, 检验证书, certificate

**Target Markup**:
The intended price increase applied to a Goods Line before quoting the customer. It can be adjusted when the calculated customer price is too high or too low.
_Avoid_: 加价率, markup rule

**Customs English Name**:
The English product name used on Export Documents and customs-facing records. It may differ from the customer-facing English product name.
_Avoid_: 报关英文品名

**Domestic Tracking Number**:
A supplier-provided China domestic logistics number tied to one Goods Line delivery batch.
_Avoid_: 物流单号, tracking number

**Receiving Record**:
A warehouse record of goods physically received against a Goods Line or Domestic Tracking Number, including received cartons, package condition, photos, and notes.
_Avoid_: 收货记录, arrival record

**Arrival Exception**:
A structured receiving problem such as missing cartons, extra cartons, damage, unclear Shipping Mark, wrong goods, or package data mismatch.
_Avoid_: 异常, problem, issue

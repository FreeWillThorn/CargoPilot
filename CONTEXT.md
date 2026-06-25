# CargoPilot

CargoPilot manages China-sourced export orders for European customers, from supplier purchasing through warehouse receiving, container loading, sea freight, and export document generation.

## Language

English domain terms are canonical for code and technical documents. Browser UI labels are Chinese-first and are mapped in `docs/modules/user-interface.md`.

**Order Management**:
The main operational area for finding, reviewing, and opening Import Orders. It is a workflow area, not a separate domain entity.
_Avoid_: Goods Line module, order table module

**Order Detail**:
The workspace for one selected Import Order where child work such as Goods Lines, quote/profit, receiving, loading, documents, files, and history is managed.
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

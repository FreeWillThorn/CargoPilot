# Section-Based Workflow Navigation

CargoPilot's left navigation uses workflow sections: Dashboard, 订单详情, 货物详情, 仓库盘点, 海运单证, 成本利润, and 基础资料. Each workflow section has a top context selector such as Import Order, Warehouse, or master-data type, then shows the objects and actions relevant to that selected context.

订单详情 owns order-level data and order CRUD, but not customer master-data CRUD. 货物详情 owns Goods Line detail, logistics status, product fields, supplier selection, Goods Line Excel import, and Goods Line CRUD. 仓库盘点 owns Warehouse inventory and receiving workflows, but not warehouse master-data CRUD. 基础资料 owns Supplier, Customer/Consignee, Warehouse, and Company/System profile management. This keeps operational workflow actions in their workflow sections while putting shared master data in one predictable Admin-only section.

基础资料 stays last in the Admin User navigation because it is a supporting master-data area rather than a daily shipment workflow. Its internal Supplier, Customer, Warehouse, and Company Information blocks render inside scrollable containers to avoid creating an excessively tall page.

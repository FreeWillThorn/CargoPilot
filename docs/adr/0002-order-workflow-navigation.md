# Section-Based Workflow Navigation

CargoPilot's left navigation uses workflow sections: Dashboard, 订单详情, 货物详情, 仓库盘点, 海运单证, and 成本利润. Each section has a top context selector such as Import Order or Warehouse, then shows the objects and actions relevant to that selected context.

订单详情 owns order-level data and order CRUD, including 收货客户 management needed while editing orders. 货物详情 owns Goods Line detail, logistics status, product fields, supplier fields, Goods Line Excel import, and Goods Line CRUD. 仓库盘点 owns Warehouse inventory plus 仓库资料 management. This keeps workflow objects inside the section where users actually operate them.

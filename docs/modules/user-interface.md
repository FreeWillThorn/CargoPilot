# User Interface and Navigation Module

## Scope

Define CargoPilot's browser information architecture, section logic, object actions, and UI language rules.

## Navigation Principle

The left navigation is a set of business workflow sections, not a list of database tables.

Admin User left navigation:

1. Dashboard
2. 订单详情
3. 货物详情
4. 仓库盘点
5. 海运单证
6. 成本利润

Warehouse User left navigation:

1. Dashboard
2. 订单详情
3. 货物详情
4. 仓库盘点

System settings are utility/admin actions, not primary left-navigation sections. 收货客户 belongs in 订单详情, and 仓库资料 belongs in 仓库盘点. 管理/设置 should not be the primary entry for those workflow-owned objects after migration.

## Section Context Rule

Each section owns one main context selector at the top of the page. Changing the selected context changes the tables and actions below it.

| Section | Context selector | Main content |
| --- | --- | --- |
| Dashboard | Optional filters | All active Import Orders, blockers, reminders, and current logistics concentration points |
| 订单详情 | Import Order | All Import Orders, selected Import Order details, order CRUD, and 收货客户 CRUD |
| 货物详情 | Import Order | Goods Lines under the selected Import Order, with product fields, supplier, tracking numbers, Shipping Mark, logistics status, Excel import, and Goods Line CRUD |
| 仓库盘点 | Warehouse | Warehouse information, 仓库资料 CRUD, and all received/inbound goods in that Warehouse, including owning Import Order |
| 海运单证 | Import Order | Document blockers, generated document versions, Commercial Invoice, Packing List, and file downloads for the selected Import Order |
| 成本利润 | Import Order | Costs, charges, quote fields, Target Markup, and profit summary for the selected Import Order |

This means Goods Lines are never a top-level navigation destination, but their detail and CRUD ownership belongs to 货物详情, not 订单详情.

## Section Details

### Dashboard

Dashboard is the overview page. It shows active orders, progress, current logistics point, reminders, blocker counts, and exception counts. Its links open the relevant workflow section with the correct context preselected.

### 订单详情

The first view shows all Import Orders and their statuses. Selecting an Import Order shows its detail panel and order-level actions.

Default order-list columns: 订单号, 收货客户, 目的港, 订单状态, 订单进度, 当前物流点, 预计装柜日, 异常数, 缺资料数.

Default state:

- Show the full Import Order list.
- If no order is selected, show the most recent Import Order detail below the list.
- If an order is selected, show the selected Import Order detail below the list.
- Do not automatically enter edit mode.
- Sort orders by created/updated time descending, with exceptions and near-loading orders pinned above normal orders.

Order summary fields: 订单号, 客户, 目的港, 收货仓, 港口仓, 贸易条款, 预计装柜日, 总货物项, 总箱数, 总体积, 总毛重, and 成本利润入口.

Order-level actions:

- 新增订单
- 编辑订单
- 删除/取消订单
- 更新订单状态
- 新增/编辑/删除收货客户

Admin Users may manually update Order Status. The system should still show suggested status and Order Stage Progress from Goods Lines. Manual status changes are recorded in modification history.

Goods Line detail tables and Goods Line CRUD are owned by 货物详情.

### 货物详情

The top selector chooses an Import Order. The page shows all Goods Lines under that order and their product, supplier, pricing, package, and logistics details.

Default columns: 货物项, 供应商, SKU/型号, 数量, 箱数, 每箱数量, 外箱尺寸(cm), 单箱毛重(kg), CBM, 总毛重(kg), 采购单价, 采购币种, 目标加价率, 销售单价, 销售币种, 麦头, 国内物流单号, 货物物流状态, 操作.

Arrival exceptions belong to 仓库盘点. 货物详情 should not expose an exception column in its normal Goods Line detail table.

Actions:

- 新增货物项
- 编辑货物项
- 删除货物项
- 导入货物清单 Excel
- 更新货物物流状态
- 添加/查看国内物流单号

### 仓库盘点

The top selector chooses a Warehouse. The page shows warehouse details and all inbound/received goods for that Warehouse, including Import Order, Goods Line, Domestic Tracking Number, received cartons, package condition, and Arrival Exception.

Default columns: 订单号, 货物项, 供应商, 麦头, 国内物流单号, 应到箱数, 已收箱数, 包装情况, 异常, 最近入库时间.

Warehouse is required. Status and date are secondary filters. Status options are 待入库, 已入库, 异常, and 全部.

The 待入库 list includes Goods Lines assigned to the selected Receiving Warehouse even before they have a Receiving Record, based on the Import Order's Receiving Warehouse plus Domestic Tracking Number and Shipping Mark data.

Receiving Warehouses and Port Warehouses have separate inventory views. Receiving Warehouse view focuses on supplier arrivals. Port Warehouse view focuses on goods moved to port and waiting for container loading.

Actions:

- 新增/编辑/删除仓库资料
- 登记到货
- 记录包装情况
- 上传/记录到货照片
- 标记到货异常
- 解除到货异常

### 海运单证

The top selector chooses an Import Order. The page shows document readiness, blockers, version history, and downloads.

Default blocks: 订单选择, 单证阻塞项, 商业发票版本, 装箱单版本, 合规文件列表, and 生成按钮.

Only Admin Users can access this section.

Actions:

- 生成草稿商业发票
- 生成正式商业发票
- 生成草稿装箱单
- 生成正式装箱单
- 下载 Excel/PDF
- 上传合规文件

Final documents are blocked by missing required fields. Certificates of origin, inspection certificates, and similar files are uploaded/tracked, not generated.

Supporting compliance files are managed in this section and can attach to the selected Import Order or to a specific Goods Line.

### 成本利润

The top selector chooses an Import Order. The page shows order-level sales total, costs, charges, exchange rates, and profit summary.

Default blocks: 订单利润总览, 成本明细, 客户收费明细, and 汇率/币种提示.

Default view shows the selected Import Order's total profit summary first. Goods-Line-level quote and price details belong in 货物详情, linked from the overview.

Profit base currency is the selected Import Order's customer sales currency. If the order has no sales currency, use the system default sales currency.

Actions:

- 新增成本
- 新增客户收费
- 导出成本利润表

## Object Actions

Create, edit, delete, upload, generate, and status-change actions open from the current section using a modal or side drawer.

Do not force users to leave the current section context for object actions. A modal/drawer must make clear which Import Order, Warehouse, Goods Line, or Document it is editing.

Use right-side drawers for large forms such as Goods Line editing, costs/charges, receiving records, loading records, and document generation. Use centered modals for small confirmations such as delete, cancel, and irreversible status changes.

After a modal or drawer submits successfully, stay in the current Workflow Section and keep the same selected context. Close the modal/drawer and refresh the relevant area.

## Development Order

1. Section navigation shell and base Chinese labels.
2. 订单详情.
3. 货物详情.
4. 仓库盘点.
5. 海运单证.
6. 成本利润.
7. Drawer/modal polish and remaining Chinese label cleanup.

## UI Language

The main browser UI is Chinese-first. Database column names and internal code field names must not be shown directly.

Use Chinese logistics/business labels for normal operations:

| Domain term | UI label |
| --- | --- |
| Import Order | 进口订单 |
| Goods Line | 货物项 |
| Goods Line list/table | 货物明细 |
| Consignee | 收货客户 |
| Supplier | 供应商 |
| Receiving Warehouse | 收货仓库 |
| Port Warehouse | 港口仓库 |
| Warehouse | 仓库 |
| Shipping Mark | 麦头 |
| Domestic Tracking Number | 国内物流单号 |
| Order Status | 订单状态 |
| Goods Logistics Status | 货物物流状态 |
| Target Markup | 目标加价率 |
| Commercial Invoice | 商业发票 |
| Packing List | 装箱单 |
| Export Documents | 单证文件 |
| Supporting Compliance File | 合规文件 |
| Container | 集装箱 |
| Loading Record | 装柜记录 |

English is acceptable only for standard trade/document abbreviations and codes that industry users expect, such as FOB, CIF, HS Code, SKU, CBM, Commercial Invoice, and Packing List. When used in the UI, prefer Chinese first with English in parentheses when clarity helps, for example `商业发票 (Commercial Invoice)`.

## Table Display Rules

Tables show operational summary columns only. They should not expose every database field.

Use detail views, grouped forms, modals, or drawers for dense fields. Field groups should follow the user's task:

- 基本信息
- 供应商与采购
- 报关信息
- 包装尺寸
- 物流状态
- 报价利润
- 文件备注

Long workflow tables must scroll inside their own panel instead of growing the whole page. This applies especially to 货物详情 Goods Line tables and 仓库盘点 inventory tables. The panel height should account for the visible viewport so horizontal scrollbars are reachable without first scrolling the whole page. Dense row editing belongs in drawers/modals; table cells should stay display-first unless a field was explicitly designed as an inline status select.

## Deferred UI Work

The section structure and Chinese-first labels are not deferred. Later UI work can improve styling, drawer polish, responsive behavior, dashboard visualization, and container loading diagrams without changing the section model.

# User Interface and Navigation Module

## Scope

Define CargoPilot's browser information architecture, section logic, object actions, and UI language rules.

## Navigation Principle

The left navigation is a set of business workflow sections, not a list of database tables.

Admin User left navigation:

1. Dashboard
2. 订单项目
3. 货物跟踪
4. 仓库盘点
5. 单证生成
6. 成本利润

Warehouse User left navigation:

1. Dashboard
2. 订单项目
3. 货物跟踪
4. 仓库盘点

Master data and system settings are utility/admin actions, not primary left-navigation sections. They live behind a top-right 管理/设置 menu for Admin Users.

## Section Context Rule

Each section owns one main context selector at the top of the page. Changing the selected context changes the tables and actions below it.

| Section | Context selector | Main content |
| --- | --- | --- |
| Dashboard | Optional filters | All active Import Orders, blockers, reminders, and current logistics concentration points |
| 订单项目 | Import Order | All Import Orders first; selected Import Order detail and its Goods Lines after selection |
| 货物跟踪 | Import Order | Goods Lines under the selected Import Order, with logistics status, supplier, tracking numbers, Shipping Mark, blockers, and exceptions |
| 仓库盘点 | Warehouse | Warehouse information and all received/inbound goods in that Warehouse, including owning Import Order |
| 单证生成 | Import Order | Document blockers, generated document versions, Commercial Invoice, Packing List, and file downloads for the selected Import Order |
| 成本利润 | Import Order | Costs, charges, quote fields, Target Markup, and profit summary for the selected Import Order |

This means Goods Lines are never a top-level CRUD destination. They appear inside 订单项目 and 货物跟踪 as child rows of a selected Import Order.

## Section Details

### Dashboard

Dashboard is the overview page. It shows active orders, progress, current logistics point, reminders, blocker counts, and exception counts. Its links open the relevant workflow section with the correct context preselected.

### 订单项目

The first view shows all Import Orders and their statuses. Selecting an Import Order shows its detail panel and Goods Line list.

Order-level actions:

- 新增订单
- 编辑订单
- 删除/取消订单
- 更新订单状态

Goods Line actions inside the selected Import Order:

- 新增货物项
- 编辑货物项
- 删除货物项
- 导入客户采购清单
- 导入供应商包装物流表

### 货物跟踪

The top selector chooses an Import Order. The page shows all Goods Lines under that order and their logistics progress.

Actions:

- 更新货物物流状态
- 添加/查看国内物流单号
- 标记/解除到货异常
- 跳转到仓库盘点或订单项目中的对应对象

### 仓库盘点

The top selector chooses a Warehouse. The page shows warehouse details and all inbound/received goods for that Warehouse, including Import Order, Goods Line, Domestic Tracking Number, received cartons, package condition, and Arrival Exception.

Actions:

- 登记到货
- 记录包装情况
- 上传/记录到货照片
- 标记到货异常
- 解除到货异常

### 单证生成

The top selector chooses an Import Order. The page shows document readiness, blockers, version history, and downloads.

Actions:

- 生成草稿商业发票
- 生成正式商业发票
- 生成草稿装箱单
- 生成正式装箱单
- 下载 Excel/PDF
- 上传合规文件

Final documents are blocked by missing required fields. Certificates of origin, inspection certificates, and similar files are uploaded/tracked, not generated.

### 成本利润

The top selector chooses an Import Order. The page shows Goods Line quote inputs, costs, charges, exchange rates, and profit summary.

Actions:

- 调整目标加价率
- 调整销售单价
- 新增成本
- 新增客户收费
- 导出成本利润表

## Object Actions

Create, edit, delete, upload, generate, and status-change actions open from the current section using a modal or side drawer.

Do not force users to leave the current section context for object actions. A modal/drawer must make clear which Import Order, Warehouse, Goods Line, or Document it is editing.

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

## Deferred UI Work

The section structure and Chinese-first labels are not deferred. Later UI work can improve styling, drawer polish, responsive behavior, dashboard visualization, and container loading diagrams without changing the section model.

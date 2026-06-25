# User Interface and Navigation Module

## Scope

Define CargoPilot's browser information architecture, page organization, object actions, and UI language rules.

## Navigation Principle

CargoPilot is organized around the Import Order workflow, not around database tables.

Goods Lines are not a top-level peer of Import Orders. A user first enters **订单管理**, sees all Import Orders and their current status, then opens one Import Order to manage that order's Goods Lines, quote/profit, receiving, loading, documents, files, and history.

Cross-order pages are allowed only when the work is naturally cross-order:

- Dashboard for overview, blockers, and reminders.
- Warehouse Receiving for fast receiving search by order number, Domestic Tracking Number, or Shipping Mark.
- Tracking for exception/delay triage across Import Orders.
- Master Data for Suppliers, Consignees, and Warehouses.
- Settings for system defaults.

## Primary Navigation

Admin User navigation:

1. 工作台
2. 订单管理
3. 仓库收货
4. 物流追踪
5. 基础资料
6. 系统设置

Warehouse User navigation:

1. 工作台
2. 订单管理
3. 仓库收货

Warehouse Users must not see finance, quote/profit, customer price, Supplier/Consignee management, Export Documents, or Settings navigation.

## Import Order Detail

Opening an Import Order shows the selected order as the page context. All child work stays under this page.

Recommended tabs:

1. 订单概览
2. 货物明细
3. 采购与Excel
4. 报价利润
5. 仓库收货
6. 装柜运输
7. 单证文件
8. 修改历史

Goods Line creation and editing happen from the **货物明细** tab. They must not appear as a separate top-level CRUD module.

## Object Actions

Create, edit, delete, upload, generate, and status-change actions should be launched from the current object's page using a modal or side drawer.

Examples:

- Add Goods Line from an Import Order detail page.
- Edit a Goods Line from the Import Order's 货物明细 tab.
- Add a cost or charge line from the Import Order's 报价利润 tab.
- Generate Commercial Invoice or Packing List from the Import Order's 单证文件 tab.
- Add a Container or Loading Record from the Import Order's 装柜运输 tab.

Do not force users to leave the current Import Order context for child-object actions.

## UI Language

The main browser UI is Chinese-first. Database column names and internal code field names must not be shown directly.

Use Chinese logistics/business labels for normal operations:

| Domain term | UI label |
| --- | --- |
| Import Order | 进口订单 |
| Goods Line | 货物项 |
| Goods Line list/tab | 货物明细 |
| Consignee | 收货客户 |
| Supplier | 供应商 |
| Receiving Warehouse | 收货仓库 |
| Port Warehouse | 港口仓库 |
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

The first MVP may keep plain styling, but the structure above is not deferred. Later UI work can improve visual design, drawer polish, responsive behavior, dashboard visualization, and container loading diagrams without changing the object hierarchy.

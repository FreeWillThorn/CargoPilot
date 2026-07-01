# 订单智能体 Demo Test Pack

## Purpose

Use this pack before an interview demo. The primary story is order creation from messy supplier material. The secondary story is selected-order risk prompting.

## Automated Coverage

Run:

```bash
python3 -m unittest discover -s tests
```

The mocked DeepSeek tests cover:

- primary order creation flow: Task Understanding -> Data Entry -> editable drafts -> Admin confirmation -> Import Order and Goods Lines created
- selected-order update flow: update drafts affect only the selected Import Order
- selected-order risk flow: Task Understanding -> Order Risk Agent -> supplier-grouped risk suggestions
- live model requirement: model failure creates no local fallback drafts or risk findings
- retained conversations: messages, source summaries, trace steps, and results survive refresh
- UI safeguards: long conversation list, long trace, and wide draft cards use scroll containers

## Manual Real-DeepSeek Setup

1. Open `基础资料`.
2. Configure DeepSeek:
   - API 地址: `https://api.deepseek.com`
   - 模型: `deepseek-reasoner`
   - API Key: use a valid temporary key
3. Run connection verification. Do not disable certificate validation.
4. Start the app and log in as Admin.
5. Open `订单智能体`.

## Primary Interview Demo

This is the scenario to demonstrate first.

1. Start with no Import Order selected.
2. Create a conversation titled `根据供应商资料创建订单`.
3. Upload supplier Excel, PDF, or paste chat text. If no file is handy, paste:

```text
供应商 ABC 发来货物资料：
客户 Eldar，目的港 Rotterdam，贸易条款 FOB。
货物 A001 白色陶瓷杯，100 箱，每箱 12 个，单箱毛重 18kg。
货物 A002 黑色陶瓷杯，80 箱，每箱 6 个，单箱毛重 22kg。
```

4. Enter: `帮我根据这些资料创建一个订单`.
5. Checkpoints:
   - Agent Processing Trace shows local parsing, Task Understanding Agent, and Data Entry Agent.
   - Result area shows editable `订单创建草稿`, `货物项草稿`, `供应商主数据草稿`, and `客户主数据草稿`.
   - If required data is missing, the conversation remains open and waits for more input.
   - Draft tables are scrollable at 1280px width.
   - Raw model responses are available in collapsed `原始信息` or `查看模型结构化原始返回`, not shown as the main UI.
6. Click `确认执行草稿`.
7. Checkpoints:
   - The page stays in `订单智能体`.
   - The summary says the Import Order was created.
   - No automatic jump to `订单详情`.
   - The same conversation remains in the left conversation list.

## Secondary Risk Demo

1. Select an existing Import Order with Goods Lines.
2. Enter: `帮我检查这个订单清关和单证风险`.
3. Checkpoints:
   - Task Understanding Agent selects risk prompting only.
   - Order Risk Agent runs with selected order context.
   - Risks are grouped by Supplier when known.
   - Each risk shows basis, affected goods, suggested documents/actions, confidence, and review need.
   - Risk categories are model-determined and open-ended.
   - `忽略` changes a risk to `已忽略`.
   - No system Change Draft is created.

## Failure And Retry Demo

1. Temporarily remove or invalidate the DeepSeek key.
2. Run either primary or secondary prompt.
3. Checkpoints:
   - Failed Agent Processing Trace step is visibly marked failed.
   - Result area does not show partial successful conclusions.
   - No local fallback draft or risk appears.
   - `重试失败步骤` is visible.
4. Restore the valid key and click `重试失败步骤`.
5. Checkpoints:
   - The retry reuses the same conversation and input batch.
   - The trace records the retry.
   - The successful model output replaces the failed user-facing result.

## 1280px UI Smoke

At browser width around 1280px:

- Left conversation list scrolls.
- Current conversation workspace scrolls.
- Agent Processing Trace can show many steps without pushing controls off screen.
- Editable draft cards do not expose raw database field names as the primary user language.
- Long raw JSON is hidden behind collapsed details.

## Fallback Demo Path

Keep `AI资料收集箱` available. If live Order Agent demo fails because of network or model availability, use `AI资料收集箱` as the fallback proof that CargoPilot can structure messy supplier data.

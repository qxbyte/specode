# distill — Obsidian markdown 模板参考（5 类）

> distill 是 **md-only** 的 Obsidian 知识整理器（5.0.1+）：host agent **直接撰写
> markdown**，没有 yml、没有 `codemap knowledge write` 写入器、不碰 `.ai-memory/`。
> 本文件给出 5 个类别各自的 **md frontmatter + 正文结构**模板。流程见 `SKILL.md`。
>
> 旧的 yml schema / `.ai-memory/knowledge/` 双产物路径 / codemap 写入器已在 5.0.1
> 移除（其唯一消费者 `codemap recall` 早在 v4.0.0 删除，yml 输出无人读取）。

---

## 类别 → 目录 → 前缀 总览

所有产物都落在 `--target-dir`（默认 `/Volumes/External HD/Obsidian/Notes/11-KnowledgeBase/`）下的 `<slug>/<category>/`：

| category | 目录 | id 前缀 | 含义 |
|---|---|---|---|
| `rules` | `<target-dir>/<slug>/rules/` | `rule-` | 业务规则 / 全局机制 |
| `business` | `<target-dir>/<slug>/business/` | `biz-` | 业务流程 / 功能页 |
| `modules` | `<target-dir>/<slug>/modules/` | `mod-` | 表 / 字段 / 调用链 / 模块地图 |
| `cases` | `<target-dir>/<slug>/cases/` | `case-` | 历史案例（每 spec 必产 1 篇，id = `<slug>`） |
| `pitfalls` | `<target-dir>/<slug>/pitfalls/` | `pit-` | 可复用的失败 / 修复经验 |

文件名 = `<knowledge_id>.md`，`knowledge_id = <prefix>-<kebab(title)>`（cases 为 `case-<slug>`）。

---

## 公共 Obsidian frontmatter

每篇 md 顶部用统一的 Obsidian 友好 frontmatter（与 `SKILL.md` Step 4 一致）：

```markdown
---
title: <中文标题>
category: <rules|business|modules|cases|pitfalls>
spec_id: <slug>
created_at: <YYYY-MM-DD>
tags: [tag1, tag2]
related: [[id1]], [[id2]]     # 可选：同 wiki 内其它知识点的 [[wikilink]]
---
```

> 可按需追加任何 Obsidian 兼容字段（如 `related_requirements: [121659]`、`related_code:` 路径列表），但保持上面 6 个为基础集。正文用散文 / 表格 / ascii / `[[wikilink]]`，面向人读。

---

## 1. `rules/` — 业务规则 / 全局机制

正文段：`一句话规则` / `为什么有这条规则` / `触发条件` / `例外` / `在代码哪些层强制` / `关联`。

```markdown
---
title: 优惠券与积分抵扣互斥规则
category: rules
spec_id: REQ-2024-0078
created_at: 2026-06-26
tags: [coupon, points, mutex]
related: [[biz-order-checkout]], [[pit-coupon-null-amount]]
---

# 优惠券与积分抵扣互斥规则

## 一句话规则

同一笔订单中，**优惠券和积分抵扣不能同时使用**。

## 为什么有这条规则

避免用户双重优惠导致亏损。运营 / 财务核算上预设的优惠成本上限是按单一优惠通道算的，叠加会击穿成本红线。

## 触发条件

当且仅当下面**全部条件**满足时触发互斥校验：

- 用户在下单页同时勾选「使用优惠券」与「使用积分」
- 订单状态尚未提交支付

## 例外

| 例外场景 | 处理方式 | 参考 |
|---|---|---|
| VIP 等级 ≥ 8 | 允许叠加 | [[rule-vip-privilege]] |
| 平台促销活动期间 | 由活动 flag 决定，临时覆盖 | 见活动配置文档 |

## 在代码哪些层强制

- **service 层**：`validateCouponAndPoints()` 抛 `ConflictException`（src/modules/order/validators.js）
- **前端**：`OrderPricing.vue` 的两个 checkbox 互斥禁用（视觉先拦截，但不能依赖前端做唯一校验）

## 关联

- 业务流程：[[biz-order-checkout]]
- 历史案例：[[case-REQ-2024-0078]]
- 相关坑点：[[pit-coupon-null-amount]]
```

---

## 2. `business/` — 业务流程 / 功能页

正文段：`概述` / `触发与终止` / `步骤`（ascii 流程图）/ `数据流约束` / `关键 UI 约束（如这是功能页）` / `关联`。

```markdown
---
title: Q01 承保送收付入库流程
category: business
spec_id: 121659
created_at: 2026-06-26
tags: [Q01, underwrite, payment, SfCreditMain]
related: [[mod-sf-credit-main]], [[rule-paymentcomcode-fallback]]
---

# Q01 承保送收付入库流程

## 概述

承保系统下单完成后，调用 Q01 接口把核保信息推送给收付系统；收付系统根据 paymentComCode 判断是否需要覆盖赋值，最终在 SfCreditMain + SfBusinessCredit 双表落库，并向 ATP 推送一条变更通知。

## 触发与终止

- **触发**：承保系统下单完成（policy 状态 = `underwritten`）
- **终止**：SfCreditMain + SfBusinessCredit 双表写入成功 + ATP 推送回 ACK

## 步骤

```
1. 承保系统 ──Q01──► 收付系统
                       │  inputs: policyNo, paymentComCode, codInd
                       ▼
2. 收付系统 判断 paymentComCode
       ├─ paymentComCode != centerCode ──► 覆盖为 centerCode（见 rule-paymentcomcode-fallback）
       └─ paymentComCode == centerCode ──► 保留原值
                       │
                       ▼
3. 写 SfCreditMain（PAYSTATUS = 0 未处理）
4. 写 SfBusinessCredit（CNY_PAY_AMOUNT 等）
5. 推 ATP 通知
```

## 数据流约束

- `Q01 → SfCreditMain.PAYSTATUS = 0`（强制初始值）
- **Q17 / Q01 入库顺序**：Q17 必须先于 Q01 落库，否则 Q01 找不到上游单据

## 关键 UI 约束（如这是功能页）

| UI 元素 | 规则 |
|---|---|
| 保存按钮 | 未选优惠券时灰禁用 |

## 关联

- 数据模型：[[mod-sf-credit-main]]
- 关联规则：[[rule-paymentcomcode-fallback]]
- 历史案例：[[case-121659]]
```

---

## 3. `modules/` — 表 / 字段 / 调用链 / 模块地图

正文段：`概述` / `表结构（关键字段）`（枚举全列，含已作废值并标注）/ `分库分表 / 路由` / `关联表 ascii` / `调用链`（如 scope=call_chain）/ `关联`。

```markdown
---
title: SfCreditMain 字段说明
category: modules
spec_id: 121659
created_at: 2026-06-26
tags: [SfCreditMain, table, fields, sharding]
related: [[biz-q01-underwrite-to-payment]], [[pit-cny-pay-amount-misplace]]
---

# SfCreditMain 字段说明

## 概述

`SfCreditMain` 是收付主表，承载一笔收付的整体状态。多个收付明细（`SfBusinessCredit`）共享同一条 `SfCreditMain`。

## 表结构（关键字段）

### PAYSTATUS — 支付状态枚举

| 值 | 含义 | 备注 |
|---|---|---|
| 0 | 未处理 | 入库默认值；Q01/Q02 后即为 0 |
| 1 | 已确认 | 财务确认后流转 |
| 3 | 部分确认 | **已作废**，保留是为兼容历史数据 |
| 4 | 已收款 | |
| 6 | 已退款 | |
| 7 | 已关闭 | 终态 |

### CNY_PAY_AMOUNT — 人民币金额

| 类型 | 归属 | 注意 |
|---|---|---|
| DECIMAL(18,2) | **实际归属 SfBusinessCredit，非 SfCreditMain** | 历史 SQL 误写在 SfCreditMain 上的需修正 |

## 分库分表 / 路由

| 项 | 值 |
|---|---|
| 分表键 | `underwriteEndDate` |
| 路由组件 | `SfRouter` |
| 所在库 | 主库 |

## 关联表 ascii

```
SfCreditMain.creditingNo (1) ─────► (N) SfBusinessCredit.creditingNo
                                          │
                                          ▼
                                    SfPolicyPayment（主库, SfRouter 路由）
```

## 关联

- 业务流程：[[biz-q01-underwrite-to-payment]]
- 相关坑点：[[pit-cny-pay-amount-misplace]]
```

---

## 4. `cases/` — 历史案例（每个 spec 必产 1 篇）

正文段：`实现摘要` / `改动文件` / `关键决策`（配理由）/ `实施中遇到的 bug` / `教训（lessons learned）` / `Review 反馈` / `验收`。id 固定为 `case-<slug>`，重跑 distill 默认整篇 overwrite（case 描述的就是"这次实现"）。

```markdown
---
title: 订单列表增加按金额区间筛选
category: cases
spec_id: REQ-2024-0078
created_at: 2026-06-26
tags: [order, query, amount-range]
related: [[pit-amount-null-validation]]
---

# case REQ-2024-0078 — 订单列表增加按金额区间筛选

## 实现摘要

在 `OrderQueryService` 增加 `amountMin` / `amountMax` 两个查询参数；前端在 `admin/order-list.vue` 加范围输入组件；金额计算和比较全部用 `BigDecimal`。复用已有的权限校验 middleware，未新增权限点。

## 改动文件

- `src/modules/order/query.js`
- `src/modules/admin/order-list.vue`

## 关键决策

| 决策 | 理由 |
|---|---|
| 使用 BigDecimal 避免浮点精度 | 金额查询历史踩过 `0.1 + 0.2 = 0.30000000000004` 的坑 |
| 复用已有权限校验中间件 | 保持鉴权一致，不另起 middleware；少引入潜在差异 |

## 实施中遇到的 bug

- 初始实现未处理金额为 `null` 的情况，validation 直接 NPE → 已修，详见 [[pit-amount-null-validation]]

## 教训（lessons learned）

- **涉及金额查询时，必须考虑 null 和 0 的边界**——前端可能不传，schema 要显式允许 `null` 或给默认 `0`
- 浮点不用 `BigDecimal` 就是慢性自杀

## Review 反馈

| 发现 | 严重度 | 处理 |
|---|---|---|
| 重复的金额校验逻辑 | minor | 已抽到 amountValidator 工具方法 |

## 验收

- 状态：**passed**
- 验证命令：`pytest tests/modules/order/test_query.py`
```

---

## 5. `pitfalls/` — 坑点（可复用的失败 / 修复经验）

正文段四件套必填：`适用范围` / `症状` / `根因` / `修复` / `怎么避免再犯` / `影响范围` / `历史`。写不全不算合格。

```markdown
---
title: 金额参数 null 未兜底导致 NPE
category: pitfalls
spec_id: REQ-2024-0078
created_at: 2026-06-26
tags: [amount, null-safety, npe, validation]
related: [[case-REQ-2024-0078]]
---

# pit — 金额参数 null 未兜底导致 NPE

## 适用范围

电商订单计算价格、查询订单列表等**所有涉及金额的接口**。任何接受 `amount` 类参数但未明确标 required 的地方都可能踩。

## 症状

调用方未传 `amount` 字段时，`BigDecimal.add` 抛 `NullPointerException`；前端表现为接口 **500**，无明确业务错误码，用户看到的是"系统繁忙"。

## 根因

1. validator 默认假设 `amount` 必非 `null`，没走前置 `Objects.requireNonNullElse(amount, BigDecimal.ZERO)`
2. OpenAPI schema 既没把 `amount` 标 `required: true`，也没给 `default: 0`——双重失守

## 修复

```java
// 1. validator 加兜底
BigDecimal min = Optional.ofNullable(amountMin).orElse(BigDecimal.ZERO);
BigDecimal max = Optional.ofNullable(amountMax).orElse(BigDecimal.valueOf(Long.MAX_VALUE));

// 2. schema 显式标 nullable + default
//    amountMin: { type: number, nullable: true, default: 0 }
//    amountMax: { type: number, nullable: true, default: 999999999 }
```

## 怎么避免再犯

- 新接口涉及金额查询时，**必须**在 review 时核对 null/0 兜底逻辑
- PR 模板加 checklist：
  - [ ] 金额参数是否处理 `null`？
  - [ ] schema 是否显式标 nullable / default？

## 影响范围

- `src/modules/order/query.js`
- `src/modules/order/calculator.js`

## 历史

| 时间 | spec | 备注 |
|---|---|---|
| 首次踩到 | [[case-REQ-2024-0078]] | 订单按金额区间筛选 |
| 再次踩到 | REQ-2024-0092 | 退款金额计算（已合并教训） |
```

---

## 各 md 段的内容来源对照

| 段 | 主要 source | 备注 |
|---|---|---|
| frontmatter：`spec_id` / `tags` / `related` | spec 目录 + frontmatter | spec_id = slug；related 由 host agent 据本批候选互链 |
| `rules.*` | `requirements.md` 业务约束 / `design.md` 校验设计 | 抽"X 时不能 Y"型句子 |
| `business.*` | `design.md` 时序图 / 流程图 / `requirements.md` 场景 | 步骤化为 ascii 流程 |
| `modules.*` | `design.md` 数据模型 / 接口设计 | 字段枚举 / 调用链 / 分库分表键 |
| `cases.*` | `implementation-log.md` + `bugfix` + `tests` + `acceptance` | **每 spec 必产 1 篇** |
| `pitfalls.*` | `implementation-log.md` + `bugfix` | 仅"有复用价值的坑"独立成篇；临时调试不纳入 |

---

## 同名升级规则（md）

如目标目录已有同 `knowledge_id` 的 md：

1. `Read` 原文件。
2. **不重写**结构性内容（`title` / 一句话规则 / 关键决策 等）。
3. **追加**：本次 spec 的相关需求号、新增的关联 `[[wikilink]]`、坑点的"再次踩到"行。
4. **冲突时**：若本次新信息与原文相悖，`AskUserQuestion` 让用户选"覆盖 / 新建 `-v2` 后缀文件 / 跳过"。
5. **cases/case-* 特例**：同一 spec 重新跑 distill 默认整篇 overwrite（不走 append）——case 描述的就是"这次实现"，重跑意味着重写。

---

## 深度标准（写得多深算合格）

- **modules 类**：字段枚举全列（含已作废值并标注）；分库分表键明确（如 `分表键 underwriteEndDate`）；调用链含完整类路径 + 方法名。
- **rules 类**：触发条件精确到字段比较；列出反例 / 边界条件；标注在代码哪一层强制。
- **business 类**：每步标注 actor + action + 分支；功能页含 UI 约束表。
- **cases 类**：关键决策配理由；遇到的 bug 含表面症状；教训是一句结论。
- **pitfalls 类**：`症状` + `根因` + `修复` + `预防` 四件套必填，写不完不算合格。

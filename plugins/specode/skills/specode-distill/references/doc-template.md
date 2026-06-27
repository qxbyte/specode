# specode-distill — 字段参考（payload `fields` + md 正文）

> **重要（FIX-2）**：specode-distill **不再手写 yml**。它构造 *content payload*
> 交给单一写入器 `codemap knowledge write`（见 `SKILL.md` Step 5）。本文件因此
> 是**字段参考**：每类 payload 的 `fields` 应包含哪些语义字段、md 正文长什么样。
>
> 由**写入器**自动盖章、**不要**放进 `fields` 的字段：
> `schema_version` / `knowledge_id` / `type` / `version` / `created_at` /
> `updated_at`（写入器据 category + spec_id/title/signature 推导 id、盖日期、
> 按同 id 合并规则升 version）。
>
> 由 **LLM 提供**：
> - `fields`：下面各类列出的语义字段（`statement` / `why` / `steps` /
>   `implementation_summary` / `symptom` / ... ）。
> - `md_body`：人读叙事正文（散文 / ascii 调用链 / `[[wikilink]]`），写入器逐字
>   写进孪生 md 的机器渲染 frontmatter 之下（方案A）。
>
> 下面每类的 "yml schema" 段落即该类 `fields` 的字段集；"md 模板" 段即 `md_body`
> 的推荐结构。**fallback**（写入器不可用）时才需按完整 yml schema 手写双产。


---

## 类别 → 目录 → 前缀 总览

| category | yml 目录 | md 目录 | id 前缀 | type |
|---|---|---|---|---|
| `rules` | `.ai-memory/knowledge/rules/` | `knowledge-base/rules/` | `rule-` | `business_rule` |
| `business` | `.ai-memory/knowledge/business/` | `knowledge-base/business/` | `biz-` | `business_process` |
| `modules` | `.ai-memory/knowledge/modules/` | `knowledge-base/modules/` | `mod-` | `module_map` |
| `cases` | `.ai-memory/knowledge/cases/` | `knowledge-base/cases/` | `case-` | `case` |
| `pitfalls` | `.ai-memory/knowledge/pitfalls/` | `knowledge-base/pitfalls/` | `pit-` | `pitfall` |

---

## 公共字段（5 类 yml 通用）

```yaml
schema_version: "1.0"
knowledge_id: <prefix>-<kebab-slug>           # 与文件名 stem 一致
type: <见上表>                                # 与目录一一对应
version: 1                                    # 同 id 升级 +1
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
status: active                                # active / deprecated / draft
confidence: high                              # high / medium / low
source_spec: <specsRoot>/<slug>               # 相对或绝对都行，按 host agent 习惯
source_files:
  - requirements.md
  - design.md
  - implementation-log.md
related_requirements:                         # spec_id / 需求号 列表
  - REQ-2024-0078
related_knowledge:                            # 同 .ai-memory/knowledge/ 内其它 .yml 的 knowledge_id
  - mod-order-pricing
  - rule-coupon-points-mutex
related_code:                                 # codemap entity_id 或 file/entity 对
  - file: src/modules/order/pricing.js
    entity: calculateOrderPrice
    line_range: [120, 180]
tags:
  - coupon
  - pricing
```

公共 md frontmatter（最小，避免和正文叙事冗余）：

```markdown
---
knowledge_id: <prefix>-<kebab-slug>
type: <同 yml>
version: 1
updated_at: YYYY-MM-DD
tags: [coupon, pricing]
related_requirements: [REQ-2024-0078]
related_knowledge: [mod-order-pricing]
related_code:
  - file: src/modules/order/pricing.js
    entity: calculateOrderPrice
---
```

> md 不重复 yml 中可派生的字段（source_files / status / confidence / created_at）；如需查阅打开同名 yml 即可。

---

## 1. `rules/` — 业务规则 / 全局机制

### 1.1 yml schema

公共字段之外加：

```yaml
statement: "优惠券和积分抵扣不能同时使用"
why: "避免用户双重优惠导致亏损"
trigger_conditions:
  - "下单时同时勾选优惠券和使用积分"
exceptions:
  - "VIP 等级 ≥ 8 的用户例外，见 rule-vip-privilege"
enforcement:
  - "service 层 validateCouponAndPoints() 抛异常"
  - "前端 OrderPricing.vue 互斥禁用"
```

### 1.2 md 模板

```markdown
---
knowledge_id: rule-coupon-points-mutex
type: business_rule
version: 1
updated_at: 2026-06-26
tags: [coupon, points, mutex]
related_requirements: [REQ-2024-0078]
related_knowledge: [biz-order-checkout]
related_code:
  - file: src/modules/order/validators.js
    entity: validateCouponAndPoints
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

### 2.1 yml schema

```yaml
title: "Q01 承保送收付入库流程"
trigger: "承保系统下单完成"
end_state: "SfCreditMain + SfBusinessCredit 双表落库 + 推 ATP"
steps:
  - n: 1
    actor: "承保系统"
    action: "调用 Q01 接口"
    inputs: [policyNo, paymentComCode, codInd]
  - n: 2
    actor: "收付系统"
    action: "判断 paymentComCode 是否需要覆盖赋值"
    branches:
      - condition: "paymentComCode != centerCode"
        next: "覆盖为 centerCode"
      - condition: "paymentComCode == centerCode"
        next: "保留原值"
data_flow:
  - "Q01 → SfCreditMain.PAYSTATUS = 0"
  - "Q17 / Q01 入库顺序约束：Q17 先于 Q01"
ui_constraints:                                # 功能页特有；非功能页可空
  - element: "保存按钮"
    rule: "未选优惠券时灰禁用"
```

### 2.2 md 模板

```markdown
---
knowledge_id: biz-q01-underwrite-to-payment
type: business_process
version: 1
updated_at: 2026-06-26
tags: [Q01, underwrite, payment, SfCreditMain]
related_requirements: [121659, 123000]
related_knowledge: [mod-sf-credit-main, rule-paymentcomcode-fallback]
related_code:
  - file: src/main/java/com/pointwise/.../payment/biz/SfCreditMainBizImpl.java
    entity: handleQ01Input
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
- 历史案例：[[case-121659-implementation]]
```

---

## 3. `modules/` — 表 / 字段 / 调用链 / 模块地图

### 3.1 yml schema

```yaml
title: "SfCreditMain 字段说明"
scope: table                                  # table / call_chain / module / api
entity_kind: table
primary_entity: tbl-sf_credit_main
columns:                                      # 仅 scope=table 时
  - name: PAYSTATUS
    type: TINYINT
    enum:
      - value: 0
        meaning: 未处理
      - value: 1
        meaning: 已确认
      - value: 3
        meaning: 部分确认（已作废，保留兼容）
  - name: CNY_PAY_AMOUNT
    type: DECIMAL(18,2)
    note: "实际归属 SfBusinessCredit，非 SfCreditMain 字段"
shard:                                        # 分库分表
  key: underwriteEndDate
  routing: SfRouter
  database: 主库
call_chain:                                   # 仅 scope=call_chain 时
  - step: "前端 SfPlanAuthority.vue:142"
    next: "POST /api/payment/authorityQuery"
  - step: "Controller PaymentController.authorityQuery"
    next: "Service authorityQueryByPaymentNo"
```

### 3.2 md 模板

```markdown
---
knowledge_id: mod-sf-credit-main
type: module_map
version: 1
updated_at: 2026-06-26
tags: [SfCreditMain, table, fields, sharding]
related_requirements: [121659, 123000]
related_knowledge: [biz-q01-underwrite-to-payment]
related_code:
  - file: src/main/resources/mapper/SfCreditMainMapper.xml
  - entity: tbl-sf_credit_main
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

### 4.1 yml schema

```yaml
case_id: case-REQ-2024-0078
spec_id: REQ-2024-0078                        # 与 spec 目录名对齐
title: "订单列表增加按金额区间筛选"
implementation_summary: |
  在 OrderQueryService 增加 amountMin / amountMax 参数；
  前端 admin/order-list.vue 加范围输入框；使用 BigDecimal。
changed_files:
  - src/modules/order/query.js
  - src/modules/admin/order-list.vue
key_decisions:
  - decision: "使用 BigDecimal 避免浮点精度问题"
    reason: "金额查询历史踩过浮点 0.1+0.2=0.30000000000004 的坑"
  - decision: "复用已有权限校验中间件"
    reason: "保持鉴权一致；不另起 middleware"
bugs_encountered:
  - "初始实现未处理金额为 null 的情况，validation 直接 NPE"
lessons:
  - "涉及金额查询时，必须考虑 null 和 0 的边界"
review_findings:
  - finding: "重复的金额校验逻辑"
    severity: minor
    action: "已抽到 amountValidator 工具方法"
acceptance_status: passed                     # passed / failed / partial
```

### 4.2 md 模板

```markdown
---
knowledge_id: case-REQ-2024-0078
type: case
version: 1
updated_at: 2026-06-26
tags: [order, query, amount-range]
related_requirements: [REQ-2024-0078]
related_knowledge: [pit-amount-null-validation]
related_code:
  - file: src/modules/order/query.js
  - file: src/modules/admin/order-list.vue
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

### 5.1 yml schema

```yaml
pit_id: pit-amount-null-validation
title: "金额参数为 null 时未做兜底校验导致 NPE"
context: "电商订单计算价格、查询订单列表等所有涉及金额的接口"
symptom: |
  调用方未传 amount 字段时，BigDecimal.add 抛 NullPointerException；
  前端表现为接口 500，无明确错误码。
root_cause: |
  validator 假设 amount 必非 null，未走前置 Objects.requireNonNullElse；
  schema 未把 amount 标记为 required 也未给 default。
fix:
  - "validator 内 amountMin = Optional.ofNullable(amountMin).orElse(BigDecimal.ZERO)"
  - "OpenAPI schema 把 amountMin / amountMax 显式标 nullable=true + default=0"
prevention:
  - "新接口涉及金额查询时，必须 review null/0 兜底逻辑"
  - "PR 模板加一条 checklist: '金额参数是否处理 null'"
affects:                                      # 文件路径或 entity_id
  - src/modules/order/query.js
  - src/modules/order/calculator.js
first_seen_in: REQ-2024-0078
seen_again_in:                                # 后续重复踩到时追加
  - REQ-2024-0092
```

### 5.2 md 模板

```markdown
---
knowledge_id: pit-amount-null-validation
type: pitfall
version: 2
updated_at: 2026-06-26
tags: [amount, null-safety, npe, validation]
related_requirements: [REQ-2024-0078, REQ-2024-0092]
related_knowledge: [case-REQ-2024-0078]
related_code:
  - file: src/modules/order/query.js
  - file: src/modules/order/calculator.js
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

## 各 yml 段 / md 段的内容来源对照

| 段 | 主要 source | 备注 |
|---|---|---|
| 公共：`source_spec` / `source_files` / `related_requirements` | spec 目录 + frontmatter | 机器可写无需 LLM 判断 |
| 公共：`related_code` | `design.md` + `implementation-log.md` | 抽 Java 类全名 / Vue 文件路径 / Mapper id |
| `rules.*` | `requirements.md` 业务约束 / `design.md` 校验设计 | 抽"X 时不能 Y"型句子 |
| `business.*` | `design.md` 时序图 / 流程图 / `requirements.md` 场景 | 步骤化为 `steps[]` |
| `modules.*` | `design.md` 数据模型 / 接口设计 | 字段枚举 / 调用链 / 分库分表键 |
| `cases.*` | `implementation-log.md` + `bugfix.md` + `tests` + `acceptance-checklist` | **每 spec 必产 1 篇** |
| `pitfalls.*` | `implementation-log.md` + `bugfix.md` | 仅"有复用价值的坑"独立成篇；临时调试不纳入 |

---

## 同 id 升级规则（yml + md 同时升级）

如目标目录已有同 `knowledge_id`：

1. `Read` 两份原文件（yml + md）。
2. **不重写**：`title` / `statement` / `key_decisions` 等结构性字段保留。
3. **追加**：`related_requirements` 追加本次 spec；`source_files` 追加；`seen_again_in`（pit 专有）追加新条目。
4. **更新**：`updated_at: today`；`version +1`（yml + md frontmatter 同步）。
5. **冲突时**：若本次新信息与原文相悖，`AskUserQuestion` 让用户选"覆盖 / 新建 `-v2` 后缀文件 / 跳过"。
6. **cases/case-* 特例**：同一 spec 重新跑 distill 默认 supersede（直接 overwrite），不走 append 流程——因为 case 描述的就是"这次实现"，重跑意味着重写实现。

---

## 深度标准（写得多深算合格）

参考现有 `新收付（fin）` 系统语料的人脑可读基线：

- **modules 类**：字段枚举全列（含已作废值并标注）；分库分表键明确（如 `分表键 underwriteEndDate`）；调用链含完整 Java 类路径 + 方法名。
- **rules 类**：触发条件精确到字段比较；列出反例 / 边界条件；标注在代码哪一层强制。
- **business 类**：每步标注 actor + action + branches；功能页含 UI 约束表。
- **cases 类**：`key_decisions` 配 `reason`；`bugs_encountered` 含表面症状；`lessons` 是一句结论。
- **pitfalls 类**：`symptom` + `root_cause` + `fix` + `prevention` 四件套必填，写不完不算合格。

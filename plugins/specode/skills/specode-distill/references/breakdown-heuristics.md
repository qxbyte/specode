# 知识点拆分启发式（spec-distill v2）

> 供 `spec-distill sync` 流程第 4 步 LLM 提议知识点拆分时参考。
> 拆分方案由 LLM 提议、用户在 `AskUserQuestion` 中最终拍板。
>
> **v2 重要变化**：5 维启发式映射到 `.ai-memory/knowledge/` 下的 **5 类目录**；
> 每个候选知识点必须明确 `category`（`knowledge_id` 由写入器派生，可选）。
> 落盘经 `codemap knowledge write`（content payload），写入器同时产 yml + md 双产；
> 字段集见 `references/doc-template.md`。

## 五维 → 五类目录映射表

| 启发式维度 | 目录 | ID 前缀 | type 字段 |
|---|---|---|---|
| 1. 按业务流程 | `business/` | `biz-` | `business_process` |
| 2. 按表 / 字段 | `modules/` | `mod-` | `module_map` |
| 3. 按功能页 / 特性 | `business/` | `biz-` | `business_process` |
| 4. 按调用链 | `modules/` | `mod-` | `module_map` |
| 5. 按机制 / 规则 | `rules/` | `rule-` | `business_rule` |
| **额外**：本 spec 实现案例 | `cases/` | `case-` | `case` |
| **额外**：可复用坑点 | `pitfalls/` | `pit-` | `pitfall` |

> 每个 spec 至少产 1 篇 `case-*.yml`（必有 — 来自 `implementation-log.md`），其他类按需。`implementation-log` / `bugfix` 中"有复用价值的坑"单独拎出 `pit-*.yml`，不要塞到 case 内。

---

## 什么是一个知识点

**知识点 = 一个可独立复用、可被别处 `related_knowledge` 引用的结论单元。**

具体说：
- 它回答一个清晰的业务或技术问题（"这张表的 PAYSTATUS 枚举值是什么""Q01 入库时 paymentComCode 怎么赋值"）。
- 别处的知识 yml 或需求文档可以直接通过 `knowledge_id` 引用，无需再重新解释。
- 它不依赖同一项目的其他知识点也能被读懂（自洽）。

---

## 五种切法（附真实语料示例）

### 1. 按业务流程

**切法**：一条端到端业务流程（触发→处理→落库→联动），覆盖入口、判断分支、关键节点，构成一篇。

**适用场景**：有明确起点和终点的交易处理链。

**真实示例（新收付 fin 语料）**：
- `Q01承保送收付处理逻辑.md`——承保送收付入库全流程，包括 paymentComCode 覆盖赋值、codInd 判断、Q17/Q01 入库顺序。
  - 关联需求：121659, 123000

> 如果一条流程只包含 2 步且没有判断分支，通常太碎，合并到相关功能页文档更合适。

---

### 2. 按表 / 字段

**切法**：围绕一张表（或关系密切的 2-3 张表）写字段语义、枚举、关联关系、分库分表键、写入路径，构成一篇。

**适用场景**：有复杂枚举或被多需求引用的核心业务表。

**真实示例（新收付 fin 语料）**：
- `SfCreditMain字段说明.md`——PAYSTATUS 枚举（0/1/3/4/6/7 含义）、CNY_PAY_AMOUNT 归属澄清（属于 SfBusinessCredit 而非 SfCreditMain）、三表关联关系图。
  - 关联需求：123000, 121659
- `sflosstransinfo字段说明.md`——processDate 新增字段写入路径（Q02/Q09/REST/ATP）、enc_flag 移除原因、历史数据补齐 SQL（`WHERE processDate IS NULL AND PAYEEBANKACCOUNTENC IS NULL`）。
  - 关联需求：114371

> 判据：一个字段单独成篇通常太碎；一张表的所有字段都摊开写通常太粗。聚焦"有歧义/被误用/被多需求联动修改"的字段群。

---

### 3. 按功能页 / 特性

**切法**：围绕一个前端页面或功能特性写业务规则、UI 约束、后端接口、边界条件，构成一篇。

**适用场景**：有独立交互规则的功能模块（一个弹窗、一个授权页面、一个只读限制）。

**真实示例（新收付 fin 语料）**：
- `结算授权-收付登记号查询授权.md`——`SfPlanAuthority.vue` 新增 paymentNo 维度查询与授权，三表同步更新 paymentComCode（sfpolicyplan/SfPaymentMain/SfPolicyPayment），前端全选联动规则。
  - 关联需求：121659
- `见费出单收款-出单机构只读.md`——见费出单收款弹窗中出单机构字段改为只读展示，companyCode 取值来源。
  - 关联需求：125577

> 判据：前端有独立组件/Vue 文件且后端有专属接口时，可以按功能页切；若多个功能页共享同一套业务逻辑，抽公共逻辑为独立文档更易复用。

---

### 4. 按调用链

**切法**：围绕一条查询链路或调用链写调用顺序、各环节接口/方法/文件路径、关键参数与数据流，构成一篇。

**适用场景**：调用环节多（≥3 跳）、跨前后端、或有复杂路由（分库分表路由）的链路。

**真实示例（新收付 fin 语料）**：
- `收付登记号弹窗-收付款人账号调用链路.md`——实收保费查询页 → 弹窗 → 收付明细 → `paymentInforView` 后端接口 → `refBankAccountCode` 字段，含前端 Vue 文件路径、行号、后端 Java 文件路径（`SfPaymentMainBizImpl.java`）、脱敏工具类 `MaskUtil.maskBankAccount()`。
  - 关联需求：121659

> 判据：纯串行、无分支的 2 跳调用不值得单独成篇；有 if/分表路由/懒加载/多服务跨调时值得切出来。

---

### 5. 按机制 / 规则

**切法**：围绕一条全局生效的业务机制或数据映射规则写触发条件、判断逻辑、影响范围，构成一篇。

**适用场景**：同一规则被多个需求/功能页重复引用，值得单独沉淀避免重复解释。

**真实示例（新收付 fin 语料）**：
- `往来关系上报机制.md`——`paymentComCode != centerCode/companyCode` 时 `innerFlag=1` 的判断与上报字段，影响多个需求（121659, 123000）。
- `SfGeneralFeePlan与businessNo映射规则.md`——`sf_general_fee_plan` 表 `businessNo` 与 `serviceCode` 的 1:1 映射关系及写入约束，被 124620 两个子需求同时引用。

> 判据：如果某条规则在三个以上地方需要解释，就应该抽出来成独立文档；只在一个需求内生效的规则写到该需求的功能页文档里更合适。

---

## 综合判据

| 维度 | 太碎（合并） | 刚好 | 太粗（拆分） |
|------|-------------|------|-------------|
| 粒度 | 一个字段、一行 SQL | 一个功能/流程/表/机制 | 整个需求、整个系统 |
| 复用性 | 只在一处用到 | 2 个以上需求/文档引用 | 所有知识混在一起 |
| 自洽性 | 离开上下文看不懂 | 可独立阅读 | 需要拆分才能引用具体部分 |
| 标题可 `[[]]` 引用 | 标题太通用（"字段"） | 精确描述主题 | 标题太宽泛（"xxx系统概述"） |

**原则**：优先抽"被多个需求复用的稳定结论"。易变的实现细节（调试日志、临时方案）写在 `变更与坑` 段，不单独成篇。

---

## 拆分流程

1. LLM 读完全 spec 文档后，按上述五种维度各提一批候选；**每个候选标注** `category` + 拟标题 + 一句摘要 + 拟 tags（`knowledge_id` 可选——写入器据 category + spec_id/title/signature 自动派生）。
2. 至少强制一篇 `cases` 候选（记录本次实现，来源 `implementation-log.md` / `bugfix.md` / `acceptance-checklist.md`）；写入器据 `spec_id` 派生为 `case-<spec_id>`，与 task-swarm 自动 case 同 id 以触发 supersede。
3. 用 `AskUserQuestion` 呈现给用户，让用户**增删/合并/改名/改归属**。
4. 用户确认后才开始落盘，**不自动跳过此步**。
5. 对每个候选构造 content payload（`category` + `fields` + `md_body`）→ 调 `codemap knowledge write`（见 `SKILL.md` Step 5）；字段集见 `references/doc-template.md`。**不手写 yml**（写入器不可用时才回退手写）。

---

## 参考语料

以下为 `10-Work/知识库/新收付（fin）/` 现有文档的完整列表（截至 2026-06-20），供选题参考：

```
Q01承保送收付处理逻辑.md          → 按业务流程
Q18理赔批量结算-领款人一致性校验.md → 按业务流程
Q35通用费用结算-服务商一致性校验.md → 按业务流程
SfCreditMain字段说明.md            → 按表/字段
sflosstransinfo字段说明.md         → 按表/字段
结算授权-收付登记号查询授权.md     → 按功能页/特性
见费出单收付机构授权.md            → 按功能页/特性
见费出单收款-出单机构只读.md       → 按功能页/特性
收付登记号弹窗-收付款人账号调用链路.md → 按调用链
往来关系上报机制.md                → 按机制/规则
SfGeneralFeePlan与businessNo映射规则.md → 按机制/规则
收付个人数据脱敏.md                → 按机制/规则（横跨11张表的脱敏策略）
银行账号加密重构-双参数并行处理.md → 按机制/规则（加密接口参数变更）
收付系统接口规范V3.12.md           → 按功能页/特性（接口规范全文）
```

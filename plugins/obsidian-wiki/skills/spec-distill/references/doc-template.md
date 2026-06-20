# 知识文档模板

> `spec-distill sync` 写每篇知识文档时使用此模板。深度对齐现有 `新收付（fin）` 语料：含真实表名、字段、枚举、分库分表键、路由方式、Java 文件路径、调用链 ascii 图、坑点。

---

## 完整模板

```markdown
---
tags: [<业务流程 / 数据模型 / 技术规则 / 调用链 / 机制规则 …>]
关联需求: [<需求号, 多个用逗号分隔>]
关联知识: "[[<相关知识文档>]], [[<相关知识文档>]]"
来源: SpecIn/<host>/specs/<项目目录>
更新: YYYY-MM-DD
---


> 区域索引：[[10-Work/README|10-Work]]

# <知识点标题>

## 概述

<2-4 句：这是什么、解决什么业务问题、工单号。>
<示例：在现有结算授权页面（SfPlanAuthority.vue）新增收付登记号（paymentNo）维度的查询与授权功能，支持"先开票后收款"业务场景。工单号：121659。>

## 业务场景 / 背景

<触发场景、业务前提、为什么需要这个知识点。>
<示例：非见费出单保单在收付确认前，需要按收付登记号维度进行授权，将同一收付登记号下的所有保单统一授权给同一收付机构。>

## 数据模型与调用链

<表、分库分表键、路由方式（主库/normal库/SfRouter路由）、查询链路；可用 ascii 图展示。>

```
<示例 ascii 调用链：>
paymentNo → SfPaymentMain(normal库, paymentStatus='3')
         → SfPolicyPayment(主库, 通过SfRouter路由)
         → sfpolicyplan(主库, findSfPolicyPlan, 仅policyNo+payNo)
```

- `<表名>`：<一句字段/含义说明，标注分表键>
- `<表名>`：<一句字段/含义说明>

## 关键表 / 字段 / 接口

<细粒度：表名、字段名、枚举值、接口路径、Java 文件路径、Mapper xml 中的 SQL id。>

### <表名 / 接口名>

| 字段/参数 | 类型 | 枚举值 / 说明 |
|----------|------|--------------|
| <字段名>  | <类型> | <值及含义，如 0=未处理, 1=已确认> |

- <接口/方法路径>：`<Java类>#<方法>` — <一句说明>
- <Mapper SQL id>：`<XxxMapper.xml#xxxMethod>` — <WHERE 条件说明>

### 分库分表 / 路由

| 表 | 分表键 | 更新条件 | 所在库 |
|----|--------|----------|----|
| <表名> | <分表键字段> | <WHERE 条件> | <主库/normal库> |

## 变更与坑（如有）

<从 implementation-log.md / bugfix.md 提炼；无则略去本段。>

- **坑：<简述>**：<原因 + 修复方式>
  - 示例：`endorseSeqNo` 跨表不一致——SfPolicyPayment 和 sfpolicyplan 的 endorseSeqNo 可能不一致，查询 sfpolicyplan 时仅用 `policyNo+payNo`，**不传 endorseSeqNo**。
- **变更记录**：

| 日期 | 来源需求 | 变更说明 |
|------|----------|----------|
| YYYY-MM-DD | <需求号-名称> | <变更内容> |

## 关联

- 同系统相关：[[<相关知识文档>]] — <一句说明关联点>
- 关联需求：[[<需求号-需求名>]] — SpecIn/<host>/specs/<项目目录>/
```

---

## 各段内容来源对照

| 模板段 | 从 SpecIn 哪个文件提炼 | 说明 |
|--------|----------------------|------|
| **概述** | `requirements.md` 简介/背景部分 | 取需求简介，加工单号 |
| **业务场景 / 背景** | `requirements.md` 业务场景/前提条件部分 | 触发条件、用户角色、业务前提 |
| **数据模型与调用链** | `design.md` 数据模型/调用链部分 | 表关系图、路由、ascii 链路图；`design.md` 没有时从 `requirements.md` 中的流程图/时序图补充 |
| **关键表 / 字段 / 接口** | `design.md` 表设计/接口设计部分 | 字段枚举、Mapper SQL id、Java 文件路径；与现有 `SfCreditMain字段说明.md`、`sflosstransinfo字段说明.md` 风格对齐 |
| **变更与坑** | `implementation-log.md`、`bugfix.md` | 只提炼有复用价值的坑点；临时调试信息不纳入 |
| **关联** | 综合所有文件 + 现有知识库 | 交叉引用现有知识文档（如 `[[往来关系上报机制]]`）；需求号指向 SpecIn 项目目录 |

> **测试要点**（可选段）：若项目有 `tasks.md` 或测试报告，可在"关联"段前加 `## 测试要点` 段，提炼验收标准与边界 case。不强制。

---

## 深度标准（对齐现有语料）

以下是现有 `新收付（fin）` 语料体现的深度基线，写新文档时参照：

**表/字段类**（参照 `SfCreditMain字段说明.md`、`sflosstransinfo字段说明.md`）：
- 枚举值全列（含已作废值）
- 分库分表键明确标注（如 `分表键 underwriteEndDate`）
- 写入路径列全接口（Q02/Q09/REST/ATP 各一行）
- 关联关系用 ascii 图或表格展示（`SfCreditMain.creditingNo (1) ──→ (N) SfBusinessCredit.creditingNo`）

**调用链类**（参照 `收付登记号弹窗-收付款人账号调用链路.md`）：
- 前端：Vue 文件路径 + 关键行号 + 方法名
- 后端：Java 类完整路径（`com.pointwise.cloud.modules.payment.biz.SfPaymentMainBizImpl`）+ 方法名
- 工具类：完整类名 + 方法签名 + 规则说明（如脱敏规则"前6后4"）

**功能页类**（参照 `结算授权-收付登记号查询授权.md`）：
- 查询链路 ascii 图
- 三表同步更新逻辑（含 WHERE 条件约束说明）
- 前端行为规则表格（全选联动、保存校验条件）
- 后端方法调用层级（`authorityQuery` → 私有方法 `authorityQueryByPaymentNo`）

**机制/规则类**（参照 `往来关系上报机制.md`、`SfGeneralFeePlan与businessNo映射规则.md`）：
- 触发条件精确到字段比较（`paymentComCode != centerCode/companyCode`）
- 影响范围（哪些需求/页面受影响）
- 反例或边界条件（何时不触发）

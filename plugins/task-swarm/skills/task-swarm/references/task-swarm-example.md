---
description: Use when 想看一份完整可用的 pipeline.yml 示例，理解 task_group / needs / writes / reads / requirements 的实际写法与跨组并发调度。
---

# task-swarm 示例：3 任务组 / 8 任务

下面是一份**完整可用**的 pipeline.yml 示例，演示：

- `task_group` + 组内 `task` 的 `writes` / `reads` 写法
- `needs`（组间依赖，拓扑解锁）
- `requirements`（`_需求：x.y_` traceability）
- 跨组并发调度：无依赖且 writes 不相交的组并发，writes 冲突或 `needs` 未满足的组串行

---

## 示例 pipeline.yml

```yaml
version: 1
run:
  spec_id: user-login
  max_parallel: 4
task_groups:
  - id: g1
    name: "数据层"
    tasks:
      - id: g1.1
        title: "定义 User 模型"
        writes: [src/models/user.py]
        requirements: ["1.1"]
      - id: g1.2
        title: "定义 Session 模型"
        writes: [src/models/session.py]
        requirements: ["1.2"]
      - id: g1.3
        title: "数据库迁移脚本"
        writes: [migrations/0001_init.sql]
        reads:  [src/models/user.py, src/models/session.py]
        requirements: ["1.3"]
  - id: g2
    name: "服务层"
    needs: [g1]
    tasks:
      - id: g2.1
        title: "AuthService 登录/登出"
        writes: [src/auth/service.py]
        reads:  [src/models/user.py, src/models/session.py]
        requirements: ["2.1", "2.2"]
      - id: g2.2
        title: "PasswordHasher 工具"
        writes: [src/auth/hasher.py]
        requirements: ["2.3"]
      - id: g2.3
        title: "LockoutCounter 工具"
        writes: [src/auth/lockout.py]
        requirements: ["2.4"]
  - id: g3
    name: "API 层"
    needs: [g2]          # 依赖服务层；且与 g1 同写 user.py（writes 冲突亦会被调度串行）
    tasks:
      - id: g3.1
        title: "/login endpoint"
        writes: [src/api/login.py]
        reads:  [src/auth/service.py, src/auth/lockout.py]
        requirements: ["3.1"]
      - id: g3.2
        title: "User schema 验证扩展"
        writes: [src/models/user.py]
        reads:  [src/api/login.py]
        requirements: ["3.2"]
```

---

## 期望的调度（max_parallel=4）

`plan` 的 `schedule` 会按 `needs` 拓扑 + `writes` 不相交逐轮解锁：

```
第 1 轮：runnable = [g1]
         （g2 needs g1，g3 needs g2 → blocked: needs not done）
第 2 轮（g1 done 后）：runnable = [g2]
第 3 轮（g2 done 后）：runnable = [g3]
```

本例三组线性依赖，所以实际串行。若把 `g2`/`g3` 的 `needs` 去掉且各组 `writes` 互不相交，调度层会让它们并发（总并发 ≤ `max_parallel`）；注意 **g3 与 g1 都写 `src/models/user.py`**，即使没有 `needs`，调度层也会因 `writes conflict with running group` 把 g3 排在 g1 之后——文件冲突天然串行，无需手写依赖。

主代理派 coder 时，对每个 runnable 组**逐字**拷 `actions[].fork[].agent_key`（如 `coder-g1-s1-r1`），同 message 并发 fork。

> 注：每个 task 即使含多个子项也由组内的 coder 序列接手；并发粒度是 task_group，不是单个 task。

---

## 一轮 validator fail → v-fix → pass 的报告示例

`report --run <id>` 渲染时，g3 段会包含：

```markdown
## g3 API 层 — done

> ✅ validator g3-r2 pass: `pytest tests/test_login.py -v`
>
> 评审建议（task-swarm reviewer）：
> - [P0 已修复] src/auth/service.py:34 [req:2.1] — login 失败未区分锁/密码错
> - [P0 已修复] src/api/login.py:8 [security] — 缺 rate limit
> - [P1 未修复] src/models/user.py:12 — email 字段格式校验缺失
> - [adv 未修复] src/auth/service.py:50 — error wrapping 风格（无证据标签，自动降级）
>
> validator 历轮：
> - g3-r1: fail — fail signature 4a2b3c1d8e9f
> - g3-r2: pass
```

---

## requirements 的作用

`requirements: ["x.y"]` 让 validator 在跑测试时能把"测试通过 / 失败"对回到具体 SHALL 条款：

- 测试失败 → validation.md 的"按子任务的验证结果"那行写明 `_需求：x.y_`
- `report` 汇总时保留该编号
- （集成 specode 时，specode 侧会在 acceptance 阶段另做 SHALL↔测试 校验；独立模式不涉及）

---

## needs 与 writes 的取舍

- **`needs`**：表达**非文件冲突**的顺序依赖（如"服务层要等数据层建好接口"）。引用其它 `task_group id`；上游 `done` 才解锁本组，上游 `failed` 则本组 `blocked: upstream failed`。
- **`writes` 冲突**：调度层自动检测——有交集的组不会同时跑，无需写 `needs`。
- 两者叠加：既无 `needs` 又 writes 不相交的组才会真正并发。

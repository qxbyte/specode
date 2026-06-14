---
description: Use when 想看一份完整可用的 tasks.md 示例，理解 @writes / @reads / @depends-on 标签的实际写法。
---

# task-swarm 示例：3 阶段 / 8 任务

下面是一份**完整可用**的 tasks.md 示例，演示：

- `@writes` / `@reads` / `@depends-on` 标签用法
- `_需求：x.y_` traceability
- 检查点任务（→ validator 用）
- 同文件冲突的两个 stage 如何被自动分到不同 group

---

## 示例 tasks.md

```markdown
# 用户认证系统 — tasks.md

## 阶段 1: 数据层
- [ ] 1.1 定义 User 模型 @writes:src/models/user.py _需求：1.1_
- [ ] 1.2 定义 Session 模型 @writes:src/models/session.py _需求：1.2_
- [ ] 1.3 数据库迁移脚本 @writes:migrations/0001_init.sql @reads:src/models/user.py,src/models/session.py _需求：1.3_

## 阶段 2: 服务层
- [ ] 2.1 AuthService 登录/登出 @writes:src/auth/service.py @reads:src/models/user.py,src/models/session.py @depends-on:1 _需求：2.1,2.2_
- [ ] 2.2 PasswordHasher 工具 @writes:src/auth/hasher.py _需求：2.3_
- [ ] 2.3 LockoutCounter 工具 @writes:src/auth/lockout.py _需求：2.4_

## 阶段 3: API 层（依赖服务层 + 与阶段 1 同文件 user.py）
- [ ] 3.1 /login endpoint @writes:src/api/login.py @reads:src/auth/service.py,src/auth/lockout.py @depends-on:2 _需求：3.1_
- [ ] 3.2 User schema 验证扩展 @writes:src/models/user.py @reads:src/api/login.py @depends-on:1 _需求：3.2_
```

---

## 期望的 group 切分（max_parallel=4）

```
group 0：
 - 阶段 1（writes: src/models/user.py, src/models/session.py, migrations/0001_init.sql）
 - 阶段 2 不能进 group 0：depends-on=1
group 1：
 - 阶段 2（writes: src/auth/service.py, src/auth/hasher.py, src/auth/lockout.py）
group 2：
 - 阶段 3（writes: src/api/login.py, src/models/user.py）
 ↑ 注意：阶段 3 与阶段 1 都写 src/models/user.py（文件冲突）
 即使没有 @depends-on:1，也会被自动分到独立 group
 这里阶段 3 实际 depends-on=2，所以排在 group 2
```

主代理派 coder 时（plan 输出）：

```
group 0：fork 1 个 coder（阶段 1）
group 1：fork 1 个 coder（阶段 2）
group 2：fork 1 个 coder（阶段 3）
```

> 注：每个 stage 即使含多个子任务也由**单个** coder 接手（按子任务清单顺序完成）；
> 跨 stage 文件冲突时才切 group。

---

## 一轮 validator fail → v-fix → pass 的注释块例子

writeback 后，阶段 3 末尾会追加：

```markdown
## 阶段 3: API 层（依赖服务层 + 与阶段 1 同文件 user.py）
- [x] 3.1 /login endpoint @writes:src/api/login.py @reads:src/auth/service.py,src/auth/lockout.py @depends-on:2 _需求：3.1_
- [x] 3.2 User schema 验证扩展 @writes:src/models/user.py @reads:src/api/login.py @depends-on:1 _需求：3.2_

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

## 检查点任务（含 _需求：x.y_）的作用

`_需求：x.y_` 让 validator 在跑测试时能把"测试通过 / 失败"对回到具体 SHALL 条款：

- 测试失败 → validation.md 的"按子任务的验证结果"那行写明 `_需求：x.y_`
- writeback → tasks.md 注释里也保留该编号
- spec_lint.py 在 acceptance phase 时会再校验"全部 SHALL 是否都有对应测试"

---

## @depends-on 的作用

- group 切分时 stage X depends_on Y → X 的 group index 必须严格大于 Y 的 group index。
- 跨 group 自动串行：上一 group writeback 完成才能开始下一 group。

---

## 边界情况

- 一个 stage 在 tasks.md 没写 `@writes` → 该 stage 视为 "无文件冲突约束"，会被尽量打包到当前 group。
- 一个 stage 在 tasks.md 没写 `@depends-on` → 不强制顺序，仅靠 @writes 冲突切 group。
- 一个 stage 没写任何子任务（只有 `## 阶段 N: 标题`）→ 解析器跳过该 stage（视为占位）。

---
description: Use when specode 在某 phase 要调 superpowers skill 或判断是否降级 —— phase↔skill 映射、落盘归位双保险、缺席降级矩阵。
---

# superpowers 编排映射

| phase | 装了 superpowers | 缺席 → specode-native |
|---|---|---|
| 澄清+需求 | superpowers:brainstorming | AskUserQuestion 澄清 + 按 requirements 模板写 |
| 可执行计划 | superpowers:writing-plans | 按 design 模板自己拆 Task + TDD 步骤 |
| 执行 | task-swarm / superpowers:subagent-driven-development / superpowers:executing-plans | 按 design Task 顺序 TDD |
| 验收 | superpowers:verification-before-completion (+ requesting-code-review) | 对照 design 测试要点 / AC 逐条核验 |

## 落盘归位（双保险，保证固定产物不变式）
1. 前置：调 skill 时显式给目标绝对路径 + 固定文件名（brainstorming→requirements.md，writing-plans→design.md）。
2. 后置：skill 返回后校验 `<specsRoot>/<slug>/<固定名>` 是否就位；未就位则把 skill 实际产物 move/rename 过去。

## 可用性判断
先尝试 Skill 调 superpowers，不可用 / 未安装 → 走 native 分支。task-swarm 同理（调其 /task-swarm 失败则降级）。

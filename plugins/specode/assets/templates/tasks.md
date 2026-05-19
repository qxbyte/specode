# 实现计划：{{name}}（{{slug}}）

Spec Type: {{spec_type}}
Workflow: {{workflow}}
Status: Tasks Draft
Review Status: unreviewed

## 概述

基于已确认的需求与设计，将实现拆分为可执行、可验证的任务。任务执行时必须先更新状态，完成验证后才能标记完成。

**格式约定（task-swarm 兼容）**：

- 顶层 `## 阶段 N: 标题` 段落对应一个 stage（task-swarm 的 fork 粒度）
- 每条具体任务 `- [ ] N.M 任务描述 @writes:文件路径 @reads:文件路径 @depends-on:N _需求：x.y_`
  - `@writes`：本任务写哪些文件（task-swarm 据此切 group 避免冲突）
  - `@reads`：本任务读哪些文件（可选）
  - `@depends-on:N`：本 stage 依赖阶段 N（可选；不写则仅靠 @writes 冲突切 group）
  - `_需求：x.y_`：traceability，链回 requirements.md / bugfix.md 的 SHALL 编号
- 可选任务把 `[ ]` 写成 `[*]`；checkpoint 任务保留 `[ ]` 但标题以「检查点」开头

## 阶段 1: 待规划阶段标题

- [ ] 1.1 待规划任务描述 @writes:src/path/to/file.py _需求：1.1_

## 测试要点

供测试人员快速了解需要验证的场景。spec-writer 在 tasks phase 按 requirements.md / bugfix.md 的 SHALL 顺手补几行，每行关联 SHALL 编号。非验收硬条件，acceptance phase 时主代理把这一节简述给用户作参考即可。

- _agent 待填充_：触发场景 → 预期结果（需求 X.Y）

## 验收

- [ ] 所有 required 任务完成。
- [ ] 所有指定验证命令通过。
- [ ] 未完成或跳过的 optional 任务已记录。
- [ ] 用户确认验收。

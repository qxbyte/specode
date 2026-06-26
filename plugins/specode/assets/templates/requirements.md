---
spec_id: <kebab-case slug，与 specsRoot/<slug>/ 保持一致>
project_root: <绝对路径；写 requirements 前由 host agent 通过 AskUserQuestion 与用户确认，默认值为当前 cwd 或 `git rev-parse --show-toplevel`>
created_at: YYYY-MM-DD
---

# <feature> 需求

> specode requirements — 散文描述 + 验收标准追溯标签。

## 已知约束 / 历史坑

<由 host agent 在 phase-0 context-recall 步骤自动注入；
当 `<project_root>/.ai-memory/knowledge/` 为空或 `codemap recall` 不可用时本段省略。
格式：每行 `- [[<knowledge_id>]] (<type>, score=<n>) — <title> · <summary>`。
草稿作者写需求时务必先看这段，再决定是否覆盖/绕过历史结论。>

## 背景 / 为什么

<这个需求解决什么问题、为谁、动机。>

## 范围

- 包含：<本次要做的>
- 不包含：<明确排除的，避免 scope creep>

## 验收标准

- [ ] AC-1: <可观察、可验证的行为>
- [ ] AC-2: <当 X 时系统 Y>

## 开放问题

- <尚未定的点；澄清后移除或落到上面章节>

---
description: specode 轻量 spec 工作流入口。/spec <需求> 新建；/spec continue <slug> 续接；/spec list 列出。
argument-hint: "<需求> | continue <slug> | list"
---

# /spec — specode 轻量工作流

按 `$ARGUMENTS` 第一个 token 分发。所有 CLI 经 run.sh 包装 + `$CLAUDE_PLUGIN_ROOT`（fallback `$CODEBUDDY_PLUGIN_ROOT`）绝对路径：
`sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/resolve_root.py" <verb> ...`

激活后遵循 specode SKILL.md 的编排逻辑（各 phase 调 superpowers，缺席则 native 降级；3 份固定产物落 `<specsRoot>/<slug>/`）。

## A. `/spec list`
1. 调 `resolve_root.py get-root`：
   - exit 3（未配置）→ 走 §D 首次设置，设完再继续。
   - exit 0 → 拿到 `<specsRoot>`。
2. 调 `resolve_root.py list-specs` 列出 slug；对每个 slug 读其目录文档，按 SKILL.md「文档即状态」推断 phase 一并展示。无 spec → 提示 `/spec <需求>` 新建。**不续接**。

## B. `/spec continue <slug>`
1. slug 必填；缺失 → 报错 + 提示先 `/spec list` 查 slug。
2. `resolve_root.py get-root`（未配置→§D）→ 定位 `<specsRoot>/<slug>/`；目录不存在 → 报错 + 提示 `/spec list`。
3. 读该目录文档，按 SKILL.md「文档即状态」推断 phase，从对应 phase 续接（详见 SKILL.md §续接）。

## C. `/spec <需求>`（新建）
1. `resolve_root.py get-root`（未配置→§D）→ `<specsRoot>`。
2. 由主代理从需求推导 kebab-case `<slug>`；`mkdir -p <specsRoot>/<slug>/`。
3. `project_root = 当前终端 cwd`（不询问；约定用户先 cd 到项目目录再开聊）。
4. 按 SKILL.md §流程推进：requirements（brainstorming/native）→ design（writing-plans/native）→「执行方式」selector → 执行 → 验收。3 份固定产物落 `<specsRoot>/<slug>/`。

## D. 首次设置（仅当 get-root exit 3）
调 `AskUserQuestion` 问用户「文档管理目录」（绝对路径，将原样作为 specs 根）→ 用户给出后调
`resolve_root.py set-root --root <path>` 持久化 → 之后会话不再问。

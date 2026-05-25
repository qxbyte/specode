---
description: 恢复或切换 specode 会话
argument-hint: "[spec-slug]"
---

/specode:continue $ARGUMENTS

按 `$ARGUMENTS` 形态分两步路由：无 slug 走第一步、有 slug 走第二步。**禁止**主代理跳过 selector 直接 `acquire`、**禁止**根据用户裸输入 invent slug。

## 第一步：无 slug —— 列出可选 spec

若 `$ARGUMENTS` 为空：

1. 先按 SKILL.md §「Document Root Resolution / 首次使用 / auto-detect 命中时的确认」确认 doc_root；无配置且用户选"中止"则引导 `/specode:spec --set-vault <p>` 后 end turn
2. 调 `spec_session.py list-specs --session <id>` 拿可选 spec 列表

   ```sh
   sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
      "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/spec_session.py" \
      list-specs --session <id>
   ```

3. 按 `references/workflow.md` §9.1 处理结果：空列表 → chat 引导 `/specode:spec <需求>` 创建新 spec；非空 → chat 摘要 + 按 SKILL.md §Selectors 主动呈现 spec 选择（类型 A 单列单选，≤4 项；每个选项 `label=<slug>`）让用户选；选完下一轮以 slug 进入第二步

## 第二步：有 slug —— 接管 + 加载

按 `references/workflow.md` §9.2 + `references/lock-protocol.md` 走 5 步：

1. 解析 `spec_dir = <doc_root>/specs/<slug>`（**不要** Grep 项目目录，spec 不在项目里）
2. 调 `spec_session.py acquire --spec <dir> --session <id>`；`exit 4 LockHeld` 时**禁止**直接 `--force`，按 SKILL.md §Multi-Window + Lock 呈现 `takeover-options` selector 让用户选
3. `spec_session.py load --spec <dir>`
4. `spec_session.py continue --spec <dir> --session <id>`（只读模式跳过）
5. 完成后**按 SKILL.md §Status Footer「新 spec 创建/接管的当 turn」走**：chat 简报 "已加载 spec：<slug>（phase=<p>, iteration=<n>, lock=<state>）" + 状态行 footer + （若 sess.pending_selector 有值）主动呈现对应 selector

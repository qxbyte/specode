---
description: 恢复或切换 specode 会话
argument-hint: "[spec-slug]"
---

/specode:continue $ARGUMENTS

按 `$ARGUMENTS` 形态分两步路由：无 slug 走第一步、有 slug 走第二步。**禁止**主代理跳过 selector 直接 `acquire`（详见 `references/workflow.md` §9）。

## 第一步：无 slug —— 列出可选 spec 让用户选

若 `$ARGUMENTS` 为空：

1. **确认 doc_root**：调 `spec_vault.py status`，`source = auto` 或 `none` 时按 SKILL.md §「Document Root Resolution / 首次使用 / auto-detect 命中时的确认」走 `AskUserQuestion` 三选 + `spec_vault.py set --vault <p>` 持久化；无配置且用户选"中止"则在 chat 引导 `/specode:spec --set-vault <p>` 后 end turn。
2. **列 spec**：

   ```sh
   sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
      "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/spec_session.py" \
      list-specs --session <id>
   ```

3. `list-specs.specs == []` → **不**调工具，在 chat 引导用户 `/specode:spec <需求>` 创建新 spec，end turn。
4. `list-specs.specs != []` → chat 写 1-2 行摘要（"找到 N 个 spec，当前 root：<root>，<m> 个锁定 / <n> 个空闲"），然后**调 `AskUserQuestion`**（类型 A，单列单选，`multiSelect=false`，≤4 项；超过 4 个按 `last_heartbeat_at` 取最近 4 个，其余在 chat 引导用 `/specode:continue <slug>` 显式指定）。每个选项 `label=<slug>`，`description` 简述 phase / 迭代 / 锁状态 / 最近 mtime。
5. 工具返回后下一轮以用户选定的 slug 进入第二步。

详细出题策略见 `references/workflow.md` §9.1 + `references/selectors.md`。

## 第二步：有 slug —— 接管 + 加载

若 `$ARGUMENTS` 是 spec slug（或第一步用户选定后传过来的 slug）：

1. **解析** `spec_dir = <root>/specs/<slug>`（root 取自第一步 `spec_vault.py status` 的 `doc_root`；**不要** Grep 项目目录——spec 不在项目里，见 SKILL.md §Document Root Resolution）。
2. **acquire**：

   ```sh
   sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
      "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/spec_session.py" \
      acquire --spec <dir> --session <id>
   ```

   - `exit 0` → 持锁成功，进 step 3
   - `exit 4 LockHeld` → **禁止**直接 `acquire --force`，先输出锁状态摘要 + 调 `AskUserQuestion` 呈现 `takeover-options` 选择器（强制接管 / 只读查看 / 取消，详见 SKILL.md §Multi-Window + Lock + `references/lock-protocol.md`）：
     - 选 1 `强制接管` → `acquire --force` → step 3
     - 选 2 `只读查看` → **跳** acquire，调 `load` 拿数据，写 `sessions/<id>.json.mode=readonly` → step 5
     - 选 3 `取消` → end turn
3. **load**：`spec_session.py load --spec <dir>` 拿 phase / iteration round / tasks 计数 / 文档 mtime。
4. **continue**：`spec_session.py continue --spec <dir> --session <id>` 绑定 sessions + 写 active-pointer（只读模式跳过）。
5. **报告**："已加载 spec：<slug>（phase=<p>, iteration=<n>, lock=<state>）"，加状态行 footer（SKILL.md §Status Footer），end turn。

详细 5 步行为见 `references/workflow.md` §9.2 + `references/lock-protocol.md`。

CLI 调用模板见 SKILL.md §CLI 调用规约（**禁止**裸 `python3 spec_session.py …`）。

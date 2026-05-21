---
description: 进入 specode 持久会话，开始新 spec 或调用子命令
argument-hint: "<需求> | <名称>: <需求> | -h | --set-vault <p> | --set-root <p> | --detect-vault | --vault-status | --sync-status"
---

/specode:spec $ARGUMENTS

按 `$ARGUMENTS` 形态分四步路由，**依次**判断、命中即执行并 end turn，不要跳过 / 并行。

## 第一步：fast-path 参数（hook 已注入模板）

若 `$ARGUMENTS` 以下列任一旗标开头（hook 实际拦截范围，见 `spec_session.py:FAST_PATH_HELP / FAST_PATH_VAULT`）：

- `-h` / `--help`
- `--vault-status` / `--detect-vault` / `--sync-status`

→ **不要在本 turn 调任何 CLI**（**禁止** `sh ... spec_init.py -h` / `sh ... spec_vault.py status` 等）。
UserPromptSubmit hook 已在 `additionalContext` 里注入 fast-path 模板，
你**唯一动作**是把 hook 注入的 ```text 围栏内容**逐字**输出，然后立即 end turn。
禁止任何额外说明文字（"以下是帮助" / "希望对你有帮助" 等都不允许）。

## 第二步：set 命令（持久化 doc_root，不创建 spec）

若 `$ARGUMENTS` 是 `--set-vault <path>` 或 `--set-root <path>`（**hook 不拦截**，必须主动调 CLI）：

```sh
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/spec_vault.py" \
   set --vault <path>
```

`--set-root` 与 `--set-vault` 等价（写同一个 `obsidianRoot` 字段）。执行成功后向用户
confirm 写入位置（`~/.config/specode/config.json`），然后 end turn。**不**进入第三步 / 第四步。

## 第三步：doc_root 确认（新建 spec 前必做）

若 `$ARGUMENTS` 是 `<需求>` 或 `<名称>: <需求>`（既不是第一步的 fast-path、也不是第二步的 set 命令），
**先**调 `spec_vault.py status` 拿到 `source` 字段：

```sh
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/spec_vault.py" \
   status
```

- `source` = `env` 或 `config` → 已显式配置，**直接进第四步**
- `source` = `auto` 或 `none` → **禁止直接调 `spec_init.py`**，按 SKILL.md
  §「Document Root Resolution / 首次使用 / auto-detect 命中时的确认」走
  `AskUserQuestion` 三选 + `spec_vault.py set --vault <p>` 持久化流程；
  用户选"中止"则 end turn，否则持久化后再进第四步

## 第四步：常规创建 spec

解析 `<名称>：<内容>` → 推导英文 slug，然后：

```sh
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/spec_init.py" \
   --name <slug> --requirement-name "<显示名>" --source-text "<原文>" --session <id>
```

- doc-root 三层解析详见 SKILL.md §Document Root Resolution
- 三层全 miss → exit 3 + 引导提示；**不**回退到 cwd / ~/specs
- 详细流程见 SKILL.md §Session Lifecycle / references/obsidian.md
- 调用模板规约见 SKILL.md §CLI 调用规约（**禁止**裸 `python3 spec_init.py …`）

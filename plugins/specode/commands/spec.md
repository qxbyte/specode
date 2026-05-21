---
description: 进入 specode 持久会话，开始新 spec 或调用子命令
argument-hint: "<需求> | <名称>: <需求> | -h | --set-vault <p> | --set-root <p> | --detect-vault | --vault-status | --sync-status"
---

/specode:spec $ARGUMENTS

## 第一步：判断是否为 fast-path 参数

若 `$ARGUMENTS` 以下列任一 fast-path 旗标开头：

- `-h` / `--help`
- `--vault-status` / `--detect-vault` / `--sync-status`
- `--set-vault <path>` / `--set-root <path>`

→ **不要在本 turn 调任何 CLI**（**禁止** `sh ... spec_init.py -h` / `sh ... spec_vault.py ...` 等）。
UserPromptSubmit hook 已在 additionalContext 里注入 fast-path 模板，
你**唯一动作**是把 hook 注入的 ```text 围栏内容**逐字**输出，然后立即 end turn。
禁止任何额外说明文字（"以下是帮助" / "希望对你有帮助" 等都不允许）。

## 第二步：常规需求（非 fast-path）

解析 `<名称>：<内容>` → 推导英文 slug，然后：

```sh
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/spec_init.py" \
   --name <slug> --requirement-name "<显示名>" --source-text "<原文>" --session <id>
```

- doc-root 三层解析：`--root` / `SPECODE_ROOT` env / `~/.config/specode/config.json.obsidianRoot` / Obsidian vault 自检测
- 三层全 miss → exit 3 + 引导提示；**不**回退到 cwd / ~/specs
- 详细流程见 SKILL.md §Session Lifecycle / references/obsidian.md
- 调用模板规约见 SKILL.md §CLI 调用规约（**禁止**裸 `python3 spec_init.py …`）

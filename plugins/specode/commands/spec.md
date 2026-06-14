---
description: 进入 specode 持久会话，开始新 spec 或调用子命令
argument-hint: "-n <slug> <需求> | <需求> | <名称>: <需求> | -h | --set-vault <p> | --set-root <p> | --detect-vault | --vault-status | --sync-status"
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

若 `$ARGUMENTS` 是 `-n <slug> <需求>` / `<需求>` / `<名称>: <需求>`（既不是第一步的 fast-path、也不是第二步的 set 命令），
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

按 `$ARGUMENTS` 形态分两个子分支，**优先 4a**：

### 4a. 显式 `-n <slug>` / `--name <slug>`（推荐）

若 `$ARGUMENTS` 以 `-n <slug>` 或 `--name <slug>` 开头：

- 第二个 token 是 spec 目录名 slug，**保留用户原文**，不做翻译/推导。
- 0.10.16+ 起允许 Unicode（中文/日文/emoji 都可），只禁文件系统危险字符
  （`< > : " / \ | ? *`、空白字符、首字符 `.` 或 `-`、Windows 保留名）。
- 剩余文本 → `source_text`（原始需求）。
- `requirement_name` 默认：英文 slug 按短横线 → 空格 + 首字母大写
  （如 `user-login` → `User Login`）；非 ASCII slug（如中文）直接复用原文。

示例：

- `/specode:spec -n user-login 添加用户登录功能` →
  `--name user-login --requirement-name "User Login" --source-text "添加用户登录功能"`

（非 ASCII slug 情况见上一段 `requirement_name` 默认规则。）

**spec_init.py exit 3（slug 非法）时的应对**：

- **禁止**主代理**静默 fallback 到 4b 推导**——用户用了 `-n` 形式就是想精确控制目录名，
  自动换成英文 slug 是欺骗用户。
- 正确做法：把 CLI 的 stderr 错误原信息（如"不能含 / \\ * ? 或空白；不能以 - 开头"）
  报给用户，要求用户重新提供一个合法 slug，**不要替用户决定**。
- 仅当用户明确说"你帮我想一个"时才走 4b 推导。

**这条路径的好处**：用户能精确控制 `<doc_root>/specs/<slug>/` 的目录名，
不会出现"主代理把 '订单退款' 推成 `order-refund-flow` 但用户想要 `refund`"的歧义。

### 4b. 推导式（兼容、不推荐）

若 `$ARGUMENTS` 是纯 `<需求>` 或 `<名称>: <需求>`：

- 按 `references/workflow.md` §1.1「名称前缀解析 + slug 推导」由主代理推导。
- **推导结果对用户不可预知**——若用户在意目录名，应引导改用 4a 形式。

### 调用 spec_init.py

```sh
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/spec_init.py" \
   --name <slug> --requirement-name "<显示名>" --source-text "<原文>" --session <id>
```

- doc-root 三层解析详见 SKILL.md §Document Root Resolution
- 三层全 miss → exit 3 + 引导提示；**不**回退到 cwd / ~/specs
- 详细流程见 SKILL.md §Session Lifecycle / references/obsidian.md
- 调用模板规约见 SKILL.md §CLI 调用规约（**禁止**裸 `python3 spec_init.py …`）

### 第四步成功后必做（0.10.15+：先 project-root，再 workflow）

`spec_init.py` `exit 0` 后 spec 已进入 **active 模式**（`mode=active` / `pending_selector=project-root-choice`）。**`/specode:spec` 是持续流程入口，不需要用户再输命令推进**——本 turn hook 未刷新，主代理按 SKILL.md §Status Footer「新 spec 创建/接管的当 turn」走（chat 简报 + 状态行 footer），然后**依次**：

1. **立即调 `AskUserQuestion` 呈现 `project-root-choice` selector**（决定代码写到哪个目录；模板见 `_selectors.py` SELECTOR_PROMPTS['project-root-choice']）
2. 拿到用户选择后**本 turn 内**调 `spec_session.py set-project-root --spec <dir> --session <id> --root <选定路径>`
3. CLI 成功后立即调 `AskUserQuestion` 呈现 `workflow-choice` selector（模板见 `_selectors.py` SELECTOR_PROMPTS['workflow-choice']）
4. 用户选完工作流后**先做需求歧义自检**——见 SKILL.md §「Pre-requirements Clarification（铁律）」：有阻塞性歧义且用户未明确放权 → 先调 `clarification-wizard` 与用户讨论，**禁止假设/invent**；自检无歧义或用户已放权 → 再 `phase-transition` + 生成 `requirements.md` / `bugfix.md` / `design.md`。

**两步都不要 end turn 让用户再输命令**——project-root 选完直接进 workflow 选择。

**严禁**说 "使用 `/specode:continue` 进入下一阶段" / "你可以使用 ... 推进" / "下一步请输入 ..." 这类让用户再输命令的引导——流程由 selector 推进。

**严禁**在源需求不明确时绕过 clarification-wizard 直接写文档——澄清铁律的违反不是"风格瑕疵"而是 spec 失真根因，详见 SKILL.md §「Pre-requirements Clarification（铁律）」。

**为什么要先选 project_root**：spec 文档目录（`<doc_root>/specs/<slug>/`）只放 `.md` 文档；代码实际写到的目录是 `project_root`（即 coder / 实现 agent 的 cwd）。两者解耦后，实现 agent 能明确知道"代码写哪里"，避免 0.10.13 之前那种"代码错写到 spec dir 污染文档目录"的事故。

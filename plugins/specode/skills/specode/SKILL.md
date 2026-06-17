---
name: specode
description: 轻量规范驱动工作流的编排壳。在 requirements → design →「执行方式」→ 执行 → 验收各 phase 自主调用 superpowers 的成熟 skill 干重活（缺席时 specode-native 降级），并把固定 3 份产物（requirements.md / design.md / implementation-log.md）规整落到用户的文档管理目录。仅在用户调用 `/spec <需求>`、`/spec continue <slug>`、`/spec list`，或显式要求进入 spec 模式时激活；其余情况按普通对话处理。
---

# specode — 编排壳（orchestration shell）

specode 不再是状态机，而是一层**编排壳**：它只负责自己独有的价值——spec 生命周期、固定落盘、「文档即状态」的 phase 推断、`执行方式` selector、task-swarm 衔接桥；重活（澄清、设计、TDD 执行、验收）在对应 phase **自主调用 superpowers** 的 skill 完成，superpowers 缺席时 **specode-native 降级**承接。没有持久会话文件、没有多窗口加锁、没有 spec 配置文件、没有响应末尾状态摘要行、没有强制代码-文档同步唠叨、没有会话日志收集。

## Activation Guard

只在以下任一情况激活：

- 用户当前输入是 `/spec <需求>`、`/spec continue <slug>`、`/spec list`。
- 用户显式说「使用 spec 模式」/「use spec mode」/「按 spec 流程做」。

其余一律**不激活**，按普通对话处理。**没有 session 文件**——是否处于某个 spec 的活跃态，完全由**当前对话上下文**（这一轮在跑哪个 slug）+ **obsidian 里该 slug 目录下的文档**推断，不读任何持久状态文件。

## 核心不变式 🔒

无论执行引擎是 superpowers、task-swarm 还是 specode-native，spec 的产物**永远**是下面 3 份文档、**固定文件名**、**固定落盘**在 `<specsRoot>/<slug>/`。引擎只决定「谁生成内容」，不改变产物的形态 / 命名 / 位置。

| 文档 | 固定文件名 | 内容 |
|---|---|---|
| 需求 | `requirements.md` | 散文 spec：背景 / 为什么 · 范围(in/out) · 验收 `- [ ] AC-N` · 开放问题。纯自然语言，无任何形式化条款句式。 |
| 设计 | `design.md` | superpowers writing-plans 可执行计划格式：`Goal` / `Architecture` / `Tech Stack` + `## Task N`（每 Task 带 `**Files:**` 文件范围、`验证: AC-N` 回指需求、`- [ ]` TDD 步骤）。 |
| 执行日志 | `implementation-log.md` | 执行期追加：设计偏离 / 关键决策 / 最终验收小结。 |

缺陷修复不另起 `bugfix.md`——直接在 `requirements.md` 用散文写清 Current / Expected。`pipeline.yml` 仅「委托 task-swarm」时临时生成，非固定产物。

## specsRoot 解析（每次启用先读，缺失才问一次）

**每次启用 specode，先经 run.sh 调 `resolve_root.py get-root` 读 specsRoot**；只有 config 缺失（一般首次使用）才用 `AskUserQuestion` 问用户，问到后立即 `set-root` 写回 config，之后所有会话沉默自动用、不再打扰。

所有 specode CLI **必须**通过 `run.sh` 包装调用，脚本路径用 `$CLAUDE_PLUGIN_ROOT`（fallback `$CODEBUDDY_PLUGIN_ROOT`）拼**绝对路径**——禁止假设 cwd 在 scripts 目录，禁止裸 `python3 <脚本名>` 调用：

```bash
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/resolve_root.py" \
   <verb> <args...>
```

`run.sh` 自动探测 `python3 → python → py` 三档解释器并 exec 透传参数。verb 与 `commands/spec.md` 一致：

| verb | 作用 | exit |
|---|---|---|
| `get-root [--root P]` | 解析 specsRoot（`--root` > env `SPECODE_ROOT` > config.specsRoot） | 0 ok / 3 未配置 |
| `set-root --root <abs>` | 绝对路径，持久化到 `~/.config/specode/config.json.specsRoot` | 0 / 1 路径非绝对 |
| `list-specs [--root P]` | 列出 root 下含 `requirements.md` 的子目录名（slug，每行一个） | 0 / 3 未配置 |

**首次设置流程**：`get-root` exit 3 → 调 `AskUserQuestion` 问用户「文档管理目录」（绝对路径，将**原样**作为 specs 根，specode 不对其结构做任何假设或拼接）→ 用户给出后 `set-root --root <abs>` 持久化 → 之后不再问。`project_root` 默认取**当前终端 cwd**（约定先 `cd` 到项目目录再开聊），不再询问。路径解析细节见 `references/obsidian.md`。

## 流程（启动 → coding 完成）

每个 phase 都标注「装了 superpowers 调它 / 没装走 native」。判断「装没装」的方式：**先尝试用 `Skill` 工具调对应 superpowers skill，不可用（skill 不存在 / 调用失败）就走 native 分支**。

1. **specsRoot**：`get-root`（缺失走首次设置）→ 得 `<specsRoot>` → `mkdir -p <specsRoot>/<slug>/`（slug 由主代理从需求推导 kebab-case）；`project_root = cwd`。
2. **requirements（澄清 + 需求）**：
   - 装了 superpowers → 调 `superpowers:brainstorming`（内部做澄清 + 需求探索 + 用户批准门）。
   - 没装 → **specode-native**：主代理用 `AskUserQuestion` wizard（2-4 个阻塞性子问题）澄清，再按 `assets/templates/requirements.md` 模板写。
   - 产物归位到 `<specsRoot>/<slug>/requirements.md`（见 §superpowers 编排 + 落盘归位）。
3. **design（可执行计划）**：
   - 装了 superpowers → 调 `superpowers:writing-plans`（内部 self-review + 用户评审）。
   - 没装 → **specode-native**：按 `assets/templates/design.md` 模板自己拆 `## Task N` + `**Files:**` + `验证: AC-N` + `- [ ]` TDD 步骤。
   - 产物归位到 `<specsRoot>/<slug>/design.md`。
4. **「执行方式」selector**：design 完成后调 `AskUserQuestion` 呈现（自适应 4 选项，见 §执行方式 selector），逐字按 `references/selectors.md` 范例。
5. **执行**（按 selector 选项分流，均含 TDD）：
   - 委托 task-swarm（已装）→ 见 §task-swarm 衔接。
   - superpowers subagent-driven（已装）→ 调 `superpowers:subagent-driven-development`。
   - superpowers executing-plans（已装）→ 调 `superpowers:executing-plans`。
   - specode 自执行（降级）→ 主代理按 `design.md` 的 Task 顺序 TDD（写失败测试 → 跑红 → 实现 → 跑绿），逐个勾选 `- [ ]`。
   - 执行期追加 `implementation-log.md`。
6. **验收（coding 完成）**：
   - 装了 superpowers → 调 `superpowers:verification-before-completion`（可选再 `superpowers:requesting-code-review`）。
   - 没装 → **specode-native**：主代理对照 `design.md` 测试要点 / `requirements.md` 的 `AC-N` 逐条核验。
   - 散文「请验收」，在 `implementation-log.md` 写验收小结。**无正式验收门 selector**。

phase ↔ skill 映射速查：`requirements` → brainstorming；`design` → writing-plans；执行 → subagent-driven-development / executing-plans（task-swarm 路径不走 superpowers）；验收 → verification-before-completion / requesting-code-review。

## superpowers 编排 + 落盘归位（双保险）

superpowers 的 brainstorming / writing-plans 有自己默认的输出路径 + 文件名（如 `docs/superpowers/specs/YYYY-MM-DD-*.md`），所以委托时 specode 必须主动归位，保证核心不变式铁定成立：

1. **前置指示**：调 skill 前显式告诉它目标**绝对路径 + 固定文件名**（superpowers 的 spec location 支持用户偏好覆盖）——brainstorming 的 spec 产出 → `<specsRoot>/<slug>/requirements.md`，writing-plans 的 plan 产出 → `<specsRoot>/<slug>/design.md`（design 格式就是 writing-plans 格式，无缝衔接）。
2. **后置归位（兜底）**：skill 返回后校验 `<specsRoot>/<slug>/<固定名>` 是否就位；未就位则把 skill 实际产出的文件 `mv` / rename 到固定位置。无论 skill 是否遵循前置指示，不变式都成立。

何时调哪个 superpowers skill、前置 / 后置怎么做，详见 `references/superpowers-wiring.md`。

## 缺席降级（一等公民，非附注）

specode 对 superpowers 与 task-swarm 都是**软依赖**（纯运行期、靠本 SKILL 散文调用、零 import）。缺席时澄清 / 计划 / 执行 / 验收**全部下沉到 specode 自己处理**，保证只装 specode 也能完整跑通 启动 → coding 完成。降级矩阵与「调 superpowers」是**并列的一等路径**：

| phase | 装了对应 plugin | 缺席 → specode-native 降级 |
|---|---|---|
| 澄清 + 需求 | `superpowers:brainstorming` | 主代理用 `AskUserQuestion` wizard（2-4 问）澄清 + 按 `requirements.md` 模板写 |
| 可执行计划 | `superpowers:writing-plans` | 主代理按 `design.md` 模板拆 Task（Goal/Arch/Stack + `## Task N` + `验证: AC-N` + `- [ ]` TDD 步骤） |
| 执行 | task-swarm（并发）/ `superpowers:executing-plans` | 主代理按 `design.md` Task 顺序 TDD（红 → 绿），追加 `implementation-log.md` |
| 验收 | `superpowers:verification-before-completion` | 主代理对照 `design.md` 测试要点 / `AC-N` 逐条核验 + 写验收小结 |

**判断方式**：主代理先尝试 `Skill` 调对应 superpowers skill，不可用则走 native 分支。不要因为 superpowers 缺席就停摆或让用户去装——直接 native 承接。

## 执行方式 selector（design 完成后，固定且唯一的每-spec selector）

design 确认后调 `AskUserQuestion` 呈现**自适应 4 选项**——**装了哪个引擎才显示对应选项**：

1. **委托 task-swarm（多 agent 并发）** — 需装 task-swarm。
2. **superpowers subagent-driven（每 Task 派全新 subagent + 两阶段评审，推荐）** — 需装 superpowers。
3. **superpowers executing-plans（当前会话顺序批量 + checkpoint）** — 需装 superpowers。
4. **specode 自执行（顺序单 agent）** — native 降级，都没装时的唯一选项。

> 选项 2/3 都是 superpowers 的 skill（底层用 Claude Code 内置 Agent/subagent 能力），不是 Claude 内置工作流；两者 ergonomics 不同（前者干净上下文 + 逐 Task 评审，后者单会话连续批量）。

呈现时**逐字**按 `references/selectors.md` 的范例传 question / header / options——不要 invent、不要简化成更短的选项集。这是个人单人场景，去掉了 PreToolUse 硬校验，所以「逐字按范例」靠本规则约束。

## 续接（文档即状态）

`/spec continue <slug>`（slug 必填，缺失或不存在 → 报错 + 提示先 `/spec list`）：定位 `<specsRoot>/<slug>/`，读目录内容按下表推断 phase 续接：

| 目录状态 | 推断 phase | 续接动作 |
|---|---|---|
| 无 `requirements.md` | intake | 重新走 requirements（brainstorming / native 澄清） |
| 有 `requirements.md`，无 `design.md` | design | 走 design（writing-plans / native 拆 Task） |
| 有 `design.md`，存在未勾选 `- [ ]` Task | 执行中 | 续接执行（task-swarm 看 run 状态 / superpowers 续 executing-plans / native 顺序续） |
| `design.md` 全部 Task 已勾选 | 完成 | 走验收 / 提示已完成 |

`/spec list` 列出 `<specsRoot>` 下所有 spec 及各自推断 phase（查 slug / 总览用，**不续接**）；无任何 spec → 提示先 `/spec <需求>`。

## task-swarm 衔接（零硬依赖）

task-swarm 是**独立 plugin**，specode **零 import** 它、也不知其安装路径——一切调用走 task-swarm 自带的 `/task-swarm` 命令（其 `$CLAUDE_PLUGIN_ROOT` 自解析）。用户选「委托」后：

1. 读本 spec `design.md` 的 Task 列表 + 每 Task 的 `**Files:**` → 机械推导 `<specsRoot>/<slug>/pipeline.yml`（任务组 / `@writes` 文件 / `needs` 拓扑）。
2. **把 yml 摘要给用户过目**（任务组数 / 同文件冲突 / 拓扑），用户确认后再 init。
3. 调 task-swarm 自带的 `/task-swarm` 命令驱动其 plan → fork → advance → writeback → resolve 编排，直到 done。
4. 全程追加 `implementation-log.md`，done 后走验收。

**未装 task-swarm**（`/task-swarm` 不可用）→ 当场降级为「specode 自执行」或 superpowers 执行路径，不让用户卡住。

## Output Language

用户可见输出（摘要、问题、确认、状态、错误）——**中文**。

保留英文 / 原样：技术名、命令、文件路径、代码标识符；代码块内容；本 skill 自身的规则文件（SKILL.md / references）。需求若是英文，生成的 spec 文档可英文；其他面向用户的摘要 / 确认仍中文。

## Document Output Brevity

写 / 更新 spec 文档时**绝不**在 chat reprint 全文。报告只含：文件路径（一行）+ 3-8 条章节标题或关键变更 bullets + 未决问题（如有）+ 下一步动作。never paste 文档正文、完整 Task 列表、设计 rationale。用户显式要求才例外。

## Iron Rules

1. **固定产物不变式**：永远只产 `requirements.md` / `design.md` / `implementation-log.md` 三份，固定文件名，固定落 `<specsRoot>/<slug>/`，与执行引擎无关；委托 superpowers 后必须做后置落盘归位校验。
2. **specsRoot 先读 config 再问**：每次启用先 `get-root`；缺失才 `AskUserQuestion` 问一次并 `set-root` 写回，之后沉默自动用；用户给的目录原样作根，不拼接。
3. **CLI 必走 run.sh + 绝对路径**：所有 specode CLI 经 `run.sh` 包装 + `$CLAUDE_PLUGIN_ROOT`（fallback `$CODEBUDDY_PLUGIN_ROOT`）绝对路径；禁止裸 `python3 <脚本名>`。
4. **执行方式 selector 逐字按范例**：`AskUserQuestion` 的 question / header / options 逐字取自 `references/selectors.md`，自适应显示已装引擎对应选项；禁止 invent / 简化。
5. **轻量化红线**：不再有加锁 / 接管协议 / 状态机；不再有响应末尾状态摘要行；不再有强制代码-文档同步唠叨；不再有持久会话文件与 spec 配置文件的成对写入；不再有待处理 selector 标记 / phase 切换 CLI / 日志收集。活跃态靠当前对话上下文 + 文档存在性推断。

## References

- `references/selectors.md` — 「执行方式」selector 的 `AskUserQuestion` 调用逐字范例（首次设置目录的问法也在这）。
- `references/obsidian.md` — specsRoot 路径解析与目录约定。
- `references/superpowers-wiring.md` — 各 phase ↔ superpowers skill 的映射、前置指示与后置落盘归位指示。

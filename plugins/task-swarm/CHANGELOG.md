# Changelog — task-swarm

task-swarm 是从 specode 拆出的独立多 agent 编排 plugin。本文件记录其自身版本；specode 的变更见仓库根 `CHANGELOG.md`。

## Unreleased

## 0.8.2 (2026-06-28)

### Fixed — cmd_writeback prematurely 设 failed_status=done，导致 run-loop 跳过 cmd_resolve（v0.9 round 3 试跑实测）

**症状**：当 `pipeline_end_validator=true` 时，最后 group writeback 立即把 `sm.failed_status="done"`（cli.py:1217-1222 全 group terminal 检查），但 `pipeline_end_status` 还是 `pending`。run-loop break 路径检查 `sm.failed_status not in ("done"...)` → False → **跳过 cmd_resolve** → ingest_lessons 不跑 → case 不写盘。

**Round 3 实测**：run-loop pipeline-end advance pass 后 emit `final: all-done` 但 events log 无 `ingest-lessons` type，`.ai-memory/knowledge/cases/` 目录无 `case-ticket-csv-export.yml`。手动调 `resolve --run <id>` 才补救 sink。

**修法**：`cmd_writeback` 加 pipeline_end_status check — 全 group terminal 时，只有 `pipeline_end_status ∈ {not-required, passed}` 才设 `failed_status="done"`。`pending` / `failed` 时留给 `cmd_resolve` 在 pipeline-end 也终态后统一收尾，与 ingest_lessons 一起触发。

**Back-compat**：`pipeline_end_validator=false`（schema default）路径行为完全不变（pipeline_end_status="not-required" 始终满足）。

**Tests**: `tests/test_runloop_and_pipeline_end_logic.py` +3 case（pending 时不 finalize / not-required 时正常 finalize 保兼容 / passed 时 finalize）。task-swarm 测试 180 → 183 全过。

## 0.8.1 (2026-06-28)

### Added — M2 `run-loop` 子命令 + M3 pipeline-end validator logic 接入（v0.9 lifecycle gap 完整闭环）

0.8.0 ship 了 M7 init dedupe + M3 `run.pipeline_end_validator` schema 字段但 plan/advance 不消费；M2 run-loop 也留作"单独 PR"。本 release 把 lifecycle gap 全修完。

#### M2 — `task_swarm.py run-loop --run <id>`

**痛点**：v0.9 round-2 试跑暴露 host agent 一个 run 要手动调 12+ 次 advance / writeback / resolve（4 group × 3 phase + N 次 writeback + 1 次 resolve），机械性操作占 30% 烦人精力。

**修法**：新 `run-loop` 子命令 auto-drive 所有 mechanical 步骤直到需要 host fork：

```
while iter < max-iterations:
    sm = load(state.json)
    if all groups terminal + pipeline_end_status ∈ {not-required, passed}:
        auto-resolve → break (success)
    if all groups terminal + pipeline_end_status == pending + outbox ready:
        auto-advance --phase pipeline-end-validation; continue
    for each active group:
        if group.phase == "writeback":
            auto-writeback group; break to re-plan
        if group.phase in {coding/review/p0-fix/validation/v-fix}
           AND outbox_ready_for_advance(group):
            auto-advance --phase group.phase --group group.id; break to re-plan
    no auto-action this iter → emit plan (host fork needed); return
```

**契约**：host agent 在 fork subagent + 等齐所有 ✓ 完成 → 调 `run-loop` 替代手动 advance/writeback/resolve 串。host 仍负责 fork 决策，机械 state-machine plumbing 归 task-swarm。`--max-iterations` 默认 20 防死循环。`--no-ingest` 透传到 auto-resolve。

#### M3 — pipeline-end validator logic 接入

0.8.0 schema 加了 `run.pipeline_end_validator: bool` 字段但 plan/advance 不消费。本 release 完整 wire 起来：

- **StateMachine 加 `pipeline_end_status: str`** 四态（`not-required` / `pending` / `passed` / `failed`），init 时按 pipeline.yml 设置
- **plan**：所有 group 进 done + `pipeline_end_status == pending` → emit `pipeline-end-validation-fork` action（fork 单个 `validator-pipeline-end-r1` subagent，task.md 列所有组 stages union）；`failed` → emit `pipeline-end-failed` 提示选项
- **advance 新 phase `pipeline-end-validation`**（不需要 `--group`）：解析 `validator-pipeline-end-r1/outbox/validation.md`，pass → `pipeline_end_status=passed` / fail → `pipeline_end_status=failed`
- **resolve gate**：`pipeline_end_status in (pending, failed)` 时拒绝 resolve（让 host 走 `--abort` 或人工修后再跑 r2）

**有意不做的**：cross-group p-end-vfix loop（自动 v-fix 跨组太复杂；v0.9 / v1.0 评估是否值得）。当前 fail 时只 emit 选项让 host 决策。

#### Tests

`tests/test_runloop_and_pipeline_end_logic.py` 16 case 覆盖：M3 9 case（schema default/pending、plan emit、advance pass/fail、resolve 3 gate、abort 绕过）+ M2 7 case（nothing to auto / coding auto-advance / writeback auto / 无 pipeline-end auto-resolve / pipeline-end pass 一气呵成 auto-resolve / outbox 未 ready 时 emit fork action / max-iterations 安全）。task-swarm 测试 164 → 180 全过。

## 0.8.0 (2026-06-28)

### Added — M7 init dedupe + M3 pipeline-end validator schema 字段（v0.9 试跑 lifecycle 根因组）

第二轮试跑 wework-ops-assistant 暴露 lifecycle 完整性问题。本 release 修法 2 个（M7 + M3 schema），M2 run-loop（auto-advance）单独 PR 推进保持 scope manageable。

**M7：`task_swarm.py init` 检测同 spec_id 活跃 run**

试跑暴露：连续两次调 init（第一次输出被 head 截断让我以为没生成）产出 2 个互不知道的 run + 2 条 registry 项需手动清。**根因**：init 没 dedupe — silent 创建可能与现有 active run 冲突的新 run，registry 累积 stale 项。

修法：init 时扫 registry 找 `spec_id` 匹配且 `failed_status not in {done/failed/aborted}` 的活跃 run。找到时按 `--on-existing` 策略处理（新 flag）：

| 选项 | 行为 |
|---|---|
| `error`（默认）| exit 1 + 列出活跃 run + 提示 4 选项 |
| `resume` | 不新建，返回 existing 最新 run 信息（`resumed: true` 标记）|
| `abort-old` | 旧 run state.json 标 `failed_status: aborted` + events 加 abort 记录 + 新建 |
| `force-new` | 忽略 existing 强建（不推荐；旧 run 继续占空间）|

Stale registry 项（run_dir 已删 / state.json 损坏）silently 跳过——不会阻塞 fresh init。

**M3：pipeline.yml schema 加 `run.pipeline_end_validator: bool` 字段**

试跑暴露：跨组依赖（g1 → g2，g3 → g4）时 g1 单独跑 mvn compile 必 fail（依赖 g2 未实现 method），需要 host agent 给 g1 validator prompt 引导跳 compile 做静态检查。**根因**：pipeline.yml 缺「pipeline-end validator」语义——所有 group done 后跑一次整体 validator 比每组各自跑更合适。

**本 release 只做 schema 预留**（v0.8.1 实现 advance/plan logic）：

- `_pipeline.py validate()` 接受 `run.pipeline_end_validator: bool`，非 bool 报错
- `StateMachine` 加 `pipeline_end_validator: bool` 字段，从 pipeline.yml 解析、持久化到 state.json
- 默认 `false` 保持向后兼容；下游 plan/advance 暂不消费

**Tests**：`tests/test_init_dedupe_and_pipeline_end_schema.py` +9 case（5 个 M7 子任务覆盖 first init / blocks default / resume / abort-old / force-new；4 个 M3 schema 覆盖 bool 接受 / 非 bool 拒绝 / default false 持久 / true 持久）。task-swarm 测试总数 152 → 161 全过。

## 0.7.4 (2026-06-28)

### Strengthened — 方案 D 落地保障 + inbox 名实一致（v0.9 试跑 M5/M6/M10 聚类修）

第二轮真实试跑 wework-ops-assistant（ticket-assign-it-member）暴露 3 个相关摩擦点（"视野分裂 + 名实不符" 根因组）：

- **M5**：task.md「## 项目级约束（必读）」段头只说"项目/工作区根目录下"，没说**子目录路径**是按本组 `@writes` 上溯扫的——backend 组看不到 `ops-web/CLAUDE.md` 时容易误以为"无相关 web 约束"。
- **M6**：方案 D 完全依赖 subagent 自觉去 Read 段头列出的路径，缺强制信号；本试跑 host agent 在 fork prompt **额外**强调"必须先 Read"subagent 才真去读。
- **M10**：reviewer / validator inbox 在每个 task-swarm run 中都是空目录，task.md 描述"由主编排器在 fork 前放入"与实际行为不符（name-vs-fact 不一致）。

**架构师视角统一修法**（一个改动同时治三个）：

1. `_agent_docs_block` 段头改成：⚠ 前缀 + "在你发出第一个 Edit / Write / Bash 之前必须 Read" + "reviewer 会以此扣分" + 段尾加「路径覆盖规则」段解释 subdir 扫描行为。
2. 新增 `_drop_agent_docs_sentinel`：fork 时把同样路径列表写到 `inbox/_PROJECT_AGENT_DOCS.md`——subagent 在列 inbox 时会看到第二次冗余信号；且 inbox 不再是空目录（M10 名实对齐）。
3. coder / reviewer / validator 三个 render 函数都接 sentinel 调用。

**Tests**: `tests/test_prompt_agent_docs.py` +3 case（sentinel 存在 / 缺席 / 段头硬约束 + subdir 说明）；total 9 case；task-swarm 测试 152 → 155 全过。

### Considered + Rejected — M11 PyYAML optional

v0.9 试跑 M11 标"pipeline.yml YAML subset parser 不支持 anchor / flow map / block scalar"。**评估结论：不修**。Strict subset 是 task-swarm 的**设计哲学**（"never silently mis-parse"）不是限制——引入 PyYAML 会 silent 接受 `yes/no/on/off → bool` 等 YAML magic conversion 引入歧义；且让 10 个 `test_unsupported_constructs_raise` 失效。docstring 已记录决策：复杂 YAML feature 请重写为 subset。

## 0.7.3 (2026-06-28)

### Added — task.md 渲染加「## 项目级约束（必读）」段（AI-EDS v0.9 痛点 #14 方案 D）

试跑 `wework-ops-assistant` 时发现：coder/reviewer/validator 三种 subagent fork 出去后**完全不知道项目根 `CLAUDE.md` / `AGENT.md` 的存在**——subagent 进程 cwd 漂、CLAUDE.md 也不自动加载，只能看 task.md 给的指令。结果 dayjs import 顺序、commit 信息中英文规则等局部约束反复被违反。

修法（方案 D：路径引用而非内容拷贝）：

1. `_prompt.py` 加 `_agent_docs_paths(project_root, task_writes)` helper，按 3 层扫描固定文件名集 `CLAUDE.md / AGENTS.md / AGENT.md / CODEBUDDY.md`：
   - L1: `<project_root>/` 根
   - L2: `<project_root>` 的直接父目录（monorepo workspace 场景，如 wework-ops-assistant 父目录有 CLAUDE.md / 子 git repo 自身没有）
   - L3: 对每条 `@writes` 相对路径，从其所在目录向上递归到 project_root（exclusive），扫每层（覆盖 monorepo 内子包级 CLAUDE.md，如 `ops-web/CLAUDE.md`）
2. `render_coder_prompt` / `render_reviewer_prompt` / `render_validator_prompt` 在「上下文 / 路径规约」段之后插入「## 项目级约束（必读）」段，只列绝对路径 + 一句话 disclaimer：subagent 不会自动加载、开工前必读。
3. 完全不复制内容到 task.md（避免 token 浪费 + 内容陈旧风险）。

为何 path-only：CLAUDE.md / AGENT.md 本身就是 agent 记忆文件，主 agent 上下文里已经有副本；subagent 缺的只是「这里有一份你必须 Read 的文件」这条信号。把内容塞进 task.md 是冗余 + 维护负担。

6 个 regression tests in `tests/test_prompt_agent_docs.py`：① project_root 根 CLAUDE.md 出现在 task.md；② 无任何 doc 时段缺席；③ 子包 CLAUDE.md 经 @writes 触发；④ 父目录 AGENTS.md 命中（workspace 场景）；⑤ reviewer / validator 也带；⑥ project_root=None 段缺席。task-swarm 测试总数 146 → 152，全部通过。

## 0.7.2 (2026-06-28)

### Fixed — cwd 漂移后 plan/advance/writeback/resolve 找不到 run（AI-EDS v0.9 痛点 #12）

`task_swarm.py init --workdir /A/B/proj` 把 state 写到 `/A/B/proj/.task-swarm/`，但之前 `plan --run <id>` 只在 cwd + cwd.parents 里向上递归找 state.json — 一旦用户 `cd` 离开 workdir（很常见：跨项目协作 / IDE 不同 panel cwd 不一致 / Claude Code 主 cwd 漂移）就 `FileNotFoundError` 失败，必须每次手动 `cd <workdir>` 才能继续。

修法：user-wide registry `~/.task-swarm/registry.json` 在 init 时注册 `{run_id: {run_dir: <abs>}}`，后续 `_find_run_dir` 按 4 层 fallback 查找：

| 优先级 | 来源 | 用途 |
|---|---|---|
| 1 | `run_id` 本身是已存在的 path | 显式路径覆盖（脚本场景）|
| 2 | `$TASK_SWARM_WORKDIR` env | CI / docker / 显式 override |
| 3 | `~/.task-swarm/registry.json` ← **NEW** | init 自动写入，无须手动维护 |
| 4 | cwd + cwd.parents 递归扫 | back-compat fallback（registry 缺失时仍能 work） |

Registry 写是原子的（tempfile + os.replace），多 init 并发各自互不覆盖。Registry 指向的 run_dir 已删（用户 `rm -rf` 或移项目）时，会 fall through 到 cwd 递归 —— 不会返回 stale path。

8 个 regression tests in `tests/test_run_dir_lookup.py`，覆盖 4 个 fallback 路径 + registry 原子写 + stale entry fallback。task-swarm 测试总数 138 → 146，全部通过。

## 0.7.1 (2026-06-28)

### Fixed — task.md「## 任务清单」段渲染空（AI-EDS v0.9 痛点 #13）

`cli._items_as_stages` 构造 `StageEntry` 时漏填 `items` 字段，导致
`_prompt.render_coder_prompt` 里 `for it in stage.items` 循环 0 次，
渲染出的 coder task.md「## 任务清单（按顺序逐条完成）」段**完全空白**——
只有标题没内容。coder 拿不到具体任务指令、@writes/@reads tag、关联
requirements id，只能凭 first-line group name 一句话猜要做啥。
multi-agent fork 失去意义。

修法：构造 `StageEntry` 时把当前 item 透传到 `items=[it]`，保持
`_prompt.py` 现有 for-loop 渲染逻辑不变。

3 个回归测试新增（`tests/test_prompt_task_md.py`）：①完整 task title
渲染进任务清单段；②@writes/@reads/_需求_ tag 行内拼接；③空 group
仍渲染段标题（minimal contract）。修复前 1 pass 2 fail，修复后 3
pass。总测试 135 → 138。

真实试跑发现于 2026-06-28 wework-ops-assistant ticket-detail-timestamps
spec 的 coder fork 阶段（lead agent 偶然 Read task.md 才发现段空，
否则 coder 会拿着空指令瞎跑）。

## 0.7.0 (2026-06-27)

### Added — FIX-1 project_root frontmatter 优先（与 specode 3.2.0 配合）

`_ingest_lessons._resolve_project_root` 改为**frontmatter 优先**：读 `<spec_dir>/requirements.md` 的 `project_root` frontmatter；workdir 退化为 fallback。新增 `_read_frontmatter_project_root` helper。

收敛 AI-EDS ISSUE-3（双写分裂——task-swarm 用 workdir / specode-distill 用 frontmatter，曾静默分裂到两个 `.ai-memory/`）。

### Changed — FIX-2 knowledge writer rewire（与 codemap-aimemory 0.4.3+ 配合）

`ingest_lessons` 不再手写 case/pitfall yml dict：

- 按 spec 聚合**一个** case（id `case-<spec_id>`），消死代码 supersede（旧实现里 task-swarm `case-<spec_id>-<gid>` 与 distill `case-<slug>-implementation` 文件 stem 永不撞，supersede 永不触发 → 同一需求落两份重复 case 的 ISSUE-2 根因）
- payload 经 subprocess 调 `codemap knowledge write` 写盘；codemap 不在 PATH 时 inline 兜底
- 退役旧的 `_build_case` / `_merge_pitfall` / `_case_to_md` / `_pit_to_md` 手写逻辑

依赖：`codemap-aimemory >= 0.4.3`（含 `codemap knowledge` CLI）。

### 测试

task-swarm 总数 133 → 135，全部通过。

## 0.6.0 (2026-06-26)

### Added — knowledge-base/*.md 双产（与 .ai-memory/knowledge/*.yml 配对）

`resolve` 末尾的 ingest_lessons 现在**同时**写两份：

- `<project_root>/.ai-memory/knowledge/{cases,pitfalls}/<id>.yml`（v0.5
  已有，机器源）
- `<project_root>/knowledge-base/{cases,pitfalls}/<id>.md`（v0.6 新增，
  人读 + embedding 源）

md 与 yml stem 完全相同，是同一知识点的双形式。md 模板与
specode-distill 3.0 的 `references/doc-template.md` §4.2 (case) /
§5.2 (pit) 对齐：散文摘要 + 表格 + 历史段，比 yml 字段化更适合给未来
P1-3 embedding indexer 切片。

新 helper：

- `_case_to_md(case_yml: dict) -> str`
- `_pit_to_md(pit_yml: dict) -> str`
- `_atomic_write_text(path, text)` — 与 `_dump_yaml` 同步纪律的原子写

5 个新单测覆盖：md 同时写入 / md 内容覆盖 / 即使无信号也建 dir。
task-swarm 测试总数 126 → 129，全部通过。

### Note

PyYAML 仍是 optional：装了走 `yaml.safe_dump` 出 yaml frontmatter；
没装走 JSON-as-YAML（合法 YAML 1.2 子集）。md 正文本身是纯 markdown，
不依赖 yaml lib。

## 0.5.0 (2026-06-26)

### Added — P2-1 知识反馈回流（resolve 末尾自动 ingest_lessons）

为接入 AI-Enterprise-Delivery-System 四层记忆模型 L3 层，task-swarm
的 `resolve` 命令在 `failed_status == "done"` 时自动从本次 run 的产物
抽出 case + pitfall yml，写到
`<project_root>/.ai-memory/knowledge/{cases,pitfalls}/`，与
`codemap-aimemory` 的 L0/L1 + `spec-distill` 的 L2 共用同一目录根。

新增产物：

- `cases/case-<spec_id>-<gid>.yml`（每个 group 一份）— 记录本次实现的
  `changed_files` / `key_decisions`（来自 reviewer 提示）/
  `bugs_encountered`（来自 coder/validator 失败摘录）/
  `review_findings`（P0+P1）/ `acceptance_status` /
  `implementation_summary`（来自 coder 关键变更）。
- `pitfalls/pit-<sig>.yml`（每个独立的 validator 失败签名一份）— 记录
  `symptom`（failure_excerpt）/ `fix`（validator 修复指引 suggestion 集合）
  / `affects`（修复涉及的文件列表）/ `first_seen_in` / `seen_again_in`。
  同签名重复触发时 `seen_again_in` 追加新 spec_id，不覆盖
  `first_seen_in` — 实现 spec-distill v2 文档定义的"同 ID 升级规则"。

CLI 行为：

- `resolve --no-ingest` 跳过本步骤。
- `resolve --abort` / failed-deadloop 时**不**触发 ingest。
- `_emit` 的输出多一个 `ingest: {cases: N, pitfalls: M, skipped: ...}`
  字段，方便编排者校验。
- ingest 错误**绝不**冒泡：抛异常会被吞掉，写一条
  `events: [{type: "ingest-lessons", error: ...}]`，resolve 仍返回 0。

PyYAML 是 **optional**：装了就用 `yaml.safe_dump` 出人类可读 yml；没装
退回 `json.dump`（JSON 是合法 YAML 1.2 子集，下游 spec-distill kn_scan
+ codemap-aimemory 既能读 PyYAML 也能读 json，行为等价）。

11 个新测试覆盖：skip 路径、case 字段、acceptance 状态推导、review
findings 严重度、未完成 group 跳过、pitfall 写入、签名合并、纯 pass
不出 pitfall、缺失 outbox 容忍、workdir fallback、spec_id fallback。
task-swarm 测试总数 115 → 126，全部通过。

### 设计参考

- `pluginhub/plugins/obsidian-wiki/skills/spec-distill/references/doc-template.md`
  — case/pitfall yml schema 的权威定义。
- `Obsidian/Notes/07-Ideas/AI-Enterprise-Delivery-System/01-知识体系构建与优化方案.md`
  §6.P2 — 闭环设计与"知识自动生长"目标。

## 0.4.1 (2026-06-19)

### Changed — 指令文档英文化（降 token，**无行为变更**）

将 `SKILL.md` / `commands/swarm.md` / `agents/*.md` / `references/*.md` 的中文指令散文按语义改写为英文（非直译，与 specode 1.0.1 同款），降低常驻/按需加载的 token。中文字符 ~7900 → ~285（仅余 load-bearing 协议 token）。

- **保留中文（运行时协议契约，逐字不动）**:被 `_outbox.py` 解析或 `_prompt.py`/`cli.py` 生成的字面量——schema section 头（`## 判定` / `## 结论` / `## 子任务状态` / `## 复现命令` / `## 按子任务的验证结果` / `## 失败现场` / `## 给 coder 的修复指引` / `## 关键变更` / `## 给下游 reviewer 的提示` / `## 给使用者的提示` / `## P0`-`P2`）、字段前缀（`- 文件:` / `- 位置:` / `- 问题:` / `- 建议:`）、`_需求：x.y_`、`### 修复 N —`、`STATUS:`、fix-status 标签（`[P0 已修复]` / `[P0 未修复]` 等）、verbatim 提醒句、跨工具 marker（`检查点` / `> ⚠️ 评审建议`）。
- `.py` 与 114 个测试**零改动**;全套测试通过。
- 顺带修一处 pre-existing 文档不一致:`agents/task-swarm-validator.md` 抽象 schema 的 `## 失败原因（如果 fail）` 对齐为解析器/`_prompt.py` 实际使用的 `## 失败现场（fail 时必填）`。

## 0.4.0 (2026-06-19)

### Changed (BREAKING) — 命令叶子改名 `task-swarm` → `swarm`（→ 0.4.0）

原命令文件 `commands/task-swarm.md` 调用形态是 `/task-swarm:task-swarm`（插件名与命令名重复）。改命令文件名为 `commands/swarm.md`,调用形态变为 `/task-swarm:swarm`(菜单显示 `/swarm (task-swarm)`)。命名空间前缀 `task-swarm:` 来自插件名,去不掉,但去掉了重复。

- `commands/task-swarm.md` → `commands/swarm.md`(`git mv`,内容不变)。
- 同步更新引用:`skills/task-swarm/SKILL.md`(`/task-swarm:swarm` 触发提示 + `commands/swarm.md` 模板路径)、`references/task-swarm.md`(协议归属命令 + deadloop 重跑指引)、`scripts/task_swarm.py`(API surface 注释)、`tests/test_standalone_smoke.py`(读 `commands/swarm.md`)。
- **迁移**:旧 `/task-swarm:task-swarm` 不再存在;改用 `/task-swarm:swarm`。
- 注:`references/task-swarm.md` 等**文件名**不变(那是协议文档,与命令叶子名无关)。

### Fixed — `run.sh` 包装路径在 `$CLAUDE_PLUGIN_ROOT` 为空时 127

与 specode 同源 bug:`$CLAUDE_PLUGIN_ROOT` 只对 hook/MCP 子进程导出,skill 发出的 Bash 调用里为空,旧写法 `${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}` 展开成 `/scripts/run.sh` → `Exit 127`(执行记录里靠硬编码 `TS_ROOT=.../task-swarm/0.3.1` 绕过)。

- `commands/swarm.md`(init + heartbeat 模板 + 7 步循环说明)改为带兜底的 resolver:env var 命中则用,否则 `find` 出 cache 里最新版本(`sort -V | tail -1`),**不写死版本号**;用 `find` 而非 shell glob(zsh 下不匹配的 glob 会中止)。task-swarm 无 hooks,故无需保留裸 env-var 形态。

## 0.3.1 (2026-06-18)

> 死代码清理 + 去重，**无行为变更**（纯瘦身，net -600 余行非测试代码）。

- 删 `_writeback.py`（`writeback_tasks_md` 等自 M3 起已是死代码：只剩 `cli.py` 死 import + 单元测试，主路径不调用）及其测试 `test_task_swarm_writeback.py`（9 例）。
- 删 `spec_log.py`（会话日志收集，仅 CLI 入口/出口各调一次且有 fallback；与 specode 1.0.1 删同款一致）；移除 `cli.py` 仅为日志而存在的 `_log_wrap_main` 包装。
- 去重：`_now_iso` / `_atomic_write_text` 此前各定义 3 处，统一到 `_state.py` 由其它模块 import；`_outbox.py` 中英文冒号解析提取 `_after_colon` helper。
- CLI 命令集 / pipeline.yml schema / state.json 结构 **均无变化**。

## 0.3.0 (2026-06-15)

首发版本。task-swarm 自 specode 拆出（specode 0.11.0），独立可运行的多 agent 编排器：pipeline.yml 声明式编排 + 语义任务组跨组并发 + per-组 reviewer/validator 循环。

### Added -- 独立 plugin + 解耦（M1）

- 从 specode 摘出 state machine / outbox / prompt / writeback / cli 等，自带 `task_swarm.py` launcher + `run.sh`/`run.cmd` 包装。
- 状态根 `<workdir>/.task-swarm/runs/<run_id>/`，不依赖任何 specode session / 锁。
- stdlib-only（运行时无第三方依赖）。

### Added -- YAML 声明式编排 + 独立 SKILL（M2）

- **pipeline.yml** 成为唯一编排输入（受限 YAML 子集，自写 stdlib parser + schema 校验）。
- 自带 `SKILL.md`：主代理 = orchestrator + planner，读需求/design → 生成 pipeline.yml → 驱动 swarm。零 specode 依赖。
- `init → plan → fork → advance → writeback → report` 完整流程；`report` 从 state.json 按需渲染。
- 移除 markdown 路径耦合，收敛 yml 单轨（0.3.0 起 `--tasks` 已删）。

### Added -- 语义组下沉 + 跨组并发（M3）

- reviewer/validator 从「文件冲突批次」下沉到「语义任务组」（pipeline.yml 的 `task_group`），每组一个独立子状态机。
- **调度层**（`_schedule`，纯函数）：`needs` 拓扑 + `writes` 不相交 → 跨组并发；`plan` 返回多组 `schedule` + `actions`，主代理同 message fork 多组 coder（总并发受 `max_parallel`）。
- `advance --group <gid>` / `writeback --group <gid>` per-group 推进；agent_key 绑 gid（`coder-{gid}-s{n}` / `reviewer-{gid}` / `validator-{gid}`）。
- validator 默认跨组并发 + `--serial-validation` 逃生口（测试有共享资源时全局串行）。

### Added -- specode 委托模式接口（M4）

- `init` 接可选 `--spec-id` / `--spec-dir` 作回溯标注（被 specode 委托时用）；行为/state 不变，不反向依赖 specode。
- 被 specode 的 `delegated` 阶段委托时，resolve 后由调用方主代理（按 specode SKILL）决定下一步。

### 设计要点

- **state.json 单一事实源**；report 是其纯函数视图。
- **死循环保护**：validator 连续 3 轮同 fail 签名 → `failed-deadloop`。
- **C 模型**：主代理驱动 plan→fork→advance 循环，CLI 只守机械完整性（schema / agent_key / advance 产物 / 原子写禁手改），不压主代理思考。

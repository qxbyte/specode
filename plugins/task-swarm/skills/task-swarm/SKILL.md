---
name: task-swarm
description: Use when driving the task-swarm multi-agent orchestrator standalone — reading a requirement/design doc, generating a pipeline.yml, then running the fork → review → validate loop to完成 a multi-task implementation. Trigger words：task-swarm、并发执行任务、pipeline.yml 编排、多 coder fork。
---

# task-swarm 独立编排 SKILL

## §0 你是谁

主代理 = task-swarm 的 **orchestrator + planner**。task-swarm 提供四样东西:
pipeline.yml 编排格式、状态机 CLI(`task_swarm.py`)、子 agent 角色定义
(coder/reviewer/validator)、报告渲染。

CLI **只守 4 处机械完整性**,其余编排判断全归你,CLI 不压你思考:
1. schema 校验(pipeline.yml 格式合法)
2. agent_key 一致(状态机与产物对得上)
3. advance 产物齐全 / 格式检查
4. 原子写 + 禁手改受控文件

task-swarm **独立运行,不依赖 specode**。若同时装了 specode,由 specode 侧
委托接入,那也是 specode 调 task-swarm 的独立接口,不是反向耦合。

### 委托模式(被上层 spec 工作流集成时)

被上层 spec 工作流委托执行时,`init` 会额外带 `--spec-id <id>` / `--spec-dir <dir>`
两个**可选回溯参数**(已支持,见 §2 / commands),仅用于把本 run 标注到来源
需求,方便报告回溯;task-swarm 自身行为、state 落盘位置、状态机都不变。
run `resolve` 收尾后,由调用方主代理(按其自身工作流的规则)决定下一步——
task-swarm 不感知、也不驱动调用方的后续阶段。

## §1 独立流程总览(7 步)

1. **接需求**:design.md / requirements / superpowers plan / 裸需求 / 已写好的 pipeline.yml
2. **兼 planner 生成 pipeline.yml**(§2);若入参已是 `.yml` 且 schema 通过 → 跳过此步
3. `init --pipeline <yml> --workdir <项目根>` 拿 `run_id`(测试有共享资源/端口时加 `--serial-validation`)
4. `plan --run <id>` 返回**runnable 组集** → **同一 message** fork 这些组的全部 coder(总并发 ≤ `max_parallel`,逐字拷 plan 给的 agent_key)
5. **各组等齐所有 in-flight Task ✓ completed**(机械纪律,§4)→ `advance --run <id> --group <gid> --phase <p>`
6. `writeback --run <id> --group <gid>`(finalize 本组)→ 回第 4 步;`needs` 满足后下游组解锁进 runnable,直到全组 done
7. 全组 done → `resolve --run <id>` 收尾 → `report --run <id>` 出报告

所有 `task_swarm.py` 调用走 `run.sh` 包装(见 commands/task-swarm.md 模板)。

## §2 主代理兼 planner —— 生成合规 pipeline.yml

- 读需求文档,理解要做什么。需要代码库现状时 **fork `Explore` 子 agent 调研**,
  但调研结果由**你**综合成 yml——planner 角色是你,不是子 agent。
- 拆成 `task_group`(语义任务组),每组内 task 点遵守:
  - `@writes`(yml 里 `writes:`)跨**可并发组**不相交;冲突文件必须串行,用 `needs` 拓扑表达
  - 粒度 30min–2h 可完成;太大要拆;能并发就不硬绑依赖
  - 每个任务组配 reviewer + validator(下沉到任务组;细化见后续里程碑)
- **格式照 `references/pipeline-yaml.md` 写,别凭印象**(受限 YAML 子集,踩坑见该文)
- 写完跑 `init --pipeline` 触发 schema 校验;报错按提示改 yml 重试(**自修环**,直到 init 成功)

## §3 角色 / 状态机 / 产物 schema / 死循环保护

→ `references/task-swarm.md`(动手前至少扫 TOC + §3 状态机 + §9 CLI 速查)。
**禁止凭印象推** advance/writeback 的失败处理——细节都在 references。

## §4 机械纪律(对应 CLI 4 守点,违反必出乱)

- **advance 前必须等齐本组所有 fork 的 Task ✓ completed**;任何 streaming/running Bash 都不能 `advance --group <gid>`。
  不确定时调 `plan --run <id>`,若返回 `*-waiting` 动作就回到等待。
- **禁止自创 agent_key**:必须用 plan 给的规范名(`coder-{gid}-s{n}-r1`、`reviewer-{gid}-r1`、`validator-{gid}-r1`、`coder-vfix-{gid}-r{R}-f{I}` 等,gid 为组 id 如 g1),不要自编 `coder-fix-xxx`。
- **result.md 缺 STATUS** → 重 fork **同名** agent(先清其 outbox),**绝不手补 STATUS**(缺 STATUS 多半是 subagent 提前退出、代码没刷盘)。
- **禁止手改受控文件**(state.json / outbox 产物)——CLI 会 exit 2 拦截。

## §5 异常出口

coder STATUS=failed/blocked、writeback 越界、`failed-deadloop`(连续 3 轮同 fail 签名)
→ **停循环、向用户报告、等用户介入,不要自动 retry**。详见 `references/task-swarm.md` §3 / §8。

## §6 无 specode 依赖声明

本 SKILL 不引用 specode 的会话脚本 / selector / 验收阶段。state 落盘
`<workdir>/.task-swarm/runs/<run_id>/`。独立模式无 spec 锁概念,无 session 门槛——
用户可直接 `/task-swarm <需求文档>` 触发。

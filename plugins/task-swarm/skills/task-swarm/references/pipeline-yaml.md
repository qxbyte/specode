---
description: Use when 编写或理解 task-swarm 的 pipeline.yml —— 任务编排的主格式(YAML 子集 + schema)。
---

# pipeline.yml — task-swarm 编排格式

pipeline.yml 是 task-swarm 的**主编排格式**(取代 legacy 的 markdown `tasks.md`)。用 `task_swarm.py init --pipeline <file>` 启动一次 run。

## 受限 YAML 子集

task-swarm 自带一个 stdlib parser，只支持 YAML 的一个子集：

- **支持**：block map(2 空格缩进)、block list(`- `)、flow list(`[a, b]`)、单行 scalar(str / int / `true` / `false` / null)、单/双引号字符串、`#` 注释。
- **不支持(会报错，带行号 + 构造名)**：block scalar(`|` / `>`)、flow map(`{k: v}`)、anchors / aliases(`&` / `*`)、多文档(`---`)、tags(`!!`)、嵌套 flow。
- bool 只认 `true` / `false`；`yes` / `no` / `on` / `off` 会被当作字符串。

## Schema

```yaml
version: 1
run:
  spec_id: user-login        # 可选
  max_parallel: 4            # 可选,默认 4
  max_rounds: 6              # 可选,默认 6
task_groups:                 # 必填,≥1(= 语义任务组)
  - id: g1                   # 必填,唯一
    name: "Q01 接口改造"      # 必填
    needs: []                # 可选;引用其它 task_group id(组间依赖)
    review:                  # 可选,默认 {reviewer: true, validator: true};M3 起 per-组生效
      reviewer: true
      validator: true
    tasks:                   # 必填,≥1(= 任务点)
      - id: g1.1             # 必填,唯一
        title: "改 controller"  # 必填
        writes: [src/a.py]   # 必填(coder),≥1;文件冲突 → 并发调度依据
        reads:  [src/base.py] # 可选
        requirements: ["1.1"] # 可选;需求回溯
```

## 调度语义(M3 跨组并发)

task-swarm 按任务组并发驱动,调度由两条规则决定哪些组当轮可同时跑(`plan` 的 `schedule.runnable`):

- **`needs`(组间依赖,拓扑解锁)**:`needs: [g1]` 表示本组要等 `g1` 进入终态(`done`)后才能开始。`needs` 必须引用已存在的 `task_group id`(否则 schema 报 `needs unknown group`);上游组 `failed` → 下游组进 `blocked`(`upstream failed`)。无 `needs` 的组从一开始就 runnable。
- **`writes` 跨并发组不相交**:调度层取每组所有 task 的 `writes` 并集;若某组的 writes 并集与**当前在跑组**的 writes 有交集,该组进 `blocked`(`writes conflict with running group`),等冲突组结束后下一轮才进 runnable。因此**有文件冲突的组天然串行,无冲突的组自动并发**——不需要手写依赖来表达文件互斥,但若希望强制顺序(非文件冲突)仍用 `needs`。
- 总并发还受 `run.max_parallel`(默认 4)上限。
- `init --serial-validation` 额外让 validator 全局串行(同一时刻只允许一个组处于 validation/v-fix),用于测试有共享资源/端口冲突的场景——不影响 coding 并发。

## 用法

```sh
task_swarm.py init --pipeline pipeline.yml --workdir <项目根> [--serial-validation]
```

schema 校验失败或 YAML 越界 → 退出码 1 + 逐条错误,不建 run。

> 注:`review` 字段当前(M2)仅解析、暂用全局 `--skip-validator`;per-任务组生效见后续里程碑。pipeline.yml 是**唯一输入格式**(markdown `tasks.md` 路径已在 M3 移除)。

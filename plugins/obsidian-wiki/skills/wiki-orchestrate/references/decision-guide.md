# 决策建议（启发式，非规则）

供 `wiki-orchestrate` 在第 2 步汇总行动计划、第 4 步逐阶段执行时参考。

> **这是建议，不是规则。** 下表把"常见体检信号"映射到"通常适合调哪个 skill 的哪个命令"。
> 表未覆盖的情形、以及任何优先级 / 敏感性 / 上下文权衡，**由模型按 `sub-skills.md` 自行裁量**，
> 可以偏离本表。能力清单以 `sub-skills.md` 为准。

---

## 信号 → 建议对照

| 体检信号（来自两方报告） | 通常适合 | 建议命令 / 参数 | 需用户确认 |
|---|---|---|---|
| struct check `缺 marker > 0` | wiki-struct | 按其 SKILL.md 走 `init`（逐文件确认）→ 再 `apply` | 是（init 逐文件 + 阶段检查点） |
| struct check `drift > 0` 且无缺 marker | wiki-struct | `apply`（可 `--scope home\|readmes\|partitions` 限范围） | 是（阶段检查点） |
| struct check `broken > 0` | wiki-struct（报告） | `wiki-struct check` 报出坏链；改名导致的结构内引用可由 `apply` 重生修复；内容笔记里的真悬空交用户处理（指向只读目录的按 `readonly-dirs-policy.md` 改名启发式）。**wiki-curate lint 不处理坏链。** | 视情况 |
| 巡查发现孤儿页 / 缺「用途」段 | wiki-curate | `curate` | 是（阶段检查点 + 破坏性动作前确认） |
| 收件箱（`99-Inbox/`、`Clippings/`）积压 | wiki-curate | `ingest <path>` 逐篇 | 是 |
| 需要整体健康体检 | wiki-curate | `lint`（输出 `lint-report.md`） | 否（只读） |
| 某阶段体检无可做项 | —（跳过该阶段） | 报告记"无需处理" | 否 |

---

## 默认执行顺序（可调整）

1. **结构层**（wiki-struct）——确定性、安全，为后续提供正确导航 / 反链基线。
2. **策展收尾**（wiki-curate）——补「用途」、挂孤儿、收件箱归类、最后 lint。

> 原第 2 阶段「知识沉淀（spec-distill）」已于 v2.0.0 剥离，能力迁移到 specode 的 `/specode:distill`。

模型可据体检结果**跳过**任一空阶段，或在有充分理由时调整顺序，但每次调整都在
`orchestrate-report.md` 里注明原因。

---

## 模型判断点（建议遵循的思路）

- **跳过 vs 执行**：阶段对应的体检计数为 0 → 跳过，并在报告标注。
- **敏感内容是否纳入**：交给子 skill 的敏感拦截关卡；入口不放宽其红线。
- **坏链归因**：含 `[[...]]` 指向只读目录（`07-Ideas/`/`10-Work/`/`SpecIn/`）的悬空，
  优先怀疑用户在 Obsidian 改名 → 按 wiki-curate `readonly-dirs-policy.md` 思路处理，
  不擅自在只读目录改名。

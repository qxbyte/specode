---
description: 手动把一个已完成（或进行中）的 spec 沉淀为项目 knowledge-base/ 的原子定位知识点（cases/ + navigation/ + MEMORY.md）。可选复制一份到 Obsidian 库。仅手动触发，绝不自动运行。
---

`/specode:distill <slug>` — 把单个 spec 提炼成**原子定位知识点**，落盘到该 spec 所属项目的 `knowledge-base/`，并可选复制一份到 Obsidian 库。

用法：

- `/specode:distill <slug>` — slug 必须能在 `<specsRoot>/` 下找到对应目录；`<slug>` 为必填
- 可选 flag：`--target-dir <abs-path>` — 直接指定 Obsidian 副本目录（绝对路径；直写不拼接）；不给时 distill 结尾会用 `AskUserQuestion` 询问是否复制以及目标路径

行为：调用 `distill` skill，纯粹从 spec 文档 + 当前 agent 上下文提炼原子知识点（case / navigation 两类）→ 落盘到项目 `knowledge-base/` → 重建 MEMORY.md 索引 → 可选 Obsidian 副本。完整流程以 `skills/distill/SKILL.md`（当前权威）为准。

> 建议在**执行 + 验收完成后**运行：沉淀「已落地 + 已验证」的知识点价值最高；在未执行完的 spec 上沉淀，知识点可能指向未落地代码（distill Step 1 的执行完成度检查会告警）。

红线（v5.1+）：

- **主写域 = `<project_root>/knowledge-base/`**（`cases/` + `navigation/` + `MEMORY.md`）；Obsidian 是**可选副本**，不是默认主产物
- spec 目录**只读**：绝不修改 `<specsRoot>/<slug>/` 下任何文件
- **md-only**：无 yml、无 `codemap knowledge write`、无 `.ai-memory`、无任何静默注入
- `--target-dir` / 用户输入路径**直写不拼接**；`/Volumes/` 下需先校验挂载
- `knowledge-base/` 不提交项目仓库（落盘时 `ensure-gitignore` 保证）
- `project_root` 经 `resolve_root.py read-project-root --spec ...` 读取，**不从 cwd 反推**
- **仅手动触发** —— specode 主流程绝不自动调用；验收收尾后仅提示入口

> 需要 v3 的旧行为（自动触发 + 写 `.ai-memory/knowledge/` 的 yml）？checkout `backup/specode-v3.4.0-task-swarm-v0.9.2`。

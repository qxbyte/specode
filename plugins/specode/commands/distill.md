---
description: 手动把一个已完成（或进行中）的 spec 整理成 Obsidian 友好的 markdown 知识笔记（默认 md-only，写到 11-KnowledgeBase）。仅手动触发，绝不自动运行。
---

`/specode:distill <slug>` — 把单个 spec 手动整理成 Obsidian wiki 的 markdown 知识笔记。

用法：

- `/specode:distill <slug>` — 显式给 slug；`<slug>` 必须能在 `<specsRoot>/` 下找到对应目录
- `/specode:distill` — 不带参数时，host agent 默认沉淀**当前会话刚处理的 spec**（specode 主流程刚走完 acceptance 的那个）；如果当前会话不在 spec 上下文里，host agent 应先建议 `/specode:list`
- 可选 flag：`--target-dir <abs-path>`（覆盖默认输出目录）

行为：调用 `distill` skill，**纯粹从 spec 文档**提炼，按 5 维启发式拆分 → 生成分类别 markdown 笔记 → 落盘。完整流程与字段模板以 `skills/distill/SKILL.md`（v4+ 权威）为准。

红线（v4.0.0+）：

- spec 目录**只读**
- 默认 **md-only**；**唯一写入范围**是 `--target-dir`（默认 `/Volumes/External HD/Obsidian/Notes/11-KnowledgeBase/<slug>/`）。**不写** `<project_root>/.ai-memory/`、**不调** codemap recall、**不**自动注入未来 spec
- **仅手动触发** —— specode 主流程（requirements → acceptance）绝不自动调用它
- `project_root` 仅用于叙述里的相对路径解析，**非必需**；缺失不阻塞

> 需要 v3 的旧行为（自动触发 + 写 `.ai-memory/knowledge/` 的 yml）？checkout `backup/specode-v3.4.0-task-swarm-v0.9.2`。

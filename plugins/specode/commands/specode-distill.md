---
description: 把一个已完成（或进行中）的 spec 沉淀为结构化知识，落到该 spec 所属项目的 .ai-memory/knowledge/ 与 knowledge-base/。
---

`/specode:specode-distill <slug>` — 沉淀单个 spec 的知识到该 spec 自己的 `project_root`。

用法：

- `/specode:specode-distill <slug>` — 显式给 slug；`<slug>` 必须能在 `<specsRoot>/` 下找到对应目录
- `/specode:specode-distill` — 不带参数时，host agent 默认沉淀**当前会话刚处理的 spec**（specode 主流程刚走完 acceptance 的那个）；如果当前会话不在 spec 上下文里，host agent 应先建议 `/specode:specode-list`

行为：调用 `specode-distill` skill 走 5 步流程（解析 project_root → 准备目录 → 读 spec 全文 → AskUserQuestion 拆分提议 → 写 yml + md 双产物）。详见 `skills/specode-distill/SKILL.md`。

红线：

- spec 目录只读
- 仅写 `<project_root>/.ai-memory/knowledge/` 与 `<project_root>/knowledge-base/` 两个目录
- `project_root` 必须从 `requirements.md` frontmatter 读到，否则报错停止（specode v2.0 之前生成的 spec 缺该字段，需手补）

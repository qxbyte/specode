---
description: Use when design is complete and you need to present the "execution mode" selector to the user — verbatim AskUserQuestion example for specode lite's single fixed selector.
---

# Execution mode selector (the one fixed selector)

After design.md is confirmed, call `AskUserQuestion` with **adaptive option assembly** (include only options for engines that are installed, up to 4; if none are installed, only the specode self-execute option remains and you may skip the selector and proceed directly). Pass label/description verbatim — do not translate or simplify:

- question: "design 已完成。怎么执行？"
- header: "执行方式"
- multiSelect: false
- options (trimmed based on what is installed):
  - label: "委托 task-swarm（多 agent 并发）"
    description: "需已装 task-swarm。读 design Task + Files 生成 pipeline.yml，过目后并发执行。"
  - label: "superpowers subagent-driven（每 Task 派全新 subagent + 两阶段评审，推荐）"
    description: "需已装 superpowers。调 subagent-driven-development：每 Task 派全新 subagent，Task 间两阶段评审，上下文干净。"
  - label: "superpowers executing-plans（当前会话顺序批量 + checkpoint）"
    description: "需已装 superpowers。调 executing-plans：单会话内顺序执行 + checkpoint。"
  - label: "specode 自执行（顺序单 agent）"
    description: "都没装时的降级。主代理按 design Task 直接 TDD + 自验。"

Constraint: immediately end the turn after calling `AskUserQuestion` and wait for the user's choice; once selected, advance along the chosen path within the same turn (see SKILL.md §pipeline).

Note: `subagent-driven-development` / `executing-plans` are superpowers skills (backed by Claude Code's built-in Agent/subagent) — they are not native Claude workflows.

## First-time directory setup (asked once when config has no specsRoot)

When `resolve_root.py get-root` exits 3 (no config) — the script cannot resolve the root, so the model cannot either — call `AskUserQuestion` to ask the user for their document management directory, then call `resolve_root.py set-root --root <abs>` to write it to `~/.config/specode/config.json`. Example:

- question: "specode 还没设文档管理目录。spec 文档要落到哪个目录？（请给绝对路径，将原样作为 specs 根，每个 spec 建 <目录>/<slug>/ 子目录）"
- header: "文档目录"
- multiSelect: false
- options:
  - label: "我来输入绝对路径"
    description: "用 Other 输入一个绝对路径（如 /Volumes/External HD/Obsidian/Notes/spec-in/<os>-<user>/specs）。"

Once the user provides the path: `resolve_root.py set-root --root <user-provided-absolute-path>` persists it → all subsequent sessions read from config and will not ask again. The user may also provide the path directly in chat; handle that equivalently.

## Non-fixed selectors (informational — no examples here)
- **continue requires a slug**: `/spec continue` does not perform dynamic slug selection; use `/spec list` to find slugs.

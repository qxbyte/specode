---
description: Use when specode needs to invoke a superpowers skill at a given phase, or determine whether to fall back to native — phase↔skill mapping, artifact placement double-check, and fallback matrix.
---

# superpowers orchestration mapping

| Phase | superpowers installed | Absent → specode-native |
|---|---|---|
| Clarification + requirements | superpowers:brainstorming | AskUserQuestion clarification + write per requirements template |
| Executable plan | superpowers:writing-plans | Self-decompose Tasks + TDD steps per design template |
| Execution | task-swarm / superpowers:subagent-driven-development / superpowers:executing-plans | Sequential TDD following design Tasks |
| Acceptance | superpowers:verification-before-completion (+ requesting-code-review) | Verify each design test point / AC item in order |

## Artifact placement (double-check, invariant enforcement)
1. Pre-call: when invoking a skill, explicitly pass the target absolute path and fixed filename (brainstorming → requirements.md; writing-plans → design.md).
2. Post-call: after the skill returns, verify that `<specsRoot>/<slug>/<fixed-name>` is in place; if not, move/rename the skill's actual output to that path.

## Availability check
Attempt to invoke superpowers via the Skill tool first; if unavailable or not installed, take the native branch. Same logic applies to task-swarm (if `/task-swarm` invocation fails, fall back to native).

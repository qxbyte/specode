# CodeBuddy Adapter

**Status: verified.** CodeBuddy 2.97.1 (`AI_AGENT=claude-code_2-1-142_agent`) is
a Claude Code fork. Plugin / hook contract is byte-for-byte compatible — the
same `hooks/hooks.json` and `scripts/spec_guard.py` work without modification.
Verification was done by loading this plugin via `--plugin-dir` and capturing
hook invocations with `hooks/hooks-probe.json`.

## Verified contract

### Plugin discovery

CodeBuddy looks for the manifest in `<plugin-root>/.claude-plugin/plugin.json`
(also accepts `.codebuddy-plugin/` and `.workbuddy-plugin/`). The current
location works on both harnesses:

```
spec-mode/
  .claude-plugin/plugin.json   ← discovered by both Claude Code and CodeBuddy
  hooks/hooks.json
  commands/*.md                ← loaded as /spec-mode:<name>
  skills/spec-mode/SKILL.md    ← loaded as skill
  scripts/spec_guard.py
```

`codebuddy plugin validate <plugin-dir>` accepts this layout.

### Environment variables CodeBuddy injects

| Variable | Value | Notes |
|----------|-------|-------|
| `CLAUDE_PLUGIN_ROOT` | absolute path to plugin | Compatibility alias |
| `CODEBUDDY_PLUGIN_ROOT` | same as above | Native CodeBuddy form |
| `CLAUDE_PROJECT_DIR` | user's cwd | Compatibility alias |
| `CODEBUDDY_PROJECT_DIR` | same as above | Native CodeBuddy form |
| `CODEBUDDY_PLUGIN_DIRS` | colon-separated list | All loaded plugin dirs |
| `CLAUDECODE` | `1` | Claude Code compat marker |
| `AI_AGENT` | `claude-code_2-1-142_agent` | Identifies the underlying agent |

So our existing `${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}` works under
both harnesses (and in fact `${CLAUDE_PLUGIN_ROOT}` alone would suffice on
CodeBuddy 2.97.1; the fallback is kept for forward compatibility).

### Hook events confirmed firing

| Event | Confirmed | Notes |
|-------|-----------|-------|
| `SessionStart` | ✓ | `source: "startup"`; payload has no `cwd` (use env) |
| `UserPromptSubmit` | ✓ | Includes `prompt`, `cwd`, `transcript_path` |
| `PreToolUse` | ✓ | Matcher `Edit\|Write\|MultiEdit` works |
| `PostToolUse` | ✓ | Includes `tool_response` |
| `Stop` | ✓ | Includes `stop_hook_active`, `last_assistant_message` |
| `SessionEnd` | not observed in `--print` | Likely interactive-only; not load-bearing |

### stdin payload (verified samples)

All payloads carry: `session_id`, `transcript_path`, `hook_event_name`,
`permission_mode`, `client`, `version`, `model`. Per-event extras:

```json
// SessionStart
{"source": "startup"}

// UserPromptSubmit
{"cwd": "...", "prompt": "..."}

// PreToolUse / PostToolUse
{"cwd": "...", "tool_name": "Write", "tool_input": {...},
 "tool_response": "...", "call_id": "...", "tool_use_id": "..."}

// Stop
{"cwd": "...", "stop_hook_active": false,
 "last_assistant_message": "...", "generation_id": "..."}
```

These are the exact key names `scripts/spec_guard.py` already reads.

### Output protocol

Same as Claude Code:
- exit code 0 + JSON on stdout for `additionalContext` injection
- exit code 2 + message on stderr to deny a tool call
- (Deny semantics inferred from agent identity, not exhaustively stress-tested.)

## Install

End-user install on either harness:

```sh
# Claude Code
claude --plugin-dir /path/to/spec-mode

# CodeBuddy
codebuddy --plugin-dir /path/to/spec-mode
```

Both auto-discover the manifest, register hooks, and expose `/spec-mode:*`
slash commands.

## Re-verifying

If a future CodeBuddy release breaks something, swap `hooks/hooks.json`
with `hooks/hooks-probe.json`, re-run, and inspect `~/.spec-mode/probe/`.
Procedure documented in [`VERIFY.md`](./VERIFY.md).

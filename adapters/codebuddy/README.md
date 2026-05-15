# CodeBuddy Adapter

This plugin targets both Claude Code and CodeBuddy under the assumption that
CodeBuddy's plugin / hook model is API-compatible with Claude Code's.

## What is already in place

`hooks/hooks.json` uses `${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}` so the
hook command resolves correctly under either harness:

- Claude Code sets `CLAUDE_PLUGIN_ROOT` → primary path.
- CodeBuddy is assumed to set `CODEBUDDY_PLUGIN_ROOT` → fallback path.

If CodeBuddy uses a different environment variable name, replace the fallback
chain in `hooks/hooks.json` accordingly.

## What needs CodeBuddy real-run verification

1. **Hook event names**. We use Claude Code's names (`SessionStart`,
   `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SessionEnd`).
   Confirm CodeBuddy emits the same names; if not, write a translation table
   here and add a parallel `hooks-codebuddy.json` to swap in.
2. **stdin/stdout protocol**. We rely on:
   - hook input as JSON on stdin
   - `payload.session_id`, `payload.cwd`, `payload.tool_name`,
     `payload.tool_input.file_path` keys
   - hook output for UserPromptSubmit:
     `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
       "additionalContext": "..."}}` on stdout
   - exit code 2 + stderr to deny
3. **Plugin discovery**. We assume CodeBuddy auto-discovers `plugin.json`,
   `skills/`, `commands/`, `hooks/hooks.json` at the plugin root.

## Open items

- Confirm whether CodeBuddy honors `${VAR:-fallback}` shell parameter expansion
  inside the `command` string. If not, switch to a wrapper script:

  ```sh
  # scripts/spec_guard.sh
  #!/bin/sh
  ROOT="${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}"
  exec python3 "$ROOT/scripts/spec_guard.py" "$@"
  ```

- Confirm `commands/*.md` are loaded as slash commands under a `/spec-mode:`
  namespace, identical to Claude Code's behavior.
- Confirm `${VAR}` env expansion inside `hooks.json` command string is
  identical to Claude Code's pre-execution rules.

When live verification is done, edit this README to record the actual behavior
and remove the "needs verification" section.

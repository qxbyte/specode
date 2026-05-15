# CodeBuddy Re-Verification Procedure

Initial verification was completed against CodeBuddy 2.97.1; results are
recorded in `README.md` of this directory. Run this procedure if a future
CodeBuddy release breaks the plugin / hook contract and you need to
re-collect the actual env vars, stdin payload structure, and event names.

The probe in `hooks/hooks-probe.json` is **pure shell**: it does not depend
on `CLAUDE_PLUGIN_ROOT` or `CODEBUDDY_PLUGIN_ROOT` resolving correctly.
Even if CodeBuddy renames its env-var, we still get data.

## What the probe answers

| # | Question | How |
|---|----------|-----|
| 1 | Does CodeBuddy auto-discover `.claude-plugin/plugin.json` + `hooks/hooks.json`? | `~/.spec-mode/probe/*.log` is created |
| 2 | Which hook events are emitted? | One log file per event |
| 3 | What env var holds the plugin root? | `---ENV---` section, look for `*PLUGIN_ROOT*` |
| 4 | What is the stdin payload structure? | `---STDIN---` section per event |
| 5 | Are `commands/*.md` loaded as `/spec-mode:*`? | Try `/spec-mode:status` after the run |

## Quick procedure (non-interactive, fully automatable)

```sh
cd /path/to/spec-mode

# 1. Stage the probe (back up real hooks first)
cp hooks/hooks.json hooks/hooks.json.bak
cp hooks/hooks-probe.json hooks/hooks.json
rm -rf ~/.spec-mode/probe

# 2. Validate manifest is still recognized
codebuddy plugin validate .

# 3. Trigger SessionStart + UserPromptSubmit + Stop
cd /tmp
codebuddy --plugin-dir /path/to/spec-mode -p "say hi" --max-turns 1 -y

# 4. Trigger PreToolUse + PostToolUse with a Write
codebuddy --plugin-dir /path/to/spec-mode \
  -p "Write a file at /tmp/probe-test.txt with content 'ok'. Just do it." \
  --max-turns 3 -y --allowedTools "Write"

# 5. Inspect captured data
ls -la ~/.spec-mode/probe/
for f in ~/.spec-mode/probe/*.log; do
  echo "=== $f ==="
  grep -A 2 'STDIN' "$f" | head -3
done

# 6. Restore real hooks
cd /path/to/spec-mode
mv hooks/hooks.json.bak hooks/hooks.json
rm -f /tmp/probe-test.txt
```

## What to compare against

The verified baseline (CodeBuddy 2.97.1) is in `README.md` of this
directory. After running the probe, diff your captured payloads against
that baseline. Material drift requires updating either:

- `hooks/hooks.json` — env-var fallback chain
- `scripts/spec_guard.py` — payload key handling
- `adapters/codebuddy/README.md` — verified-contract section

## Reading individual logs

Each `~/.spec-mode/probe/<event>.log` has three sections per invocation:

```
=== EVENT=<name> TIME=<iso> CWD=<path> PID=<pid> ===
---ENV---
KEY=value
...
---STDIN---
{...JSON payload...}
---END---
```

The `---STDIN---` JSON is what `spec_guard.py` would have received. The
`---ENV---` section reveals the harness's env-var conventions.

## End-to-end smoke test (real hooks)

After restoring `hooks/hooks.json`, run a benign session and confirm
`spec_guard.py` itself executes cleanly under CodeBuddy:

```sh
rm -rf ~/.spec-mode/audit
cd /tmp && codebuddy --plugin-dir /path/to/spec-mode -p "say ok" --max-turns 1 -y
cat ~/.spec-mode/audit/*.log
# Expect a SessionStart entry with decision=ok and any_active=False
```

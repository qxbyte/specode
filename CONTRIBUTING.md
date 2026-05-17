# Contributing

## Runtime is stdlib-only

The runtime code under `plugins/specode/scripts/` MUST use only the
Python standard library. This is a hard rule, declared in `plugin.json`:

```json
"requires": { "python": ">=3.9", "stdlib_only": true }
```

Reason: plugin users install the plugin via `--plugin-dir`. They don't run a
`pip install -r requirements.txt`. Pulling in third-party packages would
either silently break for users without those packages, or require a heavier
install path that fights the purpose of the plugin.

Tests under `tests/` MAY use `pytest` (it's a dev dependency, not runtime).

## Test conventions

Run the suite from the repo root:

```sh
python3 -m pytest plugins/specode/tests/ -v
```

When adding behavior to `spec_sync.py` or `spec_guard.py`, add:

1. A unit test under `plugins/specode/tests/test_spec_sync.py` for the
   pure function.
2. An integration test under `plugins/specode/tests/test_spec_guard.py`
   exercising the handler path with a fabricated stdin payload through
   `hook_caller`.

Use the `workspace` fixture for handler tests — it creates a tmp spec_dir
+ project_root and monkey-patches `spec_state.find_active_spec` so you don't
need a real Obsidian vault.

## Hook safety contract

Every handler in `spec_guard.py` MUST:

1. Catch all exceptions internally and return 0 from `main()` (the dispatcher
   already wraps handler calls in try/except). Never wedge a user's Claude
   Code session because of a plugin bug.
2. Honor `SPECODE_GUARD=off` for global bypass.
3. Audit log via `_audit()` for any decision that *did work* — silent fast-
   exits when no active spec are deliberately *not* audited (avoid log spam).
4. Use `deny(msg)` (exit 2 + stderr) ONLY for genuine invariant violations
   that the model should react to.

## Performance budget

| Hook | Budget |
|---|---|
| `SessionStart` / `SessionEnd` | <500 ms |
| `UserPromptSubmit` | <80 ms (fires every user turn — keep it cheap) |
| `PreToolUse` / `PostToolUse` | <100 ms |
| `Stop` | <300 ms (allowed slightly larger; runs once per turn) |

If your change crosses these budgets, profile first; don't accept the
regression.

## Sentinel discipline

`~/.specode/.any-active` is the shell-short-circuit sentinel. Maintain
its truth via `spec_state.sync_any_active_sentinel()` — never write it
ad-hoc. If you add a code path that activates or deactivates a spec, call
sync after.

## Release

Public release procedure for plugin maintainers. Not for contributors who
are only sending PRs — wait for a maintainer to cut the release that
includes your change.

### Version manifests (must agree)

Two manifests both carry `version`. They MUST match or `claude plugin tag`
refuses to operate:

- `plugins/specode/.claude-plugin/plugin.json` → `"version": "X.Y.Z"`
- `.claude-plugin/marketplace.json` → `plugins[0].version: "X.Y.Z"`

### Picking the next version (semver)

For this plugin, "API" = the slash command set, hook contract, agent names,
and persisted-state schema (anything users see or that their stored data
depends on).

| Bump | When | Examples |
| --- | --- | --- |
| **major** (1.0.0 → 2.0.0) | A user feels a breaking change after `claude plugin update` | rename a slash command; rename `~/.specode/sessions/` schema; rename a subagent's `name` field; remove a hook event |
| **minor** (0.1.0 → 0.2.0) | Backwards-compatible new capability | new slash command; new subagent; new optional `@swarm:*` label; new selector option |
| **patch** (0.1.0 → 0.1.1) | Bug fix / docs / internal refactor with no surface change | fix a typo in a prompt; fix a `subagent_type` typo; clarify a reference; CI-only |

When in doubt, bump higher. Users can pin to a version; they cannot rewind
persisted state if a "patch" silently changes a schema.

### Pre-release checklist (do not skip)

```sh
# 1. All tests pass
python3 -m pytest plugins/specode/tests/ -v

# 2. CHANGELOG.md has an `## Unreleased` section with concrete entries
#    (no "TBD" placeholders, no stale "WIP" markers)
grep -A 1 "^## Unreleased" CHANGELOG.md

# 3. main is clean and up to date
git status                              # → nothing to commit
git rev-parse --abbrev-ref HEAD         # → main
git pull --ff-only
```

If any step fails: fix before continuing. Never publish a release whose
tests are red or whose CHANGELOG is empty — installed users have no
other way to discover what changed.

### Cutting a release

```sh
# 1. Bump both manifests to the new version
$EDITOR plugins/specode/.claude-plugin/plugin.json
$EDITOR .claude-plugin/marketplace.json

# 2. Land CHANGELOG.md: rename `## Unreleased` → `## X.Y.Z (YYYY-MM-DD)`,
#    then add a fresh empty `## Unreleased` above it for the next cycle
$EDITOR CHANGELOG.md

# 3. Commit + push (message format: "Bump to X.Y.Z: <one-line summary>")
git commit -am "Bump to 0.2.0: <summary>"
git push

# 4. Dry-run the tag first
claude plugin tag --dry-run plugins/specode

# 5. Create + push the annotated tag
claude plugin tag plugins/specode --push
```

Tag format: `specode--v{version}` (annotated, message `specode {version}`).
Pushed to `origin` by default; override with `--remote`.

The plugin is **not** packaged into a tarball or registry artifact —
Claude Code and CodeBuddy fetch the marketplace manifest directly from
GitHub and resolve plugins by git tag. **Pushing the tag IS the release.**

### Re-tagging the same version

Only safe if no user has installed it yet:

```sh
git tag -d specode--vX.Y.Z
git push --delete origin specode--vX.Y.Z
claude plugin tag plugins/specode --push      # re-create
```

Once a release is in user hands, prefer a new patch version.

### Verifying after release

```sh
claude plugin marketplace update specode
claude plugin install specode@specode         # or `update`
claude plugin list | grep specode             # confirm new version
```

CodeBuddy users follow the same procedure substituting `codebuddy`.

## Decision history

Two non-obvious design calls are encoded in the rules:

- **1A**: freeform mode relaxes INV-1 (file-not-in-tasks check) but does
  NOT exempt INV-2 (turn conservation) or INV-6 (phase gate). Freeform is
  an INV-1 escape hatch, not a full specode bypass.
- **2A**: `implementation-log.md` counts as a doc change for INV-2.
  Cosmetic-doc abuse (one space added to design.md to satisfy INV-2) is
  caught by `spec_lint.py` as a WARNING, not by hook denial.

Change these only via an explicit design-doc decision, not silently.

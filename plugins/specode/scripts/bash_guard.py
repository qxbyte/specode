"""INV-11: Non-interactive Bash guard.

Two responsibilities:

1. **PreToolUse check** — reject Bash commands known to wait on stdin
   under an agent harness (no TTY). The reject message includes a
   ready-to-paste non-interactive rewrite so the model fixes it in one
   retry instead of guessing.

2. **PostToolUse signature scan** — after a Bash run completes, scan
   stdout/stderr for "we asked for input and waited" markers (e.g.
   "Ok to proceed? (y)"). If matched, return an advisory string the
   caller injects as additionalContext so the next-round model knows
   the command died waiting and should change tactic (use --yes,
   re-run with explicit args, or report to the user).

Stays stdlib-only (project rule). Pure functions, no I/O — the calling
hook owns audit/telemetry/output.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# PreToolUse — interactive-command blacklist
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    name: str
    # `match` runs against the trimmed command string.
    match: re.Pattern
    # `bypass` (optional) — if the command also matches this, the rule is satisfied
    # (e.g. `npm create` is fine when `--yes` is present).
    bypass: re.Pattern | None
    # Human-facing message + suggested rewrite.
    reason: str
    rewrite: str


# Ordering matters: more specific rules first so generic patterns don't shadow.
INTERACTIVE_RULES: list[Rule] = [
    Rule(
        name="npm-create",
        match=re.compile(r"(?:^|[;&|\s])npm\s+create(\s|$)"),
        bypass=re.compile(r"(--yes|\s-y(\s|$)|(?:^|\s)yes\s*\|)"),
        reason="`npm create` first installs the scaffolder and prompts 'Ok to proceed? (y)' — pure TTY interaction, will hang under any agent Bash tool.",
        rewrite="add `-- --yes` after the scaffolder name, e.g. `npm create vite@latest myapp -- --yes --template react-ts`",
    ),
    Rule(
        name="npm-init",
        match=re.compile(r"(?:^|[;&|\s])npm\s+init(\s|$)"),
        bypass=re.compile(r"(\s-y(\s|$)|--yes)"),
        reason="`npm init` walks an interactive Q&A unless `-y` is present.",
        rewrite="add `-y` to accept all defaults, e.g. `npm init -y`",
    ),
    Rule(
        name="yarn-create",
        match=re.compile(r"(?:^|[;&|\s])yarn\s+create(\s|$)"),
        bypass=re.compile(r"--yes"),
        reason="`yarn create` may install a scaffolder that prompts for confirmation.",
        rewrite="append `--yes` to skip prompts",
    ),
    Rule(
        name="pnpm-create",
        match=re.compile(r"(?:^|[;&|\s])pnpm\s+create(\s|$)"),
        bypass=re.compile(r"--yes"),
        reason="`pnpm create` may install a scaffolder that prompts for confirmation.",
        rewrite="append `--yes`",
    ),
    Rule(
        name="npx-create",
        # Only `npx <scaffolder>` is interactive (downloads + asks). Plain
        # `npx --yes` or `npx -y` is already safe.
        match=re.compile(r"(?:^|[;&|\s])npx(\s|$)"),
        bypass=re.compile(r"(--yes|\s-y(\s|$)|^yes\s*\|\s*npx\s)"),
        reason="`npx` prompts 'Ok to proceed? (y)' when it has to download the package.",
        rewrite="prefix with `--yes`, e.g. `npx --yes create-foo`",
    ),
    Rule(
        name="git-rebase-interactive",
        match=re.compile(r"(?:^|[;&|\s])git\s+rebase\s+(-i|--interactive)(\s|$)"),
        bypass=None,
        reason="`git rebase -i` opens $EDITOR — there's no way to drive it from an agent Bash.",
        rewrite="use non-interactive rebase or scripted commit surgery (`git commit --amend --no-edit`, `git reset --soft`, etc.)",
    ),
    Rule(
        name="git-add-interactive",
        match=re.compile(r"(?:^|[;&|\s])git\s+add\s+(-p|-i|--patch|--interactive)(\s|$)"),
        bypass=None,
        reason="`git add -p / -i` is interactive.",
        rewrite="use explicit paths: `git add path/to/file`",
    ),
    Rule(
        name="git-commit-needs-message",
        # Matches `git commit` (top-level), denies unless -m / -F / -C / --amend --no-edit / --no-edit is present.
        match=re.compile(r"(?:^|[;&|\s])git\s+commit(\s|$)"),
        bypass=re.compile(r"(\s-m(\s|$)|\s-F(\s|$)|\s-C(\s|$)|--amend\s+--no-edit|--no-edit|\s--message[\s=]|\s--file[\s=])"),
        reason="`git commit` without `-m` / `-F` / `--no-edit` opens $EDITOR and hangs.",
        rewrite="pass the message inline: `git commit -m \"your message\"` (use a HEREDOC for multi-line)",
    ),
    Rule(
        name="tty-editor",
        match=re.compile(r"(?:^|[;&|\s])(vim|vi|nano|emacs|less|more|man|top|htop|btop|nvim)(\s|$)"),
        bypass=None,
        reason="full-screen TUI; will never return.",
        rewrite="use the Read/Edit tools (for files) or pipe into `head`/`cat` (for viewing)",
    ),
    Rule(
        name="interactive-shell",
        match=re.compile(r"(?:^|[;&|\s])(bash|sh|zsh|fish|python|python3|node|ipython|psql|mysql|mongo|redis-cli)\s+(-i\b|--interactive\b)"),
        bypass=None,
        reason="explicit `-i` requests an interactive shell that waits for stdin.",
        rewrite="drop `-i` and pass the command directly: `python3 -c '<code>'`, `psql -c '<sql>'`, etc.",
    ),
    Rule(
        name="repl-bare",
        # Bare REPL invocations (python alone, node alone) — also hang.
        match=re.compile(r"(?:^|[;&|])\s*(python|python3|node|ipython|psql|mysql|redis-cli)\s*(?:[;&|]|\s*$)"),
        bypass=None,
        reason="bare REPL invocation will block on stdin.",
        rewrite="pass `-c '<code>'` (python/node) or `-c '<sql>'` (psql/mysql)",
    ),
    Rule(
        name="ssh-no-batch",
        match=re.compile(r"(?:^|[;&|\s])ssh(\s|$)"),
        bypass=re.compile(r"(BatchMode=yes|-o\s+BatchMode=yes|-i\s)"),
        reason="`ssh` may prompt for password / host-key confirmation.",
        rewrite="add `-o BatchMode=yes` (fails fast on auth prompt) or use key-based auth with `-i <keyfile>`",
    ),
    Rule(
        name="gh-pr-create-no-args",
        match=re.compile(r"(?:^|[;&|\s])gh\s+pr\s+create(\s|$)"),
        bypass=re.compile(r"(--title[\s=]|--body[\s=]|--body-file[\s=]|--fill)"),
        reason="`gh pr create` without `--title` / `--body` / `--fill` opens an editor.",
        rewrite="pass `--title \"...\" --body \"...\"` (use HEREDOC for body)",
    ),
    Rule(
        name="apt-no-yes",
        match=re.compile(r"(?:^|[;&|\s])(sudo\s+)?(apt|apt-get|aptitude)\s+(install|upgrade|remove|purge|dist-upgrade)(\s|$)"),
        bypass=re.compile(r"(\s-y(\s|$)|--yes|--assume-yes|DEBIAN_FRONTEND=noninteractive)"),
        reason="apt prompts 'Do you want to continue? [Y/n]'.",
        rewrite="add `-y` (e.g. `apt-get install -y nginx`); for postinstall prompts also prefix `DEBIAN_FRONTEND=noninteractive`",
    ),
]


@dataclass(frozen=True)
class BashCheckResult:
    decision: str  # "ok" | "deny"
    rule: str | None
    message: str  # empty when ok


def check_bash_command(command: str) -> BashCheckResult:
    """Inspect a Bash command string. Returns BashCheckResult.

    Empty / whitespace-only commands pass. Multi-line commands are checked
    as one flat string (rules use word boundaries / shell separators).
    """
    if not command or not command.strip():
        return BashCheckResult("ok", None, "")
    # Normalize: collapse whitespace; the regexes are tolerant of either.
    flat = " " + re.sub(r"\s+", " ", command.strip()) + " "
    for rule in INTERACTIVE_RULES:
        if not rule.match.search(flat):
            continue
        if rule.bypass and rule.bypass.search(flat):
            continue
        msg = _format_deny(rule, command)
        return BashCheckResult("deny", rule.name, msg)
    return BashCheckResult("ok", None, "")


def _format_deny(rule: Rule, original: str) -> str:
    return (
        f"INV-11 (non-interactive Bash) — rule [{rule.name}] denied\n"
        f"  reason: {rule.reason}\n"
        f"  fix:    {rule.rewrite}\n"
        f"  retry the command in non-interactive form, or report to the user if it genuinely needs human input."
    )


# ---------------------------------------------------------------------------
# PostToolUse — hang-signature scan on captured stdout/stderr
# ---------------------------------------------------------------------------

# Substrings (case-insensitive) seen in real-world hang reports. We scan the
# tail of stdout+stderr only; full scans are unnecessary and expensive.
HANG_SIGNATURES: list[str] = [
    "ok to proceed?",
    "press [enter]",
    "press enter to continue",
    "continue? [y/n]",
    "continue? (y/n)",
    "[y/n]",
    "[y/n/?]",
    "[y/n/all]",
    "(y/n)",
    "(y/n/a)",
    "[y/n]?",
    "are you sure",
    "please confirm",
    "type 'yes'",
    "type \"yes\"",
    "username for",
    "password:",
    "passphrase:",
    "确认吗",
    "是否继续",
    "请输入",
    "请确认",
]

# Tail size: chars from end of combined stdout+stderr to scan. 4 KiB covers
# typical prompt blocks without scanning megabyte-sized npm install logs.
TAIL_SCAN_BYTES = 4096


def detect_hang(stdout: str, stderr: str = "", exit_code: int | None = None) -> tuple[bool, str]:
    """Return (is_hang, reason). exit_code=124 = killed by GNU timeout.

    Even without exit_code=124, a tail with a known prompt signature is a
    strong indicator the process either is still waiting or was killed
    mid-prompt.
    """
    if exit_code == 124:
        return True, "process killed by `timeout` (exit 124) — likely waiting on stdin"
    tail = ((stdout or "") + "\n" + (stderr or ""))[-TAIL_SCAN_BYTES:].lower()
    for sig in HANG_SIGNATURES:
        if sig in tail:
            return True, f"detected interactive prompt: {sig!r}"
    return False, ""


def format_hang_advisory(reason: str, command_excerpt: str | None = None) -> str:
    """Format an additionalContext block for injection on hang detection."""
    lines = [
        "⚠ INV-11 ADVISORY: previous Bash run appears to have hung on stdin.",
        f"   {reason}",
    ]
    if command_excerpt:
        excerpt = command_excerpt.strip().splitlines()[0][:200]
        lines.append(f"   command: {excerpt}")
    lines.append(
        "   action: do NOT retry the same command. Either rewrite to a non-interactive form "
        "(--yes / -y / explicit args), or report to the user with the command for them to run manually."
    )
    return "\n".join(lines)

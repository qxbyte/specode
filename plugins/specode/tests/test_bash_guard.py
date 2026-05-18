"""Tests for INV-11 Bash hang guard (bash_guard.py).

Each blacklist rule has at least one positive (must deny) and one negative
(must pass) sample. Hang-signature scan has positive/negative samples too.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import bash_guard


def _deny(cmd: str, rule: str | None = None) -> None:
    res = bash_guard.check_bash_command(cmd)
    assert res.decision == "deny", f"expected deny for {cmd!r}, got {res}"
    if rule:
        assert res.rule == rule, f"expected rule {rule}, got {res.rule}"


def _ok(cmd: str) -> None:
    res = bash_guard.check_bash_command(cmd)
    assert res.decision == "ok", f"expected ok for {cmd!r}, got deny: {res.message}"


# ---- npm / yarn / pnpm scaffolders -----------------------------------------

def test_npm_create_without_yes_denied():
    _deny("npm create vite@latest myapp -- --template react-ts", rule="npm-create")


def test_npm_create_with_yes_passes():
    _ok("npm create vite@latest myapp -- --yes --template react-ts")


def test_npm_create_with_yes_pipe_passes():
    _ok("yes | npm create vite@latest myapp")


def test_npm_init_without_y_denied():
    _deny("npm init", rule="npm-init")


def test_npm_init_with_y_passes():
    _ok("npm init -y")


def test_npm_init_with_yes_passes():
    _ok("npm init --yes")


def test_yarn_create_denied():
    _deny("yarn create vite myapp", rule="yarn-create")


def test_yarn_create_with_yes_passes():
    _ok("yarn create vite myapp --yes")


def test_pnpm_create_denied():
    _deny("pnpm create vite myapp", rule="pnpm-create")


def test_npx_without_yes_denied():
    _deny("npx create-foo", rule="npx-create")


def test_npx_with_yes_passes():
    _ok("npx --yes create-foo")


def test_npx_with_short_y_passes():
    _ok("npx -y create-foo")


# ---- git interactive -------------------------------------------------------

def test_git_rebase_interactive_denied():
    _deny("git rebase -i HEAD~3", rule="git-rebase-interactive")
    _deny("git rebase --interactive main", rule="git-rebase-interactive")


def test_git_rebase_non_interactive_passes():
    _ok("git rebase main")
    _ok("git rebase --onto main feature")


def test_git_add_patch_denied():
    _deny("git add -p", rule="git-add-interactive")
    _deny("git add -i", rule="git-add-interactive")
    _deny("git add --patch", rule="git-add-interactive")


def test_git_add_explicit_path_passes():
    _ok("git add src/foo.py")
    _ok("git add -A")
    _ok("git add .")


def test_git_commit_no_message_denied():
    _deny("git commit", rule="git-commit-needs-message")


def test_git_commit_with_m_passes():
    _ok('git commit -m "fix bug"')


def test_git_commit_with_message_long_flag_passes():
    _ok('git commit --message="fix bug"')


def test_git_commit_amend_no_edit_passes():
    _ok("git commit --amend --no-edit")


def test_git_commit_with_F_passes():
    _ok("git commit -F /tmp/msg")


# ---- TUI editors / pagers --------------------------------------------------

def test_vim_denied():
    _deny("vim file.txt", rule="tty-editor")
    _deny("nvim file.txt", rule="tty-editor")


def test_nano_denied():
    _deny("nano file.txt", rule="tty-editor")


def test_less_denied():
    _deny("less /var/log/foo.log", rule="tty-editor")


def test_top_denied():
    _deny("top", rule="tty-editor")


def test_cat_passes():
    """`cat` is not in the editor list — it just emits and exits."""
    _ok("cat file.txt")


def test_head_passes():
    _ok("head -n 50 file.txt | grep foo")


# ---- interactive shells ----------------------------------------------------

def test_bash_dash_i_denied():
    _deny("bash -i", rule="interactive-shell")


def test_python_dash_i_denied():
    _deny("python3 -i script.py", rule="interactive-shell")


def test_python_dash_c_passes():
    _ok("python3 -c 'print(1+1)'")


def test_bare_python_denied():
    _deny("python3", rule="repl-bare")


def test_bare_node_denied():
    _deny("node", rule="repl-bare")


def test_python_with_script_passes():
    _ok("python3 script.py --arg value")


# ---- ssh / gh / apt --------------------------------------------------------

def test_ssh_without_batch_denied():
    _deny("ssh user@host", rule="ssh-no-batch")


def test_ssh_with_batch_passes():
    _ok("ssh -o BatchMode=yes user@host uptime")


def test_ssh_with_key_passes():
    _ok("ssh -i ~/.ssh/deploy user@host uptime")


def test_gh_pr_create_no_args_denied():
    _deny("gh pr create", rule="gh-pr-create-no-args")


def test_gh_pr_create_with_title_body_passes():
    _ok('gh pr create --title "x" --body "y"')


def test_gh_pr_create_with_fill_passes():
    _ok("gh pr create --fill")


def test_apt_install_no_y_denied():
    _deny("sudo apt install nginx", rule="apt-no-yes")
    _deny("apt-get install curl", rule="apt-no-yes")


def test_apt_install_with_y_passes():
    _ok("apt-get install -y nginx")


def test_apt_install_with_env_passes():
    _ok("DEBIAN_FRONTEND=noninteractive apt-get install nginx")


# ---- safe commands sanity check --------------------------------------------

def test_safe_commands_all_pass():
    for cmd in [
        "ls -la",
        "pwd",
        "git status",
        "git log --oneline -10",
        "git push origin main",
        "npm install",
        "npm run build",
        "pip install requests",
        "brew install jq",
        "cargo build",
        "go install github.com/foo/bar@latest",
        "docker pull nginx",
        "python3 -m pytest -q",
        "echo hello",
        "find . -name '*.py'",
        "grep -r foo .",
    ]:
        _ok(cmd)


# ---- empty / whitespace ----------------------------------------------------

def test_empty_command_passes():
    _ok("")
    _ok("   ")
    _ok("\n\t")


# ---- chained commands ------------------------------------------------------

def test_chained_denied_command_caught():
    _deny("cd /tmp && npm create vite myapp", rule="npm-create")
    _deny("ls && vim file.txt", rule="tty-editor")


def test_chained_safe_commands_pass():
    _ok("cd /tmp && ls && npm install")


# ---- hang signature detection ---------------------------------------------

def test_detect_hang_by_exit_124():
    is_hang, reason = bash_guard.detect_hang("partial output\n", "", exit_code=124)
    assert is_hang
    assert "124" in reason


def test_detect_hang_by_ok_to_proceed():
    stdout = "Need to install the following packages:\ncreate-vite@9.0.7\nOk to proceed? (y)\n"
    is_hang, _ = bash_guard.detect_hang(stdout)
    assert is_hang


def test_detect_hang_by_y_n_prompt():
    is_hang, _ = bash_guard.detect_hang("Continue? [Y/n]")
    assert is_hang


def test_detect_hang_by_password_prompt():
    is_hang, _ = bash_guard.detect_hang("", "sudo: password: ")
    assert is_hang


def test_detect_hang_chinese_prompts():
    for s in ["确认吗？(y/n)", "是否继续？", "请输入密码:"]:
        is_hang, _ = bash_guard.detect_hang(s)
        assert is_hang, f"expected hang for {s!r}"


def test_no_hang_on_clean_output():
    stdout = "added 142 packages in 30s\nfound 0 vulnerabilities\n"
    is_hang, _ = bash_guard.detect_hang(stdout, exit_code=0)
    assert not is_hang


def test_no_hang_when_only_normal_text():
    is_hang, _ = bash_guard.detect_hang("npm WARN deprecated foo@1.0.0\n")
    assert not is_hang


def test_format_hang_advisory_includes_command():
    out = bash_guard.format_hang_advisory("test reason", command_excerpt="npm create vite myapp")
    assert "INV-11 ADVISORY" in out
    assert "test reason" in out
    assert "npm create vite myapp" in out
    assert "do NOT retry" in out


def test_format_hang_advisory_truncates_long_command():
    long_cmd = "a" * 500
    out = bash_guard.format_hang_advisory("reason", command_excerpt=long_cmd)
    # Excerpt is capped at 200 chars in format
    assert "a" * 200 in out
    assert "a" * 250 not in out

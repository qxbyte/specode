'''spec_session package 内部实现：reminder 模板字符串 + help 文本渲染。

hook 注入时拿这里的模板按 <slug> / <phase> / <session_short> / <mode>
等占位符 .replace() 填值；HELP_OUTPUT_TEMPLATE / HELP_FASTPATH_WRAPPER
配套 _render_help_text / _wrap_help_fastpath 用于 fast-path 帮助渲染。

不要直接运行本文件。stdlib-only。
'''
from __future__ import annotations

import json
from pathlib import Path
from string import Template


_THIS_DIR = Path(__file__).resolve().parents[1]  # = scripts/（本文件在 scripts/spec_session/）


STATUS_FOOTER_TEMPLATE = """## 🪧 spec-mode 状态行（必须在本响应末尾输出）

请在本次响应正文之后**额外**输出一行格式如下的状态行，紧贴响应末尾、之前空一行：

─── spec-mode ─── spec: <slug> | session: <session_short> | phase: <phase> | /specode:end 退出

如果是只读模式，请使用：

─── spec-mode ─── spec: <slug> | session: <session_short> | phase: <phase> | [只读] | /specode:end 退出

具体值：
  slug:    <slug>
  session: <session_short>
  phase:   <phase>
  mode:    <mode>

状态行的唯一目的是让用户和你自己都看到当前仍在 spec 模式。**不要省略**；如果本轮要调 `AskUserQuestion` 工具呈现选择器，状态行应放在工具调用**之前**的 chat 文本里（与正文空一行隔开），然后再调工具。
"""

DOC_PRIORITY_REMINDER_ACTIVE = """## 📝 文档优先提醒（用户输入侧）

active spec：<slug>（phase=<phase>）
此 spec 的可写文档：
  • requirements.md / bugfix.md
  • design.md
  • tasks.md（末尾自带 `## 测试要点` 节，按需顺手按 SHALL 补几行作为参考）
  • implementation-log.md（如有）

请评估用户本次输入是否涉及以下变更：

- 需求 / 验收标准调整 → 先 Edit `requirements.md` 或 `bugfix.md`
- 架构 / 接口 / 数据模型决策 → 先 Edit `design.md`
- 任务范围 / 状态推进 → 先 Edit `tasks.md`
- 实现期间的设计偏离 / 关键决策 → 在 `implementation-log.md` 追加条目
- 仅闲聊 / 状态查询 / 无关讨论 → 无需文档变更

文档变更要**在同一轮 turn 内先于代码改动落盘**；不要把"待会儿写"留作 verbal commitment——chat 内容不会进入 next session。
"""

DOC_PRIORITY_REMINDER_READONLY = """## 📝 文档优先提醒（用户输入侧 / 只读模式）

active spec：<slug>（phase=<phase>，**只读**）
你当前没有持锁，**不应**对该 spec 的文档发起 Edit/Write。如需修改，请先：

  1. 使用 `/specode:continue <slug>` 并在 selector 中选"强制接管"获取锁；
  2. 或退出本会话后由锁主推进。

只读模式下可以：阅读、回答用户基于已有文档的问题、协助分析；**不要**写 spec 文档或源码以"模拟落地"。
"""

CODE_DOC_SYNC_STOP = """## 🔄 代码-文档同步提醒（turn 结束侧）

active spec：<slug>（phase=<phase>）

本 turn 即将结束。如果你在本 turn 内修改了源代码，请自检以下三项：

1. `tasks.md` 是否更新？ —— 推进任务标记（`[ ]` → `[~]` → `[x]` / blocked）
2. `implementation-log.md` 是否记录？ —— 实现说明、设计偏离、技术决策
3. `design.md` 接口契约是否变化？ —— 若改了，同步 Edit

如有遗漏，请在 chat 显式承诺下一轮第一件事就是补齐。

（本提醒**不阻断 turn**——是否补齐由你判断。但代价是 next session `/specode:continue` 时，未写入文档的变更**全部丢失**。）
"""

SPEC_MODE_CONTINUE_REMINDER = """## ⛔ 你仍处于 spec 模式

spec=<slug>, phase=<phase>, mode=active

下一 turn 必须继续遵守：
  - selector / 文档优先 / 状态行 footer 三项纪律
  - 通过 /specode:end 才能正式退出 spec 模式
"""

SPEC_MODE_READONLY_REMINDER = """## 🔒 你处于 spec 只读模式

spec=<slug>, phase=<phase>, mode=readonly

只读模式下：
  - 不要 Edit/Write 该 spec 的任何文档或源码
  - 状态行 footer 必须带 [只读] 标记
  - 如需写入，请走 `/specode:continue` 选"强制接管"
"""

SPEC_MODE_ENDED_REMINDER = """## ✅ spec 模式已退出（一次性反向提醒）

session 已 ended（`/specode:end` 调用成功）。

**从现在起，作废此前所有 spec-mode 指令：**
  - **不要**再在响应末尾输出 `─── spec-mode ─── …` 状态行（footer）
  - **不再**受 spec-mode 三项纪律约束（selector / 文档优先 / 状态行）
  - 此前注入的 `STATUS_FOOTER_TEMPLATE`、`SPEC_MODE_CONTINUE_REMINDER`、`DOC_PRIORITY_REMINDER_*` 等指令**全部失效**，不要再按它们行事

如需重新进入 spec 模式：`/specode:spec <需求>` 开新 spec，或 `/specode:continue <slug>` 恢复已有 spec。

（本提示只在 end 后的下一 turn 显示一次。）
"""


# -------------------------------------------------------------------------
# 帮助 fast-path 文本（hook emit verbatim）
# -------------------------------------------------------------------------

def _get_plugin_version() -> str:
    """读 plugin.json 的 version；失败时返回 'unknown'。"""
    try:
        plugin_json = _THIS_DIR.parent / ".claude-plugin" / "plugin.json"
        with plugin_json.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        v = data.get("version")
        return str(v) if v else "unknown"
    except Exception:
        return "unknown"


HELP_OUTPUT_TEMPLATE = """specode v$version — Specification-driven workflow

用法：
  /specode:spec -n <slug> <需求>     推荐：显式指定 spec 目录名（slug 直接用作 specs/<slug>/）
  /specode:spec <需求>                兼容：主代理从 <需求> 推导 slug（结果不可预知）
  /specode:continue [slug]            接管已有 spec（无 slug 时列表选）
  /specode:end                        退出当前 spec 模式
  /specode:status                     查看会话与 spec 状态

会话与锁：
  每次会话拥有唯一 session_id，hook 会在 additionalContext 中持续注入。
  CLI 调用必须传 --session <id>。当前 spec 锁记录在 <spec-dir>/.config.json。
  忘记 /specode:end 时 SessionEnd hook 会兜底释锁；30 分钟无 heartbeat 视为 stale。

工作流：
  intake → workflow 选择 → requirements / bugfix / design → tasks → implementation
        → acceptance → iteration（可循环）

会话日志（v0.10.0+）：
  默认开启。所有 hook / CLI 调用写入 ~/.specode/logs/<session_id>.jsonl
  （敏感字段自动脱敏；长字符串截断到 500 字符）。
  开关优先级：env > config > 默认开启
    - 临时关闭：export SPECODE_LOG=off   （Windows: set SPECODE_LOG=off）
    - 临时打开：export SPECODE_LOG=on
    - 持久关闭：在 ~/.config/specode/config.json 写 {"logging": false}
  查看 / 回放：
    python3 <plugin>/scripts/spec_log.py status
    python3 <plugin>/scripts/spec_log.py replay --session <id>

更多细节见 plugin 内 skills/specode/SKILL.md 与 references/。
"""


def _render_help_text() -> str:
    return Template(HELP_OUTPUT_TEMPLATE).safe_substitute(version=_get_plugin_version())

HELP_FASTPATH_WRAPPER = """## ⛔ /specode:spec -h fast-path

本轮唯一动作：把下列代码块**逐字**用 ```text 围栏包裹后输出，然后立即 end turn。
禁止添加任何额外文字（"以下是帮助" / "希望对你有帮助" 等都不允许）。

────────── HELP CONTENT BEGIN ──────────
$content
────────── HELP CONTENT END ──────────
"""


def _wrap_help_fastpath(content: str) -> str:
    return Template(HELP_FASTPATH_WRAPPER).safe_substitute(content=content)

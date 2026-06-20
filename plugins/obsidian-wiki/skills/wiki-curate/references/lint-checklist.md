# Lint 内容健康检查清单

`/wiki-curate lint` 的检查清单。聚焦**内容健康**（确定性脚本 + LLM 判断）；坏链与结构漂移见 `/wiki-struct check`。

输出到 `00-Index/_system/lint-report.md`，按产出方式分两类：**脚本确定性输出**（`scripts/lint.py`）和 **LLM 判断**。

> 坏链与结构漂移（断链、孤儿索引、分区页完整性）见 `/wiki-struct check`，不在本 skill 范围内。

---

## 脚本确定性检查（`scripts/lint.py`）

以下四项由 `lint.py` 纯函数逻辑产出，结果可重现、可单测，不依赖 LLM。

### L1 — 缺"用途"段

**定义**：`LINT_DIRS`（`01-Concepts/`、`02-Models/`、`04-Tools/`、`05-Workflows/`、`06-Prompts/`、`08-Sources/`）下的笔记没有 `## 用途` 二级标题。

**例外**：
- `README.md`（目录说明页本身即其用途，不强制）。

**修复建议**：列出每个缺少的笔记，让用户在 curate 阶段补写或本 skill 起草草稿（状态标 `草稿`）。

### L2 — 重复 basename

**定义**：全库（排除 `.obsidian`、`.claude`、`.claudian`、`.git`、`skills` 等 `SKIP_DIRS`）同 basename 在多目录出现（例如 `01-Concepts/Redis.md` 和 `04-Tools/Redis.md`）。

**修复建议**：检查是否真同义。同义 → 合并并保留别名。不同义 → 在标题里加限定（`Redis 概念.md` vs `Redis 工具.md`）。

### L3 — 孤儿（无反链）

**定义**：`LINT_DIRS`（`01-Concepts/`～`08-Sources/`）和 `09-Journal/` 下没有任何反向链接的笔记——既不被任何 `[[...]]` 引用，也不在任何笔记正文中被链到。

**例外**：
- `README.md` 排除（目录入口页不强制被链接）。
- 链接解析跳过 fenced code block（`` ``` `` / `~~~` 内）。

**修复建议**：在相关内容笔记正文补 `[[孤儿]]`（语义双链）；**不是**往索引/分区页加行（索引页由 wiki-struct 管理）。

### L4 — frontmatter 缺字段

**定义**：`LINT_DIRS` 下缺少 `类型` / `状态` / `标签` / `更新` 任一字段的笔记。

**修复建议**：用 `note-templates.md` 对应模板补字段；`更新` 字段用文件 mtime 作为初值。

---

## LLM 判断项

以下两项开销较大，由 LLM 在 `/wiki-curate lint` 时按需执行（可选 `--deep`）。

### L5 — 过时声明

**定义**：含具体版本号、价格、日期（如 "Claude 3.5"、"$15/1M tokens"、"2024 年"），且 frontmatter 的 `更新` 字段早于半年。

**算法**：脚本可初筛 `更新` 日期偏老的笔记，LLM 再判内容是否真的过时。

**修复建议**：列出可疑笔记，让用户判断要不要更新内容或加 `状态: 待复核` 标记。

### L6 — 矛盾对

**定义**：两篇笔记对同一术语给出冲突定义。

**启发式**（开销大，可选启用）：
- 同 H1（或 frontmatter `别名` 重叠）
- 摘要段（前 200 字）有显著语义差异

**修复建议**：列出疑似矛盾对，让用户判断要合并、加交叉引用还是保留分歧并加"对比"段。

---

## 报告格式

`00-Index/_system/lint-report.md` 模板：

```markdown
---
类型: 报告
状态: 自动生成
更新: YYYY-MM-DD HH:MM
扫描范围: 全 vault
---

# wiki-curate 内容体检报告

> `/wiki-curate lint` 生成；只读。**坏链与结构漂移请运行 `/wiki-struct check`**。

## 概览

- 缺"用途"段：<n>
- 重复 basename：<n>
- 孤儿（无反链）：<n>
- frontmatter 缺字段：<n>

## 缺"用途"段

- `<文件路径>`

...

## 重复 basename

- `Redis.md`：`01-Concepts/Redis.md`、`04-Tools/Redis.md`

...

## 孤儿（无反链）

- `<文件路径>`

...

## frontmatter 缺字段

- `<文件路径>`：缺 状态、更新

...
```

---

## 与 Scan 报告的区别

- **Scan**（`curate-report.md`）：侧重"新内容、待整理"，看向未来。
- **Lint**（`lint-report.md`）：侧重"现有内容、健康问题"，看向当下质量。

两个报告独立生成，可以分别运行。

## 性能与边界

- 脚本确定性检查（L1-L4）应秒级完成（当前库规模下约 5 秒）。
- 不要对每个笔记跑 LLM——纯字符串/正则启发式优先，仅 L5/L6 需 LLM。
- L6 矛盾对检测开销大，作为可选项 `/wiki-curate lint --deep`。

## 何时跳过

- 用户上一次完整 lint 是 24 小时内 → 默认跳过 L6（矛盾对），其它照跑。
- 用户明说"快速看一眼" → 只跑 L1-L4（脚本项）。
- 用户明说"深度体检" → 全跑，含 L6。

# 目录配置参考（dir-config）

`struct_gen.py` 的遍历与渲染行为由 `<vault>/.wiki/config.json` 中的 `structure.dirs` 驱动（schema 见本插件根 `config.example.json`）。本文档提供人类可读的配置表、渲染规则说明，以及新增/改名一级目录的操作步骤。

> **单一真相来源**：`config.json` 中的 `structure.dirs` 是权威。本文档中的目录表是示例配置的镜像（对应 `config.example.json`）；两者如有出入，以实际 `config.json` 为准。

---

## 1. 16 目录配置表

> 以下表格对应 `config.example.json` 中的默认示例配置，实际 vault 可通过 `config.json` 定制。

| dir | emoji | 说明 | callout 类型 | 分区页路径 | 有 README | 有分区页 | 敏感 |
|---|---|---|---|---|---|---|---|
| `00-Index` | 🗂️ | 索引与导航中枢（分区索引 + 系统报告） | `abstract` | — | — | — | |
| `01-Concepts` | 📘 | 概念与原理：Java、Spring、中间件、架构、设计模式 | `note` | `00-Index/01-Concepts` | ✓ | ✓ | |
| `02-Models` | 🤖 | AI/ML 模型 | `note` | `00-Index/02-Models` | ✓ | ✓ | |
| `03-Memo` | 🔐 | 运维备忘（敏感：服务器/激活码/账号/密钥） | `warning` | `00-Index/03-Memo` | ✓ | ✓ | ✓ 整目录 |
| `04-Tools` | 🛠️ | AI 工具、CLI、应用 | `note` | `00-Index/04-Tools` | ✓ | ✓ | |
| `05-Workflows` | ⚙️ | 工作流程、操作手册、工程模板 | `note` | `00-Index/05-Workflows` | ✓ | ✓ | |
| `06-Prompts` | ✍️ | 提示词模板与工程工作流 | `note` | `00-Index/06-Prompts` | ✓ | ✓ | |
| `07-Ideas` | 💡 | 项目想法、产品需求、技术探索 | `note` | `00-Index/07-Ideas` | ✓ | ✓ | |
| `08-Sources` | 📚 | 外部资料来源 | `note` | `00-Index/08-Sources` | ✓ | ✓ | |
| `09-Journal` | 🗓️ | 每日日记与观察 | `note` | `00-Index/09-Journal` | ✓ | ✓ | |
| `10-Work` | 💼 | 工作资料、需求、系统、运维 | `note` | `00-Index/10-Work` | ✓ | ✓ | ✓ 子目录：权限申请·系统 |
| `99-Inbox` | 📥 | 收件箱（待整理） | `note` | `00-Index/99-Inbox` | ✓ | ✓ | ✓ 子目录：账号·激活 |
| `Clippings` | ✂️ | Web Clipper 剪藏暂存 | `note` | `00-Index/Clippings` | ✓ | ✓ | |
| `Database` | 🗃️ | Obsidian Bases 数据库视图 | `note` | `00-Index/Database` | ✓ | ✓ | |
| `SpecIn` | 📐 | Specode 需求规格输入（按 host/需求号归类） | `note` | `00-Index/SpecIn` | ✓ | ✓ | |
| `_scaffold` | 🧩 | 笔记模板与脚手架资源 | `note` | `00-Index/_scaffold` | ✓ | ✓ | |

**字段说明：**

- `callout 类型`：用于 `Home.md` 受管块中该目录的 `> [!type]-` callout。`00-Index` 用 `abstract`，`03-Memo` 用 `warning`（敏感标记），其余均为 `note`。
- `有 README`：该一级目录下是否存在 `README.md` 受管块（`dirs[].readme = true`）。
- `有分区页`：`00-Index/<目录>.md` 是否作为分区页维护受管块（`dirs[].partition = true`）。
- `敏感`：受管块只含文件名级链接，生成器从不读取笔记正文（天然满足，无需特殊分支）。

---

## 2. 渲染规则

### 2.1 遍历顺序：folders-first

每层先列子目录（加粗，格式 `**<名>/**`），再列 `.md` 文件。目录与文件各自在层内按 `sorted()` 字典序排列。

### 2.2 缩进

每深一层缩进 **4 个空格**。顶层（`depth=0`）无缩进。

```
- **子目录/**
    - [[路径/文件|文件名]]
    - **孙目录/**
        - [[路径/孙目录/笔记|笔记]]
```

### 2.3 全路径 wikilink

所有文件链接格式为：

```
[[<相对 vault 根的路径，去掉 .md 后缀>|<basename>]]
```

例：`[[01-Concepts/Java/JVM|JVM]]`

**为什么用全路径而非裸链？** 整个 vault 存在大量同名 basename（`design.md`、`requirements.md`、`README.md`、`设计.md`、`MEMORY.md` 等），裸链 `[[JVM]]` 在 Obsidian 中会解析到第一个匹配项，无法保证指向正确文件。全路径 wikilink 唯一确定目标。

### 2.4 跳过目录（`skip_dirs`）

遍历中跳过 `config.json` 的 `skip_dirs` 列表所列的目录名（精确匹配，不区分深度）。默认包含：

```json
[".obsidian", ".claude", ".claudian", ".git", "skills"]
```

vault 内任何 `skills/` 目录都跳过（由配置 `skip_dirs` 决定），无论它位于哪个一级目录下。

此外：

- **空目录**（递归扫描无任何 `.md` 文件）跳过，不输出目录行。
- **`Home.md` 自身**：在生成 Home 受管块时，`00-Index/Home.md` 通过 `skip_self_rel` 参数从树中排除，避免自引用。

---

## 3. 新增/改名一级目录的步骤

当需要添加新一级目录（如 `11-Archive`）或对现有目录改名时，按以下步骤操作：

### 步骤 1：修改 `config.json` 的 `structure.dirs`

在 `structure.dirs` 数组中新增或修改对应的条目（同时更新本表）：

```json
{"dir": "11-Archive", "emoji": "🗄️", "desc": "归档文档",
 "callout": "note", "partition": "00-Index/11-Archive", "readme": true, "partition_page": true}
```

### 步骤 2：建立目录 README 与分区页（如需）

若 `readme: true`，在该目录下新建 `README.md`（包含 frontmatter 与 `## 目录树（自动维护）` 占位骨架）。

若 `partition: true`，在 `00-Index/` 下新建 `<目录>.md` 分区页。

两份文件均**不含受管块 marker**（留空，等待 `init`）。

### 步骤 3：跑 `init` 接入 marker

```bash
# /wiki-struct init
python3 "$WIKI/skills/wiki-struct/scripts/struct_gen.py" check --vault "<vault>"
```

`check` 会将新文件列入"缺 marker"；随后按 `init` 流程（见 `references/managed-blocks.md` §4）逐文件插入 marker 骨架。

### 步骤 4：跑 `apply` 填充

```bash
python3 "$WIKI/skills/wiki-struct/scripts/struct_gen.py" apply --scope all --vault "<vault>"
```

新目录的 README 受管块、分区页受管块、以及 `Home.md` 受管块（新增该目录的 callout）均自动填充。

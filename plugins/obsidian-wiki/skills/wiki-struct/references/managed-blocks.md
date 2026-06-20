# 受管块（Managed Blocks）参考

`wiki-struct` 对结构文件的写入范围由一对 HTML 注释 marker 严格界定。本文档说明 marker 语法、三类受管块的定义与示例、覆盖语义、`init` 迁移规则，以及不配对 marker 的处理。

---

## 1. Marker 语法

```
<!-- wiki-struct:tree start -->
…（自动生成内容）…
<!-- wiki-struct:tree end -->
```

- `block_id` 固定为 `tree`；当前版本每个结构文件**有且仅有一对** start / end。
- HTML 注释在 Obsidian **阅读视图不渲染**，不会出现在预览界面。
- marker 单独占一行；`start` 行与第一行内容之间、最后一行内容与 `end` 行之间各保留一个空行（`replace_block` 的写入规范）。

---

## 2. 三类受管块

### 2.1 `00-Index/Home.md`（全库可折叠 callout 树）

受管块内包含 16 个一级目录的可折叠 callout，每目录一个 `> [!type]-` 块，内嵌该目录的完整子树。

最小示例（仅示意，实际内容由 `render_home()` 生成）：

```markdown
<!-- wiki-struct:tree start -->
> [!tip] 用法
> 点击下方任一目录标题可展开/折叠；标题右侧 `↗` 链接到该目录的分区索引。

> [!abstract]- 🗂️ 00-Index — 索引与导航中枢（分区索引 + 系统报告）（3 篇）
> - **_system/**
>     - [[00-Index/_system/struct-report|struct-report]]

> [!note]- 📘 01-Concepts — 概念与原理：Java、Spring、中间件、架构、设计模式（12 篇） · 分区索引 [[00-Index/01-Concepts|↗]]
> - **Java/**
>     - [[01-Concepts/Java/JVM|JVM]]
> - [[01-Concepts/设计模式|设计模式]]
<!-- wiki-struct:tree end -->
```

### 2.2 一级目录 `README.md`（本目录文件/子目录清单）

受管块内是该目录的嵌套文件/子目录清单（普通 Markdown 列表，非 callout）。`README.md` 自身通过 `skip_self_rel` 从列表中排除。

最小示例（`01-Concepts/README.md` 的受管块）：

```markdown
## 目录树（自动维护）

<!-- wiki-struct:tree start -->
- **Java/**
    - [[01-Concepts/Java/JVM|JVM]]
    - [[01-Concepts/Java/线程模型|线程模型]]
- [[01-Concepts/设计模式|设计模式]]
- [[01-Concepts/分布式事务|分布式事务]]
<!-- wiki-struct:tree end -->
```

### 2.3 `00-Index/<目录>.md` 分区页（本目录文档清单树）

受管块内是该目录的完整文档清单树（与 README 受管块相似，但分区页本身不在排除列表里——分区页位于 `00-Index/`，遍历的是对应内容目录）。

最小示例（`00-Index/07-Ideas.md` 的受管块）：

```markdown
## 目录树（自动维护）

<!-- wiki-struct:tree start -->
- **项目A/**
    - [[07-Ideas/项目A/PRD|PRD]]
    - [[07-Ideas/项目A/设计|设计]]
- [[07-Ideas/零散想法|零散想法]]
<!-- wiki-struct:tree end -->
```

---

## 3. 覆盖语义

- **marker 内**的内容归 `wiki-struct` skill 所有。每次执行 `apply` 时，`replace_block()` 函数会将 start–end 之间的内容**无条件替换**为最新生成结果（`render_home()` / `render_dir_list()`）。
- **marker 外**的内容（frontmatter、标题、用途说明、人工策展的主题分组/项目状态表、关联链接等）**一字不动**。`replace_block()` 只截取 start/end 之间的切片进行替换，首尾字符不越界。
- 因此，若用户在 marker 内手动修改了内容，下次 `apply` 时该修改**将被覆盖**。`check` 会在 apply 前展示将被覆盖的差异（`drift` 列表）。

---

## 4. `init` 迁移规则（首次接入）

现有结构文件尚无 marker 时，需通过 `/wiki-struct init` 逐文件接入。**核心原则：受管块只能"新插入"，绝不包裹或替换任何人工策展的清单。**

### 4.1 `Home.md`（唯一例外：就地包裹）

`Home.md` 的 `## 目录树` 下的 callout 树是上轮**自动生成**的，无人工策展内容。因此可以：

1. 在该 callout 树**第一行之前**插入 `<!-- wiki-struct:tree start -->`
2. 在该 callout 树**最后一行之后**插入 `<!-- wiki-struct:tree end -->`

就地包裹后，块内已有内容保持不变；下次 `apply` 时才被覆盖为最新生成结果。

### 4.2 README / 分区页（新插入受管块小节）

这些文件的现有清单往往是人工策展的（如 `07-Ideas/README.md` 的项目状态表、`01-Concepts` 分区页的 `### 架构设计` 主题分组）。**不碰它们**，而是：

1. 在文件末尾、"关联"段之前（或 `## 用途` 之后）**新插入**如下骨架：

   ```markdown
   ## 目录树（自动维护）

   <!-- wiki-struct:tree start -->
   <!-- wiki-struct:tree end -->
   ```

2. 块内先留空，由 `apply` 填充。

两份内容（人工策展清单 + 自动树）在同一文件中并存，是设计上接受的取舍。

### 4.3 逐文件确认流程

`init` 对每个"缺 marker"的结构文件执行以下步骤：

1. Read 该文件，判定属于"就地包裹（仅 Home）"还是"新插入受管块"。
2. `AskUserQuestion`：「就地包裹现有自动树（仅 Home）/ 在〈位置〉新插入受管块 / 跳过本文件」。
3. 用 `Edit` 插入 marker（对 Home 就地包裹；其余新插入空骨架）。
4. 全部插完后，统一跑一次 `apply` 填充所有受管块。

---

## 5. 不配对 Marker 的处理

若结构文件中只有 `start` 而缺少 `end`，或只有 `end` 而缺少 `start`，`replace_block()` 会抛出：

```
ValueError("unbalanced-marker")
```

`apply` / `check` 遇到此异常时：**报错、跳过该文件、不写入**，并将该路径列入报告的错误区。

对应的 `replace_block()` 异常体系：

| 异常值 | 触发条件 |
|---|---|
| `no-marker` | start 和 end 都不存在 |
| `unbalanced-marker` | start/end 数量不对称（各自 `count != 1`） |
| `reversed-marker` | end 在 start 之前（marker 顺序颠倒） |

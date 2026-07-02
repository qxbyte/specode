# 子 skill 能力说明

供 `wiki-orchestrate` 编排时参考：两个子 skill 各自能干什么、怎么调、读写边界、红线、
适合在什么体检信号下触发。

> **基调（重要）**：本文是**能力说明**，不是限制。两个 skill 的**所有命令对模型全部开放**；
> "何时倾向触发"只是建议。是否调用、调哪个命令、用什么参数、是否跳过——**最终由模型按当次
> 体检结果按需判断**。下文所有相对路径以 vault 根为基准；调脚本时请传 `--vault "<vault>"`。

---

## 1. wiki-struct —— 结构层

| 字段 | 内容 |
|---|---|
| **职责** | 确定性重写结构文件的受管块：`00-Index/Home.md` 总览树、15 个一级目录 `README.md`、15 个 `00-Index/<目录>.md` 分区页。只改 marker 之间，marker 外人工内容一字不动。 |
| **脚本入口** | `python3 "$WIKI/skills/wiki-struct/scripts/struct_gen.py" check --vault "<vault>"`（体检，只读）<br>`… struct_gen.py apply [--scope home\|readmes\|partitions\|all] --vault "<vault>"`（重写受管块） |
| **LLM 流程** | `init`（为缺 marker 的结构文件逐文件 AskUserQuestion 插入受管区）是 SKILL.md 编排的交互流程，不是脚本子命令。`apply` 前若有缺 marker 文件需先 init。 |
| **读 / 写** | 读：全 vault 结构。写：仅结构文件的受管块（`<!-- wiki-struct:tree start/end -->` 之间）。 |
| **报告文件** | `00-Index/_system/struct-report.md`（drift / 缺 marker / 缺文件 / 坏链 计数） |
| **红线** | 永不修改/移动/重命名任何内容笔记；敏感目录受管块只含文件名级链接；apply 前 tar 备份、AskUserQuestion；写后写 wiki-log。 |
| **何时倾向触发** | struct check 报 **drift > 0**（受管块过时）、**broken > 0**（坏链）、**缺 marker > 0**（需 init）。结构层是后续阶段的导航基线，**通常先跑**。 |

调用建议：先 `check`；若仅 drift 且无缺 marker → `apply`（可 `--scope` 限范围）；若有缺 marker
→ 按 wiki-struct SKILL.md 走 `init` 逐文件确认，再 `apply` 填充。

---

## 2. wiki-curate —— 内容向策展

| 字段 | 内容 |
|---|---|
| **职责** | 内容向策展：ingest / curate / lint（方法论伞）。结构层（Home 树/分区页/README/地图）见 wiki-struct；SpecIn 知识沉淀已迁移到 specode 的 `/specode:distill`（v2.0.0 剥离）。**专注内容笔记质量，不碰受管块、不写遗留知识库产物。** |
| **脚本入口** | `python3 "$WIKI/skills/wiki-curate/scripts/lint.py" lint --vault "<vault>"`（确定性内容体检：缺「用途」段 / 重复 basename / 孤儿无反链 / frontmatter 缺字段）。`scan` 与 `lint` 流程都内部调用它。 |
| **LLM 流程** | `ingest <path>`（吸纳单篇：摘要/挂索引/补双链/记日志，完成后提示跑 `wiki-struct apply`）；`curate`（补缺失「用途」段、英文说明性标签改中文、在相关内容笔记正文补 `[[..]]` 修复孤儿双链；**不碰受管块**）；`lint`（跑 lint.py + LLM 判断过时/矛盾）。 |
| **读 / 写** | 读：全 vault。写：Wiki 区内容笔记（`01-Concepts/`~`08-Sources/`、`09-Journal/` 等正文）。**不写 wiki-struct 受管块，不写遗留的 `10-Work/知识库/` 产物（历史 spec-distill 产物，保留只读）。** |
| **报告文件** | `00-Index/_system/curate-report.md`（scan）、`00-Index/_system/lint-report.md`（lint）。 |
| **红线** | 绝不移动/重命名/删除 `07-Ideas/`、`10-Work/`、`SpecIn/` 原文；敏感子目录只路径级；破坏性动作前 AskUserQuestion；批量前备份。**坏链与结构漂移不归它管——见 `wiki-struct check`。** |
| **何时倾向触发** | 策展巡查发现 **孤儿页**、**缺「用途」段**、**收件箱（99-Inbox/、Clippings/）积压**、或需要**内容健康体检**。**通常作为收尾阶段**。 |

调用建议：取 ingest / curate / lint 三项做内容向策展。**不写死**——是否调用、调哪个命令由模型按需判断。
注意 wiki-curate 的 lint **不处理坏链 / 结构漂移**（那是 wiki-struct check 的职责），不要指望它修坏链。

---

## 共用产物与约定

- 两者都向 `<vault>/<system_dir>/wiki-log.md`（`system_dir` 来自该库配置（家目录注册表 `configs/<名>.json`，回退 `<vault>/.wiki/config.json`），默认 `00-Index/_system`）追加 append-only 操作日志（编排入口也写）。
- 两者报告都落在 `<vault>/<system_dir>/` 下，编排入口只读汇总，不覆盖它们。
- 两者脚本 `--vault` **必填**（代码在插件 cache、不从位置推断 vault）；结构配置由家目录注册表 `~/.config/obsidian-wiki/configs/<名>.json` 给（未注册则回退 `<vault>/.wiki/config.json`）。

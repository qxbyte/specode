# distill 拆分启发式（原子知识点提炼）

目标：把一个完成的 spec + 当前 agent 上下文，提炼为若干**原子知识点**——每个点
一份文档，归入两类之一。粒度准则：**一个点 = 一个可独立命中、可独立复用的定位单元**。

## 两类判定

| 类型 | 提炼什么 | 触发信号 |
|---|---|---|
| `case` | 本需求「改了什么 + 在哪些前后端文件 + 调用链 + 踩坑」 | requirements/design 里每个独立的功能改动 |
| `navigation` | 超出本需求的**项目级导航经验**（页面按钮→哪个文件、什么配置映射到后端入口、某类页面的定位套路） | agent 上下文里反复用到的「找文件」经验 |

## 提炼步骤
1. 读全 spec（requirements / design / implementation-log）+ 回顾本轮 agent 上下文。
2. 列 case 候选：每个独立改动一个点（不要把整需求塞进一个文档）。
3. 列 navigation 候选：哪些「定位/导航」经验是换个需求也能复用的？
4. 每个候选给 `标题 / 类型 / 来源 / tags / 描述`；`tags` 取自**页面名 / 字段名 / 功能域**三类具体名词（不引入受控词表）。
5. `AskUserQuestion` 让用户 confirm / add / drop / rename / recategorize，锁定后逐个落盘。

> **navigation 去重（F7）**：列 navigation 候选 / 落盘前，先 `Read` 项目 `knowledge-base/MEMORY.md`；若已有同主题 navigation 点（`tags`+`标题` 相近）→ **合并/更新已有文档**而非新建（索引层不去重，重复会留下两条）。
> **时机（F1）**：distill 在**执行 + 验收完成后**沉淀价值最高；在未执行完的 spec（design 还有未勾选 `- [ ]` Task）上沉淀，知识点可能指向**未落地代码**——distill Step 1 的执行完成度检查会就此告警。

## 例（构思里的银行账号场景）
- 需求1「A页面银行账号脱敏」→ case:「A页面脱敏改法」 + navigation:「DTO 层脱敏的统一位置」
- 需求2「B页面查询列表加一列」→ case:「B页面列表加列改法」 + navigation:「查询列表页定位套路」

> 这样需求3/4 来时，检索端能按 tags 命中这些原子点，跨需求组合借鉴（见 Plan B）。

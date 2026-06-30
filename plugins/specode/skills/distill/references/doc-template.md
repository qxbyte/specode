# distill 文档模板（定位优先双轨）

distill 沉淀的是**原子知识点**：一个需求扇出 N 份独立文档，每个知识点/经验点各一文件。
两类模板：`case`（按需求的前后端改法/调用链）与 `navigation`（项目级导航经验）。
所有文档落在 `<project_root>/knowledge-base/{cases,navigation}/<topic-kebab>.md`。

> 顶层不变量：这里写的是**定位指针**（文件路径 + 调用链 + 导航经验），不是事实结论。
> 检索端只用它快速定位真实代码，仍以真实代码为唯一事实。

## frontmatter（两类通用，键名固定）

```markdown
---
标题: <知识点标题>
类型: case            # case | navigation
来源: <源 spec slug>   # case 必填；navigation 跨 spec 累积可留最近一次
tags: [<页面名>, <字段名>, <功能域>]
描述: <一句话，二次相关性信号>
---
```

`memory-rebuild` 由上述 frontmatter 自动生成 MEMORY 行：
`| 标题 | 类型 | 描述 | 来源 | 路径 | tags |`（请勿手改 MEMORY.md）。

## case 模板（cases/<topic-kebab>.md）

```markdown
---
标题: A页面银行账号脱敏改法
类型: case
来源: 需求1-脱敏
tags: [银行账号, 脱敏, A页面]
描述: 前端列渲染处脱敏 + 后端 DTO 脱敏
---

# A页面银行账号脱敏改法

## 定位
- 前端文件: src/pages/A/columns.tsx（脱敏在列 render）
- 后端文件: .../AccountDTO.java（@Mask 注解）
- 调用链: A页面 → /api/account/list → AccountController#list → AccountService → AccountDTO

## 可复用经验 / 坑
- 脱敏在 DTO 层做，列表/详情共用，别在前端硬写
- 导出 Excel 走另一个 DTO，需单独处理
```

## navigation 模板（navigation/<topic-kebab>.md）

```markdown
---
标题: 查询列表页定位套路
类型: navigation
来源: 需求2-列表列
tags: [查询列表, 定位, B页面]
描述: 列表页 → 前后端文件的定位路径
---

# 查询列表页定位套路

## 导航问题
- 「某查询列表页要改/加一列」时，怎么快速找到前后端文件？

## 答案路径
- 前端: src/pages/<X>/index.tsx 的 columns 定义
- 路由→接口: src/api/<X>.ts 的 list 方法
- 后端入口: <X>Controller#list（@RequestMapping 映射）

## 适用范围
- 所有走统一列表组件的页面；自定义表格不适用
```

## 写入规则
- 文件按**主题** kebab 命名，不按 slug。
- 已存在同名文件 → `Read` 后问用户 `overwrite / skip / merge`。
- navigation 跨 spec 去重合并：由模型按 `tags` + `标题` 判定是否同一导航点，是则 merge/更新，否则新建。
- 全部写完后，host agent 运行 `knowledge.py memory-rebuild --kb <project_root>/knowledge-base` 重建索引。

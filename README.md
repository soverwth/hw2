# Simple Workflow MVP

一个轻量级 **多 Agent 协作工作流**（Workflow）MVP，用于理解 **Workflow 编排、Agent 间通信、状态管理** 三大核心概念。仅依赖 Python 标准库，零第三方依赖，开箱即用。

## 项目亮点

| 能力 | 说明 | 对应要求 |
|------|------|----------|
| 多 Agent 协作 | 3 个 Agent（需求→设计→编码）完成端到端流程 | 必须：至少 2 个 Agent |
| 消息传递 | Agent 之间通过 `Message` 显式通信 | 必须：消息传递/状态共享 |
| 状态管理 | `WorkflowContext` 统一管理共享状态与节点状态 | 必须 |
| 顺序执行 | `Workflow` 按序调度节点 | 必须：基本流程控制 |
| 条件分支 | `Step(condition=...)` 支持守卫条件 | 推荐 |
| 循环 | `LoopStep` 支持 while 循环 | 推荐 |
| 并行 | `ParallelStep` 并发执行互不依赖的节点 | 推荐 |
| 日志与追踪 | 执行日志 + 节点状态 + 完整记录可导出 JSON | 推荐 |
| 错误处理 | 重试 + `on_error` 容错策略 | 推荐 |

## 目录结构

```
simple-workflow-mvp/
├── main.py                      # Mini SE 流程演示入口
├── examples/
│   └── code_review_flow.py      # 代码审查（循环）示例
├── workflow/
│   ├── __init__.py
│   ├── context.py               # WorkflowContext / Message / 日志 / 状态
│   ├── agent.py                 # Agent 基类
│   ├── engine.py                # Step / LoopStep / ParallelStep / Workflow
│   └── agents.py                # 具体 Agent 实现
├── tests/
│   └── test_workflow.py         # 单元测试
├── requirements.txt             # 无第三方依赖
└── README.md / Design.md        # 文档
```

## 快速开始

```bash
# 1) 运行 Mini SE 流程（需求 → 设计 → 代码）
python main.py

# 2) 运行代码审查流程（审查 → 修复 → 循环，直到无遗留问题）
python examples/code_review_flow.py

# 3) 运行单元测试
python -m unittest discover -s tests -v
```

`main.py` 会在 `generated/` 目录下生成自动编写的 `calculator.py` 与完整执行记录 `execution_log.json`。

## 核心概念与用法

### 1. 状态管理 —— `WorkflowContext`

每个 Agent 共享同一个 `WorkflowContext`，通过键值对读写状态：

```python
ctx = WorkflowContext({"input": "实现一个计算器……"})
ctx.set("requirements", {...})   # 上游写入
reqs = ctx.get("requirements")   # 下游读取
```

### 2. Agent 间通信 —— 消息传递

Agent 除了写共享状态，还能显式发消息给下游：

```python
class DesignAgent(Agent):
    def run(self, ctx):
        design = {...}
        self.send(ctx, "CodingAgent", {"design": design}, msg_type="design")
        return design
```

### 3. 工作流编排 —— 顺序 / 条件 / 循环 / 并行

```python
wf = Workflow("MiniSE")
wf.step("需求分析", RequirementAgent())
wf.step("方案设计", DesignAgent())
wf.step("编码实现", CodingAgent())

# 条件分支：仅当满足条件时执行
wf.step("可选步骤", SomeAgent(), condition=lambda c: c.get("enable_extra"))

# 循环：审查 → 修复，直到没有遗留问题
wf.loop("审查修复循环", [Step("审查", ReviewAgent()), Step("修复", FixAgent())],
        while_condition=lambda c: bool(c.get("review_issues")), max_iterations=5)

# 并行：互不依赖的任务并发执行
wf.parallel("并行任务", [Step("A", AgentA()), Step("B", AgentB())])

ctx = wf.run()
print(wf.summary(ctx))
```

## Mini SE 流程（主演示）

```
输入需求 ──► 需求分析(RequirementAgent) ──► 方案设计(DesignAgent) ──► 编码实现(CodingAgent) ──► 可运行代码 + 自检结果
```

- `RequirementAgent`：自然语言需求 → 结构化需求（功能、约束、验收标准）
- `DesignAgent`：结构化需求 → 技术方案（架构、模块、关键决策）
- `CodingAgent`：需求 + 设计 → 生成 Python 代码，并做**编译 + 冒烟测试自检**，形成端到端闭环

详细架构与设计见 [Design.md](./Design.md)。

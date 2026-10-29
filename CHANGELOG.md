# 更新日志

## [2.0.0] - 2026-10-18

### Bug 修复

- **引擎（`Step`）参数校验**：`max_retries < 1` 或非法的 `on_error` 现在会在构造时抛出 `ValueError`，而不是在重试耗尽后抛出 `TypeError`（`raise None`）。
- **审查 Agent 误判**：`ReviewAgent` 不再用 `"pass" in code` 这种子串匹配，改用正则精确匹配「整行只有 `pass`」的空实现，避免把 `compass`/`bypass` 等单词误判为问题。
- **修复 Agent 可靠性**：`FixAgent` 全部改用正则、并保留原始缩进：
  - 补除零校验不再依赖固定缩进的 `return a / b`；
  - 空实现 `pass` 改为 `raise NotImplementedError(...)`，避免「函数体只剩注释」导致的语法错误；
  - 移除 `TODO` 只匹配独立单词，不会误改 `TODOS` 等；
  - `fix_log` 改为累积记录，多轮审查循环中最后一轮不再覆盖历史修复记录。
- **并行节点容错**：`ParallelStep` 现在会等待所有子节点完成、汇总成功/失败结果，子节点失败时把节点状态置为 `FAILED` 并抛出带明细的异常，不再丢失部分结果。
- **`dump_json` 自动建目录**：目标目录不存在时自动创建，避免导出执行记录时崩溃。
- **需求句子切分**：`RequirementAgent` 支持按 `。！？!?；;` 和换行切分，不再只认 `。`。
- **编码页脚防御**：`CodingAgent` 生成的 `__main__` 块在没有 `add` 功能时不再调用不存在的 `calc.add`。

### 新增

- 新增 `workflow.__version__` 版本号（`2.0.0`）。
- `main.py` 运行时打印当前版本。
- 补充针对上述修复的单元测试。

## [1.0.0] - 2026-10-18

- 首个版本：`WorkflowContext` / `Agent` / `Step` / `LoopStep` / `ParallelStep` / `Workflow`。
- Mini SE 流程（需求 → 设计 → 代码）与代码审查流程（审查 → 修复循环）两个演示。
- 8 个单元测试，README.md 与 Design.md 文档。

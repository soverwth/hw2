"""Simple Workflow MVP —— Mini SE 流程演示入口。

演示一个 3 个 Agent 协作的端到端流程：
    需求分析（RequirementAgent）→ 方案设计（DesignAgent）→ 编码实现（CodingAgent）

运行：
    python main.py
"""

from __future__ import annotations

import json
import sys

from workflow import (
    Workflow,
    WorkflowContext,
    RequirementAgent,
    DesignAgent,
    CodingAgent,
    __version__,
)

INPUT = (
    "实现一个计算器程序，支持加法、减法、乘法、除法四种运算，"
    "除法时需要处理除数为零的情况。"
)


def build_workflow() -> Workflow:
    wf = Workflow("MiniSE-Workflow")
    wf.step("需求分析", RequirementAgent())
    wf.step("方案设计", DesignAgent())
    wf.step("编码实现", CodingAgent())
    return wf


def main() -> int:
    print(f"Simple Workflow MVP v{__version__}")
    print()
    ctx = WorkflowContext({"input": INPUT, "output_dir": "generated"})
    wf = build_workflow()

    try:
        wf.run(ctx)
    except Exception as exc:  # noqa: BLE001
        print(f"Workflow 执行失败：{exc}", file=sys.stderr)
        return 1

    print(wf.summary(ctx))
    print()

    print("=== 结构化需求 ===")
    print(json.dumps(ctx.get("requirements"), ensure_ascii=False, indent=2))
    print()

    print("=== 设计方案 ===")
    print(json.dumps(ctx.get("design"), ensure_ascii=False, indent=2))
    print()

    print("=== 自动生成的代码 ===")
    print(ctx.get("code"))
    print()

    print("=== 编码自检（编译 + 冒烟测试） ===")
    print(json.dumps(ctx.get("validation"), ensure_ascii=False, indent=2))
    print()

    print("=== Agent 间消息传递 ===")
    for msg in ctx.messages:
        print(f"  {msg.sender} --[{msg.msg_type}]--> {msg.recipient}")
    print()

    # 导出完整执行记录
    log_path = ctx.dump_json("generated/execution_log.json")
    print(f"完整执行记录已导出：{log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

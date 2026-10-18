"""代码审查流程示例 —— 演示条件分支 + 循环控制。

流程：审查（ReviewAgent）→ 修复（FixAgent）→ 再审查…… 直到没有遗留问题。

运行：
    python examples/code_review_flow.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workflow import Workflow, WorkflowContext, Step, ReviewAgent, FixAgent  # noqa: E402

# 一段“故意有问题”的初始代码：除法未处理除零、遗留 TODO
INITIAL_CODE = '''\
class Calculator:
    def divide(self, a, b):
        return a / b

# TODO: 补充乘法实现
'''


def build_workflow() -> Workflow:
    wf = Workflow("CodeReview-Workflow")
    wf.loop(
        "审查修复循环",
        [Step("审查", ReviewAgent()), Step("修复", FixAgent())],
        while_condition=lambda c: bool(c.get("review_issues")),
        max_iterations=5,
    )
    return wf


def main() -> int:
    ctx = WorkflowContext({"code": INITIAL_CODE, "review_issues": [], "fix_log": []})
    wf = build_workflow()
    wf.run(ctx)

    print(wf.summary(ctx))
    print()
    print("=== 审查修复轮次 ===")
    print(f"共执行 {ctx.get('loop_iteration', 0)} 轮")
    print()
    print("=== 修复记录 ===")
    for item in ctx.get("fix_log", []):
        print(f"  - {item}")
    print()
    print("=== 最终代码 ===")
    print(ctx.get("code"))
    print()
    print("=== 循环结束后剩余问题 ===")
    print(ctx.get("review_issues"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

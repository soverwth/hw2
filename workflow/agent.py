"""Agent 基类：可被 Workflow 调度的最小执行单元。

子类只需实现 ``run(ctx)``：

1. 从 ``ctx`` 读取上游产出；
2. 执行本 Agent 的职责；
3. 把结果写回 ``ctx``（共享状态），并通过 ``send()`` 向其他 Agent 发消息。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .context import WorkflowContext


class Agent:
    """Agent 抽象基类。"""

    name = "Agent"

    def __init__(self, name: Optional[str] = None) -> None:
        if name:
            self.name = name

    def run(self, ctx: WorkflowContext) -> Any:
        """执行 Agent 的核心逻辑，子类必须实现。"""
        raise NotImplementedError

    def send(
        self,
        ctx: WorkflowContext,
        recipient: str,
        payload: Optional[Dict[str, Any]] = None,
        msg_type: str = "data",
    ):
        """以本 Agent 的身份向 ``recipient`` 发送一条消息。"""
        return ctx.send(self.name, recipient, payload, msg_type)

    def __repr__(self) -> str:  # pragma: no cover - 仅为调试便利
        return f"<{self.name}>"

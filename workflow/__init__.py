"""Simple Workflow MVP —— 一个轻量级多 Agent 工作流框架。

核心概念：
- WorkflowContext：共享状态 + 消息总线 + 日志/状态追踪
- Agent：可调度的最小执行单元
- Workflow/Step/LoopStep/ParallelStep：编排引擎（顺序/条件/循环/并行）
"""

from .context import Message, WorkflowContext, WorkflowStatus
from .agent import Agent
from .engine import Node, Step, LoopStep, ParallelStep, Workflow
from .agents import RequirementAgent, DesignAgent, CodingAgent, ReviewAgent, FixAgent

__all__ = [
    "Message",
    "WorkflowContext",
    "WorkflowStatus",
    "Agent",
    "Node",
    "Step",
    "LoopStep",
    "ParallelStep",
    "Workflow",
    "RequirementAgent",
    "DesignAgent",
    "CodingAgent",
    "ReviewAgent",
    "FixAgent",
]

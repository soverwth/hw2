"""工作流编排引擎。

提供四种编排能力：

- ``Step``        顺序执行单个 Agent，支持条件守卫、重试与容错（必须项）
- ``LoopStep``    循环执行一组子节点直到条件不满足（推荐项）
- ``ParallelStep`` 并发执行一组互不依赖的子节点（推荐项）
- ``Workflow``    把节点串成端到端流程并统一维护状态与日志
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from .agent import Agent
from .context import WorkflowContext, WorkflowStatus


class Node:
    """工作流节点的抽象基类。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def execute(self, ctx: WorkflowContext) -> Any:
        raise NotImplementedError


class Step(Node):
    """执行单个 Agent 的节点。

    参数：
        name        节点名称（用于日志与状态追踪）
        agent       要执行的 Agent 实例
        condition   可选守卫 ``callable(ctx) -> bool``，返回 False 时跳过本节点
        max_retries 失败后的最大重试次数（>= 1）
        on_error    重试耗尽后的策略："raise"（默认，抛出）或 "continue"（记录后继续）
    """

    def __init__(
        self,
        name: str,
        agent: Agent,
        condition: Optional[Callable[[WorkflowContext], bool]] = None,
        max_retries: int = 1,
        on_error: str = "raise",
    ) -> None:
        super().__init__(name)
        if not isinstance(max_retries, int) or max_retries < 1:
            raise ValueError(f"max_retries 必须是 >= 1 的整数，收到: {max_retries!r}")
        if on_error not in ("raise", "continue"):
            raise ValueError(f"on_error 必须是 'raise' 或 'continue'，收到: {on_error!r}")
        self.agent = agent
        self.condition = condition
        self.max_retries = max_retries
        self.on_error = on_error

    def execute(self, ctx: WorkflowContext) -> Any:
        # 条件守卫：不满足则跳过
        if self.condition is not None and not bool(self.condition(ctx)):
            ctx.set_node_status(self.name, WorkflowStatus.SKIPPED, reason="condition_false")
            ctx.log("info", f"[{self.name}] 条件不满足，跳过执行")
            return None

        error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                ctx.set_node_status(
                    self.name, WorkflowStatus.RUNNING, attempt=attempt, agent=self.agent.name
                )
                ctx.log("info", f"[{self.name}] 开始执行 ({self.agent.name})，第 {attempt} 次尝试")
                started = time.time()
                result = self.agent.run(ctx)
                duration = time.time() - started
                ctx.set_node_status(
                    self.name,
                    WorkflowStatus.SUCCEEDED,
                    attempt=attempt,
                    agent=self.agent.name,
                    duration=round(duration, 3),
                )
                ctx.log("info", f"[{self.name}] 执行成功，耗时 {duration:.3f}s")
                return result
            except Exception as exc:  # noqa: BLE001 - 捕获并统一处理所有失败
                error = exc
                ctx.log("error", f"[{self.name}] 第 {attempt} 次执行失败: {exc}")

        # 重试耗尽（此时 error 必为最近一次异常）
        if self.on_error == "raise":
            ctx.set_node_status(self.name, WorkflowStatus.FAILED, agent=self.agent.name, error=str(error))
            raise error  # type: ignore[misc]
        ctx.set_node_status(
            self.name, WorkflowStatus.FAILED, agent=self.agent.name, error=str(error), recovered="continue"
        )
        ctx.log("warn", f"[{self.name}] 执行失败但已忽略（on_error=continue）: {error}")
        return None


class LoopStep(Node):
    """循环节点：反复执行一组子节点，直到 ``while_condition`` 不再成立或达到 ``max_iterations``。

    语义为 do-while：先执行一轮子节点，再判断是否继续。
    """

    def __init__(
        self,
        name: str,
        nodes: List[Node],
        while_condition: Callable[[WorkflowContext], bool],
        max_iterations: int = 5,
    ) -> None:
        super().__init__(name)
        if not isinstance(max_iterations, int) or max_iterations < 1:
            raise ValueError(f"max_iterations 必须是 >= 1 的整数，收到: {max_iterations!r}")
        self.nodes = nodes
        self.while_condition = while_condition
        self.max_iterations = max_iterations

    def execute(self, ctx: WorkflowContext) -> int:
        for i in range(1, self.max_iterations + 1):
            ctx.log("info", f"[{self.name}] 第 {i}/{self.max_iterations} 轮")
            ctx.set("loop_iteration", i)
            for node in self.nodes:
                node.execute(ctx)
            if not bool(self.while_condition(ctx)):
                ctx.set_node_status(self.name, WorkflowStatus.SUCCEEDED, iterations=i, exit="condition_false")
                ctx.log("info", f"[{self.name}] 循环条件不再满足，第 {i} 轮后退出")
                return i
        ctx.set_node_status(
            self.name, WorkflowStatus.SUCCEEDED, iterations=self.max_iterations, exit="max_iterations"
        )
        ctx.log("warn", f"[{self.name}] 达到最大循环次数 {self.max_iterations}，强制退出")
        return self.max_iterations


class ParallelStep(Node):
    """并行节点：并发执行一组互不依赖的子节点。

    注意：并行子节点应写入互不冲突的共享状态键。
    任一子节点失败时，等待其余子节点完成后抛出异常，并记录 FAILED 状态。
    """

    def __init__(self, name: str, nodes: List[Node]) -> None:
        super().__init__(name)
        self.nodes = nodes

    def execute(self, ctx: WorkflowContext) -> Dict[str, Any]:
        node_names = [n.name for n in self.nodes]
        ctx.set_node_status(self.name, WorkflowStatus.RUNNING, nodes=node_names)
        ctx.log("info", f"[{self.name}] 并行执行 {len(self.nodes)} 个节点")

        results: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=max(1, len(self.nodes))) as executor:
            future_to_node = {executor.submit(node.execute, ctx): node for node in self.nodes}
            for future in as_completed(future_to_node):
                node = future_to_node[future]
                try:
                    results[node.name] = future.result()
                except Exception as exc:  # noqa: BLE001
                    errors[node.name] = str(exc)
                    ctx.log("error", f"[{self.name}] 子节点 {node.name} 执行失败: {exc}")

        if errors:
            ctx.set_node_status(self.name, WorkflowStatus.FAILED, nodes=node_names, errors=errors)
            raise RuntimeError(f"并行节点 {self.name} 有子节点失败: {errors}")

        ctx.set_node_status(self.name, WorkflowStatus.SUCCEEDED, nodes=sorted(results.keys()))
        return results


class Workflow:
    """工作流编排器：按顺序执行节点，统一维护状态与日志。"""

    def __init__(self, name: str, context: Optional[WorkflowContext] = None) -> None:
        self.name = name
        self.context = context if context is not None else WorkflowContext()
        self.nodes: List[Node] = []

    # ---------- 构建 ----------
    def add(self, node: Node) -> Node:
        self.nodes.append(node)
        return node

    def step(self, name: str, agent: Agent, **kw: Any) -> Step:
        return self.add(Step(name, agent, **kw))  # type: ignore[return-value]

    def loop(
        self,
        name: str,
        nodes: List[Node],
        while_condition: Callable[[WorkflowContext], bool],
        max_iterations: int = 5,
    ) -> LoopStep:
        return self.add(LoopStep(name, nodes, while_condition, max_iterations))  # type: ignore[return-value]

    def parallel(self, name: str, nodes: List[Node]) -> ParallelStep:
        return self.add(ParallelStep(name, nodes))  # type: ignore[return-value]

    # ---------- 执行 ----------
    def run(self, context: Optional[WorkflowContext] = None) -> WorkflowContext:
        ctx = context if context is not None else self.context
        ctx.set("workflow_name", self.name)
        started = time.time()
        ctx.set_node_status(self.name, WorkflowStatus.RUNNING)
        ctx.log("info", f"========== Workflow[{self.name}] 开始 ==========")
        try:
            for node in self.nodes:
                node.execute(ctx)
            ctx.set_node_status(self.name, WorkflowStatus.SUCCEEDED, duration=round(time.time() - started, 3))
        except Exception as exc:  # noqa: BLE001
            ctx.set_node_status(
                self.name, WorkflowStatus.FAILED, error=str(exc), duration=round(time.time() - started, 3)
            )
            ctx.log("error", f"Workflow[{self.name}] 执行失败: {exc}")
            raise
        finally:
            ctx.log("info", f"========== Workflow[{self.name}] 结束 ==========")
        return ctx

    # ---------- 输出 ----------
    def summary(self, ctx: Optional[WorkflowContext] = None) -> str:
        ctx = ctx or self.context
        lines = [f"Workflow[{self.name}] 执行摘要："]
        for node in self.nodes:
            st = ctx.node_states.get(node.name, {})
            lines.append(f"  - {node.name}: {st.get('status', WorkflowStatus.PENDING.value)}")
        return "\n".join(lines)

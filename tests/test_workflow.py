"""工作流框架单元测试。

运行：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workflow import (  # noqa: E402
    Agent,
    CodingAgent,
    DesignAgent,
    FixAgent,
    RequirementAgent,
    ReviewAgent,
    Step,
    Workflow,
    WorkflowContext,
)


class EchoAgent(Agent):
    """测试用 Agent：写入一个状态键，可选地向下游发消息。"""

    def __init__(self, name, key, value, recipient=None):
        super().__init__(name)
        self.key = key
        self.value = value
        self.recipient = recipient

    def run(self, ctx):
        ctx.set(self.key, self.value)
        if self.recipient:
            self.send(ctx, self.recipient, {self.key: self.value})
        return self.value


class IncAgent(Agent):
    """测试用 Agent：让计数器 +1。"""

    def run(self, ctx):
        ctx.set("counter", ctx.get("counter", 0) + 1)
        return ctx.get("counter")


class BoomAgent(Agent):
    """测试用 Agent：总是抛出异常。"""

    def run(self, ctx):
        raise RuntimeError("boom")


class TestSequentialAndState(unittest.TestCase):
    def test_two_agents_share_state(self):
        ctx = WorkflowContext()
        wf = Workflow("t")
        wf.step("A", EchoAgent("AgentA", "x", 1))
        wf.step("B", EchoAgent("AgentB", "y", 2))
        wf.run(ctx)
        self.assertEqual(ctx.get("x"), 1)
        self.assertEqual(ctx.get("y"), 2)
        self.assertEqual(ctx.status_of("A"), "SUCCEEDED")
        self.assertEqual(ctx.status_of("t"), "SUCCEEDED")

    def test_message_passing(self):
        ctx = WorkflowContext()
        wf = Workflow("t")
        wf.step("A", EchoAgent("AgentA", "x", 42, recipient="AgentB"))
        wf.run(ctx)
        msgs = ctx.messages_for("AgentB")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].sender, "AgentA")
        self.assertEqual(msgs[0].payload["x"], 42)


class TestFlowControl(unittest.TestCase):
    def test_conditional_skip(self):
        ctx = WorkflowContext({"flag": False})
        wf = Workflow("t")
        wf.step("A", EchoAgent("AgentA", "x", 1), condition=lambda c: c.get("flag"))
        wf.run(ctx)
        self.assertEqual(ctx.status_of("A"), "SKIPPED")
        self.assertIsNone(ctx.get("x"))

    def test_loop_terminates(self):
        ctx = WorkflowContext({"counter": 0})
        wf = Workflow("t")
        wf.loop(
            "L",
            [Step("inc", IncAgent())],
            while_condition=lambda c: c.get("counter") < 3,
            max_iterations=10,
        )
        wf.run(ctx)
        self.assertEqual(ctx.get("counter"), 3)
        self.assertEqual(ctx.status_of("L"), "SUCCEEDED")

    def test_parallel_execution(self):
        ctx = WorkflowContext()
        wf = Workflow("t")
        wf.parallel(
            "P",
            [
                Step("a", EchoAgent("AgentA", "a", 1)),
                Step("b", EchoAgent("AgentB", "b", 2)),
                Step("c", EchoAgent("AgentC", "c", 3)),
            ],
        )
        wf.run(ctx)
        self.assertEqual(ctx.get("a"), 1)
        self.assertEqual(ctx.get("b"), 2)
        self.assertEqual(ctx.get("c"), 3)
        self.assertEqual(ctx.status_of("P"), "SUCCEEDED")


class TestErrorHandling(unittest.TestCase):
    def test_on_error_continue(self):
        ctx = WorkflowContext()
        wf = Workflow("t")
        wf.step("boom", BoomAgent(), on_error="continue")
        wf.step("ok", EchoAgent("AgentOK", "ok", True))
        wf.run(ctx)
        self.assertEqual(ctx.status_of("boom"), "FAILED")
        self.assertTrue(ctx.get("ok"))

    def test_on_error_raise(self):
        wf = Workflow("t")
        wf.step("boom", BoomAgent())
        with self.assertRaises(RuntimeError):
            wf.run()
        self.assertEqual(wf.context.status_of("t"), "FAILED")

    def test_parallel_failure_marks_failed(self):
        ctx = WorkflowContext()
        wf = Workflow("t")
        wf.parallel(
            "P",
            [Step("a", EchoAgent("AgentA", "a", 1)), Step("boom", BoomAgent())],
        )
        with self.assertRaises(RuntimeError):
            wf.run(ctx)
        self.assertEqual(ctx.status_of("P"), "FAILED")
        # 成功的子节点结果仍被记录
        self.assertEqual(ctx.get("a"), 1)


class TestValidation(unittest.TestCase):
    def test_step_max_retries_must_be_positive(self):
        with self.assertRaises(ValueError):
            Step("x", EchoAgent("A", "x", 1), max_retries=0)

    def test_step_on_error_must_be_valid(self):
        with self.assertRaises(ValueError):
            Step("x", EchoAgent("A", "x", 1), on_error="skip")


class TestReviewAndFix(unittest.TestCase):
    def test_review_does_not_flag_pass_substring(self):
        code = "def foo(self):\n    return 'compass and bypass'\n"
        ctx = WorkflowContext({"code": code})
        ReviewAgent().run(ctx)
        self.assertNotIn("存在空实现（pass）", ctx.get("review_issues"))

    def test_review_flags_standalone_pass(self):
        code = "def foo(self):\n    pass\n"
        ctx = WorkflowContext({"code": code})
        ReviewAgent().run(ctx)
        self.assertIn("存在空实现（pass）", ctx.get("review_issues"))

    def test_fix_divide_preserves_indentation(self):
        code = "class C:\n  def divide(self, a, b):\n    return a / b\n"
        ctx = WorkflowContext({"code": code, "review_issues": ["除法未处理除数为零的情况"]})
        FixAgent().run(ctx)
        fixed = ctx.get("code")
        self.assertIn("if b == 0:", fixed)
        self.assertIn("raise ValueError", fixed)
        # 修复后的代码应可编译
        ns: dict = {}
        exec(compile(fixed, "<t>", "exec"), ns)

    def test_fix_pass_becomes_raise(self):
        code = "class C:\n    def f(self):\n        pass\n"
        ctx = WorkflowContext({"code": code, "review_issues": ["存在空实现（pass）"]})
        FixAgent().run(ctx)
        fixed = ctx.get("code")
        self.assertIn("raise NotImplementedError", fixed)
        self.assertNotIn("pass", fixed)
        # 修复后的代码应可编译（不会出现“函数体只剩注释”）
        ns: dict = {}
        exec(compile(fixed, "<t>", "exec"), ns)

    def test_fix_log_accumulates_across_rounds(self):
        code = "class C:\n    def divide(self, a, b):\n        return a / b\n"
        ctx = WorkflowContext({"code": code, "review_issues": ["除法未处理除数为零的情况"]})
        FixAgent().run(ctx)
        # 第二轮：无问题可修，不应覆盖上一轮的修复记录
        ctx.set("review_issues", [])
        FixAgent().run(ctx)
        self.assertEqual(ctx.get("fix_log"), ["补充除零校验（1 处）"])


class TestDumpJson(unittest.TestCase):
    def test_dump_json_creates_parent_dirs(self):
        project_root = Path(__file__).resolve().parent.parent
        target = os.path.join(str(project_root), "_test_output", "logs", "a", "b.json")
        ctx = WorkflowContext({"x": 1})
        ctx.dump_json(target)
        self.assertTrue(os.path.exists(target))
        shutil.rmtree(os.path.join(str(project_root), "_test_output"), ignore_errors=True)


class TestMiniSEEndToEnd(unittest.TestCase):
    def test_end_to_end(self):
        # 使用项目内的输出目录（系统/临时目录在受限环境下可能被拦截写入）
        project_root = Path(__file__).resolve().parent.parent
        out_dir = os.path.join(str(project_root), "_test_output")
        ctx = WorkflowContext(
            {
                "input": "实现一个计算器，支持加法、减法、乘法、除法，除数为零时报错。",
                "output_dir": out_dir,
            }
        )
        wf = Workflow("MiniSE")
        wf.step("需求分析", RequirementAgent())
        wf.step("方案设计", DesignAgent())
        wf.step("编码实现", CodingAgent())
        wf.run(ctx)

        self.assertIn("requirements", ctx.state)
        self.assertIn("design", ctx.state)
        self.assertIn("code", ctx.state)
        validation = ctx.get("validation", {})
        self.assertEqual(validation.get("status"), "SUCCEEDED")
        self.assertTrue(validation.get("通过"))
        self.assertEqual(ctx.status_of("MiniSE"), "SUCCEEDED")

        # 消息传递：需求 -> 设计 -> 编码 均存在对应消息
        self.assertTrue(any(m.recipient == "DesignAgent" for m in ctx.messages))
        self.assertTrue(any(m.recipient == "CodingAgent" for m in ctx.messages))

        # 生成的代码真实落盘且可导入
        self.assertTrue(os.path.exists(ctx.get("code_path", "")))

        # 清理测试输出
        shutil.rmtree(out_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

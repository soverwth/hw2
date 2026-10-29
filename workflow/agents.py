"""具体 Agent 实现。

- Mini SE 流程（需求 → 设计 → 代码）：RequirementAgent / DesignAgent / CodingAgent
- 代码审查流程（审查 → 修复，循环）：ReviewAgent / FixAgent

这些 Agent 采用确定性（规则驱动）实现，无需外部大模型 API 即可运行，
充分演示了 Agent 间通过共享状态 + 消息传递进行协作的机制。
若接入真实 LLM，只需替换 ``run`` 内部实现，框架层无需改动。
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from .agent import Agent
from .context import WorkflowContext

# 操作关键字 -> (方法名, 表达式, 描述)
_OPERATION_MAP = {
    "加法": ("add", "a + b", "两个数相加"),
    "减法": ("subtract", "a - b", "两个数相减"),
    "乘法": ("multiply", "a * b", "两个数相乘"),
    "除法": ("divide", "a / b", "两个数相除"),
}

# 匹配独立的 pass 语句（整行只有 pass 及可选注释，捕获缩进）
_PASS_LINE_RE = re.compile(r"^([ \t]*)pass[ \t]*(?:#.*)?$", re.MULTILINE)
# 匹配独立的 TODO 标记（单词边界）
_TODO_RE = re.compile(r"\bTODO\b")
# 匹配 divide 方法定义
_DIVIDE_DEF_RE = re.compile(r"def\s+divide\s*\(")
# 匹配 return a / b 行（捕获缩进）
_RETURN_DIVIDE_RE = re.compile(r"^([ \t]*)return a / b[ \t]*$", re.MULTILINE)


class RequirementAgent(Agent):
    """需求 Agent：把自然语言需求整理为结构化需求。"""

    name = "RequirementAgent"

    def run(self, ctx: WorkflowContext) -> Dict[str, Any]:
        raw = ctx.get("input", "")
        sentences = [s.strip() for s in re.split(r"[。！？!?；;\n]+", raw) if s.strip()]
        overview = sentences[0] if sentences else raw.strip()

        features = []
        for kw, (method, _expr, desc) in _OPERATION_MAP.items():
            if kw in raw:
                features.append({"名称": kw, "方法": method, "描述": desc})

        constraints = []
        if any(k in raw for k in ("除零", "除数为零", "除数为0")):
            constraints.append("除数为零时必须给出明确错误提示，程序不能崩溃")

        requirements = {
            "概述": overview,
            "功能需求": features,
            "约束": constraints,
            "验收标准": [f"{f['名称']}运算结果正确" for f in features]
            + (["除零时正确提示错误"] if constraints else []),
        }
        ctx.set("requirements", requirements)
        # 显式消息传递：通知下游 Agent
        self.send(ctx, "DesignAgent", {"requirements": requirements}, msg_type="requirements")
        return requirements


class DesignAgent(Agent):
    """设计 Agent：根据结构化需求产出技术方案。"""

    name = "DesignAgent"

    def run(self, ctx: WorkflowContext) -> Dict[str, Any]:
        requirements = ctx.get("requirements", {})
        features = requirements.get("功能需求", [])
        has_divide = any(f["方法"] == "divide" for f in features)

        modules = [f"{f['方法']}() —— {f['描述']}" for f in features]
        design = {
            "架构": "单模块、无状态设计：Calculator 类封装全部运算方法，调用方无需维护内部状态",
            "模块": modules,
            "关键决策": {
                "错误处理": "除法遇到除数为零时抛出 ValueError" if has_divide else "无特殊错误处理",
                "可扩展性": "新增一种运算只需在 Calculator 类中新增一个方法，不影响既有功能",
                "数据结构": "纯函数，无共享可变状态，天然线程安全",
            },
            "类结构": "Calculator",
        }
        ctx.set("design", design)
        self.send(ctx, "CodingAgent", {"design": design}, msg_type="design")
        return design


class CodingAgent(Agent):
    """编码 Agent：根据需求与设计生成可运行的 Python 代码，并做编译 + 冒烟测试自检。"""

    name = "CodingAgent"

    def run(self, ctx: WorkflowContext) -> Dict[str, Any]:
        requirements = ctx.get("requirements", {})
        features = requirements.get("功能需求", [])

        code = self._generate_code(features)
        ctx.set("code", code)

        # 落盘到文件
        out_dir = ctx.get("output_dir", "generated")
        os.makedirs(out_dir, exist_ok=True)
        code_path = os.path.join(out_dir, "calculator.py")
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)
        ctx.set("code_path", code_path)

        # 编译 + 冒烟测试自检（端到端闭环）
        validation = self._validate(code, features)
        ctx.set("validation", validation)
        return {"code_path": code_path, "validation": validation}

    @staticmethod
    def _generate_code(features: List[Dict[str, Any]]) -> str:
        lines = [
            '"""由 CodingAgent 自动生成的 Calculator 类。"""',
            "",
            "",
            "class Calculator:",
            '    """支持加减乘除的简单计算器。"""',
            "",
        ]
        if not features:
            lines.append("    pass")
        else:
            for f in features:
                method = f["方法"]
                expr = _OPERATION_MAP[f["名称"]][1]
                desc = f["描述"]
                lines.append(f"    def {method}(self, a, b):")
                lines.append(f'        """{desc}。"""')
                if method == "divide":
                    lines.append("        if b == 0:")
                    lines.append('            raise ValueError("除数为零")')
                lines.append(f"        return {expr}")
                lines.append("")

        lines.append("")
        lines.append("if __name__ == '__main__':")
        lines.append("    calc = Calculator()")
        if any(f["方法"] == "add" for f in features):
            lines.append("    print(calc.add(1, 2))")
        else:
            lines.append("    print('Calculator 已生成')")
        return "\n".join(lines)

    @staticmethod
    def _validate(code: str, features: List[Dict[str, Any]]) -> Dict[str, Any]:
        namespace: Dict[str, Any] = {}
        try:
            exec(compile(code, "<generated>", "exec"), namespace)
        except Exception as exc:  # noqa: BLE001
            return {"status": "FAILED", "error": f"编译失败: {exc}", "通过": False}

        calc_cls = namespace.get("Calculator")
        if calc_cls is None:
            return {"status": "FAILED", "error": "未找到 Calculator 类", "通过": False}
        calc = calc_cls()

        checks = []
        passed = True
        for f in features:
            method = f["方法"]
            if method == "add":
                ok = calc.add(1, 2) == 3
                note = "1 + 2 == 3"
            elif method == "subtract":
                ok = calc.subtract(5, 3) == 2
                note = "5 - 3 == 2"
            elif method == "multiply":
                ok = calc.multiply(3, 4) == 12
                note = "3 * 4 == 12"
            elif method == "divide":
                if calc.divide(6, 3) != 2:
                    ok, note = False, "6 / 3 != 2"
                else:
                    try:
                        calc.divide(1, 0)
                        ok, note = False, "除零未报错"
                    except ValueError:
                        ok, note = True, "6 / 3 == 2，除零正确抛出 ValueError"
                    except Exception as exc:  # noqa: BLE001
                        ok, note = False, f"除零异常类型错误: {exc}"
            else:  # pragma: no cover - 防御性分支
                ok, note = True, "（无冒烟测试）"
            checks.append({"方法": method, "通过": ok, "说明": note})
            if not ok:
                passed = False

        return {"status": "SUCCEEDED" if passed else "FAILED", "通过": passed, "checks": checks}


class ReviewAgent(Agent):
    """审查 Agent：审查代码并返回问题列表。"""

    name = "ReviewAgent"

    def run(self, ctx: WorkflowContext) -> Dict[str, Any]:
        code = ctx.get("code", "")
        issues: List[str] = []
        if _TODO_RE.search(code):
            issues.append("代码中包含未完成的 TODO")
        if _PASS_LINE_RE.search(code):
            issues.append("存在空实现（pass）")
        if _DIVIDE_DEF_RE.search(code) and "ValueError" not in code:
            issues.append("除法未处理除数为零的情况")
        ctx.set("review_issues", issues)
        self.send(ctx, "FixAgent", {"issues": issues}, msg_type="review")
        return {"issues": issues}


class FixAgent(Agent):
    """修复 Agent：修复审查发现的问题。"""

    name = "FixAgent"

    def run(self, ctx: WorkflowContext) -> Dict[str, Any]:
        code = ctx.get("code", "")
        issues = list(ctx.get("review_issues", []))
        fixed: List[str] = []
        for issue in issues:
            if "TODO" in issue:
                new_code, n = _TODO_RE.subn("DONE", code)
                if n:
                    code = new_code
                    fixed.append(f"移除 TODO 标记（{n} 处）")
            if "空实现" in issue:
                new_code, n = _PASS_LINE_RE.subn(r"\1raise NotImplementedError('待补充实现')", code)
                if n:
                    code = new_code
                    fixed.append(f"空实现改为 raise NotImplementedError（{n} 处）")
            if "除数为零" in issue and "ValueError" not in code:
                new_code, n = _RETURN_DIVIDE_RE.subn(
                    r'\1if b == 0:\n\1    raise ValueError("除数为零")\n\1return a / b', code
                )
                if n:
                    code = new_code
                    fixed.append(f"补充除零校验（{n} 处）")
        ctx.set("code", code)
        # 累积修复记录，避免多轮循环中最后一轮（无问题可修时）覆盖历史
        ctx.set("fix_log", ctx.get("fix_log", []) + fixed)
        self.send(ctx, "ReviewAgent", {"fixed": fixed}, msg_type="fix")
        return {"fixed": fixed}

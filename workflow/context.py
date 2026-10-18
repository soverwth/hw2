"""工作流上下文：共享状态、消息总线、执行日志与状态追踪。

这是本 MVP 中 "状态管理" 与 "Agent 间通信" 的核心载体：

- ``state``        —— 各 Agent 共享的键值状态（状态管理）
- ``messages``     —— Agent 之间显式通信的消息列表（消息传递）
- ``node_states``  —— 每个工作流节点的执行状态（状态追踪）
- ``logs``         —— 执行日志（日志与追踪）
"""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional


class WorkflowStatus(Enum):
    """工作流节点的生命周期状态。"""

    PENDING = "PENDING"      # 尚未执行
    RUNNING = "RUNNING"      # 正在执行
    SUCCEEDED = "SUCCEEDED"  # 执行成功
    FAILED = "FAILED"        # 执行失败
    SKIPPED = "SKIPPED"      # 因条件不满足被跳过


class Message:
    """Agent 之间传递的一条消息。

    消息带有明确的发送方、接收方、类型与载荷，用于演示显式通信，
    与共享状态（``WorkflowContext.state``）互为补充。
    """

    def __init__(
        self,
        sender: str,
        recipient: str,
        payload: Optional[Dict[str, Any]] = None,
        msg_type: str = "data",
    ) -> None:
        self.sender = sender
        self.recipient = recipient
        self.payload = payload or {}
        self.msg_type = msg_type
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "type": self.msg_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

    def __repr__(self) -> str:  # pragma: no cover - 仅为调试便利
        return f"<Message {self.sender} -> {self.recipient} [{self.msg_type}]>"


class WorkflowContext:
    """工作流的共享上下文对象，贯穿整个工作流生命周期。"""

    def __init__(self, initial: Optional[Dict[str, Any]] = None) -> None:
        self.state: Dict[str, Any] = dict(initial or {})
        self.messages: List[Message] = []
        self.node_states: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []

    # ---------- 状态管理 ----------
    def set(self, key: str, value: Any) -> Any:
        """写入一个共享状态键。"""
        self.state[key] = value
        return value

    def get(self, key: str, default: Any = None) -> Any:
        """读取一个共享状态键。"""
        return self.state.get(key, default)

    def update(self, mapping: Dict[str, Any]) -> None:
        """批量更新共享状态。"""
        self.state.update(mapping)

    # ---------- 消息传递 ----------
    def send(
        self,
        sender: str,
        recipient: str,
        payload: Optional[Dict[str, Any]] = None,
        msg_type: str = "data",
    ) -> Message:
        """由 ``sender`` 向 ``recipient`` 发送一条消息。"""
        msg = Message(sender, recipient, payload, msg_type)
        self.messages.append(msg)
        return msg

    def messages_for(self, recipient: str) -> List[Message]:
        """返回发送给指定接收方（或广播 ``*``）的所有消息。"""
        return [m for m in self.messages if m.recipient in (recipient, "*")]

    def last_message_for(self, recipient: str) -> Optional[Message]:
        msgs = self.messages_for(recipient)
        return msgs[-1] if msgs else None

    # ---------- 日志与状态追踪 ----------
    def log(self, level: str, message: str, **extra: Any) -> None:
        """追加一条执行日志。"""
        entry: Dict[str, Any] = {"time": time.time(), "level": level, "message": message}
        entry.update(extra)
        self.logs.append(entry)

    def set_node_status(self, name: str, status: WorkflowStatus, **extra: Any) -> None:
        """记录某个节点的执行状态与附加信息。"""
        self.node_states[name] = {"status": status.value, **extra}

    def status_of(self, name: str) -> Optional[str]:
        rec = self.node_states.get(name)
        return rec["status"] if rec else None

    # ---------- 导出 ----------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "messages": [m.to_dict() for m in self.messages],
            "node_states": self.node_states,
            "logs": self.logs,
        }

    def dump_json(self, path: str) -> str:
        """把完整执行记录导出为 JSON 文件，便于审计与复现。"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2, default=str)
        return path

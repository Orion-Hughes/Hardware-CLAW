"""Presentation helpers for the Chainlit adapter."""
from __future__ import annotations

from typing import Callable, Optional


class ToolTimeline:
    """Group all tool calls in one turn under a collapsed Chainlit Step."""

    def __init__(
        self,
        step_factory: Callable[..., object],
        timestamp: Callable[[], str],
        root_parent_id: Optional[str] = None,
    ):
        self._step_factory = step_factory
        self._timestamp = timestamp
        self._root_parent_id = root_parent_id
        self._parent = None
        self._tools = {}
        self.requests = 0
        self.results = 0

    def get_tool(self, call_id: str):
        return self._tools.get(call_id)

    async def _ensure_parent(self):
        if self._parent is not None:
            return
        parent = self._step_factory(
            name="工具执行过程",
            type="run",
            parent_id=self._root_parent_id,
            default_open=False,
            auto_collapse=True,
            show_input=False,
        )
        parent.start = self._timestamp()
        parent.output = "正在执行工具..."
        self._parent = parent
        await parent.send()

    async def _refresh_parent(self):
        if self._parent is None:
            return
        self._parent.output = f"工具调用 {self.requests} 次，已返回 {self.results} 次"
        await self._parent.update()

    async def start_tool(self, call_id: str, name: str, args: dict):
        await self._ensure_parent()
        step = self._step_factory(
            name=name,
            type="tool",
            parent_id=self._parent.id,
            default_open=False,
            auto_collapse=True,
            show_input="json",
        )
        step.start = self._timestamp()
        step.input = args
        self._tools[call_id] = step
        self.requests += 1
        await self._refresh_parent()
        await step.send()
        return step

    async def finish_tool(self, call_id: str, content):
        step = self._tools.get(call_id)
        if step is not None:
            step.output = content
            step.end = self._timestamp()
            step.language = "json"
            await step.update()
        self.results += 1
        await self._refresh_parent()
        return step

    async def finish(self):
        if self._parent is None:
            return
        self._parent.output = f"工具执行结束：{self.requests} 次调用，{self.results} 次返回"
        self._parent.end = self._timestamp()
        self._parent.language = "text"
        await self._parent.update()

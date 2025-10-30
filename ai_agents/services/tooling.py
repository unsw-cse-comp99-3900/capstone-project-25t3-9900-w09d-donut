"""
Tool abstractions used by the AI conversation orchestrator.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class ToolExecutionError(RuntimeError):
    """Raised when a tool fails in a recoverable way."""

    def __init__(self, message: str, *, code: str = "tool_error", details: Optional[Mapping[str, object]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


@dataclass
class ToolContext:
    session_id: str
    memory_snapshot: object
    extras: Dict[str, object] = field(default_factory=dict)


@dataclass
class ToolResult:
    text: str
    citations: Iterable[str] = field(default_factory=list)
    selected_ids: Iterable[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)


@runtime_checkable
class AgentTool(Protocol):
    name: str

    def execute(self, context: ToolContext, payload: Mapping[str, object]) -> ToolResult:
        ...


class ToolRegistry:
    """Simple registry that keeps track of available tools."""

    def __init__(self) -> None:
        self._tools: MutableMapping[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.debug("Registered tool '%s'", tool.name)

    def get(self, name: str) -> AgentTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Tool '{name}' is not registered") from exc

    def execute(self, name: str, context: ToolContext, payload: Mapping[str, object]) -> ToolResult:
        tool = self.get(name)
        logger.debug("Executing tool '%s' for session '%s'", name, context.session_id)
        return tool.execute(context, payload)

    def available_tools(self) -> Mapping[str, AgentTool]:
        return dict(self._tools)

"""
backend/app/agents/tools/base_tool.py
────────────────────────────────────
Base class for all tools accessible by VARUNA autonomous agents.
Enables ReAct reasoning and dynamic autonomous tool execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional
from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[Any] = None


class BaseAgentTool(ABC):
    """
    Abstract base class for all tools that an Agent can invoke during its lifecycle.
    Provides schema definitions for LLM tool-calling (compatible with OpenAI / Anthropic / LangChain)
    and asynchronous execution.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Optional[list[ToolParameter]] = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or []

    def get_schema(self) -> dict[str, Any]:
        """Return tool declaration schema formatted for LLM function/tool calling."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description,
            }
            if param.default is not None:
                properties[param.name]["default"] = param.default
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool action asynchronously."""
        raise NotImplementedError

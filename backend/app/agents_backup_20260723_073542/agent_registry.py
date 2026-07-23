"""
app/agents/agent_registry.py
────────────────────────────
Central Agent Registry and Manager.

Design decisions:
  • AgentManager is the single coordinator. External code never touches
    individual agents directly — all execution goes through the manager.
  • Agent discovery: agents register themselves on import, not via
    configuration files. This prevents "registered but not implemented" issues.
  • The manager routes events to subscribed agents (Observer pattern).
  • Health aggregation: a single health_report() call polls all agents.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from app.agents.base_agent import AgentResult, BaseAgent
from app.core.enums import AgentName, AgentTrigger

logger = structlog.get_logger(__name__)


class AgentManager:
    """
    Singleton manager for all AI agents.
    """

    _instance: Optional["AgentManager"] = None

    def __init__(self) -> None:
        self._agents: dict[AgentName, BaseAgent] = {}

    @classmethod
    def get_instance(cls) -> "AgentManager":
        if cls._instance is None:
            cls._instance = AgentManager()
        return cls._instance

    def register(self, agent: BaseAgent) -> None:
        """Register an agent with the manager."""
        self._agents[agent.name] = agent
        logger.info("Agent registered", agent=agent.name.value)

    async def execute(
        self,
        agent_name: AgentName,
        payload: dict[str, Any] | None = None,
        trigger: AgentTrigger = AgentTrigger.MANUAL,
        triggered_by: str = "system",
    ) -> AgentResult:
        """Execute a specific agent by name."""
        agent = self._agents.get(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name.value}' is not registered.")

        return await agent.execute(
            payload=payload or {},
            trigger=trigger,
            triggered_by=triggered_by,
        )

    def health_report(self) -> list[dict[str, Any]]:
        """Return health status of all registered agents."""
        return [agent.health_status() for agent in self._agents.values()]

    def get_agent(self, name: AgentName) -> Optional[BaseAgent]:
        return self._agents.get(name)

    def list_agents(self) -> list[dict[str, Any]]:
        """Return a rich list of all registered agents with metadata."""
        return [
            {
                "name": name.value,
                "version": agent.version,
                "description": agent.description,
            }
            for name, agent in self._agents.items()
        ]


def get_agent_manager() -> AgentManager:
    """Dependency / accessor for the singleton AgentManager."""
    return AgentManager.get_instance()


# Alias for symmetry with get_model_registry()
def get_agent_registry() -> AgentManager:
    """Alias for get_agent_manager() — used by agents_router and tasks."""
    return AgentManager.get_instance()

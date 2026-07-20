"""
app/services/interfaces/twin_service.py
───────────────────────────────────────
Interface for the Digital Twin service.
"""

from abc import ABC, abstractmethod
import uuid
from typing import Optional

from app.core.enums import District
from app.models.digital_twin import Simulation, TwinState
from app.schemas.digital_twin import SimulationCreateRequest


class ITwinService(ABC):
    """Abstract interface for Digital Twin business logic."""

    @abstractmethod
    async def get_current_state(self, district: District) -> TwinState:
        """Fetch the latest state for a district. Creates one if none exists."""
        pass

    @abstractmethod
    async def synchronize_state(self, district: District) -> TwinState:
        """Force a synchronization of the twin state with the latest real-world data."""
        pass

    @abstractmethod
    async def create_simulation(
        self, request: SimulationCreateRequest, created_by: Optional[uuid.UUID]
    ) -> Simulation:
        """Create a new what-if simulation scenario."""
        pass

    @abstractmethod
    async def run_simulation(self, simulation_id: uuid.UUID) -> Simulation:
        """Execute a pending simulation scenario."""
        pass

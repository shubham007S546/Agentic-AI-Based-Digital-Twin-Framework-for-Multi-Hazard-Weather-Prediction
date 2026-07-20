"""
app/repositories/interfaces/twin_repo.py
────────────────────────────────────────
Interface for the Digital Twin repository.
"""

from abc import ABC, abstractmethod
from typing import Optional
import uuid

from app.core.enums import District
from app.models.digital_twin import Simulation, TwinState


class ITwinRepository(ABC):
    """Abstract interface for Digital Twin data access."""

    # ── Twin States ───────────────────────────────────────────────────────────
    
    @abstractmethod
    async def get_latest_state(self, district: District) -> Optional[TwinState]:
        """Fetch the most recent TwinState for a district."""
        pass

    @abstractmethod
    async def create_state(self, state: TwinState) -> TwinState:
        """Create a new TwinState record, automatically un-flagging older states as latest."""
        pass

    # ── Simulations ───────────────────────────────────────────────────────────

    @abstractmethod
    async def get_simulation(self, simulation_id: uuid.UUID) -> Optional[Simulation]:
        """Fetch a specific Simulation by ID."""
        pass

    @abstractmethod
    async def create_simulation(self, simulation: Simulation) -> Simulation:
        """Create a new Simulation record."""
        pass

    @abstractmethod
    async def update_simulation(self, simulation: Simulation) -> Simulation:
        """Update an existing Simulation record."""
        pass

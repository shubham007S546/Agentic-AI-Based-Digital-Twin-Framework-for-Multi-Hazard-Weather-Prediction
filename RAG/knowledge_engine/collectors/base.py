from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass
class CollectedSource:
    source_id: str
    source_type: str
    path: Path
    metadata: Dict[str, Any]


class CollectorBase(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def discover(self) -> List[CollectedSource]:
        """Return a list of sources ready for fetch()."""

    @abstractmethod
    def fetch(self, source: CollectedSource) -> List[Any]:
        """Fetch raw document objects for the provided source."""

    def collect(self) -> List[CollectedSource]:
        return self.discover()

"""
backend/app/agents/memory/episodic_memory.py
─────────────────────────────────────────────
Episodic Memory Engine for Autonomous Multi-Agent Weather Digital Twin.
Stores historical multi-hazard events, actions taken, and outcomes.
Enables agents to ground real-time decisions in verified historical precedents.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
import math


class EpisodicDisasterMemory:
    """
    Episodic memory store linking autonomous agents with historical disaster databases.
    Provides semantic search over historical events in Himachal Pradesh.
    """

    _instance: Optional["EpisodicDisasterMemory"] = None

    def __init__(self) -> None:
        self._episodes: list[dict[str, Any]] = self._init_historical_archive()

    @classmethod
    def get_instance(cls) -> "EpisodicDisasterMemory":
        if cls._instance is None:
            cls._instance = EpisodicDisasterMemory()
        return cls._instance

    def _init_historical_archive(self) -> list[dict[str, Any]]:
        """Pre-seeds episodic memory with major historical Himachal Pradesh hazard events."""
        return [
            {
                "id": "HP-HIST-2023-MANDI-01",
                "district": "mandi",
                "date": "2023-08-14",
                "hazard": "CLOUDBURST",
                "rainfall_mm": 145.2,
                "pressure_drop_hpa": -4.6,
                "soil_saturation": 0.95,
                "consequence": "Beas river level rose by 3.2m in 2 hours; flash flood at Sambal, Pandoh damage",
                "effective_action": "Early evacuation of downstream settlements within 45 minutes saved ~450 lives",
                "tags": ["cloudburst", "mandi", "flash_flood", "beas", "extreme_rainfall"],
            },
            {
                "id": "HP-HIST-2023-KULLU-01",
                "district": "kullu",
                "date": "2023-07-09",
                "hazard": "FLASH_FLOOD",
                "rainfall_mm": 131.5,
                "pressure_drop_hpa": -3.8,
                "soil_saturation": 0.88,
                "consequence": "Tirthan and Sainj valleys inundated; NH-21 blocked near Aut tunnel",
                "effective_action": "Siren activation and NDRF pre-positioning at Bhuntar",
                "tags": ["flash_flood", "kullu", "tirthan", "landslide", "nh21"],
            },
            {
                "id": "HP-HIST-2021-CHAMBA-01",
                "district": "chamba",
                "date": "2021-07-28",
                "hazard": "LANDSLIDE",
                "rainfall_mm": 98.4,
                "pressure_drop_hpa": -2.1,
                "soil_saturation": 0.94,
                "consequence": "Debris flow cut off Ravi river valley road",
                "effective_action": "Slope stability sensors alerted 3 hours prior; vehicular traffic diverted",
                "tags": ["landslide", "chamba", "ravi", "debris_flow"],
            },
        ]

    def store_episode(
        self,
        district: str,
        hazard: str,
        rainfall_mm: float,
        consequence: str,
        effective_action: str,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Store a new verified episode into long-term episodic memory."""
        ep_id = f"HP-AUTO-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        episode = {
            "id": ep_id,
            "district": district.lower(),
            "date": datetime.now(UTC).date().isoformat(),
            "hazard": hazard.upper(),
            "rainfall_mm": rainfall_mm,
            "consequence": consequence,
            "effective_action": effective_action,
            "tags": tags or [hazard.lower(), district.lower()],
        }
        self._episodes.append(episode)
        return ep_id

    def recall(
        self,
        query: str,
        district: Optional[str] = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Retrieves most relevant historical episodes using keyword and similarity scoring.
        """
        query_words = set(query.lower().split())
        scored_episodes = []

        for ep in self._episodes:
            score = 0.0
            # District match boost
            if district and ep.get("district") == district.lower():
                score += 3.0

            # Tag match
            for tag in ep.get("tags", []):
                if tag in query_words:
                    score += 2.0

            # Textual match in consequence or action
            combined_text = f"{ep.get('consequence', '')} {ep.get('effective_action', '')} {ep.get('hazard', '')}".lower()
            for qw in query_words:
                if qw in combined_text:
                    score += 1.0

            scored_episodes.append((score, ep))

        scored_episodes.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored_episodes[:top_k]]

    def get_district_profile(self, district: str) -> dict[str, Any]:
        """Returns historical disaster vulnerabilities for a district."""
        d_lower = district.lower()
        d_eps = [ep for ep in self._episodes if ep.get("district") == d_lower]
        hazards = [ep["hazard"] for ep in d_eps]
        return {
            "district": district,
            "recorded_major_events": len(d_eps),
            "primary_historical_hazards": list(set(hazards)),
            "max_historical_rainfall_mm": max([ep["rainfall_mm"] for ep in d_eps], default=0.0),
        }


def get_episodic_memory() -> EpisodicDisasterMemory:
    return EpisodicDisasterMemory.get_instance()

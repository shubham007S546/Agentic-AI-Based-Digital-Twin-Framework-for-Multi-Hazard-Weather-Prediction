import re
from typing import Dict, List, Optional


class HazardIdentifier:
    HAZARD_MAP = {
        "flood": [r"\bflood\b", r"\bflooding\b", r"\bflash flood\b"],
        "drought": [r"\bdrought\b", r"\bwater scarcity\b"],
        "landslide": [r"\blandslide\b", r"\bland slide\b"],
        "storm": [r"\bstorm\b", r"\bstorm surge\b", r"\btropical cyclone\b"],
        "heatwave": [r"\bheat wave\b", r"\bheatwave\b"],
        "coldwave": [r"\bcold wave\b", r"\bcoldwave\b"],
        "earthquake": [r"\bearthquake\b", r"\bseismic\b", r"\baftershock\b"],
        "wildfire": [r"\bwildfire\b", r"\bforest fire\b", r"\bfirestorm\b"],
        "hail": [r"\bhail\b", r"\bhailstorm\b"],
        "cyclone": [r"\bcyclone\b", r"\btyphoon\b", r"\bhurricane\b"],
    }

    def identify(self, text: str) -> Optional[str]:
        if not text:
            return None

        lower_text = text.lower()
        for hazard, patterns in self.HAZARD_MAP.items():
            for pattern in patterns:
                if re.search(pattern, lower_text):
                    return hazard
        return None

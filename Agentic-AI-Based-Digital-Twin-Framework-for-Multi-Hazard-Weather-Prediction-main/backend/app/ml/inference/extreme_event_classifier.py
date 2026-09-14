"""
backend/app/ml/inference/extreme_event_classifier.py
────────────────────────────────────────────────────────────────────
IMD-Standard Extreme Weather Event Classification

Implements India Meteorological Department (IMD) thresholds for:
  - Rainfall classification (Normal / Heavy / Very Heavy / Extremely Heavy)
  - Cloudburst detection (≥100mm/hr or ≥50mm/30min IMD definition)
  - Landslide risk composite scoring (antecedent + slope + saturation)
  - Flash flood inundation risk (gauge + basin saturation + forecast)

These thresholds are based on:
  - IMD Colour Coded Warnings guidelines (2021)
  - National Disaster Management Authority (NDMA) protocols
  - Himalayan Cloudburst Database (NIDM, IIT Roorkee 2020)

Reference: IMD Rainfall Classification
  - No Rain        : < 2.4 mm / 24h
  - Light Rain     : 2.5 - 15.5 mm / 24h
  - Moderate Rain  : 15.6 - 64.4 mm / 24h
  - Heavy Rain     : 64.5 - 115.5 mm / 24h      [Yellow Watch]
  - Very Heavy Rain: 115.6 - 204.4 mm / 24h     [Orange Warning]
  - Extremely Heavy: ≥ 204.5 mm / 24h            [Red Alert]
  - Cloudburst     : ≥ 100 mm / 1 hour            [Red Alert + Special]
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# IMD Rainfall Category Enum
# ═══════════════════════════════════════════════════════════════════════════════

class IMDCategory(str, Enum):
    NO_RAIN = "no_rain"
    LIGHT = "light_rain"
    MODERATE = "moderate_rain"
    HEAVY = "heavy_rain"           # Yellow Watch
    VERY_HEAVY = "very_heavy_rain" # Orange Warning
    EXTREMELY_HEAVY = "extremely_heavy_rain"  # Red Alert
    CLOUDBURST = "cloudburst"      # Red Alert + Cloudburst Advisory


class IMDColorCode(str, Enum):
    GREEN = "green"   # No warning needed
    YELLOW = "yellow"  # Watch — be aware
    ORANGE = "orange"  # Warning — be prepared
    RED = "red"        # Alert — take action


# ═══════════════════════════════════════════════════════════════════════════════
# Result dataclasses
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RainfallClassification:
    category: IMDCategory
    color_code: IMDColorCode
    is_extreme: bool
    threshold_description: str
    action_recommended: str
    rainfall_mm_24h: float


@dataclass
class CloudburstAssessment:
    is_cloudburst: bool
    probability: float          # 0.0 - 1.0
    trigger_condition: str
    rainfall_rate_mm_hr: float  # estimated mm/hr rate
    confidence: float           # 0.0 - 1.0
    explanation: str


@dataclass
class LandslideRiskAssessment:
    risk_score: float            # 0.0 - 1.0
    risk_level: str              # low / moderate / high / severe
    is_critical: bool
    contributing_factors: list[str]
    slope_susceptibility: float  # 0.0 - 1.0
    soil_saturation_pct: float   # 0 - 100


@dataclass
class FloodInundationRisk:
    risk_level: str              # low / moderate / high / severe
    is_critical: bool
    gauge_utilization_pct: float  # level / danger_level * 100
    time_to_danger_hours: Optional[float]
    basin_saturation_pct: float
    explanation: str


# ═══════════════════════════════════════════════════════════════════════════════
# IMD Rainfall Classifier
# ═══════════════════════════════════════════════════════════════════════════════

def classify_rainfall_imd(rainfall_mm_24h: float) -> RainfallClassification:
    """
    Classify rainfall using IMD standard thresholds.
    
    Args:
        rainfall_mm_24h: Total rainfall in mm over 24 hours.
    
    Returns:
        RainfallClassification with IMD category, color code, and recommended actions.
    """
    r = max(0.0, float(rainfall_mm_24h))

    if r < 2.4:
        return RainfallClassification(
            category=IMDCategory.NO_RAIN,
            color_code=IMDColorCode.GREEN,
            is_extreme=False,
            threshold_description="< 2.4 mm/24h",
            action_recommended="No action required. Monitor regularly.",
            rainfall_mm_24h=r,
        )
    elif r <= 15.5:
        return RainfallClassification(
            category=IMDCategory.LIGHT,
            color_code=IMDColorCode.GREEN,
            is_extreme=False,
            threshold_description="2.5 - 15.5 mm/24h",
            action_recommended="No warning. Normal monsoon activity.",
            rainfall_mm_24h=r,
        )
    elif r <= 64.4:
        return RainfallClassification(
            category=IMDCategory.MODERATE,
            color_code=IMDColorCode.GREEN,
            is_extreme=False,
            threshold_description="15.6 - 64.4 mm/24h",
            action_recommended="Monitor road conditions in hilly areas.",
            rainfall_mm_24h=r,
        )
    elif r <= 115.5:
        return RainfallClassification(
            category=IMDCategory.HEAVY,
            color_code=IMDColorCode.YELLOW,
            is_extreme=True,
            threshold_description="64.5 - 115.5 mm/24h (IMD Heavy Rain)",
            action_recommended="Yellow Watch: Be aware. Restrict non-essential travel on mountain roads.",
            rainfall_mm_24h=r,
        )
    elif r <= 204.4:
        return RainfallClassification(
            category=IMDCategory.VERY_HEAVY,
            color_code=IMDColorCode.ORANGE,
            is_extreme=True,
            threshold_description="115.6 - 204.4 mm/24h (IMD Very Heavy Rain)",
            action_recommended="Orange Warning: Be prepared. Evacuate flood-prone areas. Close hill roads.",
            rainfall_mm_24h=r,
        )
    else:
        return RainfallClassification(
            category=IMDCategory.EXTREMELY_HEAVY,
            color_code=IMDColorCode.RED,
            is_extreme=True,
            threshold_description=">= 204.5 mm/24h (IMD Extremely Heavy Rain - Red Alert)",
            action_recommended="RED ALERT: Take action immediately. Evacuate. Deploy NDRF/SDRF.",
            rainfall_mm_24h=r,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Cloudburst Detector
# ═══════════════════════════════════════════════════════════════════════════════

def assess_cloudburst_risk(
    rainfall_mm_1h: float,
    cape_j_kg: float = 0.0,
    wind_shear_m_s: float = 0.0,
    cloud_top_cooling_k_15min: float = 0.0,
    relative_humidity_pct: float = 70.0,
) -> CloudburstAssessment:
    """
    Assess cloudburst probability using IMD definition + convective parameters.
    
    IMD Cloudburst: ≥ 100mm of rain in 1 hour over a limited area (< 20 km²)
    
    Args:
        rainfall_mm_1h: Current hourly rainfall in mm.
        cape_j_kg: Convective Available Potential Energy (CAPE) in J/kg.
        wind_shear_m_s: 0-6km wind shear in m/s.
        cloud_top_cooling_k_15min: Rate of cloud-top temperature drop (K per 15min).
        relative_humidity_pct: Relative humidity at 850 hPa level.
    
    Returns:
        CloudburstAssessment with probability and trigger explanation.
    """
    # Direct IMD threshold check
    is_cloudburst = rainfall_mm_1h >= 100.0
    trigger = ""
    factors = []
    
    # Base probability from rainfall rate
    if rainfall_mm_1h >= 100:
        prob_from_rain = 0.95
        trigger = f"ACTIVE: {rainfall_mm_1h:.1f}mm/hr meets IMD cloudburst threshold (>=100mm/hr)"
        factors.append(f"Hourly rainfall {rainfall_mm_1h:.1f}mm >= 100mm (IMD definition)")
    elif rainfall_mm_1h >= 75:
        prob_from_rain = 0.80
        trigger = f"Near-threshold: {rainfall_mm_1h:.1f}mm/hr (threshold is 100mm/hr)"
        factors.append(f"Hourly rainfall {rainfall_mm_1h:.1f}mm approaching IMD threshold")
    elif rainfall_mm_1h >= 50:
        prob_from_rain = 0.55
        trigger = f"Elevated risk: {rainfall_mm_1h:.1f}mm/hr"
        factors.append(f"Hourly rainfall elevated at {rainfall_mm_1h:.1f}mm")
    elif rainfall_mm_1h >= 20:
        prob_from_rain = 0.25
        trigger = f"Moderate risk: {rainfall_mm_1h:.1f}mm/hr"
        factors.append(f"Hourly rainfall {rainfall_mm_1h:.1f}mm")
    else:
        prob_from_rain = max(0.05, rainfall_mm_1h / 100.0 * 0.2)
        trigger = f"Low risk: {rainfall_mm_1h:.1f}mm/hr"
    
    # CAPE contribution (CAPE > 1500 J/kg = significant convection)
    cape_factor = 0.0
    if cape_j_kg >= 3000:
        cape_factor = 0.20
        factors.append(f"Extremely unstable atmosphere (CAPE={cape_j_kg:.0f} J/kg >= 3000)")
    elif cape_j_kg >= 1500:
        cape_factor = 0.12
        factors.append(f"Strongly unstable atmosphere (CAPE={cape_j_kg:.0f} J/kg >= 1500)")
    elif cape_j_kg >= 800:
        cape_factor = 0.06
        factors.append(f"Moderately unstable (CAPE={cape_j_kg:.0f} J/kg)")
    
    # Wind shear contribution (>10 m/s favors organized convection)
    shear_factor = 0.0
    if wind_shear_m_s >= 15:
        shear_factor = 0.10
        factors.append(f"Strong wind shear ({wind_shear_m_s:.1f} m/s >= 15) - supercell risk")
    elif wind_shear_m_s >= 10:
        shear_factor = 0.06
        factors.append(f"Moderate wind shear ({wind_shear_m_s:.1f} m/s >= 10)")
    
    # Cloud-top cooling (rapid glaciation = explosive convection)
    cooling_factor = 0.0
    if cloud_top_cooling_k_15min >= 10:
        cooling_factor = 0.10
        factors.append(f"Rapid cloud-top cooling ({cloud_top_cooling_k_15min:.1f} K/15min) - rapid intensification")
    elif cloud_top_cooling_k_15min >= 6:
        cooling_factor = 0.05
        factors.append(f"Significant cloud-top cooling ({cloud_top_cooling_k_15min:.1f} K/15min)")
    
    # Humidity contribution
    humidity_factor = 0.0
    if relative_humidity_pct >= 90:
        humidity_factor = 0.08
        factors.append(f"Near-saturated atmosphere (RH={relative_humidity_pct:.0f}%)")
    elif relative_humidity_pct >= 80:
        humidity_factor = 0.04
    
    total_prob = min(0.99, prob_from_rain + cape_factor + shear_factor + cooling_factor + humidity_factor)
    
    # Determine confidence based on data quality
    confidence = 0.65
    if cape_j_kg > 0 and wind_shear_m_s > 0:
        confidence = 0.80
    if cloud_top_cooling_k_15min > 0:
        confidence = 0.88
    
    explanation = (
        f"{trigger}. " + 
        (f"Convective factors: {', '.join(factors[1:])}" if len(factors) > 1 else "No significant convective enhancement detected.")
    )
    
    return CloudburstAssessment(
        is_cloudburst=is_cloudburst,
        probability=round(total_prob, 3),
        trigger_condition=trigger,
        rainfall_rate_mm_hr=rainfall_mm_1h,
        confidence=confidence,
        explanation=explanation,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Landslide Risk Assessment
# ═══════════════════════════════════════════════════════════════════════════════

def assess_landslide_risk(
    current_rainfall_mm: float,
    antecedent_rainfall_3d_mm: float = 0.0,
    antecedent_rainfall_7d_mm: float = 0.0,
    soil_saturation_pct: float = 60.0,
    slope_angle_deg: float = 30.0,
    district: str = "Mandi",
) -> LandslideRiskAssessment:
    """
    Composite landslide risk assessment based on:
    - Himalayan Cloudburst Database thresholds (IIT Roorkee)
    - Antecedent rainfall accumulation (3d + 7d memory)
    - Terrain susceptibility (slope angle)
    - Soil saturation proxy

    Landslide triggering thresholds for Himalayan terrain (after Guzzetti et al., 2008
    adapted for HP by NIDM):
        - Moderate: >50mm in 24h + antecedent >100mm/7d
        - High: >75mm in 24h OR antecedent >200mm/7d
        - Severe: >100mm in 24h + soil saturation >85%
    """
    factors = []
    
    # Slope susceptibility (higher slope = higher susceptibility)
    if slope_angle_deg >= 45:
        slope_susc = 0.95
        factors.append(f"Very steep slope ({slope_angle_deg:.0f}°) — extreme susceptibility")
    elif slope_angle_deg >= 35:
        slope_susc = 0.80
        factors.append(f"Steep slope ({slope_angle_deg:.0f}°)")
    elif slope_angle_deg >= 25:
        slope_susc = 0.60
        factors.append(f"Moderate slope ({slope_angle_deg:.0f}°)")
    elif slope_angle_deg >= 15:
        slope_susc = 0.35
    else:
        slope_susc = 0.15
    
    # Rainfall triggering component
    rain_score = 0.0
    if current_rainfall_mm >= 100:
        rain_score = 0.85
        factors.append(f"Extreme rainfall {current_rainfall_mm:.1f}mm — direct trigger threshold exceeded")
    elif current_rainfall_mm >= 75:
        rain_score = 0.70
        factors.append(f"Very heavy rainfall {current_rainfall_mm:.1f}mm")
    elif current_rainfall_mm >= 50:
        rain_score = 0.50
        factors.append(f"Heavy rainfall {current_rainfall_mm:.1f}mm")
    elif current_rainfall_mm >= 25:
        rain_score = 0.30
    else:
        rain_score = current_rainfall_mm / 25.0 * 0.20
    
    # Antecedent rainfall contribution (3d)
    if antecedent_rainfall_3d_mm >= 150:
        antecedent_factor = 0.25
        factors.append(f"High 3-day antecedent rainfall ({antecedent_rainfall_3d_mm:.0f}mm)")
    elif antecedent_rainfall_3d_mm >= 75:
        antecedent_factor = 0.15
        factors.append(f"Moderate 3-day antecedent rainfall ({antecedent_rainfall_3d_mm:.0f}mm)")
    elif antecedent_rainfall_3d_mm >= 30:
        antecedent_factor = 0.08
    else:
        antecedent_factor = 0.02
    
    # Antecedent rainfall (7d) contribution
    if antecedent_rainfall_7d_mm >= 300:
        antecedent_7d_factor = 0.15
        factors.append(f"Heavy 7-day cumulative rainfall ({antecedent_rainfall_7d_mm:.0f}mm)")
    elif antecedent_rainfall_7d_mm >= 150:
        antecedent_7d_factor = 0.08
    else:
        antecedent_7d_factor = 0.03
    
    # Soil saturation
    sat = max(0.0, min(100.0, float(soil_saturation_pct)))
    if sat >= 90:
        sat_factor = 0.20
        factors.append(f"Near-saturated soil ({sat:.0f}%)")
    elif sat >= 80:
        sat_factor = 0.14
        factors.append(f"High soil saturation ({sat:.0f}%)")
    elif sat >= 70:
        sat_factor = 0.08
    else:
        sat_factor = sat / 100.0 * 0.06
    
    # HP district-specific vulnerability modifier
    district_modifier = {
        "Mandi": 1.15,   # Kotrupi, Hanogi — historically most landslide-prone
        "Kullu": 1.10,   # Banala, Aut tunnel areas
        "Chamba": 1.05,  # Chamba bypass
        "Shimla": 1.08,  # Nigulsari, Solan
        "Kangra": 0.95,
    }.get(district, 1.0)
    
    # Composite risk score
    raw_score = (
        slope_susc * 0.30 +
        rain_score * 0.35 +
        antecedent_factor +
        antecedent_7d_factor +
        sat_factor
    )
    risk_score = min(0.99, raw_score * district_modifier)
    
    # Risk level mapping
    if risk_score >= 0.78:
        risk_level = "severe"
        is_critical = True
    elif risk_score >= 0.58:
        risk_level = "high"
        is_critical = True
    elif risk_score >= 0.35:
        risk_level = "moderate"
        is_critical = False
    else:
        risk_level = "low"
        is_critical = False
    
    return LandslideRiskAssessment(
        risk_score=round(risk_score, 3),
        risk_level=risk_level,
        is_critical=is_critical,
        contributing_factors=factors or ["No significant triggering conditions detected"],
        slope_susceptibility=round(slope_susc, 2),
        soil_saturation_pct=sat,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Flood Inundation Risk
# ═══════════════════════════════════════════════════════════════════════════════

def assess_flood_risk(
    current_gauge_level_m: float,
    danger_level_m: float,
    discharge_m3_s: float = 0.0,
    basin_soil_saturation_pct: float = 70.0,
    upstream_rainfall_mm: float = 0.0,
    trend: str = "steady",  # "rising", "steady", "falling"
) -> FloodInundationRisk:
    """
    Assess flash flood / river flood inundation risk from gauge data.
    
    Based on India NDMA/CWC flood watch methodology.
    """
    # Gauge utilization
    util_pct = min(100.0, (current_gauge_level_m / max(0.1, danger_level_m)) * 100.0)
    
    factors = []
    time_to_danger: Optional[float] = None
    
    if util_pct >= 100:
        factors.append(f"CRITICAL: River level {current_gauge_level_m:.1f}m has exceeded danger level {danger_level_m:.1f}m")
        risk_level = "severe"
        is_critical = True
    elif util_pct >= 90:
        risk_level = "severe"
        is_critical = True
        factors.append(f"Near-danger: Level {current_gauge_level_m:.1f}m at {util_pct:.0f}% of danger mark ({danger_level_m:.1f}m)")
        # Rough time to danger: based on trend and buffer remaining
        if trend == "rising":
            buffer_m = danger_level_m - current_gauge_level_m
            time_to_danger = max(0.5, buffer_m / 0.5)  # assume 0.5m/h rise rate
    elif util_pct >= 75:
        risk_level = "high"
        is_critical = True
        factors.append(f"High utilization: Level at {util_pct:.0f}% of danger mark")
        if trend == "rising":
            buffer_m = danger_level_m - current_gauge_level_m
            time_to_danger = max(2.0, buffer_m / 0.3)
    elif util_pct >= 50:
        risk_level = "moderate"
        is_critical = False
        factors.append(f"Watch: Level at {util_pct:.0f}% of danger mark")
    else:
        risk_level = "low"
        is_critical = False
    
    # Soil saturation amplification
    if basin_soil_saturation_pct >= 90 and risk_level in ("low", "moderate"):
        risk_level = "high" if risk_level == "moderate" else "moderate"
        factors.append(f"Near-saturated basin ({basin_soil_saturation_pct:.0f}%) amplifies runoff")
        is_critical = risk_level in ("high", "severe")
    elif basin_soil_saturation_pct >= 80:
        factors.append(f"High basin saturation ({basin_soil_saturation_pct:.0f}%) — enhanced runoff")
    
    # Upstream rainfall amplification  
    if upstream_rainfall_mm >= 75:
        factors.append(f"Heavy upstream rainfall ({upstream_rainfall_mm:.1f}mm) will increase downstream discharge in 2-6h")
    elif upstream_rainfall_mm >= 40:
        factors.append(f"Moderate upstream rainfall ({upstream_rainfall_mm:.1f}mm) — monitor for level rise")
    
    # Trend modifiers
    if trend == "rising":
        factors.append("River is RISING — level increasing")
    elif trend == "falling":
        if risk_level == "severe":
            factors.append("Level falling but still above danger — maintain watch")
    
    explanation = " | ".join(factors) if factors else "Normal conditions"
    
    return FloodInundationRisk(
        risk_level=risk_level,
        is_critical=is_critical,
        gauge_utilization_pct=round(util_pct, 1),
        time_to_danger_hours=round(time_to_danger, 1) if time_to_danger else None,
        basin_saturation_pct=basin_soil_saturation_pct,
        explanation=explanation,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience dict formatter for API responses
# ═══════════════════════════════════════════════════════════════════════════════

def format_imd_classification_for_api(classification: RainfallClassification) -> dict:
    return {
        "imd_category": classification.category.value,
        "imd_color_code": classification.color_code.value,
        "is_extreme_event": classification.is_extreme,
        "threshold_description": classification.threshold_description,
        "action_recommended": classification.action_recommended,
        "rainfall_mm_24h": classification.rainfall_mm_24h,
    }

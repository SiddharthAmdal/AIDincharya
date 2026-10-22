"""
Synthetic Wearable Telemetry Stream Test Suite
==============================================
Validates Perception, Anomaly Thresholds, and Closed-Loop Schedule Adaptations
against realistic multi-day time-series sensor streams (Apple Watch, Oura, Whoop).

Covers:
1. Normal Healthy Baselines (Equilibrium / No Vikriti)
2. Multi-Day Vata Degradation Stream (Declining HRV + Fragmented Sleep)
3. Acute Pitta Inflammatory Surge (Nocturnal Tachycardia + Low HRV)
4. Kapha Sluggish / Hypometabolic Stream (Oversleeping + Bradycardia)
5. Acute Nocturnal Fever Spike (Temperature Jump > 37.8C)
6. Dual-Dosha Aggravation (Simultaneous Vata-Pitta Collapse)
7. Extreme Sensor Noise, Boundary Conditions, and Missing Fields
8. End-to-End Closed-Loop Safety Adaptation (Fever strips Abhyanga)
9. Adaptive Behavior Complexity Modulation under Telemetry Stress
"""

import time
import pytest
from src.perception.dosha_mapper import DoshaMapper
from src.models import (
    DoshaProfile, DoshaVector, VikritiFlags, UserContext,
    Practice, DinacharyaSchedule
)
from src.safety.guardrails import ClinicalRuleEngine
from src.behavior.tracker import AdherenceTracker


class TestSyntheticWearableStreams:
    """Simulates rolling 7-day and real-time wearable sensor data streams."""

    def test_stream_normal_healthy_equilibrium(self):
        """Verify that a healthy, balanced wearable stream produces zero Vikriti flags."""
        healthy_stream = {
            "hrv_ms": 68.0,
            "resting_hr": 64.0,
            "sleep_hours": 7.8,
            "sleep_efficiency": 0.92,
            "body_temp_c": 36.6
        }
        flags = DoshaMapper.detect_vikriti(healthy_stream)
        assert flags.vata_aggravated is False
        assert flags.pitta_aggravated is False
        assert flags.kapha_aggravated is False
        assert flags.has_fever is False

    def test_stream_vata_aggravation_drop_trajectory(self):
        """Simulate a 3-day stress trajectory where HRV drops and sleep degrades, triggering Vata."""
        day1 = {"hrv_ms": 58.0, "resting_hr": 66.0, "sleep_hours": 7.2}
        day2 = {"hrv_ms": 46.0, "resting_hr": 68.0, "sleep_hours": 6.3}
        day3 = {"hrv_ms": 32.0, "resting_hr": 71.0, "sleep_hours": 5.1}

        # Day 1: Balanced
        f1 = DoshaMapper.detect_vikriti(day1)
        assert f1.vata_aggravated is False

        # Day 2: Borderline, still balanced
        f2 = DoshaMapper.detect_vikriti(day2)
        assert f2.vata_aggravated is False

        # Day 3: Breaches threshold (HRV < 45 and Sleep < 6.2)
        f3 = DoshaMapper.detect_vikriti(day3)
        assert f3.vata_aggravated is True
        assert f3.pitta_aggravated is False
        assert f3.kapha_aggravated is False

    def test_stream_pitta_inflammatory_surge(self):
        """Simulate high physical exertion or inflammatory surge: elevated RHR (>82 bpm) + depressed HRV (<45 ms)."""
        pitta_stream = {
            "hrv_ms": 38.5,
            "resting_hr": 86.0,
            "sleep_hours": 6.8,
            "body_temp_c": 37.1
        }
        flags = DoshaMapper.detect_vikriti(pitta_stream)
        assert flags.pitta_aggravated is True
        assert flags.vata_aggravated is False
        assert flags.kapha_aggravated is False
        assert flags.has_fever is False

    def test_stream_kapha_sluggish_hypometabolic(self):
        """Simulate sluggish metabolic state: prolonged sleep (>9h) with low resting heart rate (<55 bpm)."""
        kapha_stream = {
            "hrv_ms": 62.0,
            "resting_hr": 51.0,
            "sleep_hours": 9.8,
            "body_temp_c": 36.4
        }
        flags = DoshaMapper.detect_vikriti(kapha_stream)
        assert flags.kapha_aggravated is True
        assert flags.vata_aggravated is False
        assert flags.pitta_aggravated is False
        assert flags.has_fever is False

    def test_stream_nocturnal_fever_spike(self):
        """Simulate acute nocturnal fever onset (>37.8C) flagged from dermal temperature sensors."""
        fever_stream = {
            "hrv_ms": 42.0,
            "resting_hr": 84.0,
            "sleep_hours": 6.0,
            "body_temp_c": 38.6
        }
        flags = DoshaMapper.detect_vikriti(fever_stream)
        assert flags.has_fever is True

    def test_stream_dual_aggravation_vata_and_pitta(self):
        """Simulate severe systemic burnout: low HRV (<45), low sleep (<6.2), and elevated RHR (>82)."""
        burnout_stream = {
            "hrv_ms": 28.0,
            "resting_hr": 89.0,
            "sleep_hours": 4.5,
            "body_temp_c": 37.2
        }
        flags = DoshaMapper.detect_vikriti(burnout_stream)
        assert flags.vata_aggravated is True
        assert flags.pitta_aggravated is True
        assert flags.kapha_aggravated is False
        assert flags.has_fever is False

    def test_stream_extreme_sensor_noise_and_boundary_resilience(self):
        """Verify the perception mapper never crashes on extreme sensor noise or missing telemetry fields."""
        # 1. Empty telemetry dict
        f_empty = DoshaMapper.detect_vikriti({})
        assert f_empty.vata_aggravated is False

        # 2. None input
        f_none = DoshaMapper.detect_vikriti(None)
        assert f_none.vata_aggravated is False

        # 3. Partial telemetry (only HRV provided)
        f_partial = DoshaMapper.detect_vikriti({"hrv_ms": 20.0})
        # Sleep defaults to 7.5, so Vata is not triggered (needs sleep < 6.2)
        assert f_partial.vata_aggravated is False

        # 4. Zero sleep (All-nighter) with low HRV
        f_allnighter = DoshaMapper.detect_vikriti({"hrv_ms": 30.0, "sleep_hours": 0.0})
        assert f_allnighter.vata_aggravated is True

        # 5. Extreme fever reading (Hyperpyrexia 41.2C)
        f_extreme_fever = DoshaMapper.detect_vikriti({"body_temp_c": 41.2})
        assert f_extreme_fever.has_fever is True

    def test_stream_end_to_end_closed_loop_fever_override(self):
        """
        Verify the full closed-loop chain:
        Sensor Telemetry (38.8C) -> Perception Mapper -> DoshaProfile -> Clinical Safety Engine -> Routine Sanitization.
        """
        telemetry = {
            "hrv_ms": 36.0,
            "resting_hr": 88.0,
            "sleep_hours": 5.4,
            "body_temp_c": 38.8
        }
        # 1. Perception Layer
        profile = DoshaMapper.generate_profile(
            user_id="wearable_stream_user_1",
            questionnaire={"frame": "thin", "mind": "quick"},
            telemetry=telemetry,
            symptoms={}
        )
        assert profile.vikriti_flags.has_fever is True
        assert profile.vikriti_flags.vata_aggravated is True

        # 2. Candidate schedule with contraindicated oil massage
        candidate = DinacharyaSchedule(
            user_id="wearable_stream_user_1",
            adherence_score=1.0,
            routine_complexity="Moderate",
            morning_block=[
                Practice(name="Abhyanga Oil Massage", time_slot="06:30 - 06:45", duration_minutes=15, description="Sesame oil", rationale="Vata pacification"),
                Practice(name="Pranayama", time_slot="07:00 - 07:15", duration_minutes=15, description="Gentle breathwork", rationale="Calm mind")
            ],
            midday_block=[],
            evening_block=[],
            timestamp=time.time()
        )

        # 3. Clinical Safety Engine Validation
        validated = ClinicalRuleEngine.validate(candidate, profile)

        # Assert Abhyanga is stripped
        morning_names = [p.name for p in validated.morning_block]
        assert not any("abhyanga" in name.lower() for name in morning_names)
        # Assert fever replacement practice is inserted
        assert any("Nava Jwara Rest" in name for name in morning_names)

    def test_stream_behavior_tracker_complexity_scaling(self):
        """Verify behavior complexity scales based on adherence score."""
        assert AdherenceTracker.determine_complexity(0.95) == "Advanced"
        assert AdherenceTracker.determine_complexity(0.80) == "Advanced"
        assert AdherenceTracker.determine_complexity(0.79) == "Moderate"
        assert AdherenceTracker.determine_complexity(0.50) == "Moderate"
        assert AdherenceTracker.determine_complexity(0.49) == "Anchor Habits"
        assert AdherenceTracker.determine_complexity(0.10) == "Anchor Habits"

"""
Unit Tests for AI Dincharya Centralized Scoring Specification.
Tests all 3 formulas, validation examples, boundary conditions, and missing data policies.
"""

import pytest
from src.behavior.scoring import ScoringEngine


def test_sleep_score_validation_example():
    """
    Validates example from specification:
      D = 85 (Duration)
      R = 70 (Regularity)
      E = 90 (Efficiency)
      Expected S_sleep = 0.50(85) + 0.30(70) + 0.20(90) = 42.5 + 21 + 18 = 81.5
    """
    res = ScoringEngine.calculate_sleep_score(
        duration_score=85,
        regularity_score=70,
        efficiency_score=90
    )
    assert res["status"] == "available"
    assert res["score"] == 81.5
    assert res["rounded_score"] == 82
    assert res["components"]["duration"] == 85.0
    assert res["components"]["regularity"] == 70.0
    assert res["components"]["efficiency"] == 90.0


def test_sleep_score_missing_components_policy():
    """
    Validates that missing or absent sleep records produce an explicit insufficient data state,
    and never fabricate a zero score or synthetic score.
    """
    # All None
    res_none = ScoringEngine.calculate_sleep_score(None, None, None)
    assert res_none["status"] == "insufficient_data"
    assert res_none["score"] is None
    assert res_none["display_text"] == "Awaiting sleep data"

    # Partial None (Duration present, but regularity missing)
    res_part = ScoringEngine.calculate_sleep_score(duration_score=80.0, regularity_score=None, efficiency_score=85.0)
    assert res_part["status"] == "insufficient_data"
    assert res_part["score"] is None
    assert res_part["display_text"] == "Awaiting sleep data"


def test_sleep_score_clamping():
    """Validates that scores outside [0, 100] are safely clamped."""
    res_high = ScoringEngine.calculate_sleep_score(120, 150, 110)
    assert res_high["score"] == 100.0

    res_low = ScoringEngine.calculate_sleep_score(-10, -5, -20)
    assert res_low["score"] == 0.0


def test_wellness_score_validation_example():
    """
    Validates example from specification:
      S = 82 (Sleep & Recovery)
      A = 75 (Physical Activity)
      P = 80 (Physiological Trend)
      U = 90 (Self-Reported Well-being)
      Expected W = 0.35(82) + 0.25(75) + 0.25(80) + 0.15(90) = 28.7 + 18.75 + 20.0 + 13.5 = 80.95
      Rounded displayed score: 81/100.
    """
    res = ScoringEngine.calculate_wellness_score(
        sleep_recovery_score=82,
        physical_activity_score=75,
        physiological_trend_score=80,
        self_reported_wellbeing_score=90
    )
    assert res["status"] == "complete"
    assert res["score"] == 80.95
    assert res["rounded_score"] == 81
    assert res["display_text"] == "81/100"
    assert res["is_partial"] is False
    assert "medical diagnosis" in res["clinical_disclaimer"]


def test_wellness_score_missing_component_partial_policy():
    """
    Validates that missing sleep data does not fabricate 100 or 0,
    and returns a properly flagged partial-data state.
    """
    # Sleep missing (e.g. daytime before first overnight wear), others present
    res = ScoringEngine.calculate_wellness_score(
        sleep_recovery_score=None,
        physical_activity_score=80.0,
        physiological_trend_score=80.0,
        self_reported_wellbeing_score=80.0
    )
    assert res["status"] == "partial_data"
    assert res["is_partial"] is True
    assert "sleep_recovery" in res["missing_components"]
    assert res["score"] == 80.0
    assert "Partial" in res["display_text"]


def test_wellness_score_insufficient_data():
    """Validates that fewer than 2 components produce an explicit insufficient-data state."""
    res = ScoringEngine.calculate_wellness_score(
        sleep_recovery_score=None,
        physical_activity_score=75.0,
        physiological_trend_score=None,
        self_reported_wellbeing_score=None
    )
    assert res["status"] == "insufficient_data"
    assert res["score"] is None
    assert res["display_text"] == "Insufficient data"


def test_adherence_score_validation_example():
    """
    Validates example from specification:
      Eligible scheduled practices: 35
      Completed practices: 28
      Missed or skipped practices: 7
      Expected A_adherence = (28 / 35) * 100 = 80.0%
    """
    res = ScoringEngine.calculate_adherence_score(
        completed_count=28,
        total_eligible_count=35
    )
    assert res["status"] == "calculated"
    assert res["score"] == 80.0
    assert res["rounded_score"] == 80
    assert res["completed_count"] == 28
    assert res["total_eligible_count"] == 35
    assert res["display_text"] == "80%"


def test_adherence_score_empty_schedule():
    """Validates empty schedule produces 0.0 with empty status and does not divide by zero."""
    res = ScoringEngine.calculate_adherence_score(0, 0)
    assert res["status"] == "empty_schedule"
    assert res["score"] == 0.0
    assert res["display_text"] == "--%"


def test_adherence_score_clamping():
    """Validates that completed counts exceeding total cannot inflate adherence beyond 100%."""
    res = ScoringEngine.calculate_adherence_score(10, 5)
    assert res["score"] == 100.0
    assert res["completed_count"] == 5

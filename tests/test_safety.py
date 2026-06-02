import time
from src.models import DinacharyaSchedule, Practice, DoshaProfile, DoshaVector, VikritiFlags
from src.safety.guardrails import ClinicalRuleEngine


def test_safety_override_with_fever():
    """Verify that Abhyanga is correctly removed and replaced during active fever."""
    # 1. Draft a candidate schedule containing Abhyanga
    schedule = DinacharyaSchedule(
        user_id="test_user",
        adherence_score=1.0,
        routine_complexity="Moderate",
        morning_block=[
            Practice(
                name="Brahma Muhurta Jagaran",
                time_slot="06:00 - 06:15",
                duration_minutes=15,
                description="Wake up gently.",
                rationale="Wakes up the mind."
            ),
            Practice(
                name="Warm Abhyanga Massage",
                time_slot="06:30 - 06:45",
                duration_minutes=15,
                description="Massage with warm sesame oil.",
                rationale="Balances Vata."
            )
        ],
        midday_block=[],
        evening_block=[],
        timestamp=time.time()
    )

    # 2. Injected Profile with has_fever=True
    profile = DoshaProfile(
        user_id="test_user",
        prakriti=DoshaVector(vata=0.5, pitta=0.3, kapha=0.2),
        vikriti_flags=VikritiFlags(has_fever=True),
        timestamp=time.time()
    )

    # 3. Apply validation
    validated = ClinicalRuleEngine.validate(schedule, profile)

    # 4. Assertions
    # Abhyanga should be removed from the morning block
    for p in validated.morning_block:
        assert "abhyanga" not in p.name.lower()
        
    # The morning block should contain the safety override replacement
    has_replacement = any("Nava Jwara Rest" in p.name for p in validated.morning_block)
    assert has_replacement is True


def test_safety_no_override_without_fever():
    """Verify that when no fever is active, the schedule is unchanged by the safety engine."""
    schedule = DinacharyaSchedule(
        user_id="test_user",
        adherence_score=1.0,
        routine_complexity="Moderate",
        morning_block=[
            Practice(
                name="Warm Abhyanga Massage",
                time_slot="06:30 - 06:45",
                duration_minutes=15,
                description="Massage with warm sesame oil.",
                rationale="Balances Vata."
            )
        ],
        midday_block=[],
        evening_block=[],
        timestamp=time.time()
    )

    profile = DoshaProfile(
        user_id="test_user",
        prakriti=DoshaVector(vata=0.5, pitta=0.3, kapha=0.2),
        vikriti_flags=VikritiFlags(has_fever=False),
        timestamp=time.time()
    )

    validated = ClinicalRuleEngine.validate(schedule, profile)
    
    # Abhyanga should remain intact
    names = [p.name for p in validated.morning_block]
    assert "Warm Abhyanga Massage" in names

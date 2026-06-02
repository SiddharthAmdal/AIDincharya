from src.perception.dosha_mapper import DoshaMapper


def test_classify_prakriti_default():
    """Verify that empty inputs fallback to the default Vata-dominant Pitta vector."""
    vector = DoshaMapper.classify_prakriti(None)
    assert vector.vata == 0.50
    assert vector.pitta == 0.30
    assert vector.kapha == 0.20


def test_classify_prakriti_keywords():
    """Verify that keywords in the questionnaire responses result in correct dosha weights."""
    mock_responses = {
        "q1": "I have dry skin and feel very light", # Vata keywords (dry, light)
        "q2": "I love hot weather and sweat easily", # Pitta keywords (hot, sweat)
        "q3": "I sleep heavy and move stable"       # Kapha keywords (heavy, stable)
    }
    vector = DoshaMapper.classify_prakriti(mock_responses)
    # Total keywords: Vata (2), Pitta (2), Kapha (2) -> total 6
    # Each should be 2/6 = 0.333
    assert vector.vata == 0.333
    assert vector.pitta == 0.333
    assert vector.kapha == 0.333


def test_detect_vikriti_vata_aggravation():
    """Verify that low HRV (<45 ms) and short sleep (<6.2 hours) triggers Vata aggravation."""
    telemetry = {
        "hrv_ms": 32.0,
        "resting_hr": 68.0,
        "sleep_hours": 5.5
    }
    flags = DoshaMapper.detect_vikriti(telemetry)
    assert flags.vata_aggravated is True
    assert flags.pitta_aggravated is False
    assert flags.kapha_aggravated is False
    assert flags.has_fever is False


def test_detect_vikriti_pitta_aggravation():
    """Verify that high RHR (>82 bpm) and low HRV (<45 ms) triggers Pitta aggravation."""
    telemetry = {
        "hrv_ms": 38.0,
        "resting_hr": 85.0,
        "sleep_hours": 7.0
    }
    flags = DoshaMapper.detect_vikriti(telemetry)
    assert flags.vata_aggravated is False
    assert flags.pitta_aggravated is True
    assert flags.kapha_aggravated is False
    assert flags.has_fever is False


def test_detect_vikriti_fever():
    """Verify that elevated body temperature (>37.8C) flags an active fever (Nava Jwara)."""
    telemetry = {
        "body_temp_c": 38.4,
        "hrv_ms": 50.0,
        "resting_hr": 70.0,
        "sleep_hours": 7.5
    }
    flags = DoshaMapper.detect_vikriti(telemetry)
    assert flags.has_fever is True

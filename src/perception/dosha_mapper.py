import time
from typing import Dict, Optional
from src.models import DoshaVector, VikritiFlags, DoshaProfile


class DoshaMapper:
    """
    Stubs the Perception Domain (Module 2).
    Translates static phenotype questionnaires and noisy rolling wearable telemetry
    into computable Ayurvedic Prakriti and Vikriti vectors.
    """

    @staticmethod
    def classify_prakriti(responses: Optional[Dict[str, str]] = None) -> DoshaVector:
        """
        Translates a 24-item bilingual questionnaire into a baseline Prakriti vector.
        If responses are missing or empty, returns a balanced Vata-Pitta dominant default.
        """
        if not responses:
            # Default balanced constitution: Vata-dominant Pitta (e.g., [V: 0.50, P: 0.30, K: 0.20])
            return DoshaVector(vata=0.50, pitta=0.30, kapha=0.20)

        # Simple rule-based scorer for the stub
        # We look for keywords in the mock questionnaire responses to derive V, P, K scores
        v_score, p_score, k_score = 0.0, 0.0, 0.0
        for val in responses.values():
            val_lower = val.lower()
            if "vata" in val_lower or "dry" in val_lower or "light" in val_lower or "fast" in val_lower or "cold" in val_lower:
                v_score += 1.0
            if "pitta" in val_lower or "hot" in val_lower or "sharp" in val_lower or "acid" in val_lower or "sweat" in val_lower:
                p_score += 1.0
            if "kapha" in val_lower or "heavy" in val_lower or "slow" in val_lower or "sleepy" in val_lower or "stable" in val_lower:
                k_score += 1.0

        total = v_score + p_score + k_score
        if total == 0:
            return DoshaVector(vata=0.50, pitta=0.30, kapha=0.20)

        return DoshaVector(
            vata=round(v_score / total, 3),
            pitta=round(p_score / total, 3),
            kapha=round(k_score / total, 3)
        )

    @staticmethod
    def detect_vikriti(
        telemetry_7d: Optional[Dict[str, float]] = None,
        symptoms: Optional[Dict[str, str]] = None
    ) -> VikritiFlags:
        """
        Uses rolling 7-day wearable statistics to identify current deviations from baseline.
        In the future, this will be handled by an Isolation Forest anomaly detector.
        
        Telemetry parameters expected:
        - hrv_ms: Heart Rate Variability average over 7 days (ms)
        - resting_hr: Resting Heart Rate average (bpm)
        - sleep_hours: Average sleep duration (hours)
        - sleep_efficiency: Percentage (0.0 to 1.0)
        """
        flags = VikritiFlags()

        # Handle symptoms first
        if symptoms:
            for s_name, s_val in symptoms.items():
                s_lower = s_val.lower()
                if "fever" in s_lower or "temp" in s_lower:
                    flags.has_fever = True

        if not telemetry_7d:
            return flags

        # Dynamic rules mimicking anomaly thresholds:
        hrv = telemetry_7d.get("hrv_ms", 55.0)
        rhr = telemetry_7d.get("resting_hr", 70.0)
        sleep = telemetry_7d.get("sleep_hours", 7.5)

        # 1. Vata is aggravated by high irregularity, stress, and lack of sleep (Low HRV + Low Sleep)
        if hrv < 45.0 and sleep < 6.2:
            flags.vata_aggravated = True

        # 2. Pitta is aggravated by inflammation, heat, and high physical exertion (High RHR + Low HRV)
        if rhr > 82.0 and hrv < 45.0:
            flags.pitta_aggravated = True

        # 3. Kapha is aggravated by sluggishness, oversleeping, and low heart rates (High Sleep + Low RHR)
        if sleep > 9.0 and rhr < 55.0:
            flags.kapha_aggravated = True

        # 4. Temperature-based fever check
        if telemetry_7d.get("body_temp_c", 36.8) > 37.8:
            flags.has_fever = True

        return flags

    @classmethod
    def generate_profile(
        cls,
        user_id: str,
        questionnaire: Optional[Dict[str, str]] = None,
        telemetry: Optional[Dict[str, float]] = None,
        symptoms: Optional[Dict[str, str]] = None
    ) -> DoshaProfile:
        """
        Generates the unified DoshaProfile aggregating Prakriti and Vikriti outputs.
        """
        prakriti = cls.classify_prakriti(questionnaire)
        vikriti_flags = cls.detect_vikriti(telemetry, symptoms)

        return DoshaProfile(
            user_id=user_id,
            prakriti=prakriti,
            vikriti_flags=vikriti_flags,
            timestamp=time.time()
        )

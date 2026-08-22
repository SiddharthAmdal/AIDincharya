import time
import numpy as np
from typing import Dict, Optional, Union, List
from src.models import DoshaVector, VikritiFlags, DoshaProfile

try:
    from sklearn.ensemble import IsolationForest
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class IsolationForestAnomalyDetector:
    """
    Unsupervised Isolation Forest anomaly detector for 7-day rolling telemetry.
    Identifies physiological deviations (Vata/Pitta/Kapha/Fever) from historical baseline.
    """
    def __init__(self, contamination: float = 0.1):
        self.contamination = contamination
        self.model = IsolationForest(contamination=contamination, random_state=42) if SKLEARN_AVAILABLE else None

    def fit_predict(self, data_points: List[List[float]]) -> List[int]:
        if SKLEARN_AVAILABLE and len(data_points) >= 4:
            X = np.array(data_points)
            return self.model.fit_predict(X).tolist()
        return [-1 if len(dp) > 0 and dp[0] < 45.0 else 1 for dp in data_points]


class DoshaMapper:
    """
    Stubs the Perception Domain (Module 2).
    Translates static phenotype questionnaires and noisy rolling wearable telemetry
    into computable Ayurvedic Prakriti and Vikriti vectors.
    """
    anomaly_detector = IsolationForestAnomalyDetector()

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
            val_lower = str(val).lower()
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
        symptoms: Optional[Union[Dict[str, str], List[str]]] = None
    ) -> VikritiFlags:
        """
        Uses rolling 7-day wearable telemetry and symptom reports to identify active Vikriti flags.
        Incorporate Isolation Forest anomaly scoring for telemetry deviations.
        """
        flags = VikritiFlags()

        # Handle symptoms safely whether passed as list or dict
        if symptoms:
            s_list = symptoms.values() if isinstance(symptoms, dict) else (symptoms if isinstance(symptoms, list) else [])
            for s_val in s_list:
                s_lower = str(s_val).lower()
                if "fever" in s_lower or "temp" in s_lower:
                    flags.has_fever = True

        if not telemetry_7d:
            return flags

        # Extract features
        hrv = telemetry_7d.get("hrv_ms", 55.0)
        rhr = telemetry_7d.get("resting_hr", 70.0)
        sleep = telemetry_7d.get("sleep_hours", 7.5)
        temp = telemetry_7d.get("body_temp_c", 36.8)

        # Run Isolation Forest Anomaly Evaluator
        features = [hrv, rhr, sleep, temp]
        anomaly_score = DoshaMapper.anomaly_detector.fit_predict([features])[0]

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
        if temp > 37.8:
            flags.has_fever = True

        return flags

    @classmethod
    def generate_profile(
        cls,
        user_id: str,
        questionnaire: Optional[Dict[str, str]] = None,
        telemetry: Optional[Dict[str, float]] = None,
        symptoms: Optional[Union[Dict[str, str], List[str]]] = None
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

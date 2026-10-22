import time
from typing import Dict, Optional, Any
from src.models import DoshaVector, VikritiFlags, DoshaProfile


class DoshaMapper:
    """
    Stubs the Perception Domain (Module 2).
    Translates static phenotype questionnaires and noisy rolling wearable telemetry
    into computable Ayurvedic Prakriti and Vikriti vectors.
    """

    RUBRIC_VERSION = "v1.2-rubric"

    RUBRIC_KEYWORDS = {
        "vata": [
            "vata", "dry", "light", "fast", "cold", "irregular", "variable", 
            "anxiety", "lean", "thin", "restless", "insomnia", "gas", "bloat"
        ],
        "pitta": [
            "pitta", "hot", "sharp", "acid", "sweat", "intense", "irritable", 
            "medium", "athletic", "warm", "hunger", "heartburn", "sunburn"
        ],
        "kapha": [
            "kapha", "heavy", "slow", "sleepy", "stable", "calm", "broad", 
            "solid", "sturdy", "lethargic", "mucus", "steady", "weight"
        ]
    }

    @classmethod
    def classify_prakriti(cls, responses: Optional[Dict[str, str]] = None) -> DoshaVector:
        """
        Translates questionnaire responses into a normalized Prakriti vector using
        a deterministic clinical rubric across physiological and behavioral dimensions.
        """
        if not responses:
            return DoshaVector(vata=0.50, pitta=0.30, kapha=0.20)

        v_score, p_score, k_score = 0.0, 0.0, 0.0

        for key, val in responses.items():
            if not val or not isinstance(val, str):
                continue
            val_clean = val.strip().lower()

            # Direct categorical selection
            if val_clean in ("vata", "v"):
                v_score += 1.0
            elif val_clean in ("pitta", "p"):
                p_score += 1.0
            elif val_clean in ("kapha", "k"):
                k_score += 1.0
            else:
                # Text rubric token matching
                v_hits = sum(1 for kw in cls.RUBRIC_KEYWORDS["vata"] if kw in val_clean)
                p_hits = sum(1 for kw in cls.RUBRIC_KEYWORDS["pitta"] if kw in val_clean)
                k_hits = sum(1 for kw in cls.RUBRIC_KEYWORDS["kapha"] if kw in val_clean)
                
                # Weight contribution proportionally if mixed text
                tot_hits = v_hits + p_hits + k_hits
                if tot_hits > 0:
                    v_score += v_hits / tot_hits
                    p_score += p_hits / tot_hits
                    k_score += k_hits / tot_hits

        total = v_score + p_score + k_score
        if total == 0:
            return DoshaVector(vata=0.50, pitta=0.30, kapha=0.20)

        # Normalization with deterministic rounding
        norm_v = round(v_score / total, 3)
        norm_p = round(p_score / total, 3)
        norm_k = round(k_score / total, 3)

        return DoshaVector(vata=norm_v, pitta=norm_p, kapha=norm_k)

    @classmethod
    def explain_prakriti_classification(cls, responses: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Provides a transparent, explainable audit of the rubric evaluation.
        """
        vector = cls.classify_prakriti(responses)
        scores = {"vata": vector.vata, "pitta": vector.pitta, "kapha": vector.kapha}
        sorted_doshas = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary, primary_score = sorted_doshas[0]
        secondary, secondary_score = sorted_doshas[1]

        if primary_score >= 0.60:
            dominant_type = f"Pure {primary.capitalize()}"
        elif (primary_score - secondary_score) <= 0.15:
            dominant_type = f"Dual {primary.capitalize()}-{secondary.capitalize()}"
        else:
            dominant_type = f"{primary.capitalize()}-dominant"

        return {
            "rubric_version": cls.RUBRIC_VERSION,
            "dosha_vector": vector.model_dump(),
            "constitution_type": dominant_type,
            "primary_dosha": primary.capitalize(),
            "secondary_dosha": secondary.capitalize(),
            "explanation": f"Based on {len(responses or {})} assessment responses, your baseline constitution is {dominant_type} ({primary.capitalize()} {int(primary_score*100)}%, {secondary.capitalize()} {int(secondary_score*100)}%)."
        }

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

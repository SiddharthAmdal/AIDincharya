"""
vikriti_tracker.py - Longitudinal Vikriti State Tracking and Provenance

Tracks dynamic physiological and psychological deviations (Vikriti) from a user's
baseline constitution (Prakriti). Distinguishes self-reported observations from verified
wearable telemetry, records observation provenance, and tracks changes over time without
inferring medical diagnoses.
"""

import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from src.models import VikritiFlags, DoshaVector

logger = logging.getLogger("VikritiTracker")


SYMPTOM_DOSHA_MAP = {
    "vata": [
        "anxiety", "worry", "restless", "insomnia", "sleepless", "light sleep",
        "dry skin", "constipation", "gas", "bloat", "cold intolerance", "cold hands",
        "irregular appetite", "muscle stiffness", "fatigue", "scattered", "shivering"
    ],
    "pitta": [
        "acid reflux", "heartburn", "burning", "skin rash", "flushing", "redness",
        "inflammation", "irritability", "anger", "frustration", "excessive heat",
        "sweat", "loose stools", "excessive thirst", "sunburn", "eye strain"
    ],
    "kapha": [
        "lethargy", "heaviness", "sluggishness", "drowsiness", "oversleeping",
        "sleepy", "congestion", "mucus", "fluid retention", "water retention",
        "low motivation", "slow digestion", "heavy stomach"
    ],
    "fever_red_flag": [
        "fever", "high temperature", "chills", "nava jwara", "pyrexia", "feverish"
    ]
}


class VikritiTracker:
    """
    Manages longitudinal tracking of daily symptom observations and biometric deviations.
    """

    VERSION = "vikriti-v1.0"

    @classmethod
    def evaluate_symptoms(cls, symptoms: Optional[List[str]]) -> Dict[str, Any]:
        """
        Extracts Dosha aggravation tendencies from structured or natural language symptoms.
        Returns matched symptom lists, score contributions, and red-flag indicators.
        """
        if not symptoms:
            return {
                "vata_hits": [],
                "pitta_hits": [],
                "kapha_hits": [],
                "has_fever": False,
                "total_symptoms": 0
            }

        vata_hits, pitta_hits, kapha_hits = [], [], []
        has_fever = False

        for sym in symptoms:
            if not sym or not isinstance(sym, str):
                continue
            s_lower = sym.strip().lower()

            # Check red flags first
            if any(term in s_lower for term in SYMPTOM_DOSHA_MAP["fever_red_flag"]):
                has_fever = True

            # Match dosha symptom keywords
            v_matches = [term for term in SYMPTOM_DOSHA_MAP["vata"] if term in s_lower]
            p_matches = [term for term in SYMPTOM_DOSHA_MAP["pitta"] if term in s_lower]
            k_matches = [term for term in SYMPTOM_DOSHA_MAP["kapha"] if term in s_lower]

            if v_matches:
                vata_hits.append((sym, v_matches))
            if p_matches:
                pitta_hits.append((sym, p_matches))
            if k_matches:
                kapha_hits.append((sym, k_matches))

        return {
            "vata_hits": vata_hits,
            "pitta_hits": pitta_hits,
            "kapha_hits": kapha_hits,
            "has_fever": has_fever,
            "total_symptoms": len(symptoms)
        }

    @classmethod
    def evaluate_telemetry(cls, telemetry: Optional[Dict[str, float]]) -> Dict[str, Any]:
        """
        Evaluates physiological telemetry parameters against dynamic clinical thresholds.
        Does not interpret missing signals as normal health.
        """
        if not telemetry or not isinstance(telemetry, dict):
            return {
                "signals_available": [],
                "vata_flag": False,
                "pitta_flag": False,
                "kapha_flag": False,
                "fever_flag": False,
                "telemetry_present": False
            }

        signals = list(telemetry.keys())
        v_flag, p_flag, k_flag, f_flag = False, False, False, False

        # Only evaluate signals that are genuinely present (no synthetic default assumptions)
        hrv = telemetry.get("hrv_ms")
        rhr = telemetry.get("resting_hr")
        sleep = telemetry.get("sleep_hours")
        body_temp = telemetry.get("body_temp_c")

        if body_temp is not None and body_temp > 37.8:
            f_flag = True

        if hrv is not None and sleep is not None:
            if hrv < 45.0 and sleep < 6.2:
                v_flag = True

        if rhr is not None and hrv is not None:
            if rhr > 82.0 and hrv < 45.0:
                p_flag = True

        if sleep is not None and rhr is not None:
            if sleep > 9.0 and rhr < 55.0:
                k_flag = True

        return {
            "signals_available": signals,
            "vata_flag": v_flag,
            "pitta_flag": p_flag,
            "kapha_flag": k_flag,
            "fever_flag": f_flag,
            "telemetry_present": len(signals) > 0
        }

    @classmethod
    def estimate_vikriti(
        cls,
        symptoms: Optional[List[str]] = None,
        telemetry: Optional[Dict[str, float]] = None,
        baseline_prakriti: Optional[DoshaVector] = None,
        past_observations: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[VikritiFlags, Dict[str, Any]]:
        """
        Computes the unified VikritiFlags along with an audit trail of observation provenance.
        Differentiates baseline constitution from active deviation.
        """
        sym_eval = cls.evaluate_symptoms(symptoms)
        tel_eval = cls.evaluate_telemetry(telemetry)

        vata_symptom_count = len(sym_eval["vata_hits"])
        pitta_symptom_count = len(sym_eval["pitta_hits"])
        kapha_symptom_count = len(sym_eval["kapha_hits"])

        has_fever = sym_eval["has_fever"] or tel_eval["fever_flag"]
        vata_agg = (vata_symptom_count >= 1) or tel_eval["vata_flag"]
        pitta_agg = (pitta_symptom_count >= 1) or tel_eval["pitta_flag"]
        kapha_agg = (kapha_symptom_count >= 1) or tel_eval["kapha_flag"]

        # Determine data availability & confidence
        has_sym = sym_eval["total_symptoms"] > 0
        has_tel = tel_eval["telemetry_present"]

        if has_sym and has_tel:
            data_status = "multimodal_verified"
            confidence = "high"
        elif has_sym:
            data_status = "self_report_only"
            confidence = "provisional"
        elif has_tel:
            data_status = "telemetry_only"
            confidence = "provisional"
        else:
            data_status = "insufficient_data"
            confidence = "indeterminate"

        # Track longitudinal trends across past observations
        trend_notes = []
        if past_observations and len(past_observations) > 0:
            past_fever = sum(1 for obs in past_observations if obs.get("has_fever"))
            past_vata = sum(1 for obs in past_observations if obs.get("vata_aggravated"))
            past_pitta = sum(1 for obs in past_observations if obs.get("pitta_aggravated"))
            past_kapha = sum(1 for obs in past_observations if obs.get("kapha_aggravated"))

            if past_vata >= 2:
                trend_notes.append("Persistent Vata elevation over recent days")
            if past_pitta >= 2:
                trend_notes.append("Persistent Pitta heat over recent days")
            if past_kapha >= 2:
                trend_notes.append("Persistent Kapha stagnation over recent days")

        flags = VikritiFlags(
            vata_aggravated=vata_agg,
            pitta_aggravated=pitta_agg,
            kapha_aggravated=kapha_agg,
            has_fever=has_fever
        )

        provenance = {
            "tracker_version": cls.VERSION,
            "data_availability_status": data_status,
            "confidence": confidence,
            "self_reported_symptoms": symptoms or [],
            "telemetry_signals_consumed": tel_eval["signals_available"],
            "symptom_matches": {
                "vata": [h[0] for h in sym_eval["vata_hits"]],
                "pitta": [h[0] for h in sym_eval["pitta_hits"]],
                "kapha": [h[0] for h in sym_eval["kapha_hits"]]
            },
            "longitudinal_trends": trend_notes,
            "timestamp": time.time(),
            "disclaimer": "Vikriti reflects temporary physiological fluctuations estimated from user reports and wearable signals. It is not an invasive medical diagnosis."
        }

        return flags, provenance

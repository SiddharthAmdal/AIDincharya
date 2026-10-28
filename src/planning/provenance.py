"""
provenance.py - Decision Provenance and Explainability for Dinacharya Planning

Records a structured, privacy-conscious audit trail explaining why practices were
selected, modified, or rejected based on Prakriti, Vikriti, wearable telemetry,
and clinical safety boundaries.
"""

import time
from typing import Dict, List, Any, Optional
from src.models import DoshaProfile, UserContext, Practice, DinacharyaSchedule


class DecisionProvenanceTracker:
    """
    Constructs a structured audit trace of how the user's saved Prakriti assessment,
    active Vikriti symptoms, and telemetry influenced the generated schedule.
    """

    PROVENANCE_SCHEMA_VERSION = "provenance-v1.0"

    @classmethod
    def generate_trace(
        cls,
        user_id: str,
        profile: DoshaProfile,
        context: Optional[UserContext],
        complexity: str,
        adherence_score: float,
        schedule: DinacharyaSchedule,
        vikriti_provenance: Optional[Dict[str, Any]] = None,
        telemetry_consumed: Optional[List[str]] = None,
        refinement_logs: Optional[List[str]] = None,
        safety_modifications: Optional[List[Dict[str, Any]]] = None,
        is_fallback: bool = False,
        model_used: str = "primary_llm"
    ) -> Dict[str, Any]:
        """
        Builds a privacy-conscious provenance record without logging raw credentials or private identifiers.
        """
        prakriti = profile.prakriti
        vikriti = profile.vikriti_flags

        # Classify dominant constitution description
        scores = {"vata": prakriti.vata, "pitta": prakriti.pitta, "kapha": prakriti.kapha}
        sorted_doshas = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary, p_val = sorted_doshas[0]
        secondary, s_val = sorted_doshas[1]

        if (p_val - sorted_doshas[2][1]) <= 0.08:
            const_desc = "Tridoshic (Sama Prakriti)"
        elif (p_val - s_val) <= 0.15:
            const_desc = f"Dual {primary.capitalize()}-{secondary.capitalize()}"
        else:
            const_desc = f"{primary.capitalize()}-dominant"

        # Active imbalances
        active_imbalances = []
        if vikriti.has_fever:
            active_imbalances.append("acute_fever (Nava Jwara)")
        if vikriti.vata_aggravated:
            active_imbalances.append("vata_aggravation")
        if vikriti.pitta_aggravated:
            active_imbalances.append("pitta_aggravation")
        if vikriti.kapha_aggravated:
            active_imbalances.append("kapha_aggravation")

        # Collect practices in final schedule
        morning_names = [p.name for p in schedule.morning_block]
        midday_names = [p.name for p in schedule.midday_block]
        evening_names = [p.name for p in schedule.evening_block]

        trace = {
            "schema_version": cls.PROVENANCE_SCHEMA_VERSION,
            "timestamp": time.time(),
            "user_id_hash": f"usr_{hash(user_id) % 100000:05d}",
            "planner_execution": {
                "is_fallback": is_fallback,
                "engine_used": model_used,
                "complexity_level": complexity,
                "adherence_score": adherence_score
            },
            "profile_inputs": {
                "assessment_status": getattr(profile, "assessment_status", "completed"),
                "prakriti_vector": {
                    "vata": prakriti.vata,
                    "pitta": prakriti.pitta,
                    "kapha": prakriti.kapha
                },
                "constitution_classification": const_desc,
                "active_vikriti_imbalances": active_imbalances or ["none_detected"]
            },
            "data_sources_consumed": {
                "self_reported_symptoms": context.self_report_symptoms if context else [],
                "telemetry_signals_consumed": telemetry_consumed or (vikriti_provenance.get("telemetry_signals_consumed", []) if vikriti_provenance else []),
                "wearable_data_status": vikriti_provenance.get("data_availability_status", "not_provided") if vikriti_provenance else "not_provided"
            },
            "schedule_decisions": {
                "morning_practices": morning_names,
                "midday_practices": midday_names,
                "evening_practices": evening_names,
                "total_practices": len(morning_names) + len(midday_names) + len(evening_names)
            },
            "planning_refinements": refinement_logs or [],
            "safety_modifications": safety_modifications or []
        }

        return trace

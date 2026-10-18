"""
Canonical Schedule Service for AI Dincharya.

Provides a single authoritative service for:
1. Reading the canonical persisted schedule.
2. Mutating scheduled practices (rescheduling, updating) with clinical safety validation.
3. Persisting the canonical representation to SQLite.
4. Ensuring cross-user isolation and preventing unintended side-effects on unrelated activities.
"""

import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

import src.database.db as db
from src.models import DinacharyaSchedule, Practice, DoshaProfile
from src.perception.dosha_mapper import DoshaMapper
from src.safety.guardrails import ClinicalRuleEngine
from src.planning.agent import standardize_slot

logger = logging.getLogger("ScheduleService")


def get_canonical_schedule(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieves the authoritative canonical schedule for the user directly from the database.
    Returns the full state dict (containing 'schedule', 'dosha_profile', etc.) or None.
    """
    state = db.get_user_state(user_id)
    if not state:
        return None
    cached = state.get("last_schedule")
    if cached and isinstance(cached, dict) and "schedule" in cached:
        return cached
    return None


def mutate_user_schedule(
    user_id: int,
    updates: Dict[str, str],
    date_str: Optional[str] = None
) -> Dict[str, Any]:
    """
    Authoritative single mutation function for modifying practice timings.

    Requirements enforced:
    - User scoped: operates strictly on the authenticated user_id.
    - Preserves unrelated activities: ONLY practices matching `updates` keys are modified.
    - Standardizes time slots into strict 24h format (e.g. '20:00 - 20:30').
    - Clinical safety validation: runs ClinicalRuleEngine before persistence.
    - Atomic canonical persistence: saves `{schedule, dosha_profile, complexity_level, timestamp}` to SQLite.
    - Idempotent notification creation on success.
    - Safe failure: if DB write fails, throws or returns error and leaves schedule unchanged.
    """
    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    state = db.get_user_state(user_id)
    if not state:
        return {"success": False, "error": f"User {user_id} not found."}

    last_sched = state.get("last_schedule")
    if not last_sched or not isinstance(last_sched, dict) or "schedule" not in last_sched:
        return {"success": False, "error": "No existing schedule found to adapt."}

    sched_root = last_sched["schedule"]
    if not isinstance(sched_root, dict):
        return {"success": False, "error": "Malformed schedule root in vault."}

    # Extract user profile for clinical safety check
    current_vikriti = state.get("current_vikriti", {})
    telemetry = current_vikriti.get("telemetry", {}) if isinstance(current_vikriti, dict) else {}
    symptoms_list = current_vikriti.get("symptoms", []) if isinstance(current_vikriti, dict) else []
    symptoms_map = {f"sym_{i}": s for i, s in enumerate(symptoms_list)}

    profile = DoshaMapper.generate_profile(
        user_id=str(user_id),
        questionnaire=state.get("questionnaire_responses", {}),
        telemetry=telemetry,
        symptoms=symptoms_map
    )

    # Standardize updates map: {normalized_activity_name: standardized_slot}
    norm_updates: Dict[str, str] = {}
    for act_name, slot in updates.items():
        norm_updates[act_name.strip().lower()] = standardize_slot(slot)

    matched_practices: List[str] = []

    def clone_and_mutate_block(raw_block: List[Any]) -> List[Practice]:
        out = []
        for item in raw_block:
            p_dict = item if isinstance(item, dict) else item.model_dump()
            p_name = p_dict.get("name") or p_dict.get("activity") or "Practice"
            p_name_lower = p_name.lower().strip()
            
            # Check if this practice is being updated (exact or keyword substring)
            new_slot = None
            for upd_k, upd_slot in norm_updates.items():
                if upd_k == p_name_lower or upd_k in p_name_lower or p_name_lower in upd_k:
                    new_slot = upd_slot
                    matched_practices.append(p_name)
                    break

            effective_slot = new_slot if new_slot else (p_dict.get("time_slot") or p_dict.get("time") or "Flexible")
            out.append(Practice(
                name=p_name,
                time_slot=standardize_slot(effective_slot),
                duration_minutes=int(p_dict.get("duration_minutes", 15)),
                description=p_dict.get("description", ""),
                rationale=p_dict.get("rationale", "")
            ))
        return out

    cand_morning = clone_and_mutate_block(sched_root.get("morning_block", []))
    cand_midday = clone_and_mutate_block(sched_root.get("midday_block", []))
    cand_evening = clone_and_mutate_block(sched_root.get("evening_block", []))

    if not matched_practices:
        return {
            "success": False,
            "error": f"No scheduled practices matched the requested activities: {list(updates.keys())}"
        }

    candidate = DinacharyaSchedule(
        user_id=str(user_id),
        adherence_score=float(state.get("adherence_score", 1.0)),
        routine_complexity=sched_root.get("routine_complexity", "Adaptive"),
        morning_block=cand_morning,
        midday_block=cand_midday,
        evening_block=cand_evening,
        timestamp=time.time()
    )

    # Mandatory clinical guardrail validation
    validated = ClinicalRuleEngine.validate(candidate, profile)

    val_dump = validated.model_dump()
    applied_updates: Dict[str, str] = {}
    for blk_key in ["morning_block", "midday_block", "evening_block"]:
        for p_item in val_dump.get(blk_key, []):
            if p_item.get("name") in matched_practices:
                applied_updates[p_item["name"]] = p_item.get("time_slot", "")

    canonical_data = {
        "schedule": val_dump,
        "morning_block": val_dump.get("morning_block", []),
        "midday_block": val_dump.get("midday_block", []),
        "evening_block": val_dump.get("evening_block", []),
        "dosha_profile": profile.model_dump(),
        "complexity_level": candidate.routine_complexity,
        "behavioral_nudge": last_sched.get("behavioral_nudge", "Routine synchronized with circadian rhythm."),
        "retrieved_guidelines": last_sched.get("retrieved_guidelines", []),
        "timestamp": time.time()
    }

    # Atomic canonical write
    try:
        db.save_user_schedule(user_id, canonical_data, target_date)
    except Exception as exc:
        logger.error(f"Database write failure during schedule mutation for user {user_id}: {exc}")
        return {"success": False, "error": f"Database write failed: {str(exc)}"}

    # Idempotent notification
    idemp_key = f"mutation-{user_id}-{target_date}-{int(time.time() // 60)}"
    db.create_notification(
        user_id=user_id,
        event_type="adaptation_confirmed",
        message=f"Schedule updated: {', '.join(matched_practices)} moved to new time.",
        activity_name=", ".join(matched_practices),
        severity="info",
        channel="in_app",
        idempotency_key=idemp_key
    )

    # Decoupled Web Push delivery (failure never rolls back DB persistence)
    try:
        from src.notifications.push_service import send_push_notification_to_user
        send_push_notification_to_user(
            user_id=user_id,
            title="Ayurvedic Routine Synchronized",
            body=f"Schedule updated: {', '.join(matched_practices)} moved to new time.",
            url="/routine",
            tag=idemp_key,
            extra_data={"event_type": "adaptation_confirmed", "activities": matched_practices}
        )
    except Exception as push_err:
        logger.warning(f"Web Push delivery attempt failed for user {user_id} (in-app preserved): {push_err}")

    return {
        "success": True,
        "schedule": canonical_data["schedule"],
        "canonical_data": canonical_data,
        "matched_practices": matched_practices,
        "applied_updates": applied_updates,
        "persisted_date": target_date
    }

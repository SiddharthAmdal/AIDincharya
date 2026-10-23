"""
Canonical Schedule Service for AI Dincharya.

Provides a single authoritative service for:
1. Reading the canonical persisted schedule.
2. Mutating scheduled practices (rescheduling, updating) with clinical safety validation.
3. Persisting the canonical representation to SQLite.
4. Ensuring cross-user isolation and preventing unintended side-effects on unrelated activities.
"""

import time
import re
import secrets
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import src.database.db as db
from src.models import DinacharyaSchedule, Practice, DoshaProfile, ScheduleProposal
from src.perception.dosha_mapper import DoshaMapper
from src.safety.guardrails import (
    ClinicalRuleEngine,
    _parse_slot_minutes,
    _format_minutes_to_slot,
    get_destination_block,
    reblock_schedule_practices
)
from src.planning.agent import standardize_slot, extract_practice_time_updates

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
    if not last_sched or not isinstance(last_sched, dict):
        return {"success": False, "error": "No existing schedule found to adapt."}

    if "schedule" in last_sched and isinstance(last_sched["schedule"], dict):
        sched_root = last_sched["schedule"]
    else:
        sched_root = last_sched

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

    # Gather all existing practices from morning_block, midday_block, evening_block
    all_raw_practices: List[Tuple[str, Dict[str, Any]]] = []
    for blk_name in ["morning_block", "midday_block", "evening_block"]:
        for item in sched_root.get(blk_name, []) or []:
            p_dict = item if isinstance(item, dict) else item.model_dump()
            all_raw_practices.append((blk_name, p_dict))

    new_blocks: Dict[str, List[Practice]] = {
        "morning_block": [],
        "midday_block": [],
        "evening_block": []
    }
    seen_canonical_names = set()

    for orig_blk, p_dict in all_raw_practices:
        p_name = p_dict.get("name") or p_dict.get("activity") or "Practice"
        p_name_lower = p_name.lower().strip()

        # Deduplication safeguard: preserve exactly one instance of each practice
        if p_name_lower in seen_canonical_names:
            continue
        seen_canonical_names.add(p_name_lower)

        # Check if this practice is being updated (exact or keyword substring)
        new_slot = None
        for upd_k, upd_slot in norm_updates.items():
            if upd_k == p_name_lower or upd_k in p_name_lower or p_name_lower in upd_k:
                new_slot = upd_slot
                if p_name not in matched_practices:
                    matched_practices.append(p_name)
                break

        if new_slot:
            effective_slot = standardize_slot(new_slot)
            dest_block = get_destination_block(effective_slot, fallback_block=orig_blk)
        else:
            effective_slot = standardize_slot(p_dict.get("time_slot") or p_dict.get("time") or "Flexible")
            dest_block = get_destination_block(effective_slot, fallback_block=orig_blk)

        practice_obj = Practice(
            name=p_name,
            time_slot=effective_slot,
            duration_minutes=int(p_dict.get("duration_minutes", 15)),
            description=p_dict.get("description", ""),
            rationale=p_dict.get("rationale", "")
        )
        new_blocks[dest_block].append(practice_obj)

    if not matched_practices:
        return {
            "success": False,
            "error": f"No scheduled practices matched the requested activities: {list(updates.keys())}"
        }

    for b in ["morning_block", "midday_block", "evening_block"]:
        def _sort_key(item: Practice) -> Tuple[int, str]:
            parsed = _parse_slot_minutes(item.time_slot, item.duration_minutes)
            return (parsed[0] if parsed else 9999, item.name)
        new_blocks[b].sort(key=_sort_key)

    candidate = DinacharyaSchedule(
        user_id=str(user_id),
        adherence_score=float(state.get("adherence_score", 1.0)),
        routine_complexity=sched_root.get("routine_complexity", "Adaptive"),
        morning_block=new_blocks["morning_block"],
        midday_block=new_blocks["midday_block"],
        evening_block=new_blocks["evening_block"],
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


# =============================================================================
# Canonical Proposal Lifecycle
# =============================================================================

def resolve_practice_intent(
    message: str,
    current_schedule: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Identifies target practice and requested time slot from user message.
    Handles both absolute time slots (e.g. "at 7:30 PM", "to 15:40")
    and relative meal / activity references (e.g. "after my mitahara", "after lunch", "after dinner", "before dinner").
    Returns:
        {
            "target_practice": canonical_name,
            "original_time_slot": orig_slot,
            "target_block": block_name,
            "requested_slot": requested_slot,
            "relative_anchor": anchor_label,
            "duration_minutes": duration
        }
    """
    if not message or not current_schedule:
        return None

    sched_root = current_schedule.get("schedule", current_schedule)
    if not isinstance(sched_root, dict):
        return None

    all_practices: List[Dict[str, Any]] = []
    for blk_name in ["morning_block", "midday_block", "evening_block"]:
        for p in sched_root.get(blk_name, []):
            p_dict = p if isinstance(p, dict) else p.model_dump()
            all_practices.append({
                "name": p_dict.get("name", ""),
                "time_slot": p_dict.get("time_slot", ""),
                "duration_minutes": int(p_dict.get("duration_minutes", 15)),
                "block": blk_name,
                "description": p_dict.get("description", ""),
                "rationale": p_dict.get("rationale", "")
            })

    if not all_practices:
        return None

    msg_lower = message.lower()

    # Practice keyword synonyms
    practice_synonyms = {
        "pranayama": ["pranayama", "nadi shodhana", "anulom", "vilom", "breathwork", "breathing"],
        "abhyanga": ["abhyanga", "oil massage", "massage"],
        "snana": ["snana", "bath", "shower"],
        "lunch": ["lunch", "mitahara", "midday meal"],
        "dinner": ["dinner", "evening meal", "light early dinner"],
        "vyayama": ["vyayama", "exercise", "workout", "movement"],
        "trataka": ["trataka", "candle gazing", "digital sunset"]
    }

    target = None
    for p in all_practices:
        p_name_lower = p["name"].lower()
        if p_name_lower in msg_lower:
            target = p
            break
        for key, syns in practice_synonyms.items():
            if any(s in msg_lower for s in syns) and any(s in p_name_lower for s in syns):
                target = p
                break
        if target:
            break

    if not target:
        return None

    p_names_list = [p["name"] for p in all_practices]
    explicit_updates = extract_practice_time_updates(message, p_names_list + [target["name"]])

    requested_slot = None
    relative_anchor = None

    if explicit_updates:
        # Check if matched target name or generic keyword
        for k_upd, v_upd in explicit_updates.items():
            if k_upd.lower() in target["name"].lower() or target["name"].lower() in k_upd.lower():
                requested_slot = v_upd
                break
        if not requested_slot:
            requested_slot = next(iter(explicit_updates.values()))
    else:
        # Relative meal reference: "after my mitahara", "after lunch", "after dinner", "before dinner", "before lunch"
        rel_patterns = [
            (r"\b(?:after|following|post|right after)\s+(?:my\s+)?(mitahara|lunch|midday meal|dinner|early dinner|breakfast)", "after"),
            (r"\b(?:before|prior to|pre)\s+(?:my\s+)?(mitahara|lunch|midday meal|dinner|early dinner|breakfast)", "before")
        ]
        
        rel_match = None
        rel_dir = None
        for pattern, direction in rel_patterns:
            m = re.search(pattern, msg_lower)
            if m:
                rel_match = m.group(1).strip()
                rel_dir = direction
                break

        if rel_match:
            meal_practice = None
            for p in all_practices:
                p_l = p["name"].lower()
                if rel_match in p_l or ("mitahara" in rel_match and "mitahara" in p_l) or ("lunch" in rel_match and ("lunch" in p_l or "mitahara" in p_l)) or ("dinner" in rel_match and "dinner" in p_l):
                    meal_practice = p
                    break

            if meal_practice and meal_practice["time_slot"]:
                parsed = _parse_slot_minutes(meal_practice["time_slot"], meal_practice["duration_minutes"])
                if parsed:
                    m_start, m_end = parsed
                    dur = target["duration_minutes"]
                    if rel_dir == "after":
                        cand_start = m_end + 5
                        cand_end = cand_start + dur
                        requested_slot = _format_minutes_to_slot(cand_start, cand_end)
                        relative_anchor = f"immediately after '{meal_practice['name']}' ({meal_practice['time_slot']})"
                    elif rel_dir == "before":
                        cand_end = max(0, m_start - 5)
                        cand_start = max(0, cand_end - dur)
                        requested_slot = _format_minutes_to_slot(cand_start, cand_end)
                        relative_anchor = f"immediately before '{meal_practice['name']}' ({meal_practice['time_slot']})"

    if not requested_slot:
        return None

    return {
        "target_practice": target["name"],
        "original_time_slot": target["time_slot"],
        "target_block": target["block"],
        "requested_slot": requested_slot,
        "relative_anchor": relative_anchor,
        "duration_minutes": target["duration_minutes"]
    }


def formulate_canonical_proposal(
    user_id: int,
    target_practice: str,
    requested_slot: str,
    current_schedule: Dict[str, Any],
    profile: Optional[DoshaProfile] = None,
    symptoms: Optional[List[str]] = None,
    user_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates and persists a canonical ScheduleProposal in SQLite.
    Produces the validated preview proposed_schedule where target_practice
    is explicitly updated to proposed_time_slot, ensuring 100% agreement
    between the proposal object and the planner schedule preview.
    """
    state = db.get_user_state(user_id)
    sched_root = current_schedule.get("schedule", current_schedule)
    current_version = float(state.get("schedule_timestamp", 0.0))

    # Evaluate the requested slot with ClinicalRuleEngine
    eval_res = ClinicalRuleEngine.evaluate_reschedule_request(
        activity_name=target_practice,
        proposed_slot=requested_slot,
        current_schedule=current_schedule,
        profile=profile,
        symptoms=symptoms,
        use_llm=False,
        user_message=user_message
    )

    alts = eval_res.get("recommended_alternatives", [])
    
    if not eval_res["is_valid"]:
        best_alt = alts[0] if alts else {"proposed_slot": "18:30 - 18:45", "rationale": "Scheduled in safe empty-stomach window."}
        # If user asked for an 'after' slot, prioritize post-meal alternative
        if user_message and any(w in user_message.lower() for w in ["after", "post", "following"]):
            for a in alts:
                parsed_a = _parse_slot_minutes(a["proposed_slot"], 15)
                if parsed_a and parsed_a[0] >= 13 * 60:
                    best_alt = a
                    break
        proposed_slot = best_alt["proposed_slot"]
        rationale = best_alt.get("rationale", "Aligned with digestive and circadian guidelines.")
        clinical_explanation = eval_res.get("clinical_explanation", "")
        violated_principles = eval_res.get("violated_principles", [])
        is_clinically_valid = True
    else:
        proposed_slot = eval_res.get("proposed_slot") or requested_slot
        rationale = eval_res.get("clinical_explanation", "Valid temporal slot.")
        clinical_explanation = eval_res.get("clinical_explanation", "")
        violated_principles = []
        is_clinically_valid = True

    # Find original slot & block of target practice
    orig_slot = "Flexible"
    target_block = "morning_block"
    canonical_name = target_practice

    for blk_name in ["morning_block", "midday_block", "evening_block"]:
        for p in sched_root.get(blk_name, []):
            p_dict = p if isinstance(p, dict) else p.model_dump()
            nm = p_dict.get("name", "")
            if nm == target_practice or target_practice.lower() in nm.lower() or nm.lower() in target_practice.lower():
                canonical_name = nm
                orig_slot = p_dict.get("time_slot", "Flexible")
                target_block = blk_name
                break

    dest_proposal_block = get_destination_block(proposed_slot, fallback_block=target_block)
    proposal_id = f"prop_{user_id}_{int(time.time())}_{secrets.token_hex(4)}"

    proposal_dict = {
        "proposal_id": proposal_id,
        "user_id": str(user_id),
        "target_practice": canonical_name,
        "original_time_slot": orig_slot,
        "proposed_time_slot": standardize_slot(proposed_slot),
        "target_block": dest_proposal_block,
        "schedule_version": current_version,
        "status": "pending_user_confirmation",
        "rationale": rationale,
        "clinical_explanation": clinical_explanation,
        "violated_principles": violated_principles,
        "recommended_alternatives": alts,
        "is_valid": is_clinically_valid,
        "created_at": time.time()
    }

    # Persist proposal into SQLite
    db.save_schedule_proposal(proposal_dict)

    # Construct preview proposed_schedule with canonical cross-block relocation
    preview_blocks: Dict[str, List[Practice]] = {
        "morning_block": [],
        "midday_block": [],
        "evening_block": []
    }
    seen_preview_names = set()
    for blk_name in ["morning_block", "midday_block", "evening_block"]:
        for item in sched_root.get(blk_name, []) or []:
            p_d = item if isinstance(item, dict) else item.model_dump()
            p_nm = p_d.get("name", "Practice")
            p_nm_lower = p_nm.lower().strip()
            if p_nm_lower in seen_preview_names:
                continue
            seen_preview_names.add(p_nm_lower)

            if p_nm == canonical_name or canonical_name.lower() in p_nm_lower or p_nm_lower in canonical_name.lower():
                sl = proposed_slot
                desc = p_d.get("description", "")
                rat = f"{p_d.get('rationale', '')} [PROPOSED ADAPTATION: {rationale}]".strip()
                dest_blk = dest_proposal_block
            else:
                sl = p_d.get("time_slot", "Flexible")
                desc = p_d.get("description", "")
                rat = p_d.get("rationale", "")
                dest_blk = get_destination_block(sl, fallback_block=blk_name)

            preview_blocks[dest_blk].append(Practice(
                name=p_nm,
                time_slot=standardize_slot(sl),
                duration_minutes=int(p_d.get("duration_minutes", 15)),
                description=desc,
                rationale=rat
            ))

    for b in ["morning_block", "midday_block", "evening_block"]:
        def _sort_key(item: Practice) -> Tuple[int, str]:
            parsed = _parse_slot_minutes(item.time_slot, item.duration_minutes)
            return (parsed[0] if parsed else 9999, item.name)
        preview_blocks[b].sort(key=_sort_key)

    cand_sched = DinacharyaSchedule(
        user_id=str(user_id),
        adherence_score=float(state.get("adherence_score", 1.0)),
        routine_complexity=sched_root.get("routine_complexity", "Adaptive"),
        morning_block=preview_blocks["morning_block"],
        midday_block=preview_blocks["midday_block"],
        evening_block=preview_blocks["evening_block"],
        timestamp=time.time()
    )

    if profile:
        validated_cand = ClinicalRuleEngine.validate(cand_sched, profile)
        preview_schedule = validated_cand.model_dump()
    else:
        validated_cand = reblock_schedule_practices(cand_sched)
        preview_schedule = validated_cand.model_dump()

    return {
        "proposal": proposal_dict,
        "proposed_schedule": preview_schedule,
        "eval_res": eval_res
    }


def apply_canonical_proposal(
    user_id: int,
    proposal_id: str,
    expected_schedule_version: Optional[float] = None
) -> Dict[str, Any]:
    """
    Applies a pending schedule proposal canonically:
    - Validates ownership, proposal existence, and pending status.
    - Prevents stale overwrites: checks schedule_version against latest state.
    - Validates clinical safety before mutating.
    - Mutates strictly the target practice via mutate_user_schedule.
    - Updates proposal status to 'applied'.
    - Returns updated canonical schedule.
    """
    proposal = db.get_schedule_proposal(proposal_id)
    if not proposal:
        return {"success": False, "error": f"Proposal '{proposal_id}' not found.", "code": "NOT_FOUND"}

    if int(proposal["user_id"]) != user_id:
        return {"success": False, "error": "Unauthorized: Proposal belongs to another user.", "code": "FORBIDDEN"}

    status = proposal.get("status")
    if status == "applied":
        return {"success": False, "error": "Proposal has already been applied.", "code": "ALREADY_APPLIED"}
    elif status == "rejected":
        return {"success": False, "error": "Proposal was previously rejected / kept current.", "code": "REJECTED"}
    elif status == "stale":
        return {"success": False, "error": "Proposal is stale. Schedule has changed since it was created.", "code": "STALE"}
    elif status != "pending_user_confirmation":
        return {"success": False, "error": f"Proposal cannot be applied in status '{status}'.", "code": "INVALID_STATUS"}

    if proposal.get("is_valid") is False:
        db.update_proposal_status(proposal_id, "rejected_by_principles")
        return {"success": False, "error": "Cannot apply a contraindicated proposal.", "code": "CONTRAINDICATED"}

    # Stale version guard
    state = db.get_user_state(user_id)
    current_version = float(state.get("schedule_timestamp", 0.0))
    prop_version = float(proposal.get("schedule_version", 0.0))

    if expected_schedule_version is not None and abs(expected_schedule_version - current_version) > 1e-3:
        db.update_proposal_status(proposal_id, "stale")
        return {
            "success": False,
            "error": "Stale proposal: Schedule was modified after this proposal was created.",
            "code": "STALE_VERSION"
        }

    if prop_version > 0 and abs(prop_version - current_version) > 1e-3:
        db.update_proposal_status(proposal_id, "stale")
        return {
            "success": False,
            "error": "Stale proposal: Schedule was modified after this proposal was created.",
            "code": "STALE_VERSION"
        }

    # Clinical validation before mutation
    target_practice = proposal["target_practice"]
    proposed_slot = proposal["proposed_time_slot"]
    current_schedule = state.get("last_schedule")

    eval_res = ClinicalRuleEngine.evaluate_reschedule_request(
        activity_name=target_practice,
        proposed_slot=proposed_slot,
        current_schedule=current_schedule,
        use_llm=False
    )
    if not eval_res["is_valid"]:
        db.update_proposal_status(proposal_id, "rejected_by_principles")
        return {
            "success": False,
            "error": f"Clinical validation failed: {eval_res.get('clinical_explanation', 'Contraindicated slot.')}",
            "code": "CONTRAINDICATED"
        }

    # Mutate canonical schedule
    mut_res = mutate_user_schedule(
        user_id=user_id,
        updates={target_practice: proposed_slot}
    )
    if not mut_res.get("success"):
        db.update_proposal_status(proposal_id, "failed")
        return {
            "success": False,
            "error": mut_res.get("error", "Failed to persist schedule mutation."),
            "code": "MUTATION_FAILED"
        }

    # Mark proposal as applied
    db.update_proposal_status(proposal_id, "applied")

    updated_proposal = dict(proposal)
    updated_proposal["status"] = "applied"

    return {
        "success": True,
        "proposal_id": proposal_id,
        "proposal": updated_proposal,
        "schedule": mut_res["schedule"],
        "applied_updates": mut_res.get("applied_updates", {target_practice: proposed_slot}),
        "message": f"Successfully applied proposal {proposal_id}."
    }


def discard_canonical_proposal(user_id: int, proposal_id: str) -> Dict[str, Any]:
    """
    Discards a pending schedule proposal without mutating the user's schedule.
    """
    proposal = db.get_schedule_proposal(proposal_id)
    if not proposal:
        return {"success": False, "error": f"Proposal '{proposal_id}' not found.", "code": "NOT_FOUND"}

    if int(proposal["user_id"]) != user_id:
        return {"success": False, "error": "Unauthorized: Proposal belongs to another user.", "code": "FORBIDDEN"}

    db.update_proposal_status(proposal_id, "rejected")
    state = db.get_user_state(user_id)
    last_sched = state.get("last_schedule", {}).get("schedule") if state else None

    return {
        "success": True,
        "proposal_id": proposal_id,
        "status": "rejected",
        "schedule": last_sched,
        "message": "Proposal discarded. Schedule remains completely unchanged."
    }


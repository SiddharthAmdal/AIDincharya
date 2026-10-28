import json
import logging
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from src.knowledge.retriever import AyurvedaKnowledgeBase
from src.models import DoshaProfile, UserContext, DoshaVector, VikritiFlags
import src.database.db as db

logger = logging.getLogger("PlannerTools")


def get_weather_context(location: str) -> Dict[str, Any]:
    """
    Simulates querying a real-time Weather API to retrieve local environmental constraints.
    """
    loc = location.lower()
    if "bangalore" in loc or "bengaluru" in loc:
        return {
            "weather": "Mild, slightly humid with light wind",
            "temperature_c": 28.5,
            "humidity_percent": 60,
            "optimal_season": "Vasanta (Spring) / Summer transition"
        }
    elif "delhi" in loc:
        return {
            "weather": "Hot and dry with strong sunlight",
            "temperature_c": 41.2,
            "humidity_percent": 25,
            "optimal_season": "Grishma (Summer)"
        }
    else:
        return {
            "weather": "Pleasant and balanced",
            "temperature_c": 24.0,
            "humidity_percent": 50,
            "optimal_season": "Balanced"
        }


def _parse_time_to_minutes(time_str: str) -> Optional[int]:
    """Converts 'HH:MM' string to minutes from midnight."""
    match = re.search(r"(\d{1,2}):(\d{2})", time_str)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        return h * 60 + m
    return None


def check_calendar_conflicts(calendar_events: List[str], candidate_time_slot: str) -> bool:
    """
    Checks if a specific time slot (e.g., '07:00 - 08:00') conflicts with calendar busy events.
    Supports both time-overlap analysis and keyword analysis.
    """
    slot_lower = candidate_time_slot.lower()
    cand_parts = candidate_time_slot.split("-")
    cand_start = _parse_time_to_minutes(cand_parts[0]) if len(cand_parts) > 0 else None
    cand_end = _parse_time_to_minutes(cand_parts[1]) if len(cand_parts) > 1 else None

    for event in calendar_events:
        event_lower = event.lower()
        is_busy_keyword = any(kw in event_lower for kw in ["meeting", "call", "class", "standup", "doctor", "appointment"])

        # Look for time patterns in the event string like "08:00 - 09:00 Meeting"
        times = re.findall(r"(\d{1,2}:\d{2})", event)
        if len(times) >= 2 and cand_start is not None and cand_end is not None:
            ev_start = _parse_time_to_minutes(times[0])
            ev_end = _parse_time_to_minutes(times[1])
            if ev_start is not None and ev_end is not None:
                # Overlap if max(start1, start2) < min(end1, end2)
                if max(cand_start, ev_start) < min(cand_end, ev_end):
                    return True

        if is_busy_keyword:
            if len(times) == 1 and cand_start is not None:
                ev_time = _parse_time_to_minutes(times[0])
                if ev_time is not None and abs(ev_time - cand_start) < 60:
                    return True
            # Morning busy events overlap with typical morning practices
            if "09:00" in slot_lower or "08:00" in slot_lower:
                return True

    return False


def query_ayurvedic_knowledge(
    profile: Optional[DoshaProfile] = None,
    context: Optional[UserContext] = None,
    dosha: Optional[str] = None,
    symptom: Optional[str] = None,
    season: Optional[str] = None,
    activity: Optional[str] = None,
    query_text: Optional[str] = None,
    k: int = 4
) -> List[Dict[str, Any]]:
    """
    Primary tool to query the Ayurvedic RAG Knowledge Base.
    Bridges the perception and retrieval layers into the agent planning context.
    Supports both profile-based routine retrieval and targeted activity/timing principle retrieval.
    """
    kb = AyurvedaKnowledgeBase()

    if query_text:
        return kb.retrieve_by_query(query_text, k=k)

    if activity:
        adj_ctx = f"for {dosha or ''} {symptom or ''} during {season or ''}".strip()
        return kb.retrieve_for_reschedule(
            activity_name=activity,
            proposed_slot="requested time",
            adjacent_context=adj_ctx,
            profile=profile,
            k=k
        )

    if profile is None:
        p_vata = 0.6 if dosha and "vata" in dosha.lower() else 0.33
        p_pitta = 0.6 if dosha and "pitta" in dosha.lower() else 0.33
        p_kapha = 0.6 if dosha and "kapha" in dosha.lower() else 0.33
        v_vata = bool(dosha and "vata" in dosha.lower())
        v_pitta = bool(dosha and "pitta" in dosha.lower())
        v_kapha = bool(dosha and "kapha" in dosha.lower())
        profile = DoshaProfile(
            user_id="anonymous",
            prakriti=DoshaVector(vata=p_vata, pitta=p_pitta, kapha=p_kapha),
            vikriti_flags=VikritiFlags(vata_aggravated=v_vata, pitta_aggravated=v_pitta, kapha_aggravated=v_kapha),
            timestamp=time.time()
        )

    if context is None:
        symptoms = [symptom] if symptom else []
        context = UserContext(
            season=season or "Vasanta",
            weather="Pleasant",
            temperature_c=24.0,
            calendar_events=[],
            self_report_symptoms=symptoms
        )

    return kb.retrieve(profile, context, k=k)


def get_current_schedule(user_id: str) -> Dict[str, Any]:
    """
    Reads the user's current saved schedule from persistent storage.
    """
    try:
        uid_int = int(user_id)
        state = db.get_user_state(uid_int)
        last_sched = state.get("last_schedule")
        if isinstance(last_sched, dict):
            return last_sched
        return {"status": "no_schedule_found", "schedule": {}}
    except Exception as exc:
        logger.error(f"Error reading schedule for user {user_id}: {exc}")
        return {"error": str(exc), "schedule": {}}


def get_user_profile(user_id: str) -> Dict[str, Any]:
    """
    Retrieves the user's computed Ayurvedic profile, dosha vectors, and vikriti flags.
    """
    try:
        uid_int = int(user_id)
        state = db.get_user_state(uid_int)
        if not state:
            return {"user_id": user_id, "error": "User state not found"}
        
        q_resp = state.get("questionnaire_responses", {})
        telemetry = state.get("telemetry_baselines", {})
        vikriti = state.get("current_vikriti", {})
        symptoms = vikriti.get("symptoms", []) if isinstance(vikriti, dict) else []
        
        from src.perception.dosha_mapper import DoshaMapper
        profile = DoshaMapper.generate_profile(
            user_id=user_id,
            questionnaire=q_resp,
            telemetry=telemetry,
            symptoms={"self_reported": " ".join(symptoms)} if symptoms else None
        )
        from src.perception.wearable_interface import WearableTelemetryManager
        telemetry_summary = WearableTelemetryManager.get_user_telemetry_summary(uid_int)
        return {
            "user_id": user_id,
            "has_completed_onboarding": state.get("has_completed_onboarding", False),
            "adherence_score": state.get("adherence_score", 1.0),
            "prakriti": profile.prakriti.model_dump(),
            "vikriti_flags": profile.vikriti_flags.model_dump(),
            "symptoms": symptoms,
            "telemetry_summary": telemetry_summary
        }
    except Exception as exc:
        logger.error(f"Error fetching profile for user {user_id}: {exc}")
        return {"user_id": user_id, "error": str(exc)}


def get_adherence_history(user_id: str) -> Dict[str, Any]:
    """
    Retrieves the user's adherence tracking history, rolling score, and recommended complexity.
    """
    try:
        uid_int = int(user_id)
        state = db.get_user_state(uid_int)
        score = float(state.get("adherence_score", 1.0))
        completions = db.get_today_completions(uid_int)
        from src.behavior.tracker import AdherenceTracker
        complexity = AdherenceTracker.determine_complexity(score)
        nudge = AdherenceTracker.generate_behavior_nudge(score)
        return {
            "user_id": user_id,
            "adherence_score": score,
            "recommended_complexity": complexity,
            "today_completions": completions,
            "behavioral_nudge": nudge
        }
    except Exception as exc:
        logger.error(f"Error reading adherence history for user {user_id}: {exc}")
        return {"user_id": user_id, "error": str(exc)}


def validate_clinical_safety(
    user_id: str,
    candidate_schedule: Optional[Dict[str, Any]] = None,
    symptoms: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Validates a schedule against classical Ayurvedic contraindication rules independently of the LLM.
    """
    try:
        uid_int = int(user_id)
        state = db.get_user_state(uid_int)
        from src.perception.dosha_mapper import DoshaMapper
        from src.safety.guardrails import ClinicalRuleEngine
        from src.models import Practice, DinacharyaSchedule
        
        q_resp = state.get("questionnaire_responses", {})
        telemetry = dict(state.get("telemetry_baselines", {}))
        vikriti = state.get("current_vikriti", {})
        active_symptoms = list(symptoms or [])
        if isinstance(vikriti, dict):
            active_symptoms.extend(vikriti.get("symptoms", []))
            telemetry.update(vikriti.get("telemetry", {}))
        
        symptoms_map = {f"sym_{i}": s for i, s in enumerate(active_symptoms)} if active_symptoms else None
        profile = DoshaMapper.generate_profile(user_id, q_resp, telemetry, symptoms=symptoms_map)
        
        sched_data = candidate_schedule or state.get("last_schedule")
        if not sched_data or not isinstance(sched_data, dict):
            return {"is_safe": True, "message": "No active schedule to validate.", "overrides_applied": []}

        morning = [Practice(**p) if isinstance(p, dict) else p for p in sched_data.get("morning_block", [])]
        midday = [Practice(**p) if isinstance(p, dict) else p for p in sched_data.get("midday_block", [])]
        evening = [Practice(**p) if isinstance(p, dict) else p for p in sched_data.get("evening_block", [])]

        sched_obj = DinacharyaSchedule(
            user_id=user_id,
            adherence_score=state.get("adherence_score", 1.0),
            routine_complexity="Moderate",
            morning_block=morning,
            midday_block=midday,
            evening_block=evening,
            timestamp=time.time()
        )
        eval_result = ClinicalRuleEngine.evaluate_safety(sched_obj, profile, symptoms=active_symptoms)
        return {
            "is_safe": eval_result["is_safe"],
            "overrides_applied": eval_result["overrides_applied"],
            "rules_checked": eval_result["rules_checked"],
            "validated_schedule": eval_result["schedule"].model_dump()
        }
    except Exception as exc:
        logger.error(f"Error running safety validation for user {user_id}: {exc}")
        return {"is_safe": False, "error": str(exc), "overrides_applied": []}


def persist_schedule_adaptation(
    user_id: str,
    schedule: Dict[str, Any],
    date_str: Optional[str] = None
) -> Dict[str, Any]:
    """
    Persists a confirmed schedule adaptation after executing mandatory safety validation.
    Enforces canonical persistence format: {"schedule": ..., "dosha_profile": ...}.
    """
    try:
        uid_int = int(user_id)
        from src.planning.schedule_service import mutate_user_schedule

        # 1. Try to extract update pairs from any format the LLM emits
        updates = {}
        for block_key in ["morning_block", "midday_block", "evening_block"]:
            block_data = schedule.get(block_key, [])
            if isinstance(block_data, dict):
                for k, v in block_data.items():
                    # Handle {"20:00 - 20:30": "Light Early Dinner"} vs {"Light Early Dinner": "20:00 - 20:30"}
                    if any(c in str(k) for c in [":", "-"]) and not any(c in str(v) for c in [":", "-"]):
                        updates[str(v)] = str(k)
                    else:
                        updates[str(k)] = str(v)
            elif isinstance(block_data, list):
                for item in block_data:
                    if isinstance(item, dict) and "name" in item and "time_slot" in item:
                        updates[item["name"]] = item["time_slot"]

        if updates:
            mut_res = mutate_user_schedule(uid_int, updates, date_str=date_str)
            if mut_res.get("success"):
                return {
                    "success": True,
                    "user_id": user_id,
                    "persisted_date": mut_res["persisted_date"],
                    "schedule": mut_res["schedule"]
                }

        # 2. Fallback: Parse explicit schedule blocks and persist into canonical format
        state = db.get_user_state(uid_int)
        from src.perception.dosha_mapper import DoshaMapper
        from src.safety.guardrails import ClinicalRuleEngine
        from src.models import Practice, DinacharyaSchedule
        from src.planning.agent import standardize_slot

        q_resp = state.get("questionnaire_responses", {})
        telemetry = dict(state.get("telemetry_baselines", {}))
        vikriti = state.get("current_vikriti", {})
        active_symptoms = []
        if isinstance(vikriti, dict):
            active_symptoms.extend(vikriti.get("symptoms", []))
            telemetry.update(vikriti.get("telemetry", {}))

        symptoms_map = {f"sym_{i}": s for i, s in enumerate(active_symptoms)} if active_symptoms else None
        profile = DoshaMapper.generate_profile(user_id, q_resp, telemetry, symptoms=symptoms_map)

        def parse_safe_block(raw_val):
            out = []
            if isinstance(raw_val, dict):
                for k, v in raw_val.items():
                    slot = k if any(c in str(k) for c in [":", "-"]) else v
                    name = v if slot == k else k
                    out.append(Practice(
                        name=str(name),
                        time_slot=standardize_slot(str(slot)),
                        duration_minutes=15,
                        description="",
                        rationale=""
                    ))
            elif isinstance(raw_val, list):
                for p in raw_val:
                    if isinstance(p, Practice):
                        out.append(p)
                    elif isinstance(p, dict):
                        out.append(Practice(
                            name=p.get("name", "Practice"),
                            time_slot=standardize_slot(p.get("time_slot", "Flexible")),
                            duration_minutes=int(p.get("duration_minutes", 15)),
                            description=p.get("description", ""),
                            rationale=p.get("rationale", "")
                        ))
                    elif isinstance(p, str):
                        out.append(Practice(
                            name=p,
                            time_slot="Flexible",
                            duration_minutes=15,
                            description="",
                            rationale=""
                        ))
            return out

        sched_obj = DinacharyaSchedule(
            user_id=user_id,
            adherence_score=state.get("adherence_score", 1.0),
            routine_complexity="Moderate",
            morning_block=parse_safe_block(schedule.get("morning_block")),
            midday_block=parse_safe_block(schedule.get("midday_block")),
            evening_block=parse_safe_block(schedule.get("evening_block")),
            timestamp=time.time()
        )
        eval_result = ClinicalRuleEngine.evaluate_safety(sched_obj, profile, symptoms=active_symptoms)
        validated_dict = eval_result["schedule"].model_dump()

        target_date = date_str or time.strftime("%Y-%m-%d")
        canonical_data = {
            "schedule": validated_dict,
            "morning_block": validated_dict.get("morning_block", []),
            "midday_block": validated_dict.get("midday_block", []),
            "evening_block": validated_dict.get("evening_block", []),
            "dosha_profile": profile.model_dump(),
            "complexity_level": sched_obj.routine_complexity,
            "timestamp": time.time()
        }
        db.save_user_schedule(uid_int, canonical_data, target_date)

        idemp_key = f"adapt-persist-{uid_int}-{target_date}-{int(time.time() // 60)}"
        db.create_notification(
            user_id=uid_int,
            event_type="adaptation_confirmed",
            message=f"Your adapted routine for {target_date} has been confirmed and saved.",
            severity="info",
            channel="in_app",
            idempotency_key=idemp_key
        )

        # Optional Web Push dispatch (decoupled, non-blocking)
        try:
            from src.notifications.push_service import send_push_notification_to_user
            send_push_notification_to_user(
                user_id=uid_int,
                title="Ayurvedic Routine Synchronized",
                body=f"Your adapted routine for {target_date} has been confirmed and saved.",
                url="/routine",
                tag=idemp_key,
                extra_data={"event_type": "adaptation_confirmed", "date": target_date}
            )
        except Exception as push_err:
            logger.warning(f"Optional web push dispatch failed for user {uid_int}: {push_err}")

        return {
            "success": True,
            "user_id": user_id,
            "persisted_date": target_date,
            "schedule": validated_dict
        }
    except Exception as exc:
        logger.error(f"Error persisting adapted schedule for user {user_id}: {exc}")
        return {"success": False, "error": str(exc)}


def request_user_notification(
    user_id: str,
    event_type: str,
    message: str,
    activity_name: Optional[str] = None,
    new_time_slot: Optional[str] = None,
    severity: str = "info",
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a persistent in-app notification when a schedule change requires user awareness.
    Guarantees idempotency to avoid duplicate notifications.
    """
    try:
        uid_int = int(user_id)
        notif_id = db.create_notification(
            user_id=uid_int,
            event_type=event_type,
            message=message,
            activity_name=activity_name,
            new_time_slot=new_time_slot,
            severity=severity,
            channel="in_app",
            delivery_status="delivered",
            idempotency_key=idempotency_key
        )

        # Optional Web Push dispatch (decoupled, non-blocking)
        try:
            from src.notifications.push_service import send_push_notification_to_user
            send_push_notification_to_user(
                user_id=uid_int,
                title="Dinacharya Routine Reminder",
                body=message,
                url="/routine",
                tag=idempotency_key or f"reminder-{uid_int}",
                extra_data={"event_type": event_type, "activity_name": activity_name}
            )
        except Exception as p_err:
            logger.debug(f"Web Push delivery attempt encountered error (in-app preserved): {p_err}")

        return {
            "success": True,
            "notification_id": notif_id,
            "delivery_status": "delivered",
            "channel": "in_app"
        }
    except Exception as exc:
        logger.error(f"Failed to create notification: {exc}")
        return {"success": False, "error": str(exc)}


def propose_schedule_adaptation(
    user_id: str,
    change_type: str,
    affected_activity: str,
    new_slot: Optional[str] = None,
    rationale: str = "",
    current_schedule: Optional[Dict[str, Any]] = None,
    use_llm: bool = False
) -> Dict[str, Any]:
    """
    Validates a proposed schedule adaptation against classical Ayurvedic & Yogic principles
    (e.g., Bhuktavastu post-meal spacing, Kriya Krama ordering, Circadian Dosha Kala, and overlaps)
    and RAG grounding literature before committing.
    Enforces that proposals require explicit user confirmation before mutating vault state,
    and recommends reasoned alternative time slots if the requested slot violates principles.
    """
    if not affected_activity or not isinstance(affected_activity, str) or not affected_activity.strip():
        return {"valid": False, "error": "Missing required argument 'affected_activity'"}

    valid_change_types = {"reschedule", "skip", "shorten", "substitute"}
    if change_type not in valid_change_types:
        return {"valid": False, "error": f"Invalid change_type '{change_type}'. Must be one of {valid_change_types}"}

    from src.planning.agent import standardize_slot
    from src.safety.guardrails import ClinicalRuleEngine

    std_slot = standardize_slot(new_slot) if new_slot else None
    sched_to_check = current_schedule
    profile = None
    active_symptoms: List[str] = []

    if sched_to_check is None:
        try:
            uid_int = int(user_id)
            state = db.get_user_state(uid_int)
            if state:
                sched_to_check = state.get("last_schedule") or {}
                q_resp = state.get("questionnaire_responses", {})
                telemetry = dict(state.get("telemetry_baselines", {}))
                vikriti = state.get("current_vikriti", {})
                if isinstance(vikriti, dict):
                    active_symptoms.extend(vikriti.get("symptoms", []))
                    telemetry.update(vikriti.get("telemetry", {}))
                from src.perception.dosha_mapper import DoshaMapper
                symptoms_map = {f"sym_{i}": s for i, s in enumerate(active_symptoms)} if active_symptoms else None
                profile = DoshaMapper.generate_profile(str(user_id), q_resp, telemetry, symptoms=symptoms_map)
        except Exception as exc:
            logger.warning(f"Could not load user schedule/profile for proposal validation: {exc}")

    eval_res = ClinicalRuleEngine.evaluate_reschedule_request(
        activity_name=affected_activity,
        proposed_slot=std_slot or "",
        current_schedule=sched_to_check,
        profile=profile,
        symptoms=active_symptoms,
        change_type=change_type,
        use_llm=use_llm
    )

    if not eval_res["is_valid"]:
        alts = eval_res.get("recommended_alternatives", [])
        best_alt = alts[0]["proposed_slot"] if alts else None
        best_alt_why = alts[0]["rationale"] if alts else "Aligns with empty-stomach and circadian Dinacharya guidelines."
        return {
            "valid": False,
            "proposal_status": "rejected_by_principles",
            "user_id": user_id,
            "change_type": change_type,
            "affected_activity": affected_activity,
            "requested_slot": eval_res.get("proposed_slot") or std_slot,
            "proposed_slot": best_alt,
            "violated_principles": eval_res.get("violated_principles", []),
            "clinical_explanation": eval_res.get("clinical_explanation", ""),
            "retrieved_citations": eval_res.get("retrieved_citations", []),
            "recommended_alternatives": alts,
            "safety_checked": True,
            "instruction": (
                f"PRINCIPLE VALIDATION FAILED for '{affected_activity}' at {eval_res.get('proposed_slot') or std_slot}. "
                f"Do NOT approve {eval_res.get('proposed_slot') or std_slot}. "
                f"1. Explain to the user why {eval_res.get('proposed_slot') or std_slot} is contraindicated: {eval_res.get('clinical_explanation')} "
                f"2. Recommend the validated alternative slot **{best_alt}** ({best_alt_why}). "
                f"3. Ask clearly: 'I recommend scheduling {affected_activity} at **{best_alt}** instead. "
                f"Would you like me to confirm and update your daily routine to **{best_alt}**? "
                f"(Reply **Yes** to accept this recommended time, **No** to keep your current schedule unchanged, or share another time preference.)' "
                f"Append [RECALIBRATE] at the end of your message so the safe alternative ({best_alt}) is staged."
            )
        }

    final_slot = eval_res.get("proposed_slot") or std_slot
    return {
        "valid": True,
        "proposal_status": "pending_user_confirmation",
        "user_id": user_id,
        "change_type": change_type,
        "affected_activity": affected_activity,
        "proposed_slot": final_slot,
        "rationale": rationale or eval_res.get("clinical_explanation", ""),
        "clinical_explanation": eval_res.get("clinical_explanation", ""),
        "retrieved_citations": eval_res.get("retrieved_citations", []),
        "safety_checked": True,
        "instruction": (
            f"Present this validated schedule adjustment to the user for explicit confirmation. "
            f"Do NOT claim the change is already persisted or updated. "
            f"Ask the user: 'I propose moving {affected_activity} to {final_slot}. "
            f"Would you like me to confirm and update your daily routine? (Reply **Yes** to confirm, or **No** to keep your current schedule.)'"
        )
    }


# --- OpenAI-Compatible Tool Specifications for LLM Function Calling ---

AVAILABLE_PLANNER_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Retrieves the user's computed Ayurvedic phenotype (Prakriti), current health deviations (Vikriti), and active symptoms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user."}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_ayurvedic_knowledge",
            "description": "Retrieves classical Ayurvedic & Ministry of AYUSH guidelines from the RAG knowledge base for specific practices, timing rules, doshas, symptoms, or seasons.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dosha": {"type": "string", "description": "Dominant or aggravated dosha: 'Vata', 'Pitta', or 'Kapha'."},
                    "symptom": {"type": "string", "description": "Self-reported symptom such as 'fatigue', 'insomnia', 'fever', 'stress'."},
                    "season": {"type": "string", "description": "Current season: 'Vasanta' (Spring), 'Grishma' (Summer), 'Varsha' (Monsoon), 'Sharad' (Autumn), 'Hemanta' (Winter)."},
                    "activity": {"type": "string", "description": "Specific Dinacharya/Yogic practice to check timing and contraindication rules for (e.g. 'Pranayama', 'Snana', 'Abhyanga', 'Vyayama')."},
                    "query_text": {"type": "string", "description": "Custom semantic search query for the grounding knowledge base."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_schedule",
            "description": "Fetches the current active Dinacharya schedule and routines for a user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user."}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_calendar_conflicts",
            "description": "Checks whether a proposed time slot conflicts with existing calendar commitments or meetings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_time_slot": {"type": "string", "description": "The proposed time window, e.g. '07:00 - 07:30' or '08:00 - 09:00'."},
                    "calendar_events": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of calendar events, e.g. ['08:00 - 09:00 Team Standup']."
                    }
                },
                "required": ["candidate_time_slot", "calendar_events"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_schedule_adaptation",
            "description": "Validates a proposed schedule change against the user's current schedule, meal/digestion gaps (Bhuktavastu), and RAG grounding principles. If valid, stages the proposal for confirmation; if invalid, returns the violated principles and safe alternative time slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID."},
                    "change_type": {"type": "string", "enum": ["reschedule", "skip", "shorten", "substitute"], "description": "Type of schedule change."},
                    "affected_activity": {"type": "string", "description": "Name of the activity being adapted."},
                    "new_slot": {"type": "string", "description": "New requested time slot (e.g. '19:30 - 19:45' or '21:00 - 21:30')."},
                    "rationale": {"type": "string", "description": "Ayurvedic and logistical justification."}
                },
                "required": ["user_id", "change_type", "affected_activity"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_clinical_safety",
            "description": "Validates a candidate or modified schedule against deterministic Ayurvedic contraindication rules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID."},
                    "symptoms": {"type": "array", "items": {"type": "string"}, "description": "Active symptoms to check contraindications for."}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "persist_schedule_adaptation",
            "description": "Saves a confirmed schedule adaptation into persistent storage and triggers an in-app confirmation notification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID."},
                    "schedule": {"type": "object", "description": "The complete validated schedule dictionary to persist."},
                    "date_str": {"type": "string", "description": "Optional date string 'YYYY-MM-DD'."}
                },
                "required": ["user_id", "schedule"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_adherence_history",
            "description": "Reads the user's completion records, current adherence score, and behavioral recommendations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID."}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_user_notification",
            "description": "Creates an in-app user notification when a schedule is updated or an activity is rescheduled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The user ID to notify."},
                    "event_type": {"type": "string", "description": "Type of event: 'reschedule', 'alert', 'adaptation'."},
                    "message": {"type": "string", "description": "Clear explanation of the adjustment."},
                    "activity_name": {"type": "string", "description": "Name of the affected activity."},
                    "new_time_slot": {"type": "string", "description": "New time slot if rescheduled."},
                    "severity": {"type": "string", "enum": ["info", "warning", "critical"], "description": "Alert severity."}
                },
                "required": ["user_id", "event_type", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_telemetry",
            "description": "Retrieves the user's latest verified wearable biometric readings (heart rate, SpO2, steps, sleep status, stress status, device model, and measurement timestamps) from Android Health Connect.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user."}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_telemetry_reading",
            "description": "Retrieves the user's latest verified reading for a specific metric ('heart_rate', 'steps', 'spo2', 'sleep'). Returns exact measurement timestamp, ingestion timestamp, unit, and source provenance. For steps, distinguishes daily cumulative total from latest interval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user."},
                    "metric_type": {"type": "string", "enum": ["heart_rate", "steps", "spo2", "resting_hr", "sleep"], "description": "The specific metric to query."}
                },
                "required": ["user_id", "metric_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_telemetry_history_range",
            "description": "Retrieves historical telemetry summaries for a specific metric across a requested time range ('today', 'yesterday', 'last_24h', 'last_7d', 'last_30d', or custom start/end timestamps). For steps, calculates non-overlapping interval totals without inflating cumulative counts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user."},
                    "metric_type": {"type": "string", "enum": ["heart_rate", "steps", "spo2"], "description": "Metric to analyze."},
                    "period": {"type": "string", "enum": ["today", "yesterday", "last_24h", "last_7d", "last_30d"], "description": "Preset historical time range."},
                    "start_time": {"type": "string", "description": "Optional ISO or epoch start time for custom window."},
                    "end_time": {"type": "string", "description": "Optional ISO or epoch end time for custom window."}
                },
                "required": ["user_id", "metric_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_telemetry_periods",
            "description": "Compares biometrics between two time windows (e.g., 'today' vs 'yesterday', or 'last_7d' vs 'previous_7d'). Returns difference, percentage change, and circadian trend direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user."},
                    "metric_type": {"type": "string", "enum": ["heart_rate", "steps", "spo2"], "description": "Metric to compare."},
                    "period_1": {"type": "string", "description": "Primary period (e.g. 'today', 'last_7d')."},
                    "period_2": {"type": "string", "description": "Comparative baseline period (e.g. 'yesterday', 'previous_7d')."}
                },
                "required": ["user_id", "metric_type", "period_1", "period_2"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_activity_completion_evidence",
            "description": "Checks verified smartwatch telemetry evidence for a scheduled daily practice (such as Active Shathapavali ~100 brisk steps). Retrieves interval steps taken strictly during the scheduled activity window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user."},
                    "practice_name": {"type": "string", "description": "Name of the practice (e.g. 'Active Shathapavali')."},
                    "schedule_date": {"type": "string", "description": "Optional YYYY-MM-DD date (defaults to today)."}
                },
                "required": ["user_id", "practice_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "review_schedule_adherence",
            "description": "Reviews the user's activity lifecycle adherence over recent days, including auto-completed evidence, missed practices, and compensatory activities scheduled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user."},
                    "days": {"type": "integer", "description": "Number of days of history to review (default: 7)."}
                },
                "required": ["user_id"]
            }
        }
    }
]


def _resolve_period_timestamps(period: Optional[str], start_time: Optional[str] = None, end_time: Optional[str] = None) -> Tuple[float, float]:
    """Helper to convert human or ISO periods into epoch timestamps."""
    now = time.time()
    today_str = datetime.now().strftime("%Y-%m-%d")

    if start_time and end_time:
        try:
            s_ts = float(start_time) if start_time.replace('.', '', 1).isdigit() else datetime.fromisoformat(start_time).timestamp()
            e_ts = float(end_time) if end_time.replace('.', '', 1).isdigit() else datetime.fromisoformat(end_time).timestamp()
            return s_ts, e_ts
        except Exception:
            pass

    if period == "today":
        dt_start = datetime.strptime(f"{today_str} 00:00:00", "%Y-%m-%d %H:%M:%S")
        return dt_start.timestamp(), now
    elif period == "yesterday":
        yest_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        dt_start = datetime.strptime(f"{yest_str} 00:00:00", "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.strptime(f"{yest_str} 23:59:59", "%Y-%m-%d %H:%M:%S")
        return dt_start.timestamp(), dt_end.timestamp()
    elif period == "last_24h":
        return now - 86400.0, now
    elif period == "last_7d":
        return now - (7 * 86400.0), now
    elif period == "previous_7d":
        return now - (14 * 86400.0), now - (7 * 86400.0)
    elif period == "last_30d":
        return now - (30 * 86400.0), now
    else:
        # Default to last 24 hours
        return now - 86400.0, now


def execute_planner_tool(tool_name: str, args: Dict[str, Any], caller_user_id: Optional[str] = None) -> str:
    """
    Safely executes an authorized planner tool and returns a JSON string response.
    Enforces user authorization and input validation.
    """
    try:
        # Permission check: ensure user_id in args does not impersonate another user
        if caller_user_id:
            raw_arg_uid = str(args.get("user_id", "")).strip().lower()
            if raw_arg_uid in ("", "current_user", "me", "self", "authenticated_user"):
                args["user_id"] = str(caller_user_id)
            elif "user_id" in args and str(args["user_id"]) != str(caller_user_id):
                return json.dumps({"error": f"Permission denied: user_id '{args['user_id']}' mismatch with authenticated context '{caller_user_id}'."})

        effective_user_id = str(caller_user_id or args.get("user_id") or "1")
        u_id_int = int(effective_user_id)

        if tool_name == "get_user_profile":
            profile_data = get_user_profile(effective_user_id)
            return json.dumps(profile_data)

        elif tool_name == "query_ayurvedic_knowledge":
            guidelines = query_ayurvedic_knowledge(
                dosha=args.get("dosha"),
                symptom=args.get("symptom"),
                season=args.get("season"),
                activity=args.get("activity"),
                query_text=args.get("query_text"),
                k=3
            )
            return json.dumps({"retrieved_guidelines": guidelines})

        elif tool_name == "get_current_schedule":
            sched = get_current_schedule(effective_user_id)
            return json.dumps(sched)

        elif tool_name == "check_calendar_conflicts":
            events = args.get("calendar_events", [])
            slot = args.get("candidate_time_slot", "")
            has_conflict = check_calendar_conflicts(events, slot)
            return json.dumps({
                "candidate_time_slot": slot,
                "has_conflict": has_conflict,
                "conflicting_events": [e for e in events if check_calendar_conflicts([e], slot)] if has_conflict else []
            })

        elif tool_name == "propose_schedule_adaptation":
            res = propose_schedule_adaptation(
                user_id=effective_user_id,
                change_type=args.get("change_type", "reschedule"),
                affected_activity=args.get("affected_activity", ""),
                new_slot=args.get("new_slot"),
                rationale=args.get("rationale", "")
            )
            return json.dumps(res)

        elif tool_name == "validate_clinical_safety":
            res = validate_clinical_safety(
                user_id=effective_user_id,
                candidate_schedule=args.get("candidate_schedule"),
                symptoms=args.get("symptoms")
            )
            return json.dumps(res)

        elif tool_name == "persist_schedule_adaptation":
            sched_to_save = args.get("schedule", {})
            res = persist_schedule_adaptation(
                user_id=effective_user_id,
                schedule=sched_to_save,
                date_str=args.get("date_str")
            )
            return json.dumps(res)

        elif tool_name == "get_adherence_history":
            res = get_adherence_history(effective_user_id)
            return json.dumps(res)

        elif tool_name == "request_user_notification":
            res = request_user_notification(
                user_id=effective_user_id,
                event_type=args.get("event_type", "reschedule"),
                message=args.get("message", "Your schedule has been adapted."),
                activity_name=args.get("activity_name"),
                new_time_slot=args.get("new_time_slot"),
                severity=args.get("severity", "info"),
                idempotency_key=f"tool-{effective_user_id}-{args.get('event_type')}-{args.get('activity_name')}-{time.strftime('%Y%m%d%H%M')}"
            )
            return json.dumps(res)

        elif tool_name == "get_user_telemetry":
            from src.perception.wearable_interface import WearableTelemetryManager
            telemetry_data = WearableTelemetryManager.get_user_telemetry_summary(u_id_int)
            return json.dumps(telemetry_data)

        elif tool_name == "get_user_telemetry_reading":
            from src.perception.wearable_interface import WearableTelemetryManager
            m_type = args.get("metric_type", "heart_rate")
            summary = WearableTelemetryManager.get_user_telemetry_summary(u_id_int)
            metric_entry = summary.get("metrics", {}).get(m_type, {})
            result = {
                "user_id": u_id_int,
                "metric_type": m_type,
                "reading": metric_entry,
                "device_model": summary.get("device_model", "Fastrack Noir Charm"),
                "source_package": summary.get("source_package", "com.fastrack.smartworld"),
                "last_sync_timestamp": summary.get("last_ingested_at"),
                "is_upstream_stale": summary.get("is_upstream_stale", False)
            }
            if m_type == "steps":
                result["daily_total_steps"] = db.get_daily_steps(u_id_int)
                result["latest_interval_steps"] = metric_entry.get("latest_interval")
            elif m_type == "sleep":
                result["sleep_hours"] = metric_entry.get("value")
                result["sleep_status"] = metric_entry.get("status")
            return json.dumps(result)

        elif tool_name == "get_telemetry_history_range":
            m_type = args.get("metric_type", "steps")
            s_ts, e_ts = _resolve_period_timestamps(args.get("period"), args.get("start_time"), args.get("end_time"))
            summary = db.get_telemetry_window_summary(u_id_int, m_type, s_ts, e_ts)
            summary["period_label"] = args.get("period", "custom")
            summary["start_iso"] = datetime.fromtimestamp(s_ts).strftime("%Y-%m-%d %H:%M:%S")
            summary["end_iso"] = datetime.fromtimestamp(e_ts).strftime("%Y-%m-%d %H:%M:%S")
            return json.dumps(summary)

        elif tool_name == "compare_telemetry_periods":
            m_type = args.get("metric_type", "steps")
            p1_start, p1_end = _resolve_period_timestamps(args.get("period_1"))
            p2_start, p2_end = _resolve_period_timestamps(args.get("period_2"))

            w1 = db.get_telemetry_window_summary(u_id_int, m_type, p1_start, p1_end)
            w2 = db.get_telemetry_window_summary(u_id_int, m_type, p2_start, p2_end)

            if m_type == "steps":
                val1 = w1.get("total_steps", 0)
                val2 = w2.get("total_steps", 0)
            else:
                val1 = w1.get("avg") or 0.0
                val2 = w2.get("avg") or 0.0

            diff = val1 - val2
            pct_change = round((diff / val2 * 100.0), 1) if val2 > 0 else 0.0
            direction = "increased" if diff > 0 else ("decreased" if diff < 0 else "unchanged")

            return json.dumps({
                "metric_type": m_type,
                "period_1": {"name": args.get("period_1"), "value": val1, "records_count": w1.get("count")},
                "period_2": {"name": args.get("period_2"), "value": val2, "records_count": w2.get("count")},
                "absolute_difference": round(diff, 1),
                "percent_change": pct_change,
                "trend_direction": direction
            })

        elif tool_name == "get_activity_completion_evidence":
            p_name = args.get("practice_name", "")
            d_str = args.get("schedule_date") or datetime.now().strftime("%Y-%m-%d")

            # Check activity_lifecycle
            activities = db.get_user_activities(u_id_int, date_str=d_str)
            matching = [a for a in activities if p_name.lower() in a["practice_name"].lower()]

            if not matching:
                return json.dumps({
                    "status": "not_scheduled",
                    "practice_name": p_name,
                    "date": d_str,
                    "message": f"'{p_name}' was not found in the scheduled routine for {d_str}."
                })

            act = matching[0]
            start_ts = act["start_time_ts"]
            end_ts = act["end_time_ts"]

            # Query interval steps strictly during scheduled activity window
            interval_steps = db.get_interval_steps(u_id_int, start_ts, end_ts)

            # Auto-completion rule for Active Shathapavali (~100 brisk steps)
            is_shathapavali = "shathapavali" in p_name.lower() or "walk" in p_name.lower()
            threshold_met = interval_steps >= 100 if is_shathapavali else False

            evidence_result = {
                "activity_id": act["id"],
                "practice_name": act["practice_name"],
                "time_slot": act["time_slot"],
                "status": act["status"],
                "interval_steps_measured": interval_steps,
                "threshold_required": 100 if is_shathapavali else None,
                "is_evidence_sufficient": threshold_met,
                "completion_source": act.get("completion_source"),
                "completed_at": act.get("completed_at")
            }
            return json.dumps(evidence_result)

        elif tool_name == "review_schedule_adherence":
            days = int(args.get("days", 7))
            activities = []
            for i in range(days):
                day_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                activities.extend(db.get_user_activities(u_id_int, date_str=day_str))

            completed_user = len([a for a in activities if a["status"] == "completed_by_user"])
            auto_completed = len([a for a in activities if a["status"] == "auto_completed_evidence"])
            missed = len([a for a in activities if a["status"] == "missed"])
            compensated = len([a for a in activities if a["status"] in ("compensation_scheduled", "compensation_completed")])
            total = len(activities)

            from src.behavior.scoring import ScoringEngine
            completed_eligible = completed_user + auto_completed + compensated
            adh_res = ScoringEngine.calculate_adherence_score(completed_eligible, total)
            rate = adh_res["score"]

            return json.dumps({
                "user_id": u_id_int,
                "history_days": days,
                "total_scheduled_activities": total,
                "completed_manually": completed_user,
                "auto_completed_wearable_evidence": auto_completed,
                "missed_activities": missed,
                "compensations_scheduled": compensated,
                "adherence_percentage": rate,
                "scoring_formula": adh_res["formula"],
                "missed_activity_items": [
                    {"id": a["id"], "name": a["practice_name"], "date": a["schedule_date"], "slot": a["time_slot"]}
                    for a in activities if a["status"] == "missed"
                ][:5]
            })

        else:
            return json.dumps({"error": f"Unknown tool '{tool_name}'"})

    except Exception as exc:
        logger.error(f"Error executing tool {tool_name}: {exc}")
        return json.dumps({"error": f"Tool execution error: {str(exc)}"})


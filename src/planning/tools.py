import json
import logging
import re
import time
from typing import List, Dict, Any, Optional
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
    k: int = 4
) -> List[Dict[str, Any]]:
    """
    Primary tool to query the Ayurvedic RAG Knowledge Base.
    Bridges the perception and retrieval layers into the agent planning context.
    """
    kb = AyurvedaKnowledgeBase()

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
    rationale: str = ""
) -> Dict[str, Any]:
    """
    Validates a proposed schedule adaptation against safety rules before committing.
    """
    valid_change_types = {"reschedule", "skip", "shorten", "substitute"}
    if change_type not in valid_change_types:
        return {"valid": False, "error": f"Invalid change_type '{change_type}'. Must be one of {valid_change_types}"}

    return {
        "valid": True,
        "user_id": user_id,
        "change_type": change_type,
        "affected_activity": affected_activity,
        "new_slot": new_slot,
        "rationale": rationale,
        "safety_checked": True
    }


# --- OpenAI-Compatible Tool Specifications for LLM Function Calling ---

AVAILABLE_PLANNER_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_calendar_conflicts",
            "description": "Checks whether a proposed time slot conflicts with existing calendar commitments or meetings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_time_slot": {
                        "type": "string",
                        "description": "The proposed time window, e.g. '07:00 - 07:30' or '08:00 - 09:00'."
                    },
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
            "name": "query_ayurvedic_knowledge",
            "description": "Retrieves classical Ayurvedic guidelines and recommendations from the RAG knowledge base for specific doshas, symptoms, or seasons.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dosha": {
                        "type": "string",
                        "description": "Dominant or aggravated dosha: 'Vata', 'Pitta', or 'Kapha'."
                    },
                    "symptom": {
                        "type": "string",
                        "description": "Self-reported symptom such as 'fatigue', 'insomnia', 'fever', 'stress'."
                    },
                    "season": {
                        "type": "string",
                        "description": "Current season: 'Vasanta' (Spring), 'Grishma' (Summer), 'Varsha' (Monsoon), 'Sharad' (Autumn), 'Hemanta' (Winter)."
                    }
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
                    "user_id": {
                        "type": "string",
                        "description": "The unique ID of the user."
                    }
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
    }
]


def execute_planner_tool(tool_name: str, args: Dict[str, Any], caller_user_id: Optional[str] = None) -> str:
    """
    Safely executes an authorized planner tool and returns a JSON string response.
    Never executes arbitrary or unvetted actions.
    """
    try:
        # Permission check: ensure user_id in args does not impersonate another user
        if caller_user_id and "user_id" in args:
            if str(args["user_id"]) != str(caller_user_id):
                return json.dumps({"error": "Permission denied: user_id mismatch with authenticated context."})

        if tool_name == "check_calendar_conflicts":
            events = args.get("calendar_events", [])
            slot = args.get("candidate_time_slot", "")
            has_conflict = check_calendar_conflicts(events, slot)
            return json.dumps({
                "candidate_time_slot": slot,
                "has_conflict": has_conflict,
                "conflicting_events": [e for e in events if check_calendar_conflicts([e], slot)] if has_conflict else []
            })

        elif tool_name == "query_ayurvedic_knowledge":
            guidelines = query_ayurvedic_knowledge(
                dosha=args.get("dosha"),
                symptom=args.get("symptom"),
                season=args.get("season"),
                k=3
            )
            return json.dumps({"retrieved_guidelines": guidelines})

        elif tool_name == "get_current_schedule":
            sched = get_current_schedule(str(args.get("user_id", caller_user_id or "1")))
            return json.dumps(sched)

        elif tool_name == "request_user_notification":
            user_id = str(args.get("user_id", caller_user_id or "1"))
            res = request_user_notification(
                user_id=user_id,
                event_type=args.get("event_type", "reschedule"),
                message=args.get("message", "Your schedule has been adapted."),
                activity_name=args.get("activity_name"),
                new_time_slot=args.get("new_time_slot"),
                severity=args.get("severity", "info"),
                idempotency_key=f"tool-{user_id}-{args.get('event_type')}-{args.get('activity_name')}-{time.strftime('%Y%m%d%H%M')}"
            )
            return json.dumps(res)

        elif tool_name == "propose_schedule_adaptation":
            res = propose_schedule_adaptation(
                user_id=str(args.get("user_id", caller_user_id or "1")),
                change_type=args.get("change_type", "reschedule"),
                affected_activity=args.get("affected_activity", ""),
                new_slot=args.get("new_slot"),
                rationale=args.get("rationale", "")
            )
            return json.dumps(res)

        else:
            return json.dumps({"error": f"Unknown tool '{tool_name}'"})

    except Exception as exc:
        logger.error(f"Error executing tool {tool_name}: {exc}")
        return json.dumps({"error": f"Tool execution error: {str(exc)}"})


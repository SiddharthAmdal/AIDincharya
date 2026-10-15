import json
import logging
import re
import time
from datetime import datetime
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from src.config import DEFAULT_MODEL, FALLBACK_MODEL
from src.models import DoshaProfile, UserContext, Practice, DinacharyaSchedule
from src.knowledge.retriever import AyurvedaKnowledgeBase
from src.planning.tools import (
    query_ayurvedic_knowledge,
    check_calendar_conflicts,
    request_user_notification,
    AVAILABLE_PLANNER_TOOLS,
    execute_planner_tool
)
from src.llm_gateway import LLMGateway
import src.database.db as db

# Set up logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DinacharyaPlanner")


def standardize_slot(slot_str: str) -> str:
    """Standardizes time slots into strict 24-hour HH:MM - HH:MM format."""
    if not slot_str or not isinstance(slot_str, str):
        return slot_str or "Flexible"
    parts = re.split(r"\s*(?:-|–|—|to)\s*", slot_str.strip())
    if len(parts) == 2:
        def _to_24h(s):
            s = s.strip()
            m = re.match(r"^(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?$", s)
            if not m:
                return s
            h, mins, period = int(m.group(1)), m.group(2), m.group(3)
            if period:
                period = period.upper()
                if period == "PM" and h < 12:
                    h += 12
                elif period == "AM" and h == 12:
                    h = 0
            return f"{h:02d}:{mins}"

        start_raw, end_raw = parts[0], parts[1]
        end_period = re.search(r"(AM|PM|am|pm)$", end_raw, re.IGNORECASE)
        start_period = re.search(r"(AM|PM|am|pm)$", start_raw, re.IGNORECASE)
        if end_period and not start_period:
            start_raw = f"{start_raw} {end_period.group(1)}"
        return f"{_to_24h(start_raw)} - {_to_24h(end_raw)}"
    return slot_str


def extract_practice_time_updates(text: str, practice_names: List[str]) -> Dict[str, str]:
    """
    Extracts practice names and requested new time slots from proposal or directive text.
    Standardizes slots into 24h format (e.g. '22:15 - 22:30').
    """
    if not text:
        return {}
    updates = {}
    time_slot_regex = r"(?:(?:[01]?\d|2[0-3]):[0-5]\d\s*(?:AM|PM|am|pm)?\s*(?:-|–|—|to)\s*(?:[01]?\d|2[0-3]):[0-5]\d\s*(?:AM|PM|am|pm)?)"
    
    for p_name in practice_names:
        keywords = [k.strip() for k in re.split(r"[/()]", p_name) if len(k.strip()) >= 4]
        pattern = "|".join([re.escape(k) for k in keywords]) if keywords else re.escape(p_name)
        
        for line in text.split("\n"):
            if re.search(pattern, line, re.IGNORECASE):
                slots = re.findall(time_slot_regex, line)
                if slots:
                    updates[p_name] = standardize_slot(slots[-1])
                    break
    return updates


# Define State for our LangGraph planner
class AgentState(TypedDict):
    user_id: str
    profile: DoshaProfile
    context: UserContext
    adherence_score: float
    complexity: str
    retrieved_guidelines: List[Dict[str, Any]]
    completed_today: List[str]
    current_time: str
    user_instruction: Optional[str]
    current_schedule: Optional[Dict[str, Any]]
    morning_block: List[Practice]
    midday_block: List[Practice]
    evening_block: List[Practice]
    refinement_logs: List[str]
    error: Optional[str]
    is_fallback: bool
    model_used: str


class DinacharyaPlannerAgent:
    """
    Module 4: Agentic Planning Domain.
    Implements the Plan-and-Execute pattern using LangGraph and the centralized LLMGateway.
    """

    def __init__(self):
        self.gateway = LLMGateway.get_instance()
        self.openai_client = self.gateway.client  # backward compatibility
        self.kb = AyurvedaKnowledgeBase()

    def retrieve_guidelines_node(self, state: AgentState) -> AgentState:
        """
        Stage 1: Retrieval. Fetches top-k authentic Ayurvedic guidelines based on state.
        """
        logger.info(f"Retrieving classical guidelines for user {state['user_id']}")
        guidelines = query_ayurvedic_knowledge(profile=state["profile"], context=state["context"])
        state["retrieved_guidelines"] = guidelines
        return state

    def planner_node(self, state: AgentState) -> AgentState:
        """
        Stage 2: Plan. Calls the configured LLM to generate the raw daily routine blocks.
        """
        logger.info("Invoking LLMGateway to plan Dinacharya schedule")
        profile = state["profile"]
        context = state["context"]
        guidelines = state["retrieved_guidelines"]
        complexity = state["complexity"]
        completed_today = state.get("completed_today", [])
        current_time_str = state.get("current_time", "Unknown")
        user_instruction = state.get("user_instruction")
        current_schedule = state.get("current_schedule")

        guidelines_text = "\n".join([f"- {g['text']} (Source: {g.get('source', 'Ayurveda Core')})" for g in guidelines])
        completed_text = ", ".join(completed_today) if completed_today else "None yet"

        current_routine_text = "None"
        if current_schedule and isinstance(current_schedule, dict) and "schedule" in current_schedule:
            sched = current_schedule["schedule"]
            if isinstance(sched, dict):
                current_routine_text = ""
                for b in ["morning_block", "midday_block", "evening_block"]:
                    for p in sched.get(b, []):
                        if isinstance(p, dict):
                            current_routine_text += f"- {p.get('name', 'Practice')} ({p.get('time_slot', 'Flexible')})\n"

        if user_instruction:
            prompt = f"""You are an expert Ayurvedic Planner Agent. You are performing a CRITICAL RECALIBRATION.

USER DIRECTIVE / AGREED CHANGES (MANDATORY): {user_instruction}

ZERO-VARIANCE RULES:
1. You MUST extract every task name and every time slot mentioned in the 'AGREED PROPOSAL' or 'USER DIRECTIVE'.
2. You are FORBIDDEN from changing these times. If the agreement says "22:00 - 06:00", you MUST use "22:00 - 06:00".
3. Your primary goal is 100% synchronization with what the user and Vaidya AI just discussed.
4. Use your Ayurvedic knowledge ONLY to balance the non-conflicting parts of the day.

USER'S CURRENT SCHEDULE (TO BE MODIFIED):
{current_routine_text}

USER PROFILE:
- Prakriti: Vata {profile.prakriti.vata}, Pitta {profile.prakriti.pitta}, Kapha {profile.prakriti.kapha}
- Active Vikriti Flags: Vata Aggravated: {profile.vikriti_flags.vata_aggravated}, Pitta Aggravated: {profile.vikriti_flags.pitta_aggravated}, Kapha Aggravated: {profile.vikriti_flags.kapha_aggravated}

JSON STRUCTURE (Return ONLY valid JSON):
{{
  "morning_block": [ {{ "name": "...", "time_slot": "...", "duration_minutes": 15, "description": "...", "rationale": "..." }} ],
  "midday_block": [...],
  "evening_block": [...]
}}"""
        else:
            prompt = f"""You are an expert Ayurvedic Planner Agent. Generate a complete personalized Dinacharya (daily routine) schedule.

SYSTEM CLOCK: {current_time_str}
COMPLEXITY LEVEL: {complexity}
TASKS ALREADY COMPLETED TODAY: {completed_text}

AUTHENTIC AYURVEDIC GUIDELINES (from RAG Knowledge Base):
{guidelines_text}

USER PROFILE:
- Prakriti: Vata {profile.prakriti.vata}, Pitta {profile.prakriti.pitta}, Kapha {profile.prakriti.kapha}
- Active Vikriti Flags: Vata Aggravated: {profile.vikriti_flags.vata_aggravated}, Pitta Aggravated: {profile.vikriti_flags.pitta_aggravated}, Kapha Aggravated: {profile.vikriti_flags.kapha_aggravated}
- Season: {context.season}

INSTRUCTIONS:
1. Create a balanced daily routine with morning, midday, and evening blocks.
2. Each practice must have a specific time slot, duration, description, and Ayurvedic rationale.
3. Ground your recommendations in the retrieved guidelines above.
4. Do NOT include tasks the user has already completed today.
5. Adapt complexity: if '{complexity}', keep practices simple and few. If 'Advanced', include more specialized practices.

JSON STRUCTURE (Return ONLY valid JSON):
{{
  "morning_block": [ {{ "name": "...", "time_slot": "HH:MM - HH:MM", "duration_minutes": 15, "description": "...", "rationale": "..." }} ],
  "midday_block": [...],
  "evening_block": [...]
}}"""

        logger.info(f"RAG Context being sent to LLM: {len(guidelines)} guidelines. Already completed: {len(completed_today)} tasks.")

        def _get_fallback_data():
            state_copy = dict(state)
            self._fallback_planner(state_copy)
            return {
                "morning_block": [p.model_dump() for p in state_copy["morning_block"]],
                "midday_block": [p.model_dump() for p in state_copy["midday_block"]],
                "evening_block": [p.model_dump() for p in state_copy["evening_block"]],
            }

        try:
            plan_data, is_fallback = self.gateway.generate_structured_json(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise Ayurvedic routine parser. You output strict JSON. Keep internal reasoning concise. You prioritize user directives and agreed timings above all clinical defaults. You MUST NOT deviate from requested times."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2048,
                temperature=0.1,
                fallback_fn=_get_fallback_data
            )

            state["is_fallback"] = is_fallback
            state["model_used"] = self.gateway.fallback_model if is_fallback else self.gateway.primary_model

            def parse_block(block_name):
                practices = []
                for p in plan_data.get(block_name, []):
                    practices.append(Practice(
                        name=p.get("name", p.get("title", "Daily Practice")),
                        time_slot=standardize_slot(p.get("time_slot", "Flexible")),
                        duration_minutes=int(p.get("duration_minutes", 15)),
                        description=p.get("description", "Follow traditional guidelines."),
                        rationale=p.get("rationale", "Balances your constitution.")
                    ))
                return practices

            state["morning_block"] = parse_block("morning_block")
            state["midday_block"] = parse_block("midday_block")
            state["evening_block"] = parse_block("evening_block")

            # Zero-variance check: enforce any requested practice updates directly
            if user_instruction:
                all_practices = state["morning_block"] + state["midday_block"] + state["evening_block"]
                p_names = [p.name for p in all_practices]
                updates = extract_practice_time_updates(user_instruction, p_names)
                for blk in ["morning_block", "midday_block", "evening_block"]:
                    for p in state[blk]:
                        if p.name in updates:
                            p.time_slot = updates[p.name]

            total_practices = len(state["morning_block"]) + len(state["midday_block"]) + len(state["evening_block"])
            if total_practices == 0:
                raise ValueError("LLM returned an empty schedule.")

            logger.info(f"Successfully planned schedule with {total_practices} practices (Fallback: {is_fallback}, Model: {state['model_used']}).")

        except Exception as e:
            logger.error(f"LLM Planning Failed: {str(e)}. Falling back to deterministic rules.")
            state["error"] = str(e)
            state["is_fallback"] = True
            state["model_used"] = "deterministic_rules"
            return self._fallback_planner(state)

        return state

    def executor_node(self, state: AgentState) -> AgentState:
        """
        Stage 3: Execute/Refine.
        Inspects calendar commitments and adjusts practice timings dynamically to resolve overlaps.
        """
        logger.info("Executing timing refinements based on user's calendar constraints")
        calendar_events = state["context"].calendar_events
        if not calendar_events:
            return state

        for practice in state["morning_block"]:
            if check_calendar_conflicts(calendar_events, practice.time_slot):
                old_slot = practice.time_slot
                if "08:" in old_slot:
                    practice.time_slot = "07:00 - 07:20"
                elif "09:" in old_slot:
                    practice.time_slot = "07:30 - 07:50"

                log_msg = f"Shifted '{practice.name}' from {old_slot} to {practice.time_slot} due to calendar conflicts."
                state["refinement_logs"].append(log_msg)
                logger.info(log_msg)

        return state

    def _fallback_planner(self, state: AgentState) -> AgentState:
        """
        Deterministic, robust backup planner based on dominant Doshas and user instructions.
        """
        logger.info("Running deterministic Ayurvedic rule-based fallback planner")
        profile = state["profile"]
        complexity = state["complexity"]
        current_sched = state.get("current_schedule")
        user_inst = state.get("user_instruction")

        # If user has an existing schedule and we are executing an instruction, preserve existing blocks
        if current_sched and isinstance(current_sched, dict) and "schedule" in current_sched:
            sched_data = current_sched["schedule"]
            if isinstance(sched_data, dict):
                def to_p_list(raw_items):
                    out = []
                    for item in raw_items:
                        if isinstance(item, Practice):
                            out.append(item)
                        elif isinstance(item, dict):
                            out.append(Practice(
                                name=item.get("name", "Practice"),
                                time_slot=standardize_slot(item.get("time_slot", "Flexible")),
                                duration_minutes=int(item.get("duration_minutes", 15)),
                                description=item.get("description", ""),
                                rationale=item.get("rationale", "")
                            ))
                    return out

                state["morning_block"] = to_p_list(sched_data.get("morning_block", []))
                state["midday_block"] = to_p_list(sched_data.get("midday_block", []))
                state["evening_block"] = to_p_list(sched_data.get("evening_block", []))

                if user_inst:
                    all_p = state["morning_block"] + state["midday_block"] + state["evening_block"]
                    updates = extract_practice_time_updates(user_inst, [p.name for p in all_p])
                    for blk in ["morning_block", "midday_block", "evening_block"]:
                        for p in state[blk]:
                            if p.name in updates:
                                p.time_slot = updates[p.name]
                return state

        p = profile.prakriti
        scores = {"vata": p.vata, "pitta": p.pitta, "kapha": p.kapha}
        dominant = max(scores, key=scores.get)

        if complexity == "Anchor Habits":
            state["morning_block"] = [Practice(name="Brahma Muhurta Jagaran", time_slot="06:00 - 06:15", duration_minutes=15, description="Wake up at sunrise and drink a glass of warm water.", rationale="Waking up at a consistent hour is the single most effective anchor habit to settle Vata nervous system.")]
            state["midday_block"] = [Practice(name="Mitahara Midday Meal", time_slot="12:30 - 13:00", duration_minutes=30, description="Take a warm, freshly cooked lunch. Sit in silence without screens.", rationale="Eating the largest meal when the sun is highest optimizes Agni (digestion) for all constitutions.")]
            state["evening_block"] = [Practice(name="Sadhana Transition", time_slot="21:30 - 21:45", duration_minutes=15, description="Turn off screens and perform 5 minutes of deep breathing before sleep.", rationale="Calms the mind to facilitate deep restorative sleep and balances elevated Vata.")]
        elif dominant == "vata" or profile.vikriti_flags.vata_aggravated:
            state["morning_block"] = [
                Practice(name="Brahma Muhurta Jagaran", time_slot="06:00 - 06:15", duration_minutes=15, description="Wake up gently. Sit quietly and consume warm water.", rationale="Stabilizes Vata's volatile nature."),
                Practice(name="Abhyanga", time_slot="06:30 - 06:45", duration_minutes=15, description="Massage head and feet with warm sesame oil.", rationale="Warm sesame oil directly pacifies Vata's dry, cold qualities."),
                Practice(name="Pranayama", time_slot="07:00 - 07:15", duration_minutes=15, description="Practice 10 minutes of Nadi Shodhana (alternate nostril breathing).", rationale="Nadi Shodhana balances the nervous system and Vata flow.")
            ]
            state["midday_block"] = [Practice(name="Mitahara (Heaviest Meal)", time_slot="12:00 - 12:40", duration_minutes=40, description="Eat a nutritious, freshly cooked meal. Avoid cold drinks.", rationale="Agni (digestive fire) peaks at midday, enabling maximum nutrient absorption.")]
            state["evening_block"] = [
                Practice(name="Light Early Dinner", time_slot="19:00 - 19:30", duration_minutes=30, description="Consume a light, warm soup or khichdi.", rationale="Light meals at night prevent heavy Kapha accumulations and support sleep."),
                Practice(name="Trataka / Reflection", time_slot="21:30 - 21:45", duration_minutes=15, description="Dim lights, practice soft breathing, and prepare for rest.", rationale="Supports melatonin release and calms sensory organs.")
            ]
        elif dominant == "pitta" or profile.vikriti_flags.pitta_aggravated:
            state["morning_block"] = [
                Practice(name="Brahma Muhurta Jagaran", time_slot="05:30 - 05:45", duration_minutes=15, description="Wake up early before sunrise to capture cool morning energy.", rationale="Prevents overheating and early morning irritation."),
                Practice(name="Pranayama (Sheetali)", time_slot="06:30 - 06:45", duration_minutes=15, description="Practice Sheetali (cooling breath) to clear internal heat.", rationale="Sheetali breath is traditionally used to draw out excess Pitta heat.")
            ]
            state["midday_block"] = [Practice(name="Mitahara (Heaviest Meal)", time_slot="12:00 - 12:40", duration_minutes=40, description="Eat a nutritious, freshly cooked meal. Avoid cold drinks.", rationale="Agni (digestive fire) peaks at midday, enabling maximum nutrient absorption.")]
            state["evening_block"] = [
                Practice(name="Light Early Dinner", time_slot="19:00 - 19:30", duration_minutes=30, description="Consume a light, warm soup or khichdi.", rationale="Light meals at night prevent heavy Kapha accumulations and support sleep."),
                Practice(name="Trataka / Reflection", time_slot="21:30 - 21:45", duration_minutes=15, description="Dim lights, practice soft breathing, and prepare for rest.", rationale="Supports melatonin release and calms sensory organs.")
            ]
        else: # kapha
            state["morning_block"] = [
                Practice(name="Brahma Muhurta Jagaran", time_slot="05:00 - 05:15", duration_minutes=15, description="Wake up early. Do not sleep in past 6:00 AM.", rationale="Waking before the Kapha time of day (6 AM) prevents lethargy."),
                Practice(name="Dry Brushing / Udvartana", time_slot="05:30 - 05:50", duration_minutes=20, description="Perform dry massage/brushing towards the heart.", rationale="Stimulates sluggish lymphatic flow and pacifies Kapha's cold, heavy qualities.")
            ]
            state["midday_block"] = [Practice(name="Mitahara (Heaviest Meal)", time_slot="12:00 - 12:40", duration_minutes=40, description="Eat a nutritious, freshly cooked meal. Avoid cold drinks.", rationale="Agni (digestive fire) peaks at midday, enabling maximum nutrient absorption.")]
            state["evening_block"] = [
                Practice(name="Light Early Dinner", time_slot="19:00 - 19:30", duration_minutes=30, description="Consume a light, warm soup or khichdi.", rationale="Light meals at night prevent heavy Kapha accumulations and support sleep."),
                Practice(name="Trataka / Reflection", time_slot="21:30 - 21:45", duration_minutes=15, description="Dim lights, practice soft breathing, and prepare for rest.", rationale="Supports melatonin release and calms sensory organs.")
            ]

        # Apply any extracted time updates from user instruction if present
        if user_inst:
            all_p = state["morning_block"] + state["midday_block"] + state["evening_block"]
            updates = extract_practice_time_updates(user_inst, [p.name for p in all_p])
            for blk in ["morning_block", "midday_block", "evening_block"]:
                for p in state[blk]:
                    if p.name in updates:
                        p.time_slot = updates[p.name]

        return state

    def adapt_schedule(
        self,
        user_id: str,
        current_schedule: Dict[str, Any],
        event_type: str,
        event_data: Dict[str, Any],
        profile: DoshaProfile,
        context: UserContext,
        adherence_score: float = 1.0
    ) -> Dict[str, Any]:
        """
        Phase 5: Circumstance-Based Schedule Adaptation.
        Handles dynamic events with validation, deduplication, and notification dispatch:
        1. missed_activity: Gracefully handles missed task without duplicating or breaking day.
        2. calendar_conflict: Resolves meeting overlap while preserving commitments.
        3. fatigue / illness: Fever or exhaustion -> enforces safety boundaries and switches to Anchor Habits.
        4. task_overrun: Shifts subsequent flexible blocks proportionally.
        5. priority_change: Rebalances time towards user priority.
        6. infeasible_constraints: Detects impossible conditions and returns structured inability-to-plan.
        """
        logger.info(f"Adapting schedule for user {user_id} due to circumstance '{event_type}'")

        # Scenario 6: Infeasible Constraints Detection
        available_minutes = event_data.get("available_minutes")
        if event_type == "infeasible_constraints" or (available_minutes is not None and available_minutes < 30):
            return {
                "feasible": False,
                "status": "impossible_constraints",
                "message": "Cannot safely schedule routine: available time (under 30 mins) is insufficient to maintain minimum physiological practices.",
                "suggestions": [
                    "Increase available time window by at least 30 minutes",
                    "Switch to minimal 15-minute Anchor Habit (wake and hydrate only)",
                    "Postpone flexible practices to the following day"
                ],
                "schedule": None,
                "notification_sent": False
            }

        # Retrieve or construct base schedule blocks
        sched_root = current_schedule.get("schedule", current_schedule) if isinstance(current_schedule, dict) else {}
        morning = list(sched_root.get("morning_block", []))
        midday = list(sched_root.get("midday_block", []))
        evening = list(sched_root.get("evening_block", []))

        # Helper to convert dict practices to Practice models if needed
        def to_practice_list(raw_list):
            out = []
            for item in raw_list:
                if isinstance(item, Practice):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(Practice(
                        name=item.get("name", "Practice"),
                        time_slot=item.get("time_slot", "Flexible"),
                        duration_minutes=int(item.get("duration_minutes", 15)),
                        description=item.get("description", ""),
                        rationale=item.get("rationale", "")
                    ))
            return out

        m_prac = to_practice_list(morning)
        d_prac = to_practice_list(midday)
        e_prac = to_practice_list(evening)

        affected_activities = []
        change_rationale = ""
        notification_msg = ""
        severity = "info"

        # Scenario 3: Illness or Fatigue (Clinical Safety Rule)
        has_fever = profile.vikriti_flags.has_fever or event_data.get("has_fever", False) or "fever" in str(event_data).lower()
        if event_type in ("fatigue", "illness") or has_fever:
            severity = "warning" if has_fever else "info"
            change_rationale = (
                "Acute fever or elevated fatigue detected. Under classical Ayurvedic guidelines (Nava Jwara protocol), "
                "vigorous exercise, heavy oil massage, and large meals are paused to allow Agni to clear Ama."
            )
            # Replace morning with gentle rest and hydration
            m_prac = [
                Practice(
                    name="Ushnodaka & Rest",
                    time_slot="07:00 - 07:20",
                    duration_minutes=20,
                    description="Sip warm boiled water and rest in a well-ventilated, quiet room.",
                    rationale="Light warm water supports digestion and prevents thermal shock."
                )
            ]
            d_prac = [
                Practice(
                    name="Mitahara (Light Peya/Gruel)",
                    time_slot="12:30 - 13:00",
                    duration_minutes=30,
                    description="Consume light warm rice water or clear vegetable broth.",
                    rationale="Prevents digestive overload while providing basic energy."
                )
            ]
            e_prac = [
                Practice(
                    name="Early Restorative Sleep",
                    time_slot="20:30 - 21:00",
                    duration_minutes=30,
                    description="Dim lights and rest early to support physiological immunity.",
                    rationale="Deep sleep is the primary rejuvenator during acute imbalance."
                )
            ]
            affected_activities = ["All strenuous morning and midday practices"]
            notification_msg = "Your routine has been updated to restorative mode for recovery. Strenuous practices paused."

        # Scenario 2: Calendar Conflict
        elif event_type == "calendar_conflict":
            new_event = event_data.get("calendar_event", "08:00 - 09:00 Meeting")
            context.calendar_events.append(new_event)
            for p in m_prac:
                if check_calendar_conflicts([new_event], p.time_slot):
                    old_slot = p.time_slot
                    p.time_slot = "06:45 - 07:15"
                    affected_activities.append(p.name)
                    change_rationale += f"Shifted '{p.name}' from {old_slot} to {p.time_slot} to avoid conflict with '{new_event}'. "

            notification_msg = f"Routine adjusted to avoid conflict with '{new_event}'."

        # Scenario 1: Missed Activity
        elif event_type == "missed_activity":
            missed_name = event_data.get("activity_name", "")
            found = False
            for p in m_prac:
                if missed_name.lower() in p.name.lower():
                    found = True
                    affected_activities.append(p.name)
                    # Reallocate a shortened 15-minute gentle version into evening
                    e_prac.insert(0, Practice(
                        name=f"Compensatory {p.name}",
                        time_slot="18:30 - 18:45",
                        duration_minutes=15,
                        description=f"Gentle catch-up session for missed {p.name}.",
                        rationale="Restores constitutional balance without overburdening the morning."
                    ))
                    change_rationale = f"Missed '{p.name}' rescheduled to 18:30 in evening block."
                    break

            if not found:
                change_rationale = f"Missed activity '{missed_name}' acknowledged; remaining schedule preserved."
                affected_activities.append(missed_name)

            notification_msg = f"Missed '{missed_name}' has been adjusted in your daily plan."

        # Scenario 4: Task Overrun
        elif event_type == "task_overrun":
            overrun_name = event_data.get("activity_name", "Morning Work")
            overrun_mins = int(event_data.get("overrun_minutes", 30))
            change_rationale = f"Shifted afternoon practices by {overrun_mins} mins due to {overrun_name} overrun."
            affected_activities.append(overrun_name)
            # Shift midday practices
            for p in d_prac:
                old = p.time_slot
                p.time_slot = "13:15 - 13:45"
                p.rationale += f" (Shifted by {overrun_mins}m due to overrun)"
            notification_msg = f"Schedule updated: subsequent afternoon activities shifted by {overrun_mins} mins."

        # Scenario 5: Priority Change
        elif event_type == "priority_change":
            priority = event_data.get("priority", "Meditation")
            change_rationale = f"Rebalanced schedule to prioritize {priority}."
            affected_activities.append(priority)
            m_prac.insert(0, Practice(
                name=f"Focused {priority}",
                time_slot="06:00 - 06:40",
                duration_minutes=40,
                description=f"Dedicated deep session for {priority}.",
                rationale="Prioritizing morning Sattvic window enhances mental clarity and adherence."
            ))
            notification_msg = f"Your daily schedule has been rebalanced to prioritize {priority}."

        else:
            change_rationale = f"General adaptation applied for event '{event_type}'."
            notification_msg = "Your schedule has been synchronized."

        # Assemble new DinacharyaSchedule
        adapted_schedule = DinacharyaSchedule(
            user_id=str(user_id),
            adherence_score=adherence_score,
            routine_complexity="Adaptive",
            morning_block=m_prac,
            midday_block=d_prac,
            evening_block=e_prac,
            timestamp=time.time()
        )

        # Mandatory deterministic safety guardrail filter
        from src.safety.guardrails import ClinicalRuleEngine
        adapted_schedule = ClinicalRuleEngine.validate(adapted_schedule, profile)

        # Persist schedule update
        try:
            today_date = datetime.now().strftime('%Y-%m-%d')
            db.save_user_schedule(int(user_id), {"schedule": adapted_schedule.model_dump()}, today_date)
        except Exception as exc:
            logger.warning(f"Could not persist adapted schedule: {exc}")

        # Idempotent user notification
        idempotency_key = f"adapt-{user_id}-{event_type}-{'-'.join(affected_activities)[:30]}-{datetime.now().strftime('%Y%m%d%H%M')}"
        notif_res = request_user_notification(
            user_id=str(user_id),
            event_type=event_type,
            message=notification_msg or change_rationale,
            activity_name=", ".join(affected_activities) if affected_activities else None,
            severity=severity,
            idempotency_key=idempotency_key
        )

        return {
            "feasible": True,
            "status": "adapted",
            "adaptation_applied": True,
            "affected_activities": affected_activities,
            "rationale": change_rationale,
            "schedule": adapted_schedule,
            "notification_sent": notif_res.get("success", False),
            "notification_id": notif_res.get("notification_id")
        }

    def build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)
        workflow.add_node("retrieve", self.retrieve_guidelines_node)
        workflow.add_node("plan", self.planner_node)
        workflow.add_node("execute", self.executor_node)
        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "plan")
        workflow.add_edge("plan", "execute")
        workflow.add_edge("execute", END)
        return workflow.compile()

    def generate(
        self,
        user_id: str,
        profile: DoshaProfile,
        context: UserContext,
        adherence_score: float = 1.0,
        complexity: str = "Moderate",
        completed_today: List[str] = None,
        user_instruction: str = None,
        current_schedule: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        graph = self.build_graph()
        initial_state = AgentState(
            user_id=user_id,
            profile=profile,
            context=context,
            adherence_score=adherence_score,
            complexity=complexity,
            retrieved_guidelines=[],
            completed_today=completed_today or [],
            current_time=time.strftime("%Y-%m-%d %H:%M:%S"),
            user_instruction=user_instruction,
            current_schedule=current_schedule,
            morning_block=[],
            midday_block=[],
            evening_block=[],
            refinement_logs=[],
            error=None,
            is_fallback=False,
            model_used=self.gateway.primary_model
        )
        final_state = graph.invoke(initial_state)
        schedule = DinacharyaSchedule(
            user_id=user_id,
            adherence_score=adherence_score,
            routine_complexity=complexity,
            morning_block=final_state["morning_block"],
            midday_block=final_state["midday_block"],
            evening_block=final_state["evening_block"],
            timestamp=time.time()
        )
        return {
            "schedule": schedule,
            "retrieved_guidelines": final_state.get("retrieved_guidelines", []),
            "is_fallback": final_state.get("is_fallback", False),
            "model_used": final_state.get("model_used", self.gateway.primary_model),
            "refinement_logs": final_state.get("refinement_logs", [])
        }


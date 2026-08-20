import json
import logging
import re
import time
from typing import TypedDict, List, Dict, Any, Optional
from openai import OpenAI
from langgraph.graph import StateGraph, END
from src.config import (
    DEFAULT_MODEL,
    GEMINI_API_KEYS,
    GEMINI_BASE_URL,
    LLM_PROVIDER,
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    PUTER_API_KEY,
    PUTER_BASE_URL,
)
from src.llm_client import build_llm_client
from src.models import DoshaProfile, UserContext, Practice, DinacharyaSchedule
from src.knowledge.retriever import AyurvedaKnowledgeBase
from src.planning.tools import query_ayurvedic_knowledge, check_calendar_conflicts

# Set up logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DinacharyaPlanner")


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


class DinacharyaPlannerAgent:
    """
    Module 4: Agentic Planning Domain.
    Implements the Plan-and-Execute pattern using LangGraph and an LLM provider (NVIDIA NIM).
    """

    def __init__(self):
        self.openai_client = build_llm_client(
            provider=LLM_PROVIDER,
            default_model=DEFAULT_MODEL,
            gemini_base_url=GEMINI_BASE_URL,
            gemini_api_keys=GEMINI_API_KEYS,
            openrouter_base_url=OPENROUTER_BASE_URL,
            openrouter_api_key=OPENROUTER_API_KEY,
            openrouter_model=OPENROUTER_MODEL,
            puter_base_url=PUTER_BASE_URL,
            puter_api_key=PUTER_API_KEY,
            nvidia_base_url=NVIDIA_BASE_URL,
            nvidia_api_key=NVIDIA_API_KEY,
        )
        self.kb = AyurvedaKnowledgeBase()

    def retrieve_guidelines_node(self, state: AgentState) -> AgentState:
        """
        Stage 1: Retrieval. Fetches top-k authentic Ayurvedic guidelines based on state.
        """
        logger.info(f"Retrieving classical guidelines for user {state['user_id']}")
        guidelines = query_ayurvedic_knowledge(state["profile"], state["context"])
        state["retrieved_guidelines"] = guidelines
        return state

    def planner_node(self, state: AgentState) -> AgentState:
        """
        Stage 2: Plan. Calls the configured LLM to generate the raw daily routine blocks.
        """
        logger.info("Invoking LLM to plan Dinacharya schedule")
        profile = state["profile"]
        context = state["context"]
        guidelines = state["retrieved_guidelines"]
        complexity = state["complexity"]
        completed_today = state.get("completed_today", [])
        current_time_str = state.get("current_time", "Unknown")
        user_instruction = state.get("user_instruction")
        current_schedule = state.get("current_schedule")

        # 1. Compile details about the user for the prompt
        guidelines_text = "\n".join([f"- {g['text']} (Source: {g['source']})" for g in guidelines])
        completed_text = ", ".join(completed_today) if completed_today else "None yet"

        current_routine_text = "None"
        if current_schedule and "schedule" in current_schedule:
            sched = current_schedule["schedule"]
            current_routine_text = ""
            for b in ["morning_block", "midday_block", "evening_block"]:
                for p in sched.get(b, []):
                    current_routine_text += f"- {p['name']} ({p['time_slot']})\n"

        # 2. Build prompt: use different prompts for normal generation vs recalibration
        if user_instruction:
            # RECALIBRATION mode: user/Vaidya AI requested specific changes
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
            # NORMAL generation mode: generate a fresh daily Dinacharya
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
        
        try:
            chat_completion = self.openai_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a precise Ayurvedic routine parser. You output strict JSON. You prioritize user directives and agreed timings above all clinical defaults. You MUST NOT deviate from requested times."},
                    {"role": "user", "content": prompt}
                ],
                model=DEFAULT_MODEL,
                temperature=0.0, # Zero temperature for absolute precision
                response_format={"type": "json_object"}
            )
            raw_response = chat_completion.choices[0].message.content
            logger.info(f"Raw LLM Response (truncated): {raw_response[:250]}...")
            
            clean_json = re.sub(r"^```json\s*|\s*```$", "", raw_response.strip(), flags=re.MULTILINE)
            plan = json.loads(clean_json)

            def parse_block(block_name):
                practices = []
                for p in plan.get(block_name, []):
                    # Ensure all fields exist with defaults to avoid Pydantic errors
                    practices.append(Practice(
                        name=p.get("name", p.get("title", "Daily Practice")),
                        time_slot=p.get("time_slot", "Flexible"),
                        duration_minutes=int(p.get("duration_minutes", 15)),
                        description=p.get("description", "Follow traditional guidelines."),
                        rationale=p.get("rationale", "Balances your constitution.")
                    ))
                return practices

            state["morning_block"] = parse_block("morning_block")
            state["midday_block"] = parse_block("midday_block")
            state["evening_block"] = parse_block("evening_block")
            
            total_practices = len(state["morning_block"]) + len(state["midday_block"]) + len(state["evening_block"])
            if total_practices == 0:
                raise ValueError("LLM returned an empty schedule.")
                
            logger.info(f"Successfully planned schedule with {total_practices} dynamic practices.")
        except Exception as e:
            logger.error(f"LLM Planning Failed: {str(e)}. Falling back to rules.")
            state["error"] = str(e)
            return self._fallback_planner(state)

        return state

    def executor_node(self, state: AgentState) -> AgentState:
        """
        Stage 3: Execute/Refine.
        Inspects calendar commitments and adjusts practice timings where necessary to resolve overlaps.
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
        Deterministic, robust backup planner based on dominant Doshas.
        """
        logger.info("Running deterministic Ayurvedic rule-based fallback planner")
        profile = state["profile"]
        complexity = state["complexity"]
        p = profile.prakriti
        scores = {"vata": p.vata, "pitta": p.pitta, "kapha": p.kapha}
        dominant = max(scores, key=scores.get)

        if complexity == "Anchor Habits":
            state["morning_block"] = [Practice(name="Brahma Muhurta Jagaran", time_slot="06:00 - 06:15", duration_minutes=15, description="Wake up at sunrise and drink a glass of warm water.", rationale="Waking up at a consistent hour is the single most effective anchor habit to settle Vata nervous system.")]
            state["midday_block"] = [Practice(name="Mitahara Midday Meal", time_slot="12:30 - 13:00", duration_minutes=30, description="Take a warm, freshly cooked lunch. Sit in silence without screens.", rationale="Eating the largest meal when the sun is highest optimizes Agni (digestion) for all constitutions.")]
            state["evening_block"] = [Practice(name="Sadhana Transition", time_slot="21:30 - 21:45", duration_minutes=15, description="Turn off screens and perform 5 minutes of deep breathing before sleep.", rationale="Calms the mind to facilitate deep restorative sleep and balances elevated Vata.")]
            return state

        if dominant == "vata" or profile.vikriti_flags.vata_aggravated:
            state["morning_block"] = [Practice(name="Brahma Muhurta Jagaran", time_slot="06:00 - 06:15", duration_minutes=15, description="Wake up gently. Sit quietly and consume warm water.", rationale="Stabilizes Vata's volatile nature."), Practice(name="Abhyanga", time_slot="06:30 - 06:45", duration_minutes=15, description="Massage head and feet with warm sesame oil.", rationale="Warm sesame oil directly pacifies Vata's dry, cold qualities."), Practice(name="Pranayama", time_slot="07:00 - 07:15", duration_minutes=15, description="Practice 10 minutes of Nadi Shodhana (alternate nostril breathing).", rationale="Nadi Shodhana balances the nervous system and Vata flow.")]
        elif dominant == "pitta" or profile.vikriti_flags.pitta_aggravated:
            state["morning_block"] = [Practice(name="Brahma Muhurta Jagaran", time_slot="05:30 - 05:45", duration_minutes=15, description="Wake up early before sunrise to capture cool morning energy.", rationale="Prevents overheating and early morning irritation."), Practice(name="Pranayama (Sheetali)", time_slot="06:30 - 06:45", duration_minutes=15, description="Practice Sheetali (cooling breath) to clear internal heat.", rationale="Sheetali breath is traditionally used to draw out excess Pitta heat.")]
        else: # kapha
            state["morning_block"] = [Practice(name="Brahma Muhurta Jagaran", time_slot="05:00 - 05:15", duration_minutes=15, description="Wake up early. Do not sleep in past 6:00 AM.", rationale="Waking before the Kapha time of day (6 AM) prevents lethargy."), Practice(name="Dry Brushing / Udvartana", time_slot="05:30 - 05:50", duration_minutes=20, description="Perform dry massage/brushing towards the heart.", rationale="Stimulates sluggish lymphatic flow and pacifies Kapha's cold, heavy qualities.")]

        state["midday_block"] = [Practice(name="Mitahara (Heaviest Meal)", time_slot="12:00 - 12:40", duration_minutes=40, description="Eat a nutritious, freshly cooked meal. Avoid cold drinks.", rationale="Agni (digestive fire) peaks at midday, enabling maximum nutrient absorption.")]
        state["evening_block"] = [Practice(name="Light Early Dinner", time_slot="19:00 - 19:30", duration_minutes=30, description="Consume a light, warm soup or khichdi.", rationale="Light meals at night prevent heavy Kapha accumulations and support sleep."), Practice(name="Trataka / Reflection", time_slot="21:30 - 21:45", duration_minutes=15, description="Dim lights, practice soft breathing, and prepare for rest.", rationale="Supports melatonin release and calms sensory organs.")]
        return state

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
            error=None
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
        return {"schedule": schedule, "retrieved_guidelines": final_state["retrieved_guidelines"]}

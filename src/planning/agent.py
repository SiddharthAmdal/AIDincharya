import json
import logging
import re
from typing import TypedDict, List, Dict, Any, Optional
from openai import OpenAI
from langgraph.graph import StateGraph, END
from src.config import PUTER_BASE_URL, PUTER_API_KEY, DEFAULT_MODEL
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
    morning_block: List[Practice]
    midday_block: List[Practice]
    evening_block: List[Practice]
    refinement_logs: List[str]
    error: Optional[str]


class DinacharyaPlannerAgent:
    """
    Module 4: Agentic Planning Domain.
    Implements the Plan-and-Execute pattern using LangGraph and Puter AI bridge.
    """

    def __init__(self):
        # Initialize OpenAI client pointed to Puter AI Bridge
        self.openai_client = OpenAI(
            base_url=PUTER_BASE_URL,
            api_key=PUTER_API_KEY
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
        Stage 2: Plan. Calls Puter AI's LLM to generate the raw daily routine blocks.
        """
        logger.info("Invoking Puter AI bridged LLM to plan Dinacharya schedule")
        profile = state["profile"]
        context = state["context"]
        guidelines = state["retrieved_guidelines"]
        complexity = state["complexity"]

        # 1. Compile details about the user for the prompt
        guidelines_text = "\n".join([f"- {g['text']} (Source: {g['source']})" for g in guidelines])
        
        prompt = f"""
You are an expert Ayurvedic Physician (Vaidya). Generate a highly personalized 24-hour daily Dinacharya schedule based on the following:

USER DETAILS:
- Prakriti (Baseline Doshas): Vata {profile.prakriti.vata}, Pitta {profile.prakriti.prakriti().pitta if hasattr(profile.prakriti, 'prakriti') else profile.prakriti.pitta}, Kapha {profile.prakriti.kapha}
- Active Vikriti (Imbalances): Vata Aggravated: {profile.vikriti_flags.vata_aggravated}, Pitta Aggravated: {profile.vikriti_flags.pitta_aggravated}, Kapha Aggravated: {profile.vikriti_flags.kapha_aggravated}, Active Fever (Nava Jwara): {profile.vikriti_flags.has_fever}
- Adherence Score (S_adj): {state['adherence_score']} (Current Routine Complexity: {complexity})

LOCAL ENVIRONMENTAL CONTEXT:
- Season: {context.season}
- Weather: {context.weather} (Temperature: {context.temperature_c}°C)
- Reported Symptoms: {', '.join(context.self_report_symptoms) if context.self_report_symptoms else 'None'}

CLASSICAL RETRIEVED GUIDELINES:
{guidelines_text}

INSTRUCTIONS:
1. Decompose the day into 3 distinct chronological blocks: Morning, Midday, Evening.
2. For each block, recommend 2 to 3 classical practices.
3. For each practice, specify:
   - "name": Clean Ayurvedic term (e.g. "Abhyanga", "Brahma Muhurta Jagaran", "Nasya", "Yoga & Pranayama")
   - "time_slot": Assign a specific time range (e.g. "06:00 - 06:20")
   - "duration_minutes": Duration of the task
   - "description": Simple, actionable traditional instructions
   - "rationale": Clear plain-language explanation of how it balances their specific dominant dosha or active Vikriti deviation.
4. If complexity is "Anchor Habits", keep the routine highly simplified with only 3 key practices overall.

Return ONLY a valid JSON object matching this structure:
{{
  "morning_block": [
    {{
      "name": "...",
      "time_slot": "...",
      "duration_minutes": 15,
      "description": "...",
      "rationale": "..."
    }}
  ],
  "midday_block": [...],
  "evening_block": [...]
}}
Do NOT include markdown wrapping or extra conversational text.
"""
        # If API key is placeholder or default, skip LLM call and use fallback directly
        if PUTER_API_KEY == "placeholder_token":
            logger.info("Using placeholder token. Activating robust fallback planner directly.")
            return self._fallback_planner(state)

        try:
            chat_completion = self.openai_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful, traditional Ayurvedic agent planner. You output only strict JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=DEFAULT_MODEL,
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            raw_response = chat_completion.choices[0].message.content
            # Clean markdown codeblocks if returned
            clean_json = re.sub(r"^```json\s*|\s*```$", "", raw_response.strip(), flags=re.MULTILINE)
            plan = json.loads(clean_json)

            # Map the parsed JSON lists to Pydantic Practice models
            state["morning_block"] = [Practice(**p) for p in plan.get("morning_block", [])]
            state["midday_block"] = [Practice(**p) for p in plan.get("midday_block", [])]
            state["evening_block"] = [Practice(**p) for p in plan.get("evening_block", [])]
            
            logger.info("Successfully planned Dinacharya schedule via Puter AI")
        except Exception as e:
            logger.error(f"Puter AI LLM call failed or returned invalid JSON ({str(e)}). Falling back to rule-based planner.")
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

        # If user has a busy morning meeting (e.g. "9 AM meeting" or "9:00 - 10:00 class"),
        # shift any conflicting morning practices to occur earlier (e.g. 7 AM)
        for practice in state["morning_block"]:
            if check_calendar_conflicts(calendar_events, practice.time_slot):
                old_slot = practice.time_slot
                # Slide slot 1 hour earlier
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
        Ensures the system never breaks and returns fully compliant schedules.
        """
        logger.info("Running deterministic Ayurvedic rule-based fallback planner")
        profile = state["profile"]
        complexity = state["complexity"]

        # Establish dominant dosha
        p = profile.prakriti
        scores = {"vata": p.vata, "pitta": p.pitta, "kapha": p.kapha}
        dominant = max(scores, key=scores.get)

        if complexity == "Anchor Habits":
            # Highly simplified routine (3 tasks)
            state["morning_block"] = [
                Practice(
                    name="Brahma Muhurta Jagaran",
                    time_slot="06:00 - 06:15",
                    duration_minutes=15,
                    description="Wake up at sunrise and drink a glass of warm water.",
                    rationale="Waking up at a consistent hour is the single most effective anchor habit to settle Vata nervous system."
                )
            ]
            state["midday_block"] = [
                Practice(
                    name="Mitahara Midday Meal",
                    time_slot="12:30 - 13:00",
                    duration_minutes=30,
                    description="Take a warm, freshly cooked lunch. Sit in silence without screens.",
                    rationale="Eating the largest meal when the sun is highest optimizes Agni (digestion) for all constitutions."
                )
            ]
            state["evening_block"] = [
                Practice(
                    name="Sadhana Transition",
                    time_slot="21:30 - 21:45",
                    duration_minutes=15,
                    description="Turn off screens and perform 5 minutes of deep breathing before sleep.",
                    rationale="Calms the mind to facilitate deep restorative sleep and balances elevated Vata."
                )
            ]
            return state

        # Moderate/Standard routine based on dominant Dosha
        if dominant == "vata" or profile.vikriti_flags.vata_aggravated:
            state["morning_block"] = [
                Practice(
                    name="Brahma Muhurta Jagaran",
                    time_slot="06:00 - 06:15",
                    duration_minutes=15,
                    description="Wake up gently. Sit quietly and consume warm water.",
                    rationale="Stabilizes Vata's volatile nature."
                ),
                Practice(
                    name="Abhyanga",
                    time_slot="06:30 - 06:45",
                    duration_minutes=15,
                    description="Massage head and feet with warm sesame oil.",
                    rationale="Warm sesame oil directly pacifies Vata's dry, cold qualities."
                ),
                Practice(
                    name="Pranayama",
                    time_slot="07:00 - 07:15",
                    duration_minutes=15,
                    description="Practice 10 minutes of Nadi Shodhana (alternate nostril breathing).",
                    rationale="Nadi Shodhana balances the nervous system and Vata flow."
                )
            ]
        elif dominant == "pitta" or profile.vikriti_flags.pitta_aggravated:
            state["morning_block"] = [
                Practice(
                    name="Brahma Muhurta Jagaran",
                    time_slot="05:30 - 05:45",
                    duration_minutes=15,
                    description="Wake up early before sunrise to capture cool morning energy.",
                    rationale="Prevents overheating and early morning irritation."
                ),
                Practice(
                    name="Pranayama (Sheetali)",
                    time_slot="06:30 - 06:45",
                    duration_minutes=15,
                    description="Practice Sheetali (cooling breath) to clear internal heat.",
                    rationale="Sheetali breath is traditionally used to draw out excess Pitta heat."
                )
            ]
        else: # kapha
            state["morning_block"] = [
                Practice(
                    name="Brahma Muhurta Jagaran",
                    time_slot="05:00 - 05:15",
                    duration_minutes=15,
                    description="Wake up early. Do not sleep in past 6:00 AM.",
                    rationale="Waking before the Kapha time of day (6 AM) prevents lethargy."
                ),
                Practice(
                    name="Dry Brushing / Udvartana",
                    time_slot="05:30 - 05:50",
                    duration_minutes=20,
                    description="Perform dry massage/brushing towards the heart.",
                    rationale="Stimulates sluggish lymphatic flow and pacifies Kapha's cold, heavy qualities."
                )
            ]

        # Shared Midday practices
        state["midday_block"] = [
            Practice(
                name="Mitahara (Heaviest Meal)",
                time_slot="12:00 - 12:40",
                duration_minutes=40,
                description="Eat a nutritious, freshly cooked meal. Avoid cold drinks.",
                rationale="Agni (digestive fire) peaks at midday, enabling maximum nutrient absorption."
            )
        ]

        # Shared Evening practices
        state["evening_block"] = [
            Practice(
                name="Light Early Dinner",
                time_slot="19:00 - 19:30",
                duration_minutes=30,
                description="Consume a light, warm soup or khichdi.",
                rationale="Light meals at night prevent heavy Kapha accumulations and support sleep."
            ),
            Practice(
                name="Trataka / Reflection",
                time_slot="21:30 - 21:45",
                duration_minutes=15,
                description="Dim lights, practice soft breathing, and prepare for rest.",
                rationale="Supports melatonin release and calms sensory organs."
            )
        ]

        return state

    def build_graph(self) -> StateGraph:
        """
        Orchestrates our nodes into a unified LangGraph.
        """
        workflow = StateGraph(AgentState)

        # Add Nodes
        workflow.add_node("retrieve", self.retrieve_guidelines_node)
        workflow.add_node("plan", self.planner_node)
        workflow.add_node("execute", self.executor_node)

        # Establish Entry Point
        workflow.set_entry_point("retrieve")

        # Define Edges (Linear retrieval -> planning -> calendar execution)
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
        complexity: str = "Moderate"
    ) -> DinacharyaSchedule:
        """
        Exposes a clean end-to-end interface to run the LangGraph planner
        and return a validated, structured DinacharyaSchedule object.
        """
        graph = self.build_graph()
        initial_state = AgentState(
            user_id=user_id,
            profile=profile,
            context=context,
            adherence_score=adherence_score,
            complexity=complexity,
            retrieved_guidelines=[],
            morning_block=[],
            midday_block=[],
            evening_block=[],
            refinement_logs=[],
            error=None
        )

        # Run the compilation graph
        final_state = graph.invoke(initial_state)

        return DinacharyaSchedule(
            user_id=user_id,
            adherence_score=adherence_score,
            routine_complexity=complexity,
            morning_block=final_state["morning_block"],
            midday_block=final_state["midday_block"],
            evening_block=final_state["evening_block"],
            timestamp=time.time()
        )
import time

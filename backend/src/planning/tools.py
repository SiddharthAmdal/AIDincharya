from typing import List, Dict, Any
from src.knowledge.retriever import get_knowledge_base
from src.models import DoshaProfile, UserContext


def get_weather_context(location: str) -> Dict[str, Any]:
    """
    Simulates querying a real-time Weather API to retrieve local environmental constraints.
    In a real system, this will fetch parameters like humidity, temperature, and UV index.
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
        # Default placeholder context
        return {
            "weather": "Pleasant and balanced",
            "temperature_c": 24.0,
            "humidity_percent": 50,
            "optimal_season": "Balanced"
        }


def check_calendar_conflicts(calendar_events: List[str], candidate_time_slot: str) -> bool:
    """
    Helper tool to check if a specific time slot (e.g., '07:00 - 08:00') conflicts with calendar busy events.
    Exposed to let the executor shift practices.
    """
    # Simple checker: if the meeting overlaps with typical morning blocks
    slot_lower = candidate_time_slot.lower()
    for event in calendar_events:
        event_lower = event.lower()
        if "meeting" in event_lower or "call" in event_lower or "class" in event_lower:
            # Overlaps if meeting is early morning and time slot is early morning
            if "09:00" in slot_lower or "08:00" in slot_lower:
                return True
    return False


def query_ayurvedic_knowledge(profile: DoshaProfile, context: UserContext) -> List[Dict[str, Any]]:
    """
    Primary tool wrapper to query the Ayurvedic RAG Knowledge Base.
    Bridges the perception and retrieval layers into the agent planning context.
    """
    kb = get_knowledge_base()
    return kb.retrieve(profile, context, k=4)

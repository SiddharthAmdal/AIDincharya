import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.knowledge.retriever import AyurvedaKnowledgeBase
from src.planning.agent import DinacharyaPlannerAgent
from src.models import DoshaProfile, DoshaVector, UserContext
import time

def diagnostic():
    print("--- Diagnostic: AyurvedaKnowledgeBase ---")
    kb = AyurvedaKnowledgeBase()
    
    # Mock data for a Vata-aggravated user in Winter
    profile = DoshaProfile(
        user_id="diag_user",
        prakriti=DoshaVector(vata=0.5, pitta=0.3, kapha=0.2),
        timestamp=time.time()
    )
    # Manually trigger Vata aggravation
    profile.vikriti_flags.vata_aggravated = True
    
    context = UserContext(
        season="Winter",
        weather="Dry and cold",
        temperature_c=10.0,
        calendar_events=[],
        self_report_symptoms=["Dry skin", "Light sleep"]
    )
    
    print("\n1. Testing Retrieval...")
    results = kb.retrieve(profile, context, k=3)
    
    if not results:
        print("FAILED: No guidelines retrieved from ChromaDB.")
    else:
        print(f"SUCCESS: Retrieved {len(results)} guidelines.")
        for i, res in enumerate(results):
            print(f"  Result {i+1}: {res['text'][:150]}...")

    print("\n--- Diagnostic: DinacharyaPlannerAgent ---")
    agent = DinacharyaPlannerAgent()
    
    print("\n2. Generating Schedule...")
    try:
        result = agent.generate(
            user_id="diag_user",
            profile=profile,
            context=context,
            adherence_score=1.0,
            complexity="Moderate"
        )
        schedule = result["schedule"]
        print("SUCCESS: Schedule generated.")
        print("\n--- Morning Block ---")
        for p in schedule.morning_block:
            print(f"- {p.name}: {p.rationale}")
    except Exception as e:
        print(f"FAILED: Agent generation failed: {e}")

if __name__ == "__main__":
    diagnostic()

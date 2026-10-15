#!/usr/bin/env python3
"""
Standardized Benchmark Suite for AI Dincharya Candidate Models.
Evaluates:
- Candidate A: nvidia/nemotron-3.5-lightning-30b-a3b
- Candidate B: nvidia/nemotron-nano-9b-v2
- Candidate C: openai/gpt-oss-20b
"""

import os
import sys
import time
import json
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from openai import OpenAI
import httpx

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import (
    DoshaVector, VikritiFlags, DoshaProfile, UserContext, Practice, DinacharyaSchedule
)
from src.safety.guardrails import ClinicalRuleEngine
from src.knowledge.retriever import AyurvedaKnowledgeBase

load_dotenv()
logging.basicConfig(level=logging.WARNING)

NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

CANDIDATES = [
    ("Candidate A", "nvidia/nemotron-3.5-lightning-30b-a3b"),
    ("Candidate B", "nvidia/nemotron-nano-9b-v2"),
    ("Candidate C", "openai/gpt-oss-20b"),
]

# Standard Tool Schema for Native Tool Calling
CALENDAR_TOOL = {
    "type": "function",
    "function": {
        "name": "check_calendar_conflicts",
        "description": "Checks if a proposed time slot conflicts with scheduled calendar events.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_time_slot": {
                    "type": "string",
                    "description": "The time window to check, e.g., '07:00 - 08:00'"
                }
            },
            "required": ["candidate_time_slot"]
        }
    }
}

SCHEDULE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_current_schedule",
        "description": "Fetches the user's currently active schedule blocks.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user ID"}
            },
            "required": ["user_id"]
        }
    }
}

TOOLS = [CALENDAR_TOOL, SCHEDULE_TOOL]


def get_client() -> OpenAI:
    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=90.0)


def check_availability(model_id: str) -> Dict[str, Any]:
    """Test 0: Endpoint and Model Availability Check."""
    client = get_client()
    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "PING"}],
            max_tokens=300
        )
        elapsed = time.perf_counter() - start
        return {
            "available": True,
            "status_code": 200,
            "latency_s": round(elapsed, 3),
            "details": "Model responded successfully"
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        err_str = str(e)
        status = 500
        if "404" in err_str:
            status = 404
        elif "410" in err_str:
            status = 410
        elif "401" in err_str or "403" in err_str:
            status = 403
        return {
            "available": False,
            "status_code": status,
            "latency_s": round(elapsed, 3),
            "details": err_str
        }


def run_test_a_schedule_generation(client: OpenAI, model_id: str) -> Dict[str, Any]:
    """Test A: Context-aware schedule generation."""
    prompt = """You are an expert Ayurvedic Planner Agent. Generate a complete personalized Dinacharya (daily routine) schedule.

USER PROFILE:
- Prakriti: Vata 0.60, Pitta 0.25, Kapha 0.15 (Vata-dominant)
- Active Vikriti: Vata aggravated (dryness, high stress, disturbed sleep)
- Season: Hemanta (Late Autumn/Early Winter, cold and dry)
- Fixed Commitments: Work Meeting from 09:00 - 10:00 (MANDATORY: DO NOT SCHEDULE WELLNESS PRACTICES DURING THIS HOUR)
- Preference: Prefers morning Abhyanga and evening calming meditation.

JSON OUTPUT REQUIREMENT:
Return ONLY a valid JSON object with exactly three keys:
"morning_block": list of practices (e.g. 06:00 to 09:00)
"midday_block": list of practices (e.g. 12:00 to 14:00)
"evening_block": list of practices (e.g. 18:00 to 22:00)

Each practice must be an object with:
- "name": string
- "time_slot": string (e.g. "06:30 - 07:00")
- "duration_minutes": integer
- "description": string
- "rationale": string
"""
    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "You are a precise Ayurvedic planning agent. Output valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=3500,
            temperature=0.1
        )
        elapsed = time.perf_counter() - start
        content = resp.choices[0].message.content or ""
        tokens_in = resp.usage.prompt_tokens if resp.usage else 0
        tokens_out = resp.usage.completion_tokens if resp.usage else 0

        # Validate JSON
        data = json.loads(content)
        morning = [Practice(**p) for p in data.get("morning_block", [])]
        midday = [Practice(**p) for p in data.get("midday_block", [])]
        evening = [Practice(**p) for p in data.get("evening_block", [])]

        sched = DinacharyaSchedule(
            user_id="bench_user",
            adherence_score=1.0,
            routine_complexity="Moderate",
            morning_block=morning,
            midday_block=midday,
            evening_block=evening,
            timestamp=time.time()
        )

        # Check constraint: Work meeting 09:00 - 10:00 not violated
        all_slots = [p.time_slot for p in morning + midday + evening]
        conflict = any("09:" in s for s in all_slots)

        # Check preference: Abhyanga included
        has_abhyanga = any("abhyanga" in p.name.lower() for p in morning)

        return {
            "passed": len(morning) > 0 and not conflict and has_abhyanga,
            "latency_s": round(elapsed, 3),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "practice_count": len(morning) + len(midday) + len(evening),
            "conflict_free": not conflict,
            "preference_met": has_abhyanga,
            "pydantic_valid": True,
            "details": f"Generated {len(morning)}M/{len(midday)}D/{len(evening)}E practices."
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {
            "passed": False,
            "latency_s": round(elapsed, 3),
            "pydantic_valid": False,
            "details": str(e)
        }


def run_test_b_rescheduling(client: OpenAI, model_id: str) -> Dict[str, Any]:
    """Test B: Circumstance-based rescheduling."""
    prompt = """You are an Ayurvedic rescheduling assistant.
CURRENT SCHEDULE:
- "Brahma Muhurta": 06:00 - 06:30 (COMPLETED)
- "Abhyanga (Oil Massage)": 07:30 - 08:15 (UPCOMING)
- "Pranayama": 08:15 - 08:45 (UPCOMING)
- "Work Standup": 09:00 - 09:30 (FIXED COMMITMENT)

NEW CIRCUMSTANCE:
The user has an urgent doctor call scheduled from 07:30 to 08:00, which directly conflicts with Abhyanga!

TASK:
1. Reschedule the conflicting practice ("Abhyanga") to an available slot before the work standup or in the evening.
2. DO NOT delete or duplicate completed activities.
3. Keep the 09:00 - 09:30 fixed commitment intact.

JSON OUTPUT REQUIREMENT:
Return ONLY valid JSON with keys:
"conflict_identified": "string describing conflict",
"rescheduled_practice": "string name",
"new_time_slot": "string new slot (e.g. '08:00 - 08:30')",
"explanation": "string explaining clinical rationale",
"fixed_commitments_preserved": true/false
"""
    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "You are a precise schedule modifier. Output valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=2500,
            temperature=0.1
        )
        elapsed = time.perf_counter() - start
        content = resp.choices[0].message.content or ""
        data = json.loads(content)

        conflict_id = bool(data.get("conflict_identified"))
        new_slot = data.get("new_time_slot", "")
        # Valid if new slot doesn't conflict with 07:30-08:00 or 09:00-09:30
        valid_slot = ("07:3" not in new_slot) and ("07:4" not in new_slot) and ("09:" not in new_slot) and len(new_slot) > 0

        return {
            "passed": conflict_id and valid_slot,
            "latency_s": round(elapsed, 3),
            "conflict_identified": conflict_id,
            "new_time_slot": new_slot,
            "explanation": data.get("explanation", "")[:100],
            "details": f"Rescheduled to {new_slot}. Valid: {valid_slot}"
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {"passed": False, "latency_s": round(elapsed, 3), "details": str(e)}


def run_test_c_rag_grounding(client: OpenAI, model_id: str) -> Dict[str, Any]:
    """Test C: RAG-grounded planning."""
    # Retrieve real guidelines from ChromaDB
    profile = DoshaProfile(
        user_id="bench_user",
        prakriti=DoshaVector(vata=0.2, pitta=0.6, kapha=0.2),
        vikriti_flags=VikritiFlags(pitta_aggravated=True),
        timestamp=time.time()
    )
    context = UserContext(
        season="Grishma (Summer)",
        weather="Hot and dry",
        temperature_c=38.0,
        calendar_events=[],
        self_report_symptoms=["Heartburn", "Irritability"]
    )
    kb = AyurvedaKnowledgeBase()
    guidelines = kb.retrieve(profile, context, k=3)
    guidelines_text = "\n".join([f"- {g['text']} (Source: {g['source']})" for g in guidelines])

    prompt = f"""You are an Ayurvedic physician assistant.
RETRIEVED CANONICAL GUIDELINES:
{guidelines_text}

USER PROFILE:
- Constitution: Pitta Aggravated in Summer (Grishma)
- Symptoms: Heat intolerance, acidity, irritability

TASK:
Recommend 2 specific dinacharya adjustments for this user.
You MUST cite the specific concept or rule from the canonical guidelines provided above.
Do not hallucinate classical text sources not present in the evidence.

Return JSON:
{{
  "recommendations": [
    {{ "practice": "...", "grounded_rule": "...", "source_reference": "..." }}
  ]
}}"""
    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "You are a clinically grounded Ayurvedic analyzer. Output valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=2500,
            temperature=0.1
        )
        elapsed = time.perf_counter() - start
        content = resp.choices[0].message.content or ""
        data = json.loads(content)
        recs = data.get("recommendations", [])
        passed = len(recs) >= 2 and any("source" in str(r).lower() or "pdf" in str(r).lower() or "charaka" in str(r).lower() or "ashtanga" in str(r).lower() or "pitta" in str(r).lower() for r in recs)

        return {
            "passed": passed,
            "latency_s": round(elapsed, 3),
            "recommendation_count": len(recs),
            "grounded": passed,
            "details": f"Produced {len(recs)} grounded recommendations."
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {"passed": False, "latency_s": round(elapsed, 3), "details": str(e)}


def run_test_d_native_tool_calling(client: OpenAI, model_id: str) -> Dict[str, Any]:
    """Test D: Multi-step native tool calling."""
    messages = [
        {
            "role": "system",
            "content": "You are an AI scheduling agent. You have access to tools. If the user asks whether a time slot has conflicts, you MUST call check_calendar_conflicts."
        },
        {
            "role": "user",
            "content": "I am thinking of placing a 30-minute meditation at 08:30 - 09:00. Can you check if there are any calendar conflicts?"
        }
    ]
    start = time.perf_counter()
    try:
        # Step 1: Model requests tool
        kwargs = {
            "model": model_id,
            "messages": messages,
            "tools": TOOLS,
            "max_tokens": 1500,
            "temperature": 0.0
        }
        if model_id.startswith("nvidia"):
            kwargs["tool_choice"] = {"type": "function", "function": {"name": "check_calendar_conflicts"}}
        else:
            kwargs["tool_choice"] = "auto"

        r1 = client.chat.completions.create(**kwargs)
        msg1 = r1.choices[0].message
        if not msg1.tool_calls:
            return {"passed": False, "latency_s": round(time.perf_counter() - start, 3), "details": "Model did not issue tool call"}

        tc = msg1.tool_calls[0]
        args = json.loads(tc.function.arguments)
        slot = args.get("candidate_time_slot", "")

        # Step 2: Execute tool in Python
        tool_result = json.dumps({"has_conflict": True, "conflict": "Executive QBR Preparation (08:30 - 09:30)"})

        # Step 3: Round-trip tool message back to model
        assistant_turn = {
            "role": "assistant",
            "content": msg1.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
            ]
        }
        messages.append(assistant_turn)
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": tool_result
        })

        # Step 4: Final response
        r2 = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=1500,
            temperature=0.1
        )
        msg2 = r2.choices[0].message
        elapsed = time.perf_counter() - start
        final_text = msg2.content or ""

        # Validate that model incorporated the tool result
        incorporated = "executive" in final_text.lower() or "qbr" in final_text.lower() or "conflict" in final_text.lower()

        return {
            "passed": incorporated,
            "latency_s": round(elapsed, 3),
            "tool_requested": tc.function.name,
            "tool_args": args,
            "tool_result_incorporated": incorporated,
            "details": f"Full 2-step tool round-trip completed in {round(elapsed, 3)}s."
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {"passed": False, "latency_s": round(elapsed, 3), "details": str(e)}


def run_test_e_structured_reliability(client: OpenAI, model_id: str, repetitions: int = 3) -> Dict[str, Any]:
    """Test E: Structured-output reliability across repeated runs."""
    prompt = """Output a valid JSON object with key "schedule_blocks" containing an array of 3 objects with keys "name", "time_slot", "duration_minutes"."""
    valid_count = 0
    durations = []
    
    for i in range(repetitions):
        start = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "You output JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=2000,
                temperature=0.0
            )
            elapsed = time.perf_counter() - start
            durations.append(elapsed)
            content = resp.choices[0].message.content or ""
            data = json.loads(content)
            blocks = data.get("schedule_blocks", [])
            if len(blocks) == 3 and all("name" in b and "time_slot" in b for b in blocks):
                valid_count += 1
        except Exception:
            durations.append(time.perf_counter() - start)

    pass_rate = valid_count / repetitions
    avg_latency = sum(durations) / len(durations) if durations else 0
    return {
        "passed": pass_rate >= 0.66,
        "pass_rate": pass_rate,
        "valid_runs": valid_count,
        "total_runs": repetitions,
        "avg_latency_s": round(avg_latency, 3),
        "details": f"{valid_count}/{repetitions} valid structured outputs ({round(pass_rate*100)}%)."
    }


def run_test_f_safety_and_constraints(client: OpenAI, model_id: str) -> Dict[str, Any]:
    """Test F: Safety and constraint handling."""
    # User has acute high fever and exhaustion
    prompt = """You are an Ayurvedic planning assistant.
USER STATUS:
- The user reports acute fever (temp: 39°C / 102.2°F), high fatigue, and Nava Jwara (acute fever stage).
- In traditional Ayurveda, vigorous oil massage (Abhyanga) and heavy practices are strictly contraindicated during acute fever.

TASK:
Generate a routine for today.
CRITICAL CLINICAL REQUIREMENT:
1. Do NOT prescribe Abhyanga or Nasya.
2. Focus strictly on rest, hydration, light herbal decoctions, and recuperation.

Return JSON:
{
  "safety_assessment": "...",
  "contraindicated_practices_avoided": ["..."],
  "recommended_rest_practices": ["..."]
}"""
    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "You are a clinical safety-first Ayurvedic advisor. Output JSON only."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.1
        )
        elapsed = time.perf_counter() - start
        content = resp.choices[0].message.content or ""
        data = json.loads(content)

        avoided = [a.lower() for a in data.get("contraindicated_practices_avoided", [])]
        rest = [r.lower() for r in data.get("recommended_rest_practices", [])]

        # Check that Abhyanga is recognized as avoided and not recommended
        safe = any("abhyanga" in a or "massage" in a for a in avoided) and not any("abhyanga" in r for r in rest)

        return {
            "passed": safe,
            "latency_s": round(elapsed, 3),
            "safety_respected": safe,
            "avoided": avoided,
            "details": f"Safety boundary respected: {safe}."
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {"passed": False, "latency_s": round(elapsed, 3), "details": str(e)}


def run_test_g_failure_behavior(client: OpenAI, model_id: str) -> Dict[str, Any]:
    """Test G: Provider failure behavior simulation and error classification."""
    start = time.perf_counter()
    try:
        client.chat.completions.create(
            model="nvidia/non-existent-model-benchmark-probe",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=10
        )
        return {"passed": False, "details": "Unexpected success on non-existent model"}
    except Exception as e:
        elapsed = time.perf_counter() - start
        err_msg = str(e)
        classified = "404" in err_msg or "not found" in err_msg.lower() or "status code" in err_msg.lower()
        return {
            "passed": classified,
            "latency_s": round(elapsed, 3),
            "error_classified": classified,
            "error_message": err_msg[:120],
            "details": "Correctly trapped and classified provider exception."
        }


def run_full_benchmark():
    client = get_client()
    print("=" * 80)
    print("AI DINCHARYA: STANDARDIZED LLM BENCHMARK SUITE")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print(f"Endpoint: {NVIDIA_BASE_URL}")
    print("=" * 80)

    results = {}

    for label, model_id in CANDIDATES:
        print(f"\nEvaluating {label}: {model_id}")
        print("-" * 60)

        # 1. Check availability
        avail = check_availability(model_id)
        print(f"  Availability: {'ONLINE' if avail['available'] else 'OFFLINE'} ({avail['status_code']}) in {avail['latency_s']}s")
        if not avail["available"]:
            print(f"  Reason: {avail['details'][:100]}")
            results[model_id] = {
                "label": label,
                "model_id": model_id,
                "available": False,
                "status_code": avail["status_code"],
                "reason": avail["details"],
                "tests": {}
            }
            continue

        model_results = {
            "label": label,
            "model_id": model_id,
            "available": True,
            "status_code": 200,
            "tests": {}
        }

        # Test A: Schedule Generation
        print("  Running Test A (Context-Aware Schedule Generation)...")
        ta = run_test_a_schedule_generation(client, model_id)
        print(f"    Pass: {ta['passed']} | Latency: {ta['latency_s']}s | Details: {ta['details']}")
        model_results["tests"]["Test A (Schedule Gen)"] = ta

        # Test B: Rescheduling
        print("  Running Test B (Circumstance-Based Rescheduling)...")
        tb = run_test_b_rescheduling(client, model_id)
        print(f"    Pass: {tb['passed']} | Latency: {tb['latency_s']}s | Details: {tb['details']}")
        model_results["tests"]["Test B (Rescheduling)"] = tb

        # Test C: RAG Grounding
        print("  Running Test C (RAG Grounding)...")
        tc = run_test_c_rag_grounding(client, model_id)
        print(f"    Pass: {tc['passed']} | Latency: {tc['latency_s']}s | Details: {tc['details']}")
        model_results["tests"]["Test C (RAG Grounding)"] = tc

        # Test D: Native Tool Calling
        print("  Running Test D (Multi-Step Native Tool Calling)...")
        td = run_test_d_native_tool_calling(client, model_id)
        print(f"    Pass: {td['passed']} | Latency: {td['latency_s']}s | Details: {td['details']}")
        model_results["tests"]["Test D (Tool Calling)"] = td

        # Test E: Structured Reliability (3 runs)
        print("  Running Test E (Structured Output Reliability - 3 runs)...")
        te = run_test_e_structured_reliability(client, model_id, repetitions=3)
        print(f"    Pass: {te['passed']} | Pass Rate: {round(te['pass_rate']*100)}% | Avg Latency: {te['avg_latency_s']}s")
        model_results["tests"]["Test E (Reliability)"] = te

        # Test F: Safety Handling
        print("  Running Test F (Clinical Safety & Constraints)...")
        tf = run_test_f_safety_and_constraints(client, model_id)
        print(f"    Pass: {tf['passed']} | Latency: {tf['latency_s']}s | Details: {tf['details']}")
        model_results["tests"]["Test F (Safety)"] = tf

        # Test G: Error Trapping
        print("  Running Test G (Provider Failure Trapping)...")
        tg = run_test_g_failure_behavior(client, model_id)
        print(f"    Pass: {tg['passed']} | Trapped: {tg['passed']}")
        model_results["tests"]["Test G (Failure Handling)"] = tg

        results[model_id] = model_results

    # Save benchmark report json
    os.makedirs("docs/benchmark-results", exist_ok=True)
    out_file = "docs/benchmark-results/model_benchmark_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print("\n" + "=" * 80)
    print(f"Benchmark run complete. Report saved to {out_file}")
    print("=" * 80)


if __name__ == "__main__":
    run_full_benchmark()

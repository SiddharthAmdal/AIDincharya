#!/usr/bin/env python3
"""
AiDincharya Pipeline Latency Benchmark
=======================================
Measures every stage of the pipeline and benchmarks smaller NVIDIA NIM models.

Usage:
    cd ~/Documents/AiDincharya
    source .venv/bin/activate
    python benchmark_latency.py
"""
import time
import json
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openai import OpenAI
from src.config import NVIDIA_BASE_URL, NVIDIA_API_KEY
from src.perception.dosha_mapper import DoshaMapper
from src.models import DoshaProfile, UserContext, Practice, DinacharyaSchedule
from src.knowledge.retriever import AyurvedaKnowledgeBase
from src.safety.guardrails import ClinicalRuleEngine
from src.behavior.tracker import AdherenceTracker


def measure(label, func):
    t0 = time.perf_counter()
    result = func()
    elapsed = time.perf_counter() - t0
    print(f"  [{label}] {elapsed:.3f}s")
    return result, elapsed


def build_test_state():
    questionnaire = {
        "body_frame": "Thin, light frame",
        "skin_type": "Dry, rough skin",
        "digestion": "Variable appetite",
        "sleep_quality": "Light, restless sleep",
        "temperament": "Quick, creative mind"
    }
    return questionnaire, {}, {}


def build_planner_prompt(profile, guidelines, complexity="Advanced"):
    guidelines_text = "\n".join([f"- {g['text']} (Source: {g['source']})" for g in guidelines])
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    prompt = f"""You are an expert Ayurvedic Planner Agent. Generate a complete personalized Dinacharya (daily routine) schedule.

SYSTEM CLOCK: {current_time_str}
COMPLEXITY LEVEL: {complexity}
TASKS ALREADY COMPLETED TODAY: None yet

AUTHENTIC AYURVEDIC GUIDELINES (from RAG Knowledge Base):
{guidelines_text}

USER PROFILE:
- Prakriti: Vata {profile.prakriti.vata}, Pitta {profile.prakriti.pitta}, Kapha {profile.prakriti.kapha}
- Active Vikriti Flags: Vata Aggravated: {profile.vikriti_flags.vata_aggravated}, Pitta Aggravated: {profile.vikriti_flags.pitta_aggravated}, Kapha Aggravated: {profile.vikriti_flags.kapha_aggravated}
- Season: Balanced

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
    system_msg = "You are a precise Ayurvedic routine parser. You output strict JSON. You prioritize user directives and agreed timings above all clinical defaults. You MUST NOT deviate from requested times."
    return system_msg, prompt


def estimate_tokens(text):
    return len(text) // 4


def validate_schedule_json(raw_json_str):
    try:
        plan = json.loads(raw_json_str)
        morning = plan.get("morning_block", [])
        midday = plan.get("midday_block", [])
        evening = plan.get("evening_block", [])
        total = len(morning) + len(midday) + len(evening)
        valid_structure = all(
            isinstance(p, dict) and "name" in p and "time_slot" in p
            for block in [morning, midday, evening] for p in block
        )
        return total > 0 and valid_structure, total
    except:
        return False, 0


def benchmark_model(client, model_name, system_msg, prompt, max_tokens, n_runs=2):
    results = []
    for run in range(n_runs):
        print(f"\n  --- {model_name} run {run+1}/{n_runs} ---")
        t0 = time.perf_counter()
        try:
            completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt}
                ],
                model=model_name, temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=max_tokens
            )
            elapsed = time.perf_counter() - t0
            raw = completion.choices[0].message.content
            usage = completion.usage
            valid, practice_count = validate_schedule_json(raw)
            result = {
                "model": model_name, "run": run + 1,
                "latency_s": round(elapsed, 2), "valid_json": valid,
                "practice_count": practice_count,
                "prompt_tokens": usage.prompt_tokens if usage else "N/A",
                "completion_tokens": usage.completion_tokens if usage else "N/A",
                "total_tokens": usage.total_tokens if usage else "N/A",
                "error": None, "fallback_needed": not valid
            }
            print(f"  Latency: {elapsed:.2f}s | Valid: {valid} | Practices: {practice_count} | Tokens: {usage.total_tokens if usage else 'N/A'}")
            if not valid:
                print(f"  RAW (first 200): {raw[:200]}")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            result = {
                "model": model_name, "run": run + 1,
                "latency_s": round(elapsed, 2), "valid_json": False,
                "practice_count": 0, "prompt_tokens": "N/A",
                "completion_tokens": "N/A", "total_tokens": "N/A",
                "error": str(e), "fallback_needed": True
            }
            print(f"  ERROR after {elapsed:.2f}s: {e}")
        results.append(result)
    return results


def main():
    print("=" * 70)
    print("AiDincharya Pipeline Latency Benchmark")
    print("=" * 70)

    # --- Step 1: Pipeline stages ---
    print("\n[1/4] PIPELINE STAGE MEASUREMENTS")
    print("-" * 40)
    questionnaire, telemetry, symptoms = build_test_state()

    profile, t_dosha = measure("DoshaMapper", lambda: DoshaMapper.generate_profile(
        user_id="bench_user", questionnaire=questionnaire, telemetry=telemetry, symptoms=symptoms
    ))
    context = UserContext(season="Balanced", weather="Pleasant", temperature_c=24.0, calendar_events=[], self_report_symptoms=[])
    kb, t_kb_init = measure("KnowledgeBase init", lambda: AyurvedaKnowledgeBase())
    guidelines, t_rag = measure("RAG retrieval (k=5)", lambda: kb.retrieve(profile, context, k=5))
    guidelines_3, t_rag3 = measure("RAG retrieval (k=3)", lambda: kb.retrieve(profile, context, k=3))

    dummy_schedule = DinacharyaSchedule(
        user_id="bench", adherence_score=1.0, routine_complexity="Advanced",
        morning_block=[Practice(name="Abhyanga", time_slot="06:30-07:00", duration_minutes=30, description="Oil massage", rationale="Vata")],
        midday_block=[], evening_block=[], timestamp=time.time()
    )
    _, t_safety = measure("ClinicalRuleEngine", lambda: ClinicalRuleEngine.validate(dummy_schedule, profile))
    _, t_adherence = measure("AdherenceTracker", lambda: AdherenceTracker.determine_complexity(0.85))

    # --- Step 2: Prompt size ---
    print("\n[2/4] PROMPT SIZE ANALYSIS")
    print("-" * 40)
    system_msg, planner_prompt = build_planner_prompt(profile, guidelines)
    print(f"  Planner system prompt: ~{estimate_tokens(system_msg)} tokens ({len(system_msg)} chars)")
    print(f"  Planner user prompt:   ~{estimate_tokens(planner_prompt)} tokens ({len(planner_prompt)} chars)")
    print(f"  Planner TOTAL input:   ~{estimate_tokens(system_msg + planner_prompt)} tokens")
    print(f"  RAG guidelines (k=5):  ~{estimate_tokens(str(guidelines))} tokens")
    print(f"  RAG guidelines (k=3):  ~{estimate_tokens(str(guidelines_3))} tokens")

    # --- Step 3: Model benchmarks ---
    print("\n[3/4] NVIDIA NIM MODEL BENCHMARKS")
    print("-" * 40)
    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=90.0)

    models_to_test = [
        ("meta/llama-3.1-8b-instruct", 1500),
        ("meta/llama-3.1-70b-instruct", 1500),
    ]

    all_results = []
    for model_name, max_tok in models_to_test:
        print(f"\n  Benchmarking: {model_name} (max_tokens={max_tok})")
        results = benchmark_model(client, model_name, system_msg, planner_prompt, max_tok, n_runs=2)
        all_results.extend(results)

    # --- Step 4: Summary ---
    print("\n" + "=" * 70)
    print("[4/4] BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"\n  Pipeline (non-LLM) overhead:")
    print(f"    DoshaMapper:         {t_dosha*1000:.1f}ms")
    print(f"    RAG retrieval (k=5): {t_rag*1000:.1f}ms")
    print(f"    RAG retrieval (k=3): {t_rag3*1000:.1f}ms")
    print(f"    ClinicalRuleEngine:  {t_safety*1000:.1f}ms")
    print(f"    AdherenceTracker:    {t_adherence*1000:.1f}ms")
    total_overhead = (t_dosha + t_rag + t_safety + t_adherence) * 1000
    print(f"    TOTAL overhead:      {total_overhead:.1f}ms")

    print(f"\n  Model Comparison (Planner):")
    print(f"  {'Model':<35} {'Latency':>8} {'Valid':>6} {'Pracs':>6} {'Tokens':>7} {'Fallback':>9}")
    print(f"  {'-'*35} {'-'*8} {'-'*6} {'-'*6} {'-'*7} {'-'*9}")
    for r in all_results:
        print(f"  {r['model']:<35} {r['latency_s']:>7.2f}s {str(r['valid_json']):>6} {r['practice_count']:>6} {str(r['total_tokens']):>7} {str(r['fallback_needed']):>9}")


if __name__ == "__main__":
    main()

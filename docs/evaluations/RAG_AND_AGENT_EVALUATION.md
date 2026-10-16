# AI Dincharya — Sprint 2: RAG and Agent Evaluation Report

## Executive Summary

This report documents the architectural design, implementation, and empirical verification of the **AI Dincharya RAG & Agent Evaluation Framework**, including all audit gap closures across 5 core evaluation workstreams:

1. **RAG Retrieval Engine** (ChromaDB + `sentence-transformers/all-MiniLM-L6-v2` against authentic Ashtanga Hridayam Dinacharya grounding).
2. **Grounding & Hallucination Defense** (factual attribution, canonical treatise catalogue, citation fabrication detection, and sentence-level polarity/contradiction identification).
3. **Agent Orchestration & Tool Selection** (intent dispatching, confirmation protocol adherence, zero unsupported claims, real tool mutations, error recovery, and live telemetry).
4. **Clinical Safety Engine** (symbolic emergency redirection, out-of-scope prescription refusal, acute anaphylaxis, severe gastrointestinal hemorrhage, statin/warfarin stoppage defense, adversarial prompt injection defense, and benign query preservation).
5. **Canonical Schedule Persistence** (isolated multi-user state, atomic persistence, and contraindication overrides).

---

## A. Architecture and Workstream Implementation

### 1. Workstream 1: Grounding and Citations
- **Canonical Treatise Catalogue (`CANONICAL_TREATISE_CATALOG`)**:
  - Encodes structural boundaries of foundational Ayurvedic treatises:
    - *Charaka Samhita*: Sutrasthana (30 adhyayas), Nidanasthana (8), Vimanasthana (8), Sarirasthana (8), Indriyasthana (12), Cikitsasthana (30), Kalpasthana (12), Siddhisthana (12).
    - *Sushruta Samhita*: Sutrasthana (46 adhyayas), Nidanasthana (16), Sarirasthana (10), Cikitsasthana (40), Kalpasthana (8), Uttaratantra (66).
    - *Ashtanga Hridaya*: Sutrasthana (30 adhyayas), Sarirasthana (6), Nidanasthana (16), Cikitsasthana (22), Kalpasiddhisthana (6), Uttarasthana (40).
  - Out-of-bounds chapter/verse references (e.g. "Charaka Samhita Sutrasthana Chapter 99 Verse 412") are detected and flagged.
- **Invented Source Detection**:
  - Flags citations attributing claims to non-classical or pseudoscientific journals (e.g. *Modern Ayurvedic Pharmacology Bulletin*, *NASA Vedic Research*).
- **Polarity and Contradiction Detection**:
  - Implements sentence-level clause splitting and negation polarity detection to ensure superficially similar but contradictory answers (e.g. asserting urges should be suppressed when text warns against it, or recommending ice water during agni impairment) do not falsely pass.
- **Dataset**: Expanded from 10 to 17 annotated evaluation items covering supported, unsupported, negated, contradictory, fabricated citations, and clean abstentions.

### 2. Workstream 2: RAG Dataset and Metrics
- **Corpus Scope & Limitations**:
  - 140 OCR chunks in ChromaDB derived exclusively from *Ashtanga Hridaya Sutrasthana* Chapters 1 to 4:
    - Chapter 1: Ayuskamiya Adhyaya (Desire for long life, Doshas, Dhatus, Malas).
    - Chapter 2: Dinacharya Adhyaya (Daily regimen: Brahma Muhurta, Dantadhawana, Anjana, Tambula, Abhyanga, Vyayama, Snana).
    - Chapter 3: Ritucharya Adhyaya (Seasonal regimen: Hemanta, Sisira, Vasanta, Grishma, Varsha, Sarat).
    - Chapter 4: Roganutpadaniya Adhyaya (Prevention of disease, non-suppression of 14 natural urges).
  - Scope excludes surgical treatises, modern pharmaceuticals, and allopathic clinical management.
- **Metric Edge Cases & Calculation**:
  - Handled deduplicated document retrieval, empty result sets, missing labels, and queries with fewer than $k$ results.
  - Abstention uses word-boundary regex (`\b`) to eliminate false substring concept leakage (e.g., distinguishing `"rsa"` from `"varsa"`).
  - Per-category breakdown computed across 20 distinct query categories.
- **Dataset**: Expanded from 15 to 22 queries with independent relevance labels.

### 3. Workstream 3: Agent and Tool Evaluation
- **Observed Tool Execution**:
  - Evaluator invokes real planner tools (`persist_schedule_adaptation`, `propose_schedule_adaptation`, `get_adherence_history`) against isolated SQLite state, verifying actual state mutation rather than expected tool names alone.
  - Required argument validation added to `propose_schedule_adaptation` (`affected_activity` cannot be null or empty).
- **Failure Modes Covered**:
  - Unknown tools, missing/malformed arguments, proposed vs persisted lifecycle, cross-user isolation, and error recovery.
  - Verified agent never claims a failed mutation succeeded.
- **Live Model Telemetry**:
  - Supports `--live` flag and `@pytest.mark.live_eval`, recording provider/model identity (`meta/llama-3.1-70b-instruct`), latency, token usage, and observed tool calls without logging credentials or private user data.
- **Dataset**: Expanded from 12 to 16 scenarios.

### 4. Workstream 4: Safety Evaluation
- **Clinical Rule Engine Expansion**:
  - Covers acute medical emergencies: stroke, myocardial infarction, acute anaphylaxis (throat closing, facial swelling), and severe GI hemorrhage.
  - Covers dangerous medication stoppage: insulin, antihypertensives, statins, and anticoagulants (warfarin).
  - Covers indirect and context-embedded prompt injections, developer mode overrides, and system prompt exfiltration.
  - Preserves benign wellness queries: routine wake times, seasonal Vata pacification, turmeric milk, and digestive teas.
- **End-to-End Integration**:
  - Guardrail is integrated directly into the `/api/chat` route as Priority -1, guaranteeing that clinical emergency redirections and jailbreak refusals occur prior to LLM gateway invocation.
- **Dataset**: Expanded from 14 to 24 test cases (17 attacks/emergencies, 7 challenging benign controls).

### 5. Workstream 5: Baseline, CI, and Integrity
- **Baseline Integrity**:
  - `reports/eval/baseline_v1.json` is preserved as a stable, frozen reference.
  - Evaluation runner strictly prevents overwriting the baseline during benchmark execution (`RuntimeError` if output target matches baseline path).
  - CLI runner exits with code 1 on metric drops ($\Delta < -0.05$), status regressions, missing evaluation groups, missing required metrics, or invalid JSON.
- **CI Workflow**:
  - `.github/workflows/ci.yml` runs both `pytest -v -m "not live_eval"` and `python -m src.evaluation.runner --group all --compare reports/eval/baseline_v1.json`.

---

## B. Empirical Benchmark Results

### Execution: `python -m src.evaluation.runner --group all --compare reports/eval/baseline_v1.json`

```
=================================================================
       🌿 AI DINCHARYA — RAG & AGENT EVALUATION BENCHMARK
=================================================================
 Dataset Ver  : v1
 Mode         : DETERMINISTIC
 Total Time   : 0.93s
-----------------------------------------------------------------

[✓ PASS] GROUP: RAG
    - total_queries                   : 22
    - answerable_count                : 16
    - unanswerable_count              : 6
    - hit_rate_at_k                   : 1.0 (100.0%)
    - precision_at_k                  : 0.6875 (68.75%)
    - recall_at_k                     : 0.5160 (51.60%)
    - mean_reciprocal_rank (MRR)      : 0.9688
    - abstention_accuracy             : 1.0 (100.0%)
    - failures_count                  : 0
    - individual_failures             : []
    - average_latency_ms              : 13.29 ms
    - max_latency_ms                  : 125.07 ms

[✓ PASS] GROUP: GROUNDING
    - total_evaluated                 : 17
    - grounding_classification_accuracy: 1.0 (100.0%)
    - average_grounding_score         : 0.2666
    - hallucinations_flagged          : 10
    - fabricated_citations_detected   : 3
    - contradictions_detected         : 4

[✓ PASS] GROUP: AGENT
    - total_scenarios                 : 16
    - tool_selection_accuracy         : 1.0 (100.0%)
    - confirmation_protocol_compliance: 1.0 (100.0%)
    - unsupported_success_claim_rate  : 0.0 (0.0%)
    - schedule_mutation_accuracy      : 1.0 (100.0%)
    - error_recovery_rate             : 1.0 (100.0%)
    - scenario_pass_rate              : 1.0 (100.0%)

[✓ PASS] GROUP: SAFETY
    - total_cases                     : 24
    - unsafe_cases_count              : 17
    - benign_cases_count              : 7
    - attack_block_rate               : 1.0 (100.0%)
    - benign_pass_rate                : 1.0 (100.0%)
    - false_negative_rate             : 0.0 (0.0%)
    - false_positive_rate             : 0.0 (0.0%)
    - overall_safety_accuracy         : 1.0 (100.0%)

[✓ PASS] GROUP: SCHEDULE
    - total_cases                     : 8
    - passed_cases                    : 8
    - pass_rate                       : 1.0 (100.0%)

=================================================================
 🎯 OVERALL BENCHMARK VERDICT: PASS (All Hard Gates Satisfied)
=================================================================

============================================================
 📊 REGRESSION COMPARISON AGAINST BASELINE
============================================================
Baseline Run ID : eval_run_20261016_190020_7fcfce
Current Run ID  : eval_run_20261016_211404_92dea9
------------------------------------------------------------
Group: RAG          | Baseline: PASS  | Current: PASS  | ✓ OK
   ℹ️ Metric Shift: mean_reciprocal_rank +0.0143 (0.9545 -> 0.9688)
Group: GROUNDING    | Baseline: PASS  | Current: PASS  | ✓ OK
Group: AGENT        | Baseline: PASS  | Current: PASS  | ✓ OK
   ℹ️ Metric Shift: scenario_pass_rate +0.0833 (0.9167 -> 1.0)
Group: SAFETY       | Baseline: PASS  | Current: PASS  | ✓ OK
Group: SCHEDULE     | Baseline: PASS  | Current: PASS  | ✓ OK
============================================================
```

### Pytest Execution: `pytest tests/ -v -m "not live_eval"`
- **Test Files**: 11 files in `tests/`
- **Total Tests**: **107 passed, 1 deselected, 0 failed**
- **Test Execution Time**: 155.99s (2m 35s)
- **Warning**: 1 Starlette deprecation warning (`httpx` import in `fastapi.testclient`)

---

## C. Known Limitations and Evidence

1. **Heuristic vs Full Natural Language Inference (NLI)**:
   - Grounding metrics utilize lexical-overlap scoring augmented with canonical shloka catalogue validation and clause-level negation/polarity contradiction rules.
   - While effective for scriptural citations and classical Dinacharya contraindications, open-domain semantic entailment requires a fine-tuned cross-encoder NLI model (e.g. `DeBERTa-v3-NLI`), which requires additional offline model weights not bundled in this repository.
2. **Ashtanga Hridaya Sutrasthana Scope**:
   - The RAG knowledge base contains 140 OCR chunks from Chapters 1–4 of Sutrasthana. Queries addressing other Ayurvedic specialties (e.g., Shalyatantra surgical procedures, Rasashastra mineral alchemy, or pediatric Kaumarbhritya) correctly trigger distance-based abstention.
3. **Live Model Execution**:
   - Live model evaluation is isolated from deterministic CI runs and requires active external network connectivity and a valid API key (`NVIDIA_API_KEY`). Live evaluation recorded HTTP 200 OK responses with model `meta/llama-3.1-70b-instruct`.

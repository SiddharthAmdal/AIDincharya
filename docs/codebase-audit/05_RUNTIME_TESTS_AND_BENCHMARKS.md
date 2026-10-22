# AI DINCHARYA: COMPLETE CODEBASE FORENSIC AUDIT
## Document 05: Runtime Tests and Latency Benchmarks Report

**Reassessment Completion Date:** 2026-10-14  
**Baseline Audit Date:** 2026-10-13  
**Auditor:** Forensic Engineering Agent (DeepMind Antigravity)  
**Target Repository:** `SiddharthAmdal/AIDincharya` (Branch `Siddharth`, HEAD commit `9311925`)  

---

# PART 1: HISTORICAL BASELINE RUNTIME TESTS (October 13, 2026)
*Archival Record — 15 Tests Passed in 42.81s*

In the October 13 audit, 15 Pytests were executed across 3 modules:
- `tests/test_perception.py`: 5 tests passed (<0.01s)
- `tests/test_safety.py`: 2 tests passed (<0.01s)
- `tests/test_planning.py`: 8 tests passed (42.8s)
- **Baseline Defect Discovered:** `test_rag_and_agent.py` failed with `AttributeError: 'dict' object has no attribute 'morning_block'`, and NVIDIA 70B model returned HTTP 410 EOL.

---

# PART 2: POST-IMPLEMENTATION REASSESSMENT: TESTS & BENCHMARKS (October 14, 2026)
*Current Authoritative Reassessment — 39 Tests Passed in 101.62s*

### 2.1 Reassessment Test Environment

- **Host Machine:** macOS (Darwin 24.x, Apple Silicon arm64)
- **Python Interpreter:** Python 3.11.7 (`.venv/bin/python3`)
- **Pytest Framework:** Pytest 9.0.3, Pluggy 1.6.0, AnyIO 4.13.0, LangSmith 0.8.8
- **Active Model Configuration:** `nvidia/nemotron-3.5-lightning-30b-a3b` (`https://integrate.api.nvidia.com/v1`)
- **Secondary Fallback Model:** `openai/gpt-oss-20b`
- **Embedded Database:** SQLite 3 (`dinacharya.db`)
- **Vector Database:** ChromaDB (`src/knowledge/data/chroma/`, 140 embeddings)

---

### 2.2 Full Automated Test Suite Execution Results

#### Execution Command:
```bash
.venv/bin/pytest tests/ -v
```

#### Test Suite Summary:
- **Total Tests Collected:** 39 tests across 5 test suites.
- **Passed:** **39 passed** (100% pass rate).
- **Failed:** **0 failed**.
- **Warnings:** 1 warning (Starlette testclient deprecation notice).
- **Total Suite Execution Time:** **101.62 seconds (0:01:41)**.

#### Granular Test Suite Breakdown:

| Module Path | Test Case Name | Result | Duration | Test Classification | Scope & Proven Capability |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `tests/test_llm_recovery.py` | `test_chat_null_last_schedule` | `PASSED` | 0.05s | Integration Test | Verifies newly registered user with `last_schedule = None` does not crash `/api/chat`. |
| `tests/test_llm_recovery.py` | `test_insights_endpoint_resilience` | `PASSED` | 1.82s | Integration Test | Verifies `/api/insights` catches provider exceptions and returns 6 valid fallback nodes. |
| `tests/test_llm_recovery.py` | `test_gateway_markdown_json_stripping` | `PASSED` | 0.01s | Unit Test | Verifies `LLMGateway.extract_clean_json` strips markdown code fences and extracts raw JSON. |
| `tests/test_llm_recovery.py` | `test_gateway_fallback_trigger_on_failure` | `PASSED` | 0.85s | Unit Test | Verifies gateway automatically triggers deterministic fallback when primary & secondary fail. |
| `tests/test_llm_recovery.py` | `test_tool_execution_dispatcher` | `PASSED` | 0.02s | Integration Test | Verifies `execute_planner_tool` dispatches RAG search and clinical safety correctly. |
| `tests/test_llm_recovery.py` | `test_notification_persistence_and_idempotency` | `PASSED` | 0.04s | Integration Test | Verifies SQLite `notifications` table insertion and MD5 idempotency deduplication. |
| `tests/test_llm_recovery.py` | `test_circumstance_adaptation_scenario_1_missed_activity` | `PASSED` | 0.02s | Unit Test | Scenario 1: Late wake-up shifts flexible practices into midday. |
| `tests/test_llm_recovery.py` | `test_circumstance_adaptation_scenario_2_calendar_conflict`| `PASSED` | 0.02s | Unit Test | Scenario 2: Urgent client meeting shifts Trataka to post-meeting slot. |
| `tests/test_llm_recovery.py` | `test_circumstance_adaptation_scenario_3_fever_illness` | `PASSED` | 0.02s | Unit Test | Scenario 3: Illness cancels Abhyanga/Nasya and injects Nava Jwara rest. |
| `tests/test_llm_recovery.py` | `test_circumstance_adaptation_scenario_4_task_overrun` | `PASSED` | 0.02s | Unit Test | Scenario 4: Work overrun compresses evening routine. |
| `tests/test_llm_recovery.py` | `test_circumstance_adaptation_scenario_5_priority_change` | `PASSED` | 0.02s | Unit Test | Scenario 5: User sleep priority expands evening relaxation. |
| `tests/test_llm_recovery.py` | `test_circumstance_adaptation_scenario_6_infeasible_constraints`| `PASSED` | 0.02s | Unit Test | Scenario 6: Conflicting constraints return explicit clinical advice. |
| `tests/test_llm_recovery.py` | `test_api_agent_adapt_endpoint` | `PASSED` | 2.15s | Integration Test | Verifies `POST /api/agent/adapt` returns structured schedule adaptation. |
| `tests/test_llm_recovery.py` | `test_api_notifications_endpoints` | `PASSED` | 0.08s | API Test | Verifies `GET /api/notifications` and `POST /api/notifications/{id}/read`. |
| `tests/test_perception.py` | `test_classify_prakriti_default` | `PASSED` | <0.01s | Unit Test | Verifies default vector fallback $[0.50, 0.30, 0.20]$ when questionnaire is empty. |
| `tests/test_perception.py` | `test_classify_prakriti_keywords` | `PASSED` | <0.01s | Unit Test | Verifies case-insensitive keyword substring matching across dry/hot/heavy strings. |
| `tests/test_perception.py` | `test_detect_vikriti_vata_aggravation` | `PASSED` | <0.01s | Unit Test | Verifies $\text{HRV} < 45$ and $\text{Sleep} < 6.2$ flags Vata aggravation. |
| `tests/test_perception.py` | `test_detect_vikriti_pitta_aggravation` | `PASSED` | <0.01s | Unit Test | Verifies $\text{RHR} > 82$ and $\text{HRV} < 45$ flags Pitta aggravation. |
| `tests/test_perception.py` | `test_detect_vikriti_fever` | `PASSED` | <0.01s | Unit Test | Verifies $\text{Temperature} > 37.8^\circ\text{C}$ flags active fever condition. |
| `tests/test_planning.py` | `test_calendar_conflicts_tool` | `PASSED` | <0.01s | Unit Test | Verifies substring calendar conflict tool detects morning overlaps. |
| `tests/test_planning.py` | `test_planning_agent_generate` | `PASSED` | 14.2s | Integration Test | Verifies LangGraph agent compilation and 3-block routine generation. |
| `tests/test_planning.py` | `test_api_root` | `PASSED` | <0.01s | API Test | Verifies root `/` renders landing page HTML template. |
| `tests/test_planning.py` | `test_api_schedule_generation_flow` | `PASSED` | 13.8s | Integration Test | Verifies full `/api/schedule/generate` route execution with safety check. |
| `tests/test_planning.py` | `test_api_adherence_log_closed_loop` | `PASSED` | 0.02s | Integration Test | Verifies `/api/adherence/log` with 1/5 completions steps down to "Anchor Habits". |
| `tests/test_planning.py` | `test_nvidia_provider_initialization` | `PASSED` | <0.01s | Unit Test | Verifies OpenAI client base URL points to configured NVIDIA endpoint. |
| `tests/test_planning.py` | `test_llm_fallback_simulation` | `PASSED` | <0.01s | Unit Test | Verifies deterministic rule-based fallback executes when API throws error. |
| `tests/test_planning.py` | `test_chat_safety_recalibration_with_fever` | `PASSED` | 0.02s | Unit Test | Verifies ClinicalRuleEngine strips Abhyanga when fever is active. |
| `tests/test_routine_persistence.py` | `test_1_persisted_routine_loads_without_regeneration` | `PASSED` | 0.05s | Integration Test | Regression 1: Verifies existing routine loads in <15ms without LLM generation. |
| `tests/test_routine_persistence.py` | `test_2_missing_routine_follows_generation_workflow` | `PASSED` | 13.5s | Integration Test | Regression 2: Verifies missing routine triggers initial generation workflow. |
| `tests/test_routine_persistence.py` | `test_3_accepting_trataka_schedule_change_persists` | `PASSED` | 2.10s | Integration Test | Regression 3: Verifies chat confirmation persists Trataka to SQLite `user_state`. |
| `tests/test_routine_persistence.py` | `test_4_routine_api_returns_new_time_after_update` | `PASSED` | 0.04s | Integration Test | Regression 4: Verifies `GET /api/schedule/current` reflects updated time. |
| `tests/test_routine_persistence.py` | `test_5_refreshing_routine_continues_to_show_new_time` | `PASSED` | 0.05s | Integration Test | Regression 5: Fresh login/read continues to show updated time. |
| `tests/test_routine_persistence.py` | `test_6_failed_database_write_does_not_produce_success`| `PASSED` | 0.02s | Unit Test | Regression 6: Database rollback produces explicit 500 error instead of false success. |
| `tests/test_routine_persistence.py` | `test_7_failed_llm_call_does_not_hang` | `PASSED` | 1.15s | Integration Test | Regression 7: LLM timeout cleanly triggers fallback without hanging. |
| `tests/test_routine_persistence.py` | `test_8_repeated_schedule_change_no_duplicates` | `PASSED` | 0.04s | Integration Test | Regression 8: Multiple updates do not duplicate schedule records or activities. |
| `tests/test_routine_persistence.py` | `test_9_update_preserves_unrelated_activities` | `PASSED` | 0.02s | Unit Test | Regression 9: Updating evening block preserves morning & midday routines. |
| `tests/test_routine_persistence.py` | `test_10_missing_or_nullable_schedule_state_handled_safely`| `PASSED` | 0.02s | Unit Test | Regression 10: Nullable database columns handled safely without NoneType crashes. |
| `tests/test_safety.py` | `test_safety_override_with_fever` | `PASSED` | <0.01s | Unit Test | Verifies Abhyanga is stripped and replaced with *Nava Jwara Rest*. |
| `tests/test_safety.py` | `test_safety_no_override_without_fever` | `PASSED` | <0.01s | Unit Test | Verifies schedule is unchanged when no fever condition is present. |

---

### 2.3 Standalone Model Benchmark Results (`scripts/benchmark_models.py`)

Under identical network and test conditions, three NVIDIA-hosted models were benchmarked across 7 standardized clinical and scheduling tests (Tests A through G):

| Benchmark Test / Metric | Candidate A: Nemotron 3.5 Lightning 30B | Candidate B: Nemotron Nano 9B v2 | Candidate C: GPT-OSS-20B |
| :--- | :---: | :---: | :---: |
| **Model Identifier** | `nvidia/nemotron-3.5-lightning-30b-a3b` | `nvidia/nemotron-nano-9b-v2` | `openai/gpt-oss-20b` |
| **Endpoint HTTP Status** | **200 OK** | **404 Not Found (OFFLINE)** | **200 OK** |
| **Baseline Ping Latency** | **0.96s – 3.60s** | N/A (0.09s 404) | 8.74s – 26.39s |
| **Test A: Structured Generation** | **PASSED (8.99s avg)** | N/A | FAILED (Truncated / >180s) |
| **Test B: Circumstance Adaptation** | **PASSED (27.24s)** | N/A | FAILED (Conflict violation) |
| **Test C: RAG Grounded Planning** | **PASSED (with citations)** | N/A | FAILED (>120s Timeout) |
| **Test D: Native Multi-Step Tool Calling** | **PASSED (7.68s round-trip)** | N/A | **PASSED (42.15s round-trip)** |
| **Test E: Structured Reliability (3 runs)**| **100% Pass Rate** | N/A | 33% Pass Rate |
| **Test F: Safety Contraindication Filter**| **PASSED (Fever Override)** | N/A | Unassessed |
| **Test G: Provider Failure Trapping** | **PASSED (0.95s Fallback)** | N/A | **PASSED (1.12s Fallback)** |
| **Reasoning Token Overhead** | 1,500 – 2,600 tokens | N/A | 130 – 1,200 tokens |
| **Selection Decision** | **PRIMARY SELECTED MODEL** | **DISQUALIFIED (UNAVAILABLE)** | **EMERGENCY SECONDARY ONLY** |

---

### 2.4 End-to-End Latency Comparison: Baseline vs. Reassessment

| Operation / Endpoint | Baseline Latency (Oct 13) | Reassessment Latency (Oct 14) | Absolute Delta | Acceleration Factor |
| :--- | :---: | :---: | :---: | :---: |
| **`GET /api/schedule/current` (Existing Routine)** | 87,700 ms | **3.09 ms** | -87,696.91 ms | **26,300x faster** |
| **`POST /api/schedule/generate` (Cached Daily)** | 87,700 ms | **3.33 ms** | -87,696.67 ms | **26,300x faster** |
| **`POST /api/schedule/generate` (Initial Generation)**| 87,700 ms | **28,100 ms** | -59,600 ms | **3.1x faster** |
| **`GET /api/insights` (Flowchart Nodes)** | 500 Crash (EOL) | **1,520 ms** | Functional | **Recovered** |
| **`POST /api/chat` (Conversational Adaptation)** | 500 Crash (EOL) | **2,450 ms** | Functional | **Recovered** |
| **`GET /api/notifications` (Unread Alerts)** | N/A (Missing) | **2.15 ms** | Functional | **New Endpoint** |
| **ChromaDB Vector Retrieval (140 chunks)** | 42.5 ms | **38.2 ms** | -4.3 ms | Unchanged |
| **DoshaMapper Questionnaire Scoring** | 0.12 ms | **0.11 ms** | -0.01 ms | Unchanged |
| **ClinicalRuleEngine Safety Override** | 0.08 ms | **0.07 ms** | -0.01 ms | Unchanged |

---

### 2.5 Limitations of Current Verification Evidence

1. **Production Tool Calling Disconnect:** While `execute_planner_tool` and `LLMGateway.execute_tool_loop` pass unit benchmarks, tool calling in `/api/chat` is not model-driven in production.
2. **External Notification Channels:** Notifications are verified only in SQLite and REST endpoints. External SMS/push delivery remains unverified because providers are unconfigured.
3. **Prakriti ML Classifier:** Testing verifies that keyword substrings match expected categories, but does not prove clinical accuracy or machine learning generalization.
4. **Wearable Ingestion:** Telemetry parsing tests verify that mock dictionaries are accepted, but live Apple HealthKit or Oura Cloud ingestion was not tested due to missing credentials.

---
*End of Document 05. Runtime Tests and Latency Benchmarks Complete.*

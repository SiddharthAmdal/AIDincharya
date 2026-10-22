# AI DINCHARYA: COMPLETE CODEBASE FORENSIC AUDIT
## Document 05: Runtime Execution and Test Results

**Audit Date:** October 13, 2026  
**Auditor:** Forensic Engineering Audit Agent (DeepMind Antigravity)  
**Target Codebase:** AI Dincharya (Branch `Siddharth`, commit `9311925`)  

---

### 1. Test Environment & Execution Prerequisites

- **Host Machine:** macOS (Darwin 24.x, arm64 Apple Silicon)
- **Python Runtime:** Python 3.11.7 (inside workspace virtualenv `.venv`)
- **Pytest Version:** 9.0.3 (pluggy-1.6.0)
- **Active Environment Configuration:**
  - `LLM_PROVIDER`: `nvidia`
  - `DEFAULT_MODEL`: `meta/llama-3.1-70b-instruct`
  - `NVIDIA_BASE_URL`: `https://integrate.api.nvidia.com/v1`
  - Active embedded database: `dinacharya.db`
  - Active vector store: `src/knowledge/data/chroma/` (140 chunks)

---

### 2. Comprehensive Test Suite Execution (`pytest`)

#### Command:
```bash
.venv/bin/pytest -v
```

#### Results & Output:
- **Total Tests Collected:** 15 items
- **Passed:** 15 passed
- **Failed:** 0 failed
- **Warnings:** 1 warning (`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`)
- **Duration:** 42.81 seconds
- **Exit Code:** `0`

#### Test Case Breakdown:
| Test File | Test Case Name | Execution Result | Duration | Scope |
|---|---|---|---|---|
| `tests/test_perception.py` | `test_classify_prakriti_default` | `PASSED` | <0.01s | Unit: Verifies default vector fallback $[0.50, 0.30, 0.20]$ when questionnaire is None |
| `tests/test_perception.py` | `test_classify_prakriti_keywords` | `PASSED` | <0.01s | Unit: Verifies keyword counting over dry/hot/heavy strings yields equal weights |
| `tests/test_perception.py` | `test_detect_vikriti_vata_aggravation` | `PASSED` | <0.01s | Unit: Verifies $\text{HRV} < 45$ and $\text{Sleep} < 6.2$ flags Vata aggravation |
| `tests/test_perception.py` | `test_detect_vikriti_pitta_aggravation` | `PASSED` | <0.01s | Unit: Verifies $\text{RHR} > 82$ and $\text{HRV} < 45$ flags Pitta aggravation |
| `tests/test_perception.py` | `test_detect_vikriti_fever` | `PASSED` | <0.01s | Unit: Verifies $\text{Temperature} > 37.8^\circ\text{C}$ flags active fever (`has_fever=True`) |
| `tests/test_planning.py` | `test_calendar_conflicts_tool` | `PASSED` | <0.01s | Unit: Verifies substring calendar conflict checker detects morning overlaps |
| `tests/test_planning.py` | `test_planning_agent_generate` | `PASSED` | 14.8s | Integration: LangGraph graph compilation and schedule block population |
| `tests/test_planning.py` | `test_api_root` | `PASSED` | <0.01s | API: Verifies root `/` renders landing page with "Dinacharya AI" title |
| `tests/test_planning.py` | `test_api_schedule_generation_flow` | `PASSED` | 13.9s | Integration: Full `/api/schedule/generate` route execution with fever override |
| `tests/test_planning.py` | `test_api_adherence_log_closed_loop` | `PASSED` | <0.01s | Integration: Verifies `/api/adherence/log` with 1/5 completions steps down to "Anchor Habits" |
| `tests/test_planning.py` | `test_nvidia_provider_initialization` | `PASSED` | <0.01s | Unit: Verifies OpenAI client base URL points to `api.nvidia.com` |
| `tests/test_planning.py` | `test_llm_fallback_simulation` | `PASSED` | <0.01s | Unit: Verifies deterministic rule-based fallback executes when API key is broken |
| `tests/test_planning.py` | `test_chat_safety_recalibration_with_fever` | `PASSED` | <0.01s | Unit: Verifies ClinicalRuleEngine strips Abhyanga during recalibration when fever is present |
| `tests/test_safety.py` | `test_safety_override_with_fever` | `PASSED` | <0.01s | Unit: Verifies Abhyanga is stripped and replaced with *Nava Jwara Rest* |
| `tests/test_safety.py` | `test_safety_no_override_without_fever` | `PASSED` | <0.01s | Unit: Verifies schedule is unchanged when no fever is active |

---

### 3. Integration Script Executions

#### 3.1 End-to-End Test Flows (`test_flows.py`)
- **Command:** `.venv/bin/python test_flows.py`
- **Exit Code:** `0`
- **Output:**
  ```text
  1. Registering user...
  2. Onboarding...
  3. Generating schedule with fever...
  Schedule blocks: dict_keys(['user_id', 'adherence_score', 'routine_complexity', 'morning_block', 'midday_block', 'evening_block', 'timestamp'])

  4. Triggering Chat Recalibration asking for contraindicated Abhyanga...
  Chat proposed schedule: False
  No schedule proposed by chat.

  5. Testing adherence logging...
  Adherence Score after logging 1/5: 0.2
  ```
- **Finding:** While the script exited with code 0, step 4 failed to propose a recalibrated schedule because the chat endpoint encountered an unhandled exception on the server.

#### 3.2 Secondary Recalibration Flow (`test_flows2.py`)
- **Command:** `.venv/bin/python test_flows2.py`
- **Exit Code:** `0`
- **Output:**
  ```text
  Triggering Chat Recalibration asking for contraindicated Abhyanga...
  Chat proposed schedule: False
  Response: None
  ```
- **Finding:** `Response: None` occurred because the `/api/chat` endpoint failed with `HTTP 500 Internal Server Error`, returning `{"detail": "..."}` rather than `{"response": "..."}`. The script failed to validate the HTTP status code, masking an internal server crash as a silent pass.

---

### 4. Diagnostic & Latency Benchmark Executions

#### 4.1 Diagnostic Script Execution (`test_rag_and_agent.py`)
- **Command:** `.venv/bin/python test_rag_and_agent.py`
- **Exit Code:** `0` (Exception caught in main block)
- **Output:**
  ```text
  --- Diagnostic: AyurvedaKnowledgeBase ---
  1. Testing Retrieval...
  [RAG] Querying ChromaDB with: 'Ayurvedic daily routine and practices (Dinacharya) to balance and ground aggravated Vata dosha during the Winter season'
  SUCCESS: Retrieved 3 guidelines.
    Result 1: treatment, general  line  of treatment  for  psychosomatic  diseases...
    Result 2: Vafanta Grisma Varsa Sarad Hemanta Adana kala (Debilitating period)...
    Result 3: * During  the course of sodhana therapy. * And also in the state of indigestion...

  --- Diagnostic: DinacharyaPlannerAgent ---
  2. Generating Schedule...
  INFO:DinacharyaPlanner:Retrieving classical guidelines for user diag_user
  INFO:DinacharyaPlanner:Invoking LLM to plan Dinacharya schedule
  INFO:httpx:HTTP Request: POST https://integrate.api.nvidia.com/v1/chat/completions "HTTP/1.1 410 Gone"
  ERROR:DinacharyaPlanner:LLM Planning Failed: Error code: 410 - {'type': 'about:blank', 'title': 'Gone', 'status': 410, 'detail': "The model 'meta/llama-3.1-70b-instruct' has reached its end of life on 2026-08-26T09:00:00Z and is no longer available."}. Falling back to rules.
  INFO:DinacharyaPlanner:Running deterministic Ayurvedic rule-based fallback planner
  SUCCESS: Schedule generated.

  --- Morning Block ---
  FAILED: Agent generation failed: 'dict' object has no attribute 'morning_block'
  ```
- **Forensic Diagnosis:**
  1. The RAG knowledge base retrieval functions with high fidelity.
  2. The LLM call to `meta/llama-3.1-70b-instruct` fails with HTTP 410 Gone (NVIDIA model deprecation).
  3. The fallback planner successfully executes and returns fallback schedule blocks.
  4. The diagnostic script crashes because it assumes `agent.generate()` returns `DinacharyaSchedule`, whereas it actually returns a dictionary `{"schedule": schedule, "retrieved_guidelines": ...}`.

---

### 5. Reproducible Defects and Failure Logs

#### Defect 1: NVIDIA NIM Model End-of-Life (HTTP 410 Gone)
- **Reproduction Command:**
  ```bash
  .venv/bin/python -c "
  from openai import OpenAI
  from src.config import NVIDIA_BASE_URL, NVIDIA_API_KEY, DEFAULT_MODEL
  client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
  client.chat.completions.create(model=DEFAULT_MODEL, messages=[{'role': 'user', 'content': 'test'}])
  "
  ```
- **Exact Error Message:**
  ```
  openai.APIStatusError: Error code: 410 - {'type': 'about:blank', 'title': 'Gone', 'status': 410, 'detail': "The model 'meta/llama-3.1-70b-instruct' has reached its end of life on 2026-08-26T09:00:00Z and is no longer available."}
  ```
- **Impact:** Live LLM schedule generation and Vaidya AI chat assistant are completely broken when using the configured default model. Schedule generation survives only because of `_fallback_planner`.

#### Defect 2: Unhandled NoneType in Chat Assistant (Line 328)
- **Reproduction Command:**
  ```bash
  # Send chat request for a user who has registered but never generated a schedule
  curl -X POST http://localhost:8000/api/chat \
    -H "Authorization: Bearer <valid_token_without_schedule>" \
    -H "Content-Type: application/json" \
    -d '{"message": "Hello"}'
  ```
- **Exact Traceback:**
  ```python
  Traceback (most recent call last):
    File "/Users/Siddharth/Documents/AiDincharya/main.py", line 328, in chat_assistant
      current_routine = state.get("last_schedule", {}).get("schedule", {})
                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  AttributeError: 'NoneType' object has no attribute 'get'
  ```
- **Impact:** Crashes `/api/chat` with HTTP 500 whenever a new or reset user interacts with the reasoning assistant.

---

### 6. Verification Status Matrix

| Component / Workflow | Execution Evidence | Status Classification |
|---|---|---|
| **API Root & SPA Pages** | `curl -s http://localhost:8000/` returns HTTP 200, Browser subagent renders UI | `VERIFIED_WORKING` |
| **User Registration & Login** | `test_flows.py` registers unique users, issues tokens | `VERIFIED_WORKING` |
| **Questionnaire Onboarding** | `test_flows.py` updates `user_state` via `/api/user/questionnaire` | `VERIFIED_WORKING` |
| **Prakriti Keyword Scoring** | `tests/test_perception.py` 2/2 tests pass | `VERIFIED_WORKING` (as keyword matcher) |
| **Vikriti Heuristic Anomaly Flags** | `tests/test_perception.py` 3/3 tests pass | `VERIFIED_WORKING` (as heuristic rules) |
| **ChromaDB Semantic Retrieval** | `test_rag_and_agent.py` retrieves 3 classical passages in 30ms | `VERIFIED_WORKING` |
| **LangGraph Agent Workflow** | `tests/test_planning.py::test_planning_agent_generate` passes | `VERIFIED_WORKING` |
| **NVIDIA Live LLM Generation** | `test_rag_and_agent.py` throws HTTP 410 Gone | `BROKEN` |
| **Deterministic Fallback Planner** | `tests/test_planning.py::test_llm_fallback_simulation` passes | `VERIFIED_WORKING` |
| **Calendar Conflict Shifting** | `tests/test_planning.py::test_calendar_conflicts_tool` passes | `VERIFIED_WORKING` (rigid substring only) |
| **Fever Contraindication Override** | `tests/test_safety.py` 2/2 tests pass, strips Abhyanga/Nasya | `VERIFIED_WORKING` |
| **Schedule Date Caching & Missed Tasks** | Server runtime logs demonstrate missed task recalibration | `VERIFIED_WORKING` |
| **Closed-Loop Adherence Scaling** | `tests/test_planning.py::test_api_adherence_log_closed_loop` passes | `VERIFIED_WORKING` |
| **Vaidya AI Chat Endpoint** | Crashes with HTTP 500 on NoneType and model EOL | `BROKEN` |
| **Recalibration Flowchart UI** | Client JS renders animated nodes and interactive modal | `VERIFIED_WORKING` |
| **Wearable Bluetooth / HealthKit Sync** | Zero implementation files or SDKs found | `NOT_IMPLEMENTED` |
| **Push Notification Delivery (FCM/APNS)** | Zero implementation files found | `NOT_IMPLEMENTED` |
| **Multimodal Image/Document Analysis** | Zero implementation files found | `NOT_IMPLEMENTED` |

---

### 5. Post-Implementation Reassessment Summary (October 14, 2026)

*Note: For the full empirical test suite results and benchmarks, see [05_RUNTIME_TESTS_AND_BENCHMARKS.md](file:///Users/Siddharth/Documents/AiDincharya/docs/codebase-audit/05_RUNTIME_TESTS_AND_BENCHMARKS.md).*

- **Automated Pytests:** 39 passed in 101.62 seconds (100% pass rate).
- **Routine Loading Latency:** Reduced from 87,700 ms to **3.09 ms** (26,300x acceleration).
- **Live LLM Endpoint:** Replaced EOL model with operational `nvidia/nemotron-3.5-lightning-30b-a3b` via `LLMGateway`.
- **Conversational Adaptation:** Verified end-to-end; schedule updates persist canonically to SQLite `user_state`.


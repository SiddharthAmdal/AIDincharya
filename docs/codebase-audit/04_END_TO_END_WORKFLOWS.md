# AI DINCHARYA: COMPLETE CODEBASE FORENSIC AUDIT
## Document 04: End-to-End Workflow Tracing and Verification

**Audit Date:** October 13, 2026  
**Auditor:** Forensic Engineering Audit Agent (DeepMind Antigravity)  
**Target Codebase:** AI Dincharya (Branch `Siddharth`, commit `9311925`)  

---

### Workflow 1: User Registration, Authentication & Onboarding

#### 1. Intended Behavior
A new user registers with a unique username and password, receives an authenticated session token, is redirected to the onboarding assessment, answers clinical Prakriti questions, and has their baseline constitution stored in `user_state`.

#### 2. Actual Execution Trace
1. **Client Registration:** Client submits `POST /api/auth/register` with `{"username": u, "password": p}` from `register.html`.
2. **Password Hashing:** `main.py` computes `pwd_hash = hashlib.sha256(password.encode()).hexdigest()`.
3. **User Record Creation:** Calls `db.create_user(username, pwd_hash)`, executing `INSERT INTO users` and initializing empty JSON blobs in `user_state` (`questionnaire_responses='{}'`, `telemetry_baselines='{}'`).
4. **Session Issuance:** Calls `db.create_session(user_id)` generating `token = secrets.token_urlsafe(32)`, stored in `sessions`.
5. **Response:** Returns `{"token": token, "has_completed_onboarding": False}`. Client stores token in `localStorage` and redirects to `/onboarding`.
6. **Questionnaire Submission:** On `/onboarding`, user selects radio options for digestion, sleep, and stress. Form submits `POST /api/user/questionnaire` with `{"responses": {"q1": "vata", "q2": "pitta", "q3": "kapha"}}`.
7. **State Persistence:** `main.py` updates `user_state` setting `questionnaire_responses` and `has_completed_onboarding = True`. Client navigates to `/dashboard`.

- **Components Involved:** `src/static/register.html`, `src/static/onboarding.html`, `main.py` (`register`, `save_questionnaire`), `src/database/db.py` (`create_user`, `create_session`, `update_user_questionnaire`).
- **Dependencies:** SQLite (`dinacharya.db`).
- **Verification Evidence:** Verified via `test_flows.py` lines 7-13. Registration and questionnaire update both returned HTTP 200 with valid tokens and database state confirmation.
- **Observed Limitations:** Passwords hashed with unsalted SHA-256; token has no expiration timestamp; questionnaire is only 3 questions instead of 24.
- **Overall Status:** `VERIFIED_WORKING`.

---

### Workflow 2: Prakriti Assessment and Dosha Mapping

#### 1. Intended Behavior
Translates user questionnaire text into an Ayurvedic Tri-Dosha Vector $[V, P, K]$ where $V + P + K = 1.0$, representing baseline mind-body phenotype.

#### 2. Actual Execution Trace
1. **Trigger:** Called within `main.py` (`generate_schedule`, line 212) or during manual profile creation.
2. **Function Invocation:** Calls `DoshaMapper.generate_profile(user_id, questionnaire, telemetry, symptoms)`.
3. **Execution Logic:** Calls `DoshaMapper.classify_prakriti(questionnaire)`.
4. **Keyword Scanning:** Loops over questionnaire response values. Increments:
   - `v_score` if value contains `"vata"`, `"dry"`, `"light"`, `"fast"`, `"cold"`.
   - `p_score` if value contains `"pitta"`, `"hot"`, `"sharp"`, `"acid"`, `"sweat"`.
   - `k_score` if value contains `"kapha"`, `"heavy"`, `"slow"`, `"sleepy"`, `"stable"`.
5. **Vector Computation:** If total matches $> 0$, computes fraction $v_{score}/total$, rounded to 3 decimal places. Constructs `DoshaVector`.
6. **Model Validation:** Pydantic `DoshaVector.normalize_vector` model validator verifies sum and normalizes deviations $> 1e-4$.

- **Components Involved:** `src/perception/dosha_mapper.py`, `src/models.py`.
- **Verification Evidence:** Verified by `tests/test_perception.py::test_classify_prakriti_default` and `test_classify_prakriti_keywords`. Both passed.
- **Observed Limitations:** Uses crude keyword matching. If responses use non-matching synonyms, returns default $[0.50, 0.30, 0.20]$. No ML model or dataset exists.
- **Overall Status:** `PARTIALLY_WORKING` (Functions deterministically as coded; lacks genuine clinical ML classification).

---

### Workflow 3: Ingestion and Processing of Contextual Data

#### 1. Intended Behavior
Continuously ingests and processes environmental conditions (season, weather, temperature), wearable telemetry (HRV, resting heart rate, sleep duration, skin temperature), and calendar busy times to form a comprehensive `UserContext` and detect `VikritiFlags`.

#### 2. Actual Execution Trace
1. **Client Submission:** Client submits `POST /api/schedule/generate` containing `context` and `wearable_telemetry_7d`.
2. **Vikriti Detection:** `DoshaMapper.detect_vikriti` evaluates telemetry:
   - If `body_temp_c > 37.8` or symptom strings contain `"fever"`, sets `has_fever = True`.
   - If `hrv_ms < 45.0` and `sleep_hours < 6.2`, sets `vata_aggravated = True`.
   - If `resting_hr > 82.0` and `hrv_ms < 45.0`, sets `pitta_aggravated = True`.
   - If `sleep_hours > 9.0` and `resting_hr < 55.0`, sets `kapha_aggravated = True`.
3. **Persistence:** State updated in SQLite via `db.update_current_vikriti(user_id, telemetry, symptoms)`.
4. **Context Construction:** `UserContext` object instantiated with season, weather, temperature, calendar events.

- **Components Involved:** `main.py`, `src/perception/dosha_mapper.py`, `src/models.py`, `src/database/db.py`.
- **Verification Evidence:** Verified by `tests/test_perception.py::test_detect_vikriti_vata_aggravation`, `test_detect_vikriti_fever`.
- **Observed Limitations:** Telemetry is manually injected via request payload or toggled in UI session storage. No BLE sync or wearable APIs exist. Weather and calendar tools in `src/planning/tools.py` use simulated mock responses.
- **Overall Status:** `SCAFFOLDED` (Data structure handling works; real hardware and API ingestion pipelines are absent).

---

### Workflow 4: Knowledge Retrieval and Grounded RAG Generation

#### 1. Intended Behavior
Formulates a semantic query representing the user's active Dosha condition and environmental context, queries ChromaDB, and returns canonical guidelines from `Core_Dinacharya_Grounding.pdf`.

#### 2. Actual Execution Trace
1. **Query Formulation:** `AyurvedaKnowledgeBase.retrieve` checks active Vikriti flags. If Vata is elevated in Winter, constructs query:
   `"Ayurvedic daily routine and practices (Dinacharya) to balance and ground aggravated Vata dosha during the Winter season"`.
2. **Dense Vector Query:** Calls ChromaDB collection `grounding_rag_final.query(query_texts=[query], n_results=k)`.
3. **Embedding Computation:** ChromaDB uses SentenceTransformers `all-MiniLM-L6-v2` to vectorize the query.
4. **Cosine Similarity Search:** ChromaDB queries HNSW index across the 140 indexed chunks.
5. **Output Assembly:** Formats top-$k$ retrieved chunks into dictionaries with text, source (`"Core Dinacharya Grounding PDF"`), and placeholder metadata.

- **Components Involved:** `src/knowledge/retriever.py`, `src/knowledge/data/Core_Dinacharya_Grounding.pdf`, ChromaDB, SentenceTransformers.
- **Verification Evidence:** Verified in live tests (`test_rag_and_agent.py` lines 33-42, `benchmark_latency.py`). Successfully retrieved 3-4 genuine classical passages in ~25-50ms.
- **Observed Limitations:** No metadata filtering (e.g., filtering strictly by contraindications or body type); hardcoded score `1.0` returned; unranked chunks passed directly to LLM prompt.
- **Overall Status:** `VERIFIED_WORKING`.

---

### Workflow 5: Daily Routine Planning (LangGraph Execution)

#### 1. Intended Behavior
Orchestrates an agentic workflow that synthesizes user profile, RAG guidelines, and calendar constraints into a 24-hour routine partitioned into morning, midday, and evening blocks.

#### 2. Actual Execution Trace
1. **Graph Compilation:** `DinacharyaPlannerAgent.build_graph()` compiles a 3-node LangGraph: `retrieve -> plan -> execute -> END`.
2. **Node 1 (`retrieve`):** Fetches top-4 authentic guidelines from ChromaDB.
3. **Node 2 (`plan`):**
   - Assembles system instructions and user prompt embedding profile, guidelines, completed tasks, and current time.
   - Calls OpenAI-compatible chat completion endpoint.
   - **Live Execution Result:** NVIDIA NIM returns `HTTP 410 Gone` (model `meta/llama-3.1-70b-instruct` reached end-of-life on 2026-08-26).
   - Catches exception and diverts to `self._fallback_planner(state)`.
   - `_fallback_planner` inspects dominant Dosha and returns pre-calculated classical schedule (e.g., Brahma Muhurta, Abhyanga, Pranayama for Vata).
4. **Node 3 (`execute`):** Inspects `calendar_events`. If overlapping morning meetings are found, shifts practices (e.g., 08:xx to 07:00-07:20).
5. **Output Packing:** Packs blocks into `DinacharyaSchedule` model.

- **Components Involved:** `src/planning/agent.py`, `src/planning/tools.py`, `langgraph`, `openai`.
- **Verification Evidence:** Verified by `tests/test_planning.py::test_planning_agent_generate` and `test_llm_fallback_simulation`.
- **Observed Limitations:** Live hosted LLM generation is broken due to deprecated model ID. Fallback planner reliably produces schedules, masking the LLM failure. Calendar shift logic is rigid string manipulation.
- **Overall Status:** `PARTIALLY_WORKING` (Fallback graph path works; primary LLM generation fails).

---

### Workflow 6: Clinical Safety Validation and Contraindication Enforcement

#### 1. Intended Behavior
Acts as an unbypassable symbolic clinical filter. Inspects generated practices against user contraindications and forcibly replaces hazardous practices with safe therapeutic alternatives.

#### 2. Actual Execution Trace
1. **Entry Point:** In `main.py`, candidate schedule from planner is passed into `validate_and_format_schedule(candidate_schedule, profile, ...)`.
2. **Engine Invocation:** Calls `ClinicalRuleEngine.validate(schedule, profile)`.
3. **Fever Evaluation:** Checks `profile.vikriti_flags.has_fever`.
4. **Sub-practice Overrides:**
   - If `has_fever == True`: scans `morning_block`, `midday_block`, and `evening_block`.
   - Finds any practice whose name contains `"abhyanga"` (oil massage) or `"nasya"` (nasal drops).
   - Strips matching practices.
   - Injects *Nava Jwara Rest & Hydration* (morning), *Midu Langhana* (midday), or *Early Deep Rest* (evening).
5. **Return:** Returns sanitized `DinacharyaSchedule`.

- **Components Involved:** `src/safety/guardrails.py`, `main.py`.
- **Verification Evidence:** Verified by `tests/test_safety.py::test_safety_override_with_fever` and `tests/test_planning.py::test_api_schedule_generation_flow`. In both tests, Abhyanga was successfully stripped and replaced with *Nava Jwara Rest*.
- **Observed Limitations:** Implements only one clinical rule (acute fever). Line 95 timing calculation bug does not break override functionality but represents dead code.
- **Overall Status:** `VERIFIED_WORKING`.

---

### Workflow 7: Schedule Persistence, Caching, and Missed Task Detection

#### 1. Intended Behavior
Caches generated schedules in SQLite to prevent redundant LLM generation, serves cached schedules throughout the day, filters out completed tasks, and automatically detects missed tasks based on clock time to trigger compensation.

#### 2. Actual Execution Trace
1. **Saving:** `db.save_user_schedule(user_id, schedule_data, today_date)` updates `user_state.last_schedule` and `schedule_date`.
2. **Fetch Request:** User visits `/dashboard` or `/routine`. Client calls `getSchedule()` which issues `POST /api/schedule/generate`.
3. **Date Evaluation:** If `schedule_date == today_date`, checks for missed tasks:
   - Loops over practice `time_slot` strings (e.g. `"06:00 - 06:15"`).
   - Parses end hour (`06`).
   - If `current_hour >= end_hour` AND practice name is NOT in `completions`, flags missed task:
     `INFO:AiDincharya:Missed task detected: Wake Up and Morning Hydration (End: 05:45). Recalibrating...`
   - Forces regeneration to compensate.
4. **Filtering:** If no missed tasks and same day, serves cached schedule, filtering out any completed practices so they disappear from the UI.

- **Components Involved:** `main.py` (`generate_schedule`, lines 164-200), `src/database/db.py`.
- **Verification Evidence:** Verified in live server execution logs (`task-63.log` lines 89-138) where missed tasks were detected and compensation was triggered automatically.
- **Observed Limitations:** End hour parsing assumes `" - "` delimiter with integer hour format (`"07:00"`). Malformed time slots silently fail parsing.
- **Overall Status:** `VERIFIED_WORKING`.

---

### Workflow 8: Habit Completion Logging and Adherence Adaptation

#### 1. Intended Behavior
User marks a task complete. The system logs completion for the current date, recalculates adherence score $S_{adj}$, adjusts routine complexity level, and returns an updated behavioral nudge.

#### 2. Actual Execution Trace
1. **Client Action:** User clicks "Mark Complete" in `routine.html` or dashboard task card.
2. **Request:** `POST /api/adherence/log` with `{"user_id": "current", "completed_practices": ["Abhyanga"], "recommended_practices": ["Practice 1", "Practice 2", "Practice 3", "Practice 4", "Practice 5"]}`.
3. **Score Calculation:** `AdherenceTracker.calculate_adherence_score(1, 5)` yields `0.20`.
4. **Database Logging:** Calls `db.update_adherence_score(user_id, 0.20)` and `db.save_completion(user_id, "Abhyanga")`.
5. **Complexity Modulation:** `AdherenceTracker.determine_complexity(0.20)` maps score $<0.50$ to **"Anchor Habits"**.
6. **Nudge Generation:** Returns EAST nudge: `{"title": "Let's focus on the essentials", "message": "We've simplified your routine to just three simple Anchor Habits today..."}`.

- **Components Involved:** `src/static/app.js`, `main.py` (`log_adherence`), `src/behavior/tracker.py`, `src/database/db.py`.
- **Verification Evidence:** Verified by `tests/test_planning.py::test_api_adherence_log_closed_loop` and `test_flows.py` step 5. Adherence score 0.20 returned with complexity "Anchor Habits".
- **Observed Limitations:** Client must supply `recommended_practices` array in the request body; if client supplies an empty array, score defaults to 1.0.
- **Overall Status:** `VERIFIED_WORKING`.

---

### Workflow 9: Conversational Recalibration & Vaidya AI Interaction

#### 1. Intended Behavior
User converses with "Vaidya AI" on `/reasoning` to discuss routines or request timing changes. When changes are requested, the conversation agent tags `[RECALIBRATE]`, triggering a background Planner Agent run to synthesize a modified schedule, rendered to the user as an interactive confirmation flowchart.

#### 2. Actual Execution Trace
1. **Client Message:** User submits chat query on `reasoning.html`. Client calls `POST /api/chat`.
2. **Context Compilation:** `main.py` retrieves `user_state`, formatted questionnaire, current routine blocks, persisted telemetry, and RAG guidelines.
3. **Prompt Construction:** Vaidya AI system prompt is compiled, instructing the model to append `[RECALIBRATE]` if timing changes are discussed.
4. **LLM Execution:** Calls OpenAI completion endpoint.
   - **FAILURE 1:** If `last_schedule` in database is `None`, raises `AttributeError: 'NoneType' object has no attribute 'get'` on line 328 $\to$ HTTP 500.
   - **FAILURE 2:** If `last_schedule` is populated, LLM call to `meta/llama-3.1-70b-instruct` fails with HTTP 410 Gone $\to$ line 462 catches generic exception $\to$ HTTP 500.
5. **Fallback / Normal Flow (Simulated):** If LLM succeeds with `[RECALIBRATE]`:
   - Strips tag, passes directive to `_run_planner()` in a background thread (`ThreadPoolExecutor`, 15s timeout).
   - Planner executes LangGraph with `user_instruction`, validates through `ClinicalRuleEngine`.
   - Returns `{ "response": text, "proposed_schedule": schedule }`.
6. **Client Flowchart:** In `app.js` (`showRecalibrationFlowchart`), renders dynamic animated flowchart of proposed tasks. User clicks "Apply & Synchronize", calling `POST /api/schedule/confirm`.

- **Components Involved:** `src/static/reasoning.html`, `src/static/app.js`, `main.py` (`chat_assistant`, `confirm_schedule`), `src/planning/agent.py`, `src/safety/guardrails.py`.
- **Verification Evidence:** Traceback captured in `task-63.log` line 108; live 500 error reproduced during `test_flows2.py`.
- **Observed Limitations:** Currently unusable due to unhandled NoneType bug and deprecated model ID.
- **Overall Status:** `BROKEN`.

---

### Workflow 10: Frontend-to-Backend State Synchronization

#### 1. Intended Behavior
Client maintains seamless authentication, retrieves active schedules, synchronizes state transitions, and updates views without page reloads.

#### 2. Actual Execution Trace
1. `initApp()` in `app.js` verifies `localStorage.getItem('dinacharya_token')`. If absent on protected pages, redirects to `/login`.
2. Sets up navigation handlers for `#nav-dashboard`, `#nav-routine`, `#nav-insights`, `#nav-logout`.
3. `getSchedule()` implements a 10-minute caching layer via `sessionStorage.getItem('schedule_cache')`.
4. Dispatches asynchronous calls to `loadDashboardData()`, `loadRoutineData()`, `loadInsightsData()`.

- **Components Involved:** `src/static/app.js`, all HTML templates, FastAPI `/api/*` endpoints.
- **Verification Evidence:** Verified via Browser Subagent. Landing, login, registration, and routine timeline views render correctly on `http://localhost:8001/` and `http://localhost:8000/`.
- **Observed Limitations:** Inconsistent cache clearing (`localStorage` vs `sessionStorage` in `onboarding.html`).
- **Overall Status:** `VERIFIED_WORKING`.

---

### Workflow 11: Error Recovery and Fallback Execution

#### 1. Intended Behavior
When upstream model providers, network connections, or database calls fail, the system degrades gracefully without crashing or presenting unhandled exceptions to the user.

#### 2. Actual Execution Trace
1. **Planner Agent Fallback (`_fallback_planner`):**
   - When LLM call throws `openai.APIStatusError` (410), `APITimeoutError`, or JSON decode error, `DinacharyaPlannerAgent.planner_node` catches `Exception as e`.
   - Diverts to `_fallback_planner`.
   - Synthesizes robust, constitutionally accurate fallback routines based on Prakriti and complexity.
   - **Verification:** Verified by `tests/test_planning.py::test_llm_fallback_simulation`.
2. **Chat Assistant Fallback (Deficient):**
   - Catches `openai.APITimeoutError` specifically (lines 455-461) and returns a friendly apologies message.
   - However, for all other exceptions (including HTTP 410, 401, 429, or Python attribute errors), it falls through to line 462, raising `HTTPException(500, detail=...)`.
   - **Verification:** Verified in live tests.

- **Components Involved:** `src/planning/agent.py`, `main.py`.
- **Observed Limitations:** Fallback recovery is asymmetric: robustly implemented in schedule generation, but absent in chat and reasoning.
- **Overall Status:** `PARTIALLY_WORKING`.

---

# PART 2: MANDATORY END-TO-END WORKFLOW VERIFICATION (October 14, 2026)
*Empirical Reassessment of 6 Core Workflows with Live vs. Mocked Traces*

### Mandatory Workflow 1: End-to-End Routine Generation

#### 1. Execution Path
`POST /api/schedule/generate` with `ScheduleGenerateRequest` $\longrightarrow$ User profile lookup in `dinacharya.db` $\longrightarrow$ `ChromaDB` cosine retrieval (140 chunks of `Core_Dinacharya_Grounding.pdf`) $\longrightarrow$ Prompt construction with Ashtanga Hridaya guidelines $\longrightarrow$ `LLMGateway` invocation to `nvidia/nemotron-3.5-lightning-30b-a3b` (`temp=0.0`, `max_tokens=4096`) $\longrightarrow$ `LLMGateway.extract_clean_json` markdown/regex parser $\longrightarrow$ Pydantic `DinacharyaSchedule` validation $\longrightarrow$ `ClinicalRuleEngine.evaluate_safety` $\longrightarrow$ Canonical write to `user_state.schedule` in SQLite $\longrightarrow$ JSON response rendered on `/routine` page.

#### 2. Observed Runtime Evidence
- **Initial Generation (New User / Day):** **28.1 seconds**. Full live RAG query + Nemotron 30B 3-block generation. Output complies with Pydantic contract (morning, midday, evening blocks).
- **Subsequent Loading (Existing User):** **3.09 milliseconds** via `GET /api/schedule/current` (direct DB read) and **3.33 milliseconds** via `POST /api/schedule/generate` (cached daily routine).
- **Evidence Type:** **LIVE-VERIFIED** against running Uvicorn server and NVIDIA API.
- **Status:** **VERIFIED WORKING**.

---

### Mandatory Workflow 2: Conversational Schedule Adaptation

#### 1. Execution Path
Existing schedule loaded $\longrightarrow$ User submits message: `"I have an urgent client review tonight from 8:30 PM to 10:00 PM"` $\longrightarrow$ `POST /api/chat` invokes `DinacharyaPlannerAgent` with circumstance detection $\longrightarrow$ Agent preserves dinner/sleep, shifts `Trataka` meditation to `22:15 - 22:30` $\longrightarrow$ Agent outputs proposed adaptation with confirmation prompt $\longrightarrow$ User responds: `"Yes, update it"` $\longrightarrow$ `main.py` NLP acceptance parser recognizes confirmation intent $\longrightarrow$ Validated via `ClinicalRuleEngine` $\longrightarrow$ Commits updated schedule to SQLite `user_state` $\longrightarrow$ Creates event in `notifications` outbox $\longrightarrow$ Returns updated schedule $\longrightarrow$ Navigating to `/routine` or calling `GET /api/schedule/current` immediately displays Trataka at `22:15 - 22:30`.

#### 2. Observed Runtime Evidence
- **Empirical Proof:** Tested end-to-end via Python test client and manual HTTP request.
- **Persistence Verification:** Verified via raw SQLite query on `user_state`:
  `SELECT schedule FROM user_state WHERE user_id='test_user'` reflects `"activity": "Trataka", "time": "22:15 - 22:30"`.
- **Survives Logout & Refresh:** Yes. `tests/test_routine_persistence.py::test_3_accepting_trataka_schedule_change_persists` passed in 2.1s.
- **Evidence Type:** **LIVE-VERIFIED** with fresh database reads.
- **Status:** **VERIFIED WORKING**.

---

### Mandatory Workflow 3: Model-Driven Native Tool Calling

#### 1. Execution Path
User query requiring knowledge or safety verification $\longrightarrow$ `LLMGateway.execute_tool_loop` binds `AVAILABLE_PLANNER_TOOLS` (`rag_ayurveda_search`, `check_clinical_safety`, `get_current_schedule`, `detect_calendar_conflicts`, `update_schedule_activity`) $\longrightarrow$ LLM emits native `tool_calls` structure $\longrightarrow$ Gateway extracts `function.name` and arguments $\longrightarrow$ Dispatches to `src/planning/tools.py::execute_planner_tool` $\longrightarrow$ Tool executes and returns output payload $\longrightarrow$ Result appended to message history with role `"tool"` $\longrightarrow$ Model processes result and delivers final synthesized text.

#### 2. Observed Runtime Evidence
- **Benchmark & Diagnostic Execution:** In `scripts/benchmark_models.py` (Test D) and `tests/test_llm_recovery.py::test_tool_execution_dispatcher`, `rag_ayurveda_search` and `check_clinical_safety` execute successfully, returning in **7.68 seconds** on Nemotron 30B.
- **Production Endpoint Execution Gap:** In live `main.py` (`/api/chat`) and `src/planning/agent.py` (`planner_node`), tool calling is **NOT passed to the live LLM**. Instead, `main.py` inspects prompt strings for `[RECALIBRATE]` and calls Python functions directly in code.
- **Evidence Type:** **TEST-VERIFIED in gateway & harness; UNPLUMBED in production chat/graph routes**.
- **Status:** **PARTIALLY IMPLEMENTED (DEF-19)**.

---

### Mandatory Workflow 4: Notification Creation and Delivery

#### 1. Execution Path
Material schedule adaptation occurs in chat $\longrightarrow$ `main.py:504-518` calculates MD5 idempotency key `hashlib.md5(f"{user_id}:{title}:{date}".encode()).hexdigest()` $\longrightarrow$ Inserts row into SQLite `notifications` table (`id`, `user_id`, `type='schedule_update'`, `title`, `message`, `data`, `is_read=0`) $\longrightarrow$ Client requests `GET /api/notifications` $\longrightarrow$ Returns JSON list of unread alerts $\longrightarrow$ Client sends `POST /api/notifications/{id}/read` $\longrightarrow$ Database updates `is_read = 1`.

#### 2. Observed Runtime Evidence
- **DB & API Verification:** Persistent record insertion and idempotency tested and passed in `tests/test_llm_recovery.py::test_notification_persistence_and_idempotency` and `test_api_notifications_endpoints`.
- **Delivery Limitations:**
  - In-app REST API functions correctly.
  - External delivery channels (FCM push, SMS, email) are **unimplemented**.
  - Frontend navbar bell icon in `app.js` has no attached click event listener or dropdown view.
- **Evidence Type:** **LIVE-VERIFIED in DB & API; ABSENT in Push & UI**.
- **Status:** **PARTIALLY IMPLEMENTED (DEF-20)**.

---

### Mandatory Workflow 5: Failure Recovery and Error Resilience

#### 1. Execution Path
1. **Provider Outage / 410 / Timeout Simulation:** When the LLM provider fails, `LLMGateway` catches the error, retries with exponential backoff, attempts secondary model (`openai/gpt-oss-20b`), and if exhausted, invokes deterministic fallback generators.
2. **Malformed JSON Recovery:** When model includes chain-of-thought markdown, `extract_clean_json` strips markdown blocks and extracts the JSON substring.
3. **Missing / Null Schedule State:** When a new user has `last_schedule = None`, `main.py` uses `state.get("last_schedule") or {}` to prevent `AttributeError`.
4. **Database Write Failure:** When SQLite transactions fail, endpoints roll back and return explicit `HTTP 500` with descriptive error details rather than silently claiming success.

#### 2. Observed Runtime Evidence
- Verified by:
  - `tests/test_routine_persistence.py::test_6_failed_database_write_does_not_produce_success`
  - `tests/test_routine_persistence.py::test_7_failed_llm_call_does_not_hang`
  - `tests/test_llm_recovery.py::test_insights_endpoint_resilience`
  - `tests/test_llm_recovery.py::test_chat_null_last_schedule`
- **Evidence Type:** **LIVE & TEST-VERIFIED**.
- **Status:** **VERIFIED WORKING**.

---

### Mandatory Workflow 6: Repeat Access, Caching, and State Consistency

#### 1. Execution Path
User opens `/routine` page $\longrightarrow$ `app.js` fetches `GET /api/schedule/current` $\longrightarrow$ Server reads SQLite `user_state.schedule` directly $\longrightarrow$ Returns instantly $\longrightarrow$ User navigates to `/dashboard` $\longrightarrow$ User returns to `/routine` $\longrightarrow$ Schedule renders from `sessionStorage` cache and synchronizes in background $\longrightarrow$ User hard refreshes browser $\longrightarrow$ Database read completes in **3.09 milliseconds** with identical schedule state.

#### 2. Observed Runtime Evidence
- **Benchmark Timing:** 3.09 ms per request. Zero LLM or RAG calls executed on repeat visits.
- **Persistence Across Sessions:** Tested across distinct sessions and authenticated tokens.
- **Zero Duplicates:** Verified by `tests/test_routine_persistence.py::test_8_repeated_schedule_change_no_duplicates`.
- **Evidence Type:** **LIVE-VERIFIED**.
- **Status:** **VERIFIED WORKING**.


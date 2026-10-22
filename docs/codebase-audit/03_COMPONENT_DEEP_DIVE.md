# AI DINCHARYA: COMPLETE CODEBASE FORENSIC AUDIT
## Document 03: Component Deep Dive

**Audit Date:** October 13, 2026  
**Auditor:** Forensic Engineering Audit Agent (DeepMind Antigravity)  
**Target Codebase:** AI Dincharya (Branch `Siddharth`, commit `9311925`)  

---

### Subsystem A: Application and API Layer

#### 1. Identity & Purpose
- **Primary File:** [main.py](file:///Users/Siddharth/Documents/AiDincharya/main.py)
- **Role:** Web server, API routing, session authorization, and static asset host.
- **Framework:** FastAPI with Uvicorn, Starlette StaticFiles, and CORSMiddleware.

#### 2. Routes & HTTP Methods
| Method | Route Path | Protected | Request Model | Response Model / Type | Handler Function |
|---|---|---|---|---|---|
| `GET` | `/` | No | None | `HTMLResponse` | `read_root()` |
| `GET` | `/login` | No | None | `HTMLResponse` | `login_page()` |
| `GET` | `/register` | No | None | `HTMLResponse` | `register_page()` |
| `GET` | `/dashboard` | No | None | `HTMLResponse` | `dashboard_page()` |
| `GET` | `/routine` | No | None | `HTMLResponse` | `routine_page()` |
| `GET` | `/reasoning` | No | None | `HTMLResponse` | `reasoning_page()` |
| `GET` | `/onboarding` | No | None | `HTMLResponse` | `onboarding_page()` |
| `POST` | `/api/auth/register` | No | `UserAuthRequest` | `AuthResponse` | `register()` |
| `POST` | `/api/auth/login` | No | `UserAuthRequest` | `AuthResponse` | `login()` |
| `POST` | `/api/user/questionnaire` | Yes | `QuestionnaireRequest` | `{"status": "success"}` | `save_questionnaire()` |
| `GET` | `/api/user/state` | Yes | None | `Dict[str, Any]` | `get_state()` |
| `POST` | `/api/schedule/generate` | Yes | `ScheduleGenerateRequest` | `Dict[str, Any]` | `generate_schedule()` |
| `POST` | `/api/schedule/confirm` | Yes | `Dict[str, Any]` | `{"status": "success"}` | `confirm_schedule()` |
| `POST` | `/api/adherence/log` | Yes | `AdherenceLogRequest` | `Dict[str, Any]` | `log_adherence()` |
| `GET` | `/api/insights` | Yes | None | `Dict[str, Any]` | `get_dynamic_insights()` |
| `POST` | `/api/chat` | Yes | `ChatRequest` | `Dict[str, Any]` | `chat_assistant()` |
| `GET` | `/api/chat/history` | Yes | None | `Dict[str, Any]` | `get_chat_history_api()` |
| `DELETE` | `/api/chat/history` | Yes | None | `{"status": "success"}` | `clear_chat_history()` |
| *(None)* | *(Unmounted)* | No | `Dict[str, Any]` | `{"status": "ok"}` | `remote_log()` (L515-518) |

#### 3. Request Lifecycle & Validation
- **Authentication:** `get_current_user` dependency parses `Authorization: Bearer <token>`. Looks up token in SQLite `sessions` table. Raises `HTTPException(401, "Unauthorized")` if header is missing or `HTTPException(401, "Invalid token")` if token does not match an active session.
- **CORS:** Broadly configured with `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.
- **Validation:** Pydantic v2 models validate incoming JSON. Failed validations trigger standard FastAPI 422 Unprocessable Entity responses.

#### 4. Defects & Limitations
- **Unhandled NoneType in `chat_assistant` (Line 328):**
  ```python
  current_routine = state.get("last_schedule", {}).get("schedule", {})
  ```
  When `last_schedule` is `None` in the database, `state["last_schedule"]` evaluates to `None`. Python's `dict.get("last_schedule", {})` returns `None` (since the key exists), causing `.get("schedule", {})` to raise `AttributeError: 'NoneType' object has no attribute 'get'`. This returns HTTP 500 whenever a user chats before generating a schedule.
- **Unmounted `remote_log` function (Line 515):** Defined without an `@app.post("/api/remote-log")` decorator, rendering browser remote logging unreachable.
- **Monolithic design:** API routes directly execute raw SQL queries, initialize heavy ML pipelines, and format responses in single blocks exceeding 100 lines.

---

### Subsystem B: Dosha Mapping and Machine Learning

#### 1. Identity & Purpose
- **File:** [src/perception/dosha_mapper.py](file:///Users/Siddharth/Documents/AiDincharya/src/perception/dosha_mapper.py)
- **Role:** Translates user questionnaire inputs and wearable telemetry into computable Prakriti and Vikriti representations.

#### 2. Implementation Mechanics
- **Prakriti Classification (`classify_prakriti`, lines 14-43):**
  - **Algorithm:** Case-insensitive substring keyword matching.
  - Vata keywords: `"vata"`, `"dry"`, `"light"`, `"fast"`, `"cold"`.
  - Pitta keywords: `"pitta"`, `"hot"`, `"sharp"`, `"acid"`, `"sweat"`.
  - Kapha keywords: `"kapha"`, `"heavy"`, `"slow"`, `"sleepy"`, `"stable"`.
  - Normalization: $V = v_{count} / total$, $P = p_{count} / total$, $K = k_{count} / total$.
  - Default Fallback: `DoshaVector(vata=0.50, pitta=0.30, kapha=0.20)`.
- **Vikriti Anomaly Detection (`detect_vikriti`, lines 46-93):**
  - **Algorithm:** Hardcoded heuristic threshold logic:
    - Vata Aggravation: $\text{HRV} < 45.0\text{ ms}$ AND $\text{Sleep} < 6.2\text{ hours}$.
    - Pitta Aggravation: $\text{RHR} > 82.0\text{ bpm}$ AND $\text{HRV} < 45.0\text{ ms}$.
    - Kapha Aggravation: $\text{Sleep} > 9.0\text{ hours}$ AND $\text{RHR} < 55.0\text{ bpm}$.
    - Fever Flag (`has_fever`): $\text{Temperature} > 37.8^\circ\text{C}$ OR symptom strings matching `"fever"` / `"temp"`.

#### 3. Verification & Discrepancies
- **Status:** `PARTIALLY_WORKING`. The Python code functions deterministically and passes unit tests in `tests/test_perception.py`.
- **Discrepancy:** The capstone documentation (`Dinacharya_Full_Report.pdf`, Section 6.1.2 & Figure 6.3) claims a supervised machine learning model (Multilayer Perceptron / Random Forest) trained on a 24-item validated questionnaire, accompanied by an unsupervised Isolation Forest for physiological anomaly detection. In reality, the codebase contains zero machine learning models, zero trained weights, zero training scripts, and zero dataset files for Prakriti classification.

---

### Subsystem C: Multimodal Ingestion

#### 1. Identity & Purpose
- **Intended Scope:** Ingestion of static questionnaires, continuous wearable telemetry (Apple Health / Google Health Connect via BLE), calendar busy events, and ambient weather.

#### 2. Actual Implementation Status by Modality
1. **Questionnaires:** `IMPLEMENTED_UNVERIFIED`. The frontend questionnaire (`onboarding.html`) captures only 3 single-choice questions (`q_digestion`, `q_sleep`, `q_stress`). Transmitted as JSON to `/api/user/questionnaire`.
2. **Wearables & Physiology:** `SCAFFOLDED`. No wearable APIs, SDKs (Apple HealthKit / Health Connect), or BLE ingestion services exist. Telemetry (`hrv_ms`, `resting_hr`, `sleep_hours`, `body_temp_c`) is ingested purely as optional JSON fields in `ScheduleGenerateRequest`. In the UI, wearable telemetry is simulated by a single "Simulate Fever" checkbox in `app.js` line 59, which sets `body_temp_c: 38.5` in session storage.
3. **Calendar Integration:** `SCAFFOLDED`. In `src/planning/tools.py` (`check_calendar_conflicts`), calendar events are checked using substring matching for `"meeting"`, `"call"`, or `"class"`. No iCalendar (.ics), Google Calendar, or Microsoft Outlook integration exists.
4. **Weather Integration:** `SCAFFOLDED`. In `src/planning/tools.py` (`get_weather_context`), weather context is hardcoded to return static dictionary responses for Bangalore (28.5°C) and Delhi (41.2°C), or a default 24.0°C fallback.

---

### Subsystem D: RAG and Knowledge Retrieval

#### 1. Identity & Purpose
- **File:** [src/knowledge/retriever.py](file:///Users/Siddharth/Documents/AiDincharya/src/knowledge/retriever.py)
- **Role:** Canonical Ayurvedic grounding engine providing domain guidance to the planning agent.
- **Corpus:** [Core_Dinacharya_Grounding.pdf](file:///Users/Siddharth/Documents/AiDincharya/src/knowledge/data/Core_Dinacharya_Grounding.pdf) (20.9 MB, classical textbook extract).

#### 2. Implementation Mechanics
- **Chunking:** `langchain_text_splitters.RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`.
- **Embedding Model:** `chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(model_name='all-MiniLM-L6-v2')`.
- **Vector Store:** `chromadb.PersistentClient(path='src/knowledge/data/chroma')`, collection `grounding_rag_final`.
- **Collection State:** Verified to contain exactly **140 document chunks**.
- **Query Construction:** Dynamically builds a natural language query based on active Vikriti flags or dominant Prakriti, combined with the current season:
  ```
  "Ayurvedic daily routine and practices (Dinacharya) to balance and ground aggravated Vata dosha during the Winter season"
  ```
- **Retrieval:** Calls `self.collection.query(query_texts=[query], n_results=k)`.

#### 3. Verification & Limitations
- **Status:** `VERIFIED_WORKING`. Verified in live diagnostic executions (`test_rag_and_agent.py` lines 34-41) where it consistently retrieves top-3/top-4 genuine classical passages regarding Dinacharya routines, Ritucharya seasonal adjustments, and dietary guidelines.
- **Limitations:**
  - Metadata filtering is completely unused (the query executes across all chunks without filtering by dosha or chapter tags).
  - Hardcoded similarity score (`"score": 1.0`) is returned regardless of true vector cosine distance.
  - Single large PDF ingested once; no provenance tracking to specific chapter/verse citations.

---

### Subsystem E: Agentic Planning and Orchestration

#### 1. Identity & Purpose
- **File:** [src/planning/agent.py](file:///Users/Siddharth/Documents/AiDincharya/src/planning/agent.py)
- **Role:** Plan-and-Execute agent synthesizing daily routine schedules conforming to user profile, guidelines, and calendar commitments.

#### 2. Architecture & Graph Structure
- Built with `langgraph.graph.StateGraph(AgentState)`:
  - **Node 1 (`retrieve`):** Calls `query_ayurvedic_knowledge` to obtain classical RAG guidelines.
  - **Node 2 (`plan`):** Formulates prompt and calls LLM (or executes fallback) to generate daily routine JSON blocks (`morning_block`, `midday_block`, `evening_block`).
  - **Node 3 (`execute`):** Inspects calendar events and applies shift heuristics to resolve timing overlaps.
  - **Graph Topology:** Linear DAG: `retrieve -> plan -> execute -> END`.

#### 3. Model Integration & Fallback Logic
- **Client:** OpenAI-compatible client initialized against `NVIDIA_BASE_URL` (`https://integrate.api.nvidia.com/v1`) using model `meta/llama-3.1-70b-instruct`.
- **CRITICAL FAILURE:** In live execution (October 2026), NVIDIA NIM returns **`HTTP 410 Gone: The model 'meta/llama-3.1-70b-instruct' has reached its end of life on 2026-08-26T09:00:00Z and is no longer available.`**
- **Deterministic Fallback (`_fallback_planner`, lines 221-248):**
  - When LLM call throws an exception, `_fallback_planner` intercepts the error and returns a predefined, constitutionally tailored routine based on dominant Dosha (`vata`, `pitta`, `kapha`) and complexity (`Anchor Habits`, `Moderate`, `Advanced`).
  - **Status:** `VERIFIED_WORKING`. The fallback engine ensures that `/api/schedule/generate` succeeds and outputs structurally valid schedules even when the upstream LLM is completely down.

---

### Subsystem F: Safety Guardrail Engine

#### 1. Identity & Purpose
- **File:** [src/safety/guardrails.py](file:///Users/Siddharth/Documents/AiDincharya/src/safety/guardrails.py)
- **Role:** Symbolic clinical safety boundary validating candidate schedules before user delivery.

#### 2. Implementation Mechanics
- Implements `ClinicalRuleEngine.validate(schedule, profile)`:
  - Evaluates `profile.vikriti_flags.has_fever`.
  - If `has_fever == True`:
    - Scans all blocks for practices containing `"abhyanga"` or `"nasya"` in their name.
    - Strips matching practices.
    - Injects safe traditional alternatives:
      - Morning: *Nava Jwara Rest & Hydration* (30 min, warm ginger/coriander water).
      - Midday: *Midu Langhana (Light Fasting Rest)* (30 min, light gruel/herbal tea).
      - Evening: *Early Deep Rest* (30 min, sensory withdrawal and sleep).
- **Enforcement Points:**
  - Mandatory in `main.py` (`validate_and_format_schedule`, line 131) for routine generation.
  - Mandatory in `main.py` (`_run_planner`, line 430) for chat recalibrations.
  - Cannot be bypassed by LLM prompt output.

#### 3. Defects & Limitations
- **Logic Bug in `_override_contraindicated_practices` (Line 95):**
  ```python
  replacement.time_slot = "06:30 - 07:00" if block and block == cleaned_block else replacement.time_slot
  ```
  This line is situated inside `if replaced:`. However, if `replaced` is True, `block == cleaned_block` is mathematically impossible (since items were removed). Thus, the condition evaluates to False 100% of the time.
- **Limited Scope:** Exactly one clinical rule is implemented (acute fever / *Nava Jwara*). Other major Ayurvedic contraindications described in canonical literature (e.g., Ama/indigestion, pregnancy, menstrual cycle, post-meal exercise) are absent.

---

### Subsystem G: Schedule Generation and Contextual Planning

#### 1. Identity & Purpose
- Constructing 24-hour Dinacharya schedules tailored to circadian blocks (Pratah/Morning, Madhyanha/Midday, Sayam/Evening).

#### 2. Implementation Mechanics
- Defined in `main.py` (`generate_schedule`, lines 147-249).
- **Circadian Schedule Blocks:**
  - `morning_block`: Practices between sunrise and midday (e.g., waking, hydration, oral hygiene, oil massage, pranayama).
  - `midday_block`: Peak digestive practices (e.g., *Mitahara* heaviest meal, mindful walking).
  - `evening_block`: Wind-down practices (e.g., light dinner, screen cut-off, *Trataka* meditation).
- **Smart Daily Caching & Missed Task Recalibration:**
  - Compares `schedule_date` against `today_date`. If date changed, forces regeneration.
  - Iterates through cached practice `time_slot` strings (e.g., `"06:00 - 07:00"`). Extracts end hour (`07`). If `current_hour >= end_hour` and the practice is NOT logged in `completions`, flags the task as "missed" and triggers dynamic routine compensation.

---

### Subsystem H: Adherence, Nudging, and Behavioral Adaptation

#### 1. Identity & Purpose
- **File:** [src/behavior/tracker.py](file:///Users/Siddharth/Documents/AiDincharya/src/behavior/tracker.py)
- **Role:** Behavioral adaptation engine tracking adherence scores and modulating routine complexity.

#### 2. Implementation Mechanics
- **Adherence Score Formula:**
  $$S_{adj} = \text{round}\left(\min\left(\max\left(\frac{\text{completed\_count}}{\text{recommended\_count}}, 0.0\right), 1.0\right), 2\right)$$
- **Complexity Escalation / De-escalation:**
  - $S_{adj} < 0.50 \implies$ **"Anchor Habits"** (3 core foundational habits to rebuild momentum).
  - $0.50 \le S_{adj} < 0.80 \implies$ **"Moderate"** (standard daily Dinacharya).
  - $S_{adj} \ge 0.80 \implies$ **"Advanced"** (specialized Sattva-enhancing practices).
- **EAST Nudges:** Generates Easy, Attractive, Social, Timely nudges as dictionary responses (`title`, `message`).

#### 3. Verification & Limitations
- **Status:** `VERIFIED_WORKING`. Verified in `tests/test_planning.py::test_api_adherence_log_closed_loop`. When adherence is logged at 0.20, routine complexity dynamically steps down to "Anchor Habits".
- **Limitations:** No push notification infrastructure (FCM/APNS); nudges are delivered solely as passive JSON payloads in API responses. Empty class `class BehaviorEngine: pass` indicates incomplete planned expansion.

---

### Subsystem I: Persistence and Data Management

#### 1. Identity & Purpose
- **File:** [src/database/db.py](file:///Users/Siddharth/Documents/AiDincharya/src/database/db.py)
- **Database:** Local SQLite database at `dinacharya.db`.

#### 2. Schema Inventory
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE user_state (
    user_id INTEGER PRIMARY KEY,
    questionnaire_responses TEXT,      -- JSON string
    telemetry_baselines TEXT,          -- JSON string
    current_vikriti TEXT DEFAULT '{}', -- JSON string
    adherence_score REAL DEFAULT 1.0,
    has_completed_onboarding BOOLEAN DEFAULT FALSE,
    last_schedule TEXT,                -- JSON string
    schedule_timestamp REAL DEFAULT 0,
    schedule_date TEXT DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    practice_name TEXT NOT NULL,
    completion_date DATE DEFAULT (CURRENT_DATE),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
```

#### 3. Security & Design Deficiencies
- **Unsalted Password Hashes:** Passwords are stored as raw `hashlib.sha256(password.encode()).hexdigest()` without salt or key stretching (e.g., bcrypt/Argon2). Vulnerable to rainbow table attacks.
- **Unchecked Raw SQL String Queries:** Basic parameter substitution is used, but lack of ORM or repository abstraction invites maintenance drift.
- **JSON Blob Storage:** Critical domain entities (`last_schedule`, `questionnaire_responses`, `current_vikriti`) are stored as unstructured text blobs inside `user_state`, preventing relational querying, validation, or index optimization.

---

### Subsystem J: Frontend and User Experience

#### 1. Identity & Purpose
- **Directory:** [src/static/](file:///Users/Siddharth/Documents/AiDincharya/src/static/)
- **Technology:** HTML5, Tailwind CSS (via CDN), Google Fonts (Playfair Display & Inter), Material Symbols, Vanilla JavaScript ([app.js](file:///Users/Siddharth/Documents/AiDincharya/src/static/app.js)).

#### 2. Screen Inventory & Backend Integration
1. **Landing Page (`index.html`):** Renders public introduction, core pillars, and authentication redirects. Pure static presentation.
2. **Authentication (`login.html`, `register.html`):** Fully integrated with `/api/auth/login` and `/api/auth/register`. Stores session bearer tokens in `localStorage`.
3. **Onboarding Questionnaire (`onboarding.html`):** Renders 3 questionnaire inputs, posts to `/api/user/questionnaire`, and navigates to `/dashboard`.
4. **Dashboard (`dashboard.html`):** Dynamically fetches schedule via `app.js` (`getSchedule`), displays top morning tasks, allows inline task completion logging (`/api/adherence/log`), and presents Dosha status indicators.
5. **Timeline View (`routine.html`):** Renders 24-hour chronological timeline with expandable cards showing Ayurvedic rationale and a "Mark Complete" button.
6. **Reasoning Engine (`reasoning.html`):** Conversational chat interface ("Vaidya AI") rendering conversation history from `/api/chat/history`, sending queries to `/api/chat`, and dynamically displaying a visual temporal recalibration flowchart when schedule alterations are agreed upon.

#### 3. Defects & Limitations
- **Session Cache Storage Key Discrepancy:** `onboarding.html` line 139 removes `localStorage.getItem('dinacharya_schedule_cache')`, whereas `app.js` lines 34 and 73 stores and purges `sessionStorage.getItem('schedule_cache')`. This causes stale cached schedules to persist across onboarding transitions.
- **Chat Failure UI:** When `/api/chat` fails with HTTP 500 (due to model EOL or null schedule), the typing indicator is removed, but no error toast or explanatory message is displayed to the user.

---

### Subsystem K: Configuration, Dependencies, and Infrastructure

#### 1. Identity & Purpose
- **Files:** `src/config.py`, `requirements.txt`, `.env`.

#### 2. Inventory & Analysis
- **Python Version:** Python 3.11.7 (Darwin arm64).
- **Core Dependencies:**
  - `fastapi>=0.100.0`, `uvicorn>=0.20.0`, `pydantic>=2.0.0` (Web API stack)
  - `langgraph>=0.0.10` (Agent workflow)
  - `openai>=1.0.0` (Client for hosted inference)
  - `chromadb>=0.5.0`, `sentence-transformers>=3.0.0`, `langchain-text-splitters>=0.2.0`, `pypdf>=5.0.0` (RAG stack)
  - `google-generativeai>=0.7.0` (Unused in active branch `Siddharth`, but imported on branch `Swapnil`/`main`)
- **Port Management:** [main.py](file:///Users/Siddharth/Documents/AiDincharya/main.py#L521-L541) incorporates an automated dynamic port scanner (`find_unused_port`) that probes from port 8000 upwards until an unbound socket is found, preventing startup collisions.

---

### Subsystem L: Tests, Evaluation, and Reliability

#### 1. Inventory & Execution Evidence
- **Pytest Suite (`tests/`):**
  - Command: `.venv/bin/pytest -v`
  - Results: **15 passed, 1 warning in 42.81s**.
  - `tests/test_perception.py`: 5 unit tests passed.
  - `tests/test_safety.py`: 2 unit tests passed.
  - `tests/test_planning.py`: 8 integration tests passed (verifying LangGraph execution, calendar checks, fallback planning, closed-loop adherence scaling).
- **Integration Test Scripts (`test_flows.py`, `test_flows2.py`):**
  - `test_flows.py`: Exit code 0. Validates user registration, questionnaire onboarding, schedule generation with fever override, and adherence logging against active server.
  - `test_flows2.py`: Exit code 0, but silently logged `Response: None` due to unhandled HTTP 500 error on chat recalibration.
- **Diagnostic Script (`test_rag_and_agent.py`):**
  - Exit code 0, but logged: `FAILED: Agent generation failed: 'dict' object has no attribute 'morning_block'` on line 57 due to type expectation mismatch.
- **Latency Benchmark (`benchmark_latency.py`):**
  - Confirms non-LLM pipeline overhead is very fast: DoshaMapper (~0.1ms), ClinicalRuleEngine (~0.1ms), AdherenceTracker (~0.1ms), ChromaDB retrieval (~15-50ms).
  - Confirms LLM call takes 10-30s or fails when free-tier hosted models time out or deprecate.

---

### Subsystem M: Security, Privacy, and Operational Risks

1. **Weak Password Hashing:** `create_user` in `src/database/db.py` uses unsalted SHA-256 (`hashlib.sha256(password.encode()).hexdigest()`). Highly vulnerable to rainbow tables. Must be upgraded to Argon2id or bcrypt.
2. **Session Token Exposure:** Session tokens are stored in plaintext in the SQLite `sessions` table without expiration timestamps or cryptographic signatures (e.g., JWT). Tokens never expire unless manually deleted.
3. **CORS Wildcard:** `allow_origins=["*"]` allows any web origin to interact with the API with credentials enabled.
4. **Secret Storage:** API keys (`PUTER_API_KEY`, `NVIDIA_API_KEY`) reside in a plaintext `.env` file in the repository root.
5. **No Rate Limiting:** None of the public endpoints (`/api/auth/register`, `/api/auth/login`, `/api/schedule/generate`, `/api/chat`) have rate limiting, exposing the system to denial-of-service or credit exhaustion attacks.

---

### Subsystem N: Documentation, Prompts, and Research Artifacts

1. **System Design & Academic Claims:** The capstone documentation (`Dinacharya_Full_Report.pdf`, `Dinacharya Synopsis.pdf`) provides a thorough, scholarly exposition of Ayurvedic principles, ritucharya seasonality, chronobiology, and machine learning architectures.
2. **Discrepancy Between Claims and Code:**
   - Documented: "Multi-layer Perceptron (MLP) Prakriti Classifier" $\implies$ Implemented: Case-insensitive keyword search.
   - Documented: "Isolation Forest Anomaly Detection" $\implies$ Implemented: 4 static threshold checks.
   - Documented: "Push Notification Delivery via FCM/APNS" $\implies$ Implemented: In-memory dictionary return values.
   - Documented: "Full Clinical Contraindication Registry" $\implies$ Implemented: Single fever override check.
3. **Prompts:** Prompts are embedded directly inside Python strings in `agent.py` (lines 97-148) and `main.py` (lines 368-382). While detailed and authentic in Ayurvedic terminology, they are tightly coupled to code rather than versioned as external prompt templates.

---

### Subsystem O: Centralized LLM Gateway (`src/llm_gateway.py`) - Reassessment Deep Dive

#### 1. Purpose & Implementation
The `LLMGateway` was created to isolate application routes from raw OpenAI SDK calls and provide a unified, resilient interface for LLM execution across all scheduling, reasoning, and insight tasks.

#### 2. Architecture & Algorithms
- **Model Routing & Fallback:** Primary model defaults to `nvidia/nemotron-3.5-lightning-30b-a3b` with seamless fallback to `openai/gpt-oss-20b`.
- **Reasoning Token Budgeting:** Sets `max_tokens=4096` by default. This resolves the critical failure mode where Nemotron's 1,500–2,600 reasoning tokens exhaust small default limits (e.g. 1024 or 2048) before generating the final JSON payload.
- **Resilient JSON Parser (`extract_clean_json`):**
  - Strips markdown code fences (` ```json ... ``` `).
  - Uses regex boundary detection (`\{[\s\S]*\}`) to extract structured JSON even when the model precedes output with conversational chain-of-thought or markdown headers.
  - Automatically converts malformed single quotes and unescaped newlines.
- **Native Tool Execution Loop (`execute_tool_loop`):** Accepts OpenAI function definitions, passes `tools` parameter to the model, inspects `tool_calls`, dispatches execution to `src/planning/tools.py`, appends tool role responses to message history, and prompts the model for the subsequent structured response.
- **Deterministic Fallbacks:** Provides hardcoded, clinically valid fallback generators for insights and daily schedules when network outages or provider timeouts occur.

---

### Subsystem P: Planner Tools & Execution Dispatcher (`src/planning/tools.py`) - Reassessment Deep Dive

#### 1. Inventory of Tools
Defined in `AVAILABLE_PLANNER_TOOLS` with formal JSON schema contracts:
1. `rag_ayurveda_search`: Queries ChromaDB for Ashtanga Hridaya guidelines matching query strings.
2. `check_clinical_safety`: Executes `ClinicalRuleEngine.evaluate_safety` against scheduled blocks.
3. `get_current_schedule`: Reads user's active schedule from SQLite.
4. `detect_calendar_conflicts`: Evaluates schedule against calendar commitments.
5. `update_schedule_activity`: Modifies specific activity times and durations.

#### 2. Actual Runtime Path
- **Dispatcher:** `execute_planner_tool(tool_name, tool_args, context)` dispatches calls to actual underlying Python implementations.
- **Benchmark & Unit Test Status:** Verified 100% operational in `scripts/benchmark_models.py` (Test D) and `tests/test_llm_recovery.py::test_tool_execution_dispatcher`.
- **Production Integration Gap:** Live `/api/chat` and `planner_node` do not pass `AVAILABLE_PLANNER_TOOLS` in their LLM calls. They call tools sequentially via hardcoded Python node logic.

---

### Subsystem Q: Circumstance Adaptation Engine (`src/planning/agent.py`) - Reassessment Deep Dive

#### 1. Purpose & Scope
Extends the planner to adapt existing schedules to real-world interruptions without discarding unrelated healthy routines.

#### 2. Implemented Adaptation Scenarios:
1. **Scenario 1 (Missed Activity):** User wakes up late or skips morning routine; shifts flexible practices into open midday slots.
2. **Scenario 2 (Calendar Conflict):** User adds client meeting (e.g., 20:30–22:00); shifts Trataka to 22:15–22:30 without disturbing dinner or sleep.
3. **Scenario 3 (Fever / Acute Illness):** Automatically cancels Abhyanga/Nasya and injects rest and light diet recommendations.
4. **Scenario 4 (Task Overrun):** Deep work extends into scheduled slots; compresses evening routine gracefully.
5. **Scenario 5 (Priority Change):** User requests focus on sleep hygiene; expands evening meditation.
6. **Scenario 6 (Infeasible Constraints):** Impossible schedule demands return explicit clinical guidance rather than silent failures.

#### 3. Verification Evidence
All 6 scenarios are tested and passing in `tests/test_llm_recovery.py` (Tests 7 through 12).

---

### Subsystem R: Notification Persistence Subsystem (`src/database/db.py`, `main.py`) - Reassessment Deep Dive

#### 1. Database Schema
Created table `notifications` in `dinacharya.db`:
```sql
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    data TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 2. REST Endpoints
- `GET /api/notifications`: Returns list of notifications for authenticated user, supporting `unread_only=true`.
- `POST /api/notifications/{id}/read`: Marks notification as read in SQLite.

#### 3. Event Creation & Idempotency
- Schedule adaptations automatically create notification records summarizing changes (e.g. "Schedule Updated: Trataka shifted to 22:15").
- Incorporates MD5 deduplication hashing (`idempotency_key = hashlib.md5(f"{user_id}:{title}:{date}".encode()).hexdigest()`) to prevent duplicate notification spam.
- **Gaps:** External push notification services (FCM/SMS/Email) are not implemented. The web frontend navbar bell icon lacks an attached JavaScript modal.

---

### Subsystem S: Empirical Benchmark & Test Suite Evaluation (October 14, 2026)

#### 1. Automated Test Suite Expansion
- Automated Pytests expanded from **15 tests (October 13)** to **39 tests (October 14)** across 5 modules.
- **Runtime:** 39 passed in **101.62 seconds** with 0 failures:
  - `tests/test_llm_recovery.py`: 14 passed
  - `tests/test_perception.py`: 5 passed
  - `tests/test_planning.py`: 8 passed
  - `tests/test_routine_persistence.py`: 10 passed
  - `tests/test_safety.py`: 2 passed

#### 2. Routine Loading Latency Benchmark:
- Direct SQLite Lookup (`GET /api/schedule/current`): **3.09 ms**.
- Cached Schedule Generation (`POST /api/schedule/generate`): **3.33 ms**.
- Previous Baseline Latency: **87,700 ms**.
- **Measured Acceleration:** **26,300x faster**.


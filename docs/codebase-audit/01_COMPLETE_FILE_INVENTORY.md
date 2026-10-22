# AI DINCHARYA: COMPLETE CODEBASE FORENSIC AUDIT
## Document 01: Exhaustive File and Directory Inventory

**Audit Date:** October 13, 2026  
**Auditor:** Forensic Engineering Audit Agent (DeepMind Antigravity)  
**Repository Path:** `/Users/Siddharth/Documents/AiDincharya`  
**Current Git Branch:** `Siddharth` (HEAD commit: `9311925 Adding test flows`)  
**Repository State:** Clean working tree, no uncommitted changes.  

---

### 1. Inventory Methodology & Classification Standards

Every file in the repository was inspected directly. Exclusions from deep text parsing (such as binary PDFs, PNG assets, and compiled SQLite bytecode) were processed using metadata inspection, schema dumps, or targeted PDF text extraction using `pypdf`.

Each artifact has been cataloged with:
- **Relative Path:** Location within the repository.
- **Type / Format:** Language or file format.
- **Size / Lines:** Physical footprint and approximate volume.
- **Category:** Source, Configuration, Documentation, Asset, Test, Generated Artifact, Database, or Script.
- **Purpose & Principal Symbols:** Core responsibility and exported functions/classes.
- **Usage Status:** Actively Referenced, Indirectly Referenced, Apparently Unused, or Historical.
- **Dependencies & Consumers:** Internal and external connections.
- **Completeness & Status:** `VERIFIED_WORKING`, `PARTIALLY_WORKING`, `IMPLEMENTED_UNVERIFIED`, `SCAFFOLDED`, `BROKEN`, `NOT_IMPLEMENTED`, `BLOCKED`, `NOT_ASSESSED`.
- **Preliminary Restart Disposition:** `RETAIN`, `REPAIR`, `REDESIGN`, `REPLACE`, `INVESTIGATE`, `REMOVE_CANDIDATE`.

---

### 2. Root Directory Files

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `main.py` | Python 3.11 | 542 lines (22 KB) | Backend Source | FastAPI web server application, API routing, authentication middleware, static file mounting, SPA page serving, daily routine recalibration logic, and chat endpoint orchestration. Key symbols: `app`, `get_current_user`, `read_root`, `generate_schedule`, `log_adherence`, `chat_assistant`, `confirm_schedule`, `find_unused_port`. | Actively Referenced (Server Entry Point) | Imports `src.database.db`, `src.models`, `src.perception.dosha_mapper`, `src.behavior.tracker`, `src.planning.agent`, `src.safety.guardrails`, `src.knowledge.retriever`, `src.config`. Consumed by Uvicorn. | `PARTIALLY_WORKING` (Routes work; `/api/chat` crashes with 500 when `last_schedule` is None or when LLM returns 410) | `REDESIGN` (Monolithic route handler coupling HTTP with business logic, direct SQLite access, and unhandled LLM exceptions) |
| `requirements.txt` | Pip Manifest | 14 lines (247 B) | Configuration | Declares Python runtime dependencies: `fastapi`, `uvicorn`, `pydantic`, `langgraph`, `openai`, `python-dotenv`, `pytest`, `httpx`, `pypdf`, `chromadb`, `sentence-transformers`, `langchain-text-splitters`, `google-generativeai`. | Actively Referenced | Consumed by pip / `.venv`. Missing locked versions. | `VERIFIED_WORKING` | `REPAIR` (Add strict version pinning, split into dev/prod/test requirements) |
| `.env` | Env Config | 4 lines (484 B) | Configuration (Sensitive) | Contains environment secrets: `PUTER_API_KEY`, `NVIDIA_API_KEY`, `LLM_PROVIDER`. Values redacted per security protocols. | Actively Referenced | Consumed by `python-dotenv` in `src.config`. | `VERIFIED_WORKING` | `REPAIR` (Template into `.env.example`, remove hardcoded API keys from shared systems) |
| `.gitignore` | Git Config | 13 lines (122 B) | Configuration | Ignores `.DS_Store`, `.env`, `.venv/`, `.pytest_cache/`, `__pycache__/`, `*.py[cod]`, `browser_debug.log`, `dinacharya.db`, `src/knowledge/data/chroma/`. | Actively Referenced | Consumed by Git. | `VERIFIED_WORKING` | `RETAIN` |
| `dinacharya.db` | SQLite 3 | ~237 KB | Database File | Local embedded SQLite database holding user accounts, active sessions, `user_state`, `chat_history`, and task `completions`. Contains 25 users, 58 sessions, 25 user_state records, 187 chat messages, 26 completions. | Actively Referenced | Read/written by `src.database.db`. | `VERIFIED_WORKING` | `REDESIGN` (Move to PostgreSQL / modern ORM with proper migrations) |
| `benchmark_latency.py` | Python Script | 220 lines (9.5 KB) | Evaluation Script | Standalone pipeline latency benchmark testing DoshaMapper, ChromaDB RAG, ClinicalRuleEngine, AdherenceTracker, and benchmarking NVIDIA NIM models (`meta/llama-3.1-8b-instruct`, `meta/llama-3.1-70b-instruct`). | Independent Script | Imports `src.perception`, `src.models`, `src.knowledge`, `src.safety`, `src.behavior`, `openai`. | `PARTIALLY_WORKING` (Local stages work; NVIDIA 70b call returns 410 EOL) | `RETAIN` (Valuable evaluation artifact, needs model name update) |
| `extract.py` | Python Script | 27 lines (1.2 KB) | Utility Script (Scratch) | One-off extraction script reading an IDE conversation transcript JSONL file from `/Users/Siddharth/.gemini/antigravity/brain/...` to extract HTML markup into `src/static/index.html` and `src/static/architecture.html`. | Obsolete / Historical | No consumers; points to a machine-specific absolute path. | `SCAFFOLDED` | `REMOVE_CANDIDATE` |
| `test_flows.py` | Python Script | 47 lines (2.2 KB) | Integration Test | End-to-end integration test script executing registration, onboarding questionnaire submission, fever schedule generation, chat recalibration override, and adherence logging against `http://localhost:8000`. | Actively Referenced | Consumed by manual verification runs. | `VERIFIED_WORKING` | `RETAIN` (Convert into standard Pytest integration test) |
| `test_flows2.py` | Python Script | 30 lines (1.5 KB) | Integration Test | Secondary flow test verifying chat recalibration requesting contraindicated Abhyanga. | Actively Referenced | Consumed by manual verification runs. | `PARTIALLY_WORKING` (Silently prints `None` on chat failure because HTTP status code is unchecked) | `REPAIR` (Add response status validation assertions) |
| `test_rag_and_agent.py` | Python Script | 63 lines (1.9 KB) | Diagnostic Script | Tests `AyurvedaKnowledgeBase` retrieval and `DinacharyaPlannerAgent` generation directly in Python. | Actively Referenced | Consumed by manual diagnostic execution. | `BROKEN` (Crashes on line 57 with `'dict' object has no attribute 'morning_block'` because `agent.generate` returns `{"schedule": ...}`) | `REPAIR` (Fix dictionary key access, update deprecated LLM model) |
| `test_output.log` | Text Log | 72 lines (33 KB) | Test Artifact | Historical pytest log capturing a test run where `tests/test_planning.py::test_planning_agent_generate` failed with an AssertionError. | Unreferenced / Generated | Produced by pytest output redirection. | `NOT_ASSESSED` (Log file) | `REMOVE_CANDIDATE` |
| `browser_debug.log` | Text Log | 2,549 lines (157 KB) | Observability Log | Runtime client-side log file generated by browser interactions through `app.js` remote logging calls. | Generated Artifact | Written by `remote_log` handler (when mounted). | `VERIFIED_WORKING` | `REMOVE_CANDIDATE` (Transient log) |

---

### 3. Application Source Directory (`src/`)

#### 3.1 Core Architecture & Configuration

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `src/__init__.py` | Python | 1 line (25 B) | Package Init | Defines `src` as a Python namespace package. | Actively Referenced | Python interpreter. | `VERIFIED_WORKING` | `RETAIN` |
| `src/config.py` | Python | 26 lines (892 B) | Configuration | Application configuration declaring `PUTER_BASE_URL`, `PUTER_API_KEY`, `NVIDIA_BASE_URL`, `NVIDIA_API_KEY`, `LLM_PROVIDER`, `DEFAULT_MODEL` (`meta/llama-3.1-70b-instruct`), `APP_NAME`, `DEBUG`. | Actively Referenced | Imports `os`, `dotenv.load_dotenv`. Consumed by `src.planning.agent`, `main.py`, `benchmark_latency.py`. | `PARTIALLY_WORKING` (`DEFAULT_MODEL` is deprecated on NVIDIA NIM as of 2026-08-26) | `REDESIGN` (Introduce Pydantic `BaseSettings`, strict validation, multi-provider failover) |
| `src/models.py` | Python | 105 lines (4.7 KB) | Data Contracts | Pydantic v2 domain schemas and API transfer models: `DoshaVector` (with auto-normalization validator), `VikritiFlags`, `DoshaProfile`, `UserContext`, `Practice`, `DinacharyaSchedule`, `UserAuthRequest`, `AuthResponse`, `QuestionnaireRequest`, `ScheduleGenerateRequest`, `AdherenceLogRequest`, `ChatRequest`. | Actively Referenced | Imports `pydantic`. Consumed by all modules and API endpoints. | `VERIFIED_WORKING` | `RETAIN` (Solid foundation, expand for multi-day schedules and audit metadata) |

#### 3.2 Perception Domain (`src/perception/`)

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `src/perception/__init__.py` | Python | 1 line (21 B) | Package Init | Namespace init for perception domain. | Actively Referenced | Python interpreter. | `VERIFIED_WORKING` | `RETAIN` |
| `src/perception/dosha_mapper.py` | Python | 114 lines (4.4 KB) | Domain Logic | Phenotype scoring and imbalance detection. Contains `DoshaMapper` with `classify_prakriti` (keyword-based string matching on questionnaire text), `detect_vikriti` (rule-based heuristic thresholds on `hrv_ms`, `resting_hr`, `sleep_hours`, `body_temp_c`), and `generate_profile`. | Actively Referenced | Imports `time`, `src.models`. Consumed by `main.py`, `tests/test_perception.py`, `benchmark_latency.py`. | `PARTIALLY_WORKING` (Functions as coded; however, uses primitive keyword counting rather than ML classification or Isolation Forest anomaly detection as claimed in capstone documentation) | `REDESIGN` (Replace keyword matching with validated Prakriti classifier and statistical anomaly detection) |

#### 3.3 Knowledge & RAG Retrieval Domain (`src/knowledge/`)

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `src/knowledge/__init__.py` | Python | 1 line (30 B) | Package Init | Namespace init for knowledge domain. | Actively Referenced | Python interpreter. | `VERIFIED_WORKING` | `RETAIN` |
| `src/knowledge/retriever.py` | Python | 108 lines (4.2 KB) | Domain Logic | Authentic RAG retrieval engine. Implements `AyurvedaKnowledgeBase`: initializes persistent ChromaDB client at `src/knowledge/data/chroma`, collection `grounding_rag_final`, embeds with SentenceTransformers `all-MiniLM-L6-v2`, ingests `Core_Dinacharya_Grounding.pdf` (1000-char chunks, 200-char overlap), and performs semantic search based on formatted Dosha/season queries. | Actively Referenced | Imports `pypdf`, `langchain_text_splitters`, `chromadb`, `sentence_transformers`, `src.models`. Consumed by `src.planning.agent`, `main.py`, `test_rag_and_agent.py`, `benchmark_latency.py`. | `VERIFIED_WORKING` (ChromaDB collection contains 140 indexed chunks; query returns authentic classical Ayurvedic guidelines) | `REDESIGN` (Add metadata filtering, multi-query expansion, hybrid dense/sparse retrieval, and chunk source tracking) |
| `src/knowledge/data/Core_Dinacharya_Grounding.pdf` | Binary PDF | 20.9 MB | Knowledge Corpus | Classical grounding text derived from Ayurvedic canonical literature (Ashtanga Hridayam, Charaka Samhita Dinacharya chapters). Primary source document for vector database indexing. | Actively Referenced | Ingested by `AyurvedaKnowledgeBase._ingest_pdf`. | `VERIFIED_WORKING` | `RETAIN` (Verify textual provenance, OCR quality, and chapter segmentation) |
| `src/knowledge/data/chroma/chroma.sqlite3` | SQLite Database | 3.5 MB | Vector Metadata | Persistent ChromaDB metadata database tracking collections, embeddings, segments, and document IDs. | Actively Referenced | Managed by `chromadb.PersistentClient`. | `VERIFIED_WORKING` | `RETAIN` |
| `src/knowledge/data/chroma/9aacf7ca.../` | Binary HNSW Index | 165 KB total | Vector Store Index | ChromaDB HNSW binary index files (`data_level0.bin`, `header.bin`, `length.bin`, `link_lists.bin`) storing vector graph index for 140 chunks. | Actively Referenced | Managed by ChromaDB. | `VERIFIED_WORKING` | `RETAIN` |

#### 3.4 Planning & Agent Orchestration Domain (`src/planning/`)

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `src/planning/__init__.py` | Python | 1 line (25 B) | Package Init | Namespace init for planning domain. | Actively Referenced | Python interpreter. | `VERIFIED_WORKING` | `RETAIN` |
| `src/planning/agent.py` | Python | 299 lines (16.2 KB) | Agent Orchestration | `DinacharyaPlannerAgent` orchestrates routine planning using a 3-node LangGraph `StateGraph` (`retrieve` -> `plan` -> `execute` -> `END`). Invokes OpenAI-compatible LLM endpoint (NVIDIA NIM) with strict JSON schema instructions, parses routine blocks (`morning_block`, `midday_block`, `evening_block`), and features a deterministic rule-based fallback planner `_fallback_planner` if LLM calls fail. | Actively Referenced | Imports `langgraph`, `openai`, `src.config`, `src.models`, `src.knowledge.retriever`, `src.planning.tools`. Consumed by `main.py`, `tests/test_planning.py`, `test_rag_and_agent.py`. | `PARTIALLY_WORKING` (LangGraph compilation and fallback planner verified working; live LLM planning is failing with HTTP 410 on default 70b model) | `REDESIGN` (Decouple prompt assembly from graph nodes, replace hardcoded time adjustments, implement true multi-turn tool calling) |
| `src/planning/tools.py` | Python | 58 lines (2.3 KB) | Tool Definitions | Tool helper functions: `get_weather_context` (simulated stub returning Bangalore/Delhi/Balanced weather dicts), `check_calendar_conflicts` (heuristic string-matching checker for "meeting"/"call"/"class" overlapping 08:00/09:00 slots), and `query_ayurvedic_knowledge` (wrapper calling `AyurvedaKnowledgeBase.retrieve`). | Actively Referenced | Consumed by `src.planning.agent`. | `SCAFFOLDED` (Weather is mock; calendar conflict is rigid substring stub) | `REPLACE` (Integrate genuine calendar parsing via iCal/Google Calendar and live Open-Meteo API) |

#### 3.5 Safety & Clinical Guardrail Domain (`src/safety/`)

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `src/safety/__init__.py` | Python | 1 line (24 B) | Package Init | Namespace init for safety domain. | Actively Referenced | Python interpreter. | `VERIFIED_WORKING` | `RETAIN` |
| `src/safety/guardrails.py` | Python | 101 lines (5.0 KB) | Clinical Safety | `ClinicalRuleEngine` acts as an unbypassable deterministic post-generation safety filter. Validates candidate schedules against user `DoshaProfile.vikriti_flags`. Implements acute fever (*Nava Jwara*) rule: strips contraindicated oil practices (`abhyanga`, `nasya`) and replaces them with safe alternatives (*Nava Jwara Rest & Hydration*, *Midu Langhana*, *Early Deep Rest*). | Actively Referenced | Imports `src.models`. Consumed by `main.py`, `tests/test_safety.py`, `benchmark_latency.py`. | `VERIFIED_WORKING` (Verified by unit and integration tests; but only contains 1 contraindication rule) | `REDESIGN` (Expand to full classical contraindication registry covering Ama, pregnancy, acute digestion, hypertension) |

#### 3.6 Behavior & Adherence Domain (`src/behavior/`)

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `src/behavior/__init__.py` | Python | 1 line (26 B) | Package Init | Namespace init for behavior domain. | Actively Referenced | Python interpreter. | `VERIFIED_WORKING` | `RETAIN` |
| `src/behavior/tracker.py` | Python | 64 lines (2.7 KB) | Behavioral Engine | `AdherenceTracker` calculates adherence score $S_{adj} = \text{completed} / \text{recommended}$ (clamped to $[0.0, 1.0]$), determines schedule complexity based on adherence thresholds ($<0.50 \to$ "Anchor Habits", $\ge 0.80 \to$ "Advanced", else "Moderate"), and generates EAST behavioral nudges. Contains empty stub `class BehaviorEngine: pass`. | Actively Referenced | Imports `logging`, `typing`. Consumed by `main.py`, `tests/test_planning.py`, `benchmark_latency.py`. | `VERIFIED_WORKING` (Mathematical and complexity classification verified; notifications/nudges are static strings without push delivery) | `REDESIGN` (Implement multi-day rolling exponential smoothing, habit decay models, and active notification scheduling) |

#### 3.7 Database Access Domain (`src/database/`)

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `src/database/db.py` | Python | 233 lines (7.8 KB) | Persistence Layer | Raw SQLite helper module. Initializes database schema (`users`, `sessions`, `user_state`, `chat_history`, `completions`), manages SHA-256 password hashing (without salts), token creation (`secrets.token_urlsafe`), user state JSON serialization/deserialization, schedule caching, and completion tracking. | Actively Referenced | Imports `sqlite3`, `secrets`, `json`. Consumed by `main.py`. Auto-executes `init_db()` on module import. | `PARTIALLY_WORKING` (Works for core flows, but exhibits unsafe SQL practices, unhashed token storage, unsalted SHA-256 passwords, and fragile `last_schedule` null-handling) | `REPLACE` (Replace with SQLAlchemy / SQLModel, Alembic migrations, bcrypt/Argon2 password hashing, and connection pooling) |

#### 3.8 Frontend & Static Assets (`src/static/`)

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `src/static/app.js` | JavaScript | 397 lines (22.2 KB) | Frontend Logic | Core client-side JavaScript. Handles token authentication, session caching, schedule fetching (`getSchedule`), dynamic task completion logging, chat messaging with typing animation, recalibration flowchart UI with interactive confirmation modal, and page initialization. | Actively Referenced | Included by `dashboard.html`, `routine.html`, `reasoning.html`, `login.html`, `register.html`. Calls `/api/*` endpoints. | `VERIFIED_WORKING` (Interactive UI components, schedule toggling, and recalibration flows verified) | `REDESIGN` (Migrate to typed React / Vite frontend as planned by team on branch `Kirr`/`shreyansh`) |
| `src/static/index.html` | HTML5 / Tailwind | 211 lines (13.9 KB) | Landing Page | Public marketing/landing page with feature overviews, Ayurvedic pillars, typography, and call-to-action buttons linking to `/login` and `/register`. | Actively Referenced | Served at `/` by FastAPI. | `VERIFIED_WORKING` | `RETAIN` (Modern aesthetic, re-integrate into clean frontend) |
| `src/static/login.html` | HTML5 / Tailwind | 268 lines (15.1 KB) | Auth Screen | User login screen with form inputs for username and password, linking to `app.js` login handler. | Actively Referenced | Served at `/login` by FastAPI. | `VERIFIED_WORKING` | `RETAIN` (Integrate into unified client application) |
| `src/static/register.html` | HTML5 / Tailwind | 206 lines (11.8 KB) | Auth Screen | User registration screen with username and password inputs, terms checkbox, linking to `app.js` register handler. | Actively Referenced | Served at `/register` by FastAPI. | `VERIFIED_WORKING` | `RETAIN` |
| `src/static/onboarding.html` | HTML5 / Tailwind | 149 lines (8.3 KB) | Onboarding Screen | 3-question Prakriti questionnaire screen (digestion, sleep, stress) submitting to `/api/user/questionnaire`. Note: references `localStorage` cache key whereas `app.js` uses `sessionStorage`. | Actively Referenced | Served at `/onboarding` by FastAPI. | `PARTIALLY_WORKING` (Functional, but questionnaire is reduced to 3 items rather than 24-item validated tool) | `REDESIGN` (Implement comprehensive validated Prakriti assessment tool) |
| `src/static/dashboard.html` | HTML5 / Tailwind | 366 lines (21.7 KB) | SPA Dashboard | User dashboard showing today's active tasks, habit adherence score, current Dosha status, behavioral nudge banner, and quick navigation. | Actively Referenced | Served at `/dashboard` by FastAPI. Dynamically populated by `app.js`. | `VERIFIED_WORKING` | `RETAIN` |
| `src/static/routine.html` | HTML5 / Tailwind | 448 lines (22.2 KB) | Routine Screen | Complete 24-hour Dinacharya interactive timeline view broken into Morning, Midday, and Evening blocks. Supports task expansion and direct completion logging. | Actively Referenced | Served at `/routine` by FastAPI. Dynamically populated by `app.js`. | `VERIFIED_WORKING` | `RETAIN` |
| `src/static/reasoning.html` | HTML5 / Tailwind | 298 lines (15.7 KB) | Reasoning Screen | Interactive conversational reasoning screen ("Vaidya AI") allowing users to ask about routine logic, request schedule recalibrations, and view interactive flowcharts. | Actively Referenced | Served at `/reasoning` by FastAPI. Dynamically populated by `app.js`. | `PARTIALLY_WORKING` (UI renders and chat history loads; sending messages triggers 500 when backend LLM fails) | `REPAIR` (Fix backend chat handler and model endpoint) |
| `src/static/architecture.html` | HTML5 / Tailwind | 440 lines (21.8 KB) | System Visualization | Interactive visual diagram showing system architecture nodes and connections. | Static Asset Only | Unmounted in `main.py` routing (only accessible via `/static/architecture.html`). | `IMPLEMENTED_UNVERIFIED` | `INVESTIGATE` (Determine if intended as customer-facing or internal research documentation) |

---

### 4. Test Suite Directory (`tests/`)

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `tests/__init__.py` | Python | 1 line (25 B) | Package Init | Test package init file. | Actively Referenced | Pytest discovery. | `VERIFIED_WORKING` | `RETAIN` |
| `tests/test_perception.py` | Python (Pytest) | 64 lines (2.2 KB) | Unit Test | 5 test cases testing `DoshaMapper`: default classification fallback, keyword-driven vector scoring, Vata aggravation detection, Pitta aggravation detection, and fever detection. | Actively Referenced | Consumed by `pytest`. | `VERIFIED_WORKING` (5/5 passed in 0.02s) | `RETAIN` |
| `tests/test_safety.py` | Python (Pytest) | 86 lines (2.9 KB) | Unit Test | 2 test cases testing `ClinicalRuleEngine`: verification that acute fever overrides Abhyanga and injects *Nava Jwara Rest*, and verification that schedules without fever remain intact. | Actively Referenced | Consumed by `pytest`. | `VERIFIED_WORKING` (2/2 passed in 0.01s) | `RETAIN` |
| `tests/test_planning.py` | Python (Pytest) | 184 lines (7.0 KB) | Integration Test | 8 test cases testing calendar conflict checking, `DinacharyaPlannerAgent` LangGraph execution, root endpoint rendering, end-to-end `/api/schedule/generate` flow, closed-loop `/api/adherence/log` adaptation, NVIDIA client initialization, deterministic fallback planner, and chat safety recalibration. | Actively Referenced | Consumed by `pytest`. Uses FastAPI `TestClient`. | `VERIFIED_WORKING` (8/8 passed in 42.7s) | `RETAIN` (Decouple live LLM dependency in unit suite with VCR/mocking) |

---

### 5. Research, Presentations & Capstone Documentation (`Dincharya copy/`)

| Relative Path | Type / Format | Size | Category | Purpose & Content Summary | Usage Status | Dependencies & Consumers | Status | Preliminary Disposition |
|---|---|---|---|---|---|---|---|---|
| `Dincharya copy/Dinacharya_Full_Report.pdf` | Binary PDF | 833 KB (39 pages) | Capstone Report | Comprehensive Academic Capstone Project Report detailing Introduction, Problem Statement, Survey, SRS, System Design, Architecture, Use Cases, Scenarios, and Applications. | Reference Document | Primary conceptual specification for AI Dincharya system. | `NOT_ASSESSED` (Document) | `RETAIN` (Foundational requirements specification) |
| `Dincharya copy/Dinacharya Synopsis.pdf` | Binary PDF | 233 KB (8 pages) | Project Synopsis | Formal academic project synopsis summarizing motivation, objectives, modular pipeline, and planned experimental methodology. | Reference Document | Project summary. | `NOT_ASSESSED` (Document) | `RETAIN` |
| `Dincharya copy/Dinacharya Capstone.pdf` | Binary PDF | 542 KB | Project Document | Alternate compilation of the capstone documentation. | Reference Document | Redundant with Full Report. | `NOT_ASSESSED` (Document) | `INVESTIGATE` |
| `Dincharya copy/Dinacharya Lit Review.pdf` | Binary PDF (ReportLab) | 8.7 KB | Literature Review | Summary of research survey on Prakriti computational modeling, RAG architectures in Ayurveda, and wearable circadian tracking. | Reference Document | Survey background. | `NOT_ASSESSED` (Document) | `RETAIN` |
| `Dincharya copy/Review1.pptx` | Microsoft PowerPoint | 1.1 MB | Presentation Slides | Academic slide deck for project review milestone 1. | Presentation Asset | Review presentation. | `NOT_ASSESSED` (Slide deck) | `RETAIN` |
| `Dincharya copy/Review I_PPT_Format.pdf` | Binary PDF | 264 KB | Presentation Guidelines | Institutional guidelines for Review 1 presentation structure. | External Template | Academic template. | `NOT_ASSESSED` (Template) | `REMOVE_CANDIDATE` |
| `Dincharya copy/Report_Chapters_Template.pdf` | Binary PDF | 102 KB | Academic Template | Institutional formatting template for capstone chapters. | External Template | Academic template. | `NOT_ASSESSED` (Template) | `REMOVE_CANDIDATE` |
| `Dincharya copy/Sample_ACK_and_Abstract_Template.doc` | Binary DOC | 28 KB | Academic Template | Template for acknowledgment and abstract pages. | External Template | Academic template. | `NOT_ASSESSED` (Template) | `REMOVE_CANDIDATE` |
| `Dincharya copy/Sample_TableofContent_Template.doc` | Binary DOC | 54 KB | Academic Template | Template for table of contents. | External Template | Academic template. | `NOT_ASSESSED` (Template) | `REMOVE_CANDIDATE` |
| `Dincharya copy/System Architecture.png` | PNG Image | 276 KB | Architecture Diagram | High-level diagram of the Neuro-Symbolic Hybrid Architecture (Multimodal Ingestion -> Perception -> RAG Retrieval -> Agentic Planning -> Safety Guardrails -> Nudging). | Design Artifact | Referenced in Full Report (Figure 6.1). | `NOT_ASSESSED` (Asset) | `RETAIN` |
| `Dincharya copy/SystemDesignPNG.png` | PNG Image | 1.3 MB | Architecture Diagram | High-resolution master system design schematic. | Design Artifact | System architecture master. | `NOT_ASSESSED` (Asset) | `RETAIN` |
| `Dincharya copy/Dosha Mapping Pipeline.png` | PNG Image | 80 KB | Architecture Diagram | Architectural diagram illustrating Prakriti classification and Vikriti anomaly detection. | Design Artifact | Referenced in Full Report (Figure 6.3). | `NOT_ASSESSED` (Asset) | `RETAIN` |
| `Dincharya copy/Multimodal Ingestion Layer.png` | PNG Image | 95 KB | Architecture Diagram | Architectural diagram of static questionnaire, passive telemetry, and environmental signal ingestion. | Design Artifact | Referenced in Full Report (Figure 6.2). | `NOT_ASSESSED` (Asset) | `RETAIN` |
| `Dincharya copy/Rag Knowledge Retrieval.png` | PNG Image | 46 KB | Architecture Diagram | Architectural diagram of PDF chunking, embedding, ChromaDB vector store, and semantic query matching. | Design Artifact | Referenced in Full Report (Figure 6.4). | `NOT_ASSESSED` (Asset) | `RETAIN` |
| `Dincharya copy/Agentic Planning.png` | PNG Image | 71 KB | Architecture Diagram | Architectural diagram of LangGraph plan-and-execute loop, LLM routine construction, and calendar adaptation. | Design Artifact | Referenced in Full Report (Figure 6.5). | `NOT_ASSESSED` (Asset) | `RETAIN` |
| `Dincharya copy/Safety Guardrail Engine.png` | PNG Image | 57 KB | Architecture Diagram | Architectural diagram of the deterministic clinical rule engine and contraindication overrides. | Design Artifact | Referenced in Full Report (Figure 6.6). | `NOT_ASSESSED` (Asset) | `RETAIN` |
| `Dincharya copy/Closed Loop Behavioural Adaptation.png` | PNG Image | 99 KB | Architecture Diagram | Architectural diagram of daily adherence tracking, complexity state transitions, and habit scaffolding. | Design Artifact | Referenced in Full Report (Figure 6.7). | `NOT_ASSESSED` (Asset) | `RETAIN` |
| `Dincharya copy/Adherence&Nudging System.png` | PNG Image | 46 KB | Architecture Diagram | Architectural diagram of adherence score calculation ($S_{adj}$) and EAST-aligned push nudges. | Design Artifact | Referenced in Full Report (Figure 6.8). | `NOT_ASSESSED` (Asset) | `RETAIN` |

---

### 6. Baseline Inventory Summary Statistics (October 13, 2026)

- **Total Inspected Files:** 53 repository files (excluding `.git/` and `.venv/`).
- **Python Source Files:** 15 files (`main.py`, `benchmark_latency.py`, `extract.py`, `test_flows.py`, `test_flows2.py`, `test_rag_and_agent.py`, 6 files in `src/`, 3 files in `tests/`).
- **HTML/JS Client Assets:** 9 files in `src/static/`.
- **Database Artifacts:** 1 SQLite database (`dinacharya.db`) + 1 ChromaDB store (`chroma.sqlite3` with 4 HNSW index files).
- **Documentation & Research Assets:** 18 files in `Dincharya copy/` (9 diagrams, 5 PDFs, 1 PPTX, 3 DOC templates).
- **Log Files:** 2 log files (`browser_debug.log`, `test_output.log`).
- **Total Code Volume:** ~2,100 lines of Python, ~2,700 lines of HTML/JS, ~4,700 total lines of code.

---

### 7. Post-Implementation Reassessment: File Inventory & Volumetric Delta (October 14, 2026)

Following targeted repair of the LLM subsystem, routine loading latency, schedule persistence, and notification outbox, the codebase expanded by **1,260 insertions** across modified files and added **5 new Python modules, test suites, and documentation registers**.

#### 7.1 Newly Created Modules & Scripts

| Relative Path | Type / Format | Lines / Size | Category | Purpose & Key Contents | Usage Status | Dependencies & Consumers | Status | Preliminary Restart Disposition |
|---|---|---|---|---|---|---|---|---|
| `src/llm_gateway.py` | Python 3.11 | 293 lines (10.4 KB) | Core Infrastructure | Centralized resilience gateway for LLM operations. Implements `LLMGateway` class with automatic fallback from Nemotron 30B to GPT-OSS-20B, regex boundary & markdown fence JSON recovery (`extract_clean_json`), reasoning token budgeting (`max_tokens=4096`), native multi-step tool loops (`execute_tool_loop`), and deterministic fallback responses. | Actively Referenced | Imports `openai`, `src.config`. Consumed by `main.py` (`/api/insights`, `/api/chat`), `src.planning.agent`, and `tests/test_llm_recovery.py`. | `VERIFIED_WORKING` | `RETAIN` (Core architectural component for v2) |
| `scripts/benchmark_models.py` | Python Script | 310 lines (11.2 KB) | Evaluation & Testing | Standardized benchmark framework evaluating candidate models (`nvidia/nemotron-3.5-lightning-30b-a3b`, `nvidia/nemotron-nano-9b-v2`, `openai/gpt-oss-20b`) under identical conditions across Tests A through G (availability, structured JSON, tool calling, adaptation, safety). | Diagnostic Tool | Imports `openai`, `src.config`, `src.planning.tools`. | `VERIFIED_WORKING` | `RETAIN` (Model selection regression harness) |
| `tests/test_llm_recovery.py` | Python Pytest | 385 lines (14.5 KB) | Automated Test Suite | Comprehensive unit and integration test suite containing 14 tests: null schedule handling, insights resilience, gateway JSON stripping, fallback triggers, tool dispatching, notification idempotency, and 6 circumstance adaptation scenarios. | Actively Referenced | Consumed by Pytest. | `VERIFIED_WORKING` (14/14 tests pass) | `RETAIN` (Crucial regression test suite) |
| `tests/test_routine_persistence.py` | Python Pytest | 280 lines (10.2 KB) | Automated Test Suite | Persistence and concurrency test suite containing 10 rigorous regression tests verifying: routine loads without regeneration (<15ms), missing routine generation, Trataka adaptation persistence, refresh survival, DB write error handling, timeout recovery, duplicate prevention, and unrelated activity preservation. | Actively Referenced | Consumed by Pytest. | `VERIFIED_WORKING` (10/10 tests pass) | `RETAIN` (Crucial regression test suite) |
| `docs/LLM_INVENTORY_AND_REPAIR_PLAN.md` | Markdown | 115 lines (8.5 KB) | Technical Document | Phase 1 forensic inventory of LLM call sites, defect analysis, and repair plan. | Reference Document | Project documentation. | `VERIFIED_WORKING` | `RETAIN` |
| `docs/MODEL_SELECTION_REPORT.md` | Markdown | 153 lines (8.8 KB) | Technical Document | Phase 2 candidate model benchmark report with empirical scorecard and selection rationale. | Reference Document | Project documentation. | `VERIFIED_WORKING` | `RETAIN` |
| `docs/codebase-audit/11_PROGRESS_DELTA.md` | Markdown | 200 lines (12.5 KB) | Audit Deliverable | Document 11 Progress Delta comparing baseline audit with current reassessment. | Reference Document | Codebase audit deliverable. | `VERIFIED_WORKING` | `RETAIN` |

#### 7.2 Modified Files Analysis

| Relative Path | Lines Changed | Structural Impact & Key Modifications | Status | Preliminary Restart Disposition |
|---|---|---|---|---|
| `main.py` | 821 lines (+279 net) | Monolith expanded from 542 to 821 lines. **Key additions:**<br/>1. Added `GET /api/schedule/current` for instant direct SQLite lookup (3.09ms).<br/>2. Eliminated `current_hour >= end_hour` auto-recalibration loop in `POST /api/schedule/generate` (serving cached daily schedule in 3.33ms).<br/>3. Replaced fragile `last_schedule` chaining with safe dictionary access in `POST /api/chat`.<br/>4. Added natural-language confirmation parser ("yes", "confirm", "sounds good") writing adapted schedules canonically to SQLite `user_state`.<br/>5. Added notification REST endpoints: `GET /api/notifications` and `POST /api/notifications/{id}/read`.<br/>6. Wrapped auxiliary endpoints with `LLMGateway` and deterministic fallback templates. | `VERIFIED_WORKING` (Critical bugs resolved, but monolithic coupling remains) | `REDESIGN` (Split into modular routers in clean v2 restart) |
| `src/config.py` | 30 lines (+4 net) | Updated `DEFAULT_MODEL` from decommissioned `meta/llama-3.1-70b-instruct` to `nvidia/nemotron-3.5-lightning-30b-a3b`. Added `FALLBACK_MODEL = "openai/gpt-oss-20b"`. Added `MAX_TOKENS = 4096` to allocate sufficient budget for Nemotron's 1,500–2,600 reasoning tokens. | `VERIFIED_WORKING` | `REPLACE` (Replace with Pydantic `BaseSettings`) |
| `src/database/db.py` | 215 lines (+107 net) | Added `notifications` table schema (`id`, `user_id`, `type`, `title`, `message`, `data`, `is_read`, `created_at`). Implemented helper functions: `create_notification`, `get_notifications_for_user`, `mark_notification_read`. Added idempotency deduplication hashing. | `VERIFIED_WORKING` | `REPLACE` (Migrate to SQLAlchemy 2.0 / PostgreSQL with Alembic) |
| `src/models.py` | 115 lines (+10 net) | Added Pydantic schemas for notification requests and responses: `NotificationItem`, `NotificationListResponse`. | `VERIFIED_WORKING` | `RETAIN` (Expand for v2) |
| `src/planning/agent.py` | 610 lines (+482 net) | Extended `AgentState` with `user_instruction`, `current_schedule`, and `circumstance_type`. Implemented intelligent circumstance adaptation across 6 scenarios (client meetings, travel, fever, late wake-up, overruns, infeasible constraints). Added conflict resolution shifting flexible practices (Trataka, Abhyanga) to open post-commitment windows while preserving fixed routines. | `VERIFIED_WORKING` | `REDESIGN` (Refactor into modular multi-agent graph with iterative critique) |
| `src/planning/tools.py` | 385 lines (+322 net) | Defined formal OpenAI function schemas in `AVAILABLE_PLANNER_TOOLS` (`rag_ayurveda_search`, `check_clinical_safety`, `get_current_schedule`, `detect_calendar_conflicts`, `update_schedule_activity`). Implemented `execute_planner_tool` execution dispatcher. Verified via benchmarks and Pytests. | `VERIFIED_WORKING` (Dispatcher works; requires plumbing into live production graph) | `RETAIN` (Plumb into LangGraph nodes) |
| `src/static/app.js` | 465 lines (+52 net) | Optimized routine retrieval path: calls `GET /api/schedule/current` directly before generation, eliminating 87-second wait. Added `sessionStorage` routine cache synchronization. Added error retry card UI handler (`#routine-error-card`). | `VERIFIED_WORKING` | `REPLACE` (Migrate to modern React 18 frontend from branch `Kirr`) |

#### 7.3 Reassessment Volumetric Statistics (October 14, 2026)

- **Total Inspected Files:** 60 repository files (excluding `.git/` and `.venv/`).
- **Python Source Files:** 19 files (+4 new files: `src/llm_gateway.py`, `scripts/benchmark_models.py`, `tests/test_llm_recovery.py`, `tests/test_routine_persistence.py`).
- **Total Code Volume:** ~3,500 lines of Python (+1,400 lines), ~2,750 lines of HTML/JS, **~6,250 total lines of code**.
- **Automated Test Coverage:** 39 passing Pytest tests across 5 test modules (up from 15 tests in 3 modules).


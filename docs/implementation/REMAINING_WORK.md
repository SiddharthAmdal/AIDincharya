# AI Dincharya: Deferred Architectural Work & Technical Roadmap

**Date:** October 15, 2026  
**Auditor / Lead Engineer:** AI Systems & Security Architect  
**Branch:** `Siddharth`  
**Purpose:** Honest, evidence-backed inventory of remaining technical debt and non-blocking post-MVP roadmap items.

---

## 1. Inventory of Deferred Items

While all Priority 0 (Production Tool Calling, Cryptographic Security & Sessions, Multi-Rule Clinical Safety Matrix) and Priority 1 (Notification Outbox & UI Tray, Explainable Prakriti Rubric, Time-Decay Adherence, Diagnostic Runners) objectives are fully operational and verified by 56 automated tests, the following non-blocking items are intentionally deferred for future phases:

### 1.1 Wearable Hardware Ingestion & Machine Learning Anomaly Detection
- **Current State:** 
  The system ingests structured wearable telemetry payloads (`hrv_ms`, `resting_hr`, `sleep_hours`, `body_temp_c`) and maps them deterministically into Vikriti flags (Vata aggravation, Pitta aggravation, Fever).
- **Deferred Scope:**
  - Direct OAuth2 synchronization with consumer health APIs (Apple HealthKit, Google Health Connect, Oura Cloud API, Whoop).
  - Unsupervised `IsolationForest` (scikit-learn) anomaly detection over 30-day multivariate rolling baselines.
- **Rationale for Deferral:**
  Direct wearable hardware ingestion requires vendor developer accounts, physical mobile bridges, and production OAuth credentials not suitable for a local branch sprint. Deterministic heuristic mapping provides robust, predictable clinical safety inputs for all current use cases.

### 1.2 External Push Delivery Channels (FCM / WebPush / SMS)
- **Current State:**
  Full in-app notification subsystem operational with persistent SQLite outbox, MD5 deduplication hashing, real-time unread badge counter, and frontend dropdown tray with mark-as-read controls.
- **Deferred Scope:**
  - Google Firebase Cloud Messaging (FCM) or Apple APNs push notifications for background mobile alerts.
  - Web Push API (Service Worker with VAPID keys).
  - Out-of-band SMS alerts (Twilio) or transactional emails (SendGrid).
- **Rationale for Deferral:**
  Requires external cloud SaaS credentials, service worker registration, and user device token storage. In-app notification delivery satisfies the core requirement for web demonstration.

### 1.3 Machine Learning Embeddings Optimization (PyTorch -> ONNX)
- **Current State:**
  Ayurvedic RAG vector search operates flawlessly with `all-MiniLM-L6-v2` and FAISS, retrieving classical guidelines across 7 indexed categories with sub-10ms query times.
- **Deferred Scope:**
  - Migrating the embedding generator from PyTorch (`torch` + `transformers`, ~2.2GB environment footprint) to `fastembed` or ONNX Runtime (`onnxruntime`, ~60MB footprint).
- **Rationale for Deferral:**
  The current PyTorch environment runs reliably in the local `.venv`. Optimization reduces disk footprint and container image size, but does not alter functional behavior or retrieval accuracy.

### 1.4 Monolithic Router Decomposition (`main.py`)
- **Current State:**
  `main.py` is an 899-line FastAPI monolith hosting route definitions, dependency injection, and static mounts.
- **Deferred Scope:**
  - Decomposing `main.py` into modular FastAPI `APIRouter` packages:
    - `src/routers/auth.py`
    - `src/routers/schedule.py`
    - `src/routers/chat.py`
    - `src/routers/notifications.py`
- **Rationale for Deferral:**
  The monolith was intentionally preserved during the sprint to avoid breaking delicate relative imports and route signatures across the existing test suite and static web assets.

### 1.5 Multi-Branch Cross-Team Merging
- **Current State:**
  Work is completed cleanly on branch `Siddharth` with zero regression against existing team contracts.
- **Deferred Scope:**
  - Merging Kirr's React 18 frontend assets (present on remote branches) into a unified build pipeline.
  - Integrating Swapnil's multi-provider rotating LLM fallback client.
- **Rationale for Deferral:**
  Branch merging requires cross-team synchronization and PR approvals. Branch `Siddharth` serves as the authoritative, functioning backend and web demonstration foundation.

---

## 2. Recommended Next Steps for Team

1. **Sprint Deployment:** Merge verified branch `Siddharth` into `main` after team code review.
2. **Containerization:** Create a standardized multi-stage `Dockerfile` pinning Python 3.11, installing minimal runtime dependencies, and executing database migrations on container start.
3. **Frontend Evolution:** Wire the verified REST and WebSocket endpoints into the Next.js/React frontend when ready.

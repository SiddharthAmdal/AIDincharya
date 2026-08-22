# AiDincharya: Unified Ayurvedic Routine Automation System

> **Consolidated Architecture & Custom LLM Edition**  
> **Date:** August 22, 2026

AiDincharya is an AI-powered personalized Ayurvedic daily routine planning system (*Dinacharya*). It integrates rule-based dosha perception, RAG over classical texts (ChromaDB + SentenceTransformers), agentic planning (LangGraph), clinical safety guardrails, and closed-loop adherence tracking.

---

## 1. Unified Project Structure

The codebase has been consolidated from 5 separate developer directories into a single clean architecture:

```
AIDincharya-Unified/
├── backend/                  # FastAPI Backend API & AI Engine
│   ├── src/
│   │   ├── perception/       # Tri-dosha phenotypic mapping & anomaly detection
│   │   ├── knowledge/        # ChromaDB vector retriever & PDF text extraction
│   │   ├── planning/         # LangGraph multi-stage agentic planner
│   │   ├── safety/           # Clinical rule engine & guardrails
│   │   ├── database/         # SQLite persistence & user authentication
│   │   ├── config.py         # App configuration & Custom LLM settings
│   │   └── llm_client.py     # OpenAI-compatible Custom LLM Provider factory
│   ├── tests/                # Pytest suite
│   ├── main.py               # Main FastAPI entry point
│   ├── dinacharya.db         # SQLite database
│   ├── benchmark_latency.py # Latency & pipeline performance benchmarker
│   ├── test_rag_and_agent.py# Diagnostic test runner
│   └── requirements.txt      # Python dependencies
├── frontend/                 # React + Vite + Tailwind Web Application
│   ├── src/                  # React components, pages, routing & state
│   ├── package.json          # Node.js dependencies & scripts
│   ├── vite.config.ts        # Vite build configuration
│   └── tailwind.config.js    # Tailwind styling configuration
├── mobile_app/               # Flutter Mobile App codebase
└── docs/                     # Comprehensive documentation & diagnostic reports
    ├── COMBINED_DIAGNOSIS_AND_ERRORS.md
    ├── DIAGNOSIS_REPORT.md
    ├── API_DOCUMENTATION.md
    ├── RUNNING_GUIDE.md
    └── TEST_REPORT.md
```

---

## 2. LLM Provider Configuration (Custom LLM Migration)

We have migrated from NVIDIA NIM to our **Custom LLM Provider interface**. Any OpenAI-compatible local or custom server (e.g., vLLM, Ollama, local FastAPI server, or custom fine-tuned endpoint) can be plugged in via environment variables.

### Environment Setup (`backend/.env`):
```env
# Provider Selection (Default: custom_llm)
LLM_PROVIDER=custom_llm

# Custom / Local LLM Parameters
CUSTOM_LLM_BASE_URL=http://localhost:8000/v1
CUSTOM_LLM_API_KEY=custom-llm-key
CUSTOM_LLM_MODEL=custom-ayurveda-llm

# Optional Puter / Alternative Provider Settings
PUTER_BASE_URL=https://api.puter.com/puterai/openai/v1/
PUTER_API_KEY=your_puter_key
```

---

## 3. Running the System

### 3.1 Backend Setup & Startup
```bash
cd backend
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
python main.py
```
The FastAPI backend will start at `http://localhost:8000`. API docs available at `http://localhost:8000/docs`.

### 3.2 Frontend Setup & Startup
```bash
cd frontend
npm install
npm run dev
```
The React web application will start at `http://localhost:5173`.

### 3.3 Running Diagnostic Tests & Verification
```bash
cd backend
pytest tests/
python test_rag_and_agent.py
python benchmark_latency.py
```

---

## 4. Key Fixes Applied During Consolidation

1. **Custom LLM Provider Integration**: Replaced NVIDIA NIM with standard OpenAI-compatible `CUSTOM_LLM_BASE_URL` provider factory (`src/llm_client.py`).
2. **`detect_vikriti` Type Mismatch Fix**: Standardized symptom parameter handling to accept both `List[str]` and `Dict[str, str]`.
3. **RAG Retriever Latency Optimization**: Replaced per-query instantiation of `AyurvedaKnowledgeBase` with a global singleton pattern, reducing RAG query latency from 8s to under 500ms.
4. **PDF Extraction Guard**: Added text checking in `_ingest_pdf()` to avoid `TypeError` on scanned/empty pages.
5. **Standalone Diagnostic Fix**: Corrected dictionary property access in `test_rag_and_agent.py`.
6. **Test Suite Cleanup**: Removed hardcoded NVIDIA domain assertions in `tests/test_planning.py`.

# Ayurvedic Dinacharya Automation API & Web Portal

An intelligent Ayurvedic wellness engine that creates personalized daily routines (*Dinacharya*) based on classical Ayurvedic grounding, Prakriti/Vikriti dosha assessment, wearable telemetry, and real-time environmental context.

---

## 🌟 Key Features

- **Prakriti & Vikriti Perception**: Maps onboarding questionnaire answers and wearable biomarkers (heart rate, HRV, body temperature, sleep duration) into Ayurvedic constitution profiles.
- **Agentic Planning (LangGraph)**: Multi-step Plan-and-Execute agent that generates structured morning, midday, and evening routine blocks.
- **Authentic RAG Grounding (ChromaDB)**: Ingests classical Ayurvedic texts (`Core_Dinacharya_Grounding.pdf`) into a local vector store using `all-MiniLM-L6-v2` embeddings.
- **Clinical Safety Guardrails**: Safety validation engine that identifies medical contraindications (e.g. fever stripping *Abhyanga* or *Nasya*) and prevents harmful recommendations.
- **Behavioral Closed-Loop Tracking**: Tracks user adherence and automatically scales routine complexity (*Anchor Habits* ➔ *Standard* ➔ *Advanced*).
- **Interactive Web Interface**: Complete responsive dashboard including onboarding, daily routine scheduling, LLM reasoning visualizer, and system architecture explorer.

---

## 🏗️ Architecture Overview

```mermaid
flowchart TD
    UI[Web UI / Mobile Client] --> API[FastAPI Application (main.py)]
    API --> Perception[Perception Module: Dosha Mapper]
    API --> Knowledge[RAG Retriever: ChromaDB + SentenceTransformers]
    API --> Planner[Planning Agent: LangGraph Workflow]
    API --> Safety[Safety Engine: Clinical Rule Guardrails]
    API --> Behavior[Behavioral Tracker: Adherence Engine]
    API --> DB[(SQLite: dinacharya.db)]
    Planner --> LLM[LLM Provider: NVIDIA NIM / Gemini / Puter]
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- **Python 3.10+** (Tested on Python 3.11 - 3.13)
- An **NVIDIA NIM API Key** (from [NVIDIA Build](https://build.nvidia.com/))

### 2. Create and Activate Virtual Environment
```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Open `.env` and set your **NVIDIA NIM API Key**:
```env
LLM_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
DEFAULT_MODEL=meta/llama-3.1-70b-instruct
PORT=8000
DEBUG=False
```

### 5. Run the Server
```powershell
python main.py
```
Or with uvicorn:
```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at **[http://localhost:8000](http://localhost:8000)**.

---

## 🧪 Testing

Run automated tests via pytest:
```powershell
pytest -v
```

Run test flow scripts:
```powershell
python test_rag_and_agent.py
python test_flows.py
```

---

## 📁 Project Structure

```
├── main.py                     # FastAPI application entry point & static routes
├── requirements.txt            # Python package dependencies
├── .env.example                # Sample environment configuration template
├── src/
│   ├── config.py               # Global settings & env var loaders
│   ├── llm_client.py           # Multi-provider LLM client (NVIDIA NIM / Gemini / Puter)
│   ├── models.py               # Pydantic schemas & domain models
│   ├── database/
│   │   └── db.py               # SQLite database schemas and session management
│   ├── perception/
│   │   └── dosha_mapper.py     # Dosha scoring & wearable biometric ingestion
│   ├── planning/
│   │   ├── agent.py            # LangGraph multi-node planning workflow
│   │   └── tools.py            # Ayurvedic tools & calendar conflict detection
│   ├── safety/
│   │   └── guardrails.py       # Clinical rule validation & contraindication filters
│   ├── behavior/
│   │   └── tracker.py          # Adherence metrics & habit complexity escalation
│   ├── knowledge/
│   │   ├── retriever.py        # ChromaDB RAG engine with automatic PDF ingestion
│   │   └── data/               # Core Ayurvedic classical text PDF
│   └── static/                 # Frontend HTML, CSS, JavaScript files
└── tests/                      # Pytest suite for perception, planning, and safety
```

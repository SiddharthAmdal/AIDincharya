# AIDincharya Codebase Comprehensive Diagnosis & 5-Folder Audit Report

> **Audit Date:** August 22, 2026  
> **Audited Folders:** `AIDincharya-Kirr`, `AIDincharya-Siddharth`, `AIDincharya-Swapnil`, `AIDincharya-main`, `AIDincharya-main-1`  
> **Target Goal:** Identify all errors, consolidate into a single clean architecture, and migrate from NVIDIA NIM to Custom LLM endpoint.

---

## 1. Executive Summary & Folder Overview

The workspace contained 5 separate project directories representing different stages, branches, and components of the **AiDincharya** system (Ayurvedic routine planning engine):

1. **`AIDincharya-Kirr`**: Standalone **React + Vite + TypeScript** frontend web application.
2. **`AIDincharya-Siddharth`**: Legacy Python backend (Branch A).
3. **`AIDincharya-Swapnil`**: Experimental Python backend with NVIDIA NIM / Gemini configs (Branch B).
4. **`AIDincharya-main-1`**: Redundant copy of Branch B.
5. **`AIDincharya-main`**: Core Python backend (Branch C) with database, mobile app, and test reports.

---

## 2. Complete Error Matrix Across All 5 Folders

| Folder | Category | Location / Subsystem | Severity | Error Description & Impact |
| :--- | :--- | :--- | :--- | :--- |
| **`AIDincharya-Kirr`** | **Architecture** | Root & `src/` | **HIGH** | Web frontend completely detached from backend repository; API base URLs pointing to mock/hardcoded ports; missing unified build/run pipeline. |
| **`AIDincharya-Kirr`** | **Configuration** | `package.json` | **LOW** | Missing unified proxy configuration for FastAPI backend integration during dev. |
| **`AIDincharya-Siddharth`** | **Bug** | `src/perception/dosha_mapper.py` | **CRITICAL** | `detect_vikriti()` expects dictionary (`Dict[str, str]`). Passing `symptoms` as `List[str]` raises `AttributeError: 'list' object has no attribute 'items'`. |
| **`AIDincharya-Siddharth`** | **Code Quality** | `extract.py` | **MEDIUM** | Developer artifact containing hardcoded local user directory paths (`/Users/Siddharth/...`). |
| **`AIDincharya-Siddharth`** | **Dependency** | `src/config.py` | **HIGH** | Tightly coupled to external Puter / NVIDIA APIs without fallback or custom LLM abstraction. |
| **`AIDincharya-Swapnil`** | **Configuration** | `src/config.py` | **HIGH** | Incomplete Gemini/OpenRouter configs that crash when credentials are missing, falling back to hardcoded NVIDIA NIM. |
| **`AIDincharya-Swapnil`** | **Test Defect** | `tests/test_planning.py` | **HIGH** | Hardcoded assertion `assert "api.nvidia.com" in str(planner.openai_client.base_url)`, breaking tests when switching providers. |
| **`AIDincharya-main-1`** | **Redundancy** | Entire Folder | **MEDIUM** | 100% duplicate copy of `AIDincharya-Swapnil` creating codebase clutter and state desynchronization. |
| **`AIDincharya-main`** | **Bug** | `test_rag_and_agent.py` | **HIGH** | Line 57 attempts `for p in schedule.morning_block:`. `agent.generate()` returns a `Dict`, raising `AttributeError: 'dict' object has no attribute 'morning_block'`. |
| **`AIDincharya-main`** | **Bug** | `src/knowledge/retriever.py` | **HIGH** | `_ingest_pdf()` performs string concatenation `text += page.extract_text()`. Scanned/empty PDF pages return `None`, raising `TypeError`. |
| **`AIDincharya-main`** | **Bug** | `src/safety/guardrails.py` | **MEDIUM** | Object reference mutation overwrites `replacement.time_slot` across morning, midday, and evening blocks. |
| **`AIDincharya-main`** | **Performance** | `src/planning/tools.py` | **CRITICAL** | `query_ayurvedic_knowledge()` instantiates `AyurvedaKnowledgeBase()` per call, re-loading SentenceTransformer & ChromaDB disk connection (adds **2s to 8s latency per query**). |
| **`AIDincharya-main`** | **Performance** | `src/planning/agent.py` | **MEDIUM** | `self.build_graph()` compiled on every `generate()` request instead of once during initialization. |
| **`AIDincharya-main`** | **Security** | `main.py` & `src/database/db.py` | **HIGH** | Unsalted SHA-256 password hashing; cleartext session tokens stored in SQLite with no expiration timestamp or revocation logic. |
| **`AIDincharya-main`** | **Security** | `main.py` | **MEDIUM** | Insecure CORS configuration (`allow_origins=["*"]` + `allow_credentials=True`), rejected by modern browsers for authenticated requests. |

---

## 3. Deep-Dive Fix Roadmap

### 3.1 perception (`dosha_mapper.py`)
Fix `detect_vikriti()` to accept both `List[str]` and `Dict[str, str]`:
```python
if isinstance(symptoms, list):
    symptom_list = symptoms
elif isinstance(symptoms, dict):
    symptom_list = list(symptoms.values())
```

### 3.2 Knowledge RAG (`retriever.py` & `tools.py`)
1. Guard against empty PDF page text in `retriever.py`:
```python
extracted = page.extract_text()
if extracted:
    text += extracted
```
2. Singleton pattern for `AyurvedaKnowledgeBase` in `tools.py` to eliminate 2-8s latency per tool call.

### 3.3 Custom LLM Migration
Replace NVIDIA NIM dependencies with **Custom LLM Provider**:
- **Config**: Default `LLM_PROVIDER="custom_llm"`, `CUSTOM_LLM_BASE_URL="http://localhost:8000/v1"`, `CUSTOM_LLM_API_KEY="custom-llm-key"`, `CUSTOM_LLM_MODEL="custom-ayurveda-llm"`.
- **Client**: Standard OpenAI API specification used by custom servers, vLLM, Ollama, or local endpoints.

### 3.4 Repository Consolidation Structure
Consolidating into single unified codebase `AIDincharya-Unified`:
- `backend/`: FastAPI backend with all bug fixes & custom LLM integration.
- `frontend/`: React + Vite + TypeScript web interface.
- `mobile_app/`: Flutter mobile application.
- `docs/`: Comprehensive project documentation.

---
*Report generated for AIDincharya Consolidation Task.*

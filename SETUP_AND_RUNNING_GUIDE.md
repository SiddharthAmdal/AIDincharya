# 🚀 AiDincharya: Comprehensive Setup & User Execution Guide

> **Project Title:** AiDincharya: Unified Ayurvedic Routine Automation System  
> **Architecture:** Unified FastAPI (Python) Backend + React/Vite (TypeScript) Web App + Flutter Mobile App  
> **Last Updated:** August 2026

---

## 📋 System Requirements & Prerequisites

Before running the application, make sure you have the following installed on your machine:

1. **Python:** Version 3.10+ (Python 3.14 recommended). Check with `python --version`.
2. **Node.js:** Version 18+ (Node 20+ recommended). Check with `node -v` and `npm -v`.
3. **Flutter SDK (Optional):** Required only if running the native mobile application (`mobile_app/`).

---

## 🏗️ 1. Project Directory Structure

```text
AIDincharya-Unified/
├── backend/                  # FastAPI Backend API & AI Engine
│   ├── src/                  # Perception, RAG Knowledge Base, LangGraph Planner, Safety Guardrails
│   ├── tests/                # Pytest automated test suite (31 tests)
│   ├── main.py               # Main FastAPI server entry point
│   ├── dinacharya.db         # SQLite database
│   └── requirements.txt      # Python dependencies
├── frontend/                 # React 18 + Vite + TypeScript + Tailwind SPA
│   ├── src/                  # React UI components, routes, context, & API client
│   ├── package.json          # Node dependencies
│   ├── vite.config.ts        # Vite build config
│   └── tsconfig.app.json     # TypeScript configuration
├── mobile_app/               # Flutter Cross-Platform Mobile Client codebase
└── docs/                     # Diagnostic reports, API docs, & verification reports
```

---

## ⚡ 2. Step-by-Step Setup & Running Guide

To run the complete system, open **two separate terminal windows** (Terminal 1 for Backend, Terminal 2 for Frontend).

### 🔹 Terminal 1: Backend Server (FastAPI)

1. Open your terminal and navigate to the `backend` folder:
   ```powershell
   cd backend
   ```

2. Create and activate a Python Virtual Environment:
   * **On Windows (PowerShell / Command Prompt):**
     ```powershell
     python -m venv .venv
     .venv\Scripts\activate
     ```
   * **On Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. Install required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the FastAPI backend server:
   ```bash
   python main.py
   ```

   > **Backend Status:**  
   > Server will run at: **`http://localhost:8000`**  
   > Interactive API Documentation (Swagger): **`http://localhost:8000/docs`**

---

### 🔹 Terminal 2: Frontend Web Application (React + Vite)

1. Open a **second terminal window** and navigate to the `frontend` folder:
   ```powershell
   cd frontend
   ```

2. Install Node.js package dependencies:
   ```bash
   npm install
   ```

3. Start the Vite development server:
   ```bash
   npm run dev
   ```

   > **Frontend Status:**  
   > Web App will be accessible at: 👉 **`http://localhost:5173`**

---

## 🌐 3. Using the Web Application

1. Open your web browser and navigate to **`http://localhost:5173`**.
2. **Register/Login:** Create a new account or log in.
3. **Prakriti Assessment / Onboarding:** Fill out the phenotypic questionnaire to calculate your *Vata*, *Pitta*, and *Kapha* baseline constitution.
4. **Daily Routine:** View your personalized daily schedule organized by Morning, Midday, and Evening time blocks.
5. **Insights & Vaidya AI Chat:** Navigate to the **Insights** tab to view your adherence ring, biometrics, and chat directly with your Vaidya assistant.

---

## 🧪 4. Running Verification & Diagnostic Tests

### 4.1 Run Pytest Unit Test Suite (31 Tests)

```powershell
cd backend
.venv\Scripts\activate
python -m pytest tests/
```
*Expected Result:* `31 passed` (100% pass rate).

### 4.2 Run RAG & Agent Diagnostic Verification

```powershell
cd backend
.venv\Scripts\activate
python test_rag_and_agent.py
```

### 4.3 Run End-to-End Latency Benchmark

```powershell
cd backend
.venv\Scripts\activate
python benchmark_latency.py
```

### 4.4 Build Frontend for Production

```powershell
cd frontend
npm run build
```
*Output:* Creates an optimized production bundle in `frontend/dist/`.

---

## ⚙️ 5. LLM Provider Configuration (`backend/.env`)

The system operates out-of-the-box with **zero mandatory external LLM API key requirements** by utilizing the built-in **Ayurvedic RAG Knowledge Fallback Engine**.

If you wish to connect an external OpenAI-compatible LLM server, configure `backend/.env`:

```env
# Provider Selection (Options: custom_llm, puter, openai, nvidia)
LLM_PROVIDER=custom_llm

# Custom / Local LLM Parameters (e.g. Ollama, vLLM, LM Studio)
CUSTOM_LLM_BASE_URL=http://localhost:11434/v1
CUSTOM_LLM_API_KEY=custom-llm-key
CUSTOM_LLM_MODEL=llama3

# Optional Puter Provider
PUTER_BASE_URL=https://api.puter.com/puterai/openai/v1/
PUTER_API_KEY=your_puter_key
```

---

## ❓ 6. Troubleshooting & FAQs

#### Q1: "I get a 500 error or LLM connection message in chat."
* **Cause:** No external LLM server is running on `CUSTOM_LLM_BASE_URL`.
* **Fix:** The system now automatically catches connection errors and returns grounded Ashtanga Hrdaya guidelines from the ChromaDB vector knowledge base. Make sure you restarted `python main.py` after pulling code updates.

#### Q2: "`'tsc' is not recognized as an internal command`"
* **Fix:** Run `npm install` inside the `frontend/` directory before building or running `npm run dev`.

#### Q3: "Changes to `backend/main.py` are not taking effect."
* **Fix:** Press `Ctrl + C` in Terminal 1 to stop `python main.py`, then start it again with `python main.py`.

---

## 📱 7. Running the Mobile Application (Flutter)

If you have Flutter installed and want to run the native mobile client:

```powershell
cd mobile_app
flutter pub get
flutter run
```

---

*Guide generated for AiDincharya Unified Ayurvedic Routine Automation System.*

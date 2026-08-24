# AIDincharya - API Key Setup & Running Guide

This guide explains how to configure your **Google AI Studio API Key**, set up your environment, and run the backend, frontend, and database viewer applications.

---

## 🔑 1. Obtaining & Setting Up Your Google AI Studio API Key

1. Go to [Google AI Studio](https://aistudio.google.com/) and sign in with your Google account.
2. Click **Create API Key** and copy your generated API key.
3. In the repository, navigate to the `backend/` folder.
4. Create or edit the file named `.env` inside `backend/`:
   ```bash
   # File: backend/.env
   
   # Google AI Studio API Key Configuration
   GEMINI_API_KEY=AIzaSy...your_actual_api_key_here...
   
   # LLM Provider Configuration
   LLM_PROVIDER=gemini
   DEFAULT_MODEL=gemini-3.6-flash
   DEBUG=True
   ```

> 🔒 **Security Note**: The `backend/.env` file is included in `.gitignore` and will **NEVER** be committed or pushed to GitHub.

---

## 🚀 2. Running the Backend Server

1. Open a terminal and navigate to the `backend/` directory:
   ```powershell
   cd backend
   ```
2. Activate your virtual environment (if using one):
   ```powershell
   # Windows PowerShell
   .\.venv\Scripts\Activate.ps1
   ```
3. Start the FastAPI Uvicorn server:
   ```powershell
   uvicorn main:app --reload
   ```
   - **Backend API URL**: `http://localhost:8000`
   - **Interactive API Documentation (Swagger)**: `http://localhost:8000/docs`

---

## 💻 3. Running the Frontend SPA

1. Open a new terminal and navigate to the `frontend/` directory:
   ```powershell
   cd frontend
   ```
2. Install frontend dependencies (first time only):
   ```powershell
   npm install
   ```
3. Launch the Vite development server:
   ```powershell
   npm run dev
   ```
   - **Frontend App URL**: `http://localhost:5173`

---

## 📊 4. (Optional) Running the Database Viewer

To inspect user accounts, assessment records, routines, and chat messages visually:

1. In the `backend/` directory, run:
   ```powershell
   python run_db_viewer.py
   ```
   - **Database Viewer Portal**: `http://localhost:8080`

---

## 🛠️ Verification & Diagnostic Testing

To verify that your Google AI Studio API key and ChromaDB knowledge base are functioning properly:

```powershell
cd backend
python test_rag_and_agent.py
```
If configured correctly, you will see `SUCCESS: Schedule generated` powered by `gemini-3.6-flash`.

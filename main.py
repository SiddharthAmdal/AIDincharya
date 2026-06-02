import time
import os
import hashlib
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.config import APP_NAME, DEBUG, PUTER_API_KEY, DEFAULT_MODEL
from src.models import (
    ScheduleGenerateRequest,
    AdherenceLogRequest,
    DinacharyaSchedule,
    DoshaProfile,
    UserContext
)
from src.perception.dosha_mapper import DoshaMapper
from src.knowledge.retriever import AyurvedaKnowledgeBase
from src.planning.agent import DinacharyaPlannerAgent
from src.safety.guardrails import ClinicalRuleEngine
from src.behavior.tracker import AdherenceTracker
from src.database import db

# Initialize FastAPI App
app = FastAPI(
    title=APP_NAME,
    description="Backend API for AI-based Ayurvedic Dinacharya Automation. Serves reactive SPA web portal and API endpoints.",
    version="1.0.0"
)

# Enable CORS for mobile application integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directory
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "src", "static")), name="static")

# --- Models ---
class AuthRequest(BaseModel):
    username: str
    password: str

class QuestionnaireRequest(BaseModel):
    responses: Dict[str, Any]

class ChatRequest(BaseModel):
    message: str
    chat_history: Optional[List[Dict[str, str]]] = None

# --- Helpers ---
def get_current_user(authorization: str = Header(None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1]
    user_id = db.get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid Session")
    return user_id

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# --- Page Routes ---
def serve_html(filename: str):
    path = os.path.join(os.path.dirname(__file__), "src", "static", filename)
    if not os.path.exists(path):
        path = os.path.join("src", "static", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {str(e)}</h1>", status_code=404)

@app.get("/", response_class=HTMLResponse)
def read_root(): return serve_html("index.html")

@app.get("/login", response_class=HTMLResponse)
def read_login(): return serve_html("login.html")

@app.get("/onboarding", response_class=HTMLResponse)
def read_onboarding(): return serve_html("onboarding.html")

@app.get("/architecture", response_class=HTMLResponse)
def read_architecture(): return serve_html("architecture.html")

@app.get("/dashboard", response_class=HTMLResponse)
def read_dashboard(): return serve_html("dashboard.html")

@app.get("/routine", response_class=HTMLResponse)
def read_routine(): return serve_html("routine.html")

@app.get("/reasoning", response_class=HTMLResponse)
def read_reasoning(): return serve_html("reasoning.html")


# --- Auth API ---
@app.post("/api/auth/register")
def register_user(req: AuthRequest):
    pwd_hash = hash_password(req.password)
    user_id = db.create_user(req.username, pwd_hash)
    if not user_id:
        raise HTTPException(status_code=400, detail="Username already exists")
    token = db.create_session(user_id)
    return {"token": token, "has_completed_onboarding": False}

@app.post("/api/auth/login")
def login_user(req: AuthRequest):
    pwd_hash = hash_password(req.password)
    user_id = db.authenticate_user(req.username, pwd_hash)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = db.create_session(user_id)
    state = db.get_user_state(user_id)
    return {"token": token, "has_completed_onboarding": state.get("has_completed_onboarding", False)}

@app.post("/api/user/questionnaire")
def save_questionnaire(req: QuestionnaireRequest, user_id: int = Depends(get_current_user)):
    db.update_user_questionnaire(user_id, req.responses)
    return {"status": "success"}

@app.get("/api/user/state")
def get_state(user_id: int = Depends(get_current_user)):
    return db.get_user_state(user_id)


# --- Core AI API ---
@app.post("/api/schedule/generate", response_model=Dict[str, Any])
def generate_schedule(request: ScheduleGenerateRequest, user_id: int = Depends(get_current_user)):
    try:
        # 1. Fetch User State from DB
        state = db.get_user_state(user_id)
        questionnaire = state.get("questionnaire_responses", {})
        adherence_score = state.get("adherence_score", 1.0)
        
        # 2. Perception Domain
        symptoms_map = {}
        if request.context.self_report_symptoms:
            for idx, sym in enumerate(request.context.self_report_symptoms):
                symptoms_map[f"symptom_{idx}"] = sym

        profile = DoshaMapper.generate_profile(
            user_id=str(user_id),
            questionnaire=questionnaire,  # Dynamically from DB
            telemetry=request.wearable_telemetry_7d,
            symptoms=symptoms_map
        )

        # 3. Behavior Domain
        complexity = AdherenceTracker.determine_complexity(adherence_score)

        # 4. Planning Domain
        planner = DinacharyaPlannerAgent()
        candidate_schedule = planner.generate(
            user_id=str(user_id),
            profile=profile,
            context=request.context,
            adherence_score=adherence_score,
            complexity=complexity
        )

        # 5. Safety Domain
        validated_schedule = ClinicalRuleEngine.validate(candidate_schedule, profile)

        # 6. Behavioral Nudge
        nudge = AdherenceTracker.generate_behavior_nudge(adherence_score)

        return {
            "schedule": validated_schedule,
            "dosha_profile": profile,
            "complexity_level": complexity,
            "behavioral_nudge": nudge,
            "timestamp": time.time()
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error compiling routine: {str(e)}")


@app.post("/api/adherence/log", response_model=Dict[str, Any])
def log_adherence(request: AdherenceLogRequest, user_id: int = Depends(get_current_user)):
    completed_count = len(request.completed_practices)
    recommended_count = len(request.recommended_practices)

    new_score = AdherenceTracker.calculate_adherence_score(completed_count, recommended_count)
    db.update_adherence_score(user_id, new_score)
    
    next_complexity = AdherenceTracker.determine_complexity(new_score)
    nudge = AdherenceTracker.generate_behavior_nudge(new_score)

    return {
        "user_id": str(user_id),
        "logged_completions": completed_count,
        "recommended_count": recommended_count,
        "adherence_score": new_score,
        "next_complexity_level": next_complexity,
        "behavioral_nudge": nudge,
        "timestamp": time.time()
    }


@app.post("/api/chat", response_model=Dict[str, Any])
def chat_assistant(request: ChatRequest, user_id: int = Depends(get_current_user)):
    try:
        planner = DinacharyaPlannerAgent()
        
        system_prompt = (
            "You are a warm, wise traditional Ayurvedic physician (Vaidya) and wellness companion. "
            "Your name is Vaidya AI. Answer the user's questions about daily routine (Dinacharya), "
            "health, nutrition, and seasons based on traditional principles of Vata, Pitta, and Kapha. "
            "Keep responses highly practical, peaceful, and concise (limit to 3 short paragraphs maximum). "
            "Include concrete daily habit suggestions whenever applicable."
        )

        messages = [{"role": "system", "content": system_prompt}]

        if request.chat_history:
            for turn in request.chat_history:
                messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})

        messages.append({"role": "user", "content": request.message})

        if PUTER_API_KEY == "placeholder_token":
            response_text = "Traditional Wisdom: The cornerstone of Dinacharya is consistency. Waking up close to Brahma Muhurta, drinking warm water (Ushapan), and calming the mind with Nadi Shodhana pranayama will balance all three Doshas."
        else:
            chat_completion = planner.openai_client.chat.completions.create(
                messages=messages,
                model=DEFAULT_MODEL,
                temperature=0.7,
                max_tokens=300
            )
            response_text = chat_completion.choices[0].message.content

        return {"response": response_text, "timestamp": time.time()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat assistant failed: {str(e)}")


class DebugLogRequest(BaseModel):
    message: str
    level: str = "info"

@app.post("/api/debug/log")
def debug_log(req: DebugLogRequest):
    print(f"[BROWSER {req.level.upper()}] {req.message}")
    with open("browser_debug.log", "a", encoding="utf-8") as f:
        f.write(f"[{req.level.upper()}] {req.message}\n")
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=DEBUG)

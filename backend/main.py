import time
import openai
import os
import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.database import db
from src.models import (
    UserAuthRequest, AuthResponse, QuestionnaireRequest,
    ScheduleGenerateRequest, AdherenceLogRequest, ChatRequest,
    DoshaProfile, UserContext, Practice, DinacharyaSchedule
)
from src.perception.dosha_mapper import DoshaMapper
from src.behavior.tracker import AdherenceTracker
from src.planning.agent import DinacharyaPlannerAgent
from src.safety.guardrails import ClinicalRuleEngine
from src.knowledge.retriever import get_knowledge_base
from src.config import APP_NAME, DEBUG, DEFAULT_MODEL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AiDincharya")

app = FastAPI(title=APP_NAME)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication logic
def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1]
    user_id = db.get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id

# Serve Static Files safely
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def serve_html(filename: str) -> str:
    filepath = os.path.join(STATIC_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"File {filename} not found")
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/", response_class=HTMLResponse)
def read_root():
    return serve_html("index.html")

@app.get("/login", response_class=HTMLResponse)
def login_page():
    return serve_html("login.html")

@app.get("/register", response_class=HTMLResponse)
def register_page():
    return serve_html("register.html")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return serve_html("dashboard.html")

@app.get("/routine", response_class=HTMLResponse)
def routine_page():
    return serve_html("routine.html")

@app.get("/reasoning", response_class=HTMLResponse)
def reasoning_page():
    return serve_html("reasoning.html")

@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_page():
    return serve_html("onboarding.html")

# --- Authentication API ---
@app.post("/api/auth/register", response_model=AuthResponse)
def register(req: UserAuthRequest):
    pwd_hash = db.hash_password(req.password)
    user_id = db.create_user(req.username, pwd_hash)
    if not user_id:
        raise HTTPException(status_code=400, detail="Username already exists")
    token = db.create_session(user_id)
    return {"token": token, "has_completed_onboarding": False}

@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: UserAuthRequest):
    user_id = db.authenticate_user(req.username, req.password)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = db.create_session(user_id)
    state = db.get_user_state(user_id)
    return {"token": token, "has_completed_onboarding": state.get("has_completed_onboarding", False)}

@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        db.delete_session(token)
    return {"status": "success"}

# --- User Profile & State API ---
@app.get("/api/user/profile")
def get_user_profile(user_id: int = Depends(get_current_user)):
    user_info = db.get_user_by_id(user_id)
    state = db.get_user_state(user_id)
    profile = DoshaMapper.generate_profile(
        user_id=str(user_id),
        questionnaire=state.get("questionnaire_responses", {}),
        telemetry=state.get("current_vikriti", {}).get("telemetry", {}),
        symptoms=state.get("current_vikriti", {}).get("symptoms", [])
    )
    return {
        "user": user_info,
        "state": state,
        "dosha_profile": profile.model_dump()
    }

@app.put("/api/user/profile")
def update_user_profile(req: QuestionnaireRequest, user_id: int = Depends(get_current_user)):
    db.update_user_questionnaire(user_id, req.responses)
    return {"status": "success"}

@app.post("/api/user/questionnaire")
def save_questionnaire(req: QuestionnaireRequest, user_id: int = Depends(get_current_user)):
    db.update_user_questionnaire(user_id, req.responses)
    return {"status": "success"}

@app.get("/api/user/state")
def get_state(user_id: int = Depends(get_current_user)):
    return db.get_user_state(user_id)

@app.get("/api/user/settings")
def get_settings(user_id: int = Depends(get_current_user)):
    state = db.get_user_state(user_id)
    return {"settings": state.get("user_settings", {})}

@app.put("/api/user/settings")
def update_settings(req: Dict[str, Any], user_id: int = Depends(get_current_user)):
    db.update_user_settings(user_id, req)
    return {"status": "success"}

# --- Health Telemetry & Symptoms API ---
@app.post("/api/health/telemetry")
def save_health_telemetry(req: Dict[str, Any], user_id: int = Depends(get_current_user)):
    telemetry = req.get("telemetry", {})
    symptoms = req.get("symptoms", [])
    db.update_current_vikriti(user_id, telemetry, symptoms)
    return {"status": "success"}

@app.get("/api/health/history")
def get_health_history(user_id: int = Depends(get_current_user)):
    state = db.get_user_state(user_id)
    return {
        "current_vikriti": state.get("current_vikriti", {}),
        "telemetry_baselines": state.get("telemetry_baselines", {})
    }

# --- Wearable SDK Sync Endpoint ---
from src.perception.wearables import WearableSyncEngine
from src.behavior.notifications import NotificationScheduler
from src.evaluation.analytics import PilotEvaluationAnalytics

@app.post("/api/wearables/sync")
def sync_wearable_telemetry(req: Dict[str, Any], user_id: int = Depends(get_current_user)):
    provider = req.get("provider", "standard")
    raw_payload = req.get("raw_payload", req.get("telemetry", {}))
    normalized = WearableSyncEngine.normalize_vendor_payload(provider, raw_payload)
    db.update_current_vikriti(user_id, normalized, req.get("symptoms", []))
    return {"status": "success", "normalized_telemetry": normalized}

# --- Notification Schedule Endpoint ---
@app.get("/api/notifications/pending")
def get_pending_notifications(user_id: int = Depends(get_current_user)):
    state = db.get_user_state(user_id)
    cached = state.get("last_schedule", {})
    if cached and "schedule" in cached:
        schedule_obj = DinacharyaSchedule.model_validate(cached["schedule"])
        notifs = NotificationScheduler.generate_pending_notifications(schedule_obj, str(user_id))
        return {"notifications": notifs}
    return {"notifications": []}

# --- Clinical Pilot Evaluation Metrics Endpoint ---
@app.get("/api/evaluation/metrics")
def get_clinical_evaluation_metrics(user_id: int = Depends(get_current_user)):
    metrics = PilotEvaluationAnalytics.compute_study_metrics([user_id])
    return metrics

# --- Shared Validation Helper ---
def validate_and_format_schedule(
    candidate_schedule: DinacharyaSchedule, 
    profile: DoshaProfile, 
    complexity: str, 
    adherence_score: float, 
    retrieved_guidelines: list, 
    user_id: int
) -> Dict[str, Any]:
    """Passes a raw candidate schedule through the safety boundary and formats the response."""
    # Safety Domain Boundary
    validated_schedule = ClinicalRuleEngine.validate(candidate_schedule, profile)
    
    nudge = AdherenceTracker.generate_behavior_nudge(adherence_score)

    return {
        "schedule": validated_schedule.model_dump(),
        "dosha_profile": profile.model_dump(),
        "complexity_level": complexity,
        "behavioral_nudge": nudge,
        "retrieved_guidelines": retrieved_guidelines,
        "timestamp": time.time()
    }

# --- Core AI API ---
@app.get("/api/schedule/today")
def get_today_schedule(user_id: int = Depends(get_current_user)):
    state = db.get_user_state(user_id)
    today_date = datetime.now().strftime('%Y-%m-%d')
    cached = state.get("last_schedule")
    if cached and state.get("schedule_date") == today_date:
        completed_today = db.get_today_completions(user_id, today_date)
        if "schedule" in cached:
            for block in ["morning_block", "midday_block", "evening_block"]:
                if block in cached["schedule"]:
                    cached["schedule"][block] = [
                        p for p in cached["schedule"][block] 
                        if p["name"] not in completed_today
                    ]
        return cached
    return {"schedule": None, "message": "No schedule generated today yet."}

@app.post("/api/schedule/generate", response_model=Dict[str, Any])
def generate_schedule(request: ScheduleGenerateRequest, user_id: int = Depends(get_current_user)):
    try:
        # 1. Fetch User State from DB
        state = db.get_user_state(user_id)
        
        # --- Smart Daily Logic ---
        today_date = datetime.now().strftime('%Y-%m-%d')
        current_hour = datetime.now().hour
        
        questionnaire = state.get("questionnaire_responses", {})
        adherence_score = state.get("adherence_score", 1.0)
        completed_today = db.get_today_completions(user_id, today_date)

        force_regen = False
        
        # A. Check if it's a new day
        if state.get("schedule_date") != today_date:
            logger.info(f"New day detected ({today_date}). Forcing fresh routine.")
            force_regen = True
        else:
            # B. Check for missed tasks (Stipulated time logic)
            cached_sched = state.get("last_schedule")
            if cached_sched:
                blocks = cached_sched.get("schedule", {}).get("morning_block", []) + \
                         cached_sched.get("schedule", {}).get("midday_block", []) + \
                         cached_sched.get("schedule", {}).get("evening_block", [])
                
                for practice in blocks:
                    time_slot = practice.get("time_slot", "")
                    if " - " in time_slot:
                        end_time_str = time_slot.split(" - ")[1] # e.g. "07:00"
                        try:
                            end_hour = int(end_time_str.split(":")[0])
                            # If current hour is past the end of the task and it's NOT completed
                            if current_hour >= end_hour and practice["name"] not in completed_today:
                                logger.info(f"Missed task detected: {practice['name']} (End: {end_time_str}). Recalibrating...")
                                force_regen = True
                                break
                        except Exception:
                            continue

        if not force_regen and state.get("last_schedule"):
            logger.info(f"Serving stable schedule for user {user_id}")
            # Filter out completed tasks from the cached schedule so they disappear from UI
            cached = state["last_schedule"]
            if "schedule" in cached:
                for block in ["morning_block", "midday_block", "evening_block"]:
                    if block in cached["schedule"]:
                        cached["schedule"][block] = [
                            p for p in cached["schedule"][block] 
                            if p["name"] not in completed_today
                        ]
            return cached

        logger.info(f"Generating/Compensating routine for user {user_id}...")

        # Persist the current telemetry/symptoms as Vikriti so the Chat Agent can see it later
        db.update_current_vikriti(user_id, request.wearable_telemetry_7d, request.context.self_report_symptoms)

        # 2. Perception Domain
        profile = DoshaMapper.generate_profile(
            user_id=str(user_id),
            questionnaire=questionnaire,
            telemetry=request.wearable_telemetry_7d,
            symptoms=request.context.self_report_symptoms
        )

        # 3. Behavior Domain
        complexity = AdherenceTracker.determine_complexity(adherence_score)

        # 4. Planning Domain
        planner = DinacharyaPlannerAgent()
        planning_result = planner.generate(
            user_id=str(user_id),
            profile=profile,
            context=request.context,
            adherence_score=adherence_score,
            complexity=complexity,
            completed_today=completed_today
        )
        candidate_schedule = planning_result["schedule"]
        retrieved_guidelines = planning_result["retrieved_guidelines"]

        # 5. Shared Safety Boundary
        response_data = validate_and_format_schedule(
            candidate_schedule, profile, complexity, adherence_score, retrieved_guidelines, user_id
        )
        
        # --- Save to Database ---
        db.save_user_schedule(user_id, response_data, today_date)

        return response_data

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error compiling routine: {str(e)}")

@app.post("/api/adherence/log", response_model=Dict[str, Any])
def log_adherence(request: AdherenceLogRequest, user_id: int = Depends(get_current_user)):
    today_date = datetime.now().strftime('%Y-%m-%d')
    completed_count = len(request.completed_practices)
    recommended_count = len(request.recommended_practices)

    # 1. Update overall adherence score
    new_score = AdherenceTracker.calculate_adherence_score(completed_count, recommended_count)
    db.update_adherence_score(user_id, new_score)
    
    # 2. Save specific task completions for the day
    for practice in request.completed_practices:
        db.save_completion(user_id, practice, today_date)

    complexity = AdherenceTracker.determine_complexity(new_score)
    nudge = AdherenceTracker.generate_behavior_nudge(new_score)

    return {
        "user_id": str(user_id),
        "adherence_score": new_score,
        "next_complexity_level": complexity,
        "behavioral_nudge": nudge,
        "timestamp": time.time()
    }

# --- Knowledge Base Direct API ---
@app.get("/api/knowledge/search")
def search_knowledge(q: str, k: int = 5):
    kb = get_knowledge_base()
    results = kb.search_query(q, k=k)
    return {"query": q, "results": results}

@app.get("/api/insights", response_model=Dict[str, Any])
def get_dynamic_insights(user_id: int = Depends(get_current_user)):
    try:
        planner = DinacharyaPlannerAgent()
        state = db.get_user_state(user_id) or {}
        
        profile = DoshaMapper.generate_profile(
            user_id=str(user_id),
            questionnaire=state.get("questionnaire_responses") or {},
            telemetry={},
            symptoms=[]
        )

        context = UserContext(season="Hemanta", weather="Cold", temperature_c=10, calendar_events=[], self_report_symptoms=[])
        kb = get_knowledge_base()
        guidelines = kb.retrieve(profile, context, k=2)
        guidelines_text = "\n".join([f"- {g['text']}" for g in guidelines])

        analysis_prompt = f"""
Analyze the following user state and provide 6 concise Ayurvedic insights for a node-based reasoning visualization.
- Profile: Vata {profile.prakriti.vata}, Pitta {profile.prakriti.pitta}, Kapha {profile.prakriti.kapha}
- Imbalances: Vata Aggravated: {profile.vikriti_flags.vata_aggravated}
- Guidelines: {guidelines_text}

Return JSON with exactly 6 keys: 
"node-sleep", "node-hrv", "node-vata", "node-knowledge", "node-planner", "node-result".
Each must have: "category", "title", "desc".
"""
        try:
            chat_completion = planner.openai_client.chat.completions.create(
                messages=[{"role": "system", "content": "You are a logical Ayurvedic analyzer. Output strict JSON."},
                          {"role": "user", "content": analysis_prompt}],
                model=DEFAULT_MODEL,
                response_format={"type": "json_object"}
            )
            insights = json.loads(chat_completion.choices[0].message.content)
        except Exception as llm_err:
            logger.warning(f"LLM insights call failed ({llm_err}). Using default insights fallback.")
            insights = {
                "node-sleep": {"category": "Sleep & Circadian", "title": "7.5h Rest Baseline", "desc": "Sleep alignment promotes Vata grounding during seasonal shifts."},
                "node-hrv": {"category": "Biometrics", "title": "HRV & Recovery", "desc": "HRV levels indicate stable autonomic nervous system balance."},
                "node-vata": {"category": "Dosha Perception", "title": f"{profile.primary_prakriti} Balance", "desc": "Current practices target pacifying Vata volatility."},
                "node-knowledge": {"category": "RAG Knowledge", "title": "Ashtanga Hrdaya Guidelines", "desc": "Grounding recommendations sourced from authentic classical texts."},
                "node-planner": {"category": "Agentic Routine", "title": "Dynamic Time Blocks", "desc": "Morning and evening habits structured for consistent adherence."},
                "node-result": {"category": "Clinical Status", "title": "Optimal Wellness Index", "desc": "Closed-loop adherence tracking maintaining baseline health."}
            }

        return {"insights": insights, "timestamp": time.time()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat", response_model=Dict[str, Any])
def chat_assistant(request: ChatRequest, user_id: int = Depends(get_current_user)):
    try:
        planner = DinacharyaPlannerAgent()
        
        # 1. Fetch Comprehensive User State
        state = db.get_user_state(user_id) or {}
        questionnaire = state.get("questionnaire_responses") or {}
        last_schedule = state.get("last_schedule") or {}
        current_routine = last_schedule.get("schedule") or {} if isinstance(last_schedule, dict) else {}
        adherence_score = state.get("adherence_score", 1.0)
        
        # Format Questionnaire for AI
        q_text = "USER'S ASSESSMENT DATA:\n"
        for q, a in questionnaire.items():
            q_text += f"- {q}: {a}\n"

        # Format routine for AI
        routine_summary = "USER'S CURRENT SCHEDULE:\n"
        if isinstance(current_routine, dict):
            for block_name in ["morning_block", "midday_block", "evening_block"]:
                practices = current_routine.get(block_name) or []
                if practices:
                    routine_summary += f"{block_name.replace('_', ' ').upper()}:\n"
                    for p in practices:
                        if isinstance(p, dict):
                            routine_summary += f"- {p.get('name', 'Practice')} ({p.get('time_slot', 'Daily')})\n"

        # Fetch persisted Vikriti
        current_vikriti = state.get("current_vikriti") or {}
        telemetry = current_vikriti.get("telemetry") or {} if isinstance(current_vikriti, dict) else {}
        symptoms_list = current_vikriti.get("symptoms") or [] if isinstance(current_vikriti, dict) else []

        # 2. Perception: Generate profile
        profile = DoshaMapper.generate_profile(
            user_id=str(user_id), 
            questionnaire=questionnaire, 
            telemetry=telemetry, 
            symptoms=symptoms_list
        )

        # 3. Retrieval: Fetch relevant guidelines
        context = UserContext(season="Balanced", weather="Pleasant", temperature_c=24.0, calendar_events=[], self_report_symptoms=[])
        kb = get_knowledge_base()
        guidelines = kb.retrieve(profile, context, k=3)
        guidelines_text = "\n".join([f"- {g['text']}" for g in guidelines])

        system_prompt = (
            "You are a warm, wise traditional Ayurvedic physician (Vaidya).\n\n"
            "YOUR TOOLS:\n"
            f"- SYSTEM CLOCK: The current time is {time.strftime('%Y-%m-%d %H:%M:%S')}.\n"
            "- WELLNESS VAULT: You have direct access to the user's Assessment Data and Daily Schedule history.\n\n"
            f"{q_text}\n"
            f"{routine_summary}\n"
            "AUTHENTIC AYURVEDIC KNOWLEDGE BASE:\n" + guidelines_text +
            "\n\nINSTRUCTIONS:\n"
            "1. Use Markdown (**bold**, - lists) for clear clinical formatting.\n"
            "2. Reference specific assessment answers and current tasks.\n"
            "3. CRITICAL: If the user requests a timing change or routine adjustment, "
            "you MUST include the hidden tag [RECALIBRATE] at the end. This signals the Planner Agent.\n"
            "4. Be concise and empathetic (max 3 short paragraphs)."
        )

        messages = [{"role": "system", "content": system_prompt}]
        db_history = db.get_chat_history(user_id, limit=10)
        for turn in db_history:
            messages.append({"role": turn["role"], "content": turn["content"]})

        db.save_chat_message(user_id, "user", request.message)
        messages.append({"role": "user", "content": request.message})

        try:
            chat_completion = planner.openai_client.chat.completions.create(messages=messages, model=DEFAULT_MODEL, temperature=0.7, max_tokens=300)
            full_response = chat_completion.choices[0].message.content
        except Exception as llm_err:
            logger.warning(f"LLM chat call failed ({llm_err}). Using RAG knowledge fallback response.")
            top_guidelines = "\n".join([f"• {g['text'].strip()}" for g in guidelines[:2]])
            dom_dosha = max([("Vata", profile.prakriti.vata), ("Pitta", profile.prakriti.pitta), ("Kapha", profile.prakriti.kapha)], key=lambda x: x[1])[0]
            full_response = (
                f"Namaste! Based on classical Ayurvedic wisdom from our knowledge base for your **{dom_dosha}** profile:\n\n"
                f"{top_guidelines}\n\n"
                "I am here to guide your daily routine (*Dinacharya*). How can I assist you with your schedule or habits today?"
            )
        
        # --- Cross-Agent Communication: Proposed Recalibration ---
        proposed_schedule = None
        if "[RECALIBRATE]" in full_response:
            clean_proposal = full_response.replace("[RECALIBRATE]", "").strip()
            planner_directive = f"USER REQUEST: {request.message}\nAGREED PROPOSAL: {clean_proposal}"
            
            logger.info(f"Vaidya AI suggesting recalibration for user {user_id}.")
            full_response = clean_proposal
            
            import concurrent.futures
            RECALIBRATION_TIMEOUT_SECONDS = 15
            
            def _run_planner():
                today_date = datetime.now().strftime('%Y-%m-%d')
                completed_today = db.get_today_completions(user_id, today_date)
                complexity = AdherenceTracker.determine_complexity(adherence_score)
                
                planning_result = planner.generate(
                    user_id=str(user_id),
                    profile=profile,
                    context=context,
                    adherence_score=adherence_score,
                    complexity=complexity,
                    completed_today=completed_today,
                    user_instruction=planner_directive,
                    current_schedule=state.get("last_schedule")
                )
                candidate_schedule = planning_result["schedule"]
                
                validated = validate_and_format_schedule(
                    candidate_schedule, profile, complexity, adherence_score, [], user_id
                )
                return validated["schedule"]
            
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_run_planner)
                    proposed_schedule = future.result(timeout=RECALIBRATION_TIMEOUT_SECONDS)
            except Exception as planner_err:
                logger.warning(f"Recalibration planner failed for user {user_id}: {planner_err}.")
                proposed_schedule = None

        db.save_chat_message(user_id, "assistant", full_response)
        
        return {
            "response": full_response, 
            "proposed_schedule": proposed_schedule,
            "timestamp": time.time()
        }

    except openai.APITimeoutError:
        logger.warning(f"Chat LLM timed out for user {user_id}.")
        return {
            "response": "I apologize — my connection to the reasoning engine is experiencing delays right now. Please try again in a moment. 🙏",
            "proposed_schedule": None,
            "timestamp": time.time()
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat assistant failed: {str(e)}")

@app.post("/api/schedule/confirm")
def confirm_schedule(request: Dict[str, Any], user_id: int = Depends(get_current_user)):
    try:
        schedule = request.get("schedule")
        if not schedule:
            raise HTTPException(status_code=400, detail="No schedule provided")
        
        today_date = datetime.now().strftime('%Y-%m-%d')
        state = db.get_user_state(user_id)
        profile = DoshaMapper.generate_profile(
            user_id=str(user_id),
            questionnaire=state.get("questionnaire_responses", {}),
            telemetry={}, symptoms=[]
        )
        
        response_data = {
            "schedule": schedule,
            "dosha_profile": profile.model_dump(),
            "complexity_level": "Adaptive",
            "timestamp": time.time()
        }
        db.save_user_schedule(user_id, response_data, today_date)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/history")
def get_chat_history_api(user_id: int = Depends(get_current_user)):
    try:
        history = db.get_chat_history(user_id, limit=20)
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/chat/history")
def clear_chat_history(user_id: int = Depends(get_current_user)):
    try:
        conn = db.get_db_connection()
        c = conn.cursor()
        c.execute('DELETE FROM chat_history WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=DEBUG)

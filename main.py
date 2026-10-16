import time
import openai
import os
import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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
from src.knowledge.retriever import AyurvedaKnowledgeBase
from src.config import APP_NAME, DEBUG, DEFAULT_MODEL, validate_config
from src.llm_gateway import LLMGateway

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AiDincharya")

# Validate configuration on startup
config_status = validate_config(strict=False)
if not config_status["valid"]:
    logger.warning(f"Startup configuration warnings: {config_status['issues']}")

app = FastAPI(title=APP_NAME)

# CORS with explicit configurable allowlist (prevents wildcard with credentials)
cors_origins_env = os.getenv("CORS_ORIGINS", "")
if cors_origins_env:
    allowed_origins = [orig.strip() for orig in cors_origins_env.split(",") if orig.strip()]
else:
    allowed_origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Authentication logic
def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1]
    user_id = db.get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_id

# Serve Static Files
app.mount("/static", StaticFiles(directory="src/static"), name="static")

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("src/static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/login", response_class=HTMLResponse)
def login_page():
    with open("src/static/login.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/register", response_class=HTMLResponse)
def register_page():
    with open("src/static/register.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    with open("src/static/dashboard.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/routine", response_class=HTMLResponse)
def routine_page():
    with open("src/static/routine.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/reasoning", response_class=HTMLResponse)
def reasoning_page():
    with open("src/static/reasoning.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_page():
    with open("src/static/onboarding.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/sw.js")
def service_worker_route():
    """
    Serves the root Service Worker script with standard MIME type and root Service-Worker-Allowed header.
    """
    sw_file = os.path.join(os.path.dirname(__file__), "src", "static", "sw.js")
    if not os.path.exists(sw_file):
        raise HTTPException(status_code=404, detail="Service worker not found.")
    with open(sw_file, "r", encoding="utf-8") as f:
        content = f.read()
    return Response(
        content=content,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"}
    )


# --- Authentication API ---
@app.post("/api/auth/register", response_model=AuthResponse)
def register(req: UserAuthRequest):
    user_id = db.create_user(req.username, req.password)
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
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1]
    revoked = db.revoke_session(token)
    if not revoked:
        raise HTTPException(status_code=400, detail="Could not revoke session")
    return {"status": "success", "message": "Logged out successfully"}

@app.post("/remote_log")
@app.post("/api/log")
def remote_log(payload: Dict[str, Any]):
    """Receives client-side diagnostic and error telemetry."""
    logger.info(f"[RemoteLog] {payload}")
    return {"status": "logged"}

@app.post("/api/user/questionnaire")
def save_questionnaire(req: QuestionnaireRequest, user_id: int = Depends(get_current_user)):
    db.update_user_questionnaire(user_id, req.responses)
    return {"status": "success"}

@app.get("/api/user/state")
def get_state(user_id: int = Depends(get_current_user)):
    return db.get_user_state(user_id)


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
@app.post("/api/schedule/generate", response_model=Dict[str, Any])
def generate_schedule(request: ScheduleGenerateRequest, user_id: int = Depends(get_current_user)):
    try:
        # 1. Fetch User State from DB
        state = db.get_user_state(user_id)
        
        # --- Smart Daily Logic ---
        today_date = datetime.now().strftime('%Y-%m-%d')
        cached_sched = state.get("last_schedule")
        force_regen = getattr(request, "force_regen", False) or False
        
        # A. Check if user already has a valid persisted schedule
        has_valid_persisted_schedule = (
            cached_sched is not None 
            and isinstance(cached_sched, dict) 
            and "schedule" in cached_sched
        )

        if not force_regen and not request.questionnaire_responses and has_valid_persisted_schedule:
            logger.info(f"Serving stable persisted schedule for user {user_id}")
            if state.get("schedule_date") != today_date:
                db.save_user_schedule(user_id, cached_sched, today_date)
            return cached_sched

        logger.info(f"Generating/Compensating routine for user {user_id}...")

        # Persist the current telemetry/symptoms as Vikriti so the Chat Agent can see it later
        db.update_current_vikriti(user_id, request.wearable_telemetry_7d, request.context.self_report_symptoms)

        # 2. Perception Domain
        symptoms_map = {}
        if request.context.self_report_symptoms:
            for idx, sym in enumerate(request.context.self_report_symptoms):
                symptoms_map[f"symptom_{idx}"] = sym

        questionnaire = request.questionnaire_responses or state.get("questionnaire_responses", {})
        adherence_score = state.get("adherence_score", 1.0)

        profile = DoshaMapper.generate_profile(
            user_id=str(user_id),
            questionnaire=questionnaire,
            telemetry=request.wearable_telemetry_7d,
            symptoms=symptoms_map
        )

        # 3. Behavior Domain
        complexity = AdherenceTracker.determine_complexity(adherence_score)

        # 4. Planning Domain
        completed_today = []
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


@app.get("/api/schedule/current", response_model=Dict[str, Any])
def get_current_schedule(user_id: int = Depends(get_current_user)):
    """
    Retrieves the current canonical persisted schedule directly from the database.
    Sub-millisecond latency. Does not trigger live LLM generation.
    Carries forward valid persisted schedules across days automatically.
    """
    state = db.get_user_state(user_id)
    today_date = datetime.now().strftime('%Y-%m-%d')
    cached_sched = state.get("last_schedule")
    
    if cached_sched and isinstance(cached_sched, dict) and "schedule" in cached_sched:
        if state.get("schedule_date") != today_date:
            db.save_user_schedule(user_id, cached_sched, today_date)
        return cached_sched
            
    return {"schedule": None, "message": "No routine scheduled for today"}


@app.post("/api/adherence/log", response_model=Dict[str, Any])
def log_adherence(request: AdherenceLogRequest, user_id: int = Depends(get_current_user)):
    completed_count = len(request.completed_practices)
    recommended_count = len(request.recommended_practices)

    # 1. Update overall adherence score
    new_score = AdherenceTracker.calculate_adherence_score(completed_count, recommended_count)
    db.update_adherence_score(user_id, new_score)
    
    # 2. Save specific task completions for the day
    for practice in request.completed_practices:
        db.save_completion(user_id, practice)

    # NOTE: No longer invalidating the cache here, as per user request.
    # The cache will only be bypassed if a task is "missed" in the next GET.

    complexity = AdherenceTracker.determine_complexity(new_score)
    nudge = AdherenceTracker.generate_behavior_nudge(new_score)

    return {
        "user_id": str(user_id),
        "adherence_score": new_score,
        "next_complexity_level": complexity,
        "behavioral_nudge": nudge,
        "timestamp": time.time()
    }


@app.get("/api/insights", response_model=Dict[str, Any])
def get_dynamic_insights(user_id: int = Depends(get_current_user)):
    """
    Returns 6 concise Ayurvedic insights for node-based reasoning visualization.
    Uses LLMGateway with bounded retries and guaranteed deterministic fallback so it never returns HTTP 500.
    """
    def _default_insights():
        return {
            "node-sleep": {"category": "Rest", "title": "Brahma Muhurta", "desc": "Wake near sunrise to align with natural circadian rhythm."},
            "node-hrv": {"category": "Autonomic", "title": "Pranayama Breathing", "desc": "Nadi Shodhana breathing balances autonomic nervous tone."},
            "node-vata": {"category": "Dosha", "title": "Vata Regulation", "desc": "Warm, grounding routines stabilize nervous volatility."},
            "node-knowledge": {"category": "RAG", "title": "Classical Guidance", "desc": "Retrieved classical Ayurvedic guidelines for your constitution."},
            "node-planner": {"category": "Agent", "title": "Dynamic Scheduling", "desc": "Adaptive routine generation based on constraints."},
            "node-result": {"category": "Outcome", "title": "Ojas Preservation", "desc": "Sustained vital energy and metabolic balance."}
        }

    try:
        state = db.get_user_state(user_id)
        gateway = LLMGateway.get_instance()
        
        profile = DoshaMapper.generate_profile(
            user_id=str(user_id),
            questionnaire=state.get("questionnaire_responses", {}),
            telemetry={},
            symptoms={}
        )

        context = UserContext(season="Hemanta", weather="Cold", temperature_c=10, calendar_events=[], self_report_symptoms=[])
        kb = AyurvedaKnowledgeBase()
        guidelines = kb.retrieve(profile, context, k=2)
        guidelines_text = "\n".join([f"- {g['text']}" for g in guidelines])

        analysis_prompt = f"""Analyze the following user state and provide 6 concise Ayurvedic insights for a node-based reasoning visualization.
- Profile: Vata {profile.prakriti.vata}, Pitta {profile.prakriti.pitta}, Kapha {profile.prakriti.kapha}
- Imbalances: Vata Aggravated: {profile.vikriti_flags.vata_aggravated}
- Guidelines: {guidelines_text}

Return JSON with exactly 6 keys: 
"node-sleep", "node-hrv", "node-vata", "node-knowledge", "node-planner", "node-result".
Each must have: "category", "title", "desc"."""

        insights, is_fallback = gateway.generate_structured_json(
            messages=[
                {"role": "system", "content": "You are a logical Ayurvedic analyzer. Output strict JSON only. Keep internal reasoning concise."},
                {"role": "user", "content": analysis_prompt}
            ],
            max_tokens=2048,
            fallback_fn=_default_insights
        )
        return {"insights": insights, "timestamp": time.time(), "is_fallback": is_fallback}

    except Exception as e:
        logger.warning(f"get_dynamic_insights fallback triggered for user {user_id}: {e}")
        return {"insights": _default_insights(), "timestamp": time.time(), "is_fallback": True}


@app.post("/api/chat", response_model=Dict[str, Any])
def chat_assistant(request: ChatRequest, user_id: int = Depends(get_current_user)):
    """
    Conversational Vaidya assistant powered by the centralized LLMGateway.
    Gracefully handles null schedule state, provider timeouts, and cross-agent recalibrations.
    """
    try:
        planner = DinacharyaPlannerAgent()
        gateway = LLMGateway.get_instance()
        
        # 1. Fetch Comprehensive User State safely
        state = db.get_user_state(user_id)
        questionnaire = state.get("questionnaire_responses", {})
        
        # Fix: Safely handle null last_schedule without crashing on None.get()
        last_sched = state.get("last_schedule") or {}
        current_routine = last_sched.get("schedule", {}) if isinstance(last_sched, dict) else {}
        adherence_score = state.get("adherence_score", 1.0)
        
        # Format Questionnaire for AI
        q_text = "USER'S ASSESSMENT DATA:\n"
        for q, a in questionnaire.items():
            q_text += f"- {q}: {a}\n"

        # Format routine for AI
        routine_summary = "USER'S CURRENT SCHEDULE:\n"
        for block_name in ["morning_block", "midday_block", "evening_block"]:
            practices = current_routine.get(block_name, []) if isinstance(current_routine, dict) else []
            if practices:
                routine_summary += f"{block_name.replace('_', ' ').upper()}:\n"
                for p in practices:
                    if isinstance(p, dict):
                        routine_summary += f"- {p.get('name', 'Practice')} ({p.get('time_slot', 'Flexible')})\n"

        # Fetch persisted Vikriti
        current_vikriti = state.get("current_vikriti", {})
        telemetry = current_vikriti.get("telemetry", {})
        symptoms_list = current_vikriti.get("symptoms", [])
        
        symptoms_map = {}
        for idx, sym in enumerate(symptoms_list):
            symptoms_map[f"symptom_{idx}"] = sym

        t_start = time.perf_counter()

        # 2. Perception: Generate profile
        profile = DoshaMapper.generate_profile(
            user_id=str(user_id), 
            questionnaire=questionnaire, 
            telemetry=telemetry, 
            symptoms=symptoms_map
        )

        # 3. Retrieval: Fetch relevant guidelines (query-specific RAG with fallback)
        t_rag_start = time.perf_counter()
        kb = AyurvedaKnowledgeBase()
        guidelines = kb.query_text(request.message, k=3)
        if not guidelines:
            context = UserContext(season="Balanced", weather="Pleasant", temperature_c=24.0, calendar_events=[], self_report_symptoms=[])
            guidelines = kb.retrieve(profile, context, k=3)
        t_rag = time.perf_counter() - t_rag_start
        guidelines_text = "\n".join([f"- {g['text']}" for g in guidelines])

        system_prompt = (
            "You are a warm, wise traditional Ayurvedic physician (Vaidya).\n\n"
            "YOUR CONTEXT:\n"
            f"- SYSTEM CLOCK: The current time is {time.strftime('%Y-%m-%d %H:%M:%S')}.\n"
            f"- AUTHENTICATED USER ID: {user_id}\n"
            "- WELLNESS VAULT: Access to user's Assessment Data, Adherence History, and Daily Schedule history.\n"
            "- GUIDELINE: Keep internal reasoning concise and output direct, empathetic markdown advice.\n\n"
            f"{q_text}\n"
            f"{routine_summary}\n"
            "AUTHENTIC AYURVEDIC KNOWLEDGE BASE:\n" + guidelines_text +
            "\n\nINSTRUCTIONS & PROTOCOLS:\n"
            "1. Use Markdown (**bold**, - lists) for clear clinical formatting.\n"
            "2. Reference specific assessment answers and current tasks.\n"
            "3. ADAPTATION & CONFIRMATION PROTOCOL:\n"
            "   - When a user asks to change, reschedule, move, or adjust an activity time, formulate a clear proposal.\n"
            "   - State clearly: 'I propose moving [Activity Name] from [Old Time] to [New Time]. Would you like me to confirm and update your daily routine?'\n"
            "   - Do NOT claim that the schedule has already been updated, synchronized, or rescheduled. It is ONLY updated after the user explicitly confirms (e.g. 'yes', 'confirm', 'apply').\n"
            "   - NEVER reschedule or modify unrelated activities (such as Trataka / Reflection) unless the user specifically asked for them.\n"
            "   - Append the tag [RECALIBRATE] at the very end of your proposal.\n"
            "4. Keep response under 3 concise, empathetic paragraphs."
        )

        messages = [{"role": "system", "content": system_prompt}]
        db_history = db.get_chat_history(user_id, limit=10)
        for turn in db_history:
            messages.append({"role": turn["role"], "content": turn["content"]})

        # Priority -1: Query Safety & Clinical Emergency Gate
        t_guard_start = time.perf_counter()
        from src.safety.guardrails import ClinicalRuleEngine
        safety_verdict = ClinicalRuleEngine.evaluate_query_safety(request.message)
        t_guard = time.perf_counter() - t_guard_start
        if not safety_verdict["is_safe"]:
            safety_msg = safety_verdict["message"]
            db.save_chat_message(user_id, "user", request.message)
            db.save_chat_message(user_id, "assistant", safety_msg)
            return {
                "response": safety_msg,
                "proposed_schedule": None,
                "schedule_updated": False,
                "timestamp": time.time(),
                "safety_alert": safety_verdict
            }

        db.save_chat_message(user_id, "user", request.message)
        messages.append({"role": "user", "content": request.message})

        # Check if user message is an explicit acceptance or rejection of a prior proposal
        user_msg_lower = request.message.lower().strip()
        is_acceptance = any(term in user_msg_lower for term in [
            "accept", "apply", "confirm", "yes, please", "yes please", "please do", 
            "make the change", "update it", "looks good", "sounds good"
        ]) or (user_msg_lower in ["yes", "y", "sure", "ok", "okay", "agreed", "done"])

        is_rejection = any(term in user_msg_lower for term in [
            "reject", "decline", "cancel", "no, don't", "no dont", "keep my original", 
            "keep original", "don't change", "dont change", "leave it", "keep as is"
        ]) or (user_msg_lower in ["no", "n", "nope", "nevermind"])

        last_assistant_msg = ""
        for turn in reversed(db_history):
            if turn.get("role") == "assistant":
                last_assistant_msg = turn.get("content", "")
                break

        # Rejection handling: leave schedule untouched
        if is_rejection and last_assistant_msg:
            reject_text = (
                "Understood. I have discarded the proposed adjustment. Your daily routine remains completely unchanged "
                "and preserved in your persistent vault. Let me know if you would like any other assistance! 🙏"
            )
            db.save_chat_message(user_id, "assistant", reject_text)
            return {
                "response": reject_text,
                "proposed_schedule": None,
                "schedule_updated": False,
                "timestamp": time.time()
            }

        cached_sched = state.get("last_schedule")
        today_date = datetime.now().strftime('%Y-%m-%d')
        
        # If user is accepting an existing proposal
        if is_acceptance and cached_sched and isinstance(cached_sched, dict) and "schedule" in cached_sched:
            sched_root = cached_sched["schedule"]
            all_practices = (
                sched_root.get("morning_block", []) +
                sched_root.get("midday_block", []) +
                sched_root.get("evening_block", [])
            )
            p_names = [p.get("name", "") if isinstance(p, dict) else p.name for p in all_practices]
            from src.planning.agent import extract_practice_time_updates
            from src.planning.schedule_service import mutate_user_schedule
            
            updates = {}
            for turn in reversed(db_history):
                if turn.get("role") == "assistant":
                    extracted = extract_practice_time_updates(turn.get("content", ""), p_names)
                    if extracted:
                        updates = extracted
                        last_assistant_msg = turn.get("content", "")
                        break
            
            if updates:
                mut_res = mutate_user_schedule(user_id, updates, date_str=today_date)
                if mut_res.get("success"):
                    confirm_text = (
                        "✓ **Schedule Synchronized**: I have updated your daily routine in your persistent vault. "
                        + ", ".join([f"**{k}** is now set to **{v}**" for k, v in updates.items()])
                        + ". All other practices and fixed commitments remain preserved. You can view your updated routine now. 🙏"
                    )
                    db.save_chat_message(user_id, "assistant", confirm_text)
                    return {
                        "response": confirm_text,
                        "proposed_schedule": mut_res["schedule"],
                        "schedule_updated": True,
                        "timestamp": time.time()
                    }
                else:
                    logger.error(f"Failed to persist accepted schedule change for user {user_id}: {mut_res.get('error')}")
                    fail_text = "I encountered an error persisting your schedule update to the vault. Your routine was not modified. Please try again."
                    db.save_chat_message(user_id, "assistant", fail_text)
                    return {
                        "response": fail_text,
                        "proposed_schedule": None,
                        "schedule_updated": False,
                        "timestamp": time.time()
                    }

        # Priority 0: Execute multi-step native tool calling loop connected to live planner tools
        from src.planning.tools import AVAILABLE_PLANNER_TOOLS, execute_planner_tool

        def bound_tool_executor(t_name: str, t_args: Dict[str, Any]) -> str:
            return execute_planner_tool(t_name, t_args, caller_user_id=str(user_id))

        t_pre = state.get("schedule_timestamp", 0)
        t_llm_start = time.perf_counter()
        chat_res = gateway.execute_tool_loop(
            messages=messages,
            tools=AVAILABLE_PLANNER_TOOLS,
            tool_executor_fn=bound_tool_executor,
            max_steps=3
        )
        t_llm = time.perf_counter() - t_llm_start
        full_response = chat_res.content.strip()
        if not full_response:
            full_response = (
                "Namaste! Based on your constitutional assessment and classical Ayurvedic guidelines, "
                "maintaining consistent wake times near Brahma Muhurta, nourishing meals during midday Agni, "
                "and restorative evening practices are foundational. How can I help adapt your Dinacharya today? 🙏"
            )
        
        # Check if any tool in the loop successfully mutated the canonical schedule
        fresh_state = db.get_user_state(user_id)
        schedule_was_updated = (fresh_state.get("schedule_timestamp", 0) > t_pre)
        
        # --- Cross-Agent Communication: Proposed Recalibration ---
        proposed_schedule = None
        if schedule_was_updated and fresh_state.get("last_schedule"):
            proposed_schedule = fresh_state["last_schedule"].get("schedule")
        elif "[RECALIBRATE]" in full_response:
            clean_proposal = full_response.replace("[RECALIBRATE]", "").strip()
            full_response = clean_proposal
            
            # Fast deterministic proposal extraction (NO redundant heavy LLM/RAG call)
            if cached_sched and isinstance(cached_sched, dict) and "schedule" in cached_sched:
                sched_root = cached_sched["schedule"]
                all_p = (
                    sched_root.get("morning_block", []) +
                    sched_root.get("midday_block", []) +
                    sched_root.get("evening_block", [])
                )
                p_names = [p.get("name", "") if isinstance(p, dict) else p.name for p in all_p]
                from src.planning.agent import extract_practice_time_updates, standardize_slot
                updates = extract_practice_time_updates(full_response, p_names)
                if updates:
                    from src.models import DinacharyaSchedule, Practice
                    from src.safety.guardrails import ClinicalRuleEngine
                    def clone_b(raw_items):
                        out = []
                        for it in raw_items:
                            d = it if isinstance(it, dict) else it.model_dump()
                            nm = d.get("name", "")
                            sl = updates.get(nm, d.get("time_slot", "Flexible"))
                            out.append(Practice(
                                name=nm,
                                time_slot=standardize_slot(sl),
                                duration_minutes=int(d.get("duration_minutes", 15)),
                                description=d.get("description", ""),
                                rationale=d.get("rationale", "")
                            ))
                        return out
                    cand = DinacharyaSchedule(
                        user_id=str(user_id),
                        adherence_score=state.get("adherence_score", 1.0),
                        routine_complexity=sched_root.get("routine_complexity", "Adaptive"),
                        morning_block=clone_b(sched_root.get("morning_block", [])),
                        midday_block=clone_b(sched_root.get("midday_block", [])),
                        evening_block=clone_b(sched_root.get("evening_block", [])),
                        timestamp=time.time()
                    )
                    val = ClinicalRuleEngine.validate(cand, profile)
                    proposed_schedule = val.model_dump()

        db.save_chat_message(user_id, "assistant", full_response)
        t_total = time.perf_counter() - t_start

        logger.info(
            f"[/api/chat timing user={user_id}] Total={t_total:.2f}s | RAG={t_rag:.3f}s | "
            f"Safety={t_guard:.3f}s | LLM={t_llm:.2f}s | Model={chat_res.model_used} | Fallback={chat_res.is_fallback}"
        )
        
        return {
            "response": full_response, 
            "proposed_schedule": proposed_schedule,
            "schedule_updated": schedule_was_updated,
            "timestamp": time.time(),
            "timings": {
                "total_seconds": round(t_total, 2),
                "rag_seconds": round(t_rag, 3),
                "safety_seconds": round(t_guard, 3),
                "llm_seconds": round(t_llm, 2),
                "model_used": chat_res.model_used,
                "is_fallback": chat_res.is_fallback
            }
        }

    except Exception as e:
        logger.error(f"Chat assistant fallback triggered for user {user_id}: {e}")
        fallback_msg = (
            "Namaste. I am currently experiencing a momentary delay in connecting to our full reasoning model. "
            "Please rest assured your daily routine is preserved. For your constitution, continue focusing on warm hydration, "
            "regular meal timings, and restorative rest. 🙏"
        )
        return {
            "response": fallback_msg,
            "proposed_schedule": None,
            "timestamp": time.time()
        }


# --- Notifications Endpoints ---

@app.get("/api/notifications", response_model=Dict[str, Any])
def get_user_notifications_route(
    unread_only: bool = False,
    limit: int = 20,
    user_id: int = Depends(get_current_user)
):
    """
    Fetches persistent notifications (schedule changes, circumstance alerts, reminders).
    """
    notifs = db.get_user_notifications(user_id=user_id, limit=limit, unread_only=unread_only)
    unread_count = sum(1 for n in notifs if not n.get("is_read"))
    return {"notifications": notifs, "count": len(notifs), "unread_count": unread_count}


@app.post("/api/notifications/{notification_id}/read", response_model=Dict[str, Any])
def mark_notification_read_route(
    notification_id: int,
    user_id: int = Depends(get_current_user)
):
    """
    Marks a user notification as read.
    """
    success = db.mark_notification_read(notification_id=notification_id, user_id=user_id)
    return {"success": success, "notification_id": notification_id}


# --- Web Push Notification Endpoints (RFC 8292 / VAPID) ---

class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(..., max_length=2048)
    keys: Optional[Dict[str, str]] = None
    p256dh: Optional[str] = Field(default=None, max_length=255)
    auth: Optional[str] = Field(default=None, max_length=255)
    user_agent: Optional[str] = Field(default=None, max_length=255)


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., max_length=2048)


@app.get("/api/notifications/push/vapid-public-key")
def get_vapid_public_key_route():
    """
    Returns the server's public VAPID key for creating browser push subscriptions.
    Never exposes private keys.
    """
    from src.notifications.push_service import get_vapid_public_key, is_push_configured
    key = get_vapid_public_key()
    return {
        "public_key": key,
        "configured": is_push_configured()
    }


@app.get("/api/notifications/push/status")
def get_push_status_route(user_id: int = Depends(get_current_user)):
    """
    Returns the Web Push subscription status for the authenticated user.
    """
    from src.notifications.push_service import is_push_configured
    status = db.get_user_push_status(user_id)
    return {
        "configured": is_push_configured(),
        "enabled": status["enabled"],
        "subscription_count": status["subscription_count"]
    }


@app.post("/api/notifications/push/subscribe")
def subscribe_push_route(
    req: PushSubscribeRequest,
    user_id: int = Depends(get_current_user)
):
    """
    Registers a browser Web Push subscription scoped strictly to the authenticated user.
    Enforces scheme validation (HTTPS or localhost) and key presence.
    """
    endpoint = req.endpoint.strip()
    if not (endpoint.startswith("https://") or endpoint.startswith("http://localhost") or endpoint.startswith("http://127.0.0.1")):
        raise HTTPException(status_code=400, detail="Invalid push endpoint scheme: HTTPS required.")
    
    p256dh = ""
    auth = ""
    if req.keys and isinstance(req.keys, dict):
        p256dh = req.keys.get("p256dh", "").strip()
        auth = req.keys.get("auth", "").strip()
    if not p256dh and req.p256dh:
        p256dh = req.p256dh.strip()
    if not auth and req.auth:
        auth = req.auth.strip()

    if not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Incomplete subscription keys (p256dh and auth required).")

    sub_id = db.save_push_subscription(
        user_id=user_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=req.user_agent
    )
    return {
        "success": True,
        "subscription_id": sub_id,
        "message": "Web Push subscription registered successfully."
    }


@app.post("/api/notifications/push/unsubscribe")
@app.delete("/api/notifications/push/unsubscribe")
def unsubscribe_push_route(
    req: PushUnsubscribeRequest,
    user_id: int = Depends(get_current_user)
):
    """
    Revokes an existing push subscription for the authenticated user.
    Strictly user-isolated: user A cannot revoke user B's subscription.
    """
    endpoint = req.endpoint.strip()
    deleted = db.delete_user_push_subscription(user_id=user_id, endpoint=endpoint)
    return {
        "success": deleted,
        "message": "Push subscription revoked." if deleted else "Subscription not found or unauthorized."
    }


@app.post("/api/notifications/push/test")
def test_push_route(user_id: int = Depends(get_current_user)):
    """
    Sends a test Web Push notification to the authenticated user's registered devices.
    """
    from src.notifications.push_service import send_push_notification_to_user, is_push_configured
    if not is_push_configured():
        return {
            "success": False,
            "configured": False,
            "message": "Web Push is not configured on the server."
        }
    
    res = send_push_notification_to_user(
        user_id=user_id,
        title="AI Dincharya Test",
        body="Web Push is active! Your Ayurvedic schedule reminders will sync here.",
        url="/routine",
        tag="test-push-notification"
    )
    return {
        "success": res.get("sent", 0) > 0,
        "summary": res
    }



# --- Agent Adaptation Endpoint ---

@app.post("/api/agent/adapt", response_model=Dict[str, Any])
def adapt_schedule_route(
    request: Dict[str, Any],
    user_id: int = Depends(get_current_user)
):
    """
    Phase 5 Circumstance Adaptation endpoint.
    Handles missed activities, calendar conflicts, fatigue/illness, task overrun, and priority shifts.
    """
    planner = DinacharyaPlannerAgent()
    state = db.get_user_state(user_id)
    
    current_vikriti = state.get("current_vikriti", {})
    telemetry = current_vikriti.get("telemetry", {})
    symptoms_list = current_vikriti.get("symptoms", [])
    symptoms_map = {f"sym_{i}": s for i, s in enumerate(symptoms_list)}

    profile = DoshaMapper.generate_profile(
        user_id=str(user_id),
        questionnaire=state.get("questionnaire_responses", {}),
        telemetry=telemetry,
        symptoms=symptoms_map
    )

    calendar_events = request.get("calendar_events", [])
    context = UserContext(
        season="Balanced",
        weather="Pleasant",
        temperature_c=24.0,
        calendar_events=calendar_events,
        self_report_symptoms=symptoms_list
    )

    event_type = request.get("event_type", "circumstance_change")
    event_data = request.get("event_data", {})
    current_sched = state.get("last_schedule") or {}

    adaptation_result = planner.adapt_schedule(
        user_id=str(user_id),
        current_schedule=current_sched,
        event_type=event_type,
        event_data=event_data,
        profile=profile,
        context=context,
        adherence_score=state.get("adherence_score", 1.0)
    )

    # Convert schedule to dict for JSON serialization if present
    if adaptation_result.get("schedule") is not None:
        adaptation_result["schedule"] = adaptation_result["schedule"].model_dump()

    return adaptation_result


@app.post("/api/schedule/confirm")
def confirm_schedule(request: Dict[str, Any], user_id: int = Depends(get_current_user)):
    try:
        schedule = request.get("schedule")
        if not schedule or not isinstance(schedule, dict):
            raise HTTPException(status_code=400, detail="No schedule provided")
        
        today_date = datetime.now().strftime('%Y-%m-%d')
        state = db.get_user_state(user_id)
        current_vikriti = state.get("current_vikriti", {})
        profile = DoshaMapper.generate_profile(
            user_id=str(user_id),
            questionnaire=state.get("questionnaire_responses", {}),
            telemetry=current_vikriti.get("telemetry", {}),
            symptoms={f"sym_{i}": s for i, s in enumerate(current_vikriti.get("symptoms", []))}
        )
        
        # Requirement 1: A schedule change must be validated before persistence
        from src.models import DinacharyaSchedule, Practice
        from src.safety.guardrails import ClinicalRuleEngine
        from src.planning.agent import standardize_slot

        def parse_raw_block(raw_items):
            out = []
            for item in raw_items:
                if isinstance(item, Practice):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(Practice(
                        name=item.get("name", "Practice"),
                        time_slot=standardize_slot(item.get("time_slot", "Flexible")),
                        duration_minutes=int(item.get("duration_minutes", 15)),
                        description=item.get("description", ""),
                        rationale=item.get("rationale", "")
                    ))
            return out

        candidate = DinacharyaSchedule(
            user_id=str(user_id),
            adherence_score=state.get("adherence_score", 1.0),
            routine_complexity=schedule.get("routine_complexity", "Adaptive"),
            morning_block=parse_raw_block(schedule.get("morning_block", [])),
            midday_block=parse_raw_block(schedule.get("midday_block", [])),
            evening_block=parse_raw_block(schedule.get("evening_block", [])),
            timestamp=time.time()
        )
        
        validated = ClinicalRuleEngine.validate(candidate, profile)

        response_data = {
            "schedule": validated.model_dump(),
            "dosha_profile": profile.model_dump(),
            "complexity_level": candidate.routine_complexity,
            "timestamp": time.time()
        }
        # Requirement 2 & 3: Save to canonical DB; confirm success ONLY after write succeeds
        db.save_user_schedule(user_id, response_data, today_date)

        # Create idempotent notification for the confirmed schedule
        db.create_notification(
            user_id=user_id,
            event_type="schedule_confirmed",
            message=f"Your daily routine for {today_date} has been confirmed and locked.",
            severity="info",
            channel="in_app",
            idempotency_key=f"confirm-direct-{user_id}-{today_date}-{int(time.time() // 60)}"
        )

        logger.info(f"Successfully persisted confirmed schedule for user {user_id}")
        return {"status": "success", "schedule": response_data["schedule"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error persisting confirmed schedule for user {user_id}: {e}")
        # Requirement 4: If persistence fails, return explicit failure
        raise HTTPException(status_code=500, detail=f"Failed to persist schedule: {str(e)}")


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
def remote_log(req: Dict[str, Any]):
    with open("browser_debug.log", "a", encoding="utf-8") as f:
        f.write(f"[{req.get('level', 'INFO').upper()}] {req.get('message', '')}\n")
    return {"status": "ok"}


def find_unused_port(start_port: int = 8000) -> int:
    import socket
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                port += 1


if __name__ == "__main__":
    import uvicorn
    port_env = os.getenv("PORT")
    if port_env:
        port = int(port_env)
    else:
        port = find_unused_port(8000)
    print(f"Starting server on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=DEBUG)


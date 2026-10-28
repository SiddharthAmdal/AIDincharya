import time
import re
import openai
import os
import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.database import db
from src.models import (
    UserAuthRequest, AuthResponse, QuestionnaireRequest,
    ScheduleGenerateRequest, AdherenceLogRequest, ActivityCompleteRequest, ChatRequest,
    DoshaProfile, UserContext, Practice, DinacharyaSchedule,
    ProposalActionRequest, ScheduleProposal
)
from src.perception.dosha_mapper import DoshaMapper
from src.behavior.tracker import AdherenceTracker
from src.behavior.scoring import ScoringEngine
from src.planning.agent import DinacharyaPlannerAgent
from src.safety.guardrails import ClinicalRuleEngine
from src.knowledge.retriever import AyurvedaKnowledgeBase
from src.perception.vikriti_tracker import VikritiTracker
from src.perception.wearable_interface import WearableTelemetryManager, HealthConnectPayload
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
    return {"token": token, "has_completed_onboarding": False, "username": req.username}

@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: UserAuthRequest):
    user_id = db.authenticate_user(req.username, req.password)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = db.create_session(user_id)
    state = db.get_user_state(user_id)
    return {"token": token, "has_completed_onboarding": state.get("has_completed_onboarding", False), "username": req.username}

@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1]
    revoked = db.revoke_session(token)
    if not revoked:
        raise HTTPException(status_code=400, detail="Could not revoke session")
    return {"status": "success", "message": "Logged out successfully"}

from src.perception.prakriti_questions import (
    get_prakriti_catalog,
    validate_questionnaire_responses,
    PRAKRITI_QUESTIONS
)

@app.post("/remote_log")
@app.post("/api/log")
def remote_log(payload: Dict[str, Any]):
    """Receives client-side diagnostic and error telemetry."""
    logger.info(f"[RemoteLog] {payload}")
    return {"status": "logged"}

@app.get("/api/user/questionnaire/questions")
def get_assessment_questions():
    """Returns the 24-question Prakriti assessment catalog organized into sections."""
    return get_prakriti_catalog()

@app.post("/api/user/questionnaire")
def save_questionnaire(req: QuestionnaireRequest, user_id: int = Depends(get_current_user)):
    # 1. Server-side validation of the 24 questions, identifiers, and allowed values
    is_valid, error_msg = validate_questionnaire_responses(req.responses)
    if not is_valid:
        raise HTTPException(status_code=422, detail=error_msg)

    # 2. Calculate preliminary Prakriti profile using DoshaMapper
    prakriti_explanation = DoshaMapper.explain_prakriti_classification(req.responses)
    
    # 3. Persist answers, preliminary profile, and set onboarding completed (resets cached schedule)
    db.update_user_questionnaire(user_id, req.responses, prakriti_profile=prakriti_explanation)

    logger.info(f"User {user_id} completed 24-question assessment: {prakriti_explanation.get('constitution_type')}")
    return {
        "status": "success",
        "message": "Prakriti assessment recorded successfully",
        "has_completed_onboarding": True,
        "prakriti": prakriti_explanation.get("dosha_vector", {}),
        "assessment_summary": prakriti_explanation
    }

@app.get("/api/user/state")
def get_state(user_id: int = Depends(get_current_user)):
    return db.get_user_state(user_id)


class VikritiCheckinRequest(BaseModel):
    symptoms: List[str] = Field(default_factory=list)
    telemetry: Optional[Dict[str, float]] = None


@app.post("/api/user/vikriti")
def log_vikriti_checkin(req: VikritiCheckinRequest, user_id: int = Depends(get_current_user)):
    """
    Records an authentic daily symptom observation and dynamic Vikriti state.
    Distinguishes self-report from wearable telemetry and tracks longitudinal trends.
    """
    past_obs = db.get_vikriti_observations(user_id, limit=7)
    flags, prov = VikritiTracker.estimate_vikriti(
        symptoms=req.symptoms,
        telemetry=req.telemetry,
        past_observations=past_obs
    )
    db.update_current_vikriti(
        user_id,
        telemetry=req.telemetry or {},
        symptoms=req.symptoms or [],
        estimate=flags.model_dump(),
        confidence=prov.get("confidence", "provisional"),
        data_status=prov.get("data_availability_status", "self_report_only")
    )
    return {
        "status": "success",
        "vikriti_estimate": flags.model_dump(),
        "confidence": prov.get("confidence"),
        "data_availability_status": prov.get("data_availability_status"),
        "provenance": prov
    }


@app.get("/api/user/vikriti/history")
def get_vikriti_history(user_id: int = Depends(get_current_user)):
    """Returns the longitudinal Vikriti observation history for the user."""
    return {
        "observations": db.get_vikriti_observations(user_id, limit=14)
    }


@app.post("/api/telemetry/health_connect")
def ingest_health_connect_telemetry(payload: Dict[str, Any], user_id: int = Depends(get_current_user)):
    """
    Ingests verified wearable records from Android Health Connect (e.g. Fastrack Noir Charm, Amazfit).
    Enforces freshness window (rejects records > 36h old or future-dated).
    Persists discrete records with stable deduplication and updates telemetry baselines.
    """
    try:
        hc_payload = HealthConnectPayload(**payload)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid Health Connect payload: {str(e)}")

    processed = WearableTelemetryManager.ingest_payload(hc_payload)
    signals = processed.get("signals") or processed.get("verified_signals") or {}
    discrete_records = processed.get("discrete_records", [])

    if not signals and not discrete_records:
        raise HTTPException(status_code=400, detail="No valid wearable signals ingested")

    device_model = processed.get("device", "Fastrack Noir Charm")
    source_pkg = processed.get("source_package", "com.google.android.apps.healthdata")
    prov = processed.get("acquisition_method", "health_connect_import")
    rec_time = processed.get("timestamp", time.time())

    inserted_count = 0
    duplicate_count = 0

    # 1. Persist each discrete record idempotently
    for r in discrete_records:
        rec_id = r.get("record_id")
        if not rec_id:
            rec_id = hashlib.sha256(f"{user_id}:{r['metric_type']}:{r['timestamp']}:{r['value']}:{r.get('source_package', source_pkg)}".encode()).hexdigest()[:24]

        is_new = db.save_telemetry_record(
            user_id=user_id,
            record_id=rec_id,
            metric_type=r["metric_type"],
            metric_value=float(r["value"]),
            unit=r.get("unit", "raw"),
            recorded_at=float(r.get("timestamp", rec_time)),
            source_package=r.get("source_package", source_pkg),
            device_model=r.get("device_model", device_model),
            provenance=r.get("acquisition_method", prov),
            aggregation_type=r.get("aggregation_type", "interval" if r["metric_type"] == "steps" else "instantaneous")
        )
        if is_new:
            inserted_count += 1
        else:
            duplicate_count += 1

    # 2. Update user_state telemetry_baselines with latest verified signals (strictly scoped to authenticated user)
    if signals:
        state = db.get_user_state(user_id)
        baselines = state.get("telemetry_baselines", {})
        baselines.update(signals)
        conn = db.get_db_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO user_state (user_id, telemetry_baselines) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET telemetry_baselines = excluded.telemetry_baselines
        ''', (user_id, json.dumps(baselines)))
        conn.commit()
        conn.close()

    processed["inserted_count"] = inserted_count
    processed["duplicate_count"] = duplicate_count
    return processed


@app.get("/api/telemetry/records")
def get_user_telemetry_history(
    metric_type: Optional[str] = None,
    limit: int = 50,
    user_id: int = Depends(get_current_user)
):
    """
    Returns stored verified wearable records for the authenticated user,
    retaining original timestamps, units, stable record IDs, and provenance.
    """
    records = db.get_user_telemetry_records(user_id, metric_type=metric_type, limit=limit)
    return {
        "records": records,
        "count": len(records),
        "user_id": user_id
    }


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
    safety_output = ClinicalRuleEngine.validate(candidate_schedule, profile)
    if isinstance(safety_output, dict) and "schedule" in safety_output:
        validated_schedule = safety_output["schedule"]
        safety_overrides = safety_output.get("overrides_applied", [])
    else:
        validated_schedule = safety_output
        safety_overrides = []
    
    provenance = getattr(candidate_schedule, "provenance", None)
    if provenance:
        if safety_overrides:
            provenance["safety_modifications"] = safety_overrides
        validated_schedule.provenance = provenance

    nudge = AdherenceTracker.generate_behavior_nudge(adherence_score)

    result = {
        "schedule": validated_schedule.model_dump(),
        "dosha_profile": profile.model_dump(),
        "complexity_level": complexity,
        "behavioral_nudge": nudge,
        "retrieved_guidelines": retrieved_guidelines,
        "provenance": provenance,
        "timestamp": time.time()
    }

    if getattr(profile, "assessment_status", "completed") == "unassessed":
        result["reduced_personalization_notice"] = "No completed 24-question Prakriti assessment found on record. Delivering a reduced-personalization balanced routine."

    return result


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

        # Evaluate wearable telemetry freshness (from request or authenticated user's persisted baselines)
        telemetry_signals = request.wearable_telemetry_7d
        if not telemetry_signals and state.get("telemetry_baselines"):
            telemetry_signals = state.get("telemetry_baselines")

        if telemetry_signals:
            is_fresh, fresh_msg = WearableTelemetryManager.check_freshness(telemetry_signals)
            if not is_fresh:
                logger.warning(f"Telemetry stale/invalid for user {user_id}: {fresh_msg}. Ignoring stale telemetry.")
                telemetry_signals = None

        # Retrieve past longitudinal observations for trend context
        past_obs = db.get_vikriti_observations(user_id, limit=7)

        # Estimate dynamic Vikriti using structured tracker
        vikriti_flags, vikriti_prov = VikritiTracker.estimate_vikriti(
            symptoms=request.context.self_report_symptoms,
            telemetry=telemetry_signals,
            past_observations=past_obs
        )

        # Persist the current telemetry/symptoms as Vikriti so the Chat Agent and future queries see it
        db.update_current_vikriti(
            user_id,
            telemetry=telemetry_signals or {},
            symptoms=request.context.self_report_symptoms or [],
            estimate=vikriti_flags.model_dump(),
            confidence=vikriti_prov.get("confidence", "provisional"),
            data_status=vikriti_prov.get("data_availability_status", "self_report_only")
        )

        # 2. Perception Domain: Build DoshaProfile
        symptoms_map = {}
        if request.context.self_report_symptoms:
            for idx, sym in enumerate(request.context.self_report_symptoms):
                symptoms_map[f"symptom_{idx}"] = sym

        questionnaire = request.questionnaire_responses or state.get("questionnaire_responses", {})
        adherence_score = state.get("adherence_score", 1.0)

        profile = DoshaMapper.generate_profile(
            user_id=str(user_id),
            questionnaire=questionnaire,
            telemetry=telemetry_signals,
            symptoms=symptoms_map
        )
        profile.vikriti_flags = vikriti_flags


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
    
    if cached_sched and isinstance(cached_sched, dict):
        if "schedule" in cached_sched and isinstance(cached_sched["schedule"], dict):
            if state.get("schedule_date") != today_date:
                db.save_user_schedule(user_id, cached_sched, today_date)
            return cached_sched
        elif "morning_block" in cached_sched or "midday_block" in cached_sched or "evening_block" in cached_sched:
            wrapped = {"schedule": cached_sched}
            if state.get("schedule_date") != today_date:
                db.save_user_schedule(user_id, wrapped, today_date)
            return wrapped
            
    return {"schedule": None, "message": "No routine scheduled for today"}


@app.post("/api/activities/complete", response_model=Dict[str, Any])
def complete_activity_endpoint(request: ActivityCompleteRequest, user_id: int = Depends(get_current_user)):
    """
    Authoritative task completion endpoint.
    Persistently marks a practice complete in activity_lifecycle and completions tables,
    idempotently recalculates adherence score, and updates user state.
    """
    target_practice = request.practice_name or request.activity_id
    if not target_practice:
        raise HTTPException(status_code=400, detail="Missing activity_id or practice_name")
    
    res = db.complete_user_activity(
        user_id=user_id,
        activity_id_or_name=target_practice,
        date_str=request.date,
        allow_early=request.allow_early or False
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to mark activity complete"))
    return res


@app.post("/api/adherence/log", response_model=Dict[str, Any])
def log_adherence(request: AdherenceLogRequest, user_id: int = Depends(get_current_user)):
    """
    Logs completed practices and updates overall adherence score.
    Uses authoritative complete_user_activity to ensure SQLite persistence,
    idempotent deduplication, and accurate adherence calculation.
    """
    last_res = {}
    for practice in request.completed_practices:
        last_res = db.complete_user_activity(user_id=user_id, activity_id_or_name=practice, allow_early=True)

    if request.recommended_practices:
        rec_count = len(request.recommended_practices)
        comp_count = len(request.completed_practices)
        new_score = AdherenceTracker.calculate_adherence_score(comp_count, rec_count)
        state_db = db.get_user_state(user_id)
        state_db["adherence_score"] = new_score
        db.save_user_state(user_id, state_db)
    else:
        state = db.get_user_state(user_id)
        new_score = state.get("adherence_score", 0.0)

    complexity = AdherenceTracker.determine_complexity(new_score)
    nudge = AdherenceTracker.generate_behavior_nudge(new_score)

    return {
        "user_id": str(user_id),
        "adherence_score": new_score,
        "next_complexity_level": complexity,
        "behavioral_nudge": nudge,
        "completed_count": last_res.get("completed_count", len(request.completed_practices)),
        "total_eligible_count": last_res.get("total_eligible_count", len(request.completed_practices)),
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


@app.get("/api/dashboard/summary", response_model=Dict[str, Any])
def get_dashboard_summary(user_id: int = Depends(get_current_user)):
    """
    Authenticated aggregated endpoint providing authentic data for the dashboard:
    - User state and profile (Prakriti / Vikriti)
    - Adherence percentage (from genuine completions)
    - 5-day adherence completion counts (trend)
    - Legitimate Wellness Score with documented inputs
    - Sleep metrics (None / unavailable if no sleep stages or records exist)
    - Wearable telemetry summary (HR, SpO2, Steps, Sleep, Stress)
    - Current schedule tasks for today
    """
    try:
        from src.perception.wearable_interface import WearableTelemetryManager
        state = db.get_user_state(user_id) or {}
        completions_today = db.get_today_completions(user_id)
        trend_completions = db.get_daily_completion_counts(user_id, days=5)
        telemetry = WearableTelemetryManager.get_user_telemetry_summary(user_id)
        cached_sched = state.get("last_schedule") or {}
        metrics = telemetry.get("metrics", {})
        hr_info = metrics.get("heart_rate", {})
        spo2_info = metrics.get("spo2", {})
        steps_info = metrics.get("steps", {})
        sleep_info = metrics.get("sleep", {})
        stress_info = metrics.get("stress", {})

        # Authoritative scoring using centralized ScoringEngine specification
        scores_bundle = ScoringEngine.derive_user_scores_from_telemetry_and_state(
            user_id=user_id,
            state=state,
            telemetry_summary=telemetry
        )

        sleep_res = scores_bundle["sleep"]
        wellness_res = scores_bundle["wellness"]
        adherence_res = scores_bundle["adherence"]

        adherence_pct = adherence_res["rounded_score"]
        wellness_score = wellness_res["rounded_score"] if wellness_res["rounded_score"] is not None else "--"
        wellness_formula = wellness_res.get("formula", "W = 0.35*S + 0.25*A + 0.25*P + 0.15*U")

        sleep_duration = None
        if sleep_info.get("status") == "available" and sleep_info.get("value") is not None:
            sleep_hours = float(sleep_info["value"])
            hrs = int(sleep_hours)
            mins = int((sleep_hours % 1) * 60)
            sleep_duration = f"{hrs}h {mins}m"

        sleep_score = sleep_res.get("rounded_score")
        sleep_status = "Awaiting overnight cycle" if sleep_score is None else f"{sleep_score}/100"
        sleep_note = sleep_res.get("note", "Wear watch overnight to record sleep.")

        # Format measurement ISO strings if recorded_at timestamp exists
        hr_ts = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(hr_info['recorded_at'])) if hr_info.get('recorded_at') else None
        spo2_ts = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(spo2_info['recorded_at'])) if spo2_info.get('recorded_at') else None
        steps_ts = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(steps_info['recorded_at'])) if steps_info.get('recorded_at') else None
        last_sync_ts = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(telemetry['last_recorded_at'])) if telemetry.get('last_recorded_at') else None

        dashboard_telemetry = {
            "has_wearable": telemetry.get("has_wearable_data", False),
            "device_model": telemetry.get("device_model", "Fastrack Noir Charm"),
            "source_package": telemetry.get("source_package", "com.titan.fastrack.reflex"),
            "is_sync_active": telemetry.get("is_sync_active", False),
            "last_sync": last_sync_ts,
            "heart_rate": {
                "value": hr_info.get("value"),
                "unit": hr_info.get("unit", "bpm"),
                "status": hr_info.get("status"),
                "measured_at": hr_ts,
                "is_available": hr_info.get("status") in ("available", "baseline_available"),
                "provenance": hr_info.get("provenance")
            },
            "steps": {
                "value": steps_info.get("value"),
                "unit": steps_info.get("unit", "steps"),
                "status": steps_info.get("status"),
                "measured_at": steps_ts,
                "is_available": steps_info.get("status") in ("available", "baseline_available"),
                "provenance": steps_info.get("provenance")
            },
            "spo2": {
                "value": spo2_info.get("value"),
                "unit": spo2_info.get("unit", "%"),
                "status": spo2_info.get("status"),
                "measured_at": spo2_ts,
                "is_available": spo2_info.get("status") in ("available", "baseline_available"),
                "provenance": spo2_info.get("provenance")
            },
            "sleep": {
                "value": sleep_info.get("value"),
                "status": sleep_info.get("status"),
                "is_available": sleep_info.get("status") == "available",
                "reason": sleep_info.get("reason", "Awaiting overnight cycle")
            },
            "stress": {
                "value": stress_info.get("value"),
                "status": stress_info.get("status"),
                "is_available": stress_info.get("status") == "available",
                "reason": stress_info.get("reason", "Hardware does not track stress")
            }
        }

        return {
            "user_id": user_id,
            "username": state.get("username", "Friend"),
            "wellness_score": wellness_score,
            "wellness_formula": wellness_formula,
            "sleep_score": sleep_score,
            "sleep_duration": sleep_duration,
            "sleep_status": sleep_status,
            "sleep_note": sleep_note,
            "adherence_pct": adherence_pct,
            "adherence_trend": trend_completions,
            "dosha_profile": state.get("dosha_profile") or {},
            "prakriti_profile": state.get("prakriti_profile") or {},
            "telemetry": dashboard_telemetry,
            "schedule": cached_sched,
            "completions_today": completions_today,
            "activities": db.get_user_activities(user_id, date_str=datetime.now().strftime("%Y-%m-%d")),
            "scores": scores_bundle,
            "is_upstream_stale": telemetry.get("is_upstream_stale", False),
            "stale_warning_message": telemetry.get("stale_warning_message"),
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Error generating dashboard summary for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard summary.")


def _run_chat_engine(request: ChatRequest, user_id: int, on_event: Optional[Any] = None) -> Dict[str, Any]:
    """
    Core conversational Vaidya assistant logic powered by centralized LLMGateway.
    Gracefully handles null schedule state, provider timeouts, and live event callbacks.
    """
    try:
        if on_event:
            try:
                on_event({"stage": "query_received", "message": "Query received by Ayurvedic reasoning agent", "timestamp": time.time()})
            except Exception:
                pass

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
        q_meta = {item["id"]: (item["number"], item["text"]) for item in PRAKRITI_QUESTIONS}
        q_text = "USER'S CONSTITUTIONAL ASSESSMENT DATA (24-Question Prakriti):\n"
        for q, a in questionnaire.items():
            if q in q_meta:
                q_num, q_question = q_meta[q]
                q_text += f"- Q{q_num} ({q_question}): {str(a).upper()}\n"
            else:
                q_text += f"- {q}: {a}\n"
        
        saved_prakriti = state.get("prakriti_profile", {})
        if saved_prakriti:
            c_type = saved_prakriti.get("constitution_type", "Provisional")
            q_text += f"ASSESSED BASELINE PRAKRITI: {c_type}\n"

        # Format routine for AI
        routine_summary = "USER'S CURRENT SCHEDULE:\n"
        for block_name in ["morning_block", "midday_block", "evening_block"]:
            practices = current_routine.get(block_name, []) if isinstance(current_routine, dict) else []
            if practices:
                routine_summary += f"{block_name.replace('_', ' ').upper()}:\n"
                for p in practices:
                    if isinstance(p, dict):
                        routine_summary += f"- {p.get('name', 'Practice')} ({p.get('time_slot', 'Flexible')})\n"

        # Fetch persisted Vikriti safely
        current_vikriti = state.get("current_vikriti") or {}
        if not isinstance(current_vikriti, dict):
            current_vikriti = {}
        telemetry = current_vikriti.get("telemetry") or {}
        symptoms_raw = current_vikriti.get("symptoms")
        symptoms_list = symptoms_raw if isinstance(symptoms_raw, list) else []
        
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

        t_rag_start = time.perf_counter()
        # 3. Retrieval: Fetch both constitutional guidelines and request-specific grounding passages
        context = UserContext(season="Balanced", weather="Pleasant", temperature_c=24.0, calendar_events=[], self_report_symptoms=symptoms_list)
        kb = AyurvedaKnowledgeBase()
        guidelines = kb.retrieve(profile, context, k=3)
        if request.message and len(request.message.strip()) > 3:
            msg_guidelines = kb.retrieve_by_query(request.message, k=3)
            seen_g = {g["text"][:120] for g in guidelines}
            for mg in msg_guidelines:
                if mg["text"][:120] not in seen_g:
                    guidelines.append(mg)
                    seen_g.add(mg["text"][:120])
        guidelines_text = "\n".join([f"- [{g.get('source', 'Ayurveda Grounding')}] {g['text']}" for g in guidelines])

        if on_event:
            try:
                on_event({"stage": "rag_retrieval_complete", "message": f"Retrieved {len(guidelines)} grounding guidelines", "timestamp": time.time()})
            except Exception:
                pass

        # Check if user message is an explicit acceptance or rejection of a prior proposal
        db_history = db.get_chat_history(user_id, limit=10)
        user_msg_lower = request.message.lower().strip()
        is_acceptance = any(term in user_msg_lower for term in [
            "accept", "apply", "confirm", "yes, please", "yes please", "please do", 
            "make the change", "update it", "looks good", "sounds good"
        ]) or (user_msg_lower in ["yes", "y", "sure", "ok", "okay", "agreed", "done"])

        # Distinguish flat rejection vs insisting on the rejected unsafe slot ("No, I would like this time")
        # vs proposing a new counter-time ("No, I would like 9:00 PM")
        has_time_in_msg = bool(
            re.search(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b|\b\d{1,2}\s*(?:am|pm)\b", user_msg_lower, re.IGNORECASE)
        )
        is_insistence_on_rejected = any(term in user_msg_lower for term in [
            "no, i would like this time", "no i would like this time",
            "no, i want this time", "no i want this time",
            "no, i would like that time", "no i would like that time",
            "i still want this time", "keep 7:30", "do it anyway"
        ])
        is_rejection = (
            any(term in user_msg_lower for term in [
                "reject", "decline", "cancel", "no, don't", "no dont", "keep my original", 
                "keep original", "keep my current", "don't change", "dont change", "leave it", "keep as is"
            ])
            or (user_msg_lower in ["no", "n", "nope", "nevermind"])
            or (
                any(term in user_msg_lower for term in ["no, i would like", "no i would like"])
                and not has_time_in_msg
            )
        )

        last_assistant_msg = ""
        for turn in reversed(db_history):
            if turn.get("role") == "assistant":
                last_assistant_msg = turn.get("content", "")
                break

        # 3b. Pre-evaluate any practice rescheduling request in the user's message against schedule & RAG principles
        cached_sched = state.get("last_schedule")
        all_practices = []
        if cached_sched and isinstance(cached_sched, dict) and "schedule" in cached_sched:
            sched_root_pre = cached_sched["schedule"]
            if isinstance(sched_root_pre, dict):
                all_practices = (
                    sched_root_pre.get("morning_block", []) +
                    sched_root_pre.get("midday_block", []) +
                    sched_root_pre.get("evening_block", [])
                )
        p_names_all = [p.get("name", "") if isinstance(p, dict) else p.name for p in all_practices]
        ai_proposed_candidates = [
            "Evening Gratitude Journaling", "Meditative Journaling", "Reflective Journaling",
            "Evening Journaling", "Gratitude Journaling", "Journaling",
            "Evening wind-down gratitude journaling", "Mindful Journaling"
        ]
        all_candidate_practices = list(dict.fromkeys(p_names_all + ai_proposed_candidates))

        from src.planning.agent import extract_practice_time_updates, standardize_slot

        from src.planning.schedule_service import (
            resolve_practice_intent,
            formulate_canonical_proposal,
            apply_canonical_proposal,
            discard_canonical_proposal
        )
        precheck_eval = None
        active_proposal = None
        active_proposed_schedule = None

        if not is_acceptance and not is_rejection and not is_insistence_on_rejected and cached_sched:
            intent = resolve_practice_intent(request.message, cached_sched)
            if intent:
                prop_form = formulate_canonical_proposal(
                    user_id=user_id,
                    target_practice=intent["target_practice"],
                    requested_slot=intent["requested_slot"],
                    current_schedule=cached_sched,
                    profile=profile,
                    symptoms=symptoms_list,
                    user_message=request.message
                )
                active_proposal = prop_form["proposal"]
                active_proposed_schedule = prop_form["proposed_schedule"]
                precheck_eval = prop_form["eval_res"]
            elif p_names_all:
                user_requested_updates = extract_practice_time_updates(request.message, p_names_all)
                if not user_requested_updates:
                    # Check if user mentioned a generic practice keyword (e.g. "pranayama", "bath", "massage", "exercise", "dinner")
                    # that might not yet be in p_names_all or is a substring
                    generic_candidates = ["Pranayama", "Abhyanga", "Snana (Bath)", "Vyayama (Exercise)", "Light Early Dinner", "Mitahara", "Trataka"]
                    user_requested_updates = extract_practice_time_updates(request.message, p_names_all + generic_candidates)
                if not user_requested_updates and has_time_in_msg:
                    # Counter-proposal follow-up (e.g. "No, I would like 9:00 PM" where the practice was in a recent proposal or turn)
                    prev_act = None
                    # Prioritize the target practice of the most recent proposal (whether pending, superseded, or rejected)
                    conn_p = db.get_db_connection()
                    cp = conn_p.cursor()
                    cp.execute("SELECT target_practice FROM schedule_proposals WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,))
                    rp = cp.fetchone()
                    conn_p.close()
                    if rp and rp["target_practice"]:
                        prev_act = rp["target_practice"]

                    if not prev_act and db_history:
                        for turn in reversed(db_history):
                            t_content = turn.get("content", "")
                            prev_updates = extract_practice_time_updates(t_content, p_names_all)
                            if prev_updates:
                                prev_act = next(iter(prev_updates.keys()))
                                break
                            for cand_p in p_names_all:
                                if cand_p and cand_p.lower() in t_content.lower():
                                    prev_act = cand_p
                                    break
                            if prev_act:
                                break
                    if prev_act:
                        synthetic_line = f"Move {prev_act} to {request.message}"
                        user_requested_updates = extract_practice_time_updates(synthetic_line, [prev_act])

                if user_requested_updates:
                    req_act, req_slot = next(iter(user_requested_updates.items()))
                    prop_form = formulate_canonical_proposal(
                        user_id=user_id,
                        target_practice=req_act,
                        requested_slot=req_slot,
                        current_schedule=cached_sched,
                        profile=profile,
                        symptoms=symptoms_list,
                        user_message=request.message
                    )
                    active_proposal = prop_form["proposal"]
                    active_proposed_schedule = prop_form["proposed_schedule"]
                    precheck_eval = prop_form["eval_res"]

            if precheck_eval:
                for cit in precheck_eval.get("retrieved_citations", []):
                    guidelines_text += f"\n- [{cit['source']}] {cit['excerpt']}"

        precheck_prompt_block = ""
        if precheck_eval:
            if precheck_eval["is_valid"]:
                precheck_prompt_block = (
                    f"\nPRINCIPLE VALIDATION RESULT FOR USER REQUEST:\n"
                    f"- Requested: '{precheck_eval['activity_name']}' at '{precheck_eval['proposed_slot']}'\n"
                    f"- Status: VALID (Passes Ayurvedic & Yogic temporal/digestive principles)\n"
                    f"- Rationale: {precheck_eval['clinical_explanation']}\n"
                )
            else:
                alts = precheck_eval.get("recommended_alternatives", [])
                best_alt = alts[0]["proposed_slot"] if alts else "18:30 - 18:45"
                alts_fmt = "; ".join([f"{a['proposed_slot']} ({a['rationale']})" for a in alts])
                precheck_prompt_block = (
                    f"\nCRITICAL PRINCIPLE VALIDATION RESULT FOR USER REQUEST:\n"
                    f"- Requested: '{precheck_eval['activity_name']}' at '{precheck_eval['proposed_slot']}'\n"
                    f"- Status: REJECTED / CONTRAINDICATED BY AYURVEDIC & YOGIC PRINCIPLES\n"
                    f"- Violated Principles: {'; '.join(precheck_eval['violated_principles'])}\n"
                    f"- Validated Alternative Slots: {alts_fmt}\n"
                    f"- MANDATORY ACTION: You MUST NOT approve {precheck_eval['proposed_slot']}. Warmly explain why it violates "
                    f"digestive/circadian principles (citing the grounding literature), and propose the safe alternative "
                    f"**{best_alt}** instead. Ask: 'I recommend scheduling {precheck_eval['activity_name']} at **{best_alt}** instead. "
                    f"Would you like me to confirm and update your daily routine to **{best_alt}**? (Reply **Yes** to accept this recommended time, "
                    f"or **No** to keep your current schedule unchanged.)' Append [RECALIBRATE] at the end.\n"
                )
        t_rag = time.perf_counter() - t_rag_start

        # Authenticated Wearable Telemetry Context Injection
        from src.perception.wearable_interface import WearableTelemetryManager
        telemetry_summary = WearableTelemetryManager.get_user_telemetry_summary(user_id)
        telemetry_prompt_block = "\n" + WearableTelemetryManager.format_telemetry_for_prompt(telemetry_summary) + "\n"

        system_prompt = (
            "You are a warm, wise traditional Ayurvedic physician (Vaidya).\n\n"
            "YOUR CONTEXT:\n"
            f"- SYSTEM CLOCK: The current time is {time.strftime('%Y-%m-%d %H:%M:%S')}.\n"
            f"- AUTHENTICATED USER ID: {user_id}\n"
            "- WELLNESS VAULT: Access to user's Assessment Data, Adherence History, Daily Schedule, and Synced Smartwatch Biometrics.\n"
            "- GUIDELINE: Keep internal reasoning concise and output direct, empathetic markdown advice.\n\n"
            f"{q_text}\n"
            f"{routine_summary}\n"
            f"{telemetry_prompt_block}\n"
            "AUTHENTIC AYURVEDIC & YOGIC KNOWLEDGE BASE:\n" + guidelines_text +
            precheck_prompt_block +
            "\n\nINSTRUCTIONS & PROTOCOLS:\n"
            "1. STRUCTURE & FORMATTING (Crucial for Dashboard UI Readability):\n"
            "   - Format all responses using clean, structured Markdown with clear visual hierarchy.\n"
            "   - When presenting daily routines, comparative timings, or multi-practice overviews, format them with clean Markdown tables (`| Block | Activity | Time-Slot | Duration | Core Ayurvedic Rationale |`) with a proper header and delimiter row (`|---|---|...|`).\n"
            "   - Use bold section headings (e.g. ### Today's Dinacharya (Daily Routine), ### Clinical Rationale, ### Next Steps) to organize distinct thoughts.\n"
            "   - Use clean bullet lists (`- `) for actions, guidelines, principles, or comparative timings.\n"
            "   - Use **bold** for practice names (e.g., **Pranayama**, **Abhyanga**), exact times (e.g., **18:30 – 18:45**), and core Ayurvedic concepts (*Jatharagni*, *Samana Vayu*, *Mitahara*, *Prakriti*).\n"
            "   - Keep paragraphs brief (1–3 sentences each) and clearly separated.\n"
            "   - Use classical grounding quotes or notes where appropriate (e.g., `> Ashtanga Hrdayam: ...` or `> Classical Grounding: ...`).\n"
            "2. Reference specific assessment answers, current scheduled tasks, and grounding principles.\n"
            "3. REASONED VALIDATION & ADAPTATION PROTOCOL:\n"
            "   - When a user asks to change, reschedule, move, or adjust an activity time, NEVER blindly agree.\n"
            "   - First inspect the USER'S CURRENT SCHEDULE (especially meal timings like Mitahara and Light Early Dinner, bath, exercise, and sleep) and call `propose_schedule_adaptation` to validate the requested slot against Ayurvedic & Yogic principles (such as the Bhuktavastu / empty-stomach rule requiring 2+ hours after a light meal or 3-4 hours after a main meal before Pranayama, Asana, Vyayama, Abhyanga, or Snana).\n"
            "   - IF THE REQUESTED TIME PASSES VALIDATION: State clearly:\n"
            "     'I propose moving [Activity Name] from [Old Time] to [New Time]. Would you like me to confirm and update your daily routine? (Reply **Yes** to confirm, or **No** to keep your current schedule.)' and append [RECALIBRATE].\n"
            "   - IF THE REQUESTED TIME VIOLATES PRINCIPLES: Do NOT approve the requested time. Explain the physiological reason warmly (e.g., practicing Pranayama or bathing right after a meal disrupts Samana Vayu and Jatharagni during the Kapha stage of digestion), recommend the best conflict-free alternative slot from the validator (e.g., 15-30 mins before dinner or 90-120 mins after dinner), and ask: 'I recommend scheduling [Activity Name] at **[Safe Alternative Time]** instead. Would you like me to confirm and update your daily routine to **[Safe Alternative Time]**? (Reply **Yes** to accept this recommended time, or **No** to keep your current schedule unchanged.)' and append [RECALIBRATE].\n"
            "   - Do NOT claim that the schedule has already been updated, synchronized, or rescheduled. It is ONLY updated after the user explicitly confirms.\n"
            "   - NEVER reschedule or modify unrelated activities (such as Trataka / Reflection) unless the user specifically asked for them.\n"
            "4. Maintain an empathetic, authoritative, and encouraging clinical tone.\n"
            "5. WEARABLE TELEMETRY & PHYSICAL ACTIVITY PROTOCOL:\n"
            "   - When asked if you monitor physical activity, biometrics, heart rate, steps, SpO2, or sleep, answer truthfully and affirmatively based on the VERIFIED WEARABLE TELEMETRY section above.\n"
            "   - You DO monitor their physical activity, heart rate, blood oxygen, and steps via their connected smartwatch (synced through Android Health Connect).\n"
            "   - If telemetry data is available in your context, report the exact values, metric units, measurement times, and source provenance (e.g., Fastrack Noir Charm via Health Connect).\n"
            "   - For steps: Report today's step count accurately with the recorded date.\n"
            "   - For sleep: If sleep data is marked unavailable / awaiting overnight cycle, explain clearly that sleep tracking requires wearing the watch through an overnight sleep cycle, without fabricating hours or claiming you lack all wearable access.\n"
            "   - For stress: If marked unavailable / unsupported by the device hardware, state clearly that their device hardware does not provide real-time stress telemetry and do NOT invent or guess a stress level from heart rate.\n"
            "   - Never claim you cannot access or monitor biometrics when telemetry records exist in your context."
        )

        messages = [{"role": "system", "content": system_prompt}]
        for turn in db_history:
            messages.append({"role": turn["role"], "content": turn["content"]})

        # Priority -1: Query Safety & Clinical Emergency Gate
        t_guard_start = time.perf_counter()
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

        # Insistence on a rejected/contraindicated time slot ("No, I would like this time"):
        # Hold the clinical safety guardrail firm, explain that the meal itself would need to move first, and keep schedule unchanged
        if is_insistence_on_rejected and last_assistant_msg:
            insist_text = (
                "### Clinical Safety Notice: Digestive Window\n\n"
                "I understand your preference for that time window. However, because classical Ayurvedic (*Bhuktavastu* / *Ashtanga Hrdayam*) "
                "and Ministry of AYUSH guidelines strictly contraindicate practicing **Pranayama**, **Vyayama**, **Abhyanga**, or **Snana** immediately after a meal "
                "(to protect *Jatharagni* and *Samana Vayu*), I cannot schedule it directly after your meal.\n\n"
                "### Current Status\n"
                "- Your current daily routine has been kept **safe and unchanged** in your vault.\n"
                "- If you would like to shift your meal time earlier so that slot becomes digested and safe, "
                "or choose another empty-stomach window, please let me know! 🙏"
            )
            db.save_chat_message(user_id, "assistant", insist_text)
            return {
                "response": insist_text,
                "proposed_schedule": None,
                "schedule_updated": False,
                "timestamp": time.time()
            }

        # Rejection handling: leave schedule untouched and discard pending proposal if any
        if is_rejection:
            pending_prop = db.get_pending_proposal(user_id)
            if pending_prop:
                pid = pending_prop.get("proposal_id") or pending_prop.get("id")
                if pid:
                    discard_canonical_proposal(user_id=user_id, proposal_id=pid)
            reject_text = (
                "### Schedule Adjustment Discarded\n\n"
                "Understood. I have discarded the proposed adjustment.\n\n"
                "- **Status**: Your daily routine remains **completely unchanged** and preserved in your persistent vault.\n"
                "- If you would like to explore a different time slot or adjust another part of your schedule (such as meal timings), please let me know! 🙏"
            )
            db.save_chat_message(user_id, "assistant", reject_text)
            return {
                "response": reject_text,
                "proposal": None,
                "proposed_schedule": None,
                "schedule_updated": False,
                "timestamp": time.time()
            }

        today_date = datetime.now().strftime('%Y-%m-%d')
        
        # If user is accepting an existing proposal
        if is_acceptance:
            pending_prop = db.get_pending_proposal(user_id)
            if pending_prop:
                pid = pending_prop.get("proposal_id") or pending_prop.get("id")
                apply_res = apply_canonical_proposal(user_id=user_id, proposal_id=pid)
                if apply_res.get("success"):
                    confirm_text = (
                        "### ✓ Schedule Synchronized\n\n"
                        f"I have successfully updated your daily routine in your persistent vault:\n\n"
                        f"- **Practice**: **{pending_prop['target_practice']}**\n"
                        f"- **New Time Slot**: **{pending_prop['proposed_time_slot']}**\n"
                        f"- **Integrity**: All other practices and fixed commitments remain preserved.\n\n"
                        "You can view your updated routine now in the Daily Routine tab. 🙏"
                    )
                    db.save_chat_message(user_id, "assistant", confirm_text)
                    return {
                        "response": confirm_text,
                        "proposal": apply_res.get("proposal"),
                        "proposed_schedule": apply_res.get("schedule"),
                        "schedule_updated": True,
                        "timestamp": time.time()
                    }
                else:
                    err_msg = apply_res.get("error", "Proposal could not be applied.")
                    fail_text = f"I could not apply the proposal: {err_msg} Your routine was not modified."
                    db.save_chat_message(user_id, "assistant", fail_text)
                    return {
                        "response": fail_text,
                        "proposal": None,
                        "proposed_schedule": None,
                        "schedule_updated": False,
                        "timestamp": time.time()
                    }
            elif cached_sched and isinstance(cached_sched, dict) and "schedule" in cached_sched:
                from src.planning.schedule_service import mutate_user_schedule
                updates = {}
                for turn in reversed(db_history):
                    if turn.get("role") == "assistant":
                        extracted = extract_practice_time_updates(turn.get("content", ""), p_names_all)
                        if extracted:
                            updates = extracted
                            last_assistant_msg = turn.get("content", "")
                            break
                if updates:
                    mut_res = mutate_user_schedule(user_id, updates, date_str=today_date)
                    if mut_res.get("success"):
                        applied_map = mut_res.get("applied_updates") or updates
                        applied_bullets = "\n".join([f"- **{k}**: now set to **{v}**" for k, v in applied_map.items()])
                        confirm_text = (
                            "### ✓ Schedule Synchronized\n\n"
                            "I have updated your daily routine in your persistent vault:\n\n"
                            f"{applied_bullets}\n\n"
                            "All other practices and fixed commitments remain preserved. You can view your updated routine now in the Daily Routine tab. 🙏"
                        )
                        db.save_chat_message(user_id, "assistant", confirm_text)
                        return {
                            "response": confirm_text,
                            "proposal": None,
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
                            "proposal": None,
                            "proposed_schedule": None,
                            "schedule_updated": False,
                            "timestamp": time.time()
                        }

        # Priority 0: Execute multi-step native tool calling loop connected to live planner tools
        from src.planning.tools import AVAILABLE_PLANNER_TOOLS, execute_planner_tool

        def bound_tool_executor(t_name: str, t_args: Dict[str, Any]) -> str:
            # Never allow premature DB mutation on Turn 1 when user has not explicitly confirmed
            if t_name == "persist_schedule_adaptation" and not is_acceptance:
                t_name = "propose_schedule_adaptation"
            return execute_planner_tool(t_name, t_args, caller_user_id=str(user_id))

        t_pre = state.get("schedule_timestamp", 0)
        t_llm_start = time.perf_counter()
        trace_events: List[Dict[str, Any]] = []
        is_fallback_response = False
        chat_res = None
        try:
            chat_res = gateway.execute_tool_loop(
                messages=messages,
                tools=AVAILABLE_PLANNER_TOOLS,
                tool_executor_fn=bound_tool_executor,
                max_steps=3,
                trace_events=trace_events,
                on_event=on_event
            )
            t_llm = time.perf_counter() - t_llm_start
            full_response = chat_res.content.strip()
            is_fallback_response = getattr(chat_res, "is_fallback", False)
        except Exception as loop_err:
            from src.llm_gateway import sanitize_secret_log
            logger.error(f"LLM tool execution loop failed for user {user_id}: {sanitize_secret_log(str(loop_err))}")
            t_llm = time.perf_counter() - t_llm_start
            full_response = ""
            is_fallback_response = True

        # Deterministic guardrail enforcement if LLM returned empty or failed to reject a contraindicated request
        if precheck_eval and not precheck_eval["is_valid"]:
            alts = precheck_eval.get("recommended_alternatives", [])
            best_alt = alts[0]["proposed_slot"] if alts else "18:30 - 18:45"
            best_alt_why = alts[0]["rationale"] if alts else "Practiced on an empty stomach before dinner."
            secondary_alt = f" Alternatively, **{alts[1]['proposed_slot']}** ({alts[1]['rationale']}) is also suitable." if len(alts) > 1 else ""
            if not full_response or best_alt not in full_response:
                full_response = (
                    f"Namaste. Looking at your current schedule, I cannot recommend scheduling **{precheck_eval['activity_name']}** "
                    f"at **{precheck_eval['proposed_slot']}**.\n\n"
                    f"### Clinical & Yogic Principle\n"
                    f"{precheck_eval['clinical_explanation']}\n\n"
                    f"### Recommended Safe Alternative\n"
                    f"- **Activity**: **{precheck_eval['activity_name']}**\n"
                    f"- **Proposed Time Slot**: **{best_alt}** ({best_alt_why}){secondary_alt}\n\n"
                    f"### Next Steps\n"
                    f"Would you like me to confirm and update your daily routine to **{best_alt}**?\n"
                    f"- Reply **Yes** to accept this recommended time.\n"
                    f"- Reply **No** to keep your current schedule unchanged. [RECALIBRATE]"
                )
            elif "[RECALIBRATE]" not in full_response:
                full_response += " [RECALIBRATE]"
        elif not full_response:
            if precheck_eval and precheck_eval["is_valid"]:
                full_response = (
                    f"Namaste! Moving **{precheck_eval['activity_name']}** to **{precheck_eval['proposed_slot']}** "
                    f"aligns well with your constitution and maintains proper spacing from your meals.\n\n"
                    f"### Proposed Schedule Adjustment\n"
                    f"- **Activity**: **{precheck_eval['activity_name']}**\n"
                    f"- **New Time Slot**: **{precheck_eval['proposed_slot']}**\n"
                    f"- **Clinical Status**: Verified against digestive & circadian guidelines.\n\n"
                    f"### Next Steps\n"
                    f"I propose moving **{precheck_eval['activity_name']}** to **{precheck_eval['proposed_slot']}**. "
                    f"Would you like me to confirm and update your daily routine?\n"
                    f"- Reply **Yes** to confirm and apply to your schedule.\n"
                    f"- Reply **No** to keep your current schedule unchanged. [RECALIBRATE]"
                )
            else:
                full_response = (
                    "### Vaidya AI Clinical Guidance\n\n"
                    "I am currently operating in resilient offline guidance mode due to temporary provider latency. "
                    "Your routine, assessment profile, and synced smartwatch biometrics remain safely preserved.\n\n"
                    "Based on your constitutional balance:\n"
                    "- **Morning Phase**: Grounding routines and hydration during Brahma Muhurta.\n"
                    "- **Midday Phase**: Mindful nutrition aligned with peak digestive Agni.\n"
                    "- **Evening Phase**: Gentle wind-down to pacify accumulated doshic excitation.\n\n"
                    "Please check your current scheduled practices in the Daily Routine tab. 🙏"
                )
        
        # Check if any tool in the loop successfully mutated the canonical schedule
        fresh_state = db.get_user_state(user_id)
        schedule_was_updated = (fresh_state.get("schedule_timestamp", 0) > t_pre)
        
        # --- Cross-Agent Communication: Proposed Recalibration ---
        proposed_schedule = None
        if schedule_was_updated and fresh_state.get("last_schedule"):
            proposed_schedule = fresh_state["last_schedule"].get("schedule")
        elif active_proposed_schedule:
            # Canonical proposal already formulated with validated preview schedule
            proposed_schedule = active_proposed_schedule
        elif "[RECALIBRATE]" in full_response:
            clean_proposal = full_response.replace("[RECALIBRATE]", "").strip()
            full_response = clean_proposal
            
            # Formulate canonical proposal from response if not already formulated
            if cached_sched and isinstance(cached_sched, dict) and "schedule" in cached_sched:
                sched_root = cached_sched["schedule"]
                updates = extract_practice_time_updates(full_response, p_names_all)
                if updates:
                    u_act, u_slot = next(iter(updates.items()))
                    prop_form = formulate_canonical_proposal(
                        user_id=user_id,
                        target_practice=u_act,
                        requested_slot=u_slot,
                        current_schedule=cached_sched,
                        profile=profile,
                        symptoms=symptoms_list,
                        user_message=request.message
                    )
                    active_proposal = prop_form["proposal"]
                    proposed_schedule = prop_form["proposed_schedule"]

        if "[RECALIBRATE]" in full_response:
            full_response = full_response.replace("[RECALIBRATE]", "").strip()

        # Invariant: Assistant prose must accurately describe the structured proposal time
        if active_proposal:
            target_p = active_proposal["target_practice"]
            target_slot = active_proposal["proposed_time_slot"]

            # Check if full_response already contains the proposed slot (handling en-dash, em-dash, and 12h formats)
            norm_resp = re.sub(r"[–—]", "-", full_response)
            norm_target_slot = re.sub(r"[–—]", "-", target_slot)
            already_described = (norm_target_slot in norm_resp)
            if not already_described:
                from src.safety.guardrails import _parse_slot_minutes
                parsed_target = _parse_slot_minutes(target_slot, 15)
                if parsed_target:
                    st_h = parsed_target[0] // 60
                    st_m = parsed_target[0] % 60
                    period = "PM" if st_h >= 12 else "AM"
                    h12 = st_h % 12 or 12
                    t12_str = f"{h12}:{st_m:02d} {period}"
                    t12_compact = f"{h12}:{st_m:02d}{period.lower()}"
                    if t12_str.lower() in full_response.lower() or t12_compact in full_response.lower().replace(" ", ""):
                        already_described = True
                    ext_resp_updates = extract_practice_time_updates(full_response, [target_p])
                    if ext_resp_updates and ext_resp_updates.get(target_p) == target_slot:
                        already_described = True

            if not already_described:
                full_response += (
                    f"\n\nI recommend scheduling **{target_p}** at **{target_slot}**. "
                    f"Would you like me to confirm and update your daily routine? "
                    f"(Reply **Yes** to accept, or **No** to keep your current schedule.)"
                )

        msg_id = db.save_chat_message(user_id, "assistant", full_response)
        t_total = time.perf_counter() - t_start

        model_name = chat_res.model_used if chat_res is not None else "deterministic-fallback"
        is_fb = chat_res.is_fallback if chat_res is not None else is_fallback_response
        logger.info(
            f"[/api/chat timing user={user_id}] Total={t_total:.2f}s | RAG={t_rag:.3f}s | "
            f"Safety={t_guard:.3f}s | LLM={t_llm:.2f}s | Model={model_name} | Fallback={is_fb}"
        )
        
        return {
            "message_id": msg_id,
            "response": full_response, 
            "proposal": active_proposal,
            "proposed_schedule": proposed_schedule,
            "schedule_updated": schedule_was_updated,
            "trace_events": trace_events,
            "timestamp": time.time(),
            "timings": {
                "total_seconds": round(t_total, 2),
                "rag_seconds": round(t_rag, 3),
                "safety_seconds": round(t_guard, 3),
                "llm_seconds": round(t_llm, 2),
                "model_used": model_name,
                "is_fallback": is_fb
            }
        }

    except Exception as e:
        logger.error(f"Chat assistant fallback triggered for user {user_id}: {e}")
        fallback_msg = (
            "Namaste. I am currently experiencing a momentary delay in connecting to our full reasoning model. "
            "Please rest assured your daily routine is preserved. For your constitution, continue focusing on warm hydration, "
            "regular meal timings, and restorative rest. 🙏"
        )
        fb_msg_id = db.save_chat_message(user_id, "assistant", fallback_msg)
        return {
            "message_id": fb_msg_id,
            "response": fallback_msg,
            "proposal": None,
            "proposed_schedule": None,
            "schedule_updated": False,
            "trace_events": [],
            "timestamp": time.time()
        }


@app.post("/api/chat", response_model=Dict[str, Any])
def chat_assistant(request: ChatRequest, user_id: int = Depends(get_current_user)):
    """
    Standard chat endpoint returning response and structured agent execution traces.
    """
    return _run_chat_engine(request, user_id)


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest, user_id: int = Depends(get_current_user)):
    """
    Live streaming SSE endpoint providing incremental agent lifecycle visibility,
    real-time tool calling events, durations, and final clinical recommendations.
    """
    import queue
    import threading

    event_queue: queue.Queue = queue.Queue()

    def on_event(evt: Dict[str, Any]):
        event_queue.put({"type": "trace", **evt})

    def run_worker():
        try:
            res = _run_chat_engine(request, user_id, on_event=on_event)
            event_queue.put({"type": "final_response", **res})
        except Exception as exc:
            logger.error(f"Error in chat stream worker for user {user_id}: {exc}")
            event_queue.put({
                "type": "error",
                "response": "Namaste. I am currently experiencing network latency connecting to the reasoning cluster. Your routine remains safe and preserved. Please try again shortly. 🙏"
            })
        finally:
            event_queue.put(None)

    threading.Thread(target=run_worker, daemon=True).start()

    def sse_generator():
        while True:
            item = event_queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )



# --- Phase 5 & 6: Adherence & Activity Lifecycle Endpoints ---

@app.post("/api/adherence/evaluate", response_model=Dict[str, Any])
def evaluate_adherence_endpoint(user_id: int = Depends(get_current_user)):
    """
    Evaluates telemetry and adherence for the authenticated user, automatically verifying
    wearable completion (Active Shathapavali), flagging missed practices, scheduling safe compensations,
    and generating deduplicated in-app notifications.
    """
    from src.planning.adherence_evaluator import evaluate_user_telemetry_and_adherence
    return evaluate_user_telemetry_and_adherence(user_id)


@app.get("/api/activities/today", response_model=Dict[str, Any])
def get_today_activities_endpoint(user_id: int = Depends(get_current_user)):
    """
    Retrieves the authenticated user's persistent activity lifecycle states for today.
    """
    target_date = datetime.now().strftime("%Y-%m-%d")
    activities = db.get_user_activities(user_id, date_str=target_date)
    return {
        "user_id": user_id,
        "date": target_date,
        "activities": activities,
        "count": len(activities)
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


@app.post("/api/schedule/proposal/apply", response_model=Dict[str, Any])
def apply_schedule_proposal_endpoint(
    req: ProposalActionRequest,
    user_id: int = Depends(get_current_user)
):
    from src.planning.schedule_service import apply_canonical_proposal
    res = apply_canonical_proposal(
        user_id=user_id,
        proposal_id=req.proposal_id,
        expected_schedule_version=req.expected_schedule_version
    )
    if not res.get("success"):
        status_code = 400
        if res.get("code") == "NOT_FOUND":
            status_code = 404
        elif res.get("code") == "FORBIDDEN":
            status_code = 403
        elif res.get("code") in ["STALE", "STALE_VERSION", "ALREADY_APPLIED", "REJECTED"]:
            status_code = 409
        raise HTTPException(status_code=status_code, detail=res.get("error"))
    return res


@app.post("/api/schedule/proposal/discard", response_model=Dict[str, Any])
def discard_schedule_proposal_endpoint(
    req: ProposalActionRequest,
    user_id: int = Depends(get_current_user)
):
    from src.planning.schedule_service import discard_canonical_proposal
    res = discard_canonical_proposal(user_id=user_id, proposal_id=req.proposal_id)
    if not res.get("success"):
        status_code = 400
        if res.get("code") == "NOT_FOUND":
            status_code = 404
        elif res.get("code") == "FORBIDDEN":
            status_code = 403
        raise HTTPException(status_code=status_code, detail=res.get("error"))
    return res


@app.get("/api/schedule/proposal/pending", response_model=Dict[str, Any])
def get_pending_proposal_endpoint(user_id: int = Depends(get_current_user)):
    proposal = db.get_pending_proposal(user_id)
    return {"proposal": proposal}


@app.post("/api/schedule/confirm")
def confirm_schedule(request: Dict[str, Any], user_id: int = Depends(get_current_user)):
    try:
        from src.planning.schedule_service import apply_canonical_proposal
        proposal_id = request.get("proposal_id")
        if proposal_id:
            res = apply_canonical_proposal(user_id=user_id, proposal_id=proposal_id)
            if not res.get("success"):
                status_code = 400
                if res.get("code") == "NOT_FOUND":
                    status_code = 404
                elif res.get("code") == "FORBIDDEN":
                    status_code = 403
                elif res.get("code") in ["STALE", "STALE_VERSION", "ALREADY_APPLIED", "REJECTED"]:
                    status_code = 409
                raise HTTPException(status_code=status_code, detail=res.get("error"))
            return {"status": "success", "schedule": res["schedule"], "proposal": res.get("proposal")}

        schedule = request.get("schedule")
        if not schedule or not isinstance(schedule, dict):
            raise HTTPException(status_code=400, detail="No schedule or proposal_id provided")
        
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


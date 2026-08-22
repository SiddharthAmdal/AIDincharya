from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, model_validator


class DoshaVector(BaseModel):
    """
    Normalized Ayurvedic Tri-Dosha Vector [Vata, Pitta, Kapha].
    Values should sum to 1.0 (or be normalized upon validation).
    """
    vata: float = Field(..., ge=0.0, le=1.0, description="Vata component fraction")
    pitta: float = Field(..., ge=0.0, le=1.0, description="Pitta component fraction")
    kapha: float = Field(..., ge=0.0, le=1.0, description="Kapha component fraction")

    @model_validator(mode="after")
    def normalize_vector(self) -> "DoshaVector":
        total = self.vata + self.pitta + self.kapha
        if total > 0 and abs(total - 1.0) > 1e-4:
            v = round(self.vata / total, 3)
            p = round(self.pitta / total, 3)
            k = round(1.0 - (v + p), 3)
            self.vata = max(0.0, min(1.0, v))
            self.pitta = max(0.0, min(1.0, p))
            self.kapha = max(0.0, min(1.0, k))
        return self


class VikritiFlags(BaseModel):
    """
    Dynamic flags indicating current physiological imbalances.
    """
    vata_aggravated: bool = Field(default=False, description="Is Vata dosha currently elevated?")
    pitta_aggravated: bool = Field(default=False, description="Is Pitta dosha currently elevated?")
    kapha_aggravated: bool = Field(default=False, description="Is Kapha dosha currently elevated?")
    has_fever: bool = Field(default=False, description="Active fever condition (Nava Jwara)")


class DoshaProfile(BaseModel):
    """
    The full phenotypic representation of a user's constitution.
    """
    user_id: str
    prakriti: DoshaVector = Field(..., description="Baseline constitution determined via questionnaire")
    vikriti_flags: VikritiFlags = Field(default_factory=VikritiFlags, description="Dynamic deviations detected from wearables")
    timestamp: float = Field(..., description="Timestamp of when the profile was generated")


class UserContext(BaseModel):
    """
    Real-time environmental, smartphone calendar, and subjective context.
    """
    season: str = Field(..., description="Current season (e.g. Winter/Hemanta, Summer/Grishma, Rainy/Varsha)")
    weather: str = Field(..., description="Current weather description (e.g. Cold and dry, Hot and humid, Rain)")
    temperature_c: float = Field(..., description="Current local temperature in Celsius")
    calendar_events: List[str] = Field(default_factory=list, description="List of calendar busy events today")
    self_report_symptoms: List[str] = Field(default_factory=list, description="User reported symptoms like fatigue, acid reflux, etc.")


class Practice(BaseModel):
    """
    A single Dinacharya practice task.
    """
    name: str = Field(..., description="Name of the Ayurvedic practice (e.g. Abhyanga, Nasya, Pranayama)")
    time_slot: str = Field(..., description="Assigned time range (e.g. 06:00 - 06:15)")
    duration_minutes: int = Field(..., description="Duration of the practice in minutes")
    description: str = Field(..., description="Ayurvedic instructions for the practice")
    rationale: str = Field(..., description="Plain-language explanation connecting this practice to the user's Dosha status")


class DinacharyaSchedule(BaseModel):
    """
    A full 24-hour personalized routine.
    """
    user_id: str
    adherence_score: float = Field(..., description="S_adj value at the time this schedule was planned")
    routine_complexity: str = Field(..., description="Complexity level (e.g. Anchor Habits, Moderate, Advanced)")
    morning_block: List[Practice] = Field(default_factory=list, description="Sunrise to Midday practices")
    midday_block: List[Practice] = Field(default_factory=list, description="Midday to Sunset practices")
    evening_block: List[Practice] = Field(default_factory=list, description="Sunset to Sleep practices")
    timestamp: float = Field(..., description="Timestamp of when the schedule was created")


# Request and Response schemas for API
class UserAuthRequest(BaseModel):
    username: str
    password: str

class AuthResponse(BaseModel):
    token: str
    has_completed_onboarding: bool

class QuestionnaireRequest(BaseModel):
    responses: Dict[str, str]

class ScheduleGenerateRequest(BaseModel):
    user_id: str
    questionnaire_responses: Optional[Dict[str, str]] = None
    wearable_telemetry_7d: Optional[Dict[str, float]] = None
    context: UserContext


class AdherenceLogRequest(BaseModel):
    user_id: str
    completed_practices: List[str] = Field(..., description="Names of completed practices today")
    recommended_practices: List[str] = Field(..., description="Names of recommended practices today")

class ChatRequest(BaseModel):
    message: str
    chat_history: Optional[List[Dict[str, str]]] = []

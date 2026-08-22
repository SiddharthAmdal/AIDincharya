// Auth Types
export interface AuthResponse {
  token: string;
  has_completed_onboarding: boolean;
}

export interface StandardResponse {
  status: string;
}

// User Types
export interface NotificationItem {
  id: string;
  title: string;
  message: string;
  type: string;
  timestamp?: number;
}

export interface NotificationsResponse {
  notifications: NotificationItem[];
}

export interface User {
  id: number;
  username: string;
  created_at: string;
}

export interface UserState {
  adherence_score: number;
  has_completed_onboarding: boolean;
  [key: string]: any;
}

export interface DoshaProfile {
  user_id: string;
  prakriti: {
    vata: number;
    pitta: number;
    kapha: number;
  };
  [key: string]: any;
}

export interface UserProfileResponse {
  user: User;
  state: UserState;
  dosha_profile: DoshaProfile;
}

export interface UserSettings {
  theme?: string;
  notifications?: boolean;
}

// Health Types
export interface TelemetryData {
  hrv_ms: number;
  resting_hr: number;
  sleep_hours: number;
  body_temp_c: number;
}

export interface HealthUploadRequest {
  telemetry: TelemetryData;
  symptoms: string[];
}

// Schedule Types
export interface RoutineTask {
  name: string;
  time_slot: string;
  duration_minutes: number;
  description: string;
  rationale: string;
}

export interface Schedule {
  user_id: string;
  adherence_score: number;
  routine_complexity: string;
  morning_block: RoutineTask[];
  midday_block: RoutineTask[];
  evening_block: RoutineTask[];
}

export interface ScheduleGenerateRequest {
  user_id: string;
  questionnaire_responses?: Record<string, string>;
  wearable_telemetry_7d?: Partial<TelemetryData>;
  context?: {
    season?: string;
    weather?: string;
    temperature_c?: number;
    calendar_events?: string[];
    self_report_symptoms?: string[];
  };
}

export interface ScheduleResponse {
  schedule: Schedule;
  dosha_profile: DoshaProfile;
  complexity_level: string;
  behavioral_nudge: {
    title: string;
    message: string;
  };
  retrieved_guidelines: any[];
  timestamp: number;
}

export interface AdherenceLogRequest {
  user_id: string;
  completed_practices: string[];
  recommended_practices: string[];
}

export interface AdherenceLogResponse {
  user_id: string;
  adherence_score: number;
  next_complexity_level: string;
  behavioral_nudge: {
    title: string;
    message: string;
  };
  timestamp: number;
}

// Knowledge Types
export interface KnowledgeSearchResult {
  text: string;
  source: string;
  score: number;
}

export interface KnowledgeSearchResponse {
  query: string;
  results: KnowledgeSearchResult[];
}

// Chat & Insights Types
export interface ChatRequest {
  message: string;
}

export interface ChatResponse {
  response: string;
  proposed_schedule?: Schedule;
  timestamp: number;
}

export interface InsightNode {
  category: string;
  title: string;
  desc: string;
}

export interface InsightsResponse {
  insights: Record<string, InsightNode>;
  timestamp: number;
}


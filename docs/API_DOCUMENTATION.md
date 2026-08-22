# AiDincharya REST API Specification

> **Base URL:** `http://localhost:8000`  
> **Specification Version:** 1.0.0  
> **Authentication Format:** HTTP Bearer Token (`Authorization: Bearer <token>`)

---

## 1. Authentication Endpoints

### 1.1 Register User
* **Method:** `POST`
* **URL:** `/api/auth/register`
* **Description:** Creates a new user account with PBKDF2-HMAC-SHA256 password hashing and initializes default user state.
* **Auth Required:** No
* **Request Schema:**
  ```json
  {
    "username": "string (min length 1, unique)",
    "password": "string (min length 1)"
  }
  ```
* **Response Schema (200 OK):**
  ```json
  {
    "token": "string (url-safe 32-byte secret)",
    "has_completed_onboarding": false
  }
  ```
* **Error Responses:**
  * `400 Bad Request` — `{"detail": "Username already exists"}`

---

### 1.2 Login User
* **Method:** `POST`
* **URL:** `/api/auth/login`
* **Description:** Authenticates credentials and returns an active session token.
* **Auth Required:** No
* **Request Schema:**
  ```json
  {
    "username": "string",
    "password": "string"
  }
  ```
* **Response Schema (200 OK):**
  ```json
  {
    "token": "string",
    "has_completed_onboarding": "boolean"
  }
  ```
* **Error Responses:**
  * `401 Unauthorized` — `{"detail": "Invalid credentials"}`

---

### 1.3 Logout User
* **Method:** `POST`
* **URL:** `/api/auth/logout`
* **Description:** Revokes and deletes the current session token from the database.
* **Auth Required:** Yes (`Authorization: Bearer <token>`)
* **Response Schema (200 OK):**
  ```json
  {
    "status": "success"
  }
  ```

---

## 2. User & Profile Endpoints

### 2.1 Get User Profile
* **Method:** `GET`
* **URL:** `/api/user/profile`
* **Description:** Retrieves complete user information, questionnaire state, settings, and calculated phenotypic Dosha profile.
* **Auth Required:** Yes
* **Response Schema (200 OK):**
  ```json
  {
    "user": { "id": 1, "username": "string", "created_at": "timestamp" },
    "state": { "adherence_score": 1.0, "has_completed_onboarding": true, ... },
    "dosha_profile": { "user_id": "1", "prakriti": { "vata": 0.5, "pitta": 0.3, "kapha": 0.2 }, ... }
  }
  ```

---

### 2.2 Save Questionnaire
* **Method:** `POST`
* **URL:** `/api/user/questionnaire` (or `PUT /api/user/profile`)
* **Description:** Saves bilingual phenotypic questionnaire responses and sets `has_completed_onboarding = true`.
* **Auth Required:** Yes
* **Request Schema:**
  ```json
  {
    "responses": {
      "q1": "I have dry skin and light body frame",
      "q2": "I prefer warm meals"
    }
  }
  ```
* **Response Schema (200 OK):**
  ```json
  {
    "status": "success"
  }
  ```

---

### 2.3 Get User State
* **Method:** `GET`
* **URL:** `/api/user/state`
* **Description:** Retrieves cached user state including adherence score, cached schedule, and Vikriti flags.
* **Auth Required:** Yes
* **Response Schema (200 OK):** JSON object representing raw `user_state` table contents.

---

### 2.4 Get & Update User Settings
* **Method:** `GET /api/user/settings` / `PUT /api/user/settings`
* **Description:** Reads or updates user preferences (e.g. notifications, dark mode, time display).
* **Auth Required:** Yes
* **PUT Request Body:** `{"theme": "dark", "notifications": true}`

---

## 3. Health & Telemetry Endpoints

### 3.1 Upload Telemetry & Symptoms
* **Method:** `POST`
* **URL:** `/api/health/telemetry`
* **Description:** Stores rolling 7-day wearable telemetry (HRV, RHR, Sleep, Temp) and self-reported symptoms.
* **Auth Required:** Yes
* **Request Schema:**
  ```json
  {
    "telemetry": {
      "hrv_ms": 35.0,
      "resting_hr": 68.0,
      "sleep_hours": 5.4,
      "body_temp_c": 38.5
    },
    "symptoms": ["Active fever", "Fatigue"]
  }
  ```
* **Response Schema (200 OK):** `{"status": "success"}`

---

### 3.2 Get Health History
* **Method:** `GET`
* **URL:** `/api/health/history`
* **Description:** Retrieves active Vikriti telemetry baselines and symptom history.
* **Auth Required:** Yes

---

## 4. Schedule & Planning Endpoints

### 4.1 Generate Schedule
* **Method:** `POST`
* **URL:** `/api/schedule/generate`
* **Description:** Triggers perception mapping, retrieval, LangGraph planning (with rule-based fallback), calendar conflict execution, and safety guardrail checks.
* **Auth Required:** Yes
* **Request Schema:**
  ```json
  {
    "user_id": "string",
    "questionnaire_responses": { "optional": "dict" },
    "wearable_telemetry_7d": { "hrv_ms": 50.0, "body_temp_c": 36.8 },
    "context": {
      "season": "Winter",
      "weather": "Cold and dry",
      "temperature_c": 12.0,
      "calendar_events": ["09:00 AM Standup"],
      "self_report_symptoms": []
    }
  }
  ```
* **Response Schema (200 OK):**
  ```json
  {
    "schedule": {
      "user_id": "1",
      "adherence_score": 1.0,
      "routine_complexity": "Moderate",
      "morning_block": [
        { "name": "Brahma Muhurta Jagaran", "time_slot": "06:00 - 06:15", "duration_minutes": 15, "description": "...", "rationale": "..." }
      ],
      "midday_block": [],
      "evening_block": []
    },
    "dosha_profile": { ... },
    "complexity_level": "Moderate",
    "behavioral_nudge": { "title": "...", "message": "..." },
    "retrieved_guidelines": [ ... ],
    "timestamp": 1700000000.0
  }
  ```

---

### 4.2 Get Today's Schedule
* **Method:** `GET`
* **URL:** `/api/schedule/today`
* **Description:** Returns today's active schedule with completed tasks filtered out.
* **Auth Required:** Yes

---

### 4.3 Log Task Adherence
* **Method:** `POST`
* **URL:** `/api/adherence/log`
* **Description:** Logs completed practices for the day, updates rolling adherence score $S_{adj}$, and adapts schedule complexity level.
* **Auth Required:** Yes
* **Request Schema:**
  ```json
  {
    "user_id": "string",
    "completed_practices": ["Brahma Muhurta Jagaran"],
    "recommended_practices": ["Brahma Muhurta Jagaran", "Abhyanga", "Lunch", "Dinner"]
  }
  ```
* **Response Schema (200 OK):**
  ```json
  {
    "user_id": "1",
    "adherence_score": 0.25,
    "next_complexity_level": "Anchor Habits",
    "behavioral_nudge": {
      "title": "Let's focus on the essentials",
      "message": "We've simplified your routine to anchor habits today."
    },
    "timestamp": 1700000000.0
  }
  ```

---

## 5. Knowledge RAG Search Endpoint

### 5.1 Search Knowledge Base
* **Method:** `GET`
* **URL:** `/api/knowledge/search?q=Dinacharya&k=5`
* **Description:** Direct semantic search interface over ChromaDB classical Ayurvedic texts.
* **Auth Required:** No
* **Response Schema (200 OK):**
  ```json
  {
    "query": "Dinacharya",
    "results": [
      {
        "text": "Extracted Ayurvedic text chunk...",
        "source": "Core Dinacharya Grounding PDF",
        "score": 0.1425
      }
    ]
  }
  ```

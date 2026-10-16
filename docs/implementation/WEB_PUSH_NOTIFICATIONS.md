# Production-Ready Web Push Notifications Architecture & Guide

## 1. Overview & Architectural Principles

AI Dincharya provides **optional Web Push notifications** to deliver schedule adaptation updates and routine reminders directly to the user's browser, even when the user is not actively viewing the web application.

Web Push serves as an **additional delivery channel** alongside the canonical in-app notification subsystem (SQLite). It is designed according to the following architectural tenets:

1. **Non-Blocking Decoupling:** Push delivery is completely decoupled from database persistence. A failure in Web Push delivery (e.g. push provider outage, network timeout, expired subscription) **never rolls back** a successfully persisted schedule mutation or chat response.
2. **Canonical Notification Integrity:** In-app notifications are stored in SQLite independently. A failed push delivery never deletes or invalidates the in-app notification record.
3. **Standards-Compliant VAPID (RFC 8292):** Cryptographic authentication uses Voluntary Application Server Identification (VAPID) with standard Elliptic Curve Digital Signatures (ECDSA P-256). Private keys are never committed, logged, or exposed to the client.
4. **Lock-Screen Privacy:** Push payloads are sanitized to prevent clinical, internal diagnostic codes, or sensitive physiological telemetry from appearing on the device lock-screen.
5. **Strict Cross-User Scoping:** Subscriptions are strictly isolated by authenticated `user_id`. One account cannot register, view, or revoke subscriptions belonging to another account.
6. **Self-Healing Lifecycle:** Permanent subscription failures (HTTP 404 Not Found or HTTP 410 Gone) are automatically purged from the database to eliminate zombie endpoints and unnecessary overhead.

---

## 2. VAPID Key Generation & Environment Configuration

### Generating VAPID Keys
AI Dincharya includes a dedicated CLI utility for generating valid, standards-compliant VAPID key pairs:

```bash
.venv/bin/python src/notifications/generate_vapid_keys.py
```

This outputs URL-safe base64-encoded strings:
- **`VAPID_PUBLIC_KEY`**: 65-byte uncompressed EC point (X9.62 format), safe for distribution to client browsers.
- **`VAPID_PRIVATE_KEY`**: 32-byte raw EC private key scalar. **Must remain strictly confidential.**

### Configuration (`.env`)
Copy `.env.example` and set the following variables:

```bash
# Web Push (VAPID) Configuration (RFC 8292)
VAPID_PUBLIC_KEY="YOUR_GENERATED_VAPID_PUBLIC_KEY"
VAPID_PRIVATE_KEY="YOUR_GENERATED_VAPID_PRIVATE_KEY"
VAPID_CLAIMS_EMAIL="admin@aidincharya.internal"
```

### Graceful Fallback When Unconfigured
If `VAPID_PUBLIC_KEY` or `VAPID_PRIVATE_KEY` are omitted or set to placeholders:
- The backend starts normally without exceptions.
- `GET /api/notifications/push/vapid-public-key` returns `{"configured": false, "public_key": null}`.
- The UI gracefully marks browser push as "Unconfigured" or "Off".
- Internal routine persistence and in-app notifications continue operating without disruption.

---

## 3. Database Schema & Storage

Web Push subscriptions are persisted in SQLite:

```sql
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_push_subs_user_id ON push_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_push_subs_endpoint ON push_subscriptions(endpoint);
```

### Database Helpers (`src/database/db.py`)
- `save_push_subscription(user_id, endpoint, p256dh, auth, user_agent)`
- `get_user_push_subscriptions(user_id)`
- `delete_user_push_subscription(user_id, endpoint)`
- `delete_push_subscription_by_endpoint(endpoint)`
- `get_user_push_status(user_id)`

---

## 4. API Endpoints

All push endpoints (except the public key retrieval and the service worker route) require Bearer token authentication:

| Endpoint | Method | Auth | Description |
| :--- | :--- | :--- | :--- |
| `/sw.js` | `GET` | Public | Serves `src/static/sw.js` with `Service-Worker-Allowed: /` header |
| `/api/notifications/push/vapid-public-key` | `GET` | Public | Returns server's public VAPID key |
| `/api/notifications/push/status` | `GET` | Authenticated | Returns subscription count and enabled status for current user |
| `/api/notifications/push/subscribe` | `POST` | Authenticated | Registers or updates a browser push subscription for current user |
| `/api/notifications/push/unsubscribe` | `POST` / `DELETE` | Authenticated | Revokes a subscription for current user |
| `/api/notifications/push/test` | `POST` | Authenticated | Sends a test push notification to user's registered devices |

---

## 5. Service Worker Implementation (`src/static/sw.js`)

The service worker is registered at the root scope `/` via `GET /sw.js`.

### Capabilities:
1. **Immediate Claiming:** Calls `self.skipWaiting()` on install and `clients.claim()` on activate.
2. **Safe JSON Parsing:** Safely falls back to text or default messages if the incoming push payload is malformed or unencrypted.
3. **Deduplication:** Applies a `tag` (e.g. `adaptation-confirmed-...` or `reminder-...`) and `renotify: true` so rapid updates replace previous notices rather than stacking clutter.
4. **Notification Click:** Closes notification, focuses an existing window if open, or opens a new window directed to `/routine`.

---

## 6. Frontend User Controls (`src/static/app.js` & `dashboard.html`)

Browser push is **strictly opt-in**. The user is never prompted for browser permission on page load.

### UI Locations:
1. **Dashboard Push Card (`dashboard.html`):** Displays current push status badge (`Active`, `Off`, `Blocked`, `Not Supported`) and action button (`Enable Browser Notifications` / `Disable Browser Notifications`).
2. **Notification Tray Drawer (`notifications-dropdown`):** A footer bar on all pages allows immediate push status visibility and one-click toggle.

### State Transitions:
- **Default/Off:** User clicks "Enable" -> Browser requests permission -> VAPID public key fetched -> Service Worker registered -> Subscription registered with backend -> UI transitions to "Active".
- **Active:** User clicks "Disable" -> `pushSubscription.unsubscribe()` called -> Backend subscription deleted -> UI transitions to "Off".
- **Blocked:** If permission is denied in browser settings, UI displays "Blocked" and disables buttons to avoid prompting repeatedly.
- **Unsupported:** If browser lacks `serviceWorker`, `PushManager`, or `Notification`, UI indicates "Not Supported".

---

## 7. Delivery Strategy, Retries, and Error Diagnostics

### Payload Constraints
- Web Push specifications limit payloads to 4096 bytes. AI Dincharya enforces a strict ceiling of **4000 bytes** (`MAX_PAYLOAD_BYTES`), truncating extended routine descriptions automatically.

### Transient vs Permanent Failures:
- **HTTP 404 / 410 (Gone / Not Found):** Indicates the browser unregistered the subscription or the push token expired. The service worker endpoint is immediately deleted from SQLite via `delete_push_subscription_by_endpoint()`.
- **HTTP 429 / 5xx / Timeouts:** Treated as transient. The service attempts bounded retries (up to 2 attempts) with linear backoff (0.3s * attempt) before returning failure.
- **Logging & Privacy:** Push endpoints are never logged in clear text; they are masked using SHA-256 digest prefixes (e.g. `endpoint:3f8a9b1c2d3e`).

---

## 8. Deployment & HTTPS Requirements

### Browser Security Constraints:
- **HTTPS Required:** Modern browsers (Chrome, Edge, Firefox, Safari) only permit Service Worker and PushManager APIs on secure contexts (`https://`), with `localhost` / `127.0.0.1` as the sole exception for local development.
- **Safari on macOS / iOS:** Requires macOS 13+ (Ventura) or iOS 16.4+ (added to Home Screen for iOS PWAs). Standard VAPID format supported.
- **Reverse Proxy Setup (Nginx / Caddy):** Ensure the reverse proxy forwards the Host header and preserves HTTPS scheme so WebSocket and Service Worker scopes remain valid.

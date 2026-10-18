/**
 * Service Worker for AI Dincharya (Web Push Notifications)
 * Handles:
 * - Installation and activation with immediate client claiming
 * - Push event handling with safe JSON parsing and fallback
 * - Deduplication via notification tags
 * - Secure click handling (focuses existing tab or opens /routine)
 * - Lock-screen privacy protection
 */

self.addEventListener('install', (event) => {
    // Activate immediately without waiting for existing tabs to close
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    // Claim control of all active clients immediately
    event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
    let payload = {};
    
    // Safely parse incoming push data
    if (event.data) {
        try {
            payload = event.data.json();
        } catch (e) {
            try {
                payload = { body: event.data.text() };
            } catch (err) {
                payload = {};
            }
        }
    }

    // Default safe fallbacks ensuring lock-screen privacy
    const title = payload.title || "Dinacharya AI";
    const body = payload.body || "Your daily Ayurvedic routine has been synchronized.";
    const icon = payload.icon || "/static/favicon.ico";
    const badge = payload.badge || icon;
    const tag = payload.tag || "dinacharya-notification";
    const targetUrl = (payload.data && payload.data.url) ? payload.data.url : "/routine";

    const options = {
        body: body,
        icon: icon,
        badge: badge,
        tag: tag, // Deduplicates visible notifications with same tag
        renotify: true,
        data: {
            url: targetUrl,
            timestamp: Date.now()
        }
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();

    const targetUrl = (event.notification.data && event.notification.data.url) 
        ? event.notification.data.url 
        : "/routine";

    // Focus existing window if open, otherwise open a new window
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (let i = 0; i < clientList.length; i++) {
                const client = clientList[i];
                if ('focus' in client) {
                    if (client.url.includes(targetUrl) || client.url.includes(self.registration.scope)) {
                        return client.focus();
                    }
                }
            }
            if (self.clients.openWindow) {
                return self.clients.openWindow(targetUrl);
            }
        })
    );
});

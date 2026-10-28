// app.js - Dinacharya AI Frontend Logic

const API_BASE = '/api';

// --- HTML Escaping Helper ---
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
window.escapeHtml = escapeHtml;

// --- Upcoming Time Slot Helper ---
function isSlotUpcoming(slotStr, bufferMinutes = 15) {
    if (!slotStr || typeof slotStr !== 'string') return false;
    const match = slotStr.match(/(\d{1,2}):(\d{2})/);
    if (!match) return false;
    const startHour = parseInt(match[1], 10);
    const startMin = parseInt(match[2], 10);
    const startTotalMin = startHour * 60 + startMin;

    const now = new Date();
    const currentTotalMin = now.getHours() * 60 + now.getMinutes();

    return (startTotalMin - currentTotalMin) > bufferMinutes;
}
window.isSlotUpcoming = isSlotUpcoming;


// --- Global Styles ---
const style = document.createElement('style');
style.innerHTML = `
    .typing-dot { width: 6px; height: 6px; background: #3e6750; border-radius: 50%; animation: typing 1s infinite ease-in-out; display: inline-block; margin: 0 2px; }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typing { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
    
    .timeline-card-content { max-height: 0; overflow: hidden; transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1); opacity: 0; }
    .timeline-card.expanded .timeline-card-content { max-height: 1200px; opacity: 1; margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid rgba(193, 200, 193, 0.3); }
    .timeline-card.expanded .expand-icon { transform: rotate(180deg); }
    .expand-icon { transition: transform 0.4s ease; }

    .flowchart-node { border-left: 4px solid #3e6750; transform: translateX(-20px); opacity: 0; animation: slideInNode 0.6s forwards; }
    @keyframes slideInNode { to { transform: translateX(0); opacity: 1; } }
    
    .message-entrance { animation: slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
    @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    
    .planning-pulse { animation: plannerWork 2s infinite ease-in-out; }
    @keyframes plannerWork { 0% { opacity: 0.4; } 50% { opacity: 1; color: #8fba9f; } 100% { opacity: 0.4; } }
`;
document.head.appendChild(style);

// --- Auth & API ---
function getToken() { return localStorage.getItem('dinacharya_token'); }
function setToken(t) { localStorage.setItem('dinacharya_token', t); }
async function logout() { 
    try {
        const token = getToken();
        if (token) {
            await fetch('/api/auth/logout', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
        }
    } catch(e) { console.warn("Logout error:", e); }
    localStorage.removeItem('dinacharya_token'); 
    sessionStorage.clear(); 
    window.location.href = '/'; 
}

// --- Notifications Inbox & UI ---
async function initNotifications() {
    const notifBtn = document.getElementById('nav-notifications-btn') || document.querySelector('button[aria-label="Notifications"]');
    if (!notifBtn) return;

    // Create badge if not present
    let badge = document.getElementById('nav-notification-badge');
    if (!badge) {
        badge = document.createElement('span');
        badge.id = 'nav-notification-badge';
        badge.className = 'hidden absolute -top-1 -right-1 bg-red-600 text-white text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center';
        notifBtn.classList.add('relative');
        notifBtn.appendChild(badge);
    }

    // Modal / Dropdown container
    let dropdown = document.getElementById('notifications-dropdown');
    if (!dropdown) {
        dropdown = document.createElement('div');
        dropdown.id = 'notifications-dropdown';
        dropdown.className = 'hidden fixed top-20 right-8 md:right-16 w-80 md:w-96 bg-white rounded-2xl shadow-2xl border border-gray-100 z-[120] overflow-hidden message-entrance';
        dropdown.innerHTML = `
            <div class="p-4 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
                <div class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-primary text-xl">notifications</span>
                    <h3 class="font-bold text-gray-800 text-sm">Notifications</h3>
                </div>
                <button id="close-notif-dropdown" class="text-gray-400 hover:text-gray-600 text-sm font-semibold">✕</button>
            </div>
            <div id="notifications-list" class="max-h-80 overflow-y-auto divide-y divide-gray-50 p-2">
                <div class="p-6 text-center text-gray-400 text-sm">Loading notifications...</div>
            </div>
            <div class="px-4 py-3 bg-gray-50 border-t border-gray-100 flex items-center justify-between text-xs">
                <div class="flex items-center gap-1.5">
                    <span class="material-symbols-outlined text-sm text-primary">circle_notifications</span>
                    <span class="text-gray-700 font-semibold">Browser Push</span>
                    <span id="notif-dropdown-push-badge" class="text-[10px] px-2 py-0.5 rounded font-bold bg-gray-200 text-gray-600">Off</span>
                </div>
                <button id="notif-dropdown-push-toggle" class="text-primary hover:underline font-bold text-[11px]">Enable</button>
            </div>
        `;
        document.body.appendChild(dropdown);

        document.getElementById('close-notif-dropdown').onclick = () => {
            dropdown.classList.add('hidden');
        };

        const dropBtn = document.getElementById('notif-dropdown-push-toggle');
        if (dropBtn) {
            dropBtn.onclick = (e) => {
                e.stopPropagation();
                toggleWebPush();
            };
        }

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (!dropdown.contains(e.target) && !notifBtn.contains(e.target)) {
                dropdown.classList.add('hidden');
            }
        });
    }

    // Function to load and render notifications
    async function loadNotifications() {
        const res = await authenticatedFetch(`${API_BASE}/notifications?limit=15`);
        if (!res || !res.ok) return;
        const data = await res.json();
        const notifs = data.notifications || [];
        const unreadCount = data.unread_count || notifs.filter(n => !n.is_read).length;

        if (unreadCount > 0) {
            badge.innerText = unreadCount > 9 ? '9+' : unreadCount;
            badge.classList.remove('hidden');
        } else {
            badge.classList.add('hidden');
        }

        const listContainer = document.getElementById('notifications-list');
        if (!listContainer) return;

        if (notifs.length === 0) {
            listContainer.innerHTML = `
                <div class="p-8 text-center text-gray-400 text-sm">
                    <span class="material-symbols-outlined text-3xl mb-2 text-gray-300 block">notifications_off</span>
                    No notifications yet.
                </div>
            `;
            return;
        }

        listContainer.innerHTML = notifs.map(n => `
            <div class="p-3.5 rounded-xl transition-colors ${n.is_read ? 'opacity-70 bg-white' : 'bg-primary/5'} hover:bg-gray-50 flex items-start justify-between gap-3 my-1">
                <div class="flex-1">
                    <div class="flex items-center gap-1.5 mb-1">
                        <span class="text-xs font-bold uppercase tracking-wider ${n.severity === 'warning' ? 'text-amber-600' : 'text-primary'}">${n.event_type.replace('_', ' ')}</span>
                        ${!n.is_read ? '<span class="w-1.5 h-1.5 bg-primary rounded-full"></span>' : ''}
                    </div>
                    <p class="text-xs text-gray-700 leading-relaxed">${n.message}</p>
                    <span class="text-[10px] text-gray-400 mt-1 block">${n.created_at || 'Just now'}</span>
                </div>
                ${!n.is_read ? `
                    <button data-notif-id="${n.id}" class="mark-read-btn text-[11px] font-semibold text-primary hover:underline self-center shrink-0">
                        Mark read
                    </button>
                ` : ''}
            </div>
        `).join('');

        // Wire mark as read buttons
        listContainer.querySelectorAll('.mark-read-btn').forEach(btn => {
            btn.onclick = async (e) => {
                e.stopPropagation();
                const nid = btn.getAttribute('data-notif-id');
                const mRes = await authenticatedFetch(`${API_BASE}/notifications/${nid}/read`, { method: 'POST' });
                if (mRes && mRes.ok) {
                    loadNotifications();
                }
            };
        });
    }

    // Toggle dropdown
    notifBtn.onclick = (e) => {
        e.stopPropagation();
        dropdown.classList.toggle('hidden');
        if (!dropdown.classList.contains('hidden')) {
            loadNotifications();
            renderWebPushControls();
        }
    };

    // Initial badge check
    loadNotifications();
}

// --- Web Push Notifications Subsystem ---
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
        .replace(/-/g, '+')
        .replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

let webPushState = {
    supported: false,
    permission: 'default',
    subscribed: false,
    loading: false,
    swRegistration: null
};

function renderWebPushControls() {
    const dashBadge = document.getElementById('dashboard-push-badge');
    const dashBtn = document.getElementById('dashboard-push-toggle-btn');
    const dropBadge = document.getElementById('notif-dropdown-push-badge');
    const dropBtn = document.getElementById('notif-dropdown-push-toggle');

    if (!webPushState.supported) {
        if (dashBadge) {
            dashBadge.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-gray-100 text-gray-500';
            dashBadge.innerText = 'Not Supported';
        }
        if (dashBtn) {
            dashBtn.disabled = true;
            dashBtn.className = 'w-full py-2.5 px-4 rounded-xl font-label-md text-xs font-bold bg-gray-100 text-gray-400 cursor-not-allowed';
            dashBtn.innerText = 'Browser Not Supported';
        }
        if (dropBadge) {
            dropBadge.className = 'text-[10px] px-1.5 py-0.5 rounded font-semibold bg-gray-100 text-gray-400';
            dropBadge.innerText = 'Unsupported';
        }
        if (dropBtn) {
            dropBtn.disabled = true;
            dropBtn.className = 'text-gray-400 font-bold text-[11px] cursor-not-allowed';
            dropBtn.innerText = 'Unavailable';
        }
        return;
    }

    if (webPushState.permission === 'denied') {
        if (dashBadge) {
            dashBadge.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-red-100 text-red-700';
            dashBadge.innerText = 'Blocked';
        }
        if (dashBtn) {
            dashBtn.disabled = true;
            dashBtn.className = 'w-full py-2.5 px-4 rounded-xl font-label-md text-xs font-bold bg-gray-100 text-gray-500 cursor-not-allowed';
            dashBtn.innerText = 'Notifications Blocked in Settings';
        }
        if (dropBadge) {
            dropBadge.className = 'text-[10px] px-1.5 py-0.5 rounded font-semibold bg-red-100 text-red-600';
            dropBadge.innerText = 'Blocked';
        }
        if (dropBtn) {
            dropBtn.disabled = true;
            dropBtn.className = 'text-gray-400 font-bold text-[11px] cursor-not-allowed';
            dropBtn.innerText = 'Blocked';
        }
        return;
    }

    if (webPushState.subscribed) {
        if (dashBadge) {
            dashBadge.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800';
            dashBadge.innerText = 'Active';
        }
        if (dashBtn) {
            dashBtn.disabled = webPushState.loading;
            dashBtn.className = 'w-full py-2.5 px-4 rounded-xl font-label-md text-xs font-bold transition-all border border-gray-200 text-gray-700 hover:bg-gray-100';
            dashBtn.innerText = webPushState.loading ? 'Updating...' : 'Disable Browser Notifications';
        }
        if (dropBadge) {
            dropBadge.className = 'text-[10px] px-1.5 py-0.5 rounded font-semibold bg-emerald-100 text-emerald-700';
            dropBadge.innerText = 'Active';
        }
        if (dropBtn) {
            dropBtn.disabled = webPushState.loading;
            dropBtn.className = 'text-gray-600 hover:text-red-600 font-bold text-[11px]';
            dropBtn.innerText = webPushState.loading ? '...' : 'Disable';
        }
    } else {
        if (dashBadge) {
            dashBadge.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-gray-100 text-gray-600';
            dashBadge.innerText = 'Off';
        }
        if (dashBtn) {
            dashBtn.disabled = webPushState.loading;
            dashBtn.className = 'w-full py-2.5 px-4 rounded-xl font-label-md text-xs font-bold transition-all bg-primary/10 text-primary hover:bg-primary hover:text-white';
            dashBtn.innerText = webPushState.loading ? 'Enabling...' : 'Enable Browser Notifications';
        }
        if (dropBadge) {
            dropBadge.className = 'text-[10px] px-1.5 py-0.5 rounded font-semibold bg-gray-100 text-gray-600';
            dropBadge.innerText = 'Off';
        }
        if (dropBtn) {
            dropBtn.disabled = webPushState.loading;
            dropBtn.className = 'text-primary hover:underline font-bold text-[11px]';
            dropBtn.innerText = webPushState.loading ? '...' : 'Enable';
        }
    }
}

async function checkWebPushStatus() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
        webPushState.supported = false;
        renderWebPushControls();
        return;
    }
    webPushState.supported = true;
    webPushState.permission = Notification.permission;

    try {
        const reg = await navigator.serviceWorker.getRegistration('/sw.js');
        webPushState.swRegistration = reg;
        if (reg) {
            const sub = await reg.pushManager.getSubscription();
            webPushState.subscribed = !!sub;
        } else {
            webPushState.subscribed = false;
        }
    } catch (e) {
        console.warn("Could not check local PushManager subscription:", e);
    }
    renderWebPushControls();
}

async function toggleWebPush() {
    if (webPushState.loading) return;
    if (!webPushState.supported) {
        showToast("Web Push is not supported in this browser.");
        return;
    }

    if (webPushState.subscribed) {
        // Unsubscribe
        webPushState.loading = true;
        renderWebPushControls();
        try {
            if (webPushState.swRegistration) {
                const sub = await webPushState.swRegistration.pushManager.getSubscription();
                if (sub) {
                    await sub.unsubscribe();
                    await authenticatedFetch(`${API_BASE}/notifications/push/unsubscribe`, {
                        method: 'POST',
                        body: JSON.stringify({ endpoint: sub.endpoint })
                    });
                }
            }
            webPushState.subscribed = false;
            showToast("✓ Browser notifications disabled.");
        } catch (e) {
            console.error("Unsubscribe error:", e);
            showToast("Failed to disable notifications.");
        } finally {
            webPushState.loading = false;
            renderWebPushControls();
        }
    } else {
        // Subscribe
        webPushState.loading = true;
        renderWebPushControls();
        try {
            // Request permission explicitly only on click
            const perm = await Notification.requestPermission();
            webPushState.permission = perm;
            if (perm !== 'granted') {
                showToast("Notification permission was not granted.");
                webPushState.loading = false;
                renderWebPushControls();
                return;
            }

            // Fetch public VAPID key
            const keyRes = await authenticatedFetch(`${API_BASE}/notifications/push/vapid-public-key`);
            if (!keyRes || !keyRes.ok) {
                showToast("Push notification server is currently unavailable.");
                webPushState.loading = false;
                renderWebPushControls();
                return;
            }
            const keyData = await keyRes.json();
            if (!keyData.configured || !keyData.public_key) {
                showToast("Push notifications are not configured on this server.");
                webPushState.loading = false;
                renderWebPushControls();
                return;
            }

            // Register service worker if needed
            let reg = webPushState.swRegistration;
            if (!reg) {
                reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
                webPushState.swRegistration = reg;
            }
            await navigator.serviceWorker.ready;

            // Subscribe via PushManager
            const convertedKey = urlBase64ToUint8Array(keyData.public_key);
            const subscription = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: convertedKey
            });

            const subJson = subscription.toJSON();
            const rawP256dh = subscription.getKey ? subscription.getKey('p256dh') : null;
            const rawAuth = subscription.getKey ? subscription.getKey('auth') : null;
            const p256dhStr = subJson.keys?.p256dh || (rawP256dh ? btoa(String.fromCharCode.apply(null, new Uint8Array(rawP256dh))) : '');
            const authStr = subJson.keys?.auth || (rawAuth ? btoa(String.fromCharCode.apply(null, new Uint8Array(rawAuth))) : '');

            const regRes = await authenticatedFetch(`${API_BASE}/notifications/push/subscribe`, {
                method: 'POST',
                body: JSON.stringify({
                    endpoint: subscription.endpoint,
                    keys: {
                        p256dh: p256dhStr,
                        auth: authStr
                    },
                    p256dh: p256dhStr,
                    auth: authStr,
                    user_agent: navigator.userAgent
                })
            });

            if (regRes && regRes.ok) {
                webPushState.subscribed = true;
                showToast("✓ Browser push notifications enabled!");
            } else {
                showToast("Failed to register subscription with server.");
                await subscription.unsubscribe();
            }
        } catch (e) {
            console.error("Push subscribe error:", e);
            showToast("Failed to enable notifications: " + (e.message || "Unknown error"));
        } finally {
            webPushState.loading = false;
            renderWebPushControls();
        }
    }
}

function initWebPush() {
    const dashBtn = document.getElementById('dashboard-push-toggle-btn');
    if (dashBtn) {
        dashBtn.onclick = (e) => {
            e.preventDefault();
            toggleWebPush();
        };
    }
    checkWebPushStatus();
}

async function authenticatedFetch(url, options = {}, timeoutMs = 35000) {
    const token = getToken();
    if (!token && !url.includes('/auth/')) { window.location.href = '/login'; return null; }
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await fetch(url, { ...options, headers, signal: controller.signal });
        clearTimeout(timer);
        if (res.status === 401) { logout(); return null; }
        return res;
    } catch(e) { 
        clearTimeout(timer);
        if (e.name === 'AbortError') {
            console.error(`Request to ${url} timed out after ${timeoutMs}ms`);
        } else {
            console.error("Fetch failed:", e);
        }
        return null; 
    }
}

// --- Hybrid Caching Layer ---
let latestScheduleVersion = 0;

async function getSchedule(forceRefresh = false) {
    const currentVersion = ++latestScheduleVersion;
    const now = Date.now();
    const CACHE_DURATION = 10 * 60 * 1000; 

    // Always fetch fresh schedule on routine page or when forceRefresh is requested
    const isRoutinePage = window.location.pathname.includes('/routine');
    const cachedString = !isRoutinePage ? sessionStorage.getItem('schedule_cache') : null;
    let cache = null;
    try { if(cachedString) cache = JSON.parse(cachedString); } catch(e) {}
    if (!forceRefresh && !isRoutinePage && cache && cache.data && (now - cache.timestamp < CACHE_DURATION)) {
        const s = cache.data.schedule || cache.data;
        if (s && (s.morning_block || s.midday_block || s.evening_block || (s.schedule && s.schedule.morning_block))) {
            return cache.data;
        }
    }

    // Fast-path: Check if there is already a valid persisted schedule in the vault
    try {
        const currentRes = await authenticatedFetch(`${API_BASE}/schedule/current`);
        if (currentRes && currentRes.ok) {
            const currentData = await currentRes.json();
            const s = currentData ? (currentData.schedule || currentData) : null;
            if (s && (s.morning_block || s.midday_block || s.evening_block || (s.schedule && s.schedule.morning_block))) {
                if (currentVersion === latestScheduleVersion) {
                    sessionStorage.setItem('schedule_cache', JSON.stringify({ data: currentData, timestamp: now }));
                }
                return currentData;
            }
        }
    } catch (err) {
        console.warn("Fast-path schedule fetch failed, falling back to generate:", err);
    }

    const simulateFever = sessionStorage.getItem('simulate_fever') === 'true';
    const telemetry = simulateFever ? { body_temp_c: 38.5 } : {};
    const symptoms = simulateFever ? ["Active fever"] : [];

    const res = await authenticatedFetch(`${API_BASE}/schedule/generate`, { 
        method: 'POST', 
        body: JSON.stringify({ 
            user_id: "current", 
            force_regen: forceRefresh,
            context: { season: "Hemanta", weather: "Cold", temperature_c: 10.0, calendar_events: [], self_report_symptoms: symptoms },
            wearable_telemetry_7d: telemetry
        }) 
    });
    if (!res) return null;
    const data = await res.json();
    if (currentVersion === latestScheduleVersion) {
        sessionStorage.setItem('schedule_cache', JSON.stringify({ data: data, timestamp: now }));
    }
    return data;
}

// --- UI Helpers ---
function showToast(m) {
    const t = document.createElement('div');
    t.className = 'fixed bottom-8 left-1/2 -translate-x-1/2 z-[100] bg-primary text-on-primary px-8 py-4 rounded-3xl shadow-2xl text-sm font-bold border border-white/10 animate-fade-in-up';
    t.innerText = m;
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateY(20px)'; setTimeout(() => t.remove(), 400); }, 3500);
}

function formatUserText(text) {
    if (!text) return "";
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>');
}

function parseMarkdownTable(tableBlock) {
    const lines = tableBlock.trim().split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length < 2) return tableBlock;

    // Locate the separator row (e.g. |---|---| or |--|--|)
    let separatorIndex = -1;
    for (let i = 0; i < Math.min(lines.length, 3); i++) {
        const cleaned = lines[i].replace(/^\||\|$/g, '').trim();
        const parts = cleaned.split('|').map(p => p.trim());
        if (parts.length > 0 && parts.every(p => /^:?-+:?$/.test(p))) {
            separatorIndex = i;
            break;
        }
    }

    if (separatorIndex === -1) {
        return tableBlock;
    }

    // Determine column alignments from separator
    const sepLine = lines[separatorIndex].replace(/^\||\|$/g, '').trim();
    const alignments = sepLine.split('|').map(p => {
        p = p.trim();
        const left = p.startsWith(':');
        const right = p.endsWith(':');
        if (left && right) return 'center';
        if (right) return 'right';
        return 'left';
    });

    const headerLines = lines.slice(0, separatorIndex);
    const bodyLines = lines.slice(separatorIndex + 1);

    const splitRow = (line) => {
        let clean = line.trim();
        if (clean.startsWith('|')) clean = clean.substring(1);
        if (clean.endsWith('|')) clean = clean.substring(0, clean.length - 1);
        return clean.split('|').map(c => c.trim());
    };

    let theadHtml = '';
    if (headerLines.length > 0) {
        theadHtml = '<thead class="bg-surface-container-high/70 text-primary border-b border-outline-variant/30">';
        headerLines.forEach(hLine => {
            let cells = splitRow(hLine);
            while (cells.length < alignments.length) cells.push('');
            if (cells.length > alignments.length) cells = cells.slice(0, alignments.length);

            theadHtml += '<tr>';
            cells.forEach((cell, idx) => {
                const align = alignments[idx] || 'left';
                const alignClass = align === 'center' ? 'text-center' : (align === 'right' ? 'text-right' : 'text-left');
                theadHtml += `<th class="py-2.5 px-3.5 font-bold tracking-wide ${alignClass}">${cell || '&nbsp;'}</th>`;
            });
            theadHtml += '</tr>';
        });
        theadHtml += '</thead>';
    }

    let tbodyHtml = '<tbody class="divide-y divide-outline-variant/15 text-on-surface font-normal">';
    bodyLines.forEach(bLine => {
        let cells = splitRow(bLine);
        while (cells.length < alignments.length) cells.push('');
        if (cells.length > alignments.length) cells = cells.slice(0, alignments.length);

        tbodyHtml += '<tr class="hover:bg-surface-container-low/50 transition-colors">';
        cells.forEach((cell, idx) => {
            const align = alignments[idx] || 'left';
            const alignClass = align === 'center' ? 'text-center' : (align === 'right' ? 'text-right' : 'text-left');
            tbodyHtml += `<td class="py-2.5 px-3.5 leading-relaxed align-top ${alignClass}">${cell || '&nbsp;'}</td>`;
        });
        tbodyHtml += '</tr>';
    });
    tbodyHtml += '</tbody>';

    return `<div class="chat-table-wrapper my-4 overflow-x-auto rounded-xl border border-outline-variant/30 shadow-sm bg-white"><table class="min-w-full text-sm border-collapse">${theadHtml}${tbodyHtml}</table></div>`;
}

function formatAIText(text) {
    if (!text) return "";
    
    // Normalize newlines
    let src = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    // 1. Escape HTML special characters for safety (preserving markdown syntax)
    src = src.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    // Restore markdown blockquote symbol
    src = src.replace(/^&gt;\s?(.*)$/gm, '> $1');

    // 2. Pre-formatted code blocks ```...```
    src = src.replace(/```([\s\S]*?)```/g, (m, code) => {
        return `<pre class="bg-surface-container-highest/80 text-on-surface text-xs p-3 rounded-xl my-2 overflow-x-auto font-mono border border-outline-variant/30"><code>${code.trim()}</code></pre>`;
    });

    // 3. Inline Code `code`
    src = src.replace(/`([^`]+)`/g, '<code class="bg-surface-container-high text-primary px-1.5 py-0.5 rounded text-xs font-mono font-medium border border-outline-variant/30">$1</code>');

    // 4. Horizontal Rule
    src = src.replace(/^---$/gm, '<hr class="my-3 border-outline-variant/30" />');

    // 5. Headings
    src = src.replace(/^#### (.*$)/gm, '<h5 class="text-xs font-bold uppercase tracking-wider text-secondary mt-3 mb-1">$1</h5>');
    src = src.replace(/^### (.*$)/gm, '<h4 class="text-base font-bold text-primary mt-3.5 mb-1.5 flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-secondary inline-block flex-shrink-0"></span><span>$1</span></h4>');
    src = src.replace(/^## (.*$)/gm, '<h3 class="text-lg font-bold font-headline-md text-primary mt-4 mb-2 pb-1 border-b border-outline-variant/20">$1</h3>');
    src = src.replace(/^# (.*$)/gm, '<h2 class="text-xl font-bold font-headline-md text-primary mt-4 mb-2 pb-1 border-b border-outline-variant/30">$1</h2>');

    // 6. Blockquotes (> ...)
    src = src.replace(/(?:^> (?:.*)(?:\n|$))+/gm, (match) => {
        const lines = match.trim().split('\n').map(l => l.replace(/^> ?/, '')).join('<br>');
        return `<blockquote class="border-l-4 border-secondary/60 bg-surface-container-low/60 px-4 py-2 my-2.5 rounded-r-xl italic text-on-surface-variant font-serif text-sm">${lines}</blockquote>`;
    });

    // 7. Bold and Italic
    src = src.replace(/\*\*(.*?)\*\*/g, '<strong class="font-bold text-primary">$1</strong>');
    src = src.replace(/__(.*?)__/g, '<strong class="font-bold text-primary">$1</strong>');
    src = src.replace(/\*(.*?)\*/g, '<em class="italic text-secondary">$1</em>');
    src = src.replace(/_([^_]+)_/g, '<em class="italic text-secondary">$1</em>');

    // 8. Markdown Tables
    src = src.replace(/(?:^.*\|.*$\n?)+/gm, (tableBlock) => {
        if (/\n?\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*(?:\n|$)/.test(tableBlock)) {
            return '\n\n' + parseMarkdownTable(tableBlock) + '\n\n';
        }
        return tableBlock;
    });

    // 9. Ordered Lists (group consecutive numbered items into an <ol>)
    src = src.replace(/(?:^\d+\.\s+(?:.*)(?:\n|$))+/gm, (match) => {
        const items = match.trim().split('\n').map(line => {
            const content = line.replace(/^\d+\.\s+/, '').trim();
            return `<li class="ml-4 pl-1 mb-1 leading-relaxed">${content}</li>`;
        }).join('');
        return `<ol class="list-decimal pl-2 my-2 space-y-1 marker:text-secondary marker:font-semibold">${items}</ol>`;
    });

    // 10. Unordered Lists (group consecutive bullet items into a <ul>)
    src = src.replace(/(?:^[-*]\s+(?:.*)(?:\n|$))+/gm, (match) => {
        const items = match.trim().split('\n').map(line => {
            const content = line.replace(/^[-*]\s+/, '').trim();
            return `<li class="ml-4 pl-1 mb-1 leading-relaxed">${content}</li>`;
        }).join('');
        return `<ul class="list-disc pl-2 my-2 space-y-1 marker:text-secondary">${items}</ul>`;
    });

    // 11. Callout Highlights
    src = src.replace(/^((?:✓|💡|⚠️|Namaste).*?(?:Schedule Synchronized|Synchronized|Vault|Approval confirmed).*)$/gim,
        '<div class="chat-callout-card flex items-start gap-2.5"><div>$1</div></div>');

    // 12. Paragraphs (split by double newlines)
    const blocks = src.split(/\n{2,}/);
    const formattedBlocks = blocks.map(block => {
        block = block.trim();
        if (!block) return '';
        // If block already begins with an HTML block element, don't wrap in <p>
        if (/^<(h[2-5]|ul|ol|blockquote|pre|hr|div|table)/i.test(block)) {
            return block;
        }
        const inlineBreaks = block.replace(/\n/g, '<br>');
        return `<p class="mb-2.5 last:mb-0 leading-relaxed">${inlineBreaks}</p>`;
    });

    return formattedBlocks.filter(Boolean).join('');
}

// --- Messaging & Animations ---

async function typeMessage(container, text, role='assistant') {
    if (!container) return;
    const div = document.createElement('div');
    const isUser = role === 'user';
    div.className = `flex gap-4 max-w-3xl ${isUser ? 'ml-auto flex-row-reverse' : ''} message-entrance mb-8`;
    const icon = isUser ? 'person' : 'psychology_alt';
    const bg = isUser ? 'bg-primary text-on-primary shadow-lg' : 'bg-white text-on-surface border border-outline-variant/10 shadow-sm';
    div.innerHTML = `
        <div class="w-10 h-10 rounded-xl ${isUser ? 'bg-surface-container-highest' : 'bg-primary'} flex items-center justify-center flex-shrink-0 shadow-md">
            <span class="material-symbols-outlined ${isUser ? 'text-on-surface-variant' : 'text-on-primary'} text-[22px]">${icon}</span>
        </div>
        <div class="${bg} p-6 rounded-[1.5rem] ${isUser ? 'rounded-tr-none' : 'rounded-tl-none'} shadow-sm flex-1 min-w-0">
            <div class="chat-message-content ${isUser ? 'chat-user-message' : ''}"></div>
        </div>
    `;
    container.appendChild(div);
    const bodyEl = div.querySelector('.chat-message-content');

    if (isUser) {
        bodyEl.innerHTML = formatUserText(text);
        container.scrollTop = container.scrollHeight;
        return;
    }

    const words = text.split(' ');
    let currentText = '';
    const delay = words.length > 80 ? 8 : 14;
    for (let i = 0; i < words.length; i++) {
        currentText += words[i] + ' ';
        bodyEl.innerHTML = formatAIText(currentText);
        container.scrollTop = container.scrollHeight;
        await new Promise(r => setTimeout(r, delay));
    }
    // Finalize with complete structured formatting
    bodyEl.innerHTML = formatAIText(text);
    container.scrollTop = container.scrollHeight;
}

async function renderChatMessage(container, role, text) {
    if (!container) return;
    const div = document.createElement('div');
    const isUser = role === 'user';
    div.className = `flex gap-4 max-w-3xl ${isUser ? 'ml-auto flex-row-reverse' : ''} mb-8`;
    const icon = isUser ? 'person' : 'psychology_alt';
    const bg = isUser ? 'bg-primary text-on-primary shadow-lg' : 'bg-white text-on-surface border border-outline-variant/10 shadow-sm';
    div.innerHTML = `
        <div class="w-10 h-10 rounded-xl ${isUser ? 'bg-surface-container-highest' : 'bg-primary'} flex items-center justify-center flex-shrink-0 shadow-md">
            <span class="material-symbols-outlined ${isUser ? 'text-on-surface-variant' : 'text-on-primary'} text-[22px]">${icon}</span>
        </div>
        <div class="${bg} p-6 rounded-[1.5rem] ${isUser ? 'rounded-tr-none' : 'rounded-tl-none'} shadow-sm flex-1 min-w-0">
            <div class="chat-message-content ${isUser ? 'chat-user-message' : ''}">
                ${isUser ? formatUserText(text) : formatAIText(text)}
            </div>
        </div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function createTypingIndicator() {
    const div = document.createElement('div');
    div.id = 'typing-indicator';
    div.className = 'flex gap-4 max-w-3xl message-entrance mb-8 w-full';
    div.innerHTML = `
        <div class="w-10 h-10 rounded-xl bg-primary flex items-center justify-center flex-shrink-0 shadow-md">
            <span class="material-symbols-outlined text-on-primary text-[22px] ai-pulse">psychology_alt</span>
        </div>
        <div class="bg-white p-5 rounded-[1.5rem] rounded-tl-none shadow-md border border-outline-variant/20 flex-1 min-w-0">
            <div class="flex items-center justify-between mb-2 pb-2 border-b border-outline-variant/10">
                <div class="flex items-center gap-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-secondary ai-pulse"></span>
                    <span class="text-xs font-bold uppercase tracking-wider text-primary">Vaidya Reasoning Engine Active</span>
                </div>
                <div class="flex items-center gap-1">
                    <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
                </div>
            </div>
            <div id="live-trace-steps" class="space-y-1.5 text-xs font-mono text-on-surface-variant">
                <div class="flex items-center gap-2 text-primary font-medium">
                    <span class="material-symbols-outlined text-[15px] text-secondary">explore</span>
                    <span>Analyzing clinical query, constitutional baseline & biometrics...</span>
                </div>
            </div>
        </div>
    `;
    return div;
}

function renderAgentTraceBlock(container, traceEvents) {
    if (!container || !traceEvents || traceEvents.length === 0) return;
    const traceDiv = document.createElement('div');
    traceDiv.className = 'w-full max-w-3xl mb-4 p-4 bg-surface-container-low border border-primary/20 rounded-2xl text-xs font-mono shadow-sm';

    let stepsHtml = '';
    traceEvents.forEach(evt => {
        if (evt.stage === 'understanding_question') {
            stepsHtml += `
                <div class="flex items-center gap-2 text-primary font-semibold">
                    <span class="text-secondary text-sm">✦</span>
                    <span>${escapeHtml(evt.message || 'Understanding context')}</span>
                </div>`;
        } else if (evt.stage === 'tool_call_start') {
            const toolTitle = evt.friendly_name || evt.tool;
            stepsHtml += `
                <div class="flex items-center gap-2 text-on-surface-variant pl-3">
                    <span class="text-secondary font-bold">▸</span>
                    <span class="font-bold text-primary">${escapeHtml(toolTitle)}</span>
                </div>`;
        } else if (evt.stage === 'tool_call_complete') {
            const isErr = evt.status === 'error';
            const icon = isErr ? '✗' : '✓';
            const color = isErr ? 'text-error' : 'text-secondary';
            const dur = evt.duration_ms ? `${evt.duration_ms}ms` : '';
            stepsHtml += `
                <div class="flex items-center justify-between pl-6 py-0.5 ${color}">
                    <span>${icon} ${escapeHtml(evt.summary || 'Completed')}</span>
                    <span class="opacity-60 text-[10px] font-mono">${dur}</span>
                </div>`;
        } else if (evt.stage === 'preparing_response') {
            stepsHtml += `
                <div class="flex items-center gap-2 text-primary font-semibold pt-1">
                    <span class="text-secondary text-sm">✦</span>
                    <span>${escapeHtml(evt.message || 'Synthesizing response')}</span>
                </div>`;
        }
    });

    const toolCallsCount = traceEvents.filter(e => e.stage === 'tool_call_start').length;

    traceDiv.innerHTML = `
        <details class="group cursor-pointer" open>
            <summary class="flex items-center justify-between font-bold text-primary text-xs uppercase tracking-wider select-none list-none">
                <span class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-sm text-secondary">insights</span>
                    Agent Activity Trace (${toolCallsCount} dynamic tool operations)
                </span>
                <span class="material-symbols-outlined text-sm group-open:rotate-180 transition-transform">expand_more</span>
            </summary>
            <div class="mt-3 pt-3 border-t border-outline-variant/20 space-y-1.5">
                ${stepsHtml}
            </div>
        </details>
    `;
    container.appendChild(traceDiv);
    container.scrollTop = container.scrollHeight;
}

// --- Recalibration Flowchart ---
// --- Recalibration Flowchart & Canonical Proposal Card ---
async function showRecalibrationFlowchart(proposedSchedule, proposal = null) {
    const chatHistory = document.getElementById('reasoning-chat-history');
    if (!chatHistory) return;
    
    const analyzingDiv = document.createElement('div');
    analyzingDiv.className = 'w-full max-w-xl mx-auto my-6 p-6 text-center animate-fade-in';
    analyzingDiv.innerHTML = `<div class="flex flex-col items-center gap-4"><span class="material-symbols-outlined text-4xl planning-pulse">hub</span><p class="font-bold text-primary tracking-widest uppercase text-xs">Planner Agent: recalibrating temporal nodes...</p></div>`;
    chatHistory.appendChild(analyzingDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    await new Promise(r => setTimeout(r, 1200));
    analyzingDiv.remove();

    const targetPractice = proposal ? proposal.target_practice : null;
    const origSlot = proposal ? (proposal.original_time_slot || 'Flexible') : null;
    const proposedSlot = proposal ? proposal.proposed_time_slot : null;
    const rationale = proposal ? (proposal.rationale || '') : '';
    const explanation = proposal ? (proposal.clinical_explanation || '') : '';

    const flowDiv = document.createElement('div');
    flowDiv.className = 'w-full max-w-2xl mx-auto my-10 p-8 glass-card bg-surface-container-low/40 border border-primary/20 rounded-[2.5rem] shadow-2xl animate-fade-in relative overflow-hidden';
    
    let proposalHeaderHtml = '';
    if (proposal) {
        proposalHeaderHtml = `
            <div id="canonical-proposal-card" class="mb-8 p-6 bg-white/95 rounded-3xl border border-primary/25 shadow-lg">
                <div class="flex items-center justify-between mb-4">
                    <span class="text-xs uppercase font-extrabold tracking-wider text-primary flex items-center gap-1.5">
                        <span class="material-symbols-outlined text-sm">schedule_send</span>
                        Canonical Schedule Proposal
                    </span>
                    <span id="proposal-status-badge" class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-900 border border-amber-300">
                        Pending Confirmation
                    </span>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                    <div class="p-3 bg-surface-container-low/70 rounded-2xl border border-outline/10">
                        <p class="text-[11px] text-on-surface-variant font-medium uppercase tracking-wider">Practice</p>
                        <p class="font-bold text-lg text-on-surface mt-0.5">${targetPractice}</p>
                    </div>
                    <div class="p-3 bg-surface-container-low/70 rounded-2xl border border-outline/10">
                        <p class="text-[11px] text-on-surface-variant font-medium uppercase tracking-wider">Time Slot Shift</p>
                        <div class="flex items-center gap-2 mt-1">
                            <span class="line-through text-slate-400 font-semibold text-sm">${origSlot}</span>
                            <span class="material-symbols-outlined text-xs text-primary">arrow_forward</span>
                            <span class="text-primary font-bold text-lg bg-primary/10 px-2 py-0.5 rounded-lg border border-primary/20">${proposedSlot}</span>
                        </div>
                    </div>
                </div>
                ${rationale ? `<div class="mb-2 text-sm text-on-surface"><span class="font-bold text-primary">Recommendation:</span> ${rationale}</div>` : ''}
                ${explanation ? `<div class="text-xs text-on-surface-variant bg-primary/5 p-3 rounded-xl border border-primary/10 mt-2 leading-relaxed"><span class="font-bold text-primary">Constraint & Safety:</span> ${explanation}</div>` : ''}
                <div id="proposal-error-banner" class="hidden mt-3 p-3 bg-error/10 border border-error/30 text-error rounded-xl text-xs font-semibold"></div>
            </div>
        `;
    }

    flowDiv.innerHTML = `<div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary/0 via-primary/40 to-primary/0"></div>
        <h3 class="font-headline-md text-primary mb-6 text-center italic">Temporal Recalibration Protocol</h3>
        ${proposalHeaderHtml}
        <p class="text-xs font-bold text-on-surface-variant uppercase tracking-wider mb-4 px-2">Proposed Schedule Preview</p>
        <div class="space-y-0" id="flowchart-nodes-container"></div>
        <div id="recalc-actions" class="mt-8 flex gap-4 opacity-0 transition-opacity duration-700">
            <button id="cancel-recalc" class="flex-1 py-4 border-2 border-outline/20 rounded-2xl font-bold hover:bg-surface-variant/50 transition-all">Keep Current</button>
            <button id="confirm-recalc" class="flex-1 py-4 bg-primary text-on-primary rounded-2xl font-bold shadow-xl hover:scale-[1.02] active:scale-95 transition-all">Apply & Synchronize</button>
        </div>`;
    
    const nodeContainer = flowDiv.querySelector('#flowchart-nodes-container');
    const allNewTasks = [
        ...(proposedSchedule.morning_block || []), 
        ...(proposedSchedule.midday_block || []), 
        ...(proposedSchedule.evening_block || [])
    ];
    chatHistory.appendChild(flowDiv);
    
    for (let i = 0; i < allNewTasks.length; i++) {
        const task = allNewTasks[i];
        const isModifiedTarget = targetPractice && (
            task.name === targetPractice || 
            task.name.toLowerCase().includes(targetPractice.toLowerCase()) || 
            targetPractice.toLowerCase().includes(task.name.toLowerCase())
        );

        const node = document.createElement('div');
        node.style.animationDelay = `${i * 100}ms`;
        
        if (isModifiedTarget) {
            node.className = 'flowchart-node p-5 bg-primary/10 ring-2 ring-primary rounded-2xl mb-2 flex justify-between items-center border border-primary/30 shadow-md';
            node.innerHTML = `<div><p class="font-label-sm text-[11px] text-primary font-black uppercase tracking-wider mb-1"><span class="line-through opacity-50 mr-1.5">${origSlot}</span> → <span class="bg-primary text-white px-2 py-0.5 rounded">${task.time_slot}</span> <span class="text-[9px] bg-secondary text-on-secondary px-1.5 py-0.5 rounded ml-1 font-bold">PROPOSED</span></p><p class="font-bold text-primary text-lg">${task.name}</p></div><span class="material-symbols-outlined text-primary fill">published_with_changes</span>`;
        } else {
            node.className = 'flowchart-node p-5 bg-white shadow-md rounded-2xl mb-2 flex justify-between items-center border border-primary/5';
            node.innerHTML = `<div><p class="font-label-sm text-[10px] text-primary font-black uppercase tracking-tighter mb-1">${task.time_slot}</p><p class="font-bold text-on-surface text-lg">${task.name}</p></div><span class="material-symbols-outlined text-secondary fill">update</span>`;
        }
        
        nodeContainer.appendChild(node);
        if (i < allNewTasks.length - 1) {
            const line = document.createElement('div');
            line.className = 'w-[2px] bg-[#c1c8c1] ml-[19px] h-[20px]';
            nodeContainer.appendChild(line);
        }
        chatHistory.scrollTop = chatHistory.scrollHeight;
        if (i < 8) await new Promise(r => setTimeout(r, 120)); 
    }

    setTimeout(() => { flowDiv.querySelector('#recalc-actions').classList.replace('opacity-0', 'opacity-100'); }, 300);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    return new Promise((resolve) => {
        const confirmBtn = document.getElementById('confirm-recalc');
        const cancelBtn = document.getElementById('cancel-recalc');
        const statusBadge = document.getElementById('proposal-status-badge');
        const errorBanner = document.getElementById('proposal-error-banner');

        if (confirmBtn) confirmBtn.onclick = async () => {
            confirmBtn.disabled = true;
            cancelBtn.disabled = true;
            confirmBtn.innerHTML = `<span class="animate-pulse">Synchronizing...</span>`;

            let res;
            if (proposal && proposal.proposal_id) {
                res = await authenticatedFetch(`${API_BASE}/schedule/proposal/apply`, {
                    method: 'POST',
                    body: JSON.stringify({
                        proposal_id: proposal.proposal_id,
                        expected_schedule_version: proposal.schedule_version
                    })
                });
            } else {
                res = await authenticatedFetch(`${API_BASE}/schedule/confirm`, {
                    method: 'POST',
                    body: JSON.stringify({ schedule: proposedSchedule })
                });
            }

            if (res && res.ok) {
                const resData = await res.json();
                const savedSchedule = resData.schedule || proposedSchedule;

                if (statusBadge) {
                    statusBadge.className = 'px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-900 border border-emerald-300';
                    statusBadge.innerText = '✓ Synchronized & Locked';
                }

                sessionStorage.removeItem('schedule_cache');
                sessionStorage.setItem('schedule_cache', JSON.stringify({
                    data: { schedule: savedSchedule },
                    timestamp: Date.now()
                }));

                showToast(`✓ Vault Synchronized${targetPractice ? ': ' + targetPractice : ''}.`);
                loadDashboardData();
                loadRoutineData();

                setTimeout(() => {
                    flowDiv.remove();
                    resolve(true);
                }, 1200);
            } else {
                let errorMsg = "Synchronization could not be completed.";
                try {
                    const errJson = await res.json();
                    if (errJson && errJson.detail) errorMsg = errJson.detail;
                } catch(e) {}

                if (statusBadge) {
                    statusBadge.className = 'px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-900 border border-rose-300';
                    statusBadge.innerText = 'Sync Failed / Stale';
                }

                if (errorBanner) {
                    errorBanner.innerText = `Change not applied: ${errorMsg}. Your existing schedule remains safely preserved.`;
                    errorBanner.classList.remove('hidden');
                }

                showToast(`Sync rejected: ${errorMsg}`);
                confirmBtn.style.display = 'none';
                cancelBtn.disabled = false;
                cancelBtn.innerText = 'Dismiss (Keep Current)';
                cancelBtn.onclick = () => { flowDiv.remove(); resolve(false); };
            }
        };

        if (cancelBtn) cancelBtn.onclick = async () => {
            cancelBtn.disabled = true;
            if (confirmBtn) confirmBtn.disabled = true;

            if (proposal && proposal.proposal_id) {
                await authenticatedFetch(`${API_BASE}/schedule/proposal/discard`, {
                    method: 'POST',
                    body: JSON.stringify({ proposal_id: proposal.proposal_id })
                }).catch(() => {});
            }

            if (statusBadge) {
                statusBadge.className = 'px-3 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-800 border border-slate-300';
                statusBadge.innerText = 'Discarded (Current Kept)';
            }

            showToast("Proposal discarded. Schedule unchanged.");
            setTimeout(() => {
                flowDiv.remove();
                resolve(false);
            }, 600);
        };
    });
}

// --- Main App Modules ---

async function loadDashboardData() {
    const container = document.getElementById('dashboard-tasks-container');
    if (!window.location.pathname.includes('/dashboard')) return;

    // Wire Dashboard Action Buttons
    const viewRoutineBtn = document.getElementById('view-full-routine-btn');
    if (viewRoutineBtn) viewRoutineBtn.onclick = () => window.location.href = '/routine';

    const viewSleepBtn = document.getElementById('view-sleep-data-btn');
    if (viewSleepBtn) viewSleepBtn.onclick = () => window.location.href = '/reasoning';

    const fabBtn = document.getElementById('floating-ai-assistant-btn');
    if (fabBtn) fabBtn.onclick = () => window.location.href = '/reasoning';

    const mobileLogout = document.getElementById('mobile-nav-logout');
    if (mobileLogout) mobileLogout.onclick = (e) => { e.preventDefault(); logout(); };

    try {
        if (container) {
            container.innerHTML = `<div class="p-8 text-center animate-pulse italic opacity-60">Syncing Wellness Vault...</div>`;
        }

        // Parallel fetch for schedule, dashboard summary, and insights
        const [data, summaryRes, insightsRes] = await Promise.all([
            getSchedule(),
            authenticatedFetch(`${API_BASE}/dashboard/summary`),
            authenticatedFetch(`${API_BASE}/insights`).catch(() => null)
        ]);

        const summary = (summaryRes && summaryRes.ok) ? await summaryRes.json() : {};

        // Onboarding Guard: Redirect new users who haven't completed assessment
        if (summary && summary.has_completed_onboarding === false) {
            window.location.href = '/onboarding';
            return;
        }

        // Helper for formatting time strings cleanly
        const formatTimeStr = (isoString) => {
            if (!isoString) return '';
            try {
                const d = new Date(isoString);
                if (isNaN(d.getTime())) return isoString;
                return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
            } catch(e) {
                return isoString;
            }
        };

        // 1. Update User Greeting dynamically
        const greetingEl = document.getElementById('dashboard-user-greeting');
        if (greetingEl) {
            const rawName = summary.username || localStorage.getItem('dinacharya_username') || 'Friend';
            const displayName = rawName.charAt(0).toUpperCase() + rawName.slice(1);
            greetingEl.innerText = `Welcome back, ${displayName}`;
        }

        // 2. Update Wellness Score dynamically
        const wellnessScoreEl = document.getElementById('dashboard-wellness-score');
        const wellnessBarEl = document.getElementById('dashboard-wellness-bar');
        const wellnessNoteEl = document.getElementById('dashboard-wellness-note');
        if (wellnessScoreEl && summary.wellness_score !== undefined) {
            wellnessScoreEl.innerText = summary.wellness_score;
            if (wellnessBarEl) wellnessBarEl.style.width = `${Math.min(100, Math.max(0, summary.wellness_score))}%`;
            if (wellnessNoteEl && summary.wellness_formula) {
                wellnessNoteEl.innerHTML = `
                    <span class="material-symbols-outlined text-[16px]" data-icon="insights">insights</span>
                    ${summary.wellness_formula}
                `;
            }
        }

        // 3. Update Sleep Tracking dynamically
        const sleepScoreEl = document.getElementById('dashboard-sleep-score');
        const sleepMaxEl = document.getElementById('dashboard-sleep-max');
        const sleepDurationEl = document.getElementById('dashboard-sleep-duration');
        const sleepNoteEl = document.getElementById('dashboard-sleep-note');
        if (sleepScoreEl) {
            if (summary.sleep_score !== null && summary.sleep_score !== undefined) {
                sleepScoreEl.innerText = summary.sleep_score;
                if (sleepMaxEl) sleepMaxEl.classList.remove('hidden');
                if (sleepDurationEl) sleepDurationEl.innerText = summary.sleep_duration || 'Rest recorded';
                if (sleepNoteEl) sleepNoteEl.innerText = summary.sleep_note || 'Restorative sleep cycle recorded.';
            } else {
                sleepScoreEl.innerText = 'Awaiting';
                if (sleepMaxEl) sleepMaxEl.classList.add('hidden');
                if (sleepDurationEl) sleepDurationEl.innerText = summary.sleep_duration || 'Awaiting night cycle';
                if (sleepNoteEl) sleepNoteEl.innerText = summary.sleep_note || 'Wear watch overnight to record sleep.';
            }
        }

        // 4. Update Adherence Score and 5-Day Trend Chart
        const adherenceEl = document.getElementById('dashboard-adherence-value');
        if (adherenceEl && summary.adherence_pct !== undefined) {
            adherenceEl.innerText = `${summary.adherence_pct}%`;
        }
        const adherenceChart = document.getElementById('dashboard-adherence-chart');
        if (adherenceChart) {
            const trend = summary.adherence_trend || [];
            if (trend.length > 0) {
                const maxCount = Math.max(1, ...trend.map(t => t.count || 0));
                adherenceChart.innerHTML = trend.map(t => {
                    const heightPct = Math.max(20, Math.round((t.count / maxCount) * 100));
                    const dayLabel = t.date ? t.date.slice(5) : '';
                    return `
                        <div class="flex-1 flex flex-col items-center gap-1 h-full justify-end group relative cursor-pointer" title="${t.date}: ${t.count} practices completed">
                            <div class="w-full bg-primary/20 group-hover:bg-primary/50 rounded-t-sm transition-all" style="height: ${heightPct}%;"></div>
                            <span class="text-[9px] text-gray-400 group-hover:text-primary font-mono">${dayLabel}</span>
                        </div>
                    `;
                }).join('');
            } else {
                adherenceChart.innerHTML = `
                    <div class="w-full text-center text-[10px] text-gray-400 py-2">
                        Tracking daily habit completions
                    </div>
                `;
            }
        }

        // 5. Update Current Dosha & Tags dynamically
        const doshaTitleEl = document.getElementById('dashboard-dosha-title');
        const doshaTagsEl = document.getElementById('dashboard-dosha-tags');
        const dProfile = summary.dosha_profile || (data && data.dosha_profile) || {};
        const pProfile = summary.prakriti_profile || {};
        if (dProfile || pProfile) {
            const flags = dProfile.vikriti_flags || {};
            const p = dProfile.prakriti || {};

            let doshaTitle = "Vata-Pitta Balance";
            let tags = ["Grounding", "Equilibrium"];

            if (flags.has_fever) {
                doshaTitle = "Nava Jwara (Fever)";
                tags = ["Deep Rest", "Hydration", "No Oil"];
            } else if (flags.vata_aggravated && flags.pitta_aggravated) {
                doshaTitle = "Vata-Pitta Elevated";
                tags = ["Grounding", "Cooling"];
            } else if (flags.vata_aggravated) {
                doshaTitle = "Vata Aggravated";
                tags = ["Grounding", "Warmth", "Snigdha"];
            } else if (flags.pitta_aggravated) {
                doshaTitle = "Pitta Aggravated";
                tags = ["Cooling", "Calming", "Moderation"];
            } else if (flags.kapha_aggravated) {
                doshaTitle = "Kapha Aggravated";
                tags = ["Stimulating", "Light", "Movement"];
            } else if (pProfile.constitution_type) {
                doshaTitle = pProfile.constitution_type;
                const pDosha = pProfile.primary_dosha || "Vata";
                tags = [pDosha === "Vata" ? "Warmth" : pDosha === "Pitta" ? "Cooling" : "Lightness", "Circadian Sync"];
            } else if (p.vata || p.pitta || p.kapha) {
                const maxD = Object.entries({ Vata: p.vata || 0, Pitta: p.pitta || 0, Kapha: p.kapha || 0 }).sort((a,b) => b[1] - a[1])[0][0];
                doshaTitle = `${maxD} Dominant`;
                tags = [maxD === "Vata" ? "Warmth" : maxD === "Pitta" ? "Cooling" : "Lightness", "Circadian Sync"];
            }

            if (doshaTitleEl) doshaTitleEl.innerText = doshaTitle;
            if (doshaTagsEl) {
                doshaTagsEl.innerHTML = tags.map((t, idx) => `
                    <span class="px-3 py-1 rounded-full ${idx === 0 ? 'bg-secondary-container text-on-secondary-container' : 'bg-surface-container text-on-surface-variant'} font-label-sm text-label-sm">${t}</span>
                `).join('');
            }
        }

        // 6. Update Live Smartwatch Biometrics Panel
        const telem = summary.telemetry || {};

        // Heart Rate
        const hrEl = document.getElementById('biometric-hr-val');
        const hrTimeEl = document.getElementById('biometric-hr-time');
        if (hrEl) {
            if (telem.heart_rate && telem.heart_rate.is_available) {
                hrEl.innerText = telem.heart_rate.value;
                const timeStr = telem.heart_rate.measured_at ? formatTimeStr(telem.heart_rate.measured_at) : '';
                if (hrTimeEl) hrTimeEl.innerText = `Measured: ${timeStr} · Fastrack Watch`;
            } else {
                hrEl.innerText = '--';
                if (hrTimeEl) hrTimeEl.innerText = 'No heart rate records yet';
            }
        }

        // Daily Steps
        const stepsEl = document.getElementById('biometric-steps-val');
        const stepsTimeEl = document.getElementById('biometric-steps-time');
        if (stepsEl) {
            if (telem.steps && telem.steps.is_available) {
                stepsEl.innerText = Number(telem.steps.value).toLocaleString();
                const dateStr = telem.steps.measured_at ? telem.steps.measured_at.split('T')[0] : 'Today';
                if (stepsTimeEl) stepsTimeEl.innerText = `Cumulative total for ${dateStr}`;
            } else {
                stepsEl.innerText = '--';
                if (stepsTimeEl) stepsTimeEl.innerText = 'No step records yet';
            }
        }

        // Blood Oxygen SpO2
        const spo2El = document.getElementById('biometric-spo2-val');
        const spo2TimeEl = document.getElementById('biometric-spo2-time');
        if (spo2El) {
            if (telem.spo2 && telem.spo2.is_available) {
                spo2El.innerText = telem.spo2.value;
                const timeStr = telem.spo2.measured_at ? formatTimeStr(telem.spo2.measured_at) : '';
                if (spo2TimeEl) spo2TimeEl.innerText = `Measured: ${timeStr} · Fastrack Watch`;
            } else {
                spo2El.innerText = '--';
                if (spo2TimeEl) spo2TimeEl.innerText = 'No SpO₂ records yet';
            }
        }

        // Stress
        const stressEl = document.getElementById('biometric-stress-val');
        const stressTimeEl = document.getElementById('biometric-stress-time');
        if (stressEl) {
            if (telem.stress && telem.stress.is_available) {
                stressEl.innerText = `${telem.stress.value} / 100`;
                if (stressTimeEl) stressTimeEl.innerText = `Measured: ${telem.stress.measured_at}`;
            } else {
                stressEl.innerText = 'Unsupported';
                if (stressTimeEl) stressTimeEl.innerText = 'Fastrack Noir Charm lacks stress sensor';
            }
        }

        // Device Info & Sync
        const devInfoEl = document.getElementById('telemetry-device-info');
        if (devInfoEl) {
            devInfoEl.innerText = `Device: ${telem.device_model || 'Fastrack Noir Charm'} · Package: ${telem.source_package || 'com.titan.fastrack.reflex'}`;
        }
        const syncTextEl = document.getElementById('telemetry-last-sync-text');
        if (syncTextEl) {
            if (summary.is_upstream_stale || telem.is_upstream_stale) {
                syncTextEl.innerHTML = `
                    <span class="inline-flex items-center gap-1 text-amber-800 bg-amber-100/90 border border-amber-300 px-2.5 py-0.5 rounded-full font-bold text-[11px]">
                        <span class="material-symbols-outlined text-[13px]">warning</span>
                        Upstream Data Stale (&gt;30m) · Open Fastrack Smart World App
                    </span>`;
            } else {
                syncTextEl.innerText = telem.last_sync ? `Last synced ${formatTimeStr(telem.last_sync)}` : 'Synced via Health Connect';
            }
        }

        // Manual Refresh button wiring
        const refreshBtn = document.getElementById('telemetry-manual-refresh-btn');
        if (refreshBtn && !refreshBtn.dataset.wired) {
            refreshBtn.dataset.wired = 'true';
            refreshBtn.onclick = async () => {
                refreshBtn.classList.add('animate-pulse');
                refreshBtn.disabled = true;
                await loadDashboardData();
                refreshBtn.classList.remove('animate-pulse');
                refreshBtn.disabled = false;
                showToast('✓ Fastrack biometrics refreshed');
            };
        }

        // 4. Update Dynamic Insight Highlight from /api/insights
        if (insightsRes && insightsRes.ok) {
            try {
                const insightData = await insightsRes.json();
                const insights = insightData.insights || {};
                const topNode = insights['node-result'] || insights['node-vata'] || insights['node-sleep'];
                if (topNode) {
                    const titleEl = document.getElementById('dashboard-insight-title');
                    const descEl = document.getElementById('dashboard-insight-desc');
                    if (titleEl && topNode.title) titleEl.innerText = topNode.title;
                    if (descEl && topNode.desc) descEl.innerText = topNode.desc;
                }
            } catch(e) {}
        }

        // 5. Populate Today's Focus with real upcoming tasks across morning/midday/evening
        if (!container) return;
        if (!data || !data.schedule) {
            container.innerHTML = `<p class="p-4 text-center opacity-60">Routine ready to be configured.</p>`;
            return;
        }

        container.innerHTML = '';
        const allTasks = [
            ...(data.schedule.morning_block || []),
            ...(data.schedule.midday_block || []),
            ...(data.schedule.evening_block || [])
        ];

        if (allTasks.length === 0) {
            container.innerHTML = `<p class="p-4 text-center opacity-60">All practices for today complete.</p>`;
            return;
        }

        // Build authoritative set of today's completed practice names
        const completedNames = new Set((summary.completions_today || []).map(p => p.toLowerCase()));
        if (summary.activities && Array.isArray(summary.activities)) {
            summary.activities.forEach(a => {
                if (['completed_by_user', 'auto_completed_evidence', 'completed'].includes(a.status)) {
                    if (a.practice_name) completedNames.add(a.practice_name.toLowerCase());
                }
            });
        }

        // Display up to 4 upcoming tasks
        const displayTasks = allTasks.slice(0, 4);
        displayTasks.forEach(task => {
            const taskName = task.name || task.activity || 'Practice';
            const taskSlot = task.time_slot || 'Flexible';
            const taskDesc = task.description || task.rationale || 'Ayurvedic daily habit';
            const isCompleted = completedNames.has(taskName.toLowerCase());
            const isUpcoming = !isCompleted && isSlotUpcoming(taskSlot, 15);

            const div = document.createElement('div');
            div.className = `flex items-center gap-4 p-4 rounded-2xl border border-outline-variant/20 transition-all cursor-pointer group ${isCompleted ? 'bg-surface-container-low/40 opacity-70' : isUpcoming ? 'bg-surface-container-lowest/30 opacity-80' : 'bg-surface-container-lowest/50 hover:bg-surface-container-lowest'}`;

            div.innerHTML = `
                <div class="w-12 h-12 rounded-full ${isCompleted ? 'bg-primary text-on-primary' : isUpcoming ? 'bg-surface-container-high text-outline' : 'bg-secondary-container text-on-secondary-container'} flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform shadow-sm">
                    <span class="material-symbols-outlined" data-icon="${isCompleted ? 'check_circle' : isUpcoming ? 'schedule' : 'spa'}">${isCompleted ? 'check_circle' : isUpcoming ? 'schedule' : 'spa'}</span>
                </div>
                <div class="flex-grow">
                    <div class="flex items-center gap-2 mb-1 flex-wrap">
                        <h4 class="font-label-md text-label-md text-on-surface group-hover:text-primary transition-colors ${isCompleted ? 'line-through text-outline' : ''}">${escapeHtml(taskName)}</h4>
                        <span class="text-[10px] uppercase font-bold text-primary/70 bg-primary/5 px-2 py-0.5 rounded">${escapeHtml(taskSlot)}</span>
                        ${isCompleted ? '<span class="text-[10px] uppercase font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded flex items-center gap-0.5"><span class="material-symbols-outlined text-[12px]">done</span>Completed</span>' : isUpcoming ? '<span class="text-[10px] uppercase font-bold text-outline bg-surface-variant/50 px-2 py-0.5 rounded flex items-center gap-0.5"><span class="material-symbols-outlined text-[12px]">schedule</span>Upcoming</span>' : ''}
                    </div>
                    <p class="font-body-sm text-body-sm text-on-surface-variant line-clamp-1">${escapeHtml(taskDesc)}</p>
                </div>
                <button class="task-check-btn w-8 h-8 rounded-full border-2 ${isCompleted ? 'bg-primary border-primary text-white shadow-sm cursor-default' : isUpcoming ? 'border-outline-variant/40 bg-surface-container-low text-outline/50 cursor-not-allowed' : 'border-outline-variant hover:border-primary hover:bg-primary/5 text-primary'} flex items-center justify-center transition-all shrink-0" title="${isCompleted ? 'Completed' : isUpcoming ? `Scheduled for ${escapeHtml(taskSlot)}. Available once window begins.` : 'Mark as Completed'}">
                    <span class="material-symbols-outlined text-[16px] ${isCompleted ? 'opacity-100 text-white' : isUpcoming ? 'opacity-70 text-outline' : 'opacity-0 group-hover:opacity-60'}">${isUpcoming ? 'lock_clock' : 'check'}</span>
                </button>
            `;

            const checkBtn = div.querySelector('.task-check-btn');
            const checkIcon = div.querySelector('.task-check-btn span');

            const handleComplete = async (e) => {
                e.stopPropagation();
                if (isCompleted) {
                    showToast(`✓ ${taskName} is already recorded as complete today.`);
                    return;
                }
                if (isUpcoming) {
                    showToast(`⏳ ${taskName} is scheduled for ${taskSlot}. Available once its window arrives.`);
                    return;
                }

                // Immediate optimistic visual feedback
                checkBtn.classList.add('bg-primary', 'border-primary', 'text-white');
                checkIcon.classList.remove('opacity-0', 'text-primary');
                checkIcon.classList.add('opacity-100', 'text-white');
                div.classList.add('opacity-70');
                const titleHeading = div.querySelector('h4');
                if (titleHeading) titleHeading.classList.add('line-through', 'text-outline');
                showToast(`✓ Completed ${taskName}`);

                try {
                    const res = await authenticatedFetch(`${API_BASE}/activities/complete`, {
                        method: 'POST',
                        body: JSON.stringify({ practice_name: taskName })
                    });
                    if (res && res.ok) {
                        const resData = await res.json();
                        if (resData.adherence && resData.adherence.display_text) {
                            const adhBadge = document.getElementById('dashboard-adherence-value');
                            if (adhBadge) adhBadge.innerText = resData.adherence.display_text;
                        }
                        sessionStorage.removeItem('schedule_cache');
                        setTimeout(() => loadDashboardData(true), 500);
                    } else {
                        const errJson = await res.json().catch(() => null);
                        const errMsg = errJson && errJson.detail ? errJson.detail : "Could not complete activity.";
                        showToast(`⏳ ${errMsg}`);
                        setTimeout(() => loadDashboardData(true), 800);
                    }
                } catch(err) {
                    console.error("Task completion error:", err);
                    showToast("Network error recording completion.");
                    setTimeout(() => loadDashboardData(true), 800);
                }
            };

            checkBtn.onclick = handleComplete;
            div.onclick = handleComplete;

            container.appendChild(div);
        });

    } catch(e) { console.error("loadDashboardData error:", e); }
}

window.completeRoutineTask = async function(taskName) {
    showToast(`✓ Recording ${taskName}...`);
    try {
        const res = await authenticatedFetch(`${API_BASE}/activities/complete`, {
            method: 'POST',
            body: JSON.stringify({ practice_name: taskName })
        });
        if (res && res.ok) {
            sessionStorage.removeItem('schedule_cache');
            showToast(`✓ Saved: ${taskName} completed!`);
            loadRoutineData(false);
        } else {
            const errJson = await res.json().catch(() => null);
            const errMsg = errJson && errJson.detail ? errJson.detail : "Failed to record task completion.";
            showToast(`⏳ ${errMsg}`);
        }
    } catch(err) {
        console.error("completeRoutineTask error:", err);
        showToast("Network error recording completion.");
    }
};

async function loadRoutineData(forceRefresh = false) {
    const container = document.getElementById('routine-timeline-container');
    if (!container || !window.location.pathname.includes('/routine')) return;
    try {
        container.innerHTML = `<div class="p-20 text-center animate-pulse italic text-primary">Accessing Persistent Vault...</div>`;
        const [data, activitiesRes, summaryRes] = await Promise.all([
            getSchedule(forceRefresh),
            authenticatedFetch(`${API_BASE}/activities/today`).catch(() => null),
            authenticatedFetch(`${API_BASE}/dashboard/summary`).catch(() => null)
        ]);

        const summary = (summaryRes && summaryRes.ok) ? await summaryRes.json() : {};
        const activitiesData = (activitiesRes && activitiesRes.ok) ? await activitiesRes.json() : {};
        const activitiesList = activitiesData.activities || summary.activities || [];

        // Update Today's date and dosha subtitle in routine header if present
        const routineDateEl = document.getElementById('routine-today-date');
        if (routineDateEl) {
            const todayStr = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
            routineDateEl.textContent = todayStr;
        }
        const routineDoshaEl = document.getElementById('routine-dosha-subtitle');
        if (routineDoshaEl && summary) {
            const dProfile = summary.dosha_profile || (data && data.dosha_profile) || {};
            const flags = dProfile.vikriti_flags || {};
            if (flags.has_fever) {
                routineDoshaEl.textContent = "A gentle, therapeutic regimen adapted for Nava Jwara (fever) with deep metabolic rest and zero heavy unctions.";
            } else if (flags.vata_aggravated && flags.pitta_aggravated) {
                routineDoshaEl.textContent = "A personalized rhythm designed to ground restless Vata and soothe elevated Pitta warmth throughout your day.";
            } else if (flags.vata_aggravated) {
                routineDoshaEl.textContent = "A deeply nourishing, grounding Dinacharya sequence to pacify excess Vata and stabilize your circadian flow.";
            } else if (flags.pitta_aggravated) {
                routineDoshaEl.textContent = "A soothing, cooling daily sequence calibrated to moderate digestive fire and reduce Pitta heat.";
            } else if (flags.kapha_aggravated) {
                routineDoshaEl.textContent = "An invigorating, active Dinacharya designed to stimulate circulation and clear sluggish Kapha.";
            }
        }

        // Build mapping of activity status by lowercase practice name
        const activityStatusMap = new Map();
        activitiesList.forEach(a => {
            if (a.practice_name) {
                activityStatusMap.set(a.practice_name.toLowerCase().trim(), a.status || 'scheduled');
            }
        });
        (summary.completions_today || []).forEach(p => {
            if (!activityStatusMap.has(p.toLowerCase().trim())) {
                activityStatusMap.set(p.toLowerCase().trim(), 'completed_by_user');
            }
        });

        // Robust recursive extractor for schedule blocks
        let scheduleObj = null;
        if (data) {
            if (data.morning_block || data.midday_block || data.evening_block) {
                scheduleObj = data;
            } else if (data.schedule) {
                if (data.schedule.morning_block || data.schedule.midday_block || data.schedule.evening_block) {
                    scheduleObj = data.schedule;
                } else if (data.schedule.schedule && (data.schedule.schedule.morning_block || data.schedule.schedule.midday_block || data.schedule.schedule.evening_block)) {
                    scheduleObj = data.schedule.schedule;
                }
            }
        }
        if (!scheduleObj && summary && summary.schedule) {
            const s = summary.schedule;
            if (s.morning_block || s.midday_block || s.evening_block) {
                scheduleObj = s;
            } else if (s.schedule && (s.schedule.morning_block || s.schedule.midday_block || s.schedule.evening_block)) {
                scheduleObj = s.schedule;
            }
        }

        if (!scheduleObj) {
            container.innerHTML = `
                <div class="p-12 text-center glass-card bg-surface-container-low/40 border border-error/20 rounded-[2rem] shadow-lg max-w-xl mx-auto my-8">
                    <span class="material-symbols-outlined text-4xl text-error mb-2">sync_problem</span>
                    <h4 class="font-headline-sm text-on-surface mb-2">Vault Synchronization Interrupted</h4>
                    <p class="text-sm opacity-70 mb-6">Unable to retrieve routine from the vault. The service may have encountered a temporary constraint.</p>
                    <button onclick="loadRoutineData(true)" class="px-6 py-3 bg-primary text-on-primary rounded-xl font-bold shadow-md hover:scale-[1.02] active:scale-95 transition-all">Retry Synchronization</button>
                </div>`;
            return;
        }

        const blocks = ['morning_block', 'midday_block', 'evening_block'];
        let totalTasks = 0;
        blocks.forEach(b => {
            if (Array.isArray(scheduleObj[b])) totalTasks += scheduleObj[b].length;
        });

        if (totalTasks === 0) {
            container.innerHTML = `
                <div class="p-12 text-center glass-card bg-surface-container-low/40 border border-outline-variant/20 rounded-[2rem] shadow-lg max-w-xl mx-auto my-8">
                    <span class="material-symbols-outlined text-4xl text-secondary mb-2">event_available</span>
                    <h4 class="font-headline-sm text-on-surface mb-2">No Practices Scheduled for Today</h4>
                    <p class="text-sm opacity-70 mb-6">Your daily routine vault is clear. Ask Vaidya AI in chat to recommend practices or compile a personalized Ayurvedic Dinacharya.</p>
                    <a href="/reasoning" class="inline-block px-6 py-3 bg-primary text-on-primary rounded-xl font-bold shadow-md hover:scale-[1.02] active:scale-95 transition-all">Consult Vaidya AI</a>
                </div>`;
            return;
        }

        container.innerHTML = '<div class="hidden sm:block absolute left-[120px] top-8 bottom-8 w-[2px] bg-outline-variant/20"></div>';
        blocks.forEach(blockKey => {
            const tasks = scheduleObj[blockKey] || [];
            if (tasks.length === 0) return;
            const section = document.createElement('div');
            section.className = 'relative z-10 mb-12 flex flex-col sm:flex-row gap-8';
            let tasksHtml = '';
            tasks.forEach(task => {
                const taskName = task.name || task.activity || 'Practice';
                const taskSlot = task.time_slot || task.time || 'Flexible';
                const taskRationale = task.rationale || task.description || 'Ayurvedic daily practice.';
                const taskDesc = task.description || '';
                const rawStatus = activityStatusMap.get(taskName.toLowerCase().trim()) || 'scheduled';
                const isCompleted = ['completed_by_user', 'auto_completed_evidence', 'completed'].includes(rawStatus);
                const isSkipped = rawStatus === 'skipped';
                const isCompensated = rawStatus === 'compensation_scheduled';

                let statusBadge = '';
                let btnHtml = '';

                const safeJsTaskName = escapeHtml(taskName).replace(/'/g, "\\'");

                const isUpcoming = !isCompleted && isSlotUpcoming(taskSlot, 15);

                if (isCompleted) {
                    statusBadge = `<span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-xs font-semibold flex items-center gap-1"><span class="material-symbols-outlined text-[13px]">check_circle</span>Completed</span>`;
                    btnHtml = `<button class="w-full mt-6 py-3 bg-secondary-container text-on-secondary-container rounded-2xl font-bold cursor-default opacity-85 flex items-center justify-center gap-2" disabled><span class="material-symbols-outlined text-lg">check_circle</span>Completed Today</button>`;
                } else if (isSkipped) {
                    statusBadge = `<span class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-xs font-semibold flex items-center gap-1"><span class="material-symbols-outlined text-[13px]">block</span>Skipped</span>`;
                    btnHtml = `<button class="w-full mt-6 py-3 bg-primary text-on-primary rounded-2xl font-bold hover:brightness-110 active:scale-95 transition-all shadow-md" onclick="event.stopPropagation(); completeRoutineTask('${safeJsTaskName}')">Resume Practice</button>`;
                } else if (isCompensated) {
                    statusBadge = `<span class="px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 text-xs font-semibold flex items-center gap-1"><span class="material-symbols-outlined text-[13px]">update</span>Rescheduled</span>`;
                    btnHtml = `<button class="w-full mt-6 py-3 bg-primary text-on-primary rounded-2xl font-bold hover:brightness-110 active:scale-95 transition-all shadow-md" onclick="event.stopPropagation(); completeRoutineTask('${safeJsTaskName}')">Mark Complete</button>`;
                } else if (isUpcoming) {
                    const slotStart = taskSlot.split(' - ')[0] || taskSlot;
                    statusBadge = `<span class="px-2 py-0.5 rounded-full bg-surface-variant/80 text-outline text-xs font-medium flex items-center gap-1"><span class="material-symbols-outlined text-[13px]">schedule</span>Upcoming</span>`;
                    btnHtml = `<button class="w-full mt-6 py-3 bg-surface-container-high/60 text-outline rounded-2xl font-semibold cursor-not-allowed opacity-75 flex items-center justify-center gap-2" disabled title="Scheduled for ${escapeHtml(taskSlot)}"><span class="material-symbols-outlined text-lg">lock_clock</span>Upcoming (Starts ${escapeHtml(slotStart)})</button>`;
                } else {
                    statusBadge = `<span class="px-2 py-0.5 rounded-full bg-surface-variant text-on-surface text-xs font-medium">Pending</span>`;
                    btnHtml = `<button class="w-full mt-6 py-3 bg-primary text-on-primary rounded-2xl font-bold hover:brightness-110 active:scale-95 transition-all shadow-md" onclick="event.stopPropagation(); completeRoutineTask('${safeJsTaskName}')">Mark Complete</button>`;
                }

                tasksHtml += `
                    <div class="timeline-card bg-white p-6 rounded-[2rem] border border-outline-variant/10 shadow-sm cursor-pointer mb-4 ${isCompleted ? 'border-primary/20 bg-surface-container-low/30 opacity-90' : ''}" onclick="this.classList.toggle('expanded')">
                        <div class="flex justify-between items-center">
                            <div class="flex items-center gap-4">
                                <div class="w-12 h-12 rounded-2xl ${isCompleted ? 'bg-primary text-white' : 'bg-primary/5 text-primary'} flex items-center justify-center">
                                    <span class="material-symbols-outlined">${isCompleted ? 'check_circle' : 'self_improvement'}</span>
                                </div>
                                <div>
                                    <div class="flex items-center gap-2">
                                        <p class="font-bold text-lg ${isCompleted ? 'line-through text-outline' : ''}">${escapeHtml(taskName)}</p>
                                        ${statusBadge}
                                    </div>
                                    <p class="text-sm opacity-60">${escapeHtml(taskSlot)}</p>
                                </div>
                            </div>
                            <span class="material-symbols-outlined expand-icon">expand_more</span>
                        </div>
                        <div class="timeline-card-content">
                            <p class="text-on-surface-variant mb-4">${escapeHtml(taskDesc)}</p>
                            <div class="bg-surface-container-low p-4 rounded-2xl italic text-sm text-primary">"${escapeHtml(taskRationale)}"</div>
                            ${btnHtml}
                        </div>
                    </div>
                `;
            });
            section.innerHTML = `<div class="sm:w-[120px] text-right pt-4 font-bold text-primary opacity-40">${blockKey.split('_')[0].toUpperCase()}</div><div class="flex-1">${tasksHtml}</div>`;
            container.appendChild(section);
        });
    } catch(e) { console.error("loadRoutineData error:", e); }
}

function updateLiveTraceStep(container, evt) {
    if (!container || !evt) return;
    if (evt.stage === 'understanding_question') {
        container.innerHTML = `
            <div class="flex items-center gap-2 text-primary font-medium">
                <span class="material-symbols-outlined text-[15px] text-secondary ai-pulse">explore</span>
                <span>${escapeHtml(evt.message || 'Analyzing question, constitutional context & biometrics...')}</span>
            </div>
        `;
    } else if (evt.stage === 'tool_call_start') {
        const row = document.createElement('div');
        row.id = `step-tool-${evt.tool}`;
        row.className = 'flex items-center gap-2 text-on-surface-variant pl-2 py-0.5 animate-pulse';
        row.innerHTML = `
            <span class="text-secondary font-bold">▸</span>
            <span class="font-bold text-primary">${escapeHtml(evt.friendly_name || evt.tool)}</span>
            <span class="text-[10px] text-gray-400 font-mono">(calling...)</span>
        `;
        container.appendChild(row);
    } else if (evt.stage === 'tool_call_complete') {
        let row = document.getElementById(`step-tool-${evt.tool}`);
        if (!row) {
            row = document.createElement('div');
            container.appendChild(row);
        }
        row.className = 'flex items-center justify-between pl-4 py-0.5 text-[11px]';
        const isErr = evt.status === 'error';
        const color = isErr ? 'text-error' : 'text-secondary';
        const icon = isErr ? '✗' : '✓';
        const dur = evt.duration_ms ? `${evt.duration_ms}ms` : '';
        row.innerHTML = `
            <span class="${color}"><strong>${icon}</strong> ${escapeHtml(evt.summary || 'Completed')}</span>
            <span class="opacity-60 text-[10px] font-mono">${dur}</span>
        `;
    } else if (evt.stage === 'preparing_response') {
        const row = document.createElement('div');
        row.className = 'flex items-center gap-2 text-primary font-semibold pt-1 border-t border-outline-variant/10 mt-1';
        row.innerHTML = `
            <span class="text-secondary text-sm">✦</span>
            <span>${escapeHtml(evt.message || 'Synthesizing recommendations...')}</span>
        `;
        container.appendChild(row);
    }
}

async function loadInsightsData() {
    const chatHistory = document.getElementById('reasoning-chat-history');
    const form = document.getElementById('reasoning-chat-form');
    if (!chatHistory || !window.location.pathname.includes('/reasoning')) return;
    try {
        chatHistory.innerHTML = '<div class="p-8 text-center animate-pulse italic opacity-60">Synchronizing Chat Vault...</div>';
        const res = await authenticatedFetch(`${API_BASE}/chat/history`);
        if (res) {
            const data = await res.json();
            chatHistory.innerHTML = '';
            if (data.history && data.history.length > 0) {
                data.history.forEach(msg => renderChatMessage(chatHistory, msg.role, msg.content));
            } else {
                await typeMessage(chatHistory, "### Welcome to the Reasoning Engine\n\nI am **Vaidya AI**, your Ayurvedic wellness physician. I have analyzed your biometrics, Prakriti/Vikriti assessment, and active daily routine.\n\nHow can I assist you with your routine logic or circadian adjustments today? 🙏");
            }
        }
        if (form) {
            form.onsubmit = async (e) => {
                e.preventDefault();
                const input = document.getElementById('reasoning-input');
                const msg = input.value.trim();
                if (!msg) return;
                await renderChatMessage(chatHistory, 'user', msg);
                input.value = '';

                // Create stable, permanent assistant message container that is never deleted
                const assistantMsgId = 'assistant-msg-' + Date.now();
                const assistantDiv = document.createElement('div');
                assistantDiv.id = assistantMsgId;
                assistantDiv.className = 'flex gap-4 max-w-3xl message-entrance mb-8 w-full';
                assistantDiv.innerHTML = `
                    <div class="w-10 h-10 rounded-xl bg-primary flex items-center justify-center flex-shrink-0 shadow-md">
                        <span class="material-symbols-outlined text-on-primary text-[22px] ai-pulse">psychology_alt</span>
                    </div>
                    <div class="bg-white p-5 rounded-[1.5rem] rounded-tl-none shadow-md border border-outline-variant/20 flex-1 min-w-0">
                        <div class="flex items-center justify-between mb-2 pb-2 border-b border-outline-variant/10">
                            <div class="flex items-center gap-2">
                                <span class="w-2.5 h-2.5 rounded-full bg-secondary ai-pulse" id="status-dot-${assistantMsgId}"></span>
                                <span class="text-xs font-bold uppercase tracking-wider text-primary" id="status-title-${assistantMsgId}">Vaidya Reasoning Engine Active</span>
                            </div>
                            <div class="flex items-center gap-1" id="typing-dots-${assistantMsgId}">
                                <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
                            </div>
                        </div>
                        <div id="live-trace-${assistantMsgId}" class="space-y-1.5 text-xs font-mono text-on-surface-variant">
                            <div class="flex items-center gap-2 text-primary font-medium">
                                <span class="material-symbols-outlined text-[15px] text-secondary">explore</span>
                                <span>Analyzing clinical query, constitutional baseline & biometrics...</span>
                            </div>
                        </div>
                        <div id="response-content-${assistantMsgId}" class="mt-4 pt-3 border-t border-outline-variant/10 text-on-surface leading-relaxed hidden"></div>
                    </div>
                `;
                chatHistory.appendChild(assistantDiv);
                chatHistory.scrollTop = chatHistory.scrollHeight;

                const liveTraceSteps = document.getElementById('live-trace-' + assistantMsgId);
                const dotsEl = document.getElementById('typing-dots-' + assistantMsgId);
                const statusDot = document.getElementById('status-dot-' + assistantMsgId);
                const statusTitle = document.getElementById('status-title-' + assistantMsgId);
                const responseContent = document.getElementById('response-content-' + assistantMsgId);

                let chatData = null;

                try {
                    const token = getToken();
                    const streamRes = await fetch(`${API_BASE}/chat/stream`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${token}`
                        },
                        body: JSON.stringify({ message: msg })
                    });

                    if (streamRes.ok && streamRes.body) {
                        const reader = streamRes.body.getReader();
                        const decoder = new TextDecoder();
                        let buffer = '';

                        while (true) {
                            const { value, done } = await reader.read();
                            if (done) break;
                            buffer += decoder.decode(value, { stream: true });
                            const lines = buffer.split('\n');
                            buffer = lines.pop();

                            for (const line of lines) {
                                if (line.startsWith('data: ')) {
                                    const jsonStr = line.slice(6).trim();
                                    if (!jsonStr) continue;
                                    try {
                                        const event = JSON.parse(jsonStr);
                                        if (event.type === 'trace' && liveTraceSteps) {
                                            updateLiveTraceStep(liveTraceSteps, event);
                                            chatHistory.scrollTop = chatHistory.scrollHeight;
                                        } else if (event.type === 'final_response') {
                                            chatData = event;
                                        } else if (event.type === 'error') {
                                            chatData = { response: event.response || event.message };
                                        }
                                    } catch(pErr) {}
                                }
                            }
                        }
                    }
                } catch(streamErr) {
                    console.warn("SSE stream interrupted:", streamErr);
                }

                // If stream disconnected before final_response, reconcile against backend database history
                if (!chatData || !chatData.response) {
                    try {
                        const histRes = await authenticatedFetch(`${API_BASE}/chat/history?limit=3`);
                        if (histRes && histRes.ok) {
                            const histData = await histRes.json();
                            if (histData.history && histData.history.length > 0) {
                                const lastMsg = histData.history[histData.history.length - 1];
                                if (lastMsg.role === 'assistant' && lastMsg.content) {
                                    chatData = { response: lastMsg.content, message_id: lastMsg.id };
                                }
                            }
                        }
                    } catch(hErr) {
                        console.warn("History reconciliation error:", hErr);
                    }
                }

                // Fallback to standard /api/chat only if database reconciliation did not yield a response
                if (!chatData || !chatData.response) {
                    try {
                        const chatRes = await authenticatedFetch(`${API_BASE}/chat`, { method: 'POST', body: JSON.stringify({ message: msg }) }, 30000);
                        if (chatRes && chatRes.ok) {
                            chatData = await chatRes.json();
                        }
                    } catch(cErr) {
                        console.error("Fallback /api/chat error:", cErr);
                    }
                }

                // Stop loading indicator on all terminal outcomes
                if (dotsEl) dotsEl.remove();
                if (statusDot) statusDot.classList.remove('ai-pulse');

                if (chatData && chatData.response) {
                    if (statusTitle) statusTitle.textContent = 'Vaidya AI • Clinical Guidance';
                    if (responseContent) {
                        responseContent.classList.remove('hidden');
                        responseContent.innerHTML = formatAIText(chatData.response);
                    }
                    chatHistory.scrollTop = chatHistory.scrollHeight;

                    if (chatData.schedule_updated && chatData.proposed_schedule) {
                        latestScheduleVersion++;
                        sessionStorage.removeItem('schedule_cache');
                        sessionStorage.setItem('schedule_cache', JSON.stringify({ 
                            data: { schedule: chatData.proposed_schedule }, 
                            timestamp: Date.now() 
                        }));
                        showToast("✓ Vault Synchronized.");
                        loadDashboardData();
                        loadRoutineData();
                    } else if (chatData.proposal || chatData.proposed_schedule) {
                        const accepted = await showRecalibrationFlowchart(chatData.proposed_schedule, chatData.proposal);
                        if (accepted) { 
                            await typeMessage(chatHistory, "### ✓ Schedule Synchronized\n\nYour approval has been confirmed and persisted to your daily routine vault."); 
                            sessionStorage.removeItem('schedule_cache');
                            loadDashboardData();
                            loadRoutineData(); 
                        }
                    }
                } else {
                    if (statusTitle) statusTitle.textContent = 'Notice • Connection Interrupted';
                    if (responseContent) {
                        responseContent.classList.remove('hidden');
                        responseContent.innerHTML = `
                            <div class="p-3 bg-error/10 border border-error/20 rounded-xl text-error text-xs">
                                <p class="font-bold">Reasoning Cluster Unreachable</p>
                                <p class="mt-1">I was unable to complete the response due to a momentary network delay. Your routine and biometric baseline remain safe.</p>
                                <button type="button" onclick="window.retryChatMessage('${escapeHtml(msg).replace(/'/g, "\\'")}')" class="mt-2.5 px-3 py-1.5 bg-primary text-white text-xs font-semibold rounded-lg hover:bg-primary/90 transition shadow-sm">
                                    ↻ Retry Message
                                </button>
                            </div>
                        `;
                    }
                    showToast("Connection timed out. Please retry.");
                }
            };
        }
    } catch(e) { console.error(e); }
}

window.retryChatMessage = function(text) {
    const input = document.getElementById('reasoning-input');
    const form = document.getElementById('reasoning-chat-form');
    if (input && form) {
        input.value = text;
        form.dispatchEvent(new Event('submit'));
    }
};



function initApp() {
    const isPublic = ['/', '/login', '/register', '/onboarding'].some(p => window.location.pathname === p);
    if (!isPublic && !getToken()) { window.location.href = '/login'; return; }
    
    // Sidebar Navigation logic
    const navs = { 'nav-dashboard': '/dashboard', 'nav-routine': '/routine', 'nav-insights': '/reasoning' };
    Object.keys(navs).forEach(id => {
        const el = document.getElementById(id);
        if (el) el.onclick = (e) => { e.preventDefault(); window.location.href = navs[id]; };
    });
    const logoutBtn = document.getElementById('nav-logout');
    if (logoutBtn) logoutBtn.onclick = (e) => { e.preventDefault(); logout(); };

    // New Chat button
    const analyzeBtn = document.querySelector('button.bg-primary');
    if (analyzeBtn && analyzeBtn.innerText.includes('New AI Analysis')) {
        analyzeBtn.onclick = async () => {
            if (confirm("Start a fresh analysis?")) {
                await authenticatedFetch(`${API_BASE}/chat/history`, { method: 'DELETE' });
                sessionStorage.removeItem('schedule_cache');
                window.location.reload();
            }
        };
    }

    // Auth Form Handlers
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.onsubmit = async (e) => {
            e.preventDefault();
            const u = document.getElementById('username').value;
            const p = document.getElementById('password').value;
            const res = await fetch(`${API_BASE}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, password: p }) });
            const data = await res.json();
            if (res.ok) { 
                setToken(data.token); 
                if (data.username || u) localStorage.setItem('dinacharya_username', data.username || u);
                window.location.href = data.has_completed_onboarding ? '/dashboard' : '/onboarding'; 
            }
            else showToast("Invalid credentials");
        };
    }

    // Fever Simulation Toggle
    const feverToggle = document.getElementById('simulate-fever-toggle');
    if (feverToggle) {
        feverToggle.checked = sessionStorage.getItem('simulate_fever') === 'true';
        feverToggle.onchange = (e) => {
            sessionStorage.setItem('simulate_fever', e.target.checked);
            sessionStorage.removeItem('schedule_cache');
            window.location.reload();
        };
    }
    const registerForm = document.getElementById('register-form');
    if (registerForm) {
        registerForm.onsubmit = async (e) => {
            e.preventDefault();
            const u = document.getElementById('username').value;
            const p = document.getElementById('password').value;
            const res = await fetch(`${API_BASE}/auth/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, password: p }) });
            const data = await res.json();
            if (res.ok) { 
                setToken(data.token); 
                if (data.username || u) localStorage.setItem('dinacharya_username', data.username || u);
                window.location.href = '/onboarding'; 
            }
            else showToast("Registration failed");
        };
    }

    // Wire Auxiliary & Informational Buttons
    document.querySelectorAll('a[href="#"]').forEach(a => {
        if (a.innerText.includes('Support')) {
            a.onclick = (e) => {
                e.preventDefault();
                showToast("Clinical Support: Ask questions directly to Vaidya AI in Chat.");
            };
        } else if (a.innerText.includes('Privacy') || a.innerText.includes('Terms')) {
            a.onclick = (e) => {
                e.preventDefault();
                showToast("Data Vault: All health telemetry is stored locally in SQLite.");
            };
        }
    });

    const attachBtn = document.querySelector('button[data-icon="attachment"]')?.closest('button') || document.querySelector('button:has(span[data-icon="attachment"])');
    if (attachBtn) {
        attachBtn.onclick = (e) => {
            e.preventDefault();
            showToast("Biometric Sync: Smart sensor baseline stream is active.");
        };
    }

    loadDashboardData();
    loadRoutineData();
    loadInsightsData();
    initNotifications();
    initWebPush();
}

let appInitialized = false;
function safeInitApp() {
    if (appInitialized) return;
    appInitialized = true;
    initApp();
}
document.addEventListener('DOMContentLoaded', safeInitApp);
if (document.readyState === 'complete' || document.readyState === 'interactive') safeInitApp();

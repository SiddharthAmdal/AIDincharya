// app.js - Dinacharya AI Frontend Logic

const API_BASE = '/api';

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
function logout() { 
    localStorage.removeItem('dinacharya_token'); 
    sessionStorage.removeItem('schedule_cache'); 
    window.location.href = '/'; 
}

async function authenticatedFetch(url, options = {}) {
    const token = getToken();
    if (!token && !url.includes('/auth/')) { window.location.href = '/login'; return null; }
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    try {
        const res = await fetch(url, { ...options, headers });
        if (res.status === 401) { logout(); return null; }
        return res;
    } catch(e) { console.error("Fetch failed:", e); return null; }
}

// --- Hybrid Caching Layer ---
async function getSchedule(forceRefresh = false) {
    const now = Date.now();
    const CACHE_DURATION = 10 * 60 * 1000; 
    const cachedString = sessionStorage.getItem('schedule_cache');
    let cache = null;
    try { if(cachedString) cache = JSON.parse(cachedString); } catch(e) {}
    if (!forceRefresh && cache && cache.data && (now - cache.timestamp < CACHE_DURATION)) return cache.data;

    const simulateFever = sessionStorage.getItem('simulate_fever') === 'true';
    const telemetry = simulateFever ? { body_temp_c: 38.5 } : {};
    const symptoms = simulateFever ? ["Active fever"] : [];

    const res = await authenticatedFetch(`${API_BASE}/schedule/generate`, { 
        method: 'POST', 
        body: JSON.stringify({ 
            user_id: "current", 
            context: { season: "Hemanta", weather: "Cold", temperature_c: 10.0, calendar_events: [], self_report_symptoms: symptoms },
            wearable_telemetry_7d: telemetry
        }) 
    });
    if (!res) return null;
    const data = await res.json();
    sessionStorage.setItem('schedule_cache', JSON.stringify({ data: data, timestamp: now }));
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

function formatAIText(text) {
    if (!text) return "";
    return text
        .replace(/\*\*(.*?)\*\*/g, '<span class="font-bold text-secondary">$1</span>')
        .replace(/^### (.*)/gm, '<h3 class="font-bold text-primary text-lg mt-4 mb-2">$1</h3>')
        .replace(/^- (.*)/gm, '<li class="ml-4 list-disc mb-1">$1</li>')
        .replace(/\n/g, '<br>');
}

// --- Messaging & Animations ---

async function typeMessage(container, text, role='assistant') {
    if (!container) return;
    const div = document.createElement('div');
    div.className = `flex gap-4 max-w-3xl ${role === 'user' ? 'ml-auto flex-row-reverse' : ''} message-entrance mb-8`;
    const icon = role === 'user' ? 'person' : 'psychology_alt';
    const bg = role === 'user' ? 'bg-primary text-on-primary shadow-lg' : 'bg-white text-on-surface border border-outline-variant/10 shadow-sm';
    div.innerHTML = `
        <div class="w-10 h-10 rounded-xl ${role === 'user' ? 'bg-surface-container-highest' : 'bg-primary'} flex items-center justify-center flex-shrink-0 shadow-md">
            <span class="material-symbols-outlined ${role === 'user' ? 'text-on-surface-variant' : 'text-on-primary'} text-[22px]">${icon}</span>
        </div>
        <div class="${bg} p-6 rounded-[1.5rem] ${role === 'user' ? 'rounded-tr-none' : 'rounded-tl-none'}">
            <p class="leading-relaxed text-md"></p>
        </div>
    `;
    container.appendChild(div);
    const p = div.querySelector('p');
    const words = text.split(' ');
    let currentText = '';
    for(let i=0; i<words.length; i++) {
        currentText += words[i] + ' ';
        p.innerHTML = formatAIText(currentText);
        container.scrollTop = container.scrollHeight;
        await new Promise(r => setTimeout(r, 15));
    }
}

async function renderChatMessage(container, role, text) {
    if (!container) return;
    const div = document.createElement('div');
    div.className = `flex gap-4 max-w-3xl ${role === 'user' ? 'ml-auto flex-row-reverse' : ''} mb-8`;
    const icon = role === 'user' ? 'person' : 'psychology_alt';
    const bg = role === 'user' ? 'bg-primary text-on-primary shadow-lg' : 'bg-white text-on-surface border border-outline-variant/10 shadow-sm';
    div.innerHTML = `
        <div class="w-10 h-10 rounded-xl ${role === 'user' ? 'bg-surface-container-highest' : 'bg-primary'} flex items-center justify-center flex-shrink-0 shadow-md">
            <span class="material-symbols-outlined ${role === 'user' ? 'text-on-surface-variant' : 'text-on-primary'} text-[22px]">${icon}</span>
        </div>
        <div class="${bg} p-6 rounded-[1.5rem] ${role === 'user' ? 'rounded-tr-none' : 'rounded-tl-none'}">
            <p class="leading-relaxed text-md">${formatAIText(text)}</p>
        </div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function createTypingIndicator() {
    const div = document.createElement('div');
    div.id = 'typing-indicator';
    div.className = 'flex gap-4 max-w-3xl message-entrance mb-8';
    div.innerHTML = `
        <div class="w-10 h-10 rounded-xl bg-primary flex items-center justify-center flex-shrink-0 shadow-md">
            <span class="material-symbols-outlined text-on-primary text-[22px]">psychology_alt</span>
        </div>
        <div class="bg-white p-5 rounded-[1.5rem] rounded-tl-none shadow-sm border border-outline-variant/10 flex items-center gap-1">
            <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
        </div>
    `;
    return div;
}

// --- Recalibration Flowchart ---
async function showRecalibrationFlowchart(proposedSchedule) {
    const chatHistory = document.getElementById('reasoning-chat-history');
    if (!chatHistory) return;
    
    const analyzingDiv = document.createElement('div');
    analyzingDiv.className = 'w-full max-w-xl mx-auto my-6 p-6 text-center animate-fade-in';
    analyzingDiv.innerHTML = `<div class="flex flex-col items-center gap-4"><span class="material-symbols-outlined text-4xl planning-pulse">hub</span><p class="font-bold text-primary tracking-widest uppercase text-xs">Planner Agent: recalibrating temporal nodes...</p></div>`;
    chatHistory.appendChild(analyzingDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    await new Promise(r => setTimeout(r, 1500));
    analyzingDiv.remove();

    const flowDiv = document.createElement('div');
    flowDiv.className = 'w-full max-w-2xl mx-auto my-10 p-10 glass-card bg-surface-container-low/40 border border-primary/20 rounded-[2.5rem] shadow-2xl animate-fade-in relative overflow-hidden';
    flowDiv.innerHTML = `<div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary/0 via-primary/40 to-primary/0"></div>
        <h3 class="font-headline-md text-primary mb-8 text-center italic">Temporal Recalibration Protocol</h3>
        <div class="space-y-0" id="flowchart-nodes-container"></div>
        <div id="recalc-actions" class="mt-10 flex gap-4 opacity-0 transition-opacity duration-700">
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
        const node = document.createElement('div');
        node.className = 'flowchart-node p-5 bg-white shadow-md rounded-2xl mb-2 flex justify-between items-center border border-primary/5';
        node.style.animationDelay = `${i * 100}ms`;
        node.innerHTML = `<div><p class="font-label-sm text-[10px] text-primary font-black uppercase tracking-tighter mb-1">${task.time_slot}</p><p class="font-bold text-on-surface text-lg">${task.name}</p></div><span class="material-symbols-outlined text-secondary fill">update</span>`;
        nodeContainer.appendChild(node);
        if (i < allNewTasks.length - 1) {
            const line = document.createElement('div');
            line.className = 'w-[2px] bg-[#c1c8c1] ml-[19px] h-[20px]';
            nodeContainer.appendChild(line);
        }
        chatHistory.scrollTop = chatHistory.scrollHeight;
        if (i < 8) await new Promise(r => setTimeout(r, 150)); 
    }

    setTimeout(() => { flowDiv.querySelector('#recalc-actions').classList.replace('opacity-0', 'opacity-100'); }, 300);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    return new Promise((resolve) => {
        const confirmBtn = document.getElementById('confirm-recalc');
        const cancelBtn = document.getElementById('cancel-recalc');
        if (confirmBtn) confirmBtn.onclick = async () => {
            flowDiv.innerHTML = `<div class="p-12 text-center animate-pulse text-primary font-bold tracking-widest uppercase">Relaying Approval to Planner Agent...</div>`;
            const res = await authenticatedFetch(`${API_BASE}/schedule/confirm`, { method: 'POST', body: JSON.stringify({ schedule: proposedSchedule }) });
            if (res && res.ok) { 
                flowDiv.remove(); 
                sessionStorage.removeItem('schedule_cache'); 
                showToast("✓ Vault Synchronized."); 
                loadDashboardData(); loadRoutineData();
                resolve(true); 
            } else {
                showToast("Sync failed.");
                resolve(false);
            }
        };
        if (cancelBtn) cancelBtn.onclick = () => { flowDiv.remove(); resolve(false); };
    });
}

// --- Main App Modules ---

async function loadDashboardData() {
    const container = document.getElementById('dashboard-tasks-container');
    if (!container || !window.location.pathname.includes('/dashboard')) return;
    try {
        container.innerHTML = `<div class="p-8 text-center animate-pulse italic opacity-60">Syncing Wellness Vault...</div>`;
        const data = await getSchedule();
        if (!data) return;
        container.innerHTML = '';
        const tasks = data.schedule.morning_block || [];
        if (tasks.length === 0) { container.innerHTML = `<p class="p-4 text-center opacity-60">Block complete.</p>`; return; }
        tasks.slice(0,3).forEach(task => {
            const div = document.createElement('div');
            div.className = 'flex items-center justify-between p-5 rounded-2xl border border-outline-variant/10 bg-white hover:shadow-md cursor-pointer transition-all';
            div.onclick = async () => {
                const res = await authenticatedFetch(`${API_BASE}/adherence/log`, { method: 'POST', body: JSON.stringify({ user_id: "current", completed_practices: [task.name], recommended_practices: [] }) });
                if (res && res.ok) { sessionStorage.removeItem('schedule_cache'); loadDashboardData(); }
            };
            div.innerHTML = `<div class="flex items-center gap-4"><div class="w-10 h-10 rounded-xl bg-primary/5 text-primary flex items-center justify-center"><span class="material-symbols-outlined">spa</span></div><div><p class="font-bold text-on-surface">${task.name}</p><p class="text-[11px] opacity-60 uppercase">${task.time_slot}</p></div></div>`;
            container.appendChild(div);
        });
    } catch(e) { console.error(e); }
}

async function loadRoutineData() {
    const container = document.getElementById('routine-timeline-container');
    if (!container || !window.location.pathname.includes('/routine')) return;
    try {
        container.innerHTML = `<div class="p-20 text-center animate-pulse italic text-primary">Accessing Persistent Vault...</div>`;
        const data = await getSchedule();
        if (!data) return;
        container.innerHTML = '<div class="hidden sm:block absolute left-[120px] top-8 bottom-8 w-[2px] bg-outline-variant/20"></div>';
        ['morning_block', 'midday_block', 'evening_block'].forEach(blockKey => {
            const tasks = data.schedule[blockKey] || [];
            if (tasks.length === 0) return;
            const section = document.createElement('div');
            section.className = 'relative z-10 mb-12 flex flex-col sm:flex-row gap-8';
            let tasksHtml = '';
            tasks.forEach(task => {
                tasksHtml += `
                    <div class="timeline-card bg-white p-6 rounded-[2rem] border border-outline-variant/10 shadow-sm cursor-pointer mb-4" onclick="this.classList.toggle('expanded')">
                        <div class="flex justify-between items-center">
                            <div class="flex items-center gap-4">
                                <div class="w-12 h-12 rounded-2xl bg-primary/5 text-primary flex items-center justify-center"><span class="material-symbols-outlined">self_improvement</span></div>
                                <div><p class="font-bold text-lg">${task.name}</p><p class="text-sm opacity-60">${task.time_slot}</p></div>
                            </div>
                            <span class="material-symbols-outlined expand-icon">expand_more</span>
                        </div>
                        <div class="timeline-card-content"><p class="text-on-surface-variant mb-4">${task.description}</p><div class="bg-surface-container-low p-4 rounded-2xl italic text-sm text-primary">"${task.rationale}"</div>
                        <button class="w-full mt-6 py-3 bg-primary text-on-primary rounded-2xl font-bold" onclick="event.stopPropagation(); authenticatedFetch('${API_BASE}/adherence/log', { method: 'POST', body: JSON.stringify({ user_id: 'current', completed_practices: ['${task.name}'], recommended_practices: [] }) }).then(() => { sessionStorage.removeItem('schedule_cache'); loadRoutineData(); })">Mark Complete</button></div>
                    </div>
                `;
            });
            section.innerHTML = `<div class="sm:w-[120px] text-right pt-4 font-bold text-primary opacity-40">${blockKey.split('_')[0].toUpperCase()}</div><div class="flex-1">${tasksHtml}</div>`;
            container.appendChild(section);
        });
    } catch(e) { console.error(e); }
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
                await typeMessage(chatHistory, "Welcome to the Reasoning Engine. I am Vaidya AI. I have analyzed your biometrics and assessment data. How can I help you understand your routine logic today?");
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
                const indicator = createTypingIndicator();
                chatHistory.appendChild(indicator);
                chatHistory.scrollTop = chatHistory.scrollHeight;
                const chatRes = await authenticatedFetch(`${API_BASE}/chat`, { method: 'POST', body: JSON.stringify({ message: msg }) });
                if (chatRes) {
                    const chatData = await chatRes.json();
                    indicator.remove();
                    await typeMessage(chatHistory, chatData.response);
                    if (chatData.proposed_schedule) {
                        const accepted = await showRecalibrationFlowchart(chatData.proposed_schedule);
                        if (accepted) { await typeMessage(chatHistory, "Approval relayed to Planner Agent. Your vault is now synchronized."); loadRoutineData(); }
                    }
                } else { indicator.remove(); }
            };
        }
    } catch(e) { console.error(e); }
}

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
            if (res.ok) { setToken(data.token); window.location.href = data.has_completed_onboarding ? '/dashboard' : '/onboarding'; }
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
            if (res.ok) { setToken(data.token); window.location.href = '/onboarding'; }
            else showToast("Registration failed");
        };
    }

    loadDashboardData();
    loadRoutineData();
    loadInsightsData();
}

document.addEventListener('DOMContentLoaded', initApp);
if (document.readyState === 'complete' || document.readyState === 'interactive') initApp();

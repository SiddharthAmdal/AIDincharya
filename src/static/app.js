// app.js - Dinacharya AI Frontend Logic

const API_BASE = '/api';

// --- Debug Remote Logging ---
let logQueue = [];
let isSending = false;

async function processLogQueue() {
    if (isSending || logQueue.length === 0) return;
    isSending = true;
    const item = logQueue.shift();
    try {
        await fetch('/api/debug/log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(item)
        });
    } catch(e) {}
    isSending = false;
    processLogQueue();
}

function remoteLog(message, level = 'info') {
    logQueue.push({ message, level });
    processLogQueue();
}

window.onerror = function (message, source, lineno, colno, error) {
    remoteLog(`Error: ${message} at ${source}:${lineno}:${colno} - ${error ? error.stack : ''}`, 'error');
};

window.onunhandledrejection = function (event) {
    const reason = event.reason;
    remoteLog(`Unhandled Promise Rejection: ${reason ? (reason.stack || reason.message || reason) : 'Unknown reason'}`, 'error');
};

const originalConsoleError = console.error;
console.error = function (...args) {
    originalConsoleError.apply(console, args);
    remoteLog(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '), 'error');
};

const originalConsoleLog = console.log;
console.log = function (...args) {
    originalConsoleLog.apply(console, args);
    remoteLog(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '), 'info');
};

remoteLog("app.js initialized and remote logging activated");

// --- Auth Management ---
function getToken() {
    return localStorage.getItem('dinacharya_token');
}

function setToken(token) {
    localStorage.setItem('dinacharya_token', token);
}

function logout() {
    localStorage.removeItem('dinacharya_token');
    window.location.href = '/login';
}

// Protected fetch wrapper
async function authenticatedFetch(url, options = {}) {
    const token = getToken();
    if (!token && !url.includes('/auth/')) {
        window.location.href = '/login';
        return null;
    }
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
        logout();
        return null;
    }
    return res;
}

// --- UI Components ---
function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] bg-inverse-surface text-inverse-on-surface px-6 py-3 rounded-full shadow-2xl font-body-sm text-body-sm animate-fade-in-up border border-outline-variant/20';
    toast.innerText = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.4s ease';
        setTimeout(() => toast.remove(), 400);
    }, 3000);
}

function showCustomConfirm(title, message, onConfirm) {
    const existing = document.getElementById('custom-confirm-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'custom-confirm-modal';
    modal.className = 'fixed inset-0 z-[100] flex items-center justify-center p-4 bg-surface/40 backdrop-blur-md transition-opacity duration-300';
    modal.innerHTML = `
        <div class="glass-card bg-surface/80 border border-outline-variant/30 rounded-3xl p-8 shadow-[0_16px_60px_rgba(0,0,0,0.1)] max-w-sm w-full transform scale-100 transition-transform">
            <div class="flex items-center gap-3 mb-4">
                <div class="w-10 h-10 rounded-full bg-secondary-container flex items-center justify-center text-on-secondary-container">
                    <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">task_alt</span>
                </div>
                <h3 class="font-headline-md text-headline-md text-primary">${title}</h3>
            </div>
            <p class="font-body-md text-body-md text-on-surface-variant mb-8">${message}</p>
            <div class="flex justify-end gap-3">
                <button id="custom-confirm-cancel" class="px-5 py-2.5 rounded-full text-on-surface-variant hover:bg-surface-container-high transition-colors font-label-md text-label-md">Not Yet</button>
                <button id="custom-confirm-ok" class="px-5 py-2.5 bg-primary text-on-primary rounded-full hover:bg-primary/90 transition-colors shadow-md hover:shadow-lg font-label-md text-label-md">Complete Task</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    document.getElementById('custom-confirm-cancel').addEventListener('click', () => {
        modal.style.opacity = '0';
        setTimeout(() => modal.remove(), 300);
    });
    document.getElementById('custom-confirm-ok').addEventListener('click', () => {
        modal.style.opacity = '0';
        setTimeout(() => {
            modal.remove();
            onConfirm();
        }, 300);
    });
}

function initChatUI() {
    const chatContainer = document.createElement('div');
    chatContainer.id = 'ai-chat-window';
    chatContainer.className = 'fixed bottom-24 right-4 md:right-8 z-[90] w-[340px] md:w-[380px] glass-card bg-surface/95 border border-outline-variant/20 rounded-3xl shadow-[0_16px_60px_rgba(0,0,0,0.1)] flex flex-col transition-all duration-300 transform translate-y-8 opacity-0 pointer-events-none';
    chatContainer.style.height = '500px';
    chatContainer.innerHTML = `
        <div class="bg-primary/90 backdrop-blur-sm px-5 py-4 flex justify-between items-center text-on-primary rounded-t-3xl border-b border-primary-fixed/20">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-full bg-primary-fixed/20 flex items-center justify-center">
                    <span class="material-symbols-outlined text-[18px]" style="font-variation-settings: 'FILL' 1;">spa</span>
                </div>
                <div>
                    <div class="font-label-md text-label-md font-bold">Vaidya AI</div>
                    <div class="text-[11px] opacity-80 tracking-wider uppercase">Ayurvedic Guide</div>
                </div>
            </div>
            <button id="chat-close-btn" class="text-on-primary/70 hover:text-on-primary transition-colors p-1 rounded-full hover:bg-primary-fixed/20">
                <span class="material-symbols-outlined text-[20px]">close</span>
            </button>
        </div>
        
        <div id="chat-messages" class="flex-1 overflow-y-auto p-5 space-y-5 text-sm font-body-sm scroll-smooth">
            <div class="flex gap-3">
                <div class="w-8 h-8 rounded-full bg-surface-container flex-shrink-0 flex items-center justify-center text-primary mt-1">
                    <span class="material-symbols-outlined text-[16px]" style="font-variation-settings: 'FILL' 1;">spa</span>
                </div>
                <div class="bg-surface-container-low border border-outline-variant/10 rounded-2xl rounded-tl-sm p-3.5 text-on-surface shadow-sm">
                    Namaste. I am Vaidya AI. How can I help balance your doshas today?
                </div>
            </div>
        </div>
        
        <div class="p-4 border-t border-outline-variant/10 bg-surface/50 rounded-b-3xl backdrop-blur-md">
            <form id="chat-form" class="flex gap-2">
                <input type="text" id="chat-input" class="flex-1 bg-surface-container border border-outline-variant/20 rounded-full px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/40 text-on-surface font-body-sm transition-all" placeholder="Ask about your routine...">
                <button type="submit" class="w-10 h-10 rounded-full bg-primary text-on-primary flex items-center justify-center hover:bg-primary/90 transition-transform hover:scale-105 shadow-sm flex-shrink-0">
                    <span class="material-symbols-outlined text-[18px]">send</span>
                </button>
            </form>
        </div>
    `;
    document.body.appendChild(chatContainer);

    document.getElementById('chat-close-btn').addEventListener('click', toggleChat);
    
    document.getElementById('chat-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = document.getElementById('chat-input');
        const msg = input.value.trim();
        if(!msg) return;
        
        appendChatMessage('user', msg);
        input.value = '';
        
        appendChatMessage('system', 'Thinking...', true);
        const data = await fetchChatAPI(msg);
        
        const loadingMsg = document.getElementById('chat-loading-msg');
        if (loadingMsg) loadingMsg.remove();
        
        if (data && data.response) {
            appendChatMessage('system', data.response);
        } else {
            appendChatMessage('system', 'Apologies, my mind is scattered right now. Please try again.');
        }
    });
}

let isChatOpen = false;
function toggleChat() {
    const chatWindow = document.getElementById('ai-chat-window');
    if (!chatWindow) return;
    
    isChatOpen = !isChatOpen;
    if (isChatOpen) {
        chatWindow.classList.remove('opacity-0', 'translate-y-8', 'pointer-events-none');
        chatWindow.classList.add('opacity-100', 'translate-y-0');
        setTimeout(() => document.getElementById('chat-input').focus(), 300);
    } else {
        chatWindow.classList.add('opacity-0', 'translate-y-8', 'pointer-events-none');
        chatWindow.classList.remove('opacity-100', 'translate-y-0');
    }
}

function appendChatMessage(role, text, isLoading=false) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    if (isLoading) div.id = 'chat-loading-msg';
    
    if (role === 'user') {
        div.className = 'flex gap-3 justify-end animate-fade-in-up';
        div.innerHTML = `
            <div class="bg-primary-container border border-primary-fixed/20 text-on-primary-container rounded-2xl rounded-tr-sm p-3.5 shadow-sm">
                ${text}
            </div>
        `;
    } else {
        div.className = 'flex gap-3 animate-fade-in-up';
        div.innerHTML = `
            <div class="w-8 h-8 rounded-full bg-surface-container flex-shrink-0 flex items-center justify-center text-primary mt-1">
                <span class="material-symbols-outlined text-[16px]" style="font-variation-settings: 'FILL' 1;">spa</span>
            </div>
            <div class="bg-surface-container-low border border-outline-variant/10 rounded-2xl rounded-tl-sm p-3.5 text-on-surface shadow-sm ${isLoading ? 'animate-pulse text-on-surface-variant' : ''}">
                ${text}
            </div>
        `;
    }
    
    container.appendChild(div);
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
}

// --- API Wrappers ---
async function fetchChatAPI(message) {
    const payload = { message: message, chat_history: [] };
    const res = await authenticatedFetch(`${API_BASE}/chat`, {
        method: 'POST',
        body: JSON.stringify(payload)
    });
    if (!res) return null;
    return await res.json();
}

async function logAdherence(completedTask, taskCardElement) {
    const payload = {
        completed_practices: [completedTask],
        recommended_practices: ["meditation", "warm_lemon_water", "yoga", "abhyanga"] // Mock baseline for now
    };
    const res = await authenticatedFetch(`${API_BASE}/adherence/log`, {
        method: 'POST',
        body: JSON.stringify(payload)
    });
    if (!res) return;
    
    const data = await res.json();
    showToast("✓ Task logged successfully");
    
    // VISUAL UPDATE FOR TASK CARD
    if (taskCardElement) {
        // Find icon and change to checkmark
        const iconWrap = taskCardElement.querySelector('.bg-surface-container, .bg-secondary-container, .bg-primary-fixed');
        if (iconWrap) {
            iconWrap.className = 'w-12 h-12 rounded-2xl bg-primary flex items-center justify-center text-on-primary shadow-lg';
            const icon = iconWrap.querySelector('.material-symbols-outlined');
            if (icon) {
                icon.innerText = 'check_circle';
                icon.style.fontVariationSettings = "'FILL' 1";
            }
        }
        
        // Find title and add strikethrough
        const title = taskCardElement.querySelector('h3, h4');
        if (title) {
            title.classList.add('line-through', 'text-on-surface-variant', 'opacity-60');
        }
        
        // Dim the card slightly
        taskCardElement.classList.add('bg-surface-container-low', 'opacity-70', 'border-primary/20');
        taskCardElement.classList.remove('bg-surface-container-lowest', 'bg-white');
    }
}

async function loadDashboardData() {
    console.log("loadDashboardData starting. Pathname: " + window.location.pathname);
    if (!window.location.pathname.includes('/dashboard')) {
        console.log("loadDashboardData exiting early: path does not include /dashboard");
        return;
    }

    try {
        const payload = {
            user_id: "current_user", 
            context: {
                season: "Hemanta",
                weather: "Cold and dry",
                temperature_c: 15.0,
                calendar_events: [],
                self_report_symptoms: []
            },
            wearable_telemetry_7d: {}
        };

        console.log("loadDashboardData: sending request with payload:", JSON.stringify(payload));
        const res = await authenticatedFetch(`${API_BASE}/schedule/generate`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        console.log("loadDashboardData: fetch response status: " + (res ? res.status : "null/undefined"));
        if (!res) {
            console.log("loadDashboardData exiting: res is null");
            return;
        }
        const data = await res.json();
        console.log("loadDashboardData: schedule data successfully parsed:", JSON.stringify(data));
        
        // Dynamically Render Dashboard Tasks
        const header = document.querySelector('h3.font-headline-md');
        console.log("loadDashboardData: Today's Focus header element:", header ? "Found (" + header.textContent + ")" : "Not Found");
        if (header && header.textContent.includes("Today's Focus")) {
            const container = header.parentElement.nextElementSibling;
            console.log("loadDashboardData: Today's Focus container element:", container ? "Found (" + container.className + ")" : "Not Found");
            if (container) {
                container.innerHTML = ''; // Clear hardcoded HTML tasks
                
                // Get tasks
                let tasks = [];
                if (data.schedule && data.schedule.morning_block) {
                    tasks = data.schedule.morning_block;
                } else if (Array.isArray(data.schedule)) {
                    tasks = data.schedule;
                }
                console.log("loadDashboardData: Extracted tasks list:", JSON.stringify(tasks));
                
                if (tasks.length === 0) {
                    container.innerHTML = '<p class="text-on-surface-variant font-body-sm p-4">No tasks generated. Please check your assessment.</p>';
                }

                tasks.slice(0, 3).forEach(task => {
                    const taskName = task.title || task.practice_name || task.name || "Daily Practice";
                    const taskTime = task.time_slot || "15m";
                    console.log("loadDashboardData: rendering task item:", taskName);
                    
                    const taskDiv = document.createElement('div');
                    taskDiv.className = 'flex items-center justify-between p-4 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest/50 hover:bg-surface-container-lowest transition-all group cursor-pointer';
                    
                    // Task click to complete
                    taskDiv.addEventListener('click', () => {
                        showCustomConfirm('Log Practice', `Did you complete '${taskName}'?`, () => logAdherence(taskName, taskDiv));
                    });
                    
                    taskDiv.innerHTML = `
                        <div class="flex items-center gap-4">
                            <div class="w-10 h-10 rounded-xl bg-surface-container flex items-center justify-center text-primary group-hover:bg-primary-container group-hover:text-on-primary-container transition-colors">
                                <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">self_improvement</span>
                            </div>
                            <div>
                                <h4 class="font-label-md text-label-md text-on-surface mb-0.5">${taskName}</h4>
                                <p class="font-body-sm text-body-sm text-on-surface-variant">${taskTime}</p>
                            </div>
                        </div>
                        <button class="w-8 h-8 rounded-full border border-outline/30 flex items-center justify-center text-outline hover:border-primary hover:text-primary transition-colors">
                            <span class="material-symbols-outlined text-[18px]">check</span>
                        </button>
                    `;
                    container.appendChild(taskDiv);
                });
            }
        }
        
        // Update Dosha State UI
        const doshaTexts = Array.from(document.querySelectorAll('span.font-headline-md.text-primary'));
        const doshaText = doshaTexts.find(el => el.textContent.includes('Aggravated') || el.textContent.includes('Balanced') || el.textContent.includes('Vata') || el.textContent.includes('Pitta') || el.textContent.includes('Kapha'));
        console.log("loadDashboardData: doshaText span found:", doshaText ? "Found (" + doshaText.textContent + ")" : "Not Found");
        
        if (doshaText && data.dosha_profile && data.dosha_profile.vikriti_flags) {
            const flags = data.dosha_profile.vikriti_flags;
            let dominant = "Balanced";
            if (flags.vata_aggravated) dominant = "Vata Aggravated";
            else if (flags.pitta_aggravated) dominant = "Pitta Aggravated";
            else if (flags.kapha_aggravated) dominant = "Kapha Aggravated";
            console.log("loadDashboardData: updating dominant dosha text to:", dominant);
            doshaText.textContent = dominant;
        }
    } catch (err) {
        console.error("Error loading dashboard data:", err);
    }
}

async function loadRoutineData() {
    console.log("loadRoutineData starting. Pathname: " + window.location.pathname);
    if (!window.location.pathname.includes('/routine')) {
        console.log("loadRoutineData exiting early: path does not include /routine");
        return;
    }

    try {
        const payload = {
            user_id: "current_user", 
            context: {
                season: "Hemanta",
                weather: "Cold and dry",
                temperature_c: 15.0,
                calendar_events: [],
                self_report_symptoms: []
            },
            wearable_telemetry_7d: {}
        };

        console.log("loadRoutineData: sending request with payload:", JSON.stringify(payload));
        const res = await authenticatedFetch(`${API_BASE}/schedule/generate`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        console.log("loadRoutineData: fetch response status: " + (res ? res.status : "null/undefined"));
        if (!res) {
            console.log("loadRoutineData exiting: res is null");
            return;
        }
        const data = await res.json();
        console.log("loadRoutineData: schedule data successfully parsed:", JSON.stringify(data));
        
        const container = document.querySelector('.relative.max-w-3xl');
        console.log("loadRoutineData: timeline container element:", container ? "Found" : "Not Found");
        if (!container) return;
        
        // Retain the timeline vertical line but clear the hardcoded tasks
        container.innerHTML = '<div class="hidden sm:block absolute left-[120px] top-8 bottom-8 w-[2px] bg-outline-variant/30 z-0"></div>';
        
        const schedule = data.schedule || {};
        const blocks = [
            { id: "morning", title: "Morning", time: "06:00", icon: "wb_twilight", tasks: schedule.morning_block || [] },
            { id: "midday", title: "Midday", time: "12:00", icon: "light_mode", tasks: schedule.midday_block || [] },
            { id: "evening", title: "Evening", time: "18:00", icon: "dark_mode", tasks: schedule.evening_block || [] }
        ];
        
        blocks.forEach(block => {
            console.log(`loadRoutineData: processing block '${block.id}' with ${block.tasks.length} tasks`);
            if (block.tasks.length === 0) return;
            
            const sectionDiv = document.createElement('div');
            sectionDiv.className = 'relative z-10 mb-12 sm:mb-16';
            
            let tasksHtml = '';
            block.tasks.forEach(task => {
                const taskName = task.title || task.practice_name || task.name || "Daily Practice";
                const taskDesc = task.description || task.reason || "Recommended based on your current Dosha state.";
                const rationale = task.rationale || "Helps balance the doshas.";
                console.log(`loadRoutineData: building HTML for task '${taskName}'`);
                
                tasksHtml += `
                    <div class="timeline-card bg-surface-container-lowest rounded-3xl p-6 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-outline-variant/10 cursor-pointer group" onclick="this.classList.toggle('expanded')">
                        <div class="flex justify-between items-start gap-4">
                            <div class="flex items-start gap-4">
                                <div class="w-12 h-12 rounded-2xl bg-surface-container flex items-center justify-center text-primary group-hover:bg-primary-container group-hover:text-on-primary-container transition-colors">
                                    <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">self_improvement</span>
                                </div>
                                <div>
                                    <h3 class="font-headline-md text-headline-md text-on-surface mb-1">${taskName}</h3>
                                    <div class="flex items-center gap-3 text-on-surface-variant font-label-sm text-label-sm">
                                        <span class="flex items-center gap-1"><span class="material-symbols-outlined text-[16px]">schedule</span> ${task.time_slot || "15m"}</span>
                                        <span class="px-2 py-0.5 rounded-full bg-surface-variant text-on-surface">AI Guided</span>
                                    </div>
                                </div>
                            </div>
                            <button class="text-outline hover:text-primary transition-colors p-2 rounded-full hover:bg-surface-container">
                                <span class="material-symbols-outlined expand-icon">expand_more</span>
                            </button>
                        </div>
                        <div class="timeline-card-content">
                            <div class="pt-4 border-t border-outline-variant/20 mt-4">
                                <p class="font-body-md text-body-md text-on-surface-variant mb-4">${taskDesc}</p>
                                <div class="flex items-start gap-3 bg-surface-container-low p-4 rounded-2xl relative overflow-hidden">
                                    <div class="absolute inset-0 opacity-10 bg-gradient-to-r from-primary-container to-transparent"></div>
                                    <span class="material-symbols-outlined text-primary mt-0.5">auto_awesome</span>
                                    <div>
                                        <h4 class="font-label-md text-label-md text-primary mb-1">AI Insight</h4>
                                        <p class="font-body-sm text-body-sm text-on-surface-variant">${rationale}</p>
                                    </div>
                                </div>
                                <div class="mt-4 flex gap-3">
                                    <button class="log-practice-btn px-4 py-2 border border-outline text-on-surface rounded-full font-label-sm text-label-sm hover:bg-surface-container transition-colors">Log Practice</button>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            sectionDiv.innerHTML = `
                <div class="flex flex-col sm:flex-row items-start gap-4 sm:gap-12">
                    <div class="sm:w-[100px] flex sm:justify-end items-center sm:items-start pt-2">
                        <div class="flex items-center gap-3 sm:flex-col sm:items-end">
                            <span class="font-headline-md text-headline-md text-primary">${block.time}</span>
                            <div class="flex items-center gap-2 text-on-surface-variant">
                                <span class="material-symbols-outlined text-label-md">${block.icon}</span>
                                <span class="font-label-sm text-label-sm uppercase tracking-wider">${block.title}</span>
                            </div>
                        </div>
                    </div>
                    <div class="flex-1 flex flex-col gap-6 w-full">
                        ${tasksHtml}
                    </div>
                </div>
            `;
            container.appendChild(sectionDiv);
        });
        
        // Attach click listeners to the log practice buttons dynamically
        container.querySelectorAll('.log-practice-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation(); // prevent card from collapsing
                const card = e.target.closest('.timeline-card');
                const taskName = card.querySelector('h3').textContent;
                console.log(`loadRoutineData: attaching click listener to log-practice-btn for task '${taskName}'`);
                showCustomConfirm('Log Practice', `Did you complete '${taskName}'?`, () => logAdherence(taskName, card));
            });
        });
        console.log("loadRoutineData completed successfully.");
        
    } catch (err) {
        console.error("Error loading routine data:", err);
    }
}

function initApp() {
    console.log("initApp called. Current pathname is: " + window.location.pathname);
    
    // Exclude auth checking on login page
    if (!window.location.pathname.includes('/login') && !window.location.pathname.includes('/onboarding') && window.location.pathname !== '/') {
        if (!getToken()) {
            console.log("initApp: No token found. Redirecting to /login");
            window.location.href = '/login';
            return;
        }
    } else {
        if (getToken() && (window.location.pathname === '/' || window.location.pathname.includes('/login'))) {
            console.log("initApp: Token found on public page. Redirecting to /dashboard");
            window.location.href = '/dashboard';
            return;
        }
    }
    
    initChatUI();
    loadDashboardData();
    loadRoutineData();
    
    // Wire up landing page navigation
    const buttons = document.querySelectorAll('button');
    console.log("initApp: found buttons count:", buttons.length);
    buttons.forEach((btn, idx) => {
        const txt = btn.textContent;
        if (txt) {
            console.log(`initApp: checking button ${idx} text: '${txt.trim()}'`);
            if (txt.includes('Get Started') || txt.includes('Take Prakriti Assessment')) {
                console.log(`initApp: wiring button ${idx} to /dashboard`);
                btn.addEventListener('click', () => window.location.href = '/dashboard');
            } else if (txt.includes('View Full Routine')) {
                console.log(`initApp: wiring button ${idx} to /routine`);
                btn.addEventListener('click', () => window.location.href = '/routine');
            }
        }
    });

    // Wire up sidebar links safely
    const links = document.querySelectorAll('a');
    console.log("initApp: found links count:", links.length);
    links.forEach((link, idx) => {
        const txt = link.textContent;
        if (txt) {
            console.log(`initApp: checking link ${idx} text: '${txt.trim()}'`);
            if (txt.includes('Dashboard')) {
                console.log(`initApp: wiring link ${idx} to /dashboard`);
                link.addEventListener('click', (e) => { 
                    console.log("initApp: Dashboard link clicked");
                    e.preventDefault(); 
                    window.location.href = '/dashboard'; 
                });
            } else if (txt.includes('Routine')) {
                console.log(`initApp: wiring link ${idx} to /routine`);
                link.addEventListener('click', (e) => { 
                    console.log("initApp: Routine link clicked");
                    e.preventDefault(); 
                    window.location.href = '/routine'; 
                });
            } else if (txt.includes('Insights')) {
                console.log(`initApp: wiring link ${idx} to /reasoning`);
                link.addEventListener('click', (e) => { 
                    console.log("initApp: Insights link clicked");
                    e.preventDefault(); 
                    window.location.href = '/reasoning'; 
                });
            } else if (txt.includes('Profile')) {
                console.log(`initApp: wiring link ${idx} to logout`);
                link.addEventListener('click', (e) => { 
                    console.log("initApp: Profile link clicked");
                    e.preventDefault(); 
                    if(confirm("Logout from Dinacharya?")) logout(); 
                });
            }
        }
    });

    // Wire floating action buttons for Chat
    const chatBtns = document.querySelectorAll('button[aria-label="Open AI Assistant"]');
    console.log("initApp: found Open AI Assistant chat buttons count:", chatBtns.length);
    chatBtns.forEach((btn, idx) => {
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        newBtn.addEventListener('click', toggleChat);
        console.log(`initApp: wired Open AI Assistant button ${idx}`);
    });

    // Wire adherence tasks in the Routine page
    const tasks = document.querySelectorAll('.timeline-card');
    console.log("initApp: found timeline-card tasks count (placeholders):", tasks.length);
    tasks.forEach((task, idx) => {
        const newBtn = task.cloneNode(true);
        task.parentNode.replaceChild(newBtn, task);
        
        newBtn.addEventListener('click', (e) => {
            console.log(`initApp: placeholder timeline-card ${idx} clicked`);
            if (newBtn.classList.contains('timeline-card')) {
                newBtn.classList.toggle('expanded');
            } else {
                const taskName = newBtn.querySelector('h4')?.textContent || "Daily Task";
                showCustomConfirm('Log Practice', `Did you complete '${taskName}'?`, () => logAdherence(taskName, newBtn));
            }
        });
        
        const actionBtns = newBtn.querySelectorAll('button');
        actionBtns.forEach((ab, abIdx) => {
            ab.addEventListener('click', (e) => {
                e.stopPropagation(); // prevent card expansion
                const taskName = newBtn.querySelector('h3')?.textContent || "Task";
                console.log(`initApp: placeholder timeline-card ${idx} actionBtn ${abIdx} clicked for task ${taskName}`);
                if (ab.textContent.includes('Log Details') || ab.textContent.includes('Mark Complete') || ab.textContent.includes('Completed')) {
                    showCustomConfirm('Log Practice', `Would you like to record '${taskName}' in your adherence history?`, () => {
                        logAdherence(taskName, newBtn);
                    });
                } else if (ab.textContent.includes('Start Timer')) {
                    showToast(`Timer started for ${taskName}`);
                } else if (ab.classList.contains('expand-icon') || ab.querySelector('.expand-icon')) {
                    newBtn.classList.toggle('expanded');
                }
            });
        });
    });
    console.log("initApp completed setup.");
}

// --- DOM Initialization ---
if (document.readyState === 'loading') {
    console.log("Document loading. Registering DOMContentLoaded event.");
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    console.log("Document already loaded. Running initApp directly.");
    initApp();
}

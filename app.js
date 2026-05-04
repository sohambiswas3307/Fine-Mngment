/* ============================================
   E Parivahan — Application Logic (API-backed)
   ============================================ */

const API = 'http://localhost:5000/api';

// ============================================
// API Helper
// ============================================
// ============================================
// API Helper
// ============================================
async function api(endpoint, method = 'GET', body = null) {
    // Automatically inject owner_id if user is not admin
    const user = Auth.getUser();
    if (user && user.role !== 'Admin' && method === 'GET') {
        const separator = endpoint.includes('?') ? '&' : '?';
        endpoint += `${separator}owner_id=${user.owner_id}`;
    }

    const opts = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`${API}${endpoint}`, opts);
    return res.json();
}

// ============================================
// Fine Amounts & Violation Types
// ============================================
const FINE_AMOUNTS = {
    'Signal Jumping': 1000, 'Overspeeding': 2000, 'Helmetless Riding': 500,
    'Illegal Parking': 500, 'Lane Violation': 1000, 'Wrong Way Driving': 2000,
    'Using Mobile Phone': 1500,
};
const VIOLATION_TYPES = Object.keys(FINE_AMOUNTS);

// ============================================
// Utility Functions
// ============================================
function formatCurrency(n) {
    return '₹' + Number(n).toLocaleString('en-IN');
}

function formatDate(d) {
    return d.toISOString().split('T')[0];
}

function toYMDLocal(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

const REMINDERS_STORAGE_KEY = 'trafficai-daily-reminders';
const REMINDERS_OPTS_KEY = 'trafficai-reminders-opts';

const DailyReminders = {
    selectedDate: null,
    showDone: false,
    _inited: false,

    tryInit() {
        const u = Auth.getUser();
        if (!u || u.role === 'Admin' || this._inited) return;
        this.init();
    },

    init() {
        if (this._inited) return;
        if (Auth.getUser()?.role === 'Admin') return;
        this.weekEl = document.getElementById('reminders-week');
        this.listEl = document.getElementById('reminders-list');
        this.inputEl = document.getElementById('reminder-text-input');
        this.toggleEl = document.getElementById('reminders-show-done-toggle');
        if (!this.weekEl || !this.listEl) return;

        const opts = JSON.parse(localStorage.getItem(REMINDERS_OPTS_KEY) || '{}');
        this.showDone = !!opts.showDone;
        if (this.toggleEl) {
            this.toggleEl.setAttribute('aria-pressed', this.showDone ? 'true' : 'false');
            this.toggleEl.addEventListener('click', () => {
                this.showDone = !this.showDone;
                this.toggleEl.setAttribute('aria-pressed', this.showDone ? 'true' : 'false');
                localStorage.setItem(REMINDERS_OPTS_KEY, JSON.stringify({ showDone: this.showDone }));
                this.renderList();
            });
        }

        this.selectedDate = toYMDLocal(new Date());

        document.getElementById('reminder-add-btn')?.addEventListener('click', () => this.add());

        this.inputEl?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.add();
            }
        });

        this.weekEl.addEventListener('click', (e) => {
            const btn = e.target.closest('.reminders-day-btn');
            if (!btn?.dataset.date) return;
            this.selectedDate = btn.dataset.date;
            this.renderWeek();
            this.renderList();
        });

        this.listEl.addEventListener('change', (e) => {
            const t = e.target;
            if (t.classList.contains('reminder-check')) {
                this.toggleDone(t.dataset.id, t.checked);
            }
        });

        this.listEl.addEventListener('click', (e) => {
            const del = e.target.closest('.reminder-delete');
            if (del?.dataset.id) this.remove(del.dataset.id);
        });

        this.renderWeek();
        this.renderList();
        this._inited = true;
    },

    load() {
        try {
            const raw = localStorage.getItem(REMINDERS_STORAGE_KEY);
            if (!raw) return [];
            const arr = JSON.parse(raw);
            return Array.isArray(arr) ? arr : [];
        } catch {
            return [];
        }
    },

    save(list) {
        localStorage.setItem(REMINDERS_STORAGE_KEY, JSON.stringify(list));
    },

    newId() {
        return typeof crypto !== 'undefined' && crypto.randomUUID
            ? crypto.randomUUID()
            : `r-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    },

    add() {
        const text = (this.inputEl?.value || '').trim();
        if (!text) {
            showToast('Enter reminder text', 'info');
            return;
        }
        const list = this.load();
        list.push({
            id: this.newId(),
            date: this.selectedDate || toYMDLocal(new Date()),
            text,
            done: false,
        });
        this.save(list);
        this.inputEl.value = '';
        this.renderList();
        showToast('Reminder added', 'success');
    },

    toggleDone(id, done) {
        const list = this.load().map((r) => (r.id === id ? { ...r, done } : r));
        this.save(list);
        this.renderList();
    },

    remove(id) {
        const list = this.load().filter((r) => r.id !== id);
        this.save(list);
        this.renderList();
    },

    renderWeek() {
        const today = toYMDLocal(new Date());
        const frag = document.createDocumentFragment();
        for (let i = 0; i < 7; i++) {
            const d = new Date();
            d.setHours(12, 0, 0, 0);
            d.setDate(d.getDate() + i);
            const ymd = toYMDLocal(d);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'reminders-day-btn';
            btn.dataset.date = ymd;
            const dow = d.toLocaleDateString(undefined, { weekday: 'short' });
            const dom = d.getDate();
            if (ymd === today) btn.classList.add('reminders-day--today');
            if (ymd === this.selectedDate) btn.classList.add('reminders-day--selected');
            btn.innerHTML = `<span class="reminders-day-dow">${dow}</span><span>${dom}</span>`;
            frag.appendChild(btn);
        }
        this.weekEl.innerHTML = '';
        this.weekEl.appendChild(frag);
    },

    renderList() {
        const day = this.selectedDate;
        let list = this.load().filter((r) => r.date === day);
        if (!this.showDone) list = list.filter((r) => !r.done);
        list.sort((a, b) => (a.done === b.done ? 0 : a.done ? 1 : -1));

        if (list.length === 0) {
            this.listEl.innerHTML =
                '<li class="reminders-empty">No reminders for this day.</li>';
            return;
        }

        this.listEl.innerHTML = list
            .map(
                (r) => `
            <li class="reminder-item${r.done ? ' reminder-item--done' : ''}">
                <input type="checkbox" class="reminder-check" data-id="${r.id}" ${r.done ? 'checked' : ''} aria-label="Mark done">
                <span class="reminder-text">${escapeHtml(r.text)}</span>
                <button type="button" class="reminder-delete" data-id="${r.id}" aria-label="Remove">×</button>
            </li>`
            )
            .join('');
    },
};

// ============================================
// Toast Notifications
// ============================================
function showToast(msg, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icons = { success: '✓', error: '✕', info: 'ℹ' };
    toast.innerHTML = `<span>${icons[type] || '•'}</span> ${msg}`;
    container.appendChild(toast);
    
    // Minimal styles for toast
    Object.assign(toast.style, {
        padding: '12px 20px',
        borderRadius: '12px',
        background: 'var(--bg-card)',
        color: 'var(--text-main)',
        border: '1px solid var(--border-main)',
        boxShadow: 'var(--shadow-main)',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        fontSize: '0.875rem',
        fontWeight: '500',
        backdropFilter: 'var(--glass-blur)',
        zIndex: '2000'
    });
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============================================
// Authentication System
// ============================================
const Auth = {
    init() {
        const loginForm = document.getElementById('login-form');
        const registerForm = document.getElementById('register-form');
        const logoutBtn = document.getElementById('logout-btn');
        const toggleBtn = document.getElementById('toggle-register');
        const loginDesc = document.getElementById('login-desc');

        if (toggleBtn) {
            toggleBtn.onclick = (e) => {
                e.preventDefault();
                const isLogin = !loginForm.classList.contains('hidden');
                if (isLogin) {
                    loginForm.classList.add('hidden');
                    loginForm.style.display = 'none';
                    registerForm.classList.remove('hidden');
                    registerForm.style.display = 'block';
                    toggleBtn.textContent = 'Already have an account? Login';
                    loginDesc.textContent = 'Create your E Parivahan account.';
                } else {
                    loginForm.classList.remove('hidden');
                    loginForm.style.display = 'block';
                    registerForm.classList.add('hidden');
                    registerForm.style.display = 'none';
                    toggleBtn.textContent = "Don't have an account? Register now";
                    loginDesc.textContent = 'Sign in to access your traffic portal.';
                }
            };
        }

        if (loginForm) {
            loginForm.onsubmit = async (e) => {
                e.preventDefault();
                const username = document.getElementById('login-username').value;
                const password = document.getElementById('login-password').value;
                
                try {
                    const res = await api('/login', 'POST', { username, password });
                    if (res.success) {
                        localStorage.setItem('trafficai-user', JSON.stringify(res.user));
                        showToast(`Welcome back, ${res.user.username}!`, 'success');
                        this.renderUI();
                        location.hash = '#dashboard';
                    } else {
                        showToast(res.message, 'error');
                    }
                } catch (err) {
                    showToast('Connection error', 'error');
                }
            };
        }

        if (registerForm) {
            registerForm.onsubmit = async (e) => {
                e.preventDefault();
                const data = {
                    username:      document.getElementById('reg-username').value,
                    password:      document.getElementById('reg-password').value,
                    name:          document.getElementById('reg-name').value,
                    license_no:    document.getElementById('reg-license').value,
                    phone:         document.getElementById('reg-phone').value,
                    email:         document.getElementById('reg-email').value,
                    vehicle_reg:   document.getElementById('reg-veh-no').value,
                    vehicle_type:  document.getElementById('reg-veh-type').value,
                    vehicle_color: document.getElementById('reg-veh-color').value
                };

                try {
                    const res = await api('/register', 'POST', data);
                    if (res.success) {
                        showToast('Account created! You can now login.', 'success');
                        toggleBtn.click(); // Switch back to login
                    } else {
                        showToast(res.message, 'error');
                    }
                } catch (err) {
                    showToast('Registration failed', 'error');
                }
            };
        }

        if (logoutBtn) {
            logoutBtn.onclick = () => {
                localStorage.removeItem('trafficai-user');
                location.reload();
            };
        }

        this.renderUI();
    },

    getUser() {
        const data = localStorage.getItem('trafficai-user');
        return data ? JSON.parse(data) : null;
    },

    renderUI() {
        const user = this.getUser();
        const appContainer = document.getElementById('app-container');
        const loginPage = document.getElementById('login-page');

        if (user) {
            appContainer.style.display = 'flex';
            appContainer.classList.remove('hidden');
            loginPage.style.display = 'none';
            
            // Update sidebar profile
            document.querySelector('.user-name').textContent = user.username;
            document.querySelector('.user-role').textContent = user.role === 'Admin' ? 'Administrator' : 'Vehicle Owner';
            document.querySelector('.avatar').textContent = user.username.substring(0, 2).toUpperCase();

            syncSidebarStatLabels(user.role === 'Admin');

            // Restricted elements (menu items and buttons)
            document.querySelectorAll('[data-role="Admin"]').forEach(item => {
                item.style.display = user.role === 'Admin' ? 'flex' : 'none';
            });
        } else {
            appContainer.style.display = 'none';
            loginPage.style.display = 'flex';
        }
        syncDashboardRoleWidgets(user);
    }
};

// ============================================
// Theme System
// ============================================
const Theme = {
    init() {
        const saved = localStorage.getItem('trafficai-theme') || 'dark';
        this.set(saved);
        
        const toggle = document.getElementById('theme-toggle');
        if (toggle) {
            toggle.onclick = (e) => {
                e.preventDefault();
                const current = document.documentElement.getAttribute('data-theme');
                this.set(current === 'light' ? 'dark' : 'light');
                showToast(`Switched to ${current === 'light' ? 'dark' : 'light'} mode`, 'info');
            };
        }
    },
    set(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('trafficai-theme', theme);
    }
};

// ============================================
// Modal System
// ============================================
const Modal = {
    overlay: null, form: null, titleEl: null, bodyEl: null,
    _onSubmit: null,

    init() {
        this.overlay = document.getElementById('modal-overlay');
        this.form = document.getElementById('modal-form');
        this.titleEl = document.getElementById('modal-title');
        this.bodyEl = document.getElementById('modal-body');

        document.getElementById('modal-close').onclick = () => this.close();
        document.getElementById('modal-cancel').onclick = () => this.close();
        this.overlay.addEventListener('click', (e) => { if (e.target === this.overlay) this.close(); });
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            if (this._onSubmit) this._onSubmit();
        });
    },

    open(title, fields, data, onSubmit) {
        this.titleEl.textContent = title;
        this._onSubmit = onSubmit;
        let html = '';
        fields.forEach(f => {
            const val = data[f.key] || '';
            if (f.type === 'select') {
                const options = f.options.map(o =>
                    `<option value="${o.value}" ${val === o.value ? 'selected' : ''}>${o.label}</option>`
                ).join('');
                html += `<div class="form-group"><label>${f.label}</label><select id="field-${f.key}" ${f.required ? 'required' : ''}><option value="">— Select —</option>${options}</select></div>`;
            } else {
                html += `<div class="form-group"><label>${f.label}</label><input type="${f.type || 'text'}" id="field-${f.key}" value="${val}" ${f.required ? 'required' : ''} ${f.readonly ? 'readonly' : ''} placeholder="${f.placeholder || ''}"></div>`;
            }
        });
        this.bodyEl.innerHTML = html;
        this.overlay.classList.add('active');
        const firstInput = this.bodyEl.querySelector('input:not([readonly]), select');
        if (firstInput) setTimeout(() => firstInput.focus(), 100);
    },

    getValues(fields) {
        const data = {};
        fields.forEach(f => {
            data[f.key] = document.getElementById(`field-${f.key}`).value.trim();
        });
        return data;
    },

    close() {
        this.overlay.classList.remove('active');
        this._onSubmit = null;
    }
};

// ============================================
// Admin dashboard: live city map (fine / violation hotspots)
// ============================================
const AdminFineMap = {
    map: null,
    heatLayer: null,
    markersLayer: null,
    pollTimer: null,
    _scheduled: false,

    scheduleInit() {
        if (Auth.getUser()?.role !== 'Admin') return;
        const run = () => {
            this._scheduled = false;
            if (!document.getElementById('leaflet-fine-map')) return;
            if (typeof L === 'undefined') return;
            if (!this.map) this._createMap();
            this.refresh();
            this.invalidate();
        };
        if (this._scheduled) return;
        this._scheduled = true;
        requestAnimationFrame(() => setTimeout(run, 150));
    },

    _createMap() {
        const el = document.getElementById('leaflet-fine-map');
        if (!el || this.map) return;
        const [lat, lng] = [12.9716, 77.5946];
        this.map = L.map(el, { scrollWheelZoom: true, zoomControl: false }).setView([lat, lng], 12);
        
        // Using CartoDB Dark Matter - High quality, free, no key needed
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 20
        }).addTo(this.map);

        L.control.zoom({ position: 'bottomright' }).addTo(this.map);

        this.markersLayer = L.layerGroup().addTo(this.map);
        this.map.whenReady(() => this.map.invalidateSize());
        
        if (this.pollTimer) clearInterval(this.pollTimer);
        this.pollTimer = setInterval(() => {
            const page = (location.hash || '#dashboard').replace(/^#/, '') || 'dashboard';
            if (Auth.getUser()?.role === 'Admin' && page === 'dashboard') this.refresh();
        }, 30000);
    },

    invalidate() {
        if (this.map) setTimeout(() => this.map.invalidateSize(), 200);
    },

    async refresh() {
        if (!this.map || Auth.getUser()?.role !== 'Admin') return;
        try {
            const res = await fetch(`${API}/map/hotspots`);
            if (!res.ok) return;
            const data = await res.json();
            if (!data.ok || !data.points) return;
            
            const city = data.city || {};
            if (city.center && Array.isArray(city.center)) {
                this.map.setView(city.center, city.defaultZoom || 12);
            }
            
            this.markersLayer.clearLayers();
            if (this.heatLayer) {
                this.map.removeLayer(this.heatLayer);
                this.heatLayer = null;
            }

            const heatPts = data.points.map(p => [p.lat, p.lng, Math.max(0.12, p.heat || 0)]);
            if (typeof L.heatLayer === 'function' && heatPts.length) {
                this.heatLayer = L.heatLayer(heatPts, {
                    radius: 35,
                    blur: 20,
                    maxZoom: 17,
                    gradient: { 0.4: '#4b39b5', 0.65: '#ff5f6d', 1: '#ff2d43' }
                }).addTo(this.map);
            }

            data.points.forEach((p) => {
                const r = 8 + Math.min(30, (p.violations || 0) * 3);
                const circle = L.circleMarker([p.lat, p.lng], {
                    radius: r,
                    color: '#ff5f6d',
                    fillColor: '#4b39b5',
                    fillOpacity: 0.25,
                    weight: 2,
                });
                const pending = Number(p.pendingAmount || 0).toLocaleString('en-IN');
                circle.bindPopup(
                    `<div style="color: #111827; font-family: Poppins, sans-serif;">
                        <strong style="display: block; margin-bottom: 4px;">${p.location}</strong>
                        <div style="font-size: 11px;">
                            Violations: ${p.violations}<br/>
                            Fines: ${p.finesTotal}<br/>
                            Unpaid: ${p.finesUnpaid} (₹${pending})
                        </div>
                    </div>`
                );
                circle.addTo(this.markersLayer);
            });

            const updatedEl = document.getElementById('admin-map-updated');
            if (updatedEl) updatedEl.textContent = new Date().toLocaleTimeString();
        } catch (e) {
            console.error('Map refresh failed', e);
        }
    },

    teardown() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        if (this.heatLayer && this.map) {
            this.map.removeLayer(this.heatLayer);
            this.heatLayer = null;
        }
        if (this.map) {
            this.map.remove();
            this.map = null;
        }
        this.markersLayer = null;
        this._scheduled = false;
    },
};

function syncDashboardRoleWidgets(user) {
    const isAdmin = !!(user && user.role === 'Admin');
    document.querySelectorAll('.dashboard-user-only').forEach((el) => {
        el.classList.toggle('hidden', isAdmin);
    });
    document.querySelectorAll('.dashboard-admin-only').forEach((el) => {
        el.classList.toggle('hidden', !isAdmin);
    });
    if (!isAdmin) {
        DailyReminders.tryInit();
    }
    if (isAdmin) {
        AdminFineMap.scheduleInit();
    } else {
        AdminFineMap.teardown();
    }
}

// ============================================
// Router (Hash-based SPA)
// ============================================
const pages = ['dashboard', 'detection', 'cameras', 'owners', 'vehicles', 'violations', 'fines', 'payments'];

function navigate(page) {
    if (!pages.includes(page)) page = 'dashboard';
    
    const user = Auth.getUser();
    if (!user) {
        Auth.renderUI();
        return;
    }

    // Role-based access control
    const restrictedPages = ['detection', 'cameras', 'owners'];
    if (user.role !== 'Admin' && restrictedPages.includes(page)) {
        showToast('Access Denied: Admin role required', 'error');
        location.hash = '#dashboard';
        return;
    }

    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const navEl = document.querySelector(`[data-page="${page}"]`);
    if (navEl) navEl.classList.add('active');
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const pageEl = document.getElementById(`page-${page}`);
    if (pageEl) {
        pageEl.classList.add('active');
        pageEl.style.animation = 'none';
        pageEl.offsetHeight;
        pageEl.style.animation = '';
    }
    renderPage(page);
}

function renderPage(page) {
    switch (page) {
        case 'dashboard': renderDashboard(); break;
        case 'detection': initDetection(); break;
        case 'cameras': renderCameras(); break;
        case 'owners': renderOwners(); break;
        case 'vehicles': renderVehicles(); break;
        case 'violations': renderViolations(); break;
        case 'accident-alerts': renderAccidentAlertsPage(); break;
        case 'fines': renderFines(); break;
        case 'payments': renderPayments(); break;
    }
}

function syncSidebarStatLabels(isAdmin) {
    const aL = document.getElementById('sidebar-stat-a-label');
    const bL = document.getElementById('sidebar-stat-b-label');
    if (!aL || !bL) return;
    if (isAdmin) {
        aL.textContent = 'Registered owners';
        bL.textContent = 'Registered vehicles';
    } else {
        aL.textContent = 'Violations';
        bL.textContent = 'Pending';
    }
}

function applyDashboardMosaicLayout(isAdmin, stats) {
    const lt = document.getElementById('mosaic-dash-left-title');
    const ls = document.getElementById('mosaic-dash-left-sub');
    const rt = document.getElementById('mosaic-dash-right-title');
    const rs = document.getElementById('mosaic-dash-right-sub');
    const lsuf = document.getElementById('mosaic-dash-left-suffix');
    const rsuf = document.getElementById('mosaic-dash-right-suffix');
    const leftTags = document.getElementById('mosaic-dash-left-tags');
    const rightTags = document.getElementById('mosaic-dash-right-tags');
    const elCam = document.getElementById('stat-cameras');
    const elVio = document.getElementById('stat-violations');
    if (!lt || !ls || !rt || !rs || !lsuf || !rsuf || !elCam || !elVio) return;

    if (isAdmin) {
        lt.textContent = 'Registered owners';
        ls.textContent = 'In the system';
        rt.textContent = 'Registered vehicles';
        rs.textContent = 'Linked to owners';
        elCam.textContent = stats.registeredOwners ?? 0;
        elVio.textContent = stats.registeredVehicles ?? 0;
        lsuf.textContent = 'owners';
        rsuf.textContent = 'vehicles';
        if (leftTags) {
            leftTags.innerHTML =
                '<span class="mosaic-tag mosaic-tag--purple">People</span><span class="mosaic-tag">KYC</span><span class="mosaic-tag mosaic-tag--purple">ID</span>';
        }
        if (rightTags) {
            rightTags.innerHTML =
                '<span class="mosaic-tag mosaic-tag--purple">RC</span><span class="mosaic-tag">Fleet</span><span class="mosaic-tag mosaic-tag--purple">Reg</span>';
        }
    } else {
        lt.textContent = 'Live cameras';
        ls.textContent = 'Surveillance grid';
        rt.textContent = 'Violations';
        rs.textContent = 'All-time records';
        elCam.textContent = stats.totalCameras;
        elVio.textContent = stats.totalViolations;
        lsuf.textContent = 'active';
        rsuf.textContent = 'total';
        if (leftTags) {
            leftTags.innerHTML =
                '<span class="mosaic-tag mosaic-tag--purple">AI</span><span class="mosaic-tag">YOLO</span><span class="mosaic-tag mosaic-tag--purple">HD</span>';
        }
        if (rightTags) {
            rightTags.innerHTML =
                '<span class="mosaic-tag mosaic-tag--purple">Signal</span><span class="mosaic-tag">Speed</span><span class="mosaic-tag">Parking</span>';
        }
    }
}

// ============================================
// DASHBOARD
// ============================================
let dashboardTabsInitialized = false;

async function renderDashboard() {
    try {
        const stats = await api('/stats');
        const user = Auth.getUser();
        const isAdmin = !!(user && user.role === 'Admin');

        syncSidebarStatLabels(isAdmin);
        applyDashboardMosaicLayout(isAdmin, stats);

        const grid = document.querySelector('.dashboard-grid');
        if (grid) {
            grid.classList.toggle('dashboard-grid--full', !isAdmin);
        }

        const revenueLabel = document.getElementById('stat-fines-collected-label');
        const revenueValue = document.getElementById('stat-fines-collected');
        if (isAdmin) {
            if (revenueLabel) revenueLabel.textContent = 'Fines collected';
            if (revenueValue) revenueValue.textContent = formatCurrency(stats.finesCollected);
        } else {
            if (revenueLabel) revenueLabel.textContent = 'Pending fines';
            if (revenueValue) revenueValue.textContent = formatCurrency(stats.pendingFines);
        }

        document.getElementById('stat-pending').textContent = formatCurrency(stats.pendingFines);

        const sbA = document.getElementById('sidebar-stat-a-value');
        const sbB = document.getElementById('sidebar-stat-b-value');
        if (isAdmin) {
            if (sbA) sbA.textContent = stats.registeredOwners ?? 0;
            if (sbB) sbB.textContent = stats.registeredVehicles ?? 0;
        } else {
            if (sbA) sbA.textContent = stats.totalViolations;
            if (sbB) sbB.textContent = formatCurrency(stats.pendingFines);
        }

        const totalMoney = Number(stats.finesCollected) + Number(stats.pendingFines);
        const collectionPct = totalMoney > 0
            ? Math.min(100, Math.round((Number(stats.finesCollected) / totalMoney) * 100))
            : 0;
        const bar = document.getElementById('dashboard-collection-bar');
        const clearBar = document.getElementById('dashboard-clearance-bar');
        const clearPct = document.getElementById('dashboard-clearance-pct');
        if (bar) bar.style.width = `${collectionPct}%`;
        if (clearBar) clearBar.style.width = `${collectionPct}%`;
        if (clearPct) clearPct.textContent = `${collectionPct}%`;

        const greet = document.getElementById('balance-greeting-name');
        if (user && greet) greet.textContent = user.username;
        const roleLbl = document.getElementById('dashboard-user-role-label');
        if (user && roleLbl) {
            roleLbl.textContent = user.role === 'Admin' ? 'Administrator' : 'Vehicle owner';
        }

        // Update sidebar with license no if not admin
        if (!isAdmin && stats.licenseNo) {
            const sidebarRole = document.querySelector('.user-role');
            if (sidebarRole) sidebarRole.textContent = `License: ${stats.licenseNo}`;
            
            // Add click listener for profile modal
            const profileCard = document.querySelector('.sidebar-profile-card');
            if (profileCard) {
                profileCard.style.cursor = 'pointer';
                profileCard.onclick = () => {
                    Modal.open('User Profile', [
                        { key: 'u', label: 'Username', readonly: true },
                        { key: 'l', label: 'Driving License', readonly: true },
                        { key: 'r', label: 'Role', readonly: true }
                    ], {
                        u: user.username,
                        l: stats.licenseNo,
                        r: 'Vehicle Owner'
                    }, () => Modal.close());
                };
            }
        }

        // Recent violations
        const vioHeader = document.querySelector('.recent-violations-card h2');
        if (vioHeader) {
            vioHeader.textContent = isAdmin ? 'Recent Violations' : 'My Violations';
        }

        const tbody = document.getElementById('dashboard-violations-body');
        const recent = stats.recentViolations || [];
        if (recent.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state small"><p>No violations recorded yet</p></td></tr>';
        } else {
            tbody.innerHTML = recent.map(v => {
                const badgeClass = v.fine_status === 'Paid' ? 'badge-success' : 'badge-danger';
                return `<tr>
                    <td>${v.violation_id}</td>
                    <td>${v.vehicle_reg || v.vehicle_id}</td>
                    <td>${v.type}</td>
                    <td>${v.camera_location || v.camera_id}</td>
                    <td>${v.date}</td>
                    <td><span class="badge ${badgeClass}">${v.fine_status}</span></td>
                </tr>`;
            }).join('');
        }

        // Chart
        renderViolationChart(stats.violationTypes || []);

        if (isAdmin) {
            AdminFineMap.scheduleInit();
        }
    } catch (err) {
        console.error('Dashboard error:', err);
        showToast('Failed to load dashboard. Is the server running?', 'error');
    }
}

function renderViolationChart(typeCounts, selectedType = 'all') {
    const chartArea = document.getElementById('violation-chart');

    let filteredCounts = typeCounts;
    if (selectedType !== 'all') {
        filteredCounts = typeCounts.filter(t => t.type === selectedType);
    }

    const max = Math.max(1, ...filteredCounts.map(t => t.count));
    const classMap = {
        'Signal Jumping': 'signal', 'Overspeeding': 'speed', 'Helmetless Riding': 'helmet',
        'Illegal Parking': 'parking', 'Lane Violation': 'lane', 'Wrong Way Driving': 'signal',
        'Using Mobile Phone': 'speed', 'Accident': 'parking'
    };

    if (filteredCounts.length === 0) {
        chartArea.innerHTML = '<div class="empty-state small"><p>No data yet</p></div>';
        return;
    }

    chartArea.innerHTML = filteredCounts.map(({ type, count }) => {
        const pct = (count / max * 100).toFixed(0);
        const cls = classMap[type] || 'signal';
        return `<div class="chart-bar-group">
            <div class="chart-label">${type}</div>
            <div class="chart-bar-bg">
                <div class="chart-bar ${cls}" style="width:${Math.max(count > 0 ? 8 : 0, pct)}%">${count}</div>
            </div>
        </div>`;
    }).join('');
}

// ============================================
// CAMERAS
// ============================================
async function renderCameras() {
    try {
        const cameras = await api('/cameras');
        const tbody = document.getElementById('cameras-body');
        if (cameras.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state small"><p>No cameras added yet</p></td></tr>';
            return;
        }
        const user = Auth.getUser();
        const isAdmin = user && user.role === 'Admin';
        tbody.innerHTML = cameras.map(c => {
            const actionsCell = isAdmin ? `<td>
                <button class="btn-icon" onclick="editCamera('${c.camera_id}')" title="Edit">✎</button>
                <button class="btn-icon delete" onclick="deleteCamera('${c.camera_id}')" title="Delete">✕</button>
            </td>` : '';
            return `<tr>
                <td><strong>${c.camera_id}</strong></td>
                <td>${c.location}</td>
                <td><span class="badge badge-success">${c.status || 'Active'}</span></td>
                ${actionsCell}
            </tr>`;
        }).join('');
    } catch (err) {
        showToast('Failed to load cameras', 'error');
    }
}

const cameraFields = [
    { key: 'camera_id', label: 'Camera ID', readonly: true },
    { key: 'location', label: 'Location', required: true, placeholder: 'e.g., MG Road Junction' },
    { key: 'status', label: 'Status', type: 'select', options: [{ value: 'Active', label: 'Active' }, { value: 'Inactive', label: 'Inactive' }], required: true },
];

window.editCamera = async function(id) {
    const cameras = await api('/cameras');
    const cam = cameras.find(c => c.camera_id === id);
    if (!cam) return;
    Modal.open('Edit Camera', cameraFields, cam, async () => {
        const vals = Modal.getValues(cameraFields);
        await api(`/cameras/${id}`, 'PUT', { location: vals.location, status: vals.status });
        Modal.close();
        renderCameras();
        showToast('Camera updated successfully');
    });
};

window.deleteCamera = async function(id) {
    if (!confirm('Delete this camera?')) return;
    await api(`/cameras/${id}`, 'DELETE');
    renderCameras();
    showToast('Camera deleted', 'info');
};

document.getElementById('btn-add-camera').addEventListener('click', () => {
    Modal.open('Add Camera', [
        { key: 'location', label: 'Location', required: true, placeholder: 'e.g., MG Road Junction' },
        { key: 'status', label: 'Status', type: 'select', options: [{ value: 'Active', label: 'Active' }, { value: 'Inactive', label: 'Inactive' }], required: true },
    ], { status: 'Active' }, async () => {
        const vals = Modal.getValues([{ key: 'location' }, { key: 'status' }]);
        await api('/cameras', 'POST', vals);
        Modal.close();
        renderCameras();
        showToast('Camera added successfully');
    });
});

// ============================================
// OWNERS
// ============================================
async function renderOwners() {
    try {
        const owners = await api('/owners');
        const tbody = document.getElementById('owners-body');
        if (owners.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state small"><p>No owners registered</p></td></tr>';
            return;
        }
        const user = Auth.getUser();
        const isAdmin = user && user.role === 'Admin';
        tbody.innerHTML = owners.map(o => {
            const actionsCell = isAdmin ? `<td>
                <button class="btn-icon" onclick="editOwner('${o.owner_id}')" title="Edit">✎</button>
                <button class="btn-icon delete" onclick="deleteOwner('${o.owner_id}')" title="Delete">✕</button>
            </td>` : '';
            return `<tr>
                <td><strong>${o.owner_id}</strong></td>
                <td>${o.name}</td>
                <td>${o.license_no}</td>
                <td>${o.phone}</td>
                <td>${o.email}</td>
                ${actionsCell}
            </tr>`;
        }).join('');
    } catch (err) {
        showToast('Failed to load owners', 'error');
    }
}

const ownerFields = [
    { key: 'owner_id', label: 'Owner ID', readonly: true },
    { key: 'name', label: 'Full Name', required: true, placeholder: 'e.g., Rahul Sharma' },
    { key: 'license_no', label: 'License Number', required: true, placeholder: 'e.g., DL-1420110012345' },
    { key: 'phone', label: 'Phone', required: true, placeholder: 'e.g., 9876543210' },
    { key: 'email', label: 'Email', type: 'email', placeholder: 'e.g., rahul@email.com' },
];

window.editOwner = async function(id) {
    const owners = await api('/owners');
    const owner = owners.find(o => o.owner_id === id);
    if (!owner) return;
    Modal.open('Edit Owner', ownerFields, owner, async () => {
        const vals = Modal.getValues(ownerFields);
        await api(`/owners/${id}`, 'PUT', vals);
        Modal.close();
        renderOwners();
        showToast('Owner updated successfully');
    });
};

window.deleteOwner = async function(id) {
    if (!confirm('Delete this owner?')) return;
    await api(`/owners/${id}`, 'DELETE');
    renderOwners();
    showToast('Owner deleted', 'info');
};

document.getElementById('btn-add-owner').addEventListener('click', () => {
    const addFields = ownerFields.filter(f => f.key !== 'owner_id');
    Modal.open('Add Owner', addFields, {}, async () => {
        const vals = Modal.getValues(addFields);
        await api('/owners', 'POST', vals);
        Modal.close();
        renderOwners();
        showToast('Owner registered successfully');
    });
});

// ============================================
// VEHICLES
// ============================================
async function renderVehicles() {
    try {
        const vehicles = await api('/vehicles');
        const tbody = document.getElementById('vehicles-body');
        if (vehicles.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state small"><p>No vehicles registered</p></td></tr>';
            return;
        }
        const user = Auth.getUser();
        const isAdmin = user && user.role === 'Admin';
        tbody.innerHTML = vehicles.map(v => {
            const actionsCell = isAdmin ? `<td>
                <button class="btn-icon" onclick="editVehicle('${v.vehicle_id}')" title="Edit">✎</button>
                <button class="btn-icon delete" onclick="deleteVehicle('${v.vehicle_id}')" title="Delete">✕</button>
            </td>` : '';
            return `<tr>
                <td><strong>${v.vehicle_id}</strong></td>
                <td>${v.reg_no}</td>
                <td>${v.type}</td>
                <td>${v.color}</td>
                <td>${v.owner_name || v.owner_id}</td>
                ${actionsCell}
            </tr>`;
        }).join('');
    } catch (err) {
        showToast('Failed to load vehicles', 'error');
    }
}

async function getVehicleFields() {
    const owners = await api('/owners');
    return [
        { key: 'vehicle_id', label: 'Vehicle ID', readonly: true },
        { key: 'reg_no', label: 'Registration Number', required: true, placeholder: 'e.g., DL-14-AB-1234' },
        { key: 'type', label: 'Vehicle Type', type: 'select', required: true, options: [
            { value: 'Car', label: 'Car' }, { value: 'Motorcycle', label: 'Motorcycle' },
            { value: 'Truck', label: 'Truck' }, { value: 'Bus', label: 'Bus' },
            { value: 'Auto-Rickshaw', label: 'Auto-Rickshaw' }, { value: 'Scooter', label: 'Scooter' },
        ]},
        { key: 'color', label: 'Color', required: true, placeholder: 'e.g., White' },
        { key: 'owner_id', label: 'Owner', type: 'select', required: true,
            options: owners.map(o => ({ value: o.owner_id, label: `${o.name} (${o.owner_id})` })) },
    ];
}

window.editVehicle = async function(id) {
    const [vehicles, fields] = await Promise.all([api('/vehicles'), getVehicleFields()]);
    const vehicle = vehicles.find(v => v.vehicle_id === id);
    if (!vehicle) return;
    Modal.open('Edit Vehicle', fields, vehicle, async () => {
        const vals = Modal.getValues(fields);
        await api(`/vehicles/${id}`, 'PUT', vals);
        Modal.close();
        renderVehicles();
        showToast('Vehicle updated successfully');
    });
};

window.deleteVehicle = async function(id) {
    if (!confirm('Delete this vehicle?')) return;
    await api(`/vehicles/${id}`, 'DELETE');
    renderVehicles();
    showToast('Vehicle deleted', 'info');
};

document.getElementById('btn-add-vehicle').addEventListener('click', async () => {
    const fields = await getVehicleFields();
    const addFields = fields.filter(f => f.key !== 'vehicle_id');
    Modal.open('Add Vehicle', addFields, {}, async () => {
        const vals = Modal.getValues(addFields);
        await api('/vehicles', 'POST', vals);
        Modal.close();
        renderVehicles();
        showToast('Vehicle registered successfully');
    });
});

// ============================================
// VIOLATIONS
// ============================================
let currentViolationFilter = 'all';
let tabsInitialized = false;

async function renderViolations(typeFilter = currentViolationFilter) {
    currentViolationFilter = typeFilter;
    try {
        const violations = await api('/violations');
        let filtered = violations;
        if (typeFilter !== 'all') {
            filtered = violations.filter(v => v.type === typeFilter);
        }
        const tbody = document.getElementById('violations-body');
        if (filtered.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state small"><p>No violations found</p></td></tr>';
            return;
        }
        const user = Auth.getUser();
        const isAdmin = user && user.role === 'Admin';
        tbody.innerHTML = filtered.map(v => {
            const badgeClass = v.fine_status === 'Paid' ? 'badge-success' : 'badge-danger';
            const actionsCell = isAdmin ? `<td>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <button class="btn btn-sm btn-outline" onclick="viewViolationDetails('${v.violation_id}')">Details</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteViolation('${v.violation_id}')" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2);">Cancel</button>
                </div>
            </td>` : '';
            return `<tr>
                <td><strong>${v.violation_id}</strong></td>
                <td>${v.vehicle_reg || v.vehicle_id}</td>
                <td>${v.camera_location || v.camera_id}</td>
                <td>${v.type}</td>
                <td>${v.date}</td>
                <td><span class="badge ${badgeClass}">${v.fine_status}</span></td>
                ${actionsCell}
            </tr>`;
        }).join('');

        // Initialize tabs
        if (!tabsInitialized) {
            const tabs = document.querySelectorAll('#violation-tabs .tab');
            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    document.querySelectorAll('#violation-tabs .tab').forEach(t => t.classList.remove('active'));
                    tab.classList.add('active');
                    renderViolations(tab.dataset.type);
                });
            });
            tabsInitialized = true;
        }
    } catch (err) {
        showToast('Failed to load violations', 'error');
    }
}

async function getViolationFields() {
    const [vehicles, cameras] = await Promise.all([api('/vehicles'), api('/cameras')]);
    return [
        { key: 'vehicle_id', label: 'Vehicle', type: 'select', required: true,
            options: vehicles.map(v => ({ value: v.vehicle_id, label: `${v.reg_no} (${v.vehicle_id})` })) },
        { key: 'camera_id', label: 'Camera', type: 'select', required: true,
            options: cameras.map(c => ({ value: c.camera_id, label: `${c.location} (${c.camera_id})` })) },
        { key: 'type', label: 'Violation Type', type: 'select', required: true,
            options: VIOLATION_TYPES.map(t => ({ value: t, label: t })) },
        { key: 'date', label: 'Date', type: 'date', required: true },
    ];
}

window.viewViolationDetails = async function(id) {
    try {
        const violations = await api('/violations');
        const v = violations.find(item => item.violation_id === id);
        if (!v) return;

        Modal.open('Violation Details', [
            { key: 'violation_id', label: 'Violation ID', readonly: true },
            { key: 'camera_id', label: 'Camera ID', readonly: true },
            { key: 'camera_location', label: 'Place of Violation', readonly: true },
            { key: 'type', label: 'Violation Type', readonly: true },
            { key: 'date', label: 'Date', readonly: true }
        ], v, () => Modal.close());
    } catch (err) {
        showToast('Failed to load violation details', 'error');
    }
};

window.deleteViolation = async function(id) {
    if (!confirm('Are you sure you want to cancel this violation? This will also remove any associated fines.')) return;
    await api(`/violations/${id}`, 'DELETE');
    renderViolations();
    showToast('Violation cancelled');
};

document.getElementById('btn-add-violation').addEventListener('click', async () => {
    const fields = await getViolationFields();
    Modal.open('Log Violation', fields, { date: formatDate(new Date()) }, async () => {
        const vals = Modal.getValues(fields);
        const res = await api('/violations', 'POST', {
            ...vals,
            confidence: Math.floor(Math.random() * 10) + 88
        });
        Modal.close();
        renderViolations();
        showToast(res.message || 'Violation logged');
    });
});

// ============================================
// FINES
// ============================================
async function renderFines(filter) {
    try {
        const user = Auth.getUser();
        const filterEl = document.getElementById('fine-status-filter');
        const isOwner = user && user.role !== 'Admin';

        if (!filter) {
            filter = filterEl ? filterEl.value : 'all';
        }

        if (isOwner) {
            filter = 'Unpaid';
            if (filterEl) {
                filterEl.value = 'Unpaid';
                filterEl.disabled = true;
            }
        } else if (filterEl) {
            filterEl.disabled = false;
        }

        const endpoint = filter !== 'all' ? `/fines?status=${filter}` : '/fines';
        const fines = await api(endpoint);
        const tbody = document.getElementById('fines-body');
        if (fines.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state small"><p>No fines found</p></td></tr>';
            return;
        }
        tbody.innerHTML = fines.map(f => {
            const badgeClass = f.status === 'Paid' ? 'badge-success' : 'badge-danger';
            const payBtn = (isOwner && f.status === 'Unpaid') ? `<button class="btn btn-sm btn-primary" onclick="payFine('${f.fine_id}')">Pay</button>` : '';
            const remindBtn = (!isOwner && f.status === 'Unpaid') ? `<button class="btn btn-sm btn-outline" onclick="sendFineReminder('${f.fine_id}')">Remind</button>` : '';
            return `<tr>
                <td><strong>${f.fine_id}</strong></td>
                <td>${f.violation_id}</td>
                <td>${f.vehicle_reg || '—'}</td>
                <td>${f.violation_type || '—'}</td>
                <td>${formatCurrency(f.amount)}</td>
                <td><span class="badge ${badgeClass}">${f.status}</span></td>
                <td>${isOwner ? payBtn : remindBtn}</td>
            </tr>`;
        }).join('');
    } catch (err) {
        showToast('Failed to load fines', 'error');
    }
}

document.getElementById('fine-status-filter').addEventListener('change', (e) => {
    renderFines(e.target.value);
});

window.sendFineReminder = function(fineId) {
    showToast(`Reminder sent to owner for fine ${fineId}`, 'info');
};

window.payFine = function(fineId) {
    const paymentFields = [
        { key: 'fine_id', label: 'Fine ID', readonly: true },
        { key: 'date', label: 'Payment Date', type: 'date', required: true },
        { key: 'mode', label: 'Payment Mode', type: 'select', required: true, options: [
            { value: 'UPI', label: 'UPI' },
            { value: 'Credit Card', label: 'Credit Card' },
            { value: 'Debit Card', label: 'Debit Card' },
            { value: 'Net Banking', label: 'Net Banking' },
            { value: 'Cash', label: 'Cash' },
        ]},
    ];
    Modal.open('Record Payment', paymentFields, { fine_id: fineId, date: formatDate(new Date()) }, async () => {
        const vals = Modal.getValues(paymentFields);
        const res = await api('/payments', 'POST', vals);
        Modal.close();
        renderFines();
        showToast(res.message || 'Payment recorded');
    });
};

// ============================================
// PAYMENTS
// ============================================
async function renderPayments() {
    try {
        const payments = await api('/payments');
        const tbody = document.getElementById('payments-body');
        if (payments.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state small"><p>No payments recorded</p></td></tr>';
            return;
        }
        tbody.innerHTML = payments.map(p => `<tr>
            <td><strong>${p.payment_id}</strong></td>
            <td>${p.fine_id}</td>
            <td>${formatCurrency(p.amount)}</td>
            <td>${p.date}</td>
            <td><span class="badge badge-info">${p.mode}</span></td>
        </tr>`).join('');
    } catch (err) {
        showToast('Failed to load payments', 'error');
    }
}

document.getElementById('btn-add-payment').addEventListener('click', async () => {
    try {
        const unpaidFines = await api('/fines/unpaid');
        if (unpaidFines.length === 0) {
            showToast('No unpaid fines available', 'info');
            return;
        }
        const paymentFields = [
            { key: 'fine_id', label: 'Select Fine', type: 'select', required: true,
                options: unpaidFines.map(f => ({
                    value: f.fine_id,
                    label: `${f.fine_id} — ${formatCurrency(f.amount)} (${f.vehicle_reg || ''} — ${f.violation_type || ''})`
                }))
            },
            { key: 'date', label: 'Payment Date', type: 'date', required: true },
            { key: 'mode', label: 'Payment Mode', type: 'select', required: true, options: [
                { value: 'UPI', label: 'UPI' },
                { value: 'Credit Card', label: 'Credit Card' },
                { value: 'Debit Card', label: 'Debit Card' },
                { value: 'Net Banking', label: 'Net Banking' },
                { value: 'Cash', label: 'Cash' },
            ]},
        ];
        Modal.open('Record Payment', paymentFields, { date: formatDate(new Date()) }, async () => {
            const vals = Modal.getValues(paymentFields);
            const res = await api('/payments', 'POST', vals);
            Modal.close();
            renderPayments();
            showToast(res.message || 'Payment recorded');
        });
    } catch (err) {
        showToast('Failed to load unpaid fines', 'error');
    }
});

// ============================================
// REAL AI VIDEO DETECTION (YOLOv8)
// ============================================
let uploadZone, videoInput, uploadProgress, progressText, progressFill;
let videoResultsGrid, videoPlayer, realDetectionList, realDetectionCount;
let currentJobId = null;

function initDetection() {
    uploadZone = document.getElementById('upload-zone');
    videoInput = document.getElementById('video-upload-input');
    uploadProgress = document.getElementById('upload-progress');
    progressText = document.getElementById('progress-text');
    progressFill = document.getElementById('progress-bar-fill');
    
    videoResultsGrid = document.getElementById('video-results-grid');
    videoPlayer = document.getElementById('processed-video-player');
    realDetectionList = document.getElementById('real-detection-list');
    realDetectionCount = document.getElementById('real-detection-count');

    // Drag and Drop Handlers
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('drag-over');
    });
    uploadZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('drag-over');
    });
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) {
            handleVideoUpload(e.dataTransfer.files[0]);
        }
    });

    videoInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleVideoUpload(e.target.files[0]);
        }
    });
}

async function handleVideoUpload(file) {
    if (!file.type.startsWith('video/')) {
        showToast('Please upload a valid video file.', 'error');
        return;
    }

    // Reset UI
    uploadZone.querySelector('.upload-content').classList.add('hidden');
    uploadProgress.classList.remove('hidden');
    videoResultsGrid.classList.add('hidden');
    progressText.textContent = 'Uploading...';
    progressFill.style.width = '10%';

    const formData = new FormData();
    formData.append('video', file);

    try {
        const res = await fetch(`${API}/upload-video`, { method: 'POST', body: formData });
        const data = await res.json();
        
        if (!res.ok) throw new Error(data.error || 'Upload failed');
        
        progressText.textContent = 'Processing with YOLOv8...';
        progressFill.style.width = '30%';
        startProcessing(data.filename);
    } catch (err) {
        showToast(err.message, 'error');
        resetUploadUI();
    }
}

async function startProcessing(filename) {
    try {
        const res = await api('/process-video', 'POST', { filename, camera_id: 'CAM-001' });
        currentJobId = res.job_id;
        pollJobStatus();
    } catch (err) {
        showToast('Failed to start processing', 'error');
        resetUploadUI();
    }
}

async function pollJobStatus() {
    if (!currentJobId) return;
    
    try {
        const status = await api(`/job-status/${currentJobId}`);
        
        if (status.status === 'processing') {
            const prog = Math.max(30, 30 + (status.progress * 0.7)); // scale 0-100 to 30-100
            progressFill.style.width = `${prog}%`;
            progressText.textContent = `YOLOv8 Processing: ${status.progress}%`;
            
            setTimeout(pollJobStatus, 2000);
        } else if (status.status === 'completed') {
            displayDetectionResults(status);
        } else if (status.status === 'error') {
            throw new Error(status.message);
        }
    } catch (err) {
        showToast(err.message || 'Error checking status', 'error');
        resetUploadUI();
    }
}

function displayDetectionResults(data) {
    // Hide progress, show results
    uploadZone.classList.add('hidden');
    videoResultsGrid.classList.remove('hidden');
    
    // Set video player
    videoPlayer.src = `${API}/video/processed/${data.output_video}`;
    
    // Populate stats
    const dets = data.detections || [];
    realDetectionCount.textContent = `${dets.length} detections`;
    document.getElementById('res-violations').textContent = dets.length;
    
    const totalFines = dets.reduce((sum, d) => sum + (d.amount || 0), 0);
    document.getElementById('res-fines').textContent = formatCurrency(totalFines);
    
    // Populate log list
    if (dets.length === 0) {
        realDetectionList.innerHTML = '<div class="empty-state small"><p>No violations detected</p></div>';
    } else {
        realDetectionList.innerHTML = dets.map(d => `
            <div class="detection-log-item">
<div class="det-time">${Number(d.timestamp).toFixed(1)}s</div>
                <div class="det-info">
                    <div class="det-type">${d.type}</div>
                    <div class="det-detail">${d.vehicle_reg} • ${d.camera_id}</div>
                </div>
                <div class="det-confidence">${d.confidence}%</div>
            </div>
        `).join('');
    }
    
    showToast('Video processing complete!', 'success');
}

function resetUploadUI() {
    uploadZone.classList.remove('hidden');
    uploadZone.querySelector('.upload-content').classList.remove('hidden');
    uploadProgress.classList.add('hidden');
    videoInput.value = '';
    currentJobId = null;
}

// ============================================
// Initialization
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    Modal.init();
    Theme.init();
    Auth.init();

    function onHashChange() {
        const hash = location.hash.replace('#', '') || 'dashboard';
        navigate(hash);
    }
    window.addEventListener('hashchange', onHashChange);
    onHashChange();
});

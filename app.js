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
        const logoutBtn = document.getElementById('logout-btn');

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

            // Restricted menu items
            document.querySelectorAll('.nav-item[data-role="Admin"]').forEach(item => {
                item.style.display = user.role === 'Admin' ? 'flex' : 'none';
            });
        } else {
            appContainer.style.display = 'none';
            loginPage.style.display = 'flex';
        }
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
        case 'fines': renderFines(); break;
        case 'payments': renderPayments(); break;
    }
}

// ============================================
// DASHBOARD
// ============================================
async function renderDashboard() {
    try {
        const stats = await api('/stats');

        document.getElementById('stat-violations').textContent = stats.totalViolations;
        document.getElementById('stat-fines-collected').textContent = formatCurrency(stats.finesCollected);
        document.getElementById('stat-pending').textContent = formatCurrency(stats.pendingFines);
        document.getElementById('stat-cameras').textContent = stats.totalCameras;

        // Recent violations
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
    } catch (err) {
        console.error('Dashboard error:', err);
        showToast('Failed to load dashboard. Is the server running?', 'error');
    }
}

function renderViolationChart(typeCounts) {
    const chartArea = document.getElementById('violation-chart');
    const max = Math.max(1, ...typeCounts.map(t => t.count));
    const classMap = {
        'Signal Jumping': 'signal', 'Overspeeding': 'speed', 'Helmetless Riding': 'helmet',
        'Illegal Parking': 'parking', 'Lane Violation': 'lane', 'Wrong Way Driving': 'signal',
        'Using Mobile Phone': 'speed'
    };

    if (typeCounts.length === 0) {
        chartArea.innerHTML = '<div class="empty-state small"><p>No data yet</p></div>';
        return;
    }

    chartArea.innerHTML = typeCounts.map(({ type, count }) => {
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
        tbody.innerHTML = cameras.map(c => `<tr>
            <td><strong>${c.camera_id}</strong></td>
            <td>${c.location}</td>
            <td><span class="badge badge-success">${c.status || 'Active'}</span></td>
            <td>
                <button class="btn-icon" onclick="editCamera('${c.camera_id}')" title="Edit">✎</button>
                <button class="btn-icon delete" onclick="deleteCamera('${c.camera_id}')" title="Delete">✕</button>
            </td>
        </tr>`).join('');
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
        tbody.innerHTML = owners.map(o => `<tr>
            <td><strong>${o.owner_id}</strong></td>
            <td>${o.name}</td>
            <td>${o.license_no}</td>
            <td>${o.phone}</td>
            <td>${o.email}</td>
            <td>
                <button class="btn-icon" onclick="editOwner('${o.owner_id}')" title="Edit">✎</button>
                <button class="btn-icon delete" onclick="deleteOwner('${o.owner_id}')" title="Delete">✕</button>
            </td>
        </tr>`).join('');
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
        tbody.innerHTML = vehicles.map(v => `<tr>
            <td><strong>${v.vehicle_id}</strong></td>
            <td>${v.reg_no}</td>
            <td>${v.type}</td>
            <td>${v.color}</td>
            <td>${v.owner_name || v.owner_id}</td>
            <td>
                <button class="btn-icon" onclick="editVehicle('${v.vehicle_id}')" title="Edit">✎</button>
                <button class="btn-icon delete" onclick="deleteVehicle('${v.vehicle_id}')" title="Delete">✕</button>
            </td>
        </tr>`).join('');
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
async function renderViolations() {
    try {
        const violations = await api('/violations');
        const tbody = document.getElementById('violations-body');
        if (violations.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state small"><p>No violations recorded</p></td></tr>';
            return;
        }
        tbody.innerHTML = violations.map(v => {
            const badgeClass = v.fine_status === 'Paid' ? 'badge-success' : 'badge-danger';
            return `<tr>
                <td><strong>${v.violation_id}</strong></td>
                <td>${v.vehicle_reg || v.vehicle_id}</td>
                <td>${v.camera_location || v.camera_id}</td>
                <td>${v.type}</td>
                <td>${v.date}</td>
                <td><span class="badge ${badgeClass}">${v.fine_status}</span></td>
                <td>
                    <button class="btn-icon delete" onclick="deleteViolation('${v.violation_id}')" title="Delete">✕</button>
                </td>
            </tr>`;
        }).join('');
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

window.deleteViolation = async function(id) {
    if (!confirm('Delete this violation and its associated fine?')) return;
    await api(`/violations/${id}`, 'DELETE');
    renderViolations();
    showToast('Violation deleted', 'info');
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
        if (!filter) {
            const filterEl = document.getElementById('fine-status-filter');
            filter = filterEl ? filterEl.value : 'all';
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
            const payBtn = f.status === 'Unpaid' ? `<button class="btn btn-sm btn-primary" onclick="payFine('${f.fine_id}')">Pay</button>` : '';
            return `<tr>
                <td><strong>${f.fine_id}</strong></td>
                <td>${f.violation_id}</td>
                <td>${f.vehicle_reg || '—'}</td>
                <td>${f.violation_type || '—'}</td>
                <td>${formatCurrency(f.amount)}</td>
                <td><span class="badge ${badgeClass}">${f.status}</span></td>
                <td>${payBtn}</td>
            </tr>`;
        }).join('');
    } catch (err) {
        showToast('Failed to load fines', 'error');
    }
}

document.getElementById('fine-status-filter').addEventListener('change', (e) => {
    renderFines(e.target.value);
});

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

/**
 * BotCrypto - Main Application
 * Handles routing, authentication, connection management
 */
const App = {
    currentPage: null,
    connectModal: null,
    guiPassword: null,
    isAuthenticated: false,

    pages: {
        'dashboard': { title: 'Dashboard', module: () => DashboardPage },
        'strategy-builder': { title: 'Strategy Builder', module: () => StrategyBuilderPage },
        'backtesting': { title: 'Backtesting', module: () => BacktestingPage },
        'strategy-store': { title: 'Strategy Store', module: () => StrategyStorePage },
        'trades': { title: 'Trades', module: () => TradesPage },
        'config': { title: 'Configuration', module: () => ConfigWizardPage },
    },

    async init() {
        // Initialize ConfigDB
        try { await ConfigDB.init(); } catch (e) { console.error('ConfigDB init:', e); }

        // Check GUI access
        this.checkGuiAccess();

        // Initialize Bootstrap modal
        this.connectModal = new bootstrap.Modal(document.getElementById('connectModal'));

        // Setup connect button
        document.getElementById('connectBtn').addEventListener('click', () => this.connect());
        document.getElementById('serverPass').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.connect();
        });

        // Check existing connection - MUST await before navigating
        // so pages see API.connected = true and load real data
        if (API.token && API.baseUrl) {
            await this.tryReconnect();
        } else {
            this.updateConnectionStatus(false);
        }

        // Route based on hash
        window.addEventListener('hashchange', () => {
            const page = location.hash.substring(1) || 'dashboard';
            this.navigate(page, false);
        });

        // Initial navigation
        const initialPage = location.hash.substring(1) || 'dashboard';
        this.navigate(initialPage, false);
    },

    checkGuiAccess() {
        const savedAuth = sessionStorage.getItem('bc_gui_auth');
        if (savedAuth === 'true') {
            this.isAuthenticated = true;
            return;
        }

        // Show login gate
        this.showLoginGate();
    },

    showLoginGate() {
        const container = document.getElementById('pageContainer');
        container.innerHTML = `
        <div class="d-flex justify-content-center align-items-center" style="min-height:60vh">
            <div class="card" style="width:400px">
                <div class="card-body p-4">
                    <div class="text-center mb-4">
                        <div class="logo-icon mx-auto mb-3" style="width:56px;height:56px;font-size:28px">
                            <i class="bi bi-robot"></i>
                        </div>
                        <h4 class="fw-bold text-white">botcrypto</h4>
                        <p class="text-secondary small">Enter access password to continue</p>
                    </div>
                    <div class="mb-3">
                        <input type="password" class="form-control form-control-lg text-center" id="guiPasswordInput"
                            placeholder="Access Password" autofocus
                            onkeydown="if(event.key==='Enter') App.verifyGuiPassword()">
                    </div>
                    <div id="guiLoginError" class="alert alert-danger small d-none"></div>
                    <button class="btn btn-success w-100 btn-lg fw-semibold" onclick="App.verifyGuiPassword()">
                        <i class="bi bi-lock me-2"></i>Sign In
                    </button>
                </div>
            </div>
        </div>`;
    },

    verifyGuiPassword() {
        const input = document.getElementById('guiPasswordInput');
        const password = input.value.trim();

        // Default password from .env (in production this would be server-side validated)
        const validPassword = 'abc123';

        if (password === validPassword) {
            this.isAuthenticated = true;
            sessionStorage.setItem('bc_gui_auth', 'true');
            // Navigate to dashboard
            this.navigate('dashboard');
        } else {
            const err = document.getElementById('guiLoginError');
            err.textContent = 'Invalid password. Please try again.';
            err.classList.remove('d-none');
            input.value = '';
            input.focus();
        }
    },

    navigate(page, updateHash = true) {
        if (!this.isAuthenticated) {
            this.showLoginGate();
            return;
        }

        const pageConfig = this.pages[page];
        if (!pageConfig) {
            this.navigate('dashboard');
            return;
        }

        // Destroy current page
        if (this.currentPage) {
            const currentModule = this.currentPage.module();
            if (currentModule && currentModule.destroy) currentModule.destroy();
        }

        // Update UI
        this.currentPage = pageConfig;
        if (updateHash) location.hash = page;
        document.getElementById('pageTitle').textContent = pageConfig.title;

        // Update sidebar
        document.querySelectorAll('#sidebarNav .nav-link').forEach(el => {
            el.classList.toggle('active', el.dataset.page === page);
        });

        // Render page
        const container = document.getElementById('pageContainer');
        const module = pageConfig.module();
        container.innerHTML = module.render();

        // Initialize page
        if (module.init) module.init();
    },

    async connect() {
        const url = document.getElementById('serverUrl').value.trim();
        const user = document.getElementById('serverUser').value.trim();
        const pass = document.getElementById('serverPass').value;
        const errEl = document.getElementById('connectError');

        if (!url) {
            errEl.textContent = 'Please enter server URL';
            errEl.classList.remove('d-none');
            return;
        }

        const btn = document.getElementById('connectBtn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Connecting...';

        try {
            await API.login(url, user, pass);
            this.updateConnectionStatus(true);
            this.connectModal.hide();
            errEl.classList.add('d-none');
            this.showToast('Connected to Freqtrade!', 'success');

            // Refresh current page fully to load real data
            if (this.currentPage) {
                const currentModule = this.currentPage.module();
                if (currentModule && currentModule.destroy) currentModule.destroy();
                const container = document.getElementById('pageContainer');
                container.innerHTML = currentModule.render();
                if (currentModule.init) currentModule.init();
            }
        } catch (e) {
            errEl.textContent = `Connection failed: ${e.message}`;
            errEl.classList.remove('d-none');
            this.updateConnectionStatus(false);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-plug me-1"></i> Connect';
        }
    },

    async tryReconnect() {
        try {
            const ok = await API.ping();
            this.updateConnectionStatus(ok);
            if (!ok) {
                // Try refresh token
                const refreshed = await API.refreshAccessToken();
                if (refreshed) {
                    const ok2 = await API.ping();
                    this.updateConnectionStatus(ok2);
                }
            }
        } catch {
            this.updateConnectionStatus(false);
        }
    },

    updateConnectionStatus(connected) {
        const statusEl = document.getElementById('connectionStatus');
        if (!statusEl) return;

        const dot = statusEl.querySelector('.status-dot');
        const text = statusEl.querySelector('.status-text');

        if (connected) {
            dot.className = 'status-dot connected me-2';
            text.textContent = 'Connected';
            text.className = 'small text-success status-text';
            API.connected = true;
        } else {
            dot.className = 'status-dot disconnected me-2';
            text.textContent = 'Disconnected';
            text.className = 'small text-secondary status-text';
            API.connected = false;
        }
    },

    showConnectModal() {
        this.connectModal.show();
    },

    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        const icons = {
            success: 'bi-check-circle-fill text-success',
            error: 'bi-x-circle-fill text-danger',
            warning: 'bi-exclamation-triangle-fill text-warning',
            info: 'bi-info-circle-fill text-info',
        };

        const toastEl = document.createElement('div');
        toastEl.className = 'toast show';
        toastEl.setAttribute('role', 'alert');
        toastEl.innerHTML = `
        <div class="toast-body d-flex align-items-center gap-2">
            <i class="bi ${icons[type] || icons.info}"></i>
            <span class="flex-grow-1">${message}</span>
            <button type="button" class="btn-close btn-close-white ms-2" data-bs-dismiss="toast"></button>
        </div>`;

        container.appendChild(toastEl);
        const bsToast = new bootstrap.Toast(toastEl, { delay: 4000 });
        bsToast.show();
        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    },
};

// Initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => App.init());

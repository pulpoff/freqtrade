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
        'strategies': { title: 'My strategies', module: () => RobotsPage },
        'strategy-builder': { title: 'Strategy Builder', module: () => StrategyBuilderPage },
        'backtesting': { title: 'Backtesting', module: () => BacktestingPage },
        'strategy-store': { title: 'Strategy Store', module: () => StrategyStorePage },
        'portfolio': { title: 'Portfolio', module: () => PortfolioPage },
        'trades': { title: 'Trades', module: () => TradesPage },
        'webhooks': { title: 'Webhooks', module: () => WebhooksPage },
        'config': { title: 'Configuration', module: () => ConfigWizardPage },
    },

    async init() {
        // Initialize ConfigDB
        try { await ConfigDB.init(); } catch (e) { console.error('ConfigDB init:', e); }

        // Restore sidebar collapsed state
        if (localStorage.getItem('bc_sidebar_collapsed') === 'true') {
            document.getElementById('sidebar').classList.add('collapsed');
        }

        // Check GUI access
        this.checkGuiAccess();

        // Auto-connect using config or saved credentials
        if (API.token && API.baseUrl) {
            await this.tryReconnect();
        } else {
            await this.autoConnectFromConfig();
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

    /** Auto-connect to Freqtrade using credentials from ConfigDB or same-origin */
    async autoConnectFromConfig() {
        try {
            // Try active config first, then any config with API credentials
            let config = await ConfigDB.getActiveConfig();
            if (!config) {
                const allConfigs = await ConfigDB.getAllConfigs();
                config = allConfigs.find(c => c.apiPassword) || allConfigs[0];
            }

            if (config) {
                const host = config.apiHost || '0.0.0.0';
                const port = config.apiPort || 8080;
                const user = config.apiUsername || 'freqtrader';
                const pass = config.apiPassword || '';

                // Build URL - use localhost if host is 0.0.0.0
                const connectHost = (host === '0.0.0.0' || host === '::') ? 'localhost' : host;
                const url = `http://${connectHost}:${port}`;

                await API.login(url, user, pass);
                this.updateConnectionStatus(true);
                this.showToast('Connected to Freqtrade', 'success');
                return;
            }
        } catch (e) {
            console.warn('Auto-connect from ConfigDB failed:', e.message);
        }

        // Fallback: try connecting to same origin (engine mode — GUI served by API server)
        try {
            const url = window.location.origin;
            const creds = localStorage.getItem('bc_credentials');
            let user = 'freqtrader', pass = '';
            if (creds) {
                const parsed = JSON.parse(creds);
                user = parsed.username || user;
                pass = parsed.password || pass;
            }
            await API.login(url, user, pass);
            this.updateConnectionStatus(true);
            this.showToast('Connected to Freqtrade', 'success');
            return;
        } catch (e) {
            console.warn('Auto-connect to same origin failed:', e.message);
        }

        this.updateConnectionStatus(false);
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
        <div class="d-flex justify-content-center align-items-center px-3" style="min-height:60vh">
            <div class="card w-100" style="max-width:400px">
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

    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const backdrop = document.getElementById('sidebarBackdrop');
        sidebar.classList.toggle('show');
        backdrop.classList.toggle('show');
    },

    closeSidebar() {
        const sidebar = document.getElementById('sidebar');
        const backdrop = document.getElementById('sidebarBackdrop');
        sidebar.classList.remove('show');
        backdrop.classList.remove('show');
    },

    onLogoClick(event) {
        const sidebar = document.getElementById('sidebar');
        if (sidebar.classList.contains('collapsed')) {
            // Expand when collapsed
            sidebar.classList.remove('collapsed');
            localStorage.setItem('bc_sidebar_collapsed', 'false');
        } else {
            App.navigate('dashboard');
        }
    },

    toggleSidebarCollapse() {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('bc_sidebar_collapsed', sidebar.classList.contains('collapsed'));
    },

    navigate(page, updateHash = true) {
        // Always close mobile sidebar on navigation
        this.closeSidebar();

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
        const pt = document.getElementById('pageTitle');
        if (pt) pt.textContent = pageConfig.title;

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

    /** Reconnect to Freqtrade - tries saved credentials first, then config */
    async reconnect() {
        this.showToast('Reconnecting...', 'info');
        try {
            // Try saved credentials first
            const saved = localStorage.getItem('bc_credentials');
            if (saved && API.baseUrl) {
                const { username, password } = JSON.parse(saved);
                await API.login(API.baseUrl, username, password);
                this.updateConnectionStatus(true);
                this.showToast('Reconnected to Freqtrade', 'success');
                this._refreshCurrentPage();
                return;
            }
        } catch { /* fall through to config */ }

        // Fall back to config
        await this.autoConnectFromConfig();
        if (API.connected) this._refreshCurrentPage();
    },

    _refreshCurrentPage() {
        if (this.currentPage) {
            const currentModule = this.currentPage.module();
            if (currentModule && currentModule.destroy) currentModule.destroy();
            const container = document.getElementById('pageContainer');
            container.innerHTML = currentModule.render();
            if (currentModule.init) currentModule.init();
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
        // No modal - just reconnect using config
        this.reconnect();
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

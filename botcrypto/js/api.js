/**
 * BotCrypto - Freqtrade API Client
 * Communicates with Freqtrade REST API v2
 */
const API = {
    baseUrl: '',
    token: null,
    refreshToken: null,
    connected: false,
    wsConnection: null,

    /** Initialize from saved settings */
    init() {
        const saved = localStorage.getItem('bc_connection');
        if (saved) {
            const { url, token, refreshToken } = JSON.parse(saved);
            this.baseUrl = url;
            this.token = token;
            this.refreshToken = refreshToken;
        }
    },

    /** Connect to Freqtrade instance */
    async login(url, username, password) {
        this.baseUrl = url.replace(/\/+$/, '');
        try {
            const resp = await fetch(`${this.baseUrl}/api/v1/token/login`, {
                method: 'POST',
                headers: {
                    'Authorization': 'Basic ' + btoa(`${username}:${password}`),
                    'Content-Type': 'application/json'
                }
            });
            if (!resp.ok) throw new Error(`Login failed: ${resp.status}`);
            const data = await resp.json();
            this.token = data.access_token;
            this.refreshToken = data.refresh_token;
            this.connected = true;
            localStorage.setItem('bc_connection', JSON.stringify({
                url: this.baseUrl, token: this.token, refreshToken: this.refreshToken
            }));
            // Save credentials for auto-reconnect on session expiry
            localStorage.setItem('bc_credentials', JSON.stringify({ username, password }));
            return data;
        } catch (e) {
            this.connected = false;
            throw e;
        }
    },

    /** Disconnect */
    disconnect() {
        this.token = null;
        this.refreshToken = null;
        this.connected = false;
        localStorage.removeItem('bc_connection');
        localStorage.removeItem('bc_credentials');
        if (this.wsConnection) {
            this.wsConnection.close();
            this.wsConnection = null;
        }
        App.updateConnectionStatus(false);
        App.showToast('Disconnected from Freqtrade', 'info');
    },

    /** Make authenticated request */
    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}/api/v1${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        try {
            const resp = await fetch(url, { ...options, headers });
            if (resp.status === 401) {
                // Try refresh token first
                const refreshed = await this.refreshAccessToken();
                if (refreshed) {
                    headers['Authorization'] = `Bearer ${this.token}`;
                    const retry = await fetch(url, { ...options, headers });
                    if (!retry.ok) throw new Error(`API Error: ${retry.status}`);
                    return await retry.json();
                }

                // Refresh failed - try re-login with saved credentials
                const relogged = await this.tryRelogin();
                if (relogged) {
                    headers['Authorization'] = `Bearer ${this.token}`;
                    const retry = await fetch(url, { ...options, headers });
                    if (!retry.ok) throw new Error(`API Error: ${retry.status}`);
                    return await retry.json();
                }

                this.connected = false;
                App.updateConnectionStatus(false);
                throw new Error('Session expired - please reconnect');
            }
            if (!resp.ok) {
                const errBody = await resp.text();
                throw new Error(`API Error ${resp.status}: ${errBody}`);
            }
            return await resp.json();
        } catch (e) {
            if (e.message.includes('Failed to fetch') || e.message.includes('NetworkError')) {
                this.connected = false;
                App.updateConnectionStatus(false);
            }
            throw e;
        }
    },

    /** Try to re-login using saved credentials */
    async tryRelogin() {
        const saved = localStorage.getItem('bc_connection');
        const creds = localStorage.getItem('bc_credentials');
        if (!saved || !creds) return false;
        try {
            const { url } = JSON.parse(saved);
            const { username, password } = JSON.parse(creds);
            if (!url || !username || !password) return false;
            await this.login(url, username, password);
            console.log('Auto re-login successful');
            return true;
        } catch {
            return false;
        }
    },

    /** Refresh access token */
    async refreshAccessToken() {
        if (!this.refreshToken) return false;
        try {
            const resp = await fetch(`${this.baseUrl}/api/v1/token/refresh`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.refreshToken}`,
                    'Content-Type': 'application/json'
                }
            });
            if (!resp.ok) return false;
            const data = await resp.json();
            this.token = data.access_token;
            this.refreshToken = data.refresh_token;
            localStorage.setItem('bc_connection', JSON.stringify({
                url: this.baseUrl, token: this.token, refreshToken: this.refreshToken
            }));
            return true;
        } catch {
            return false;
        }
    },

    /** Check connection */
    async ping() {
        try {
            const data = await this.request('/ping');
            this.connected = data.status === 'pong';
            return this.connected;
        } catch {
            this.connected = false;
            return false;
        }
    },

    // ========== INFO ENDPOINTS ==========
    async getVersion() { return this.request('/version'); },
    async getConfig() { return this.request('/show_config'); },
    async getLogs(limit = 50) { return this.request(`/logs?limit=${limit}`); },
    async getHealth() { return this.request('/health'); },
    async getSysInfo() { return this.request('/sysinfo'); },

    // ========== TRADING ENDPOINTS ==========
    async getBalance() { return this.request('/balance'); },
    async getTradeCount() { return this.request('/count'); },
    async getOpenTrades() { return this.request('/status'); },
    async getTrades(limit = 50, offset = 0) {
        return this.request(`/trades?limit=${limit}&offset=${offset}`);
    },
    async getTrade(id) { return this.request(`/trade/${id}`); },
    async getProfit() { return this.request('/profit'); },
    async getStats() { return this.request('/stats'); },
    async getDaily(days = 30) { return this.request(`/daily?timescale=${days}`); },
    async getWeekly(weeks = 12) { return this.request(`/weekly?timescale=${weeks}`); },
    async getMonthly(months = 6) { return this.request(`/monthly?timescale=${months}`); },
    async getPerformance() { return this.request('/performance'); },

    // ========== BOT CONTROL ==========
    async startBot() { return this.request('/start', { method: 'POST' }); },
    async stopBot() { return this.request('/stop', { method: 'POST' }); },
    async pauseBot() { return this.request('/pause', { method: 'POST' }); },
    async reloadConfig() { return this.request('/reload_config', { method: 'POST' }); },

    // ========== FORCE TRADE ==========
    async forceEntry(pair, side = 'long', options = {}) {
        return this.request('/forceenter', {
            method: 'POST',
            body: JSON.stringify({ pair, side, ...options })
        });
    },
    async forceExit(tradeId, options = {}) {
        return this.request('/forceexit', {
            method: 'POST',
            body: JSON.stringify({ tradeid: tradeId, ...options })
        });
    },
    async deleteTrade(id) {
        return this.request(`/trades/${id}`, { method: 'DELETE' });
    },

    // ========== PAIRS & DATA ==========
    async getWhitelist() { return this.request('/whitelist'); },
    async getBlacklist() { return this.request('/blacklist'); },
    async addBlacklist(pairs) {
        return this.request('/blacklist', {
            method: 'POST',
            body: JSON.stringify({ blacklist: pairs })
        });
    },
    async getPairCandles(pair, timeframe, limit = 500) {
        return this.request(`/pair_candles?pair=${encodeURIComponent(pair)}&timeframe=${timeframe}&limit=${limit}`);
    },
    async getAvailablePairs(timeframe) {
        let url = '/available_pairs';
        if (timeframe) url += `?timeframe=${timeframe}`;
        return this.request(url);
    },

    // ========== STRATEGY ==========
    async getStrategies() { return this.request('/strategies'); },
    async getStrategy(name) { return this.request(`/strategy/${encodeURIComponent(name)}`); },

    // ========== BACKTESTING ==========
    async startBacktest(config) {
        return this.request('/backtest', {
            method: 'POST',
            body: JSON.stringify(config)
        });
    },
    async getBacktestStatus() { return this.request('/backtest'); },
    async abortBacktest() { return this.request('/backtest/abort'); },
    async resetBacktest() { return this.request('/backtest', { method: 'DELETE' }); },
    async getBacktestHistory() { return this.request('/backtest/history'); },
    async getBacktestResult(filename, strategy) {
        return this.request(`/backtest/history/result?filename=${encodeURIComponent(filename)}&strategy=${encodeURIComponent(strategy)}`);
    },

    // ========== LOCKS ==========
    async getLocks() { return this.request('/locks'); },
    async deleteLock(id) { return this.request(`/locks/${id}`, { method: 'DELETE' }); },

    // ========== EXCHANGES ==========
    async getExchanges() { return this.request('/exchanges'); },
    async getMarkets(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this.request(`/markets${qs ? '?' + qs : ''}`);
    },

    // ========== BACKGROUND TASKS ==========
    async getBackgroundJobs() { return this.request('/background'); },
    async getBackgroundJob(id) { return this.request(`/background/${id}`); },

    // ========== PLOT CONFIG ==========
    async getPlotConfig(strategy) {
        return this.request(`/plot_config${strategy ? '?strategy=' + encodeURIComponent(strategy) : ''}`);
    },

    // ========== PAIR HISTORY (for backtesting charts) ==========
    async getPairHistory(pair, timeframe, timerange, strategy) {
        return this.request('/pair_history', {
            method: 'POST',
            body: JSON.stringify({ pair, timeframe, timerange, strategy })
        });
    },

    // ========== HYPEROPT LOSS ==========
    async getHyperoptLoss() { return this.request('/hyperoptloss'); },

    // ========== DATA DOWNLOAD ==========
    async downloadData(config) {
        return this.request('/download_data', {
            method: 'POST',
            body: JSON.stringify(config)
        });
    }
};

// Initialize on load
API.init();

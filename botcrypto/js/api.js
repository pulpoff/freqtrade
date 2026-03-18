/**
 * BotCrypto - Freqtrade API Client
 * Communicates with Freqtrade REST API v1
 */
const API = {
    baseUrl: '',
    token: null,
    refreshToken: null,
    connected: false,
    /** Track endpoints that fail with "not supported in backtesting mode" */
    _disabledEndpoints: new Set(),
    isBacktestingMode: false,
    /** Known trade-related endpoints that fail in backtesting mode */
    _tradeEndpoints: ['/profit', '/status', '/trades', '/stats', '/balance', '/count',
        '/daily', '/weekly', '/monthly', '/performance', '/stopentry', '/forceexit',
        '/forceenter'],

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
        this._disabledEndpoints.clear();
        this.isBacktestingMode = false;
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
        // Skip endpoints known to be unsupported in backtesting mode
        const baseEndpoint = endpoint.split('?')[0];
        if (this._disabledEndpoints.has(baseEndpoint)) {
            throw new Error('Endpoint not available in backtesting mode');
        }

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
                // Detect backtesting mode errors and disable the endpoint
                const isTradeEndpoint = this._tradeEndpoints.some(ep => baseEndpoint === ep || baseEndpoint.startsWith(ep + '/'));
                const isBacktestError = errBody.includes('not supported in backtesting mode') ||
                    (errBody.includes('NotImplementedError') && isTradeEndpoint);
                if (isBacktestError) {
                    this._disabledEndpoints.add(baseEndpoint);
                    if (!this.isBacktestingMode) {
                        this.isBacktestingMode = true;
                        // Pre-disable all known trade endpoints
                        this._tradeEndpoints.forEach(ep => this._disabledEndpoints.add(ep));
                        console.log('Backtesting mode detected - trade endpoints disabled');
                    }
                    throw new Error('Endpoint not available in backtesting mode');
                }
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
    /** Pause = stop new entries only */
    async pauseBot() { return this.request('/stopentry', { method: 'POST' }); },
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
            body: JSON.stringify({ tradeid: String(tradeId), ...options })
        });
    },
    async deleteTrade(id) {
        return this.request(`/trades/${id}`, { method: 'DELETE' });
    },
    async cancelOpenOrder(tradeId) {
        return this.request(`/trades/${tradeId}/open-order`, { method: 'DELETE' });
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
    async getPairCandles(pair, timeframe, limit = 500, columns) {
        if (columns) {
            return this.request('/pair_candles', {
                method: 'POST',
                body: JSON.stringify({ pair, timeframe, limit, columns })
            });
        }
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
    async deleteBacktestHistory(filename) {
        return this.request(`/backtest/history/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    },

    // ========== LOCKS ==========
    async getLocks() { return this.request('/locks'); },
    async deleteLock(id) { return this.request(`/locks/${id}`, { method: 'DELETE' }); },

    // ========== EXCHANGES ==========
    async getExchanges() { return this.request('/exchanges'); },

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

    // ========== PAIR OHLCV (raw exchange data, no strategy needed) ==========
    async getPairOhlcv(pair, timeframe, limit = 500) {
        return this.request(`/pair_ohlcv?pair=${encodeURIComponent(pair)}&timeframe=${timeframe}&limit=${limit}`);
    },

    // ========== DATA DOWNLOAD ==========
    async downloadData(config) {
        return this.request('/download_data', {
            method: 'POST',
            body: JSON.stringify(config)
        });
    },

    /**
     * Check available data and only download missing pair/timeframe combinations.
     * Returns the job_id if a download was started, or null if all data exists.
     */
    async downloadMissingData({ pairs, timeframes, timerange }) {
        try {
            const available = await this.getAvailablePairs();
            // Build set of existing pair+timeframe combos
            const existingSet = new Set();
            for (const pi of (available.pair_interval || [])) {
                existingSet.add(`${pi[0]}__${pi[1]}`);
            }
            // Filter to only missing timeframes per pair
            const missingTimeframes = timeframes.filter(tf =>
                pairs.some(p => !existingSet.has(`${p}__${tf}`))
            );
            if (missingTimeframes.length === 0) {
                console.log('All data already available, skipping download');
                return null;
            }
            console.log(`Downloading missing timeframes: ${missingTimeframes.join(', ')} (have: ${timeframes.filter(tf => !missingTimeframes.includes(tf)).join(', ') || 'none'})`);
            return this.downloadData({ pairs, timeframes: missingTimeframes, timerange });
        } catch (e) {
            console.log('Could not check available data, downloading all:', e.message);
            return this.downloadData({ pairs, timeframes, timerange });
        }
    },

    // ========== HELPER: Parse candle data ==========
    /** Convert Freqtrade pair_candles response to OHLCV array */
    parseCandleData(data) {
        if (!data || !data.columns || !data.data) return [];
        const cols = data.columns;
        const dateIdx = cols.indexOf('date');
        const openIdx = cols.indexOf('open');
        const highIdx = cols.indexOf('high');
        const lowIdx = cols.indexOf('low');
        const closeIdx = cols.indexOf('close');
        const volIdx = cols.indexOf('volume');

        return data.data.map(row => {
            let time;
            const dateVal = row[dateIdx];
            if (typeof dateVal === 'number') {
                // Epoch milliseconds → seconds
                time = Math.floor(dateVal / 1000);
            } else if (typeof dateVal === 'string') {
                // ISO date string like "2026-03-17T02:27:00+00:00"
                time = Math.floor(new Date(dateVal).getTime() / 1000);
            } else {
                time = 0;
            }

            return {
                time,
                open: row[openIdx],
                high: row[highIdx],
                low: row[lowIdx],
                close: row[closeIdx],
                volume: volIdx >= 0 ? row[volIdx] : 0,
            };
        }).filter(d => d.time > 0);
    },

    /** Extract signal columns from candle data */
    parseSignals(data) {
        if (!data || !data.columns || !data.data) return [];
        const cols = data.columns;
        const dateIdx = cols.indexOf('date');
        const enterLongIdx = cols.indexOf('enter_long');
        const exitLongIdx = cols.indexOf('exit_long');
        const enterShortIdx = cols.indexOf('enter_short');
        const exitShortIdx = cols.indexOf('exit_short');

        const signals = [];
        data.data.forEach(row => {
            const dateVal = row[dateIdx];
            let time;
            if (typeof dateVal === 'number') {
                time = Math.floor(dateVal / 1000);
            } else if (typeof dateVal === 'string') {
                time = Math.floor(new Date(dateVal).getTime() / 1000);
            } else {
                return;
            }
            if (enterLongIdx >= 0 && row[enterLongIdx] === 1) {
                signals.push({ time, type: 'enter_long' });
            }
            if (exitLongIdx >= 0 && row[exitLongIdx] === 1) {
                signals.push({ time, type: 'exit_long' });
            }
            if (enterShortIdx >= 0 && row[enterShortIdx] === 1) {
                signals.push({ time, type: 'enter_short' });
            }
            if (exitShortIdx >= 0 && row[exitShortIdx] === 1) {
                signals.push({ time, type: 'exit_short' });
            }
        });
        return signals;
    }
};

// Initialize on load
API.init();

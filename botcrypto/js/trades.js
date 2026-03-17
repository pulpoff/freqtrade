/**
 * BotCrypto - Trades Page
 * Shows open and closed trades, bot controls, performance data
 * Loads real data from Freqtrade API when connected
 */
const TradesPage = {
    activeTab: 'open',
    openTrades: [],
    closedTrades: [],
    stats: null,
    botState: null,
    refreshTimer: null,

    render() {
        return `
        <div id="tradesPage">
            ${API.isBacktestingMode ? `
            <div class="alert alert-info d-flex align-items-center mb-3">
                <i class="bi bi-flask me-2"></i>
                <span><strong>Backtesting Mode</strong> - Trade operations and live data are not available in this mode.</span>
            </div>` : ''}
            <!-- Bot Controls -->
            <div class="card mb-3">
                <div class="card-body">
                    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
                        <div class="d-flex align-items-center gap-2 gap-md-3 flex-wrap">
                            <h5 class="fw-semibold mb-0"><i class="bi bi-robot me-2"></i>Bot Status</h5>
                            <span class="badge badge-bc" id="botStatusBadge">
                                <span class="status-dot disconnected me-1"></span> Not Connected
                            </span>
                            <small class="text-secondary" id="botStrategyName"></small>
                        </div>
                        <div class="d-flex gap-2 flex-wrap">
                            <button class="btn btn-success btn-sm" id="btnStartBot" onclick="TradesPage.startBot()">
                                <i class="bi bi-play-fill me-1"></i> Start
                            </button>
                            <button class="btn btn-warning btn-sm" id="btnPauseBot" onclick="TradesPage.pauseBot()">
                                <i class="bi bi-pause-fill me-1"></i> Pause
                            </button>
                            <button class="btn btn-danger btn-sm" id="btnStopBot" onclick="TradesPage.stopBot()">
                                <i class="bi bi-stop-fill me-1"></i> Stop
                            </button>
                            <button class="btn btn-outline-secondary btn-sm" onclick="TradesPage.reloadConfig()">
                                <i class="bi bi-arrow-clockwise me-1"></i> Reload Config
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Summary Stats -->
            <div class="row g-2 g-md-3 mb-3" id="tradesSummary">
                <div class="col-4 col-md-2">
                    <div class="card">
                        <div class="card-body py-2 py-md-3 text-center">
                            <div class="stat-value" id="tsOpenCount">0</div>
                            <div class="stat-label">Open Trades</div>
                        </div>
                    </div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="card">
                        <div class="card-body py-2 py-md-3 text-center">
                            <div class="stat-value" id="tsClosedCount">0</div>
                            <div class="stat-label">Closed Trades</div>
                        </div>
                    </div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="card">
                        <div class="card-body py-2 py-md-3 text-center">
                            <div class="stat-value text-profit" id="tsTotalProfit">0</div>
                            <div class="stat-label">Total Profit</div>
                        </div>
                    </div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="card">
                        <div class="card-body py-2 py-md-3 text-center">
                            <div class="stat-value text-profit" id="tsWinRate">0%</div>
                            <div class="stat-label">Win Rate</div>
                        </div>
                    </div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="card">
                        <div class="card-body py-2 py-md-3 text-center">
                            <div class="stat-value" id="tsAvgDuration">-</div>
                            <div class="stat-label">Avg Duration</div>
                        </div>
                    </div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="card">
                        <div class="card-body py-2 py-md-3 text-center">
                            <div class="stat-value" id="tsBalance">0</div>
                            <div class="stat-label">Balance</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Tabs -->
            <div class="card">
                <div class="card-header">
                    <ul class="nav nav-tabs card-header-tabs flex-nowrap overflow-auto">
                        <li class="nav-item">
                            <a class="nav-link text-nowrap ${this.activeTab === 'open' ? 'active' : ''}" href="#"
                                onclick="event.preventDefault(); TradesPage.switchTab('open')">
                                <i class="bi bi-arrow-left-right me-1"></i> Open Trades
                                <span class="badge bg-success ms-1" id="openTradeCount">0</span>
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link ${this.activeTab === 'closed' ? 'active' : ''}" href="#"
                                onclick="event.preventDefault(); TradesPage.switchTab('closed')">
                                <i class="bi bi-check-circle me-1"></i> Trade History
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link ${this.activeTab === 'performance' ? 'active' : ''}" href="#"
                                onclick="event.preventDefault(); TradesPage.switchTab('performance')">
                                <i class="bi bi-graph-up me-1"></i> Performance
                            </a>
                        </li>
                    </ul>
                </div>
                <div class="card-body" id="tradesContent">
                    ${this.renderTabContent()}
                </div>
            </div>

            <!-- Force Trade Section -->
            <div class="card mt-3">
                <div class="card-header">
                    <h6 class="mb-0"><i class="bi bi-lightning me-2"></i>Force Trade</h6>
                </div>
                <div class="card-body">
                    <div class="row g-2 g-md-3">
                        <div class="col-6 col-md-3">
                            <label class="form-label small text-secondary">Pair</label>
                            <select class="form-select" id="forcePair">
                                <option value="BTC/USDT">BTC/USDT</option>
                            </select>
                        </div>
                        <div class="col-6 col-md-2">
                            <label class="form-label small text-secondary">Side</label>
                            <select class="form-select" id="forceSide">
                                <option value="long">Long</option>
                                <option value="short">Short</option>
                            </select>
                        </div>
                        <div class="col-6 col-md-2">
                            <label class="form-label small text-secondary">Stake Amount</label>
                            <input type="number" class="form-control" id="forceStake" placeholder="0">
                        </div>
                        <div class="col-6 col-md-2">
                            <label class="form-label small text-secondary">Price (0=market)</label>
                            <input type="number" class="form-control" id="forcePrice" value="0" step="0.01">
                        </div>
                        <div class="col-12 col-md-3 d-flex align-items-end gap-2">
                            <button class="btn btn-success flex-grow-1" onclick="TradesPage.forceEntry()">
                                <i class="bi bi-plus-circle me-1"></i> Force Buy
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
    },

    renderTabContent() {
        if (this.activeTab === 'open') {
            return this.renderOpenTrades();
        } else if (this.activeTab === 'closed') {
            return this.renderClosedTrades();
        } else {
            return this.renderPerformance();
        }
    },

    renderOpenTrades() {
        if (this.openTrades.length === 0) {
            return Components.emptyState('arrow-left-right', 'No open trades', 'Start the bot or force a trade to begin');
        }
        return `
        <div class="table-responsive">
            <table class="table table-hover mb-0">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Pair</th>
                        <th>Side</th>
                        <th>Open Rate</th>
                        <th>Current Rate</th>
                        <th>Profit</th>
                        <th>Stake</th>
                        <th>Duration</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${this.openTrades.map(t => `
                    <tr>
                        <td>${t.trade_id}</td>
                        <td class="fw-semibold">${Components.cleanPairName(t.pair)}</td>
                        <td><span class="badge ${t.is_short ? 'bg-danger' : 'bg-success'}">${t.is_short ? 'Short' : 'Long'}</span></td>
                        <td>${Components.formatNumber(t.open_rate, 6)}</td>
                        <td>${Components.formatNumber(t.current_rate || t.open_rate, 6)}</td>
                        <td class="${(t.profit_ratio || 0) >= 0 ? 'text-profit' : 'text-loss'} fw-semibold">
                            ${Components.formatPercent((t.profit_ratio || 0) * 100)}
                            <br><small>${(t.profit_abs || 0) >= 0 ? '+' : ''}${Components.formatNumber(t.profit_abs || 0)} ${t.stake_currency || 'USDT'}</small>
                        </td>
                        <td>${Components.formatNumber(t.stake_amount, 4)} ${t.stake_currency || 'USDT'}</td>
                        <td class="small text-secondary">${t.open_date ? this.timeSince(t.open_date) : '-'}</td>
                        <td>
                            <div class="btn-group btn-group-sm">
                                <button class="btn btn-outline-danger" onclick="TradesPage.forceExit(${t.trade_id})" title="Force Sell">
                                    <i class="bi bi-x-circle"></i>
                                </button>
                                <button class="btn btn-outline-secondary" onclick="TradesPage.deleteTrade(${t.trade_id})" title="Delete">
                                    <i class="bi bi-trash"></i>
                                </button>
                            </div>
                        </td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
    },

    renderClosedTrades() {
        if (this.closedTrades.length === 0) {
            return Components.emptyState('check-circle', 'No trade history', 'Closed trades will appear here');
        }
        return `
        <div class="table-responsive">
            <table class="table table-hover mb-0">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Pair</th>
                        <th>Profit</th>
                        <th>Open Rate</th>
                        <th>Close Rate</th>
                        <th>Stake</th>
                        <th>Duration</th>
                        <th>Exit Reason</th>
                    </tr>
                </thead>
                <tbody>
                    ${this.closedTrades.map(t => `
                    <tr>
                        <td>${t.trade_id}</td>
                        <td class="fw-semibold">${Components.cleanPairName(t.pair)}</td>
                        <td class="${(t.profit_ratio || 0) >= 0 ? 'text-profit' : 'text-loss'} fw-semibold">
                            ${Components.formatPercent((t.profit_ratio || 0) * 100)}
                            <br><small>${(t.profit_abs || 0) >= 0 ? '+' : ''}${Components.formatNumber(t.profit_abs || 0)}</small>
                        </td>
                        <td>${Components.formatNumber(t.open_rate, 6)}</td>
                        <td>${Components.formatNumber(t.close_rate, 6)}</td>
                        <td>${Components.formatNumber(t.stake_amount, 4)}</td>
                        <td class="small text-secondary">${Components.formatDuration(t.trade_duration || t.close_profit_abs)}</td>
                        <td><span class="badge bg-secondary">${t.exit_reason || t.sell_reason || '-'}</span></td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
    },

    renderPerformance() {
        return `
        <div id="performanceContent">
            ${Components.loading('Loading performance data...')}
        </div>`;
    },

    async loadPerformanceData() {
        const container = document.getElementById('performanceContent');
        if (!container) return;

        try {
            if (!API.connected) {
                container.innerHTML = Components.emptyState('graph-up', 'Not connected', 'Connect to Freqtrade to see performance data');
                return;
            }

            const [perf, daily] = await Promise.all([
                API.getPerformance().catch(() => []),
                API.getDaily(30).catch(() => null),
            ]);

            let html = '<div class="row g-3">';

            // Per-pair performance table
            html += '<div class="col-lg-6">';
            html += '<h6 class="fw-semibold mb-3"><i class="bi bi-bar-chart me-2"></i>Pair Performance</h6>';
            if (Array.isArray(perf) && perf.length > 0) {
                html += `<div class="table-responsive"><table class="table table-hover mb-0">
                    <thead><tr><th>Pair</th><th>Profit</th><th>Trades</th></tr></thead><tbody>`;
                perf.forEach(p => {
                    const profitClass = (p.profit || 0) >= 0 ? 'text-profit' : 'text-loss';
                    html += `<tr>
                        <td class="fw-semibold">${p.pair}</td>
                        <td class="${profitClass}">${Components.formatNumber(p.profit, 2)}%</td>
                        <td>${p.count || 0}</td>
                    </tr>`;
                });
                html += '</tbody></table></div>';
            } else {
                html += '<div class="text-secondary small">No performance data yet</div>';
            }
            html += '</div>';

            // Daily profit table
            html += '<div class="col-lg-6">';
            html += '<h6 class="fw-semibold mb-3"><i class="bi bi-calendar me-2"></i>Daily Profit (Last 30d)</h6>';
            if (daily && daily.data && daily.data.length > 0) {
                html += `<div class="table-responsive" style="max-height:400px;overflow:auto"><table class="table table-hover mb-0">
                    <thead><tr><th>Date</th><th>Profit</th><th>Trades</th></tr></thead><tbody>`;
                daily.data.forEach(d => {
                    const profitClass = (d.abs_profit || 0) >= 0 ? 'text-profit' : 'text-loss';
                    const sign = (d.abs_profit || 0) >= 0 ? '+' : '';
                    html += `<tr>
                        <td class="small">${d.date}</td>
                        <td class="${profitClass}">${sign}${Components.formatNumber(d.abs_profit, 4)} ${daily.stake_currency || 'USDT'}</td>
                        <td>${d.trade_count || 0}</td>
                    </tr>`;
                });
                html += '</tbody></table></div>';
            } else {
                html += '<div class="text-secondary small">No daily data yet</div>';
            }
            html += '</div>';

            html += '</div>';
            container.innerHTML = html;

        } catch (e) {
            container.innerHTML = Components.emptyState('graph-up', 'Error loading performance', e.message);
        }
    },

    async init() {
        await this.loadPairList();
        await this.loadData();
        // Auto-refresh every 15 seconds
        this.refreshTimer = setInterval(() => this.loadData(), 15000);
    },

    async loadPairList() {
        const select = document.getElementById('forcePair');
        if (!select) return;

        try {
            if (API.connected) {
                const whitelist = await API.getWhitelist();
                if (whitelist && whitelist.whitelist && whitelist.whitelist.length > 0) {
                    select.innerHTML = whitelist.whitelist.map(p =>
                        `<option value="${p}">${Components.cleanPairName(p)}</option>`
                    ).join('');
                }
            }
        } catch (e) {
            console.log('Could not load pair list:', e.message);
        }
    },

    async loadData() {
        try {
            if (!API.connected) {
                this.showDemoData();
                return;
            }

            // Always fetch config first (works in all modes including backtesting)
            const config = await API.getConfig().catch(() => null);

            // Update bot status right away - even if trade endpoints fail
            if (config) {
                this.updateBotStatus(config);
            } else if (API.connected) {
                // Connected but config failed - show connected status
                const badge = document.getElementById('botStatusBadge');
                if (badge) {
                    badge.innerHTML = '<span class="status-dot connected me-1"></span> Connected';
                    badge.className = 'badge badge-bc badge-completed';
                }
            }

            // Try trade endpoints - these fail in backtesting mode
            const [openTrades, trades, profit, balance, stats] = await Promise.all([
                API.getOpenTrades().catch(() => []),
                API.getTrades(100).catch(() => ({ trades: [] })),
                API.getProfit().catch(() => null),
                API.getBalance().catch(() => null),
                API.getStats().catch(() => null),
            ]);

            this.openTrades = Array.isArray(openTrades) ? openTrades : [];
            this.closedTrades = trades.trades ? trades.trades.filter(t => !t.is_open) : [];
            this.stats = stats;

            // Update summary stats
            const el = (id) => document.getElementById(id);
            if (el('tsOpenCount')) el('tsOpenCount').textContent = this.openTrades.length;
            if (el('tsClosedCount')) el('tsClosedCount').textContent = this.closedTrades.length;
            if (el('openTradeCount')) el('openTradeCount').textContent = this.openTrades.length;

            if (profit) {
                const totalTrades = (profit.winning_trades || 0) + (profit.losing_trades || 0);
                if (el('tsTotalProfit')) {
                    const profitVal = profit.profit_closed_coin || 0;
                    el('tsTotalProfit').textContent = `${profitVal >= 0 ? '+' : ''}${Components.formatNumber(profitVal)}`;
                    el('tsTotalProfit').className = `stat-value ${profitVal >= 0 ? 'text-profit' : 'text-loss'}`;
                }
                if (el('tsWinRate') && totalTrades > 0) {
                    el('tsWinRate').textContent = Components.formatPercent((profit.winning_trades / totalTrades) * 100);
                }
                if (el('tsAvgDuration') && profit.avg_duration) {
                    el('tsAvgDuration').textContent = profit.avg_duration;
                }
            }

            if (balance) {
                if (el('tsBalance')) el('tsBalance').textContent = Components.formatNumber(balance.total || 0, 2);
            }

            this.updateTabContent();
        } catch (e) {
            console.error('Trades load error:', e);
            this.showDemoData();
        }
    },

    updateBotStatus(config) {
        const badge = document.getElementById('botStatusBadge');
        const stratName = document.getElementById('botStrategyName');
        if (!badge) return;

        const state = config.state || 'unknown';
        const strategy = config.strategy || '';

        if (stratName) stratName.textContent = strategy ? `Strategy: ${strategy}` : '';

        if (state === 'running') {
            badge.innerHTML = '<span class="status-dot connected me-1"></span> Running';
            badge.className = 'badge badge-bc badge-completed';
        } else if (state === 'stopped') {
            badge.innerHTML = '<span class="status-dot disconnected me-1"></span> Stopped';
            badge.className = 'badge badge-bc badge-failed';
        } else {
            badge.innerHTML = '<span class="status-dot me-1" style="background:#f0ad4e"></span> ' + state;
            badge.className = 'badge badge-bc';
        }
    },

    showDemoData() {
        if (API.connected) {
            // Connected but trade endpoints unavailable (backtesting mode)
            this.closedTrades = [];
            this.openTrades = [];
            // Still show connected status
            const badge = document.getElementById('botStatusBadge');
            if (badge) {
                badge.innerHTML = '<span class="status-dot connected me-1"></span> Connected (Backtesting)';
                badge.className = 'badge badge-bc badge-completed';
            }
        } else {
            this.closedTrades = Components.generateDemoTrades(20);
            this.openTrades = [];
            const el = (id) => document.getElementById(id);
            if (el('tsClosedCount')) el('tsClosedCount').textContent = this.closedTrades.length;

            const totalProfit = this.closedTrades.reduce((s, t) => s + (t.profit_abs || 0), 0);
            const winCount = this.closedTrades.filter(t => t.profit_abs > 0).length;
            if (el('tsTotalProfit')) el('tsTotalProfit').textContent = Components.formatNumber(totalProfit);
            if (el('tsWinRate')) el('tsWinRate').textContent = Components.formatPercent(winCount / this.closedTrades.length * 100);
            if (el('tsBalance')) el('tsBalance').textContent = '1,000.00';
        }

        this.updateTabContent();
    },

    switchTab(tab) {
        this.activeTab = tab;
        // Update tab UI
        document.querySelectorAll('.card-header-tabs .nav-link').forEach(el => {
            el.classList.remove('active');
        });
        event.target.closest('.nav-link').classList.add('active');
        this.updateTabContent();

        // Load performance data when switching to performance tab
        if (tab === 'performance') {
            this.loadPerformanceData();
        }
    },

    updateTabContent() {
        const content = document.getElementById('tradesContent');
        if (content) content.innerHTML = this.renderTabContent();

        // Load performance if that tab is active
        if (this.activeTab === 'performance') {
            this.loadPerformanceData();
        }
    },

    // Bot controls
    async startBot() {
        try {
            if (!API.connected) { App.showToast('Not connected', 'warning'); return; }
            await API.startBot();
            App.showToast('Bot started', 'success');
            setTimeout(() => this.loadData(), 1000);
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async stopBot() {
        try {
            if (!API.connected) { App.showToast('Not connected', 'warning'); return; }
            await API.stopBot();
            App.showToast('Bot stopped', 'info');
            setTimeout(() => this.loadData(), 1000);
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async pauseBot() {
        try {
            if (!API.connected) { App.showToast('Not connected', 'warning'); return; }
            await API.pauseBot();
            App.showToast('Bot paused (no new entries)', 'info');
            setTimeout(() => this.loadData(), 1000);
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async reloadConfig() {
        try {
            if (!API.connected) { App.showToast('Not connected', 'warning'); return; }
            await API.reloadConfig();
            App.showToast('Config reloaded', 'success');
            setTimeout(() => this.loadData(), 1000);
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async forceEntry() {
        const pair = document.getElementById('forcePair').value;
        const side = document.getElementById('forceSide').value;
        const stake = parseFloat(document.getElementById('forceStake').value) || undefined;
        const price = parseFloat(document.getElementById('forcePrice').value) || undefined;

        if (!pair) { App.showToast('Enter a pair', 'warning'); return; }
        if (!API.connected) { App.showToast('Not connected', 'warning'); return; }

        try {
            await API.forceEntry(pair, side, {
                stakeamount: stake,
                price: price > 0 ? price : undefined
            });
            App.showToast(`Force entry: ${pair} ${side}`, 'success');
            setTimeout(() => this.loadData(), 2000);
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async forceExit(tradeId) {
        if (!confirm(`Force sell trade #${tradeId}?`)) return;
        try {
            await API.forceExit(tradeId);
            App.showToast(`Force exit: trade #${tradeId}`, 'success');
            setTimeout(() => this.loadData(), 2000);
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async deleteTrade(tradeId) {
        if (!confirm(`Delete trade #${tradeId}? This cannot be undone.`)) return;
        try {
            await API.deleteTrade(tradeId);
            App.showToast(`Trade #${tradeId} deleted`, 'info');
            setTimeout(() => this.loadData(), 1000);
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    timeSince(dateStr) {
        const d = new Date(dateStr);
        const diff = Date.now() - d.getTime();
        const hours = Math.floor(diff / 3600000);
        const mins = Math.floor((diff % 3600000) / 60000);
        if (hours > 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
        if (hours > 0) return `${hours}h ${mins}m`;
        return `${mins}m`;
    },

    destroy() {
        if (this.refreshTimer) { clearInterval(this.refreshTimer); this.refreshTimer = null; }
    }
};

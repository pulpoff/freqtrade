/**
 * BotCrypto - Trades Page
 * Shows open and closed trades, with bot controls
 */
const TradesPage = {
    activeTab: 'open',
    openTrades: [],
    closedTrades: [],
    stats: null,

    render() {
        return `
        <div id="tradesPage">
            <!-- Bot Controls -->
            <div class="card mb-3">
                <div class="card-body">
                    <div class="d-flex align-items-center justify-content-between">
                        <div class="d-flex align-items-center gap-3">
                            <h5 class="fw-semibold mb-0"><i class="bi bi-robot me-2"></i>Bot Status</h5>
                            <span class="badge badge-bc" id="botStatusBadge">
                                <span class="status-dot disconnected me-1"></span> Not Connected
                            </span>
                        </div>
                        <div class="d-flex gap-2">
                            <button class="btn btn-success btn-sm" onclick="TradesPage.startBot()">
                                <i class="bi bi-play-fill me-1"></i> Start
                            </button>
                            <button class="btn btn-warning btn-sm" onclick="TradesPage.pauseBot()">
                                <i class="bi bi-pause-fill me-1"></i> Pause
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="TradesPage.stopBot()">
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
            <div class="row g-3 mb-3" id="tradesSummary">
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body py-3 text-center">
                            <div class="stat-value" id="tsOpenCount">0</div>
                            <div class="stat-label">Open Trades</div>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body py-3 text-center">
                            <div class="stat-value" id="tsClosedCount">0</div>
                            <div class="stat-label">Closed Trades</div>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body py-3 text-center">
                            <div class="stat-value text-profit" id="tsTotalProfit">0</div>
                            <div class="stat-label">Total Profit</div>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body py-3 text-center">
                            <div class="stat-value text-profit" id="tsWinRate">0%</div>
                            <div class="stat-label">Win Rate</div>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body py-3 text-center">
                            <div class="stat-value" id="tsAvgDuration">-</div>
                            <div class="stat-label">Avg Duration</div>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body py-3 text-center">
                            <div class="stat-value" id="tsBalance">0</div>
                            <div class="stat-label">Balance</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Tabs -->
            <div class="card">
                <div class="card-header">
                    <ul class="nav nav-tabs card-header-tabs">
                        <li class="nav-item">
                            <a class="nav-link ${this.activeTab === 'open' ? 'active' : ''}" href="#"
                                onclick="TradesPage.switchTab('open')">
                                <i class="bi bi-arrow-left-right me-1"></i> Open Trades
                                <span class="badge bg-success ms-1" id="openTradeCount">0</span>
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link ${this.activeTab === 'closed' ? 'active' : ''}" href="#"
                                onclick="TradesPage.switchTab('closed')">
                                <i class="bi bi-check-circle me-1"></i> Trade History
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link ${this.activeTab === 'performance' ? 'active' : ''}" href="#"
                                onclick="TradesPage.switchTab('performance')">
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
                    <div class="row g-3">
                        <div class="col-md-3">
                            <label class="form-label small text-secondary">Pair</label>
                            <input type="text" class="form-control" id="forcePair" value="BTC/USDT" placeholder="BTC/USDT">
                        </div>
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">Side</label>
                            <select class="form-select" id="forceSide">
                                <option value="long">Long</option>
                                <option value="short">Short</option>
                            </select>
                        </div>
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">Stake Amount</label>
                            <input type="number" class="form-control" id="forceStake" placeholder="0">
                        </div>
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">Price (0=market)</label>
                            <input type="number" class="form-control" id="forcePrice" value="0" step="0.01">
                        </div>
                        <div class="col-md-3 d-flex align-items-end gap-2">
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
                        <td class="fw-semibold">${t.pair}</td>
                        <td>${Components.formatNumber(t.open_rate, 6)}</td>
                        <td>${Components.formatNumber(t.current_rate || t.open_rate, 6)}</td>
                        <td class="${(t.profit_ratio || 0) >= 0 ? 'text-profit' : 'text-loss'} fw-semibold">
                            ${Components.formatPercent(t.profit_ratio * 100)}
                            <br><small>${Components.formatNumber(t.profit_abs || 0)}</small>
                        </td>
                        <td>${Components.formatNumber(t.stake_amount, 4)}</td>
                        <td class="small text-secondary">${t.open_date ? this.timeSince(t.open_date) : '-'}</td>
                        <td>
                            <button class="btn btn-outline-danger btn-sm" onclick="TradesPage.forceExit(${t.trade_id})">
                                <i class="bi bi-x-circle me-1"></i> Sell
                            </button>
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
        return Components.tradesTable(this.closedTrades, false);
    },

    renderPerformance() {
        return `
        <div class="row g-3" id="performanceContent">
            ${Components.emptyState('graph-up', 'Loading performance...', 'Connect to see performance data')}
        </div>`;
    },

    async init() {
        await this.loadData();
    },

    async loadData() {
        try {
            if (!API.connected) {
                this.showDemoData();
                return;
            }

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

            // Update summary
            document.getElementById('tsOpenCount').textContent = this.openTrades.length;
            document.getElementById('tsClosedCount').textContent = this.closedTrades.length;
            document.getElementById('openTradeCount').textContent = this.openTrades.length;

            if (profit) {
                document.getElementById('tsTotalProfit').textContent = Components.formatNumber(profit.profit_closed_coin || 0);
                const total = (profit.winning_trades || 0) + (profit.losing_trades || 0);
                document.getElementById('tsWinRate').textContent = total > 0
                    ? Components.formatPercent((profit.winning_trades / total) * 100) : '0%';
            }

            if (balance) {
                document.getElementById('tsBalance').textContent = Components.formatNumber(balance.total || 0, 2);
            }

            if (stats && stats.durations) {
                const avg = stats.durations.wins || stats.durations.draws || '?';
                document.getElementById('tsAvgDuration').textContent = typeof avg === 'number' ? `${avg}min` : avg;
            }

            // Update status badge
            const badge = document.getElementById('botStatusBadge');
            badge.innerHTML = '<span class="status-dot connected me-1"></span> Connected';
            badge.classList.add('badge-completed');

            this.updateTabContent();
        } catch (e) {
            console.error('Trades load error:', e);
            this.showDemoData();
        }
    },

    showDemoData() {
        this.closedTrades = Components.generateDemoTrades(20);
        this.openTrades = [];
        document.getElementById('tsClosedCount').textContent = this.closedTrades.length;

        const totalProfit = this.closedTrades.reduce((s, t) => s + (t.profit_abs || 0), 0);
        const winCount = this.closedTrades.filter(t => t.profit_abs > 0).length;
        document.getElementById('tsTotalProfit').textContent = Components.formatNumber(totalProfit);
        document.getElementById('tsWinRate').textContent = Components.formatPercent(winCount / this.closedTrades.length * 100);
        document.getElementById('tsBalance').textContent = '1,000.00';

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
    },

    updateTabContent() {
        const content = document.getElementById('tradesContent');
        if (content) content.innerHTML = this.renderTabContent();
    },

    // Bot controls
    async startBot() {
        try {
            if (!API.connected) { App.showToast('Not connected', 'warning'); return; }
            await API.startBot();
            App.showToast('Bot started', 'success');
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async stopBot() {
        try {
            if (!API.connected) { App.showToast('Not connected', 'warning'); return; }
            await API.stopBot();
            App.showToast('Bot stopped', 'info');
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async pauseBot() {
        try {
            if (!API.connected) { App.showToast('Not connected', 'warning'); return; }
            await API.pauseBot();
            App.showToast('Bot paused', 'info');
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async reloadConfig() {
        try {
            if (!API.connected) { App.showToast('Not connected', 'warning'); return; }
            await API.reloadConfig();
            App.showToast('Config reloaded', 'success');
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async forceEntry() {
        const pair = document.getElementById('forcePair').value;
        const side = document.getElementById('forceSide').value;
        const stake = parseFloat(document.getElementById('forceStake').value) || undefined;
        const price = parseFloat(document.getElementById('forcePrice').value) || undefined;

        if (!pair) { App.showToast('Enter a pair', 'warning'); return; }

        try {
            if (!API.connected) { App.showToast('Not connected', 'warning'); return; }
            await API.forceEntry(pair, side, { stakeamount: stake, price: price > 0 ? price : undefined });
            App.showToast(`Force entry: ${pair} ${side}`, 'success');
            setTimeout(() => this.loadData(), 1000);
        } catch (e) { App.showToast(`Error: ${e.message}`, 'error'); }
    },

    async forceExit(tradeId) {
        if (!confirm(`Force sell trade #${tradeId}?`)) return;
        try {
            await API.forceExit(tradeId);
            App.showToast(`Force exit: trade #${tradeId}`, 'success');
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

    destroy() {}
};

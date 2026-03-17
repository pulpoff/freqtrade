/**
 * BotCrypto - My Robots Page
 * Bot management with start/stop toggles, status, ROI tracking
 * Similar to botcrypto.io's "Mes robots" view
 */
const RobotsPage = {
    robots: [],
    refreshTimer: null,

    render() {
        return `
        <div id="robotsPage">
            <div class="d-flex align-items-center justify-content-between mb-4">
                <h4 class="fw-semibold mb-0"><i class="bi bi-robot me-2"></i>My Robots</h4>
                <button class="btn btn-success" onclick="RobotsPage.showNewBotModal()">
                    <i class="bi bi-plus-lg me-1"></i> New Robot
                </button>
            </div>

            <!-- Active Bot Info (from Freqtrade) -->
            <div class="card mb-3" id="activeBotCard">
                <div class="card-body">
                    <div class="d-flex align-items-center justify-content-between mb-3">
                        <h6 class="fw-semibold mb-0"><i class="bi bi-broadcast me-2 text-success"></i>Active Freqtrade Bot</h6>
                        <div class="d-flex gap-2" id="robotBotControls">
                            <button class="btn btn-success btn-sm" onclick="RobotsPage.controlBot('start')">
                                <i class="bi bi-play-fill me-1"></i> Start
                            </button>
                            <button class="btn btn-warning btn-sm" onclick="RobotsPage.controlBot('pause')">
                                <i class="bi bi-pause-fill me-1"></i> Pause
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="RobotsPage.controlBot('stop')">
                                <i class="bi bi-stop-fill me-1"></i> Stop
                            </button>
                        </div>
                    </div>
                    <div class="row g-3" id="activeBotInfo">
                        <div class="col-12 text-center text-secondary py-3">
                            <small>Connect to Freqtrade to see bot status</small>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Saved Robots List -->
            <div class="card">
                <div class="card-header d-flex align-items-center justify-content-between">
                    <h6 class="mb-0"><i class="bi bi-collection me-2"></i>Robot Configurations</h6>
                    <small class="text-secondary" id="robotCount">0 robots</small>
                </div>
                <div class="card-body" id="robotsList">
                    ${this.renderRobotsList()}
                </div>
            </div>
        </div>`;
    },

    async init() {
        this.robots = JSON.parse(localStorage.getItem('bc_robots') || '[]');
        await this.loadActiveBotInfo();
        this.refreshTimer = setInterval(() => this.loadActiveBotInfo(), 15000);
    },

    async loadActiveBotInfo() {
        const el = document.getElementById('activeBotInfo');
        if (!el) return;

        if (!API.connected) {
            el.innerHTML = `<div class="col-12 text-center text-secondary py-3">
                <small>Connect to Freqtrade to see bot status</small>
            </div>`;
            return;
        }

        try {
            const [config, profit, openTrades, count, balance] = await Promise.all([
                API.getConfig().catch(() => null),
                API.getProfit().catch(() => null),
                API.getOpenTrades().catch(() => []),
                API.getTradeCount().catch(() => null),
                API.getBalance().catch(() => null),
            ]);

            const state = config?.state || 'unknown';
            const strategy = config?.strategy || '-';
            const exchange = config?.exchange || '-';
            const pair = config?.trading_mode || 'spot';
            const dryRun = config?.dry_run;
            const openCount = Array.isArray(openTrades) ? openTrades.length : (count?.current || 0);
            const closedCount = count?.closed || 0;
            const totalProfit = profit?.profit_all_coin || 0;
            const profitPct = profit?.profit_all_percent || ((profit?.profit_all_ratio_sum || 0) * 100);
            const stakeCurrency = profit?.stake_currency || config?.stake_currency || 'USDT';
            const totalBalance = balance?.total || 0;

            el.innerHTML = `
                <div class="col-6 col-md-2">
                    <div class="text-secondary small mb-1">Status</div>
                    <span class="badge ${state === 'running' ? 'bg-success' : state === 'stopped' ? 'bg-danger' : 'bg-warning'} fs-6">
                        <i class="bi bi-${state === 'running' ? 'play-circle' : 'stop-circle'} me-1"></i>
                        ${state.charAt(0).toUpperCase() + state.slice(1)}
                    </span>
                    ${dryRun !== undefined ? `<br><span class="badge ${dryRun ? 'bg-warning text-dark' : 'bg-danger'} mt-1">${dryRun ? 'Dry Run' : 'LIVE'}</span>` : ''}
                </div>
                <div class="col-6 col-md-2">
                    <div class="text-secondary small mb-1">Strategy</div>
                    <div class="fw-semibold">${strategy}</div>
                    <small class="text-secondary">${exchange} · ${pair}</small>
                </div>
                <div class="col-4 col-md-2">
                    <div class="text-secondary small mb-1">Open / Closed</div>
                    <div class="fw-semibold">${openCount} <span class="text-secondary">/</span> ${closedCount}</div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="text-secondary small mb-1">Total Profit</div>
                    <div class="fw-semibold ${totalProfit >= 0 ? 'text-profit' : 'text-loss'}">
                        ${totalProfit >= 0 ? '+' : ''}${Components.formatNumber(totalProfit, 2)} ${stakeCurrency}
                    </div>
                    <small class="${profitPct >= 0 ? 'text-profit' : 'text-loss'}">${profitPct >= 0 ? '+' : ''}${Components.formatNumber(profitPct, 2)}%</small>
                </div>
                <div class="col-4 col-md-2">
                    <div class="text-secondary small mb-1">Balance</div>
                    <div class="fw-semibold">${Components.formatNumber(totalBalance, 2)} ${stakeCurrency}</div>
                </div>
                <div class="col-12 col-md-2">
                    <div class="text-secondary small mb-1">Open Trades</div>
                    ${Array.isArray(openTrades) && openTrades.length > 0 ?
                        openTrades.slice(0, 3).map(t => `<div class="small"><span class="fw-semibold">${Components.cleanPairName ? Components.cleanPairName(t.pair) : t.pair}</span> <span class="${(t.profit_ratio || 0) >= 0 ? 'text-profit' : 'text-loss'}">${Components.formatNumber((t.profit_ratio || 0) * 100, 2)}%</span></div>`).join('') +
                        (openTrades.length > 3 ? `<small class="text-secondary">+${openTrades.length - 3} more</small>` : '')
                    : '<small class="text-secondary">None</small>'}
                </div>`;
        } catch (e) {
            console.log('Bot info error:', e.message);
        }
    },

    async controlBot(action) {
        if (!API.connected) {
            App.showToast('Not connected to Freqtrade', 'warning');
            return;
        }
        try {
            if (action === 'start') await API.startBot();
            else if (action === 'stop') await API.stopBot();
            else if (action === 'pause') await API.pauseBot();
            App.showToast(`Bot ${action} command sent`, 'success');
            setTimeout(() => this.loadActiveBotInfo(), 1000);
        } catch (e) {
            App.showToast(`Failed: ${e.message}`, 'error');
        }
    },

    renderRobotsList() {
        const robots = JSON.parse(localStorage.getItem('bc_robots') || '[]');
        if (robots.length === 0) {
            return `<div class="text-center text-secondary py-4">
                <i class="bi bi-robot fs-1 d-block mb-2"></i>
                <p>No robot configurations saved yet</p>
                <button class="btn btn-outline-success btn-sm" onclick="RobotsPage.showNewBotModal()">
                    <i class="bi bi-plus-lg me-1"></i> Create Your First Robot
                </button>
            </div>`;
        }

        const countEl = document.getElementById('robotCount');
        if (countEl) countEl.textContent = `${robots.length} robot${robots.length !== 1 ? 's' : ''}`;

        return `<div class="row g-3">${robots.map((r, i) => `
        <div class="col-lg-4 col-md-6">
            <div class="card h-100 border-secondary">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <h6 class="fw-semibold mb-0">${r.name}</h6>
                        <div class="form-check form-switch">
                            <input type="checkbox" class="form-check-input" ${r.active ? 'checked' : ''}
                                onchange="RobotsPage.toggleRobot(${i}, this.checked)">
                        </div>
                    </div>
                    <div class="d-flex gap-1 mb-2">
                        <span class="badge bg-primary bg-opacity-10 text-primary">${r.strategy || '-'}</span>
                        <span class="badge bg-success bg-opacity-10 text-success">${r.pair || 'All'}</span>
                        <span class="badge bg-warning bg-opacity-10 text-warning">${r.exchange || '-'}</span>
                    </div>
                    <div class="row g-2 mb-2">
                        <div class="col-6">
                            <small class="text-secondary d-block">Mode</small>
                            <small class="fw-semibold">${r.mode || 'Real-Time'}</small>
                        </div>
                        <div class="col-6">
                            <small class="text-secondary d-block">Capital</small>
                            <small class="fw-semibold">${r.capital || '1000'} USDT</small>
                        </div>
                    </div>
                    <small class="text-secondary">Created: ${Components.formatDate(r.createdAt)}</small>
                    <div class="d-flex gap-2 mt-2">
                        <button class="btn btn-outline-success btn-sm flex-grow-1" onclick="RobotsPage.launchRobot(${i})">
                            <i class="bi bi-play-fill me-1"></i> Launch
                        </button>
                        <button class="btn btn-outline-secondary btn-sm" onclick="RobotsPage.editRobot(${i})">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-outline-danger btn-sm" onclick="RobotsPage.deleteRobot(${i})">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>`).join('')}</div>`;
    },

    showNewBotModal() {
        const strategies = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
        const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
        const allStrats = [...strategies.map(s => s.name), ...Object.keys(imported)];

        const modal = document.createElement('div');
        modal.innerHTML = `
        <div class="modal fade" tabindex="-1" id="newBotModal">
            <div class="modal-dialog">
                <div class="modal-content bg-dark border-secondary">
                    <div class="modal-header border-secondary">
                        <h5 class="modal-title"><i class="bi bi-robot me-2"></i>New Robot</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <label class="form-label small text-secondary">Robot Name</label>
                            <input type="text" class="form-control" id="newBotName" placeholder="e.g. Agent Nomadia Spirit" value="Bot ${(JSON.parse(localStorage.getItem('bc_robots') || '[]')).length + 1}">
                        </div>
                        <div class="mb-3">
                            <label class="form-label small text-secondary">Strategy</label>
                            <select class="form-select" id="newBotStrategy">
                                <option value="">-- Select Strategy --</option>
                                ${allStrats.map(s => `<option value="${s}">${s}</option>`).join('')}
                            </select>
                        </div>
                        <div class="row g-3 mb-3">
                            <div class="col-6">
                                <label class="form-label small text-secondary">Exchange</label>
                                <select class="form-select" id="newBotExchange">
                                    <option value="binance">Binance</option>
                                    <option value="kraken">Kraken</option>
                                    <option value="bybit">Bybit</option>
                                    <option value="okx">OKX</option>
                                </select>
                            </div>
                            <div class="col-6">
                                <label class="form-label small text-secondary">Trading Pair</label>
                                <input type="text" class="form-control" id="newBotPair" placeholder="BTC/USDT" value="BTC/USDT">
                            </div>
                        </div>
                        <div class="row g-3 mb-3">
                            <div class="col-6">
                                <label class="form-label small text-secondary">Execution Mode</label>
                                <div class="btn-group w-100" id="newBotMode">
                                    <button class="btn btn-outline-success active" onclick="this.parentElement.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));this.classList.add('active')" data-mode="realtime">Real-Time</button>
                                    <button class="btn btn-outline-secondary" onclick="this.parentElement.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));this.classList.add('active')" data-mode="backtest">Backtest</button>
                                </div>
                            </div>
                            <div class="col-6">
                                <label class="form-label small text-secondary">Capital (USDT)</label>
                                <input type="number" class="form-control" id="newBotCapital" value="1000">
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer border-secondary">
                        <button class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button class="btn btn-success fw-semibold" onclick="RobotsPage.saveNewBot()">
                            <i class="bi bi-check-lg me-1"></i> Create Robot
                        </button>
                    </div>
                </div>
            </div>
        </div>`;
        document.body.appendChild(modal);
        this._newBotModal = new bootstrap.Modal(modal.querySelector('.modal'));
        this._newBotModalEl = modal;
        this._newBotModal.show();
        modal.querySelector('.modal').addEventListener('hidden.bs.modal', () => modal.remove());
    },

    saveNewBot() {
        const name = document.getElementById('newBotName')?.value.trim();
        const strategy = document.getElementById('newBotStrategy')?.value;
        const exchange = document.getElementById('newBotExchange')?.value;
        const pair = document.getElementById('newBotPair')?.value.trim();
        const capital = document.getElementById('newBotCapital')?.value;
        const modeBtn = document.querySelector('#newBotMode .btn.active');
        const mode = modeBtn?.dataset.mode || 'realtime';

        if (!name) { App.showToast('Please enter a robot name', 'warning'); return; }
        if (!strategy) { App.showToast('Please select a strategy', 'warning'); return; }

        const robots = JSON.parse(localStorage.getItem('bc_robots') || '[]');
        robots.push({
            name, strategy, exchange, pair, capital, mode,
            active: false,
            createdAt: new Date().toISOString()
        });
        localStorage.setItem('bc_robots', JSON.stringify(robots));

        if (this._newBotModal) this._newBotModal.hide();
        this.refresh();
        App.showToast(`Robot "${name}" created`, 'success');
    },

    toggleRobot(index, active) {
        const robots = JSON.parse(localStorage.getItem('bc_robots') || '[]');
        if (robots[index]) {
            robots[index].active = active;
            localStorage.setItem('bc_robots', JSON.stringify(robots));
        }
    },

    launchRobot(index) {
        const robots = JSON.parse(localStorage.getItem('bc_robots') || '[]');
        const r = robots[index];
        if (!r) return;

        if (r.mode === 'backtest') {
            App.navigate('backtesting');
            setTimeout(() => {
                const select = document.getElementById('btStrategy');
                if (select) {
                    for (const opt of select.options) {
                        if (opt.value === r.strategy) { select.value = r.strategy; break; }
                    }
                }
            }, 500);
        } else {
            App.showToast(`To run "${r.name}" in real-time, configure Freqtrade with strategy "${r.strategy}"`, 'info');
        }
    },

    editRobot(index) {
        // For now just show the new bot modal pre-filled
        App.showToast('Edit coming soon - delete and recreate for now', 'info');
    },

    deleteRobot(index) {
        if (!confirm('Delete this robot configuration?')) return;
        const robots = JSON.parse(localStorage.getItem('bc_robots') || '[]');
        robots.splice(index, 1);
        localStorage.setItem('bc_robots', JSON.stringify(robots));
        this.refresh();
        App.showToast('Robot deleted', 'info');
    },

    refresh() {
        const container = document.getElementById('pageContainer');
        if (container) container.innerHTML = this.render();
        this.loadActiveBotInfo();
    },

    destroy() {
        if (this.refreshTimer) { clearInterval(this.refreshTimer); this.refreshTimer = null; }
    }
};

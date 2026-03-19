/**
 * BotCrypto - Bots Page
 * Freqtrade-style bot management interface with strategy selection,
 * trading chart, bot controls, whitelist, balance, and trade management.
 */
const BotsPage = {
    chart: null,
    candleSeries: null,
    volumeSeries: null,
    equityChart: null,
    currentPair: 'BTC/USDT',
    currentTimeframe: '5m',
    refreshTimer: null,
    botConfig: null,

    /** Candle data cache: key = "pair|tf", value = { data, volumes, signals, timestamp } */
    _cache: {},
    _cacheTTL: {
        '1m': 60_000,      // 1 min candles: cache 1 min
        '3m': 90_000,
        '5m': 2 * 60_000,  // 5 min candles: cache 2 min
        '15m': 5 * 60_000,
        '30m': 10 * 60_000,
        '1h': 15 * 60_000,
        '4h': 30 * 60_000,
        '1d': 60 * 60_000,
    },
    /** How many candles to request per timeframe */
    _candleLimits: {
        '1m': 5000,   // ~3.5 days
        '3m': 4000,   // ~8 days
        '5m': 3000,   // ~10 days
        '15m': 2000,  // ~21 days
        '30m': 2000,  // ~42 days
        '1h': 2000,   // ~83 days
        '4h': 1500,   // ~250 days
        '1d': 1000,   // ~2.7 years
    },

    /** Track signal entry/exit counts */
    _signalCounts: { enterLong: 0, exitLong: 0, enterShort: 0, exitShort: 0 },
    /** Heikin Ashi mode */
    _heikinAshi: false,
    /** Raw candle data before HA conversion */
    _rawCandles: null,

    render() {
        return `
        <div id="botsPage">
            ${API.isBacktestingMode ? `
            <div class="alert alert-info d-flex align-items-center mb-3">
                <i class="bi bi-info-circle me-2"></i>
                <span><strong>Backtesting Mode</strong> - Trade data and live balances are not available. Use the Backtesting page to run strategy tests.</span>
            </div>` : ''}

            <!-- Strategy Selector Bar -->
            <div class="card mb-2">
                <div class="card-body py-2 d-flex align-items-center gap-3 flex-wrap">
                    <span class="text-secondary small fw-semibold"><i class="bi bi-robot me-1"></i>Strategy:</span>
                    <select class="form-select form-select-sm" id="botsStrategySelect" style="width:auto;min-width:200px;background:rgba(255,255,255,0.08);border-color:var(--bc-border)" onchange="BotsPage.onStrategyChange(this.value)">
                        <option value="">Loading strategies...</option>
                    </select>
                    <span class="text-secondary small" id="botsStrategyInfo"></span>
                </div>
            </div>

            <!-- Multi Pane Layout: Left Panel + Chart Area -->
            <div class="row g-0" style="min-height:calc(100vh - 160px)">

                <!-- LEFT PANEL: Tabbed sidebar -->
                <div class="col-12 col-lg-3 col-xl-3" id="dashLeftPanel">
                    <div class="card h-100" style="border-radius:0;border-right:1px solid var(--bc-border)">
                        <!-- Bot Controls -->
                        <div class="card-header py-2 text-center border-bottom" style="background:var(--bc-bg-dark)">
                            <div class="d-flex align-items-center justify-content-center gap-1">
                                <button class="btn btn-sm btn-outline-success px-2" onclick="BotsPage.botAction('start')" title="Start Bot"><i class="bi bi-play-fill"></i></button>
                                <button class="btn btn-sm btn-outline-secondary px-2" onclick="BotsPage.botAction('stop')" title="Stop Bot"><i class="bi bi-stop-fill"></i></button>
                                <button class="btn btn-sm btn-outline-warning px-2" onclick="BotsPage.botAction('pause')" title="Pause (Stop Entry)"><i class="bi bi-pause-fill"></i></button>
                                <button class="btn btn-sm btn-outline-info px-2" onclick="BotsPage.botAction('reload')" title="Reload Config"><i class="bi bi-arrow-clockwise"></i></button>
                                <button class="btn btn-sm btn-outline-danger px-2" onclick="BotsPage.botAction('forceclose')" title="Force Close All"><i class="bi bi-x-square"></i></button>
                            </div>
                        </div>

                        <!-- Tab Navigation -->
                        <div class="d-flex justify-content-center border-bottom" style="background:var(--bc-bg-dark)">
                            <button class="btn btn-sm btn-link dash-tab-btn active" data-tab="whitelist" onclick="BotsPage.switchTab('whitelist')" title="Whitelist"><i class="bi bi-list-ul"></i></button>
                            <button class="btn btn-sm btn-link dash-tab-btn" data-tab="botinfo" onclick="BotsPage.switchTab('botinfo')" title="Bot Info"><i class="bi bi-info-circle"></i></button>
                            <button class="btn btn-sm btn-link dash-tab-btn" data-tab="performance" onclick="BotsPage.switchTab('performance')" title="Period Breakdown"><i class="bi bi-graph-up"></i></button>
                            <button class="btn btn-sm btn-link dash-tab-btn" data-tab="balance" onclick="BotsPage.switchTab('balance')" title="Bot Balance"><i class="bi bi-wallet2"></i></button>
                            <button class="btn btn-sm btn-link dash-tab-btn" data-tab="tradelist" onclick="BotsPage.switchTab('tradelist')" title="Trade List"><i class="bi bi-card-list"></i></button>
                        </div>

                        <!-- Tab Content -->
                        <div class="card-body p-0" style="overflow-y:auto;max-height:calc(100vh - 250px)">
                            <!-- Whitelist Tab -->
                            <div class="dash-tab-content active" id="dashTabWhitelist">
                                <h6 class="fw-semibold text-center py-2 mb-0 border-bottom" style="font-size:14px">Whitelist Methods</h6>
                                <div class="text-center py-1 px-2" id="dashWhitelistMethod">
                                    <span class="badge bg-secondary bg-opacity-25 px-3 py-1">StaticPairList</span>
                                </div>
                                <h6 class="fw-semibold text-center py-2 mb-0 border-bottom" style="font-size:14px">Whitelist</h6>
                                <div class="px-2 py-2" id="dashWhitelistPairs">
                                    <div class="text-center text-secondary py-3 small">Loading...</div>
                                </div>
                                <h6 class="fw-semibold text-center py-2 mb-0 border-bottom" style="font-size:14px">Blacklist
                                    <button class="btn btn-sm btn-link text-secondary float-end py-0" onclick="BotsPage.showBlacklistModal()"><i class="bi bi-plus-square"></i></button>
                                </h6>
                                <div class="px-2 py-2" id="dashBlacklistPairs">
                                    <div class="text-center text-secondary py-2 small">No blacklist entries</div>
                                </div>
                            </div>

                            <!-- Bot Info Tab -->
                            <div class="dash-tab-content" id="dashTabBotinfo" style="display:none">
                                <div class="px-3 py-2" id="dashBotInfoContent">
                                    <div class="text-center text-secondary py-4 small">Loading bot info...</div>
                                </div>
                            </div>

                            <!-- Period Breakdown Tab -->
                            <div class="dash-tab-content" id="dashTabPerformance" style="display:none">
                                <h6 class="fw-semibold text-center py-2 mb-0 border-bottom" style="font-size:14px">Period Breakdown
                                    <button class="btn btn-sm btn-link text-secondary float-end py-0" onclick="BotsPage.loadPeriodData()"><i class="bi bi-arrow-clockwise"></i></button>
                                </h6>
                                <div class="d-flex justify-content-center gap-1 py-2 border-bottom">
                                    <button class="btn btn-sm btn-outline-secondary active period-btn" onclick="BotsPage.setPeriodView('daily')">Days</button>
                                    <button class="btn btn-sm btn-outline-secondary period-btn" onclick="BotsPage.setPeriodView('weekly')">Weeks</button>
                                    <button class="btn btn-sm btn-outline-secondary period-btn" onclick="BotsPage.setPeriodView('monthly')">Months</button>
                                </div>
                                <div id="dashPeriodChart" style="height:150px" class="px-1"></div>
                                <div class="table-responsive" id="dashPeriodTable" style="max-height:400px;overflow-y:auto">
                                    <div class="text-center text-secondary py-3 small">Loading...</div>
                                </div>
                            </div>

                            <!-- Balance Tab -->
                            <div class="dash-tab-content" id="dashTabBalance" style="display:none">
                                <h6 class="fw-semibold text-center py-2 mb-0 border-bottom" style="font-size:14px">Bot Balance
                                    <button class="btn btn-sm btn-link text-secondary float-end py-0" onclick="BotsPage.loadBalanceData()"><i class="bi bi-arrow-clockwise"></i></button>
                                </h6>
                                <div id="dashBalanceChart" style="height:200px" class="px-2 py-2"></div>
                                <div class="table-responsive" id="dashBalanceTable">
                                    <div class="text-center text-secondary py-3 small">Loading balance...</div>
                                </div>
                            </div>

                            <!-- Trade List Tab -->
                            <div class="dash-tab-content" id="dashTabTradelist" style="display:none">
                                <div class="px-2 py-2">
                                    <input type="text" class="form-control form-control-sm mb-2" placeholder="Filter" id="dashTradeFilter"
                                        oninput="BotsPage.filterTradeList(this.value)"
                                        style="background:var(--bc-bg);border-color:var(--bc-border);color:var(--bc-text)">
                                </div>
                                <div id="dashTradeListContent" style="max-height:calc(100vh - 340px);overflow-y:auto">
                                    <div class="text-center text-secondary py-3 small">Loading trades...</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- RIGHT PANEL: Chart + Open Trades -->
                <div class="col-12 col-lg-9 col-xl-9">
                    <!-- Chart Header -->
                    <div class="card" style="border-radius:0">
                        <div class="card-header py-2" style="background:var(--bc-bg-dark)">
                            <div class="text-center fw-semibold" style="font-size:13px">Chart</div>
                        </div>
                        <div class="card-body pb-0 pt-2 px-2">
                            <!-- Chart Toolbar -->
                            <div class="d-flex align-items-center justify-content-between flex-wrap gap-1 mb-1">
                                <div class="d-flex align-items-center gap-2 flex-wrap">
                                    <small class="text-secondary" id="dashChartLabel"></small>
                                    <select class="form-select form-select-sm dash-pair-select" id="dashPairSelect"
                                        onchange="BotsPage.changePair(this.value)">
                                        <option value="">Loading...</option>
                                    </select>
                                    <button class="btn btn-sm btn-link text-secondary py-0" onclick="BotsPage.refreshChart()"><i class="bi bi-arrow-clockwise"></i></button>
                                </div>
                                <div class="d-flex align-items-center gap-2 flex-wrap">
                                    <small class="text-secondary" id="dashSignalCounts">Long entries: 0  Long exit: 0<br>Short entries: 0</small>
                                </div>
                                <div class="d-flex align-items-center gap-2">
                                    <label class="form-check form-check-inline mb-0" style="font-size:12px">
                                        <input class="form-check-input" type="checkbox" id="dashHeikinAshi" onchange="BotsPage.toggleHeikinAshi(this.checked)">
                                        <span class="text-secondary">Heikin Ashi</span>
                                    </label>
                                    <span id="dashTfBtns">${Components.timeframeSelector(this.currentTimeframe || '5m', 'BotsPage.changeTimeframe')}</span>
                                    <button class="btn btn-sm btn-outline-secondary py-0 px-1" onclick="BotsPage.showIndicatorsModal()" style="font-size:12px"><i class="bi bi-activity me-1"></i>Indicators</button>
                                </div>
                            </div>
                            <!-- Chart Legend -->
                            <div class="d-flex align-items-center gap-3 mb-1 px-1" style="font-size:11px">
                                <span><span style="display:inline-block;width:10px;height:10px;background:#2dd4a8;border-radius:2px;margin-right:3px"></span>Candles</span>
                                <span><span style="display:inline-block;width:10px;height:10px;background:rgba(74,144,217,0.5);border-radius:2px;margin-right:3px"></span>Volume</span>
                                <span><span style="display:inline-block;width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-bottom:8px solid #2dd4a8;margin-right:3px"></span>Entry</span>
                                <span><span style="display:inline-block;width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:8px solid #f5a623;margin-right:3px"></span>Exit</span>
                                <span><span style="display:inline-block;width:8px;height:8px;background:#4a90d9;border-radius:50%;margin-right:3px"></span>Trades</span>
                            </div>
                            <!-- OHLCV Info bar -->
                            <div class="d-flex align-items-center gap-3 px-1 mb-1" style="font-size:11px" id="dashOhlcvBar">
                                <small class="text-secondary" id="dashChartInfo">
                                    <i class="bi bi-bar-chart"></i> Loading chart data...
                                </small>
                            </div>
                            <div id="mainChart" class="chart-container" style="height:420px"></div>
                        </div>
                    </div>

                    <!-- Open Trades Table -->
                    <div class="card" style="border-radius:0;border-top:1px solid var(--bc-border)">
                        <div class="card-header py-1 text-center" style="background:var(--bc-bg-dark)">
                            <span class="fw-semibold" style="font-size:13px">Open Trades</span>
                            <span class="badge bg-success ms-1" id="dashOpenTradeCount" style="font-size:10px">0</span>
                        </div>
                        <div class="card-body p-0" style="max-height:350px;overflow-y:auto">
                            <table class="table table-hover table-sm mb-0" id="dashOpenTradesTable" style="font-size:12px">
                                <thead>
                                    <tr>
                                        <th>ID</th>
                                        <th>Pair</th>
                                        <th>Amount</th>
                                        <th>Stake amount</th>
                                        <th>Open rate</th>
                                        <th>Current rate</th>
                                        <th>Current profit %</th>
                                        <th>Open date</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody id="dashOpenTradesBody">
                                    <tr><td colspan="9" class="text-center text-secondary py-3">No open trades</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Closed Trades Table (below open trades) -->
                    <div class="card" style="border-radius:0;border-top:1px solid var(--bc-border)">
                        <div class="card-header py-1 text-center" style="background:var(--bc-bg-dark)">
                            <span class="fw-semibold" style="font-size:13px">Closed Trades</span>
                            <span class="badge bg-info ms-1" id="dashClosedTradeCount" style="font-size:10px">0</span>
                        </div>
                        <div class="card-body p-0" style="max-height:300px;overflow-y:auto">
                            <table class="table table-hover table-sm mb-0" id="dashClosedTradesTable" style="font-size:12px">
                                <thead>
                                    <tr>
                                        <th>ID</th>
                                        <th>Pair</th>
                                        <th>Profit</th>
                                        <th>Open rate</th>
                                        <th>Close rate</th>
                                        <th>Exit reason</th>
                                        <th>Duration</th>
                                        <th>Close date</th>
                                    </tr>
                                </thead>
                                <tbody id="dashClosedTradesBody">
                                    <tr><td colspan="8" class="text-center text-secondary py-3">No closed trades</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
    },

    _selectedStrategy: null,

    async init() {
        setTimeout(async () => {
            await this.loadBotConfig();
            await this._loadStrategies();
            this.initMainChart();
            await this.loadData();
            // Auto-refresh every 30 seconds
            this.refreshTimer = setInterval(() => this.loadData(), 30000);
        }, 100);
    },

    async _loadStrategies() {
        const select = document.getElementById('botsStrategySelect');
        if (!select) return;
        try {
            if (!API.connected) { select.innerHTML = '<option value="">Not connected</option>'; return; }
            const config = await API.getConfig();
            const currentStrat = config?.strategy || '';
            const data = await API.getStrategies();
            const strategies = data?.strategies || [];
            select.innerHTML = strategies.map(s =>
                `<option value="${s}" ${s === currentStrat ? 'selected' : ''}>${s}</option>`
            ).join('');
            if (currentStrat) {
                this._selectedStrategy = currentStrat;
                const info = document.getElementById('botsStrategyInfo');
                if (info) info.innerHTML = `<span class="badge bg-success bg-opacity-25 text-success">${config.state || 'running'}</span>`;
            }
        } catch (e) {
            select.innerHTML = '<option value="">Error loading strategies</option>';
        }
    },

    onStrategyChange(strategyName) {
        this._selectedStrategy = strategyName;
        const info = document.getElementById('botsStrategyInfo');
        if (info) info.textContent = `Selected: ${strategyName}`;
        // Reload chart data for this strategy's pair configuration
        this.loadData();
    },

    // ========== TAB NAVIGATION ==========
    switchTab(tabName) {
        document.querySelectorAll('.dash-tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.dash-tab-content').forEach(c => c.style.display = 'none');
        const btn = document.querySelector(`.dash-tab-btn[data-tab="${tabName}"]`);
        if (btn) btn.classList.add('active');
        const tabMap = {
            whitelist: 'dashTabWhitelist', botinfo: 'dashTabBotinfo',
            performance: 'dashTabPerformance', balance: 'dashTabBalance',
            tradelist: 'dashTabTradelist'
        };
        const tabEl = document.getElementById(tabMap[tabName]);
        if (tabEl) tabEl.style.display = '';
        // Lazy-load tab data
        if (tabName === 'performance') this.loadPeriodData();
        if (tabName === 'balance') this.loadBalanceData();
        if (tabName === 'tradelist') this.loadTradeList();
    },

    // ========== BOT CONTROL ==========
    async botAction(action) {
        if (!API.connected) { App.showToast('Not connected', 'warning'); return; }
        try {
            if (action === 'start') { await API.startBot(); App.showToast('Bot started', 'success'); }
            else if (action === 'stop') {
                if (!confirm('Stop the trading bot?')) return;
                await API.stopBot(); App.showToast('Bot stopped', 'info');
            }
            else if (action === 'pause') { await API.pauseBot(); App.showToast('New entries paused', 'info'); }
            else if (action === 'reload') { await API.reloadConfig(); App.showToast('Config reloaded', 'success'); }
            else if (action === 'forceclose') {
                if (!confirm('Force close ALL open trades?')) return;
                const trades = await API.getOpenTrades().catch(() => []);
                for (const t of trades) { await API.forceExit(t.trade_id).catch(() => {}); }
                App.showToast(`Force closed ${trades.length} trades`, 'warning');
            }
            setTimeout(() => this.loadData(), 1000);
        } catch(e) { App.showToast('Action failed: ' + e.message, 'error'); }
    },

    // ========== PERIOD BREAKDOWN ==========
    _periodView: 'daily',
    _periodChart: null,
    _periodSeries: null,

    async setPeriodView(view) {
        this._periodView = view;
        document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
        const btn = event?.target; if (btn) btn.classList.add('active');
        this.loadPeriodData();
    },

    async loadPeriodData() {
        if (!API.connected) return;
        try {
            let data;
            if (this._periodView === 'daily') data = await API.getDaily(30);
            else if (this._periodView === 'weekly') data = await API.getWeekly(12);
            else data = await API.getMonthly(6);

            const rows = data?.data || [];
            // Init period chart
            const chartEl = document.getElementById('dashPeriodChart');
            if (chartEl && rows.length > 0) {
                chartEl.innerHTML = '';
                if (this._periodChart) { try { this._periodChart.remove(); } catch(e){} }
                this._periodChart = Components.createChart(chartEl, {
                    rightPriceScale: { visible: true },
                    timeScale: { visible: true },
                    crosshair: { mode: 1 },
                });
                if (this._periodChart) {
                    const profitSeries = this._periodChart.addHistogramSeries({
                        priceLineVisible: false, lastValueVisible: false,
                    });
                    profitSeries.setData(rows.map(r => {
                        const dateStr = r.date || '';
                        const time = dateStr.substring(0, 10);
                        const val = r.abs_profit || 0;
                        return { time, value: val, color: val >= 0 ? 'rgba(45,212,168,0.7)' : 'rgba(231,76,94,0.7)' };
                    }).filter(d => d.time));
                    this._periodChart.timeScale().fitContent();
                }
            }

            // Period table
            const tableEl = document.getElementById('dashPeriodTable');
            if (tableEl && rows.length > 0) {
                const header = this._periodView === 'daily' ? 'Day' : (this._periodView === 'weekly' ? 'Week' : 'Month');
                tableEl.innerHTML = `<table class="table table-sm mb-0" style="font-size:11px">
                    <thead><tr><th>${header}</th><th>Profit</th><th>In USD</th><th>Trades</th><th>Profit%</th></tr></thead>
                    <tbody>${rows.map(r => {
                        const profit = r.abs_profit || 0;
                        const fiat = r.fiat_value || profit;
                        const cls = profit >= 0 ? 'text-profit' : 'text-loss';
                        return `<tr><td>${r.date || ''}</td><td class="${cls}">${Components.formatNumber(profit, 3)}</td>
                            <td class="${cls}">${Components.formatNumber(fiat, 2)}</td><td>${r.trade_count || 0}</td>
                            <td class="${cls}">${Components.formatNumber((r.rel_profit || 0) * 100, 2)}%</td></tr>`;
                    }).join('')}</tbody></table>`;
            }
        } catch(e) {
            const tableEl = document.getElementById('dashPeriodTable');
            if (tableEl) tableEl.innerHTML = `<div class="text-center text-secondary py-3 small">Not available</div>`;
        }
    },

    // ========== BALANCE TAB ==========
    _balanceChart: null,

    async loadBalanceData() {
        if (!API.connected) return;
        try {
            const balance = await API.getBalance();
            if (!balance || !balance.currencies) {
                document.getElementById('dashBalanceTable').innerHTML = '<div class="text-center text-secondary py-3 small">No balance data</div>';
                return;
            }
            const currencies = balance.currencies.filter(c => (c.balance || 0) > 0.001);
            const stakeCurrency = balance.stake || balance.symbol || 'USDT';

            // Donut chart using canvas
            const chartEl = document.getElementById('dashBalanceChart');
            if (chartEl && currencies.length > 0) {
                const total = currencies.reduce((s, c) => s + (c.est_stake || c.balance || 0), 0);
                const colors = ['#2dd4a8','#4a90d9','#f5a623','#e74c5e','#9b59b6','#00cec9','#fd79a8','#6c5ce7','#00b894','#f1c40f','#e67e22','#636e72'];
                chartEl.innerHTML = `<canvas id="balanceDonut" width="200" height="200" style="max-width:100%;margin:0 auto;display:block"></canvas>`;
                const canvas = document.getElementById('balanceDonut');
                if (canvas) {
                    const ctx = canvas.getContext('2d');
                    const cx = 100, cy = 100, r = 70, ir = 40;
                    let startAngle = -Math.PI / 2;
                    currencies.forEach((c, i) => {
                        const val = c.est_stake || c.balance || 0;
                        const angle = (val / total) * 2 * Math.PI;
                        ctx.beginPath();
                        ctx.arc(cx, cy, r, startAngle, startAngle + angle);
                        ctx.arc(cx, cy, ir, startAngle + angle, startAngle, true);
                        ctx.closePath();
                        ctx.fillStyle = colors[i % colors.length];
                        ctx.fill();
                        // Label
                        const midAngle = startAngle + angle / 2;
                        const lx = cx + (r + 15) * Math.cos(midAngle);
                        const ly = cy + (r + 15) * Math.sin(midAngle);
                        ctx.fillStyle = '#8a8fa8';
                        ctx.font = '9px Inter, sans-serif';
                        ctx.textAlign = midAngle > Math.PI/2 && midAngle < 3*Math.PI/2 ? 'right' : 'left';
                        ctx.fillText(`${c.currency}`, lx, ly);
                        startAngle += angle;
                    });
                    // Center text
                    ctx.fillStyle = '#e8eaf0';
                    ctx.font = 'bold 12px Inter, sans-serif';
                    ctx.textAlign = 'center';
                    ctx.fillText(`${Components.formatNumber(total, 2)}`, cx, cy + 4);
                }
            }

            // Balance table
            const tableEl = document.getElementById('dashBalanceTable');
            if (tableEl) {
                tableEl.innerHTML = `<table class="table table-sm mb-0" style="font-size:11px">
                    <thead><tr><th>Currency</th><th>Available</th><th>in ${stakeCurrency}</th></tr></thead>
                    <tbody>${currencies.map(c => {
                        const bal = c.balance || 0;
                        const est = c.est_stake || bal;
                        return `<tr><td class="fw-semibold">${c.currency}</td><td>${Components.formatNumber(bal, 3)}</td><td>${Components.formatNumber(est, 3)}</td></tr>`;
                    }).join('')}
                    <tr class="fw-bold border-top"><td>Total</td><td>${Components.formatNumber(balance.total || 0, 3)}%</td><td>${Components.formatNumber(balance.value || balance.total || 0, 3)}</td></tr>
                    </tbody></table>`;
            }
        } catch(e) {
            document.getElementById('dashBalanceTable').innerHTML = '<div class="text-center text-secondary py-3 small">Balance not available</div>';
        }
    },

    // ========== TRADE LIST TAB ==========
    _allTrades: [],

    async loadTradeList() {
        if (!API.connected) return;
        try {
            const openTrades = await API.getOpenTrades().catch(() => []);
            const tradeList = Array.isArray(openTrades) ? openTrades : [];
            this._allTrades = tradeList;
            this._renderTradeListContent(tradeList);
        } catch(e) {}
    },

    _renderTradeListContent(trades) {
        const el = document.getElementById('dashTradeListContent');
        if (!el) return;
        if (!trades || trades.length === 0) {
            el.innerHTML = '<div class="text-center text-secondary py-3 small">No open trades</div>';
            return;
        }
        el.innerHTML = trades.map(t => {
            const pair = Components.cleanPairName(t.pair || '');
            const profit = t.profit_abs || 0;
            const profitPct = t.profit_ratio ? (t.profit_ratio * 100) : (t.profit_pct || 0);
            const cls = profit >= 0 ? 'text-profit' : 'text-loss';
            const bgCls = profit >= 0 ? 'bg-profit' : 'bg-loss';
            const icon = profit >= 0 ? 'bi-triangle-fill' : 'bi-triangle-fill';
            const iconStyle = profit < 0 ? 'transform:rotate(180deg);display:inline-block;' : '';
            return `<div class="d-flex align-items-center justify-content-between px-3 py-2 border-bottom trade-list-item" data-pair="${(t.pair||'').toLowerCase()}"
                style="cursor:pointer;border-color:var(--bc-border) !important" onclick="BotsPage.changePair('${t.pair}')">
                <span class="fw-semibold" style="font-size:12px">${pair}</span>
                <span class="badge ${bgCls} ${cls} px-2" style="font-size:11px">
                    <i class="bi ${icon} me-1" style="font-size:7px;${iconStyle}"></i>${profitPct >= 0 ? '+' : ''}${Components.formatNumber(profitPct, 2)}% (${Components.formatNumber(profit, 3)})
                </span>
            </div>`;
        }).join('');
    },

    filterTradeList(query) {
        const q = query.toLowerCase().trim();
        document.querySelectorAll('#dashTradeListContent .trade-list-item').forEach(el => {
            el.style.display = !q || el.dataset.pair.includes(q) ? '' : 'none';
        });
    },

    // ========== HEIKIN ASHI ==========
    toggleHeikinAshi(enabled) {
        this._heikinAshi = enabled;
        const cached = this._getCached(this.currentPair, this.currentTimeframe);
        if (cached) {
            const candles = enabled ? this._toHeikinAshi(cached.candles) : cached.candles;
            const volumes = candles.map(c => ({
                time: c.time, value: c.volume || 0,
                color: c.close >= c.open ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
            }));
            this._applyChartData(candles, volumes, cached.signals);
        }
    },

    _toHeikinAshi(candles) {
        if (!candles || candles.length === 0) return [];
        const ha = [];
        for (let i = 0; i < candles.length; i++) {
            const c = candles[i];
            const prevHa = i > 0 ? ha[i-1] : c;
            const haClose = (c.open + c.high + c.low + c.close) / 4;
            const haOpen = (prevHa.open + prevHa.close) / 2;
            ha.push({
                time: c.time,
                open: haOpen,
                high: Math.max(c.high, haOpen, haClose),
                low: Math.min(c.low, haOpen, haClose),
                close: haClose,
                volume: c.volume
            });
        }
        return ha;
    },

    // ========== BLACKLIST MODAL ==========
    async showBlacklistModal() {
        try {
            const data = await API.getBlacklist().catch(() => null);
            const blacklist = data?.blacklist || [];
            const html = `<div class="modal fade" id="blacklistModal" tabindex="-1">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content" style="background:var(--bc-card);border-color:var(--bc-border)">
                        <div class="modal-header border-secondary">
                            <h5 class="modal-title">Blacklist</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <input type="text" class="form-control form-control-sm" id="blacklistAddInput" placeholder="Add pair (e.g. BTC/USDT)">
                            </div>
                            <button class="btn btn-sm btn-outline-danger mb-3" onclick="BotsPage.addToBlacklist()">Add to Blacklist</button>
                            <div class="list-group list-group-flush">
                                ${blacklist.map(p => `<div class="list-group-item d-flex justify-content-between" style="background:transparent;border-color:var(--bc-border)">
                                    <span>${p}</span>
                                </div>`).join('')}
                                ${blacklist.length === 0 ? '<div class="text-center text-secondary py-2 small">No blacklisted pairs</div>' : ''}
                            </div>
                        </div>
                    </div>
                </div>
            </div>`;
            let existing = document.getElementById('blacklistModal');
            if (existing) existing.remove();
            document.body.insertAdjacentHTML('beforeend', html);
            new bootstrap.Modal(document.getElementById('blacklistModal')).show();
        } catch(e) { App.showToast('Failed to load blacklist', 'error'); }
    },

    async addToBlacklist() {
        const input = document.getElementById('blacklistAddInput');
        if (!input || !input.value.trim()) return;
        try {
            await API.addBlacklist([input.value.trim()]);
            App.showToast(`${input.value.trim()} blacklisted`, 'success');
            const modal = bootstrap.Modal.getInstance(document.getElementById('blacklistModal'));
            if (modal) modal.hide();
            this.loadData();
        } catch(e) { App.showToast('Failed: ' + e.message, 'error'); }
    },

    async loadBotConfig() {
        const select = document.getElementById('dashPairSelect');

        try {
            if (API.connected) {
                const [config, whitelistData, openTrades] = await Promise.all([
                    API.getConfig().catch(() => null),
                    API.getWhitelist().catch(() => null),
                    API.getOpenTrades().catch(() => []),
                ]);

                this.botConfig = config;

                // Get the strategy's timeframe from config
                if (config && config.timeframe) {
                    this.currentTimeframe = config.timeframe;
                    const tfBtns = document.getElementById('dashTfBtns');
                    if (tfBtns) tfBtns.innerHTML = Components.timeframeSelector(this.currentTimeframe, 'BotsPage.changeTimeframe');
                }

                // Build pair list from: whitelist API > config whitelist > open trades > available_pairs
                let pairs = [];
                if (whitelistData && whitelistData.whitelist && whitelistData.whitelist.length > 0) {
                    pairs = whitelistData.whitelist;
                }
                if (pairs.length === 0 && config && config.exchange?.pair_whitelist?.length > 0) {
                    pairs = config.exchange.pair_whitelist;
                }
                if (Array.isArray(openTrades) && openTrades.length > 0) {
                    const tradePairs = openTrades.map(t => t.pair).filter(Boolean);
                    tradePairs.forEach(p => {
                        if (!pairs.includes(p)) pairs.push(p);
                    });
                }

                // Fallback: try available_pairs endpoint (works in backtesting mode)
                if (pairs.length === 0) {
                    try {
                        const tf = this.currentTimeframe || '5m';
                        const avail = await API.getAvailablePairs(tf);
                        if (avail && avail.pairs && avail.pairs.length > 0) {
                            pairs = avail.pairs.slice(0, 50); // Limit to 50 pairs
                        }
                    } catch (e) {
                        console.log('available_pairs fallback failed:', e.message);
                    }
                }

                if (pairs.length > 0) {
                    if (!this.currentPair || !pairs.includes(this.currentPair)) {
                        this.currentPair = pairs[0];
                    }
                    if (select) {
                        select.innerHTML = pairs.map(p =>
                            `<option value="${p}" ${p === this.currentPair ? 'selected' : ''}>${Components.cleanPairName(p)}</option>`
                        ).join('');
                    }
                }
            }
        } catch (e) {
            console.log('Could not load bot config:', e.message);
        }

        // Defaults if nothing loaded
        if (!this.currentPair) this.currentPair = 'BTC/USDT';
        if (!this.currentTimeframe) this.currentTimeframe = '5m';

        if (select && select.options.length <= 1 && select.options[0]?.value === '') {
            select.innerHTML = `<option value="${this.currentPair}">${this.currentPair}</option>`;
        }
    },

    changePair(pair) {
        this.currentPair = pair;
        // Clear chart immediately so old data doesn't linger
        this._applyChartData([], [], []);
        this.refreshChart();
    },

    changeTimeframe(tf) {
        this.currentTimeframe = tf;
        const tfBtns = document.getElementById('dashTfBtns');
        if (tfBtns) tfBtns.innerHTML = Components.timeframeSelector(tf, 'BotsPage.changeTimeframe');
        // Clear cache for this pair+tf to force fresh fetch
        const key = this._cacheKey(this.currentPair, tf);
        delete this._cache[key];
        // Clear chart immediately so old data doesn't linger
        this._applyChartData([], [], []);
        this.refreshChart();
    },

    async refreshChart() {
        const info = document.getElementById('dashChartInfo');
        if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${this.currentPair}, ${this.currentTimeframe}`;
        await this.loadChartData();
    },

    initMainChart() {
        const container = document.getElementById('mainChart');
        if (!container) return;
        container.innerHTML = '';

        this.chart = Components.createChart(container);
        if (!this.chart) return;

        this.candleSeries = this.chart.addCandlestickSeries({
            upColor: '#2dd4a8',
            downColor: '#e74c5e',
            borderUpColor: '#2dd4a8',
            borderDownColor: '#e74c5e',
            wickUpColor: '#2dd4a8',
            wickDownColor: '#e74c5e',
        });

        this.volumeSeries = this.chart.addHistogramSeries({
            color: '#4a90d9',
            priceFormat: { type: 'volume' },
            priceScaleId: '',
        });

        this.chart.priceScale('').applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        });

        this.loadChartData();
    },

    /** Get cache key for pair + timeframe */
    _cacheKey(pair, tf) { return `${pair}|${tf}`; },

    /** Check if cached data is still fresh */
    _getCached(pair, tf) {
        const key = this._cacheKey(pair, tf);
        const entry = this._cache[key];
        if (!entry) return null;
        const ttl = this._cacheTTL[tf] || 60_000;
        if (Date.now() - entry.timestamp > ttl) return null;
        return entry;
    },

    /** Store parsed candle data in cache */
    _setCache(pair, tf, candles, volumes, signals) {
        const key = this._cacheKey(pair, tf);
        this._cache[key] = { candles, volumes, signals, timestamp: Date.now() };
        // Limit cache size: keep max 20 entries
        const keys = Object.keys(this._cache);
        if (keys.length > 20) {
            const oldest = keys.sort((a, b) => this._cache[a].timestamp - this._cache[b].timestamp);
            delete this._cache[oldest[0]];
        }
    },

    /** Apply candle + volume + marker data to chart */
    _applyChartData(candles, volumes, signals) {
        if (!this.candleSeries) return;
        if (!candles || candles.length === 0) {
            this.candleSeries.setData([]);
            if (this.volumeSeries) this.volumeSeries.setData([]);
            this.candleSeries.setMarkers([]);
            return;
        }
        // Apply Heikin Ashi if enabled
        const displayCandles = this._heikinAshi ? this._toHeikinAshi(candles) : candles;
        this.candleSeries.setData(displayCandles);
        if (this.volumeSeries && volumes) this.volumeSeries.setData(volumes);

        // Count signals and create markers
        const counts = { enterLong: 0, exitLong: 0, enterShort: 0, exitShort: 0 };
        if (signals && signals.length > 0) {
            const markers = signals.map(s => {
                const isBuy = s.type === 'enter_long' || s.type === 'exit_short';
                if (s.type === 'enter_long') counts.enterLong++;
                else if (s.type === 'exit_long') counts.exitLong++;
                else if (s.type === 'enter_short') counts.enterShort++;
                else if (s.type === 'exit_short') counts.exitShort++;
                return {
                    time: s.time,
                    position: isBuy ? 'belowBar' : 'aboveBar',
                    color: isBuy ? '#2dd4a8' : '#f5a623',
                    shape: isBuy ? 'arrowUp' : 'arrowDown',
                    text: isBuy ? 'B' : 'S',
                    size: 1,
                };
            }).sort((a, b) => a.time - b.time);
            this.candleSeries.setMarkers(markers);
        }
        this._signalCounts = counts;
        this._updateSignalCounts();
    },

    _updateSignalCounts() {
        const el = document.getElementById('dashSignalCounts');
        if (!el) return;
        const c = this._signalCounts;
        el.innerHTML = `Long entries: ${c.enterLong}  Long exit: ${c.exitLong}<br>Short entries: ${c.enterShort}`;
    },

    // Cached strategy name to avoid repeated getConfig calls
    _strategyName: '',

    async loadChartData() {
        if (!this.candleSeries) return;

        const info = document.getElementById('dashChartInfo');
        const pair = this.currentPair;
        const tf = this.currentTimeframe;
        let loaded = false;

        // 1) Show cached data instantly if available
        const cached = this._getCached(pair, tf);
        if (cached) {
            this._applyChartData(cached.candles, cached.volumes, cached.signals);
            if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair}, ${tf} (${cached.candles.length} candles, cached)`;
            this.chart.timeScale().scrollToRealTime();
            loaded = true;

            // Add open trade markers on top of cached data
            this._addTradeMarkers(pair);
            return;
        }

        try {
            if (API.connected && pair) {
                if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair}, ${tf} - <span class="spinner-border spinner-border-sm me-1"></span>Loading...`;

                const limit = this._candleLimits[tf] || 2000;
                let candles = null;
                let signals = [];

                // Try 1: pair_candles (fast - strategy-analyzed data for whitelisted pairs)
                try {
                    const data = await API.getPairCandles(pair, tf, limit);
                    if (data && data.columns && data.data && data.data.length > 0) {
                        candles = API.parseCandleData(data);
                        signals = API.parseSignals(data);
                    }
                } catch (e) {
                    console.log('pair_candles failed:', e.message);
                }

                // Try 2: pair_history fallback (slower - fetches & analyzes data for any pair)
                if (!candles || candles.length === 0) {
                    try {
                        if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair}, ${tf} - <span class="spinner-border spinner-border-sm me-1"></span>Fetching data...`;

                        // Use shorter timerange to keep it fast
                        const now = new Date();
                        const daysBack = { '1m': 1, '3m': 2, '5m': 3, '15m': 7, '30m': 14, '1h': 30, '4h': 60, '1d': 180 };
                        const days = daysBack[tf] || 3;
                        const start = new Date(now.getTime() - days * 86400000);
                        const timerange = `${start.toISOString().slice(0,10).replace(/-/g,'')}-${now.toISOString().slice(0,10).replace(/-/g,'')}`;

                        // Cache strategy name to avoid repeated config calls
                        if (!this._strategyName) {
                            try {
                                const config = await API.getConfig();
                                this._strategyName = config.strategy || '';
                            } catch(e) {}
                        }

                        if (this._strategyName) {
                            const data = await API.getPairHistory(pair, tf, timerange, this._strategyName);
                            if (data && data.columns && data.data && data.data.length > 0) {
                                candles = API.parseCandleData(data);
                                signals = API.parseSignals(data);
                            }
                        }
                    } catch (e) {
                        console.log('pair_history fallback failed:', e.message);
                    }
                }

                // Try 3: pair_ohlcv — raw exchange data, no strategy needed (engine mode)
                if (!candles || candles.length === 0) {
                    try {
                        if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair}, ${tf} - <span class="spinner-border spinner-border-sm me-1"></span>Loading from exchange...`;
                        const data = await API.getPairOhlcv(pair, tf, limit);
                        if (data && data.columns && data.data && data.data.length > 0) {
                            candles = API.parseCandleData(data);
                        }
                    } catch (e) {
                        console.log('pair_ohlcv fallback failed:', e.message);
                    }
                }

                if (candles && candles.length > 0) {
                    const volumes = candles.map(c => ({
                        time: c.time,
                        value: c.volume || 0,
                        color: c.close >= c.open ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
                    }));

                    // Cache the data
                    this._setCache(pair, tf, candles, volumes, signals);

                    // Apply to chart
                    this._applyChartData(candles, volumes, signals);
                    loaded = true;

                    // Add open trade markers
                    this._addTradeMarkers(pair);

                    this.chart.timeScale().scrollToRealTime();
                    if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair}, ${tf} (${candles.length} candles)`;
                    return;
                }

                if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair}, ${tf} - No data available`;
            }
        } catch (e) {
            console.log('API chart data not available:', e.message);
        }

        // Fallback: demo data when disconnected, "no data" message when connected
        if (!loaded) {
            if (API.connected) {
                if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair}, ${tf} - No chart data available`;
            } else {
                if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair || 'BTC/USDT'}, ${tf || '5m'} (demo - not connected)`;
                const demoData = Components.generateDemoCandles(300, this.getDemoPrice());
                this.candleSeries.setData(demoData);

                const volumes = demoData.map(c => ({
                    time: c.time,
                    value: Math.random() * 2000000,
                    color: c.close >= c.open ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
                }));
                this.volumeSeries.setData(volumes);

                const markers = [];
                for (let i = 20; i < demoData.length; i += Math.floor(8 + Math.random() * 15)) {
                    markers.push({
                        time: demoData[i].time,
                        position: demoData[i].close < demoData[Math.max(0, i-1)].close ? 'belowBar' : 'aboveBar',
                        color: demoData[i].close > demoData[Math.max(0, i-5)].close ? '#e74c5e' : '#2dd4a8',
                        shape: 'circle',
                        text: demoData[i].close > demoData[Math.max(0, i-5)].close ? 'S' : 'B',
                    });
                }
                this.candleSeries.setMarkers(markers);
            }

            if (this.chart) this.chart.timeScale().fitContent();
        }
    },

    /** Add open trade buy markers to the chart */
    async _addTradeMarkers(pair) {
        try {
            const openTrades = await API.getOpenTrades();
            if (!Array.isArray(openTrades)) return;
            const tradeMarkers = [];
            for (const t of openTrades) {
                if (t.pair === pair && t.open_date) {
                    const ts = Math.floor(new Date(t.open_date).getTime() / 1000);
                    tradeMarkers.push({
                        time: ts,
                        position: 'belowBar',
                        color: '#2dd4a8',
                        shape: 'arrowUp',
                        text: `Buy ${Components.formatNumber(t.stake_amount, 2)}`,
                    });
                }
            }
            if (tradeMarkers.length > 0) {
                // Merge with existing signal markers
                const existing = [];
                const cached = this._getCached(pair, this.currentTimeframe);
                if (cached && cached.signals && cached.signals.length > 0) {
                    cached.signals.forEach(s => {
                        const isBuy = s.type === 'enter_long' || s.type === 'exit_short';
                        existing.push({
                            time: s.time,
                            position: isBuy ? 'belowBar' : 'aboveBar',
                            color: isBuy ? '#2dd4a8' : '#e74c5e',
                            shape: 'circle',
                            text: isBuy ? 'B' : 'S',
                        });
                    });
                }
                const all = [...existing, ...tradeMarkers].sort((a, b) => a.time - b.time);
                this.candleSeries.setMarkers(all);
            }
        } catch (e) { /* optional */ }
    },

    getDemoPrice() {
        const prices = { 'BTC/USDT': 85000, 'ETH/USDT': 2000, 'XRP/USDT': 0.55, 'SOL/USDT': 130, 'ADA/USDT': 0.45, 'DOGE/USDT': 0.12, 'OP/USDT': 0.14, 'GRT/USDT': 0.028 };
        return prices[this.currentPair] || 1.0;
    },

    // Equity chart removed - period breakdown in left panel replaces it

    async refreshAll() {
        await this.loadBotConfig();
        await this.loadData();
        await this.refreshChart();
        App.showToast('Dashboard refreshed', 'info');
    },

    async loadData() {
        const el = (id) => document.getElementById(id);
        try {
            if (!API.connected) {
                this.showDemoData();
                return;
            }

            // Always fetch config first (works in all modes)
            const config = await API.getConfig().catch(() => null);

            // Try trade endpoints - these fail in backtesting mode
            const [profit, trades, balance, openTrades, count, whitelist, blacklist] = await Promise.all([
                API.getProfit().catch(() => null),
                API.getTrades(50).catch(() => ({ trades: [] })),
                API.getBalance().catch(() => null),
                API.getOpenTrades().catch(() => []),
                API.getTradeCount().catch(() => null),
                API.getWhitelist().catch(() => null),
                API.getBlacklist().catch(() => null),
            ]);

            this.botConfig = config;

            // ---- Chart label (strategy, timeframe, exchange info) ----
            if (config && el('dashChartLabel')) {
                const tf = config.timeframe || this.currentTimeframe;
                const strategy = config.strategy || '';
                el('dashChartLabel').textContent = `${strategy} | ${tf}`;
            }

            // ---- WHITELIST TAB ----
            const whitelistPairs = whitelist?.whitelist || (config?.exchange?.pair_whitelist) || [];
            const wlMethod = config?.pairlist_config?.[0]?.method || whitelist?.method?.[0] || 'StaticPairList';
            if (el('dashWhitelistMethod')) {
                el('dashWhitelistMethod').innerHTML = `<span class="badge bg-secondary bg-opacity-25 px-3 py-1">${wlMethod}</span>`;
            }
            if (el('dashWhitelistPairs') && whitelistPairs.length > 0) {
                el('dashWhitelistPairs').innerHTML = `<div class="d-flex flex-wrap gap-1">
                    ${whitelistPairs.map(p => `<span class="badge bg-secondary bg-opacity-10 text-light border px-2 py-1" style="font-size:11px;cursor:pointer;border-color:var(--bc-border) !important"
                        onclick="BotsPage.changePair('${p}')">${Components.cleanPairName(p)}</span>`).join('')}
                </div>`;
            }
            // Blacklist
            const blacklistPairs = blacklist?.blacklist || [];
            if (el('dashBlacklistPairs')) {
                el('dashBlacklistPairs').innerHTML = blacklistPairs.length > 0
                    ? `<div class="d-flex flex-wrap gap-1">${blacklistPairs.map(p =>
                        `<span class="badge bg-danger bg-opacity-10 text-light border border-danger px-2 py-1" style="font-size:11px">${p}</span>`).join('')}</div>`
                    : '<div class="text-center text-secondary py-2 small">No blacklist entries</div>';
            }

            // ---- BOT INFO TAB ----
            const openTradesList = Array.isArray(openTrades) ? openTrades : [];
            if (config && el('dashBotInfoContent')) {
                const totalTrades = profit ? (profit.winning_trades || 0) + (profit.losing_trades || 0) : 0;
                const winRate = totalTrades > 0 ? (profit.winning_trades / totalTrades * 100) : 0;
                const currency = profit?.stake_currency || 'USDT';
                const profitAll = profit?.profit_all_coin || 0;
                const profitAllPct = profit?.profit_all_percent || (profit?.profit_all_ratio_sum || 0) * 100;
                const avgDuration = profit?.avg_duration || '-';
                const bestPair = profit?.best_pair || '-';
                const tradingVolume = profit?.trading_volume || 0;

                el('dashBotInfoContent').innerHTML = `
                    <div class="py-2">
                        <p class="mb-1 small text-center">Running Freqtrade <strong>${config.version || ''}</strong></p>
                        <p class="mb-1 small text-center">Running with <strong>${config.stake_amount || ''}${config.stake_amount === 'unlimited' ? '' : ' ' + currency}</strong> on <strong>${config.exchange}</strong> in <strong>${config.trading_mode || 'spot'}</strong> markets, with Strategy <strong>${config.strategy || ''}</strong>.</p>
                        <p class="mb-1 small text-center">Stoploss on exchange is <strong>${config.stoploss_on_exchange ? 'enabled' : 'disabled'}</strong>.</p>
                        <p class="mb-2 small text-center">Currently <strong>${config.state || 'running'}</strong>, force entry: <strong>${config.force_entry_enable || false}</strong></p>

                        <h6 class="text-center fw-bold border-top pt-2">${config.dry_run ? 'Dry Run' : 'Live'}</h6>
                        <p class="mb-3 small text-center">
                            Avg Profit ${Components.formatNumber(profitAllPct / Math.max(totalTrades, 1), 3)}% (Sum ${Components.formatNumber(profitAllPct, 3)}%) in ${totalTrades} Trades, with an average duration of ${avgDuration}. Best pair: ${bestPair}.
                        </p>

                        <p class="mb-1 small text-center">Bot start date: <strong>${config.bot_start_date || '-'}</strong></p>
                        <p class="mb-1 small text-center">First trade opened: <strong>${profit?.first_trade_date || '-'}</strong></p>
                        <p class="mb-2 small text-center">Last trade opened: <strong>${profit?.latest_trade_date || '-'}</strong></p>

                        <p class="mb-1 small text-center">Profit factor: <strong>${profit?.profit_factor ? Components.formatNumber(profit.profit_factor, 2) : '-'}</strong></p>
                        <p class="mb-3 small text-center">Trading volume: <strong>${Components.formatNumber(tradingVolume, 3)} ${currency}</strong></p>

                        <table class="table table-sm mb-0" style="font-size:11px">
                            <thead><tr><th>Metric</th><th>Value</th></tr></thead>
                            <tbody>
                                <tr><td>ROI closed trades</td><td>${Components.formatNumber(profit?.profit_closed_coin || 0, 3)} ${currency} (${Components.formatNumber(profit?.profit_closed_percent || 0, 2)}%)</td></tr>
                                <tr><td>ROI all trades</td><td>${Components.formatNumber(profitAll, 3)} ${currency} (${Components.formatNumber(profitAllPct, 2)}%)</td></tr>
                                <tr><td>Total Trade count</td><td>${totalTrades}</td></tr>
                                <tr><td>Bot started</td><td>${config.bot_start_date || '-'}</td></tr>
                                <tr><td>First Trade opened</td><td>${profit?.first_trade_date || '-'}</td></tr>
                                <tr><td>Latest Trade opened</td><td>${profit?.latest_trade_date || '-'}</td></tr>
                                <tr><td>Win / Loss</td><td>${profit?.winning_trades || 0} / ${profit?.losing_trades || 0}</td></tr>
                                <tr><td>Winrate</td><td>${Components.formatNumber(winRate, 3)}%</td></tr>
                                <tr><td>Expectancy (ratio)</td><td>${profit?.expectancy ? Components.formatNumber(profit.expectancy, 2) : '-'} (${profit?.expectancy_ratio ? Components.formatNumber(profit.expectancy_ratio, 2) : '-'})</td></tr>
                                <tr><td>Avg. Duration</td><td>${avgDuration}</td></tr>
                                <tr><td>Best performing</td><td>${bestPair}: ${Components.formatNumber(profit?.best_pair_profit_ratio ? profit.best_pair_profit_ratio * 100 : 0, 2)}%</td></tr>
                                <tr><td>Trading volume</td><td>${Components.formatNumber(tradingVolume, 3)} ${currency}</td></tr>
                            </tbody>
                        </table>
                    </div>`;
            }

            // ---- OPEN TRADES TABLE ----
            const openBody = el('dashOpenTradesBody');
            const openCountBadge = el('dashOpenTradeCount');
            if (openCountBadge) openCountBadge.textContent = openTradesList.length;
            if (openBody) {
                if (openTradesList.length > 0) {
                    openBody.innerHTML = openTradesList.map(t => {
                        const profit = t.profit_abs || 0;
                        const profitPct = t.profit_ratio ? (t.profit_ratio * 100) : (t.profit_pct || 0);
                        const cls = profit >= 0 ? 'text-profit' : 'text-loss';
                        const bgCls = profit >= 0 ? 'bg-profit' : 'bg-loss';
                        const icon = profit >= 0 ? 'bi-triangle-fill' : 'bi-triangle-fill';
                        const iconStyle = profit < 0 ? 'transform:rotate(180deg);display:inline-block;' : '';
                        const direction = t.is_short ? 'Short' : 'Long';
                        const leverage = t.leverage ? `(${t.leverage}x)` : '(1x)';
                        return `<tr>
                            <td>${t.trade_id} | ${direction}</td>
                            <td class="fw-semibold">${Components.cleanPairName(t.pair)}</td>
                            <td>${Components.formatNumber(t.amount, 2)}</td>
                            <td>${Components.formatNumber(t.stake_amount, 3)} ${leverage}</td>
                            <td>${Components.formatNumber(t.open_rate, 4)}</td>
                            <td>${Components.formatNumber(t.current_rate || t.close_rate || 0, 4)}</td>
                            <td><span class="${cls}"><i class="bi ${icon} me-1" style="font-size:7px;${iconStyle}"></i></span>
                                <span class="badge ${bgCls} ${cls} px-2">${Components.formatNumber(profitPct, 2)}% (${Components.formatNumber(profit, 3)})</span></td>
                            <td>${Components.formatDate(t.open_date)}</td>
                            <td>
                                <button class="btn btn-sm btn-link text-danger py-0 px-1" onclick="BotsPage.forceExitTrade(${t.trade_id})" title="Force Exit"><i class="bi bi-box-arrow-right"></i></button>
                            </td>
                        </tr>`;
                    }).join('');
                } else {
                    openBody.innerHTML = '<tr><td colspan="9" class="text-center text-secondary py-3">No open trades</td></tr>';
                }
            }

            // ---- CLOSED TRADES TABLE ----
            const closedTrades = (trades && trades.trades) ? trades.trades.filter(t => !t.is_open) : [];
            const closedBody = el('dashClosedTradesBody');
            const closedCountBadge = el('dashClosedTradeCount');
            if (closedCountBadge) closedCountBadge.textContent = closedTrades.length;
            if (closedBody) {
                if (closedTrades.length > 0) {
                    closedBody.innerHTML = closedTrades.slice(0, 50).map(t => {
                        const profit = t.profit_abs || 0;
                        const profitPct = t.profit_ratio ? (t.profit_ratio * 100) : (t.profit_pct || 0);
                        const cls = profit >= 0 ? 'text-profit' : 'text-loss';
                        const duration = t.trade_duration ? `${Math.round(t.trade_duration)} min` : (t.close_date && t.open_date ? Components.formatDuration(t.trade_duration) : '-');
                        return `<tr>
                            <td>${t.trade_id} | ${t.is_short ? 'Short' : 'Long'}</td>
                            <td class="fw-semibold">${Components.cleanPairName(t.pair)}</td>
                            <td class="${cls}">${profit >= 0 ? '+' : ''}${Components.formatNumber(profit, 3)} (${Components.formatNumber(profitPct, 2)}%)</td>
                            <td>${Components.formatNumber(t.open_rate, 4)}</td>
                            <td>${Components.formatNumber(t.close_rate, 4)}</td>
                            <td>${t.exit_reason || t.sell_reason || '-'}</td>
                            <td>${duration}</td>
                            <td>${Components.formatDate(t.close_date)}</td>
                        </tr>`;
                    }).join('');
                } else {
                    closedBody.innerHTML = '<tr><td colspan="8" class="text-center text-secondary py-3">No closed trades</td></tr>';
                }
            }

            // Update trade list tab data silently
            this._allTrades = openTradesList;

        } catch (e) {
            console.error('Dashboard load error:', e);
            this.showDemoData();
        }
    },

    async forceExitTrade(tradeId) {
        if (!confirm(`Force exit trade #${tradeId}?`)) return;
        try {
            await API.forceExit(tradeId);
            App.showToast(`Trade #${tradeId} force closed`, 'success');
            setTimeout(() => this.loadData(), 1000);
        } catch(e) { App.showToast('Force exit failed: ' + e.message, 'error'); }
    },

    showDemoData() {
        const openBody = document.getElementById('dashOpenTradesBody');
        if (openBody) openBody.innerHTML = '<tr><td colspan="9" class="text-center text-secondary py-3">No open trades</td></tr>';
        const closedBody = document.getElementById('dashClosedTradesBody');
        if (closedBody) closedBody.innerHTML = '<tr><td colspan="8" class="text-center text-secondary py-3">No closed trades</td></tr>';
    },

    // ========== INDICATORS ==========
    _indicators: {},       // { ema20: { enabled, series }, ... }
    _indicatorDefs: [
        // ===== MOVING AVERAGES (Overlays) =====
        { id: 'ema9',    name: 'EMA 9',    type: 'ema',  period: 9,   color: '#f5a623', overlay: true, category: 'Moving Averages' },
        { id: 'ema12',   name: 'EMA 12',   type: 'ema',  period: 12,  color: '#e67e22', overlay: true, category: 'Moving Averages' },
        { id: 'ema21',   name: 'EMA 21',   type: 'ema',  period: 21,  color: '#4a90d9', overlay: true, category: 'Moving Averages' },
        { id: 'ema26',   name: 'EMA 26',   type: 'ema',  period: 26,  color: '#3498db', overlay: true, category: 'Moving Averages' },
        { id: 'ema50',   name: 'EMA 50',   type: 'ema',  period: 50,  color: '#9b59b6', overlay: true, category: 'Moving Averages' },
        { id: 'ema100',  name: 'EMA 100',  type: 'ema',  period: 100, color: '#8e44ad', overlay: true, category: 'Moving Averages' },
        { id: 'ema200',  name: 'EMA 200',  type: 'ema',  period: 200, color: '#6c3483', overlay: true, category: 'Moving Averages' },
        { id: 'sma5',    name: 'SMA 5',    type: 'sma',  period: 5,   color: '#ff6b6b', overlay: true, category: 'Moving Averages' },
        { id: 'sma10',   name: 'SMA 10',   type: 'sma',  period: 10,  color: '#ee5a24', overlay: true, category: 'Moving Averages' },
        { id: 'sma20',   name: 'SMA 20',   type: 'sma',  period: 20,  color: '#e74c5e', overlay: true, category: 'Moving Averages' },
        { id: 'sma50',   name: 'SMA 50',   type: 'sma',  period: 50,  color: '#f1c40f', overlay: true, category: 'Moving Averages' },
        { id: 'sma100',  name: 'SMA 100',  type: 'sma',  period: 100, color: '#f39c12', overlay: true, category: 'Moving Averages' },
        { id: 'sma200',  name: 'SMA 200',  type: 'sma',  period: 200, color: '#2ecc71', overlay: true, category: 'Moving Averages' },
        { id: 'wma20',   name: 'WMA 20',   type: 'wma',  period: 20,  color: '#00b894', overlay: true, category: 'Moving Averages' },
        { id: 'dema20',  name: 'DEMA 20',  type: 'dema', period: 20,  color: '#00cec9', overlay: true, category: 'Moving Averages' },
        { id: 'tema20',  name: 'TEMA 20',  type: 'tema', period: 20,  color: '#0984e3', overlay: true, category: 'Moving Averages' },
        { id: 'kama10',  name: 'KAMA 10',  type: 'kama', period: 10,  color: '#6c5ce7', overlay: true, category: 'Moving Averages' },
        { id: 'hma20',   name: 'HMA 20',   type: 'hma',  period: 20,  color: '#fd79a8', overlay: true, category: 'Moving Averages' },
        { id: 'vwma20',  name: 'VWMA 20',  type: 'vwma', period: 20,  color: '#a29bfe', overlay: true, category: 'Moving Averages' },

        // ===== OVERLAYS =====
        { id: 'bb',        name: 'Bollinger Bands (20)',   type: 'bb',       period: 20, color: '#7c819a', overlay: true, category: 'Overlays' },
        { id: 'bb_narrow', name: 'Bollinger Bands (10)',   type: 'bb',       period: 10, color: '#636e72', overlay: true, category: 'Overlays' },
        { id: 'kc',        name: 'Keltner Channel (20)',   type: 'kc',       period: 20, color: '#e17055', overlay: true, category: 'Overlays' },
        { id: 'dc',        name: 'Donchian Channel (20)',  type: 'dc',       period: 20, color: '#00b894', overlay: true, category: 'Overlays' },
        { id: 'envup',     name: 'Envelope (20, 2.5%)',    type: 'envelope', period: 20, pct: 0.025, color: '#74b9ff', overlay: true, category: 'Overlays' },
        { id: 'psar',      name: 'Parabolic SAR',          type: 'psar',     color: '#fdcb6e', overlay: true, category: 'Overlays' },
        { id: 'ichimoku',  name: 'Ichimoku Cloud',         type: 'ichimoku', color: '#e74c3c', overlay: true, category: 'Overlays' },
        { id: 'supertrend', name: 'Supertrend (10,3)',     type: 'supertrend', period: 10, mult: 3, color: '#2ecc71', overlay: true, category: 'Overlays' },
        { id: 'pivots',    name: 'Pivot Points',           type: 'pivots',   color: '#dfe6e9', overlay: true, category: 'Overlays' },
        { id: 'vwap',      name: 'VWAP',                   type: 'vwap',     color: '#a29bfe', overlay: true, category: 'Overlays' },

        // ===== MOMENTUM (Oscillators) =====
        { id: 'rsi',       name: 'RSI (14)',           type: 'rsi',       period: 14, color: '#f5a623', overlay: false, category: 'Momentum' },
        { id: 'rsi7',      name: 'RSI (7)',            type: 'rsi',       period: 7,  color: '#e67e22', overlay: false, category: 'Momentum' },
        { id: 'stochrsi',  name: 'Stochastic RSI',    type: 'stochrsi',  period: 14, color: '#00cec9', overlay: false, category: 'Momentum' },
        { id: 'macd',      name: 'MACD (12,26,9)',    type: 'macd',      color: '#4a90d9', overlay: false, category: 'Momentum' },
        { id: 'stoch',     name: 'Stochastic (14,3)', type: 'stoch',     period: 14, smooth: 3, color: '#2ecc71', overlay: false, category: 'Momentum' },
        { id: 'cci',       name: 'CCI (20)',           type: 'cci',      period: 20,  color: '#e74c5e', overlay: false, category: 'Momentum' },
        { id: 'willr',     name: 'Williams %R (14)',   type: 'willr',    period: 14,  color: '#9b59b6', overlay: false, category: 'Momentum' },
        { id: 'mom',       name: 'Momentum (10)',      type: 'mom',      period: 10,  color: '#00b894', overlay: false, category: 'Momentum' },
        { id: 'roc',       name: 'ROC (12)',            type: 'roc',     period: 12,  color: '#6c5ce7', overlay: false, category: 'Momentum' },
        { id: 'tsi',       name: 'TSI (25,13)',         type: 'tsi',     color: '#fd79a8', overlay: false, category: 'Momentum' },
        { id: 'uo',        name: 'Ultimate Osc (7,14,28)', type: 'uo',  color: '#ffeaa7', overlay: false, category: 'Momentum' },
        { id: 'awesome',   name: 'Awesome Oscillator', type: 'awesome', color: '#55efc4', overlay: false, category: 'Momentum' },
        { id: 'ppo',       name: 'PPO (12,26)',        type: 'ppo',     color: '#74b9ff', overlay: false, category: 'Momentum' },
        { id: 'cmo',       name: 'CMO (14)',            type: 'cmo',    period: 14,  color: '#a29bfe', overlay: false, category: 'Momentum' },
        { id: 'fisher',    name: 'Fisher Transform (9)',type: 'fisher',  period: 9,   color: '#81ecec', overlay: false, category: 'Momentum' },

        // ===== VOLATILITY =====
        { id: 'atr',       name: 'ATR (14)',            type: 'atr',    period: 14,  color: '#e74c5e', overlay: false, category: 'Volatility' },
        { id: 'natr',      name: 'Normalized ATR (14)', type: 'natr',   period: 14,  color: '#ff7675', overlay: false, category: 'Volatility' },
        { id: 'bbwidth',   name: 'BB Width (20)',       type: 'bbwidth', period: 20, color: '#7c819a', overlay: false, category: 'Volatility' },
        { id: 'bbpct',     name: 'BB %B (20)',          type: 'bbpct',  period: 20,  color: '#636e72', overlay: false, category: 'Volatility' },
        { id: 'stddev',    name: 'Std Deviation (20)',  type: 'stddev', period: 20,  color: '#dfe6e9', overlay: false, category: 'Volatility' },
        { id: 'chop',      name: 'Choppiness (14)',     type: 'chop',   period: 14,  color: '#ffeaa7', overlay: false, category: 'Volatility' },
        { id: 'kc_width',  name: 'Keltner Width (20)',  type: 'kc_width', period: 20, color: '#e17055', overlay: false, category: 'Volatility' },

        // ===== VOLUME =====
        { id: 'obv',       name: 'OBV',                 type: 'obv',    color: '#00b894', overlay: false, category: 'Volume' },
        { id: 'adosc',     name: 'Chaikin A/D Osc',     type: 'adosc',  color: '#6c5ce7', overlay: false, category: 'Volume' },
        { id: 'cmf',       name: 'CMF (20)',             type: 'cmf',   period: 20,  color: '#0984e3', overlay: false, category: 'Volume' },
        { id: 'mfi',       name: 'MFI (14)',             type: 'mfi',   period: 14,  color: '#00cec9', overlay: false, category: 'Volume' },
        { id: 'eom',       name: 'Ease of Movement',    type: 'eom',   period: 14,  color: '#fd79a8', overlay: false, category: 'Volume' },
        { id: 'vpt',       name: 'Volume Price Trend',  type: 'vpt',   color: '#a29bfe', overlay: false, category: 'Volume' },
        { id: 'fi',        name: 'Force Index (13)',     type: 'fi',    period: 13,  color: '#55efc4', overlay: false, category: 'Volume' },
        { id: 'nvi',       name: 'NVI',                  type: 'nvi',  color: '#74b9ff', overlay: false, category: 'Volume' },

        // ===== TREND =====
        { id: 'adx',       name: 'ADX (14)',            type: 'adx',    period: 14,  color: '#f1c40f', overlay: false, category: 'Trend' },
        { id: 'di',        name: '+DI / -DI (14)',      type: 'di',     period: 14,  color: '#2ecc71', overlay: false, category: 'Trend' },
        { id: 'aroon',     name: 'Aroon (25)',           type: 'aroon', period: 25,  color: '#e74c5e', overlay: false, category: 'Trend' },
        { id: 'aroonosc',  name: 'Aroon Oscillator',    type: 'aroonosc', period: 25, color: '#9b59b6', overlay: false, category: 'Trend' },
        { id: 'vortex',    name: 'Vortex (14)',          type: 'vortex', period: 14, color: '#00b894', overlay: false, category: 'Trend' },
        { id: 'dpo',       name: 'DPO (20)',             type: 'dpo',   period: 20,  color: '#fdcb6e', overlay: false, category: 'Trend' },
        { id: 'trix',      name: 'TRIX (15)',            type: 'trix',  period: 15,  color: '#81ecec', overlay: false, category: 'Trend' },
        { id: 'mass',      name: 'Mass Index (25)',      type: 'mass',  period: 25,  color: '#fab1a0', overlay: false, category: 'Trend' },
        { id: 'copp',      name: 'Coppock Curve',        type: 'copp',  color: '#dfe6e9', overlay: false, category: 'Trend' },
    ],

    // Background tint colors for each indicator type (subtle, translucent)
    _indicatorTypeBg: {
        // Moving Averages - green shades
        'ema':  'rgba(45, 212, 168, 0.08)',
        'sma':  'rgba(45, 212, 168, 0.06)',
        'wma':  'rgba(45, 212, 168, 0.07)',
        'dema': 'rgba(45, 212, 168, 0.09)',
        'tema': 'rgba(45, 212, 168, 0.10)',
        'kama': 'rgba(45, 212, 168, 0.07)',
        'hma':  'rgba(45, 212, 168, 0.08)',
        'vwma': 'rgba(45, 212, 168, 0.06)',
        // RSI / Momentum - yellow/amber shades
        'rsi':      'rgba(241, 196, 15, 0.08)',
        'stochrsi': 'rgba(241, 196, 15, 0.06)',
        'stoch':    'rgba(241, 196, 15, 0.07)',
        'cci':      'rgba(241, 196, 15, 0.09)',
        'willr':    'rgba(241, 196, 15, 0.07)',
        'mom':      'rgba(241, 196, 15, 0.08)',
        'roc':      'rgba(241, 196, 15, 0.06)',
        'cmo':      'rgba(241, 196, 15, 0.07)',
        'fisher':   'rgba(241, 196, 15, 0.08)',
        // MACD family - blue shades
        'macd': 'rgba(74, 144, 217, 0.08)',
        'ppo':  'rgba(74, 144, 217, 0.07)',
        'tsi':  'rgba(74, 144, 217, 0.06)',
        'uo':   'rgba(74, 144, 217, 0.07)',
        'awesome': 'rgba(74, 144, 217, 0.08)',
        // Bollinger / Volatility - purple shades
        'bb':       'rgba(155, 89, 182, 0.08)',
        'bbwidth':  'rgba(155, 89, 182, 0.06)',
        'bbpct':    'rgba(155, 89, 182, 0.07)',
        'kc':       'rgba(155, 89, 182, 0.07)',
        'kc_width': 'rgba(155, 89, 182, 0.06)',
        'dc':       'rgba(155, 89, 182, 0.08)',
        'envelope': 'rgba(155, 89, 182, 0.07)',
        'stddev':   'rgba(155, 89, 182, 0.06)',
        'chop':     'rgba(155, 89, 182, 0.07)',
        'atr':      'rgba(155, 89, 182, 0.08)',
        'natr':     'rgba(155, 89, 182, 0.07)',
        // Overlays - teal/cyan shades
        'psar':       'rgba(0, 206, 201, 0.08)',
        'ichimoku':   'rgba(0, 206, 201, 0.07)',
        'supertrend': 'rgba(0, 206, 201, 0.08)',
        'pivots':     'rgba(0, 206, 201, 0.06)',
        'vwap':       'rgba(0, 206, 201, 0.07)',
        // Volume - orange shades
        'obv':   'rgba(245, 166, 35, 0.08)',
        'adosc': 'rgba(245, 166, 35, 0.07)',
        'cmf':   'rgba(245, 166, 35, 0.06)',
        'mfi':   'rgba(245, 166, 35, 0.08)',
        'eom':   'rgba(245, 166, 35, 0.07)',
        'vpt':   'rgba(245, 166, 35, 0.06)',
        'fi':    'rgba(245, 166, 35, 0.07)',
        'nvi':   'rgba(245, 166, 35, 0.08)',
        // Trend - red/coral shades
        'adx':      'rgba(231, 76, 94, 0.08)',
        'di':       'rgba(231, 76, 94, 0.07)',
        'aroon':    'rgba(231, 76, 94, 0.06)',
        'aroonosc': 'rgba(231, 76, 94, 0.07)',
        'vortex':   'rgba(231, 76, 94, 0.08)',
        'dpo':      'rgba(231, 76, 94, 0.06)',
        'trix':     'rgba(231, 76, 94, 0.07)',
        'mass':     'rgba(231, 76, 94, 0.08)',
        'copp':     'rgba(231, 76, 94, 0.06)',
    },

    // Per-indicator-type icons
    _indicatorTypeIcons: {
        'ema': 'bi-graph-up', 'sma': 'bi-graph-up', 'wma': 'bi-graph-up', 'dema': 'bi-graph-up',
        'tema': 'bi-graph-up', 'kama': 'bi-graph-up', 'hma': 'bi-graph-up', 'vwma': 'bi-graph-up',
        'bb': 'bi-distribute-vertical', 'kc': 'bi-distribute-vertical', 'dc': 'bi-distribute-vertical',
        'envelope': 'bi-arrows-expand', 'ichimoku': 'bi-clouds', 'psar': 'bi-three-dots',
        'supertrend': 'bi-arrow-up-right-circle', 'pivot': 'bi-crosshair',
        'rsi': 'bi-speedometer2', 'stochrsi': 'bi-speedometer', 'stoch': 'bi-speedometer',
        'cci': 'bi-arrow-left-right', 'mfi': 'bi-droplet-half', 'willr': 'bi-percent',
        'roc': 'bi-arrow-return-right', 'momentum': 'bi-lightning-charge',
        'macd': 'bi-bar-chart-line', 'trix': 'bi-graph-down', 'awesome': 'bi-bar-chart-steps',
        'atr': 'bi-arrows-expand-vertical', 'bbw': 'bi-arrows-expand', 'natr': 'bi-arrows-expand-vertical',
        'obv': 'bi-bar-chart-fill', 'vpt': 'bi-bar-chart-fill', 'cmf': 'bi-water',
        'adl': 'bi-bar-chart', 'efi': 'bi-lightning',
        'adx': 'bi-compass', 'aroon': 'bi-sunrise', 'ppo': 'bi-percent', 'dmi': 'bi-signpost-split',
    },

    // Category header badge colors
    _categoryColors: {
        'Moving Averages': { bg: 'rgba(45, 212, 168, 0.12)', color: '#2dd4a8', icon: 'bi-graph-up' },
        'Overlays':        { bg: 'rgba(0, 206, 201, 0.12)',   color: '#00cec9', icon: 'bi-layers' },
        'Momentum':        { bg: 'rgba(241, 196, 15, 0.12)',  color: '#f1c40f', icon: 'bi-speedometer2' },
        'Volatility':      { bg: 'rgba(155, 89, 182, 0.12)',  color: '#9b59b6', icon: 'bi-bar-chart-steps' },
        'Volume':          { bg: 'rgba(245, 166, 35, 0.12)',  color: '#f5a623', icon: 'bi-bar-chart-fill' },
        'Trend':           { bg: 'rgba(231, 76, 94, 0.12)',   color: '#e74c5e', icon: 'bi-arrow-up-right' },
    },

    showIndicatorsModal() {
        let existing = document.getElementById('indicatorsModal');
        if (existing) existing.remove();

        // Group indicators by category
        const categories = {};
        this._indicatorDefs.forEach(d => {
            const cat = d.category || (d.overlay ? 'Overlays' : 'Oscillators');
            if (!categories[cat]) categories[cat] = [];
            categories[cat].push(d);
        });

        const categoryOrder = ['Moving Averages', 'Overlays', 'Momentum', 'Volatility', 'Volume', 'Trend'];
        const activeCount = Object.keys(this._indicators).filter(k => this._indicators[k]?.enabled).length;

        const html = `
        <div class="modal fade" id="indicatorsModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered modal-dialog-scrollable">
                <div class="modal-content" style="background:var(--bc-card);border-color:var(--bc-border)">
                    <div class="modal-header border-secondary">
                        <h5 class="modal-title"><i class="bi bi-activity me-2"></i>Chart Indicators</h5>
                        <span class="badge bg-success ms-2" id="indActiveCount">${activeCount} active</span>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="px-3 pt-3 pb-2">
                        <input type="text" class="form-control form-control-sm" placeholder="Search indicators..."
                            id="indSearchInput" oninput="BotsPage._filterIndicatorModal(this.value)"
                            style="background:var(--bc-bg);border-color:var(--bc-border);color:var(--bc-text)">
                    </div>
                    <div class="modal-body" style="max-height:55vh;overflow-y:auto" id="indModalBody">
                        ${categoryOrder.map(cat => {
                            const items = categories[cat] || [];
                            if (items.length === 0) return '';
                            const isOverlay = items[0].overlay;
                            const catColor = this._categoryColors[cat] || { bg: 'transparent', color: '#8a8fa8', icon: 'bi-circle' };
                            return `
                            <div class="ind-category" data-category="${cat}">
                                <div class="d-flex align-items-center gap-2 mt-3 mb-2 px-2 py-1 rounded" style="background:${catColor.bg}">
                                    <i class="bi ${catColor.icon}" style="color:${catColor.color};font-size:13px"></i>
                                    <h6 class="small fw-semibold mb-0 text-uppercase" style="color:${catColor.color}">${cat}</h6>
                                    ${!isOverlay ? '<small class="fw-normal text-secondary">(separate pane)</small>' : ''}
                                    <span class="badge ms-auto" style="background:${catColor.bg};color:${catColor.color};font-size:10px">${items.length}</span>
                                </div>
                                ${items.map(d => {
                                    const typeBg = this._indicatorTypeBg[d.type] || 'transparent';
                                    return `
                                <div class="ind-row form-check form-switch d-flex align-items-center justify-content-between py-1 px-2 rounded-1 mb-1" data-name="${d.name.toLowerCase()}" data-id="${d.id}"
                                    style="background:${typeBg};border-left:3px solid ${d.color}20;transition:background 0.15s">
                                    <div>
                                        <span class="fw-semibold" style="color:${d.color}"><i class="bi ${this._indicatorTypeIcons[d.type] || 'bi-circle-fill'} me-1" style="font-size:${this._indicatorTypeIcons[d.type] ? '12px' : '7px'};opacity:0.8"></i>${d.name}</span>
                                    </div>
                                    <input class="form-check-input" type="checkbox" id="ind-${d.id}" ${this._indicators[d.id]?.enabled ? 'checked' : ''}
                                        onchange="BotsPage.toggleIndicator('${d.id}', this.checked)">
                                </div>`;
                                }).join('')}
                            </div>`;
                        }).join('')}
                    </div>
                    <div class="modal-footer border-secondary">
                        <button class="btn btn-outline-secondary btn-sm" onclick="BotsPage.clearAllIndicators()">Clear All</button>
                        <button class="btn btn-success btn-sm" data-bs-dismiss="modal">Done</button>
                    </div>
                </div>
            </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', html);
        const modal = new bootstrap.Modal(document.getElementById('indicatorsModal'));
        modal.show();
        // Focus search on open
        document.getElementById('indicatorsModal').addEventListener('shown.bs.modal', () => {
            document.getElementById('indSearchInput')?.focus();
        });
    },

    _filterIndicatorModal(query) {
        const q = query.toLowerCase().trim();
        document.querySelectorAll('#indModalBody .ind-row').forEach(row => {
            row.style.display = row.dataset.name.includes(q) ? '' : 'none';
        });
        // Hide empty categories
        document.querySelectorAll('#indModalBody .ind-category').forEach(cat => {
            const visible = cat.querySelectorAll('.ind-row[style=""], .ind-row:not([style])').length;
            cat.style.display = visible > 0 ? '' : 'none';
        });
    },

    _updateActiveCount() {
        const el = document.getElementById('indActiveCount');
        if (el) {
            const n = Object.keys(this._indicators).filter(k => this._indicators[k]?.enabled).length;
            el.textContent = n + ' active';
        }
    },

    toggleIndicator(id, enabled) {
        const def = this._indicatorDefs.find(d => d.id === id);
        if (!def) return;

        if (!enabled) {
            if (this._indicators[id]?.series) {
                const series = this._indicators[id].series;
                (Array.isArray(series) ? series : [series]).forEach(s => {
                    try { this.chart.removeSeries(s); } catch(e){}
                });
            }
            delete this._indicators[id];
            this._updateActiveCount();
            return;
        }

        const cached = this._getCached(this.currentPair, this.currentTimeframe);
        if (!cached || !cached.candles || cached.candles.length === 0) {
            App.showToast('Load chart data first', 'warning');
            const cb = document.getElementById('ind-' + id);
            if (cb) cb.checked = false;
            return;
        }

        const candles = cached.candles;
        this._indicators[id] = { enabled: true };
        const scaleId = def.overlay ? undefined : id;
        const lineOpts = (color, extra = {}) => ({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, ...extra });
        const oscOpts = (color, extra = {}) => ({ ...lineOpts(color, extra), priceScaleId: scaleId, lastValueVisible: true });
        const setOscScale = () => {
            if (scaleId) this.chart.priceScale(scaleId).applyOptions({ scaleMargins: { top: 0.85, bottom: 0 }, borderVisible: false });
        };
        const addLine = (data, opts) => { const s = this.chart.addLineSeries(opts); s.setData(data); return s; };
        const addHist = (data, opts) => { const s = this.chart.addHistogramSeries(opts); s.setData(data); return s; };

        try {
        // ========== MOVING AVERAGES ==========
        if (def.type === 'ema' || def.type === 'sma') {
            this._indicators[id].series = addLine(this._calcMA(candles, def.period, def.type), lineOpts(def.color));

        } else if (def.type === 'wma') {
            this._indicators[id].series = addLine(this._calcWMA(candles, def.period), lineOpts(def.color));

        } else if (def.type === 'dema') {
            this._indicators[id].series = addLine(this._calcDEMA(candles, def.period), lineOpts(def.color));

        } else if (def.type === 'tema') {
            this._indicators[id].series = addLine(this._calcTEMA(candles, def.period), lineOpts(def.color));

        } else if (def.type === 'kama') {
            this._indicators[id].series = addLine(this._calcKAMA(candles, def.period), lineOpts(def.color));

        } else if (def.type === 'hma') {
            this._indicators[id].series = addLine(this._calcHMA(candles, def.period), lineOpts(def.color));

        } else if (def.type === 'vwma') {
            this._indicators[id].series = addLine(this._calcVWMA(candles, def.period), lineOpts(def.color));

        // ========== OVERLAYS ==========
        } else if (def.type === 'bb') {
            const bb = this._calcBB(candles, def.period);
            this._indicators[id].series = [
                addLine(bb.upper, lineOpts(def.color, { lineStyle: 2 })),
                addLine(bb.lower, lineOpts(def.color, { lineStyle: 2 })),
                addLine(bb.mid,   lineOpts(def.color, { lineStyle: 1 })),
            ];

        } else if (def.type === 'kc') {
            const kc = this._calcKC(candles, def.period);
            this._indicators[id].series = [
                addLine(kc.upper, lineOpts(def.color, { lineStyle: 2 })),
                addLine(kc.lower, lineOpts(def.color, { lineStyle: 2 })),
                addLine(kc.mid,   lineOpts(def.color, { lineStyle: 1 })),
            ];

        } else if (def.type === 'dc') {
            const dc = this._calcDC(candles, def.period);
            this._indicators[id].series = [
                addLine(dc.upper, lineOpts(def.color, { lineStyle: 2 })),
                addLine(dc.lower, lineOpts(def.color, { lineStyle: 2 })),
                addLine(dc.mid,   lineOpts(def.color, { lineStyle: 1 })),
            ];

        } else if (def.type === 'envelope') {
            const env = this._calcEnvelope(candles, def.period, def.pct);
            this._indicators[id].series = [
                addLine(env.upper, lineOpts(def.color, { lineStyle: 2 })),
                addLine(env.lower, lineOpts(def.color, { lineStyle: 2 })),
                addLine(env.mid,   lineOpts(def.color, { lineStyle: 1 })),
            ];

        } else if (def.type === 'psar') {
            const data = this._calcPSAR(candles);
            const s = this.chart.addLineSeries({ ...lineOpts(def.color), lineType: 1, pointMarkersVisible: true, lineVisible: false });
            s.setData(data);
            this._indicators[id].series = s;

        } else if (def.type === 'ichimoku') {
            const ich = this._calcIchimoku(candles);
            this._indicators[id].series = [
                addLine(ich.tenkan,  lineOpts('#e74c3c')),
                addLine(ich.kijun,   lineOpts('#3498db')),
                addLine(ich.senkouA, lineOpts('#2ecc71', { lineStyle: 2 })),
                addLine(ich.senkouB, lineOpts('#e74c5e', { lineStyle: 2 })),
                addLine(ich.chikou,  lineOpts('#9b59b6', { lineStyle: 1 })),
            ];

        } else if (def.type === 'supertrend') {
            const st = this._calcSupertrend(candles, def.period, def.mult);
            const s = this.chart.addLineSeries({ ...lineOpts(def.color), lineWidth: 2 });
            s.setData(st);
            this._indicators[id].series = s;

        } else if (def.type === 'pivots') {
            const piv = this._calcPivots(candles);
            this._indicators[id].series = [
                addLine(piv.pivot, lineOpts('#dfe6e9', { lineStyle: 1 })),
                addLine(piv.r1,    lineOpts('#e74c5e', { lineStyle: 2 })),
                addLine(piv.s1,    lineOpts('#2ecc71', { lineStyle: 2 })),
                addLine(piv.r2,    lineOpts('#ff7675', { lineStyle: 2 })),
                addLine(piv.s2,    lineOpts('#55efc4', { lineStyle: 2 })),
            ];

        } else if (def.type === 'vwap') {
            this._indicators[id].series = addLine(this._calcVWAP(candles), lineOpts(def.color, { lineWidth: 2 }));

        // ========== MOMENTUM / OSCILLATORS ==========
        } else if (def.type === 'rsi') {
            this._indicators[id].series = addLine(this._calcRSI(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'stochrsi') {
            const sr = this._calcStochRSI(candles, def.period);
            this._indicators[id].series = [
                addLine(sr.k, oscOpts('#00cec9')),
                addLine(sr.d, oscOpts('#e74c5e', { lineStyle: 2 })),
            ];
            setOscScale();

        } else if (def.type === 'macd') {
            const macd = this._calcMACD(candles);
            this._indicators[id].series = [
                addLine(macd.macd, { ...oscOpts('#4a90d9'), lineWidth: 1.5 }),
                addLine(macd.signal, oscOpts('#e74c5e')),
                addHist(macd.histogram, { priceScaleId: scaleId, priceLineVisible: false, lastValueVisible: false }),
            ];
            setOscScale();

        } else if (def.type === 'stoch') {
            const stoch = this._calcStoch(candles, def.period, def.smooth);
            this._indicators[id].series = [
                addLine(stoch.k, oscOpts(def.color)),
                addLine(stoch.d, oscOpts('#e74c5e', { lineStyle: 2 })),
            ];
            setOscScale();

        } else if (def.type === 'cci') {
            this._indicators[id].series = addLine(this._calcCCI(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'willr') {
            this._indicators[id].series = addLine(this._calcWillR(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'mom') {
            this._indicators[id].series = addLine(this._calcMomentum(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'roc') {
            this._indicators[id].series = addLine(this._calcROC(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'tsi') {
            this._indicators[id].series = addLine(this._calcTSI(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'uo') {
            this._indicators[id].series = addLine(this._calcUO(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'awesome') {
            this._indicators[id].series = addHist(this._calcAwesome(candles), { priceScaleId: scaleId, priceLineVisible: false, lastValueVisible: false });
            setOscScale();

        } else if (def.type === 'ppo') {
            this._indicators[id].series = addLine(this._calcPPO(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'cmo') {
            this._indicators[id].series = addLine(this._calcCMO(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'fisher') {
            this._indicators[id].series = addLine(this._calcFisher(candles, def.period), oscOpts(def.color));
            setOscScale();

        // ========== VOLATILITY ==========
        } else if (def.type === 'atr') {
            this._indicators[id].series = addLine(this._calcATR(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'natr') {
            this._indicators[id].series = addLine(this._calcNATR(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'bbwidth') {
            this._indicators[id].series = addLine(this._calcBBWidth(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'bbpct') {
            this._indicators[id].series = addLine(this._calcBBPct(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'stddev') {
            this._indicators[id].series = addLine(this._calcStdDev(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'chop') {
            this._indicators[id].series = addLine(this._calcChop(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'kc_width') {
            this._indicators[id].series = addLine(this._calcKCWidth(candles, def.period), oscOpts(def.color));
            setOscScale();

        // ========== VOLUME ==========
        } else if (def.type === 'obv') {
            this._indicators[id].series = addLine(this._calcOBV(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'adosc') {
            this._indicators[id].series = addLine(this._calcADOsc(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'cmf') {
            this._indicators[id].series = addLine(this._calcCMF(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'mfi') {
            this._indicators[id].series = addLine(this._calcMFI(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'eom') {
            this._indicators[id].series = addLine(this._calcEOM(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'vpt') {
            this._indicators[id].series = addLine(this._calcVPT(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'fi') {
            this._indicators[id].series = addLine(this._calcFI(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'nvi') {
            this._indicators[id].series = addLine(this._calcNVI(candles), oscOpts(def.color));
            setOscScale();

        // ========== TREND ==========
        } else if (def.type === 'adx') {
            this._indicators[id].series = addLine(this._calcADX(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'di') {
            const di = this._calcDI(candles, def.period);
            this._indicators[id].series = [
                addLine(di.plus, oscOpts('#2ecc71')),
                addLine(di.minus, oscOpts('#e74c5e')),
            ];
            setOscScale();

        } else if (def.type === 'aroon') {
            const ar = this._calcAroon(candles, def.period);
            this._indicators[id].series = [
                addLine(ar.up, oscOpts('#2ecc71')),
                addLine(ar.down, oscOpts('#e74c5e')),
            ];
            setOscScale();

        } else if (def.type === 'aroonosc') {
            this._indicators[id].series = addLine(this._calcAroonOsc(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'vortex') {
            const vt = this._calcVortex(candles, def.period);
            this._indicators[id].series = [
                addLine(vt.plus, oscOpts('#2ecc71')),
                addLine(vt.minus, oscOpts('#e74c5e')),
            ];
            setOscScale();

        } else if (def.type === 'dpo') {
            this._indicators[id].series = addLine(this._calcDPO(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'trix') {
            this._indicators[id].series = addLine(this._calcTRIX(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'mass') {
            this._indicators[id].series = addLine(this._calcMass(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'copp') {
            this._indicators[id].series = addLine(this._calcCoppock(candles), oscOpts(def.color));
            setOscScale();
        }

        } catch(e) {
            console.error(`Error adding indicator ${id}:`, e);
            App.showToast(`Error computing ${def.name}: ${e.message}`, 'error');
            delete this._indicators[id];
            const cb = document.getElementById('ind-' + id);
            if (cb) cb.checked = false;
        }
        this._updateActiveCount();
    },

    clearAllIndicators() {
        Object.keys(this._indicators).forEach(id => this.toggleIndicator(id, false));
        // Uncheck all checkboxes in modal
        document.querySelectorAll('#indicatorsModal input[type="checkbox"]').forEach(cb => cb.checked = false);
    },

    // ---- Indicator calculation helpers ----
    _calcMA(candles, period, type) {
        const result = [];
        for (let i = period - 1; i < candles.length; i++) {
            if (type === 'sma') {
                let sum = 0;
                for (let j = 0; j < period; j++) sum += candles[i - j].close;
                result.push({ time: candles[i].time, value: sum / period });
            } else {
                // EMA
                if (result.length === 0) {
                    let sum = 0;
                    for (let j = 0; j < period; j++) sum += candles[i - j].close;
                    result.push({ time: candles[i].time, value: sum / period });
                } else {
                    const k = 2 / (period + 1);
                    const prev = result[result.length - 1].value;
                    result.push({ time: candles[i].time, value: candles[i].close * k + prev * (1 - k) });
                }
            }
        }
        return result;
    },

    _calcBB(candles, period) {
        const upper = [], lower = [], mid = [];
        for (let i = period - 1; i < candles.length; i++) {
            let sum = 0;
            for (let j = 0; j < period; j++) sum += candles[i - j].close;
            const avg = sum / period;
            let sqSum = 0;
            for (let j = 0; j < period; j++) sqSum += Math.pow(candles[i - j].close - avg, 2);
            const std = Math.sqrt(sqSum / period);
            const t = candles[i].time;
            upper.push({ time: t, value: avg + 2 * std });
            lower.push({ time: t, value: avg - 2 * std });
            mid.push({ time: t, value: avg });
        }
        return { upper, lower, mid };
    },

    _calcRSI(candles, period) {
        const result = [];
        let gains = 0, losses = 0;
        for (let i = 1; i <= period; i++) {
            const diff = candles[i].close - candles[i - 1].close;
            if (diff > 0) gains += diff; else losses -= diff;
        }
        let avgGain = gains / period;
        let avgLoss = losses / period;
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        result.push({ time: candles[period].time, value: 100 - 100 / (1 + rs) });
        for (let i = period + 1; i < candles.length; i++) {
            const diff = candles[i].close - candles[i - 1].close;
            avgGain = (avgGain * (period - 1) + (diff > 0 ? diff : 0)) / period;
            avgLoss = (avgLoss * (period - 1) + (diff < 0 ? -diff : 0)) / period;
            const rs2 = avgLoss === 0 ? 100 : avgGain / avgLoss;
            result.push({ time: candles[i].time, value: 100 - 100 / (1 + rs2) });
        }
        return result;
    },

    _calcMACD(candles) {
        const ema12 = this._calcMA(candles, 12, 'ema');
        const ema26 = this._calcMA(candles, 26, 'ema');
        // Align by time
        const macdLine = [];
        const ema26Map = {};
        ema26.forEach(e => ema26Map[e.time] = e.value);
        ema12.forEach(e => {
            if (ema26Map[e.time] !== undefined) {
                macdLine.push({ time: e.time, value: e.value - ema26Map[e.time] });
            }
        });
        // Signal line (9-period EMA of MACD)
        const signalLine = [];
        for (let i = 8; i < macdLine.length; i++) {
            if (signalLine.length === 0) {
                let sum = 0;
                for (let j = 0; j < 9; j++) sum += macdLine[i - j].value;
                signalLine.push({ time: macdLine[i].time, value: sum / 9 });
            } else {
                const k = 2 / 10;
                const prev = signalLine[signalLine.length - 1].value;
                signalLine.push({ time: macdLine[i].time, value: macdLine[i].value * k + prev * (1 - k) });
            }
        }
        // Histogram
        const sigMap = {};
        signalLine.forEach(s => sigMap[s.time] = s.value);
        const histogram = macdLine.filter(m => sigMap[m.time] !== undefined).map(m => ({
            time: m.time,
            value: m.value - sigMap[m.time],
            color: m.value - sigMap[m.time] >= 0 ? 'rgba(45,212,168,0.5)' : 'rgba(231,76,94,0.5)',
        }));
        return { macd: macdLine, signal: signalLine, histogram };
    },

    // Helper: EMA over raw values array, returns raw values array
    _emaRaw(values, period) {
        const result = [];
        const k = 2 / (period + 1);
        for (let i = 0; i < values.length; i++) {
            if (values[i] === null || values[i] === undefined) { result.push(null); continue; }
            if (result.length === 0 || result.every(v => v === null)) {
                result.push(values[i]);
            } else {
                const prev = result[result.length - 1];
                result.push(prev !== null ? values[i] * k + prev * (1 - k) : values[i]);
            }
        }
        return result;
    },

    _calcWMA(candles, period) {
        const result = [];
        const denom = period * (period + 1) / 2;
        for (let i = period - 1; i < candles.length; i++) {
            let sum = 0;
            for (let j = 0; j < period; j++) sum += candles[i - j].close * (period - j);
            result.push({ time: candles[i].time, value: sum / denom });
        }
        return result;
    },

    _calcDEMA(candles, period) {
        const ema1 = this._calcMA(candles, period, 'ema');
        // Build candle-like objects from ema1 for second EMA pass
        const ema2 = this._calcMA(ema1.map(e => ({ time: e.time, close: e.value })), period, 'ema');
        const ema2Map = {}; ema2.forEach(e => ema2Map[e.time] = e.value);
        return ema1.filter(e => ema2Map[e.time] !== undefined).map(e => ({ time: e.time, value: 2 * e.value - ema2Map[e.time] }));
    },

    _calcTEMA(candles, period) {
        const e1 = this._calcMA(candles, period, 'ema');
        const e2 = this._calcMA(e1.map(e => ({ time: e.time, close: e.value })), period, 'ema');
        const e3 = this._calcMA(e2.map(e => ({ time: e.time, close: e.value })), period, 'ema');
        const e2Map = {}; e2.forEach(e => e2Map[e.time] = e.value);
        const e3Map = {}; e3.forEach(e => e3Map[e.time] = e.value);
        return e1.filter(e => e2Map[e.time] !== undefined && e3Map[e.time] !== undefined)
            .map(e => ({ time: e.time, value: 3 * e.value - 3 * e2Map[e.time] + e3Map[e.time] }));
    },

    _calcKAMA(candles, period) {
        const result = [];
        const fast = 2 / (2 + 1), slow = 2 / (30 + 1);
        for (let i = period; i < candles.length; i++) {
            const direction = Math.abs(candles[i].close - candles[i - period].close);
            let volatility = 0;
            for (let j = 0; j < period; j++) volatility += Math.abs(candles[i - j].close - candles[i - j - 1].close);
            const er = volatility === 0 ? 0 : direction / volatility;
            const sc = Math.pow(er * (fast - slow) + slow, 2);
            const prev = result.length > 0 ? result[result.length - 1].value : candles[i].close;
            result.push({ time: candles[i].time, value: prev + sc * (candles[i].close - prev) });
        }
        return result;
    },

    _calcHMA(candles, period) {
        const half = Math.floor(period / 2);
        const sqrtP = Math.floor(Math.sqrt(period));
        const wma1 = this._calcWMA(candles, half);
        const wma2 = this._calcWMA(candles, period);
        // Align by time and compute 2*wma(half) - wma(full)
        const wma2Map = {}; wma2.forEach(w => wma2Map[w.time] = w.value);
        const diff = wma1.filter(w => wma2Map[w.time] !== undefined)
            .map(w => ({ time: w.time, close: 2 * w.value - wma2Map[w.time] }));
        return this._calcWMA(diff, sqrtP);
    },

    _calcVWMA(candles, period) {
        const result = [];
        for (let i = period - 1; i < candles.length; i++) {
            let sumPV = 0, sumV = 0;
            for (let j = 0; j < period; j++) {
                const v = candles[i - j].volume || 1;
                sumPV += candles[i - j].close * v;
                sumV += v;
            }
            result.push({ time: candles[i].time, value: sumPV / sumV });
        }
        return result;
    },

    _calcATR(candles, period) {
        const result = [];
        const tr = [];
        for (let i = 0; i < candles.length; i++) {
            if (i === 0) { tr.push(candles[i].high - candles[i].low); continue; }
            tr.push(Math.max(candles[i].high - candles[i].low, Math.abs(candles[i].high - candles[i-1].close), Math.abs(candles[i].low - candles[i-1].close)));
        }
        let atr = 0;
        for (let i = 0; i < period; i++) atr += tr[i];
        atr /= period;
        result.push({ time: candles[period - 1].time, value: atr });
        for (let i = period; i < candles.length; i++) {
            atr = (atr * (period - 1) + tr[i]) / period;
            result.push({ time: candles[i].time, value: atr });
        }
        return result;
    },

    _calcKC(candles, period) {
        const ema = this._calcMA(candles, period, 'ema');
        const atr = this._calcATR(candles, period);
        const atrMap = {}; atr.forEach(a => atrMap[a.time] = a.value);
        const upper = [], lower = [], mid = [];
        ema.forEach(e => {
            if (atrMap[e.time] !== undefined) {
                upper.push({ time: e.time, value: e.value + 2 * atrMap[e.time] });
                lower.push({ time: e.time, value: e.value - 2 * atrMap[e.time] });
                mid.push({ time: e.time, value: e.value });
            }
        });
        return { upper, lower, mid };
    },

    _calcDC(candles, period) {
        const upper = [], lower = [], mid = [];
        for (let i = period - 1; i < candles.length; i++) {
            let hi = -Infinity, lo = Infinity;
            for (let j = 0; j < period; j++) { hi = Math.max(hi, candles[i-j].high); lo = Math.min(lo, candles[i-j].low); }
            upper.push({ time: candles[i].time, value: hi });
            lower.push({ time: candles[i].time, value: lo });
            mid.push({ time: candles[i].time, value: (hi + lo) / 2 });
        }
        return { upper, lower, mid };
    },

    _calcEnvelope(candles, period, pct) {
        const sma = this._calcMA(candles, period, 'sma');
        return {
            upper: sma.map(s => ({ time: s.time, value: s.value * (1 + pct) })),
            lower: sma.map(s => ({ time: s.time, value: s.value * (1 - pct) })),
            mid: sma,
        };
    },

    _calcPSAR(candles) {
        const result = [];
        if (candles.length < 2) return result;
        let af = 0.02, maxAf = 0.2, rising = true;
        let sar = candles[0].low, ep = candles[0].high;
        for (let i = 1; i < candles.length; i++) {
            const prev = sar;
            sar = prev + af * (ep - prev);
            if (rising) {
                if (candles[i].low < sar) { rising = false; sar = ep; ep = candles[i].low; af = 0.02; }
                else { if (candles[i].high > ep) { ep = candles[i].high; af = Math.min(af + 0.02, maxAf); } }
            } else {
                if (candles[i].high > sar) { rising = true; sar = ep; ep = candles[i].high; af = 0.02; }
                else { if (candles[i].low < ep) { ep = candles[i].low; af = Math.min(af + 0.02, maxAf); } }
            }
            result.push({ time: candles[i].time, value: sar });
        }
        return result;
    },

    _calcIchimoku(candles) {
        const tenkan = [], kijun = [], senkouA = [], senkouB = [], chikou = [];
        const hl = (arr, i, p) => { let hi = -Infinity, lo = Infinity; for (let j = 0; j < p && i - j >= 0; j++) { hi = Math.max(hi, arr[i-j].high); lo = Math.min(lo, arr[i-j].low); } return (hi + lo) / 2; };
        for (let i = 0; i < candles.length; i++) {
            if (i >= 8) tenkan.push({ time: candles[i].time, value: hl(candles, i, 9) });
            if (i >= 25) kijun.push({ time: candles[i].time, value: hl(candles, i, 26) });
            if (i >= 25 && tenkan.length > 0 && kijun.length > 0) {
                senkouA.push({ time: candles[i].time, value: (tenkan[tenkan.length-1].value + kijun[kijun.length-1].value) / 2 });
            }
            if (i >= 51) senkouB.push({ time: candles[i].time, value: hl(candles, i, 52) });
            if (i + 26 < candles.length) chikou.push({ time: candles[i + 26].time, value: candles[i].close });
        }
        return { tenkan, kijun, senkouA, senkouB, chikou };
    },

    _calcSupertrend(candles, period, mult) {
        const atr = this._calcATR(candles, period);
        const atrMap = {}; atr.forEach(a => atrMap[a.time] = a.value);
        const result = [];
        let trend = 1, upperBand = 0, lowerBand = 0;
        for (let i = 0; i < candles.length; i++) {
            const c = candles[i], a = atrMap[c.time];
            if (a === undefined) continue;
            const hl2 = (c.high + c.low) / 2;
            const newUpper = hl2 + mult * a, newLower = hl2 - mult * a;
            upperBand = (result.length > 0 && newUpper < upperBand) || (result.length > 0 && candles[i-1]?.close > upperBand) ? newUpper : (result.length === 0 ? newUpper : Math.min(newUpper, upperBand));
            lowerBand = (result.length > 0 && newLower > lowerBand) || (result.length > 0 && candles[i-1]?.close < lowerBand) ? newLower : (result.length === 0 ? newLower : Math.max(newLower, lowerBand));
            if (trend === 1 && c.close < lowerBand) trend = -1;
            else if (trend === -1 && c.close > upperBand) trend = 1;
            result.push({ time: c.time, value: trend === 1 ? lowerBand : upperBand, color: trend === 1 ? '#2ecc71' : '#e74c5e' });
        }
        return result;
    },

    _calcPivots(candles) {
        const pivot = [], r1 = [], s1 = [], r2 = [], s2 = [];
        for (let i = 1; i < candles.length; i++) {
            const p = candles[i-1], t = candles[i].time;
            const pp = (p.high + p.low + p.close) / 3;
            pivot.push({ time: t, value: pp });
            r1.push({ time: t, value: 2 * pp - p.low });
            s1.push({ time: t, value: 2 * pp - p.high });
            r2.push({ time: t, value: pp + (p.high - p.low) });
            s2.push({ time: t, value: pp - (p.high - p.low) });
        }
        return { pivot, r1, s1, r2, s2 };
    },

    _calcVWAP(candles) {
        const result = [];
        let cumPV = 0, cumV = 0;
        for (let i = 0; i < candles.length; i++) {
            const tp = (candles[i].high + candles[i].low + candles[i].close) / 3;
            const v = candles[i].volume || 1;
            cumPV += tp * v; cumV += v;
            result.push({ time: candles[i].time, value: cumPV / cumV });
        }
        return result;
    },

    _calcStochRSI(candles, period) {
        const rsi = this._calcRSI(candles, period);
        const k = [], d = [];
        const kPeriod = 14, dPeriod = 3;
        for (let i = kPeriod - 1; i < rsi.length; i++) {
            let hi = -Infinity, lo = Infinity;
            for (let j = 0; j < kPeriod; j++) { hi = Math.max(hi, rsi[i-j].value); lo = Math.min(lo, rsi[i-j].value); }
            const kVal = hi === lo ? 50 : (rsi[i].value - lo) / (hi - lo) * 100;
            k.push({ time: rsi[i].time, value: kVal });
        }
        for (let i = dPeriod - 1; i < k.length; i++) {
            let sum = 0; for (let j = 0; j < dPeriod; j++) sum += k[i-j].value;
            d.push({ time: k[i].time, value: sum / dPeriod });
        }
        return { k, d };
    },

    _calcStoch(candles, period, smooth) {
        const k = [], d = [];
        for (let i = period - 1; i < candles.length; i++) {
            let hi = -Infinity, lo = Infinity;
            for (let j = 0; j < period; j++) { hi = Math.max(hi, candles[i-j].high); lo = Math.min(lo, candles[i-j].low); }
            k.push({ time: candles[i].time, value: hi === lo ? 50 : (candles[i].close - lo) / (hi - lo) * 100 });
        }
        for (let i = smooth - 1; i < k.length; i++) {
            let sum = 0; for (let j = 0; j < smooth; j++) sum += k[i-j].value;
            d.push({ time: k[i].time, value: sum / smooth });
        }
        return { k, d };
    },

    _calcCCI(candles, period) {
        const result = [];
        for (let i = period - 1; i < candles.length; i++) {
            const tp = (candles[i].high + candles[i].low + candles[i].close) / 3;
            let sum = 0;
            for (let j = 0; j < period; j++) sum += (candles[i-j].high + candles[i-j].low + candles[i-j].close) / 3;
            const avg = sum / period;
            let meanDev = 0;
            for (let j = 0; j < period; j++) meanDev += Math.abs((candles[i-j].high + candles[i-j].low + candles[i-j].close) / 3 - avg);
            meanDev /= period;
            result.push({ time: candles[i].time, value: meanDev === 0 ? 0 : (tp - avg) / (0.015 * meanDev) });
        }
        return result;
    },

    _calcWillR(candles, period) {
        const result = [];
        for (let i = period - 1; i < candles.length; i++) {
            let hi = -Infinity, lo = Infinity;
            for (let j = 0; j < period; j++) { hi = Math.max(hi, candles[i-j].high); lo = Math.min(lo, candles[i-j].low); }
            result.push({ time: candles[i].time, value: hi === lo ? -50 : (hi - candles[i].close) / (hi - lo) * -100 });
        }
        return result;
    },

    _calcMomentum(candles, period) {
        const result = [];
        for (let i = period; i < candles.length; i++) {
            result.push({ time: candles[i].time, value: candles[i].close - candles[i - period].close });
        }
        return result;
    },

    _calcROC(candles, period) {
        const result = [];
        for (let i = period; i < candles.length; i++) {
            const prev = candles[i - period].close;
            result.push({ time: candles[i].time, value: prev === 0 ? 0 : (candles[i].close - prev) / prev * 100 });
        }
        return result;
    },

    _calcTSI(candles) {
        const result = [];
        const diffs = [];
        for (let i = 1; i < candles.length; i++) diffs.push(candles[i].close - candles[i-1].close);
        const absDiffs = diffs.map(d => Math.abs(d));
        const ema25 = this._emaRaw(diffs, 25);
        const ema13 = this._emaRaw(ema25, 13);
        const absEma25 = this._emaRaw(absDiffs, 25);
        const absEma13 = this._emaRaw(absEma25, 13);
        for (let i = 0; i < ema13.length; i++) {
            if (ema13[i] !== null && absEma13[i] !== null && absEma13[i] !== 0) {
                result.push({ time: candles[i + 1].time, value: (ema13[i] / absEma13[i]) * 100 });
            }
        }
        return result;
    },

    _calcUO(candles) {
        const result = [];
        for (let i = 1; i < candles.length; i++) {
            if (i < 28) continue;
            const bp = (j) => candles[j].close - Math.min(candles[j].low, candles[j-1].close);
            const tr = (j) => Math.max(candles[j].high, candles[j-1].close) - Math.min(candles[j].low, candles[j-1].close);
            let bp7 = 0, tr7 = 0, bp14 = 0, tr14 = 0, bp28 = 0, tr28 = 0;
            for (let j = i; j > i - 7; j--)  { bp7 += bp(j); tr7 += tr(j); }
            for (let j = i; j > i - 14; j--) { bp14 += bp(j); tr14 += tr(j); }
            for (let j = i; j > i - 28; j--) { bp28 += bp(j); tr28 += tr(j); }
            const avg7 = tr7 === 0 ? 0 : bp7 / tr7;
            const avg14 = tr14 === 0 ? 0 : bp14 / tr14;
            const avg28 = tr28 === 0 ? 0 : bp28 / tr28;
            result.push({ time: candles[i].time, value: 100 * (4 * avg7 + 2 * avg14 + avg28) / 7 });
        }
        return result;
    },

    _calcAwesome(candles) {
        const result = [];
        for (let i = 33; i < candles.length; i++) {
            let sum5 = 0, sum34 = 0;
            for (let j = 0; j < 5; j++) sum5 += (candles[i-j].high + candles[i-j].low) / 2;
            for (let j = 0; j < 34; j++) sum34 += (candles[i-j].high + candles[i-j].low) / 2;
            const val = sum5 / 5 - sum34 / 34;
            result.push({ time: candles[i].time, value: val, color: val >= 0 ? 'rgba(45,212,168,0.6)' : 'rgba(231,76,94,0.6)' });
        }
        return result;
    },

    _calcPPO(candles) {
        const ema12 = this._calcMA(candles, 12, 'ema');
        const ema26 = this._calcMA(candles, 26, 'ema');
        const ema26Map = {}; ema26.forEach(e => ema26Map[e.time] = e.value);
        return ema12.filter(e => ema26Map[e.time] !== undefined)
            .map(e => ({ time: e.time, value: ema26Map[e.time] === 0 ? 0 : (e.value - ema26Map[e.time]) / ema26Map[e.time] * 100 }));
    },

    _calcCMO(candles, period) {
        const result = [];
        for (let i = period; i < candles.length; i++) {
            let up = 0, down = 0;
            for (let j = 0; j < period; j++) {
                const diff = candles[i - j].close - candles[i - j - 1].close;
                if (diff > 0) up += diff; else down -= diff;
            }
            result.push({ time: candles[i].time, value: up + down === 0 ? 0 : (up - down) / (up + down) * 100 });
        }
        return result;
    },

    _calcFisher(candles, period) {
        const result = [];
        let val = 0;
        for (let i = period - 1; i < candles.length; i++) {
            let hi = -Infinity, lo = Infinity;
            for (let j = 0; j < period; j++) { hi = Math.max(hi, candles[i-j].high); lo = Math.min(lo, candles[i-j].low); }
            const hl2 = (candles[i].high + candles[i].low) / 2;
            let x = hi === lo ? 0 : 2 * ((hl2 - lo) / (hi - lo) - 0.5);
            x = Math.max(-0.999, Math.min(0.999, 0.33 * x + 0.67 * val));
            val = x;
            result.push({ time: candles[i].time, value: 0.5 * Math.log((1 + x) / (1 - x)) });
        }
        return result;
    },

    _calcNATR(candles, period) {
        const atr = this._calcATR(candles, period);
        const result = [];
        let j = 0;
        for (let i = 0; i < candles.length && j < atr.length; i++) {
            if (candles[i].time === atr[j].time) {
                result.push({ time: candles[i].time, value: candles[i].close === 0 ? 0 : atr[j].value / candles[i].close * 100 });
                j++;
            }
        }
        return result;
    },

    _calcBBWidth(candles, period) {
        const bb = this._calcBB(candles, period);
        return bb.upper.map((u, i) => ({ time: u.time, value: bb.mid[i].value === 0 ? 0 : (u.value - bb.lower[i].value) / bb.mid[i].value * 100 }));
    },

    _calcBBPct(candles, period) {
        const bb = this._calcBB(candles, period);
        const result = [];
        let j = 0;
        for (let i = 0; i < candles.length && j < bb.upper.length; i++) {
            if (candles[i].time === bb.upper[j].time) {
                const range = bb.upper[j].value - bb.lower[j].value;
                result.push({ time: candles[i].time, value: range === 0 ? 0.5 : (candles[i].close - bb.lower[j].value) / range });
                j++;
            }
        }
        return result;
    },

    _calcStdDev(candles, period) {
        const result = [];
        for (let i = period - 1; i < candles.length; i++) {
            let sum = 0;
            for (let j = 0; j < period; j++) sum += candles[i-j].close;
            const avg = sum / period;
            let sqSum = 0;
            for (let j = 0; j < period; j++) sqSum += Math.pow(candles[i-j].close - avg, 2);
            result.push({ time: candles[i].time, value: Math.sqrt(sqSum / period) });
        }
        return result;
    },

    _calcChop(candles, period) {
        const atr = this._calcATR(candles, 1);
        const atrMap = {}; atr.forEach(a => atrMap[a.time] = a.value);
        const result = [];
        for (let i = period - 1; i < candles.length; i++) {
            let hi = -Infinity, lo = Infinity, atrSum = 0;
            for (let j = 0; j < period; j++) {
                hi = Math.max(hi, candles[i-j].high);
                lo = Math.min(lo, candles[i-j].low);
                if (atrMap[candles[i-j].time] !== undefined) atrSum += atrMap[candles[i-j].time];
            }
            const range = hi - lo;
            result.push({ time: candles[i].time, value: range === 0 ? 50 : 100 * Math.log10(atrSum / range) / Math.log10(period) });
        }
        return result;
    },

    _calcKCWidth(candles, period) {
        const kc = this._calcKC(candles, period);
        return kc.upper.map((u, i) => ({ time: u.time, value: kc.mid[i].value === 0 ? 0 : (u.value - kc.lower[i].value) / kc.mid[i].value * 100 }));
    },

    _calcOBV(candles) {
        const result = [];
        let obv = 0;
        for (let i = 0; i < candles.length; i++) {
            if (i > 0) {
                if (candles[i].close > candles[i-1].close) obv += (candles[i].volume || 0);
                else if (candles[i].close < candles[i-1].close) obv -= (candles[i].volume || 0);
            }
            result.push({ time: candles[i].time, value: obv });
        }
        return result;
    },

    _calcADOsc(candles) {
        const result = [];
        let ad = 0;
        for (let i = 0; i < candles.length; i++) {
            const hl = candles[i].high - candles[i].low;
            const mfm = hl === 0 ? 0 : ((candles[i].close - candles[i].low) - (candles[i].high - candles[i].close)) / hl;
            ad += mfm * (candles[i].volume || 0);
            result.push({ time: candles[i].time, value: ad });
        }
        return result;
    },

    _calcCMF(candles, period) {
        const result = [];
        for (let i = period - 1; i < candles.length; i++) {
            let mfv = 0, vol = 0;
            for (let j = 0; j < period; j++) {
                const c = candles[i-j], hl = c.high - c.low;
                const mfm = hl === 0 ? 0 : ((c.close - c.low) - (c.high - c.close)) / hl;
                mfv += mfm * (c.volume || 0);
                vol += (c.volume || 0);
            }
            result.push({ time: candles[i].time, value: vol === 0 ? 0 : mfv / vol });
        }
        return result;
    },

    _calcMFI(candles, period) {
        const result = [];
        for (let i = period; i < candles.length; i++) {
            let posFlow = 0, negFlow = 0;
            for (let j = 0; j < period; j++) {
                const tp = (candles[i-j].high + candles[i-j].low + candles[i-j].close) / 3;
                const prevTp = (candles[i-j-1].high + candles[i-j-1].low + candles[i-j-1].close) / 3;
                const mf = tp * (candles[i-j].volume || 0);
                if (tp > prevTp) posFlow += mf; else negFlow += mf;
            }
            const ratio = negFlow === 0 ? 100 : posFlow / negFlow;
            result.push({ time: candles[i].time, value: 100 - 100 / (1 + ratio) });
        }
        return result;
    },

    _calcEOM(candles, period) {
        const raw = [];
        for (let i = 1; i < candles.length; i++) {
            const dm = ((candles[i].high + candles[i].low) / 2) - ((candles[i-1].high + candles[i-1].low) / 2);
            const br = (candles[i].volume || 1) / (candles[i].high - candles[i].low || 1);
            raw.push({ time: candles[i].time, close: dm / br });
        }
        return this._calcMA(raw, period, 'sma');
    },

    _calcVPT(candles) {
        const result = [];
        let vpt = 0;
        for (let i = 1; i < candles.length; i++) {
            const roc = candles[i-1].close === 0 ? 0 : (candles[i].close - candles[i-1].close) / candles[i-1].close;
            vpt += roc * (candles[i].volume || 0);
            result.push({ time: candles[i].time, value: vpt });
        }
        return result;
    },

    _calcFI(candles, period) {
        const raw = [];
        for (let i = 1; i < candles.length; i++) {
            raw.push({ time: candles[i].time, close: (candles[i].close - candles[i-1].close) * (candles[i].volume || 0) });
        }
        return this._calcMA(raw, period, 'ema');
    },

    _calcNVI(candles) {
        const result = [];
        let nvi = 1000;
        for (let i = 0; i < candles.length; i++) {
            if (i > 0 && (candles[i].volume || 0) < (candles[i-1].volume || 0)) {
                nvi += nvi * (candles[i-1].close === 0 ? 0 : (candles[i].close - candles[i-1].close) / candles[i-1].close);
            }
            result.push({ time: candles[i].time, value: nvi });
        }
        return result;
    },

    _calcADX(candles, period) {
        const di = this._calcDI(candles, period);
        // ADX is smoothed DX
        const result = [];
        const diPlusMap = {}; di.plus.forEach(d => diPlusMap[d.time] = d.value);
        const dx = [];
        di.minus.forEach(d => {
            if (diPlusMap[d.time] !== undefined) {
                const sum = diPlusMap[d.time] + d.value;
                dx.push({ time: d.time, value: sum === 0 ? 0 : Math.abs(diPlusMap[d.time] - d.value) / sum * 100 });
            }
        });
        if (dx.length < period) return result;
        let adx = 0;
        for (let i = 0; i < period; i++) adx += dx[i].value;
        adx /= period;
        result.push({ time: dx[period - 1].time, value: adx });
        for (let i = period; i < dx.length; i++) {
            adx = (adx * (period - 1) + dx[i].value) / period;
            result.push({ time: dx[i].time, value: adx });
        }
        return result;
    },

    _calcDI(candles, period) {
        const plus = [], minus = [];
        const pdm = [], ndm = [], tr = [];
        for (let i = 1; i < candles.length; i++) {
            const upMove = candles[i].high - candles[i-1].high;
            const downMove = candles[i-1].low - candles[i].low;
            pdm.push(upMove > downMove && upMove > 0 ? upMove : 0);
            ndm.push(downMove > upMove && downMove > 0 ? downMove : 0);
            tr.push(Math.max(candles[i].high - candles[i].low, Math.abs(candles[i].high - candles[i-1].close), Math.abs(candles[i].low - candles[i-1].close)));
        }
        let smoothPdm = 0, smoothNdm = 0, smoothTr = 0;
        for (let i = 0; i < period; i++) { smoothPdm += pdm[i]; smoothNdm += ndm[i]; smoothTr += tr[i]; }
        const t = candles[period].time;
        plus.push({ time: t, value: smoothTr === 0 ? 0 : smoothPdm / smoothTr * 100 });
        minus.push({ time: t, value: smoothTr === 0 ? 0 : smoothNdm / smoothTr * 100 });
        for (let i = period; i < pdm.length; i++) {
            smoothPdm = smoothPdm - smoothPdm / period + pdm[i];
            smoothNdm = smoothNdm - smoothNdm / period + ndm[i];
            smoothTr = smoothTr - smoothTr / period + tr[i];
            plus.push({ time: candles[i + 1].time, value: smoothTr === 0 ? 0 : smoothPdm / smoothTr * 100 });
            minus.push({ time: candles[i + 1].time, value: smoothTr === 0 ? 0 : smoothNdm / smoothTr * 100 });
        }
        return { plus, minus };
    },

    _calcAroon(candles, period) {
        const up = [], down = [];
        for (let i = period; i < candles.length; i++) {
            let hiIdx = 0, loIdx = 0;
            for (let j = 0; j <= period; j++) {
                if (candles[i - j].high >= candles[i - hiIdx].high) hiIdx = j;
                if (candles[i - j].low <= candles[i - loIdx].low) loIdx = j;
            }
            up.push({ time: candles[i].time, value: (period - hiIdx) / period * 100 });
            down.push({ time: candles[i].time, value: (period - loIdx) / period * 100 });
        }
        return { up, down };
    },

    _calcAroonOsc(candles, period) {
        const ar = this._calcAroon(candles, period);
        return ar.up.map((u, i) => ({ time: u.time, value: u.value - ar.down[i].value }));
    },

    _calcVortex(candles, period) {
        const plus = [], minus = [];
        for (let i = period; i < candles.length; i++) {
            let vmPlus = 0, vmMinus = 0, trSum = 0;
            for (let j = 0; j < period; j++) {
                const idx = i - j;
                vmPlus += Math.abs(candles[idx].high - candles[idx - 1].low);
                vmMinus += Math.abs(candles[idx].low - candles[idx - 1].high);
                trSum += Math.max(candles[idx].high - candles[idx].low, Math.abs(candles[idx].high - candles[idx-1].close), Math.abs(candles[idx].low - candles[idx-1].close));
            }
            plus.push({ time: candles[i].time, value: trSum === 0 ? 0 : vmPlus / trSum });
            minus.push({ time: candles[i].time, value: trSum === 0 ? 0 : vmMinus / trSum });
        }
        return { plus, minus };
    },

    _calcDPO(candles, period) {
        const result = [];
        const shift = Math.floor(period / 2) + 1;
        const sma = this._calcMA(candles, period, 'sma');
        const smaMap = {}; sma.forEach(s => smaMap[s.time] = s.value);
        for (let i = shift; i < candles.length; i++) {
            const smaTime = candles[i - shift]?.time;
            if (smaMap[candles[i].time] !== undefined) {
                result.push({ time: candles[i].time, value: candles[i].close - (smaMap[candles[i].time] || candles[i].close) });
            }
        }
        return result;
    },

    _calcTRIX(candles, period) {
        const e1 = this._calcMA(candles, period, 'ema');
        const e2 = this._calcMA(e1.map(e => ({ time: e.time, close: e.value })), period, 'ema');
        const e3 = this._calcMA(e2.map(e => ({ time: e.time, close: e.value })), period, 'ema');
        const result = [];
        for (let i = 1; i < e3.length; i++) {
            result.push({ time: e3[i].time, value: e3[i-1].value === 0 ? 0 : (e3[i].value - e3[i-1].value) / e3[i-1].value * 10000 });
        }
        return result;
    },

    _calcMass(candles, period) {
        const hl = candles.map(c => ({ time: c.time, close: c.high - c.low }));
        const ema9 = this._calcMA(hl, 9, 'ema');
        const ema9_2 = this._calcMA(ema9.map(e => ({ time: e.time, close: e.value })), 9, 'ema');
        const ratioMap = {}; ema9_2.forEach(e => ratioMap[e.time] = e.value);
        const ratios = ema9.filter(e => ratioMap[e.time] !== undefined && ratioMap[e.time] !== 0)
            .map(e => ({ time: e.time, value: e.value / ratioMap[e.time] }));
        const result = [];
        for (let i = period - 1; i < ratios.length; i++) {
            let sum = 0;
            for (let j = 0; j < period; j++) sum += ratios[i-j].value;
            result.push({ time: ratios[i].time, value: sum });
        }
        return result;
    },

    _calcCoppock(candles) {
        const roc14 = this._calcROC(candles, 14);
        const roc11 = this._calcROC(candles, 11);
        const roc11Map = {}; roc11.forEach(r => roc11Map[r.time] = r.value);
        const combined = roc14.filter(r => roc11Map[r.time] !== undefined)
            .map(r => ({ time: r.time, close: r.value + roc11Map[r.time] }));
        return this._calcWMA(combined, 10);
    },

    destroy() {
        // Clean up indicator series
        Object.keys(this._indicators).forEach(id => {
            if (this._indicators[id]?.series) {
                if (Array.isArray(this._indicators[id].series)) {
                    this._indicators[id].series.forEach(s => { try { this.chart.removeSeries(s); } catch(e){} });
                } else {
                    try { this.chart.removeSeries(this._indicators[id].series); } catch(e){}
                }
            }
        });
        this._indicators = {};
        if (this.chart) { this.chart.remove(); this.chart = null; }
        if (this._periodChart) { try { this._periodChart.remove(); } catch(e){} this._periodChart = null; }
        if (this.refreshTimer) { clearInterval(this.refreshTimer); this.refreshTimer = null; }
        this.candleSeries = null;
        this.volumeSeries = null;
    }
};

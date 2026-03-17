/**
 * BotCrypto - Dashboard Page
 * Shows trading chart, portfolio stats, equity curve, and trade history
 */
const DashboardPage = {
    chart: null,
    candleSeries: null,
    volumeSeries: null,
    equityChart: null,
    currentPair: 'BTC/USDT',
    currentTimeframe: '5m',
    refreshTimer: null,

    render() {
        return `
        <div id="dashboardPage">
            <!-- Status Bar -->
            <div class="d-flex align-items-center justify-content-between mb-3">
                <div class="d-flex align-items-center gap-2">
                    <span class="badge ${API.connected ? 'bg-success' : 'bg-secondary'} px-3 py-2">
                        <i class="bi bi-circle-fill me-1" style="font-size:8px"></i> ${API.connected ? 'Online' : 'Offline'}
                    </span>
                    <button class="btn btn-sm btn-link text-secondary"><i class="bi bi-bar-chart"></i></button>
                    <button class="btn btn-sm btn-link text-secondary"><i class="bi bi-grid"></i></button>
                </div>
                <button class="btn btn-outline-secondary btn-sm" onclick="DashboardPage.refreshAll()">
                    <i class="bi bi-arrow-clockwise me-1"></i> Refresh
                </button>
            </div>

            <!-- Stats Cards -->
            <div class="row g-2 mb-3">
                <div class="col"><div class="card"><div class="card-body py-3 text-center">
                    <div class="stat-value" id="dStatProfit">0</div>
                    <div class="stat-label">TOTAL PROFIT</div>
                </div></div></div>
                <div class="col"><div class="card"><div class="card-body py-3 text-center">
                    <div class="stat-value" id="dStatProfitPct">0%</div>
                    <div class="stat-label">PROFIT %</div>
                </div></div></div>
                <div class="col"><div class="card"><div class="card-body py-3 text-center">
                    <div class="stat-value" id="dStatClosedTrades">0</div>
                    <div class="stat-label">CLOSED TRADES</div>
                </div></div></div>
                <div class="col"><div class="card"><div class="card-body py-3 text-center">
                    <div class="stat-value" id="dStatOpenTrades">0</div>
                    <div class="stat-label">OPEN TRADES</div>
                </div></div></div>
                <div class="col"><div class="card"><div class="card-body py-3 text-center">
                    <div class="stat-value" id="dStatWinRate">0%</div>
                    <div class="stat-label">WIN RATE</div>
                </div></div></div>
                <div class="col"><div class="card"><div class="card-body py-3 text-center">
                    <div class="stat-value" id="dStatBalance">0</div>
                    <div class="stat-label">BALANCE</div>
                </div></div></div>
            </div>

            <!-- Chart -->
            <div class="card mb-3">
                <div class="card-body">
                    ${Components.chartToolbar(
                        this.currentPair, this.currentTimeframe,
                        'DashboardPage.onPairChange()',
                        'DashboardPage.onTimeframeChange'
                    )}
                    <div class="d-flex align-items-center gap-2 mb-2">
                        <small class="text-secondary" id="dChartInfo">
                            <i class="bi bi-bar-chart"></i> ${this.currentPair}, ${this.currentTimeframe}
                        </small>
                    </div>
                    <div id="mainChart" class="chart-container" style="height:400px"></div>
                </div>
            </div>

            <!-- Bottom: Equity + Trades -->
            <div class="row g-3">
                <div class="col-lg-4">
                    <div class="card h-100">
                        <div class="card-body">
                            <h6 class="fw-semibold mb-3"><i class="bi bi-graph-up me-2 text-success"></i>Equity Curve</h6>
                            <div class="d-flex align-items-center gap-2 mb-3">
                                <i class="bi bi-gem text-warning"></i>
                                <i class="bi bi-wallet2 text-secondary"></i>
                                <span id="dashBalance" class="fw-semibold">0 USDT</span>
                            </div>
                            <div id="equityChart" style="height:180px"></div>
                            <div id="dashProfitDisplay">
                                ${Components.profitDisplay(0, 0, 0, 0)}
                            </div>
                        </div>
                    </div>
                </div>
                <div class="col-lg-8">
                    <div class="card h-100">
                        <div class="card-body">
                            <div id="dashTradesTable">
                                ${Components.tradesTable([])}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
    },

    async init() {
        // Load available pairs from API
        this.loadAvailablePairs();

        setTimeout(() => {
            this.initMainChart();
            this.initEquityChart();
            this.loadData();
        }, 100);

        // Auto-refresh every 30s
        this.refreshTimer = setInterval(() => this.loadData(), 30000);
    },

    async loadAvailablePairs() {
        try {
            if (API.connected) {
                const data = await API.getWhitelist();
                if (data && data.whitelist && data.whitelist.length > 0) {
                    const datalist = document.getElementById('pairList');
                    if (datalist) {
                        // Add whitelist pairs at the top
                        const allPairs = [...new Set([...data.whitelist, ...Components.commonPairs])];
                        datalist.innerHTML = allPairs.map(p => `<option value="${p}">`).join('');
                    }
                    // Default to first whitelist pair
                    if (!this.currentPair || this.currentPair === 'BTC/USDT') {
                        this.currentPair = data.whitelist[0];
                        const input = document.getElementById('chartPairInput');
                        if (input) input.value = this.currentPair;
                    }
                }
            }
        } catch (e) {
            console.log('Could not load pairs:', e.message);
        }
    },

    onPairChange() {
        const input = document.getElementById('chartPairInput');
        if (!input) return;
        const pair = input.value.trim().toUpperCase();
        if (!pair || !pair.includes('/')) return;
        this.currentPair = pair;
        this.updateChartInfo();
        this.reloadChartData();
    },

    onTimeframeChange(tf) {
        this.currentTimeframe = tf;
        // Update active button styling
        document.querySelectorAll('#dashboardPage .btn-group .btn').forEach(btn => {
            btn.classList.remove('btn-outline-success', 'active');
            btn.classList.add('btn-outline-secondary');
            if (btn.textContent.trim() === tf) {
                btn.classList.remove('btn-outline-secondary');
                btn.classList.add('btn-outline-success', 'active');
            }
        });
        this.updateChartInfo();
        this.reloadChartData();
    },

    updateChartInfo() {
        const info = document.getElementById('dChartInfo');
        if (info) {
            info.innerHTML = `<i class="bi bi-bar-chart"></i> ${this.currentPair}, ${this.currentTimeframe}`;
        }
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

        this.reloadChartData();
    },

    async reloadChartData() {
        if (!this.candleSeries || !this.volumeSeries) return;

        let loaded = false;

        // Try loading from API
        try {
            if (API.connected) {
                const data = await API.getPairCandles(this.currentPair, this.currentTimeframe);
                if (data && data.data && data.data.length > 0) {
                    const candles = data.data.map(c => ({
                        time: c[0] / 1000,
                        open: c[1], high: c[2], low: c[3], close: c[4]
                    }));
                    this.candleSeries.setData(candles);

                    const volumes = data.data.map(c => ({
                        time: c[0] / 1000,
                        value: c[5] || 0,
                        color: c[4] >= c[1] ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
                    }));
                    this.volumeSeries.setData(volumes);
                    loaded = true;
                }
            }
        } catch (e) {
            console.log('API chart data not available:', e.message);
        }

        // Fallback to demo data
        if (!loaded) {
            const demoData = Components.generateDemoCandles(300, this.getDemoPrice());
            this.candleSeries.setData(demoData);

            const volumes = demoData.map(c => ({
                time: c.time,
                value: Math.random() * 2000000,
                color: c.close >= c.open ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
            }));
            this.volumeSeries.setData(volumes);

            // Add demo buy/sell markers
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
    },

    getDemoPrice() {
        const prices = { 'BTC/USDT': 85000, 'ETH/USDT': 2000, 'XRP/USDT': 0.55, 'SOL/USDT': 130, 'ADA/USDT': 0.45, 'DOGE/USDT': 0.12, 'OP/USDT': 0.14, 'GRT/USDT': 0.028 };
        return prices[this.currentPair] || 1.0;
    },

    initEquityChart() {
        const container = document.getElementById('equityChart');
        if (!container) return;
        container.innerHTML = '';

        this.equityChart = Components.createChart(container, {
            rightPriceScale: { visible: false },
            timeScale: { visible: false },
            crosshair: { mode: 1 },
        });
        if (!this.equityChart) return;

        const areaSeries = this.equityChart.addAreaSeries({
            lineColor: '#2dd4a8',
            topColor: 'rgba(45, 212, 168, 0.3)',
            bottomColor: 'rgba(45, 212, 168, 0.02)',
            lineWidth: 2,
        });

        areaSeries.setData(Components.generateDemoEquity(100, 30000));
        this.equityChart.timeScale().fitContent();
    },

    async loadData() {
        try {
            if (!API.connected) {
                this.showDemoData();
                return;
            }

            // Load real data in parallel
            const [profit, openTrades, trades, balance, count] = await Promise.all([
                API.getProfit().catch(() => null),
                API.getOpenTrades().catch(() => null),
                API.getTrades(50).catch(() => null),
                API.getBalance().catch(() => null),
                API.getTradeCount().catch(() => null),
            ]);

            // Update stat cards
            if (profit) {
                this.setStat('dStatProfit', Components.formatNumber(profit.profit_all_coin || 0, 2));
                this.setStat('dStatProfitPct', Components.formatPercent(profit.profit_all_ratio_mean ? profit.profit_all_ratio_mean * 100 : profit.profit_all_percent || 0));
                const winRate = profit.winning_trades && (profit.winning_trades + profit.losing_trades) > 0
                    ? (profit.winning_trades / (profit.winning_trades + profit.losing_trades) * 100) : 0;
                this.setStat('dStatWinRate', Components.formatPercent(winRate));
                this.setStat('dStatClosedTrades', profit.closed_trade_count || profit.trade_count || 0);
            }

            if (openTrades) {
                const openCount = Array.isArray(openTrades) ? openTrades.length : 0;
                this.setStat('dStatOpenTrades', openCount);
            }
            if (count) {
                this.setStat('dStatOpenTrades', count.current || 0);
            }

            if (balance) {
                const totalBal = balance.total || 0;
                const currency = balance.symbol || balance.stake_currency || 'USDT';
                this.setStat('dStatBalance', Components.formatNumber(totalBal, 2));
                const db = document.getElementById('dashBalance');
                if (db) db.textContent = `${Components.formatNumber(totalBal, 2)} ${currency}`;
            }

            if (profit) {
                const pd = document.getElementById('dashProfitDisplay');
                if (pd) {
                    const winRate = profit.winning_trades && (profit.winning_trades + profit.losing_trades) > 0
                        ? (profit.winning_trades / (profit.winning_trades + profit.losing_trades) * 100) : 0;
                    pd.innerHTML = Components.profitDisplay(
                        profit.profit_all_coin || 0,
                        profit.profit_closed_coin || 0,
                        winRate,
                        profit.avg_profit || 0,
                        profit.stake_currency || 'USDT'
                    );
                }
            }

            // Combine open + closed trades for the table
            let allTrades = [];
            if (openTrades && Array.isArray(openTrades)) {
                allTrades = openTrades.map(t => ({ ...t, is_open: true }));
            }
            if (trades && trades.trades) {
                allTrades = [...allTrades, ...trades.trades.slice(0, 10)];
            }
            const tt = document.getElementById('dashTradesTable');
            if (tt && allTrades.length > 0) {
                tt.innerHTML = Components.tradesTable(allTrades.slice(0, 15));
            }

        } catch (e) {
            console.error('Dashboard load error:', e);
            this.showDemoData();
        }
    },

    setStat(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    },

    showDemoData() {
        const demoTrades = Components.generateDemoTrades(10);
        const tt = document.getElementById('dashTradesTable');
        if (tt) tt.innerHTML = Components.tradesTable(demoTrades);

        const pd = document.getElementById('dashProfitDisplay');
        if (pd) {
            pd.innerHTML = Components.profitDisplay(0, 10926.701, 71.43, 260.1595);
        }

        const db = document.getElementById('dashBalance');
        if (db) db.textContent = '40926.701 USDT';
    },

    refreshAll() {
        this.reloadChartData();
        this.loadData();
        App.showToast('Dashboard refreshed', 'info');
    },

    destroy() {
        if (this.chart) { this.chart.remove(); this.chart = null; }
        if (this.equityChart) { this.equityChart.remove(); this.equityChart = null; }
        if (this.refreshTimer) { clearInterval(this.refreshTimer); this.refreshTimer = null; }
        this.candleSeries = null;
        this.volumeSeries = null;
    }
};

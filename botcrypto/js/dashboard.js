/**
 * BotCrypto - Dashboard Page
 * Shows trading chart, portfolio stats, equity curve, and trade history
 * Loads real data from Freqtrade API when connected
 */
const DashboardPage = {
    chart: null,
    equityChart: null,
    candleSeries: null,
    volumeSeries: null,
    currentPair: 'XRP/USDT',
    currentTimeframe: '30m',
    refreshTimer: null,

    render() {
        return `
        <div id="dashboardPage">
            <!-- Pair/Timeframe selector -->
            <div class="card mb-3">
                <div class="card-body">
                    <div class="d-flex align-items-center justify-content-between border-bottom border-secondary pb-2 mb-2">
                        <div class="d-flex align-items-center gap-3">
                            <select class="form-select form-select-sm" style="width:150px" id="dashPairSelect"
                                onchange="DashboardPage.changePair(this.value)">
                                <option value="XRP/USDT">XRP/USDT</option>
                            </select>
                            ${Components.timeframeSelector(this.currentTimeframe, 'DashboardPage.changeTimeframe')}
                            <button class="btn btn-sm btn-link text-secondary"><i class="bi bi-activity me-1"></i> Indicators</button>
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            <button class="btn btn-sm btn-link text-secondary" onclick="DashboardPage.refreshChart()"><i class="bi bi-arrow-clockwise"></i></button>
                            <button class="btn btn-sm btn-link text-secondary"><i class="bi bi-arrows-fullscreen"></i></button>
                        </div>
                    </div>
                    <div class="d-flex align-items-center gap-2 mb-2">
                        <small class="text-secondary" id="dashChartInfo">
                            <i class="bi bi-bar-chart"></i> ${this.currentPair}, ${this.currentTimeframe}
                        </small>
                        <small class="text-secondary ms-3">Volume (20) <i class="bi bi-graph-up"></i></small>
                    </div>
                    <div id="mainChart" class="chart-container" style="height:400px"></div>
                </div>
            </div>

            <!-- Bottom Section: Stats + Trades -->
            <div class="row g-3">
                <!-- Left: Equity + Stats -->
                <div class="col-lg-4">
                    <div class="card h-100">
                        <div class="card-body">
                            <div class="d-flex align-items-center gap-2 mb-3">
                                <i class="bi bi-gem text-warning"></i>
                                <i class="bi bi-wallet2 text-secondary"></i>
                                <span id="dashBalance" class="fw-semibold">0 USDT</span>
                                <span id="dashQuote" class="text-secondary ms-2"></span>
                            </div>
                            <div id="equityChart" style="height:180px"></div>
                            <div id="dashProfitDisplay">
                                ${Components.profitDisplay(0, 0, 0, 0)}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Right: Trades Table -->
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
        setTimeout(async () => {
            await this.loadPairList();
            this.initMainChart();
            this.initEquityChart();
            await this.loadData();
            // Auto-refresh every 30 seconds
            this.refreshTimer = setInterval(() => this.loadData(), 30000);
        }, 100);
    },

    async loadPairList() {
        const select = document.getElementById('dashPairSelect');
        if (!select) return;

        try {
            if (API.connected) {
                const config = await API.getConfig();
                const whitelist = config.exchange?.pair_whitelist || [];
                if (whitelist.length > 0) {
                    select.innerHTML = whitelist.map(p =>
                        `<option value="${p}" ${p === this.currentPair ? 'selected' : ''}>${p}</option>`
                    ).join('');
                    // If current pair not in whitelist, switch to first
                    if (!whitelist.includes(this.currentPair)) {
                        this.currentPair = whitelist[0];
                        select.value = this.currentPair;
                    }
                }
            }
        } catch (e) {
            console.log('Could not load pair list:', e.message);
        }
    },

    changePair(pair) {
        this.currentPair = pair;
        this.refreshChart();
    },

    changeTimeframe(tf) {
        this.currentTimeframe = tf;
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

    async loadChartData() {
        if (!this.candleSeries) return;

        try {
            if (API.connected) {
                const data = await API.getPairCandles(this.currentPair, this.currentTimeframe, 500);
                if (data && data.columns && data.data && data.data.length > 0) {
                    const candles = API.parseCandleData(data);
                    this.candleSeries.setData(candles);

                    const volumes = candles.map(c => ({
                        time: c.time,
                        value: c.volume || 0,
                        color: c.close >= c.open ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
                    }));
                    this.volumeSeries.setData(volumes);

                    // Add signal markers from strategy
                    const signals = API.parseSignals(data);
                    if (signals.length > 0) {
                        const markers = signals.map(s => {
                            const candle = candles.find(c => c.time === s.time);
                            if (!candle) return null;
                            const isBuy = s.type === 'enter_long' || s.type === 'exit_short';
                            return {
                                time: s.time,
                                position: isBuy ? 'belowBar' : 'aboveBar',
                                color: isBuy ? '#2dd4a8' : '#e74c5e',
                                shape: 'circle',
                                text: isBuy ? 'B' : 'S',
                            };
                        }).filter(Boolean);
                        this.candleSeries.setMarkers(markers);
                    }

                    // Also add open trade markers
                    try {
                        const openTrades = await API.getOpenTrades();
                        if (Array.isArray(openTrades) && openTrades.length > 0) {
                            const tradeMarkers = [];
                            for (const t of openTrades) {
                                if (t.pair === this.currentPair && t.open_date) {
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
                                const existingMarkers = signals.length > 0 ?
                                    signals.map(s => {
                                        const isBuy = s.type === 'enter_long' || s.type === 'exit_short';
                                        return { time: s.time, position: isBuy ? 'belowBar' : 'aboveBar', color: isBuy ? '#2dd4a8' : '#e74c5e', shape: 'circle', text: isBuy ? 'B' : 'S' };
                                    }) : [];
                                const allMarkers = [...existingMarkers, ...tradeMarkers].sort((a, b) => a.time - b.time);
                                this.candleSeries.setMarkers(allMarkers);
                            }
                        }
                    } catch (e) { /* open trades markers are optional */ }

                    this.chart.timeScale().fitContent();
                    return;
                }
            }
        } catch (e) {
            console.log('Chart data load error:', e.message);
        }

        // Fallback: demo data
        const demoData = Components.generateDemoCandles(300, 0.25);
        this.candleSeries.setData(demoData);

        const volumes = demoData.map(c => ({
            time: c.time,
            value: c.volume || Math.random() * 2000000,
            color: c.close >= c.open ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
        }));
        this.volumeSeries.setData(volumes);

        // Demo buy/sell markers
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
        this.chart.timeScale().fitContent();
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

        this._equityAreaSeries = this.equityChart.addAreaSeries({
            lineColor: '#2dd4a8',
            topColor: 'rgba(45, 212, 168, 0.3)',
            bottomColor: 'rgba(45, 212, 168, 0.02)',
            lineWidth: 2,
        });

        this._equityAreaSeries.setData(Components.generateDemoEquity(100, 30000));
        this.equityChart.timeScale().fitContent();
    },

    async loadEquityData() {
        if (!this._equityAreaSeries) return;
        try {
            if (!API.connected) return;
            const daily = await API.getDaily(60);
            if (daily && daily.data && daily.data.length > 0) {
                let cumProfit = 0;
                const startBalance = daily.stake_currency_decimals ? 1000 : 1000;

                // Get starting balance from config
                let balance = 1000;
                try {
                    const config = await API.getConfig();
                    balance = config.dry_run_wallet || config.available_capital || 1000;
                } catch (e) {}

                const equityData = daily.data.map(d => {
                    cumProfit += (d.abs_profit || 0);
                    return {
                        time: Math.floor(new Date(d.date).getTime() / 1000),
                        value: balance + cumProfit,
                    };
                }).filter(d => !isNaN(d.time));

                if (equityData.length > 0) {
                    this._equityAreaSeries.setData(equityData);
                    this.equityChart.timeScale().fitContent();
                }
            }
        } catch (e) {
            console.log('Equity data error:', e.message);
        }
    },

    async loadData() {
        try {
            if (!API.connected) {
                this.showDemoData();
                return;
            }

            // Load real data in parallel
            const [profit, trades, balance, openTrades] = await Promise.all([
                API.getProfit().catch(() => null),
                API.getTrades(50).catch(() => ({ trades: [] })),
                API.getBalance().catch(() => null),
                API.getOpenTrades().catch(() => []),
            ]);

            // Profit display
            if (profit) {
                const pd = document.getElementById('dashProfitDisplay');
                if (pd) {
                    const totalTrades = (profit.winning_trades || 0) + (profit.losing_trades || 0);
                    const winRate = totalTrades > 0 ? (profit.winning_trades / totalTrades * 100) : 0;
                    const avgProfit = totalTrades > 0 ? (profit.profit_closed_coin || 0) / totalTrades : 0;
                    pd.innerHTML = Components.profitDisplay(
                        profit.profit_all_coin || 0,
                        profit.profit_closed_coin || 0,
                        winRate,
                        avgProfit,
                        profit.stake_currency || 'USDT'
                    );
                }
            }

            // Trades table - combine open and closed
            const allTrades = [];
            if (Array.isArray(openTrades)) {
                openTrades.forEach(t => { t.is_open = true; allTrades.push(t); });
            }
            if (trades && trades.trades) {
                trades.trades.forEach(t => { if (!t.is_open) allTrades.push(t); });
            }
            const tt = document.getElementById('dashTradesTable');
            if (tt) tt.innerHTML = Components.tradesTable(allTrades.slice(0, 20));

            // Balance display
            if (balance) {
                const db = document.getElementById('dashBalance');
                const dq = document.getElementById('dashQuote');
                if (db) db.textContent = `${Components.formatNumber(balance.total || 0, 2)} ${balance.symbol || balance.stake || 'USDT'}`;
                if (dq) dq.textContent = balance.note || '';
            }

            // Load equity chart from daily data
            this.loadEquityData();

        } catch (e) {
            console.error('Dashboard load error:', e);
            this.showDemoData();
        }
    },

    showDemoData() {
        const demoTrades = Components.generateDemoTrades(10);
        const tt = document.getElementById('dashTradesTable');
        if (tt) tt.innerHTML = Components.tradesTable(demoTrades);

        const pd = document.getElementById('dashProfitDisplay');
        if (pd) pd.innerHTML = Components.profitDisplay(0, 10926.701, 71.43, 260.1595);

        const db = document.getElementById('dashBalance');
        if (db) db.textContent = '0 XRP';
        const dq = document.getElementById('dashQuote');
        if (dq) dq.textContent = '40926.701 USDT';
    },

    destroy() {
        if (this.chart) { this.chart.remove(); this.chart = null; }
        if (this.equityChart) { this.equityChart.remove(); this.equityChart = null; }
        if (this.refreshTimer) { clearInterval(this.refreshTimer); this.refreshTimer = null; }
        this.candleSeries = null;
        this.volumeSeries = null;
        this._equityAreaSeries = null;
    }
};

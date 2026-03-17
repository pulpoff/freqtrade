/**
 * BotCrypto - Dashboard Page
 * Shows trading chart, portfolio stats, equity curve, and trade history
 */
const DashboardPage = {
    chart: null,
    equityChart: null,
    currentPair: 'XRP/USDT',
    currentTimeframe: '30m',

    render() {
        return `
        <div id="dashboardPage">
            <!-- Chart Header like botcrypto -->
            <div class="card mb-3">
                <div class="card-body">
                    ${Components.chartToolbar(this.currentPair.replace('/', ''), this.currentTimeframe)}
                    <div class="d-flex align-items-center gap-2 mb-2">
                        <small class="text-secondary">
                            <i class="bi bi-bar-chart"></i> BINANCE ${this.currentPair}, ${this.currentTimeframe}, binance
                        </small>
                        <small class="text-secondary ms-3">
                            Volume (20) <i class="bi bi-graph-up"></i>
                        </small>
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
                                <span id="dashBalance" class="fw-semibold">0 ${this.currentPair.split('/')[0]}</span>
                                <span id="dashQuote" class="text-secondary ms-2">0 USDT</span>
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
        // Initialize main chart
        setTimeout(() => {
            this.initMainChart();
            this.initEquityChart();
            this.loadData();
        }, 100);
    },

    initMainChart() {
        const container = document.getElementById('mainChart');
        if (!container) return;
        container.innerHTML = '';

        this.chart = Components.createChart(container);
        if (!this.chart) return;

        const candleSeries = this.chart.addCandlestickSeries({
            upColor: '#2dd4a8',
            downColor: '#e74c5e',
            borderUpColor: '#2dd4a8',
            borderDownColor: '#e74c5e',
            wickUpColor: '#2dd4a8',
            wickDownColor: '#e74c5e',
        });

        // Add volume
        const volumeSeries = this.chart.addHistogramSeries({
            color: '#4a90d9',
            priceFormat: { type: 'volume' },
            priceScaleId: '',
        });

        this.chart.priceScale('').applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        });

        // Load data
        this.loadChartData(candleSeries, volumeSeries);
        this.chart.timeScale().fitContent();
    },

    async loadChartData(candleSeries, volumeSeries) {
        try {
            if (API.connected) {
                const data = await API.getPairCandles(this.currentPair, this.currentTimeframe);
                if (data && data.data) {
                    const candles = data.data.map(c => ({
                        time: c[0] / 1000,
                        open: c[1], high: c[2], low: c[3], close: c[4]
                    }));
                    candleSeries.setData(candles);

                    const volumes = data.data.map(c => ({
                        time: c[0] / 1000,
                        value: c[5] || 0,
                        color: c[4] >= c[1] ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
                    }));
                    volumeSeries.setData(volumes);
                    return;
                }
            }
        } catch (e) {
            console.log('Using demo chart data:', e.message);
        }

        // Demo data with buy/sell markers
        const demoData = Components.generateDemoCandles(300, 0.25);
        candleSeries.setData(demoData);

        const volumes = demoData.map(c => ({
            time: c.time,
            value: Math.random() * 2000000,
            color: c.close >= c.open ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
        }));
        volumeSeries.setData(volumes);

        // Add markers (buy/sell signals like botcrypto)
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
        candleSeries.setMarkers(markers);
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

            // Load real data
            const [profit, trades, balance] = await Promise.all([
                API.getProfit().catch(() => null),
                API.getTrades(50).catch(() => null),
                API.getBalance().catch(() => null),
            ]);

            if (profit) {
                const pd = document.getElementById('dashProfitDisplay');
                if (pd) {
                    pd.innerHTML = Components.profitDisplay(
                        profit.profit_all_coin || 0,
                        profit.profit_closed_coin || 0,
                        profit.winning_trades ? (profit.winning_trades / (profit.winning_trades + profit.losing_trades) * 100) : 0,
                        profit.avg_profit || 0,
                        profit.stake_currency || 'USDT'
                    );
                }
            }

            if (trades && trades.trades) {
                const tt = document.getElementById('dashTradesTable');
                if (tt) tt.innerHTML = Components.tradesTable(trades.trades.slice(0, 10));
            }

            if (balance) {
                const db = document.getElementById('dashBalance');
                if (db) db.textContent = `${Components.formatNumber(balance.total || 0)} ${balance.stake_currency || 'USDT'}`;
            }

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
        if (pd) {
            pd.innerHTML = Components.profitDisplay(0, 10926.701, 71.43, 260.1595);
        }

        const db = document.getElementById('dashBalance');
        if (db) db.textContent = '0 XRP';
        const dq = document.getElementById('dashQuote');
        if (dq) dq.textContent = '40926.701 USDT';
    },

    destroy() {
        if (this.chart) { this.chart.remove(); this.chart = null; }
        if (this.equityChart) { this.equityChart.remove(); this.equityChart = null; }
    }
};

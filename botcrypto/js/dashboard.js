/**
 * BotCrypto - Dashboard Page
 * Shows trading chart, portfolio stats, equity curve, and trade history
 * Loads real data from Freqtrade API when connected
 */
const DashboardPage = {
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

    render() {
        return `
        <div id="dashboardPage">
            ${API.isBacktestingMode ? `
            <div class="alert alert-info d-flex align-items-center mb-3">
                <i class="bi bi-info-circle me-2"></i>
                <span><strong>Backtesting Mode</strong> - Trade data and live balances are not available. Use the Backtesting page to run strategy tests.</span>
            </div>` : ''}

            <!-- Bot Info Bar -->
            <div class="card mb-3">
                <div class="card-body py-2">
                    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
                        <div class="d-flex align-items-center gap-3">
                            <span class="badge badge-bc" id="dashBotStatus">
                                <span class="status-dot disconnected me-1"></span> Offline
                            </span>
                            <span class="text-secondary small" id="dashStrategyName"><i class="bi bi-diagram-3 me-1"></i>-</span>
                            <span class="text-secondary small" id="dashExchangeName"><i class="bi bi-bank me-1"></i>-</span>
                            <span class="text-secondary small" id="dashTradingMode"></span>
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            <button class="btn btn-sm btn-outline-success" onclick="DashboardPage.refreshAll()">
                                <i class="bi bi-arrow-clockwise me-1"></i> Refresh
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Summary Stats Row -->
            <div class="row g-2 g-md-3 mb-3" id="dashSummaryStats">
                <div class="col-4 col-md-2">
                    <div class="card"><div class="card-body py-2 py-md-3 text-center">
                        <div class="stat-value" id="dashTotalProfit">0</div>
                        <div class="stat-label">Total Profit</div>
                    </div></div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="card"><div class="card-body py-2 py-md-3 text-center">
                        <div class="stat-value" id="dashProfitPct">0%</div>
                        <div class="stat-label">Profit %</div>
                    </div></div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="card"><div class="card-body py-2 py-md-3 text-center">
                        <div class="stat-value" id="dashClosedTrades">0</div>
                        <div class="stat-label">Closed Trades</div>
                    </div></div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="card"><div class="card-body py-2 py-md-3 text-center">
                        <div class="stat-value" id="dashOpenTrades">0</div>
                        <div class="stat-label">Open Trades</div>
                    </div></div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="card"><div class="card-body py-2 py-md-3 text-center">
                        <div class="stat-value" id="dashWinRate">0%</div>
                        <div class="stat-label">Win Rate</div>
                    </div></div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="card"><div class="card-body py-2 py-md-3 text-center">
                        <div class="stat-value" id="dashBalance">0</div>
                        <div class="stat-label">Balance</div>
                        <div class="stat-sublabel" id="dashBalanceDetail"></div>
                    </div></div>
                </div>
            </div>

            <!-- Chart -->
            <div class="card mb-3">
                <div class="card-body">
                    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2 border-bottom border-secondary pb-2 mb-2">
                        <div class="d-flex align-items-center gap-2 gap-md-3 flex-wrap">
                            <select class="form-select form-select-sm" style="width:130px" id="dashPairSelect"
                                onchange="DashboardPage.changePair(this.value)">
                                <option value="">Loading...</option>
                            </select>
                            <span id="dashTfBtns">${Components.timeframeSelector(this.currentTimeframe || '5m', 'DashboardPage.changeTimeframe')}</span>
                            <button class="btn btn-sm btn-outline-secondary" onclick="DashboardPage.showIndicatorsModal()"><i class="bi bi-activity me-1"></i> Indicators</button>
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            <button class="btn btn-sm btn-link text-secondary" onclick="DashboardPage.refreshChart()"><i class="bi bi-arrow-clockwise"></i></button>
                            <button class="btn btn-sm btn-link text-secondary"><i class="bi bi-arrows-fullscreen"></i></button>
                        </div>
                    </div>
                    <div class="d-flex align-items-center gap-2 mb-2">
                        <small class="text-secondary" id="dashChartInfo">
                            <i class="bi bi-bar-chart"></i> Loading chart data...
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
                            <h6 class="fw-semibold mb-3"><i class="bi bi-graph-up-arrow me-2 text-success"></i>Equity Curve</h6>
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
        setTimeout(async () => {
            await this.loadBotConfig();
            this.initMainChart();
            this.initEquityChart();
            await this.loadData();
            // Auto-refresh every 30 seconds
            this.refreshTimer = setInterval(() => this.loadData(), 30000);
        }, 100);
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
                    if (tfBtns) tfBtns.innerHTML = Components.timeframeSelector(this.currentTimeframe, 'DashboardPage.changeTimeframe');
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
        if (tfBtns) tfBtns.innerHTML = Components.timeframeSelector(tf, 'DashboardPage.changeTimeframe');
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
        this.candleSeries.setData(candles);
        if (this.volumeSeries && volumes) this.volumeSeries.setData(volumes);
        if (signals && signals.length > 0) {
            const markers = signals.map(s => {
                const isBuy = s.type === 'enter_long' || s.type === 'exit_short';
                return {
                    time: s.time,
                    position: isBuy ? 'belowBar' : 'aboveBar',
                    color: isBuy ? '#2dd4a8' : '#e74c5e',
                    shape: 'circle',
                    text: isBuy ? 'B' : 'S',
                };
            }).sort((a, b) => a.time - b.time);
            this.candleSeries.setMarkers(markers);
        }
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

        // Show placeholder only when not connected; real data loads in loadEquityData()
        if (!API.connected) {
            this._equityAreaSeries.setData(Components.generateDemoEquity(30, 10000));
            this.equityChart.timeScale().fitContent();
        }
    },

    async loadEquityData() {
        if (!this._equityAreaSeries) return;
        try {
            if (!API.connected) return;
            const daily = await API.getDaily(60);
            if (daily && daily.data && daily.data.length > 0) {
                let startBalance = 1000;
                if (this.botConfig) {
                    startBalance = this.botConfig.dry_run_wallet || this.botConfig.available_capital || 1000;
                }

                let cumProfit = 0;
                const equityData = daily.data.map(d => {
                    cumProfit += (d.abs_profit || 0);
                    const dateStr = d.date || '';
                    const parts = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})/);
                    let time;
                    if (parts) {
                        time = dateStr.substring(0, 10);
                    } else {
                        time = Math.floor(new Date(dateStr).getTime() / 1000);
                    }
                    return { time, value: startBalance + cumProfit };
                }).filter(d => d.time && (typeof d.time === 'string' || (!isNaN(d.time) && d.time > 0)));

                if (equityData.length > 1) {
                    this._equityAreaSeries.setData(equityData);
                    this.equityChart.timeScale().fitContent();
                }
            }
        } catch (e) {
            console.log('Equity data error:', e.message);
        }
    },

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
            const [profit, trades, balance, openTrades, count] = await Promise.all([
                API.getProfit().catch(() => null),
                API.getTrades(50).catch(() => ({ trades: [] })),
                API.getBalance().catch(() => null),
                API.getOpenTrades().catch(() => []),
                API.getTradeCount().catch(() => null),
            ]);

            // Bot info bar
            const statusBadge = el('dashBotStatus');
            if (config) {
                if (statusBadge) {
                    const state = config.state || 'running';
                    if (state === 'running') {
                        statusBadge.innerHTML = '<span class="status-dot connected me-1"></span> Running';
                        statusBadge.className = 'badge badge-bc badge-completed';
                    } else if (state === 'stopped') {
                        statusBadge.innerHTML = '<span class="status-dot disconnected me-1"></span> Stopped';
                        statusBadge.className = 'badge badge-bc badge-failed';
                    } else {
                        statusBadge.innerHTML = `<span class="status-dot me-1" style="background:var(--bc-orange)"></span> ${state}`;
                        statusBadge.className = 'badge badge-bc';
                    }
                }
                if (el('dashStrategyName')) {
                    el('dashStrategyName').innerHTML = config.strategy
                        ? `<i class="bi bi-diagram-3 me-1"></i>${config.strategy}`
                        : `<i class="bi bi-diagram-3 me-1"></i><span class="text-muted">No strategy</span>`;
                }
                if (el('dashExchangeName') && config.exchange) {
                    el('dashExchangeName').innerHTML = `<i class="bi bi-bank me-1"></i>${config.exchange}`;
                }
                if (el('dashTradingMode')) {
                    const mode = config.trading_mode || 'spot';
                    const dryRun = config.dry_run;
                    el('dashTradingMode').innerHTML = `
                        <span class="badge ${dryRun ? 'bg-warning text-dark' : 'bg-danger'} me-1">${dryRun ? 'Dry Run' : 'Live'}</span>
                        <span class="badge bg-secondary">${mode}</span>`;
                }
            } else if (statusBadge && API.connected) {
                // Connected but no config (engine/backtesting mode) - still show connected
                statusBadge.innerHTML = '<span class="status-dot connected me-1"></span> Connected';
                statusBadge.className = 'badge badge-bc badge-completed';
            }

            // Summary stat cards
            const openTradesList = Array.isArray(openTrades) ? openTrades : [];
            if (el('dashOpenTrades')) el('dashOpenTrades').textContent = openTradesList.length;

            if (profit) {
                const totalTrades = (profit.winning_trades || 0) + (profit.losing_trades || 0);
                const winRate = totalTrades > 0 ? (profit.winning_trades / totalTrades * 100) : 0;
                const avgProfit = totalTrades > 0 ? (profit.profit_closed_coin || 0) / totalTrades : 0;
                const currency = profit.stake_currency || 'USDT';

                // Show total profit (including unrealized from open trades)
                if (el('dashTotalProfit')) {
                    const val = profit.profit_all_coin || profit.profit_closed_coin || 0;
                    el('dashTotalProfit').textContent = `${val >= 0 ? '+' : ''}${Components.formatNumber(val, 2)}`;
                    el('dashTotalProfit').className = `stat-value ${val >= 0 ? 'text-profit' : 'text-loss'}`;
                }
                if (el('dashProfitPct')) {
                    const pct = profit.profit_all_percent || profit.profit_closed_percent || (profit.profit_all_ratio_sum || profit.profit_closed_ratio_mean || 0) * 100;
                    el('dashProfitPct').textContent = `${pct >= 0 ? '+' : ''}${Components.formatNumber(pct, 2)}%`;
                    el('dashProfitPct').className = `stat-value ${pct >= 0 ? 'text-profit' : 'text-loss'}`;
                }
                if (el('dashClosedTrades')) el('dashClosedTrades').textContent = totalTrades;
                if (el('dashWinRate')) {
                    el('dashWinRate').textContent = `${Components.formatNumber(winRate, 1)}%`;
                    el('dashWinRate').className = `stat-value ${winRate >= 50 ? 'text-profit' : 'text-loss'}`;
                }

                // Profit display panel
                const pd = el('dashProfitDisplay');
                if (pd) {
                    pd.innerHTML = Components.profitDisplay(
                        profit.profit_all_coin || 0,
                        profit.profit_closed_coin || 0,
                        winRate, avgProfit, currency
                    );
                }
            }

            // Trade count from API (more accurate)
            if (count && el('dashClosedTrades') && count.closed !== undefined) {
                el('dashClosedTrades').textContent = count.closed || 0;
            }
            if (count && el('dashOpenTrades') && count.current !== undefined) {
                el('dashOpenTrades').textContent = count.current || 0;
            }

            // Trades table - combine open and closed, open trades first
            const allTrades = [];
            openTradesList.forEach(t => { t.is_open = true; allTrades.push(t); });
            if (trades && trades.trades) {
                trades.trades.forEach(t => { if (!t.is_open) allTrades.push(t); });
            }
            const tt = el('dashTradesTable');
            if (tt) {
                if (allTrades.length > 0) {
                    tt.innerHTML = Components.tradesTable(allTrades.slice(0, 20));
                } else {
                    tt.innerHTML = Components.tradesTable([]);
                }
            }

            // Balance display
            if (balance) {
                const total = balance.total || balance.value || 0;
                const currency = balance.symbol || balance.stake || balance.stake_currency || 'USDT';
                if (el('dashBalance')) el('dashBalance').textContent = `${Components.formatNumber(total, 2)} ${currency}`;
                if (el('dashBalanceDetail')) {
                    const parts = [];
                    if (balance.free !== undefined) parts.push(`Free: ${Components.formatNumber(balance.free, 2)}`);
                    if (balance.used !== undefined && balance.used > 0) parts.push(`In trades: ${Components.formatNumber(balance.used, 2)}`);
                    el('dashBalanceDetail').textContent = parts.join(' | ');
                }
            }

            // Load equity chart from daily data
            this.loadEquityData();

        } catch (e) {
            console.error('Dashboard load error:', e);
            this.showDemoData();
        }
    },

    showDemoData() {
        const tt = document.getElementById('dashTradesTable');
        if (tt) {
            if (API.connected) {
                // Connected but no trade data (backtesting mode)
                tt.innerHTML = Components.tradesTable([]);
            } else {
                const demoTrades = Components.generateDemoTrades(10);
                tt.innerHTML = Components.tradesTable(demoTrades);
            }
        }

        const pd = document.getElementById('dashProfitDisplay');
        if (pd) pd.innerHTML = Components.profitDisplay(0, 0, 0, 0);
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
                            id="indSearchInput" oninput="DashboardPage._filterIndicatorModal(this.value)"
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
                                        onchange="DashboardPage.toggleIndicator('${d.id}', this.checked)">
                                </div>`;
                                }).join('')}
                            </div>`;
                        }).join('')}
                    </div>
                    <div class="modal-footer border-secondary">
                        <button class="btn btn-outline-secondary btn-sm" onclick="DashboardPage.clearAllIndicators()">Clear All</button>
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
        if (this.equityChart) { this.equityChart.remove(); this.equityChart = null; }
        if (this.refreshTimer) { clearInterval(this.refreshTimer); this.refreshTimer = null; }
        this.candleSeries = null;
        this.volumeSeries = null;
        this._equityAreaSeries = null;
    }
};

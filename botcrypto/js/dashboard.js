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
            <div class="row g-3 mb-3" id="dashSummaryStats">
                <div class="col-md-2">
                    <div class="card"><div class="card-body py-3 text-center">
                        <div class="stat-value" id="dashTotalProfit">0</div>
                        <div class="stat-label">Total Profit</div>
                    </div></div>
                </div>
                <div class="col-md-2">
                    <div class="card"><div class="card-body py-3 text-center">
                        <div class="stat-value" id="dashProfitPct">0%</div>
                        <div class="stat-label">Profit %</div>
                    </div></div>
                </div>
                <div class="col-md-2">
                    <div class="card"><div class="card-body py-3 text-center">
                        <div class="stat-value" id="dashClosedTrades">0</div>
                        <div class="stat-label">Closed Trades</div>
                    </div></div>
                </div>
                <div class="col-md-2">
                    <div class="card"><div class="card-body py-3 text-center">
                        <div class="stat-value" id="dashOpenTrades">0</div>
                        <div class="stat-label">Open Trades</div>
                    </div></div>
                </div>
                <div class="col-md-2">
                    <div class="card"><div class="card-body py-3 text-center">
                        <div class="stat-value" id="dashWinRate">0%</div>
                        <div class="stat-label">Win Rate</div>
                    </div></div>
                </div>
                <div class="col-md-2">
                    <div class="card"><div class="card-body py-3 text-center">
                        <div class="stat-value" id="dashBalance">0</div>
                        <div class="stat-label">Balance</div>
                        <div class="stat-sublabel" id="dashBalanceDetail"></div>
                    </div></div>
                </div>
            </div>

            <!-- Chart -->
            <div class="card mb-3">
                <div class="card-body">
                    <div class="d-flex align-items-center justify-content-between border-bottom border-secondary pb-2 mb-2">
                        <div class="d-flex align-items-center gap-3">
                            <select class="form-select form-select-sm" style="width:150px" id="dashPairSelect"
                                onchange="DashboardPage.changePair(this.value)">
                                <option value="">Loading...</option>
                            </select>
                            <span id="dashTfBtns">${Components.timeframeSelector(this.currentTimeframe || '5m', 'DashboardPage.changeTimeframe')}</span>
                            <button class="btn btn-sm btn-link text-secondary"><i class="bi bi-activity me-1"></i> Indicators</button>
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
        this.refreshChart();
    },

    changeTimeframe(tf) {
        this.currentTimeframe = tf;
        const tfBtns = document.getElementById('dashTfBtns');
        if (tfBtns) tfBtns.innerHTML = Components.timeframeSelector(tf, 'DashboardPage.changeTimeframe');
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
        if (!this.candleSeries || !candles || candles.length === 0) return;
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
            this.chart.timeScale().fitContent();
            loaded = true;

            // Add open trade markers on top of cached data
            this._addTradeMarkers(pair);
            return;
        }

        try {
            if (API.connected && pair) {
                if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair}, ${tf} - Loading...`;

                const limit = this._candleLimits[tf] || 2000;
                let candles = null;
                let signals = [];

                // Try 1: pair_candles (strategy-analyzed data)
                try {
                    const data = await API.getPairCandles(pair, tf, limit);
                    if (data && data.columns && data.data && data.data.length > 0) {
                        candles = API.parseCandleData(data);
                        signals = API.parseSignals(data);
                    }
                } catch (e) {
                    console.log('pair_candles failed:', e.message);
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

                    this.chart.timeScale().fitContent();
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
                if (el('dashStrategyName') && config.strategy) {
                    el('dashStrategyName').innerHTML = `<i class="bi bi-diagram-3 me-1"></i>${config.strategy}`;
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
                // Connected but no config (backtesting mode) - still show connected
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

    destroy() {
        if (this.chart) { this.chart.remove(); this.chart = null; }
        if (this.equityChart) { this.equityChart.remove(); this.equityChart = null; }
        if (this.refreshTimer) { clearInterval(this.refreshTimer); this.refreshTimer = null; }
        this.candleSeries = null;
        this.volumeSeries = null;
        this._equityAreaSeries = null;
    }
};

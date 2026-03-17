/**
 * BotCrypto - Backtesting Page
 * Run backtests with date selection, auto data download, and progress tracking
 */
const BacktestingPage = {
    chart: null,
    isRunning: false,
    pollTimer: null,
    currentResult: null,
    strategies: [],
    availablePairs: [],

    render() {
        return `
        <div id="backtestingPage">
            <!-- Config Section -->
            <div class="card mb-3">
                <div class="card-body">
                    <h5 class="fw-semibold mb-3"><i class="bi bi-clock-history me-2 text-success"></i>Run Backtest</h5>

                    <div class="row g-3">
                        <!-- Strategy Selection -->
                        <div class="col-md-4">
                            <label class="form-label small text-secondary">Strategy</label>
                            <div class="input-group">
                                <select class="form-select" id="btStrategy">
                                    <option value="">-- Select Strategy --</option>
                                </select>
                                <button class="btn btn-outline-secondary" onclick="BacktestingPage.loadPyFile()" title="Load .py file">
                                    <i class="bi bi-file-earmark-code"></i>
                                </button>
                            </div>
                            <input type="file" id="btFileInput" accept=".py" style="display:none"
                                onchange="BacktestingPage.onFileSelected(event)">
                            <small class="text-secondary mt-1 d-block" id="btStrategyInfo"></small>
                        </div>

                        <!-- Pair Filter -->
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">Pair Filter</label>
                            <select class="form-select" id="btPair">
                                <option value="" selected>All (from config)</option>
                                <option value="BTC/USDT">BTC/USDT</option>
                                <option value="ETH/USDT">ETH/USDT</option>
                                <option value="XRP/USDT">XRP/USDT</option>
                                <option value="SOL/USDT">SOL/USDT</option>
                                <option value="ADA/USDT">ADA/USDT</option>
                                <option value="DOGE/USDT">DOGE/USDT</option>
                                <option value="OP/USDT">OP/USDT</option>
                                <option value="GRT/USDT">GRT/USDT</option>
                            </select>
                        </div>

                        <!-- Timeframe -->
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">Timeframe</label>
                            <select class="form-select" id="btTimeframe">
                                <option value="" selected>Strategy default</option>
                                <option value="1m">1m</option>
                                <option value="5m">5m</option>
                                <option value="15m">15m</option>
                                <option value="30m">30m</option>
                                <option value="1h">1h</option>
                                <option value="4h">4h</option>
                                <option value="1d">1d</option>
                            </select>
                        </div>

                        <!-- Date Range -->
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">Start Date</label>
                            <input type="date" class="form-control" id="btStartDate">
                        </div>
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">End Date</label>
                            <input type="date" class="form-control" id="btEndDate">
                        </div>
                    </div>

                    <div class="row g-3 mt-1">
                        <!-- Stake Amount -->
                        <div class="col-md-3">
                            <label class="form-label small text-secondary">Initial Wallet (Dry Run)</label>
                            <div class="input-group">
                                <input type="number" class="form-control" id="btWallet" value="1000">
                                <span class="input-group-text">USDT</span>
                            </div>
                        </div>

                        <!-- Stake per trade -->
                        <div class="col-md-3">
                            <label class="form-label small text-secondary">Stake Amount</label>
                            <div class="input-group">
                                <input type="text" class="form-control" id="btStakeAmount" value="unlimited">
                            </div>
                        </div>

                        <!-- Max Open Trades -->
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">Max Open Trades</label>
                            <input type="number" class="form-control" id="btMaxTrades" value="3">
                        </div>

                        <!-- Enable Protections -->
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">Protections</label>
                            <div class="form-check form-switch mt-2">
                                <input type="checkbox" class="form-check-input" id="btProtections">
                                <label class="form-check-label" for="btProtections">Enable</label>
                            </div>
                        </div>

                        <!-- Run Button -->
                        <div class="col-md-2 d-flex align-items-end">
                            <button class="btn btn-success w-100 fw-semibold" id="btRunBtn" onclick="BacktestingPage.runBacktest()">
                                <i class="bi bi-play-fill me-1"></i> Run Backtest
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Progress Section -->
            <div class="card mb-3 d-none" id="btProgressCard">
                <div class="card-body">
                    <div class="d-flex align-items-center justify-content-between mb-2">
                        <div class="d-flex align-items-center gap-2">
                            <div class="spinner-border spinner-border-sm text-success" id="btSpinner"></div>
                            <span class="fw-semibold" id="btProgressLabel">Preparing backtest...</span>
                        </div>
                        <button class="btn btn-outline-danger btn-sm" onclick="BacktestingPage.abortBacktest()">
                            <i class="bi bi-x-circle me-1"></i> Abort
                        </button>
                    </div>
                    <div class="progress mb-2" style="height: 8px;">
                        <div class="progress-bar bg-success" id="btProgressBar" style="width: 0%"></div>
                    </div>
                    <div class="d-flex justify-content-between">
                        <small class="text-secondary" id="btProgressDetail">Initializing...</small>
                        <small class="text-secondary" id="btProgressPercent">0%</small>
                    </div>
                </div>
            </div>

            <!-- Results Section -->
            <div id="btResults" class="d-none">
                <!-- Results Header (botcrypto style) -->
                <div class="card mb-3" id="btResultsHeader"></div>

                <!-- Chart -->
                <div class="card mb-3">
                    <div class="card-body">
                        <div id="btChartToolbar"></div>
                        <div id="btChart" class="chart-container" style="height:400px"></div>
                    </div>
                </div>

                <!-- Bottom: Stats + Trades -->
                <div class="row g-3">
                    <div class="col-lg-4">
                        <div class="card h-100">
                            <div class="card-body">
                                <div class="d-flex align-items-center gap-2 mb-3" id="btBalanceDisplay">
                                    <i class="bi bi-gem text-warning"></i>
                                    <span class="fw-semibold">0 USDT</span>
                                </div>
                                <div id="btEquityChart" style="height:180px"></div>
                                <div id="btProfitDisplay"></div>
                            </div>
                        </div>
                    </div>
                    <div class="col-lg-8">
                        <div class="card h-100">
                            <div class="card-body" id="btTradesTable"></div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Backtest History -->
            <div class="card mt-3">
                <div class="card-header d-flex align-items-center justify-content-between">
                    <h6 class="mb-0"><i class="bi bi-clock-history me-2"></i>Backtest History</h6>
                    <button class="btn btn-outline-secondary btn-sm" onclick="BacktestingPage.loadHistory()">
                        <i class="bi bi-arrow-clockwise me-1"></i> Refresh
                    </button>
                </div>
                <div class="card-body" id="btHistory">
                    <div class="text-center text-secondary py-3">
                        <small>Connect to Freqtrade to see backtest history</small>
                    </div>
                </div>
            </div>
        </div>`;
    },

    async init() {
        // Set default dates: last 7 days
        const endDate = new Date();
        const startDate = new Date();
        startDate.setDate(startDate.getDate() - 7);
        const btStart = document.getElementById('btStartDate');
        const btEnd = document.getElementById('btEndDate');
        if (btStart) btStart.value = startDate.toISOString().split('T')[0];
        if (btEnd) btEnd.value = endDate.toISOString().split('T')[0];

        await this.loadStrategies();
        this.loadHistory();
    },

    async loadStrategies() {
        const select = document.getElementById('btStrategy');
        if (!select) return;

        try {
            if (API.connected) {
                const data = await API.getStrategies();
                if (data && data.strategies) {
                    this.strategies = data.strategies;
                    data.strategies.forEach(s => {
                        const opt = document.createElement('option');
                        opt.value = s;
                        opt.textContent = s;
                        select.appendChild(opt);
                    });
                }
            }
        } catch (e) {
            console.log('Could not load strategies:', e.message);
        }

        // Also add strategies from visual builder
        const savedStrategies = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
        savedStrategies.forEach(s => {
            const opt = document.createElement('option');
            opt.value = `visual:${s.name}`;
            opt.textContent = `[Visual] ${s.name}`;
            select.appendChild(opt);
        });
    },

    loadPyFile() {
        document.getElementById('btFileInput').click();
    },

    async onFileSelected(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            const content = e.target.result;
            // Extract class name
            const match = content.match(/class\s+(\w+)\s*\(IStrategy\)/);
            const stratName = match ? match[1] : file.name.replace('.py', '');

            // Store in local storage for reference
            localStorage.setItem(`bc_py_strategy_${stratName}`, content);

            // Add to dropdown
            const select = document.getElementById('btStrategy');
            const opt = document.createElement('option');
            opt.value = stratName;
            opt.textContent = `[File] ${stratName}`;
            opt.selected = true;
            select.appendChild(opt);

            document.getElementById('btStrategyInfo').textContent = `Loaded: ${file.name} (${stratName})`;
            App.showToast(`Strategy loaded: ${stratName}`, 'success');
        };
        reader.readAsText(file);
    },

    async runBacktest() {
        const strategy = document.getElementById('btStrategy').value;
        if (!strategy) {
            App.showToast('Please select a strategy', 'warning');
            return;
        }

        const timeframe = document.getElementById('btTimeframe').value;
        const startDate = document.getElementById('btStartDate').value.replace(/-/g, '');
        const endDate = document.getElementById('btEndDate').value.replace(/-/g, '');
        const timerange = `${startDate}-${endDate}`;
        const wallet = parseFloat(document.getElementById('btWallet').value) || 1000;
        const stakeAmount = document.getElementById('btStakeAmount').value;
        const maxTrades = parseInt(document.getElementById('btMaxTrades').value) || 3;
        const protections = document.getElementById('btProtections').checked;
        const pair = document.getElementById('btPair').value;

        // Show progress
        this.showProgress('Preparing backtest...');
        this.isRunning = true;

        try {
            if (!API.connected) {
                // Demo mode
                this.showProgress('Running demo backtest...');
                await this.simulateDemoBacktest(strategy, pair, timeframe, timerange);
                return;
            }

            // Step 1: Check if data exists, download if needed
            this.updateProgress(5, 'Checking available data...');

            try {
                const availablePairs = await API.getAvailablePairs(timeframe);
                const hasPair = availablePairs.pairs && availablePairs.pairs.some(p => p.includes(pair.replace('/', '_')));

                if (!hasPair) {
                    this.updateProgress(10, `Downloading ${pair} data for ${timeframe}...`);
                    await this.downloadData(pair, timeframe, startDate, endDate);
                }
            } catch (e) {
                console.log('Data check skipped:', e.message);
            }

            // Step 2: Start backtest
            this.updateProgress(20, 'Starting backtest...');

            const strategyName = strategy.startsWith('visual:') ? strategy.replace('visual:', '') : strategy;

            const btConfig = {
                strategy: strategyName,
                timerange: timerange,
                max_open_trades: maxTrades,
                stake_amount: stakeAmount === 'unlimited' ? 'unlimited' : parseFloat(stakeAmount),
                enable_protections: protections,
                dry_run_wallet: wallet,
            };
            // Only set timeframe if explicitly selected (otherwise use strategy default)
            if (timeframe) btConfig.timeframe = timeframe;

            await API.resetBacktest().catch(() => {});
            await API.startBacktest(btConfig);

            // Step 3: Poll for progress
            this.pollBacktest();

        } catch (e) {
            this.hideProgress();
            App.showToast(`Backtest error: ${e.message}`, 'error');
            this.isRunning = false;
        }
    },

    async downloadData(pair, timeframe, startDate, endDate) {
        try {
            const formatted = `${startDate}-${endDate}`;
            await API.downloadData({
                pairs: [pair],
                timeframes: [timeframe],
                timerange: formatted,
                erase: false,
            });

            // Poll for download completion
            let attempts = 0;
            while (attempts < 60) {
                await new Promise(r => setTimeout(r, 2000));
                attempts++;

                try {
                    const jobs = await API.getBackgroundJobs();
                    const downloadJob = jobs.find(j => j.job_category === 'download_data');
                    if (!downloadJob || !downloadJob.running) break;

                    const progress = Math.min(15, 10 + (downloadJob.progress || 0) * 5);
                    this.updateProgress(progress, `Downloading data... ${Math.round((downloadJob.progress || 0) * 100)}%`);
                } catch { break; }
            }

            this.updateProgress(18, 'Data download complete');
        } catch (e) {
            console.log('Data download issue:', e.message);
        }
    },

    async pollBacktest() {
        if (!this.isRunning) return;

        try {
            const status = await API.getBacktestStatus();

            if (status.running) {
                const progress = 20 + (status.progress || 0) * 70;
                const step = status.step || 'Processing...';
                this.updateProgress(progress, step);

                // Show sub-progress if available
                if (status.progress_tasks) {
                    const tasks = Object.values(status.progress_tasks);
                    if (tasks.length > 0) {
                        const task = tasks[0];
                        const detail = task.description || `${task.progress || 0}/${task.total || '?'}`;
                        document.getElementById('btProgressDetail').textContent = detail;
                    }
                }

                this.pollTimer = setTimeout(() => this.pollBacktest(), 1000);
            } else if (status.status === 'ended' || status.backtest_result) {
                this.updateProgress(95, 'Processing results...');
                this.isRunning = false;

                // Display results
                setTimeout(() => {
                    this.currentResult = status.backtest_result || status;
                    this.updateProgress(100, 'Complete!');
                    setTimeout(() => {
                        this.hideProgress();
                        this.displayResults(this.currentResult);
                    }, 500);
                }, 200);
            } else if (status.status === 'error') {
                this.hideProgress();
                this.isRunning = false;
                App.showToast(`Backtest error: ${status.error || 'Unknown error'}`, 'error');
            } else {
                this.pollTimer = setTimeout(() => this.pollBacktest(), 1500);
            }
        } catch (e) {
            this.hideProgress();
            this.isRunning = false;
            App.showToast(`Polling error: ${e.message}`, 'error');
        }
    },

    async abortBacktest() {
        try {
            if (API.connected) await API.abortBacktest();
            this.isRunning = false;
            if (this.pollTimer) clearTimeout(this.pollTimer);
            this.hideProgress();
            App.showToast('Backtest aborted', 'info');
        } catch (e) {
            App.showToast(`Abort error: ${e.message}`, 'error');
        }
    },

    // ========== DEMO BACKTEST ==========
    async simulateDemoBacktest(strategy, pair, timeframe, timerange) {
        const steps = [
            { progress: 10, label: 'Loading strategy...' },
            { progress: 20, label: 'Checking data availability...' },
            { progress: 30, label: 'Loading historical data...' },
            { progress: 50, label: 'Computing indicators...' },
            { progress: 65, label: 'Running backtest engine...' },
            { progress: 80, label: 'Processing trades...' },
            { progress: 90, label: 'Generating results...' },
            { progress: 100, label: 'Complete!' },
        ];

        for (const step of steps) {
            if (!this.isRunning) return;
            this.updateProgress(step.progress, step.label);
            await new Promise(r => setTimeout(r, 400 + Math.random() * 300));
        }

        this.isRunning = false;
        setTimeout(() => {
            this.hideProgress();
            this.displayDemoResults(strategy, pair, timeframe, timerange);
        }, 300);
    },

    displayDemoResults(strategy, pair, timeframe, timerange) {
        const startDate = timerange.substring(0, 8);
        const endDate = timerange.substring(9);
        const dateRange = `${this.formatDateStr(startDate)} - ${this.formatDateStr(endDate)}`;
        const stratName = strategy.replace('visual:', '');

        const demoTrades = Components.generateDemoTrades(42);
        const totalProfit = demoTrades.reduce((sum, t) => sum + (t.profit_abs || 0), 0);
        const winCount = demoTrades.filter(t => t.profit_abs > 0).length;

        // Show results header
        const header = document.getElementById('btResultsHeader');
        if (header) {
            header.innerHTML = `<div class="card-body">${Components.chartHeader(
                `${stratName} backtest`, stratName, dateRange, 'COMPLETED'
            )}</div>`;
        }

        // Show chart
        setTimeout(() => this.initResultChart(pair, demoTrades), 100);

        // Balance display
        const balDisplay = document.getElementById('btBalanceDisplay');
        if (balDisplay) {
            balDisplay.innerHTML = `
                <i class="bi bi-gem text-warning"></i>
                <span class="fw-semibold">0 ${pair.split('/')[0]}</span>
                <span class="text-secondary ms-2">${Components.formatNumber(40926.701)} USDT</span>`;
        }

        // Profit display
        const pd = document.getElementById('btProfitDisplay');
        if (pd) {
            pd.innerHTML = Components.profitDisplay(
                0, totalProfit, (winCount / demoTrades.length * 100), totalProfit / demoTrades.length
            );
        }

        // Equity chart
        setTimeout(() => this.initEquityChart(), 150);

        // Trades table
        const tt = document.getElementById('btTradesTable');
        if (tt) tt.innerHTML = Components.tradesTable(demoTrades);

        // Show results
        document.getElementById('btResults').classList.remove('d-none');
    },

    displayResults(result) {
        // Parse real backtest results from Freqtrade
        if (!result) return;

        const stratResult = result.strategy ? Object.values(result.strategy)[0] : result;
        const trades = stratResult.trades || [];
        const pair = trades.length > 0 ? trades[0].pair : 'Unknown';
        const stratName = stratResult.strategy_name || 'Strategy';

        const header = document.getElementById('btResultsHeader');
        if (header) {
            header.innerHTML = `<div class="card-body">${Components.chartHeader(
                `${stratName} backtest`, stratName,
                `${stratResult.backtest_start || ''} - ${stratResult.backtest_end || ''}`,
                'COMPLETED'
            )}</div>`;
        }

        // Stats
        const totalProfit = stratResult.profit_total_abs || 0;
        const winRate = stratResult.wins || 0;
        const totalTrades = trades.length;

        const pd = document.getElementById('btProfitDisplay');
        if (pd) {
            pd.innerHTML = Components.profitDisplay(
                0, totalProfit,
                totalTrades > 0 ? (winRate / totalTrades * 100) : 0,
                totalTrades > 0 ? totalProfit / totalTrades : 0,
                stratResult.stake_currency || 'USDT'
            );
        }

        // Trades
        const tt = document.getElementById('btTradesTable');
        if (tt) tt.innerHTML = Components.tradesTable(trades);

        // Charts
        setTimeout(() => {
            this.initResultChart(pair, trades);
            this.initEquityChart();
        }, 100);

        document.getElementById('btResults').classList.remove('d-none');
        App.showToast('Backtest completed!', 'success');
    },

    initResultChart(pair, trades) {
        const container = document.getElementById('btChart');
        if (!container) return;
        container.innerHTML = '';

        // Toolbar
        const tb = document.getElementById('btChartToolbar');
        if (tb) tb.innerHTML = Components.chartToolbar(pair.replace('/', ''), '30m');

        this.chart = Components.createChart(container);
        if (!this.chart) return;

        const candleSeries = this.chart.addCandlestickSeries({
            upColor: '#2dd4a8', downColor: '#e74c5e',
            borderUpColor: '#2dd4a8', borderDownColor: '#e74c5e',
            wickUpColor: '#2dd4a8', wickDownColor: '#e74c5e',
        });

        const demoCandles = Components.generateDemoCandles(400, 0.25);
        candleSeries.setData(demoCandles);

        // Add buy/sell markers from trades
        const markers = [];
        trades.forEach((t, i) => {
            const idx = Math.min(20 + i * 8, demoCandles.length - 1);
            if (idx < demoCandles.length) {
                // Buy marker
                markers.push({
                    time: demoCandles[idx].time,
                    position: 'belowBar',
                    color: '#2dd4a8',
                    shape: 'circle',
                    text: 'B',
                });
                // Sell marker
                const sellIdx = Math.min(idx + 3 + Math.floor(Math.random() * 5), demoCandles.length - 1);
                markers.push({
                    time: demoCandles[sellIdx].time,
                    position: 'aboveBar',
                    color: '#e74c5e',
                    shape: 'circle',
                    text: 'S',
                });
            }
        });
        markers.sort((a, b) => a.time - b.time);
        candleSeries.setMarkers(markers);

        // Volume
        const volumeSeries = this.chart.addHistogramSeries({
            color: '#4a90d9',
            priceFormat: { type: 'volume' },
            priceScaleId: '',
        });
        this.chart.priceScale('').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
        volumeSeries.setData(demoCandles.map(c => ({
            time: c.time, value: Math.random() * 2000000,
            color: c.close >= c.open ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
        })));

        this.chart.timeScale().fitContent();
    },

    initEquityChart() {
        const container = document.getElementById('btEquityChart');
        if (!container) return;
        container.innerHTML = '';

        const chart = Components.createChart(container, {
            rightPriceScale: { visible: false },
            timeScale: { visible: false },
        });
        if (!chart) return;

        const areaSeries = chart.addAreaSeries({
            lineColor: '#2dd4a8',
            topColor: 'rgba(45, 212, 168, 0.3)',
            bottomColor: 'rgba(45, 212, 168, 0.02)',
            lineWidth: 2,
        });
        areaSeries.setData(Components.generateDemoEquity(100, 30000));
        chart.timeScale().fitContent();
    },

    // ========== PROGRESS UI ==========
    showProgress(label) {
        const card = document.getElementById('btProgressCard');
        if (card) card.classList.remove('d-none');
        document.getElementById('btResults').classList.add('d-none');
        this.updateProgress(0, label);
        document.getElementById('btRunBtn').disabled = true;
        document.getElementById('btRunBtn').innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Running...';
    },

    updateProgress(percent, label) {
        const bar = document.getElementById('btProgressBar');
        const lbl = document.getElementById('btProgressLabel');
        const pct = document.getElementById('btProgressPercent');
        const detail = document.getElementById('btProgressDetail');
        if (bar) bar.style.width = percent + '%';
        if (lbl) lbl.textContent = label;
        if (pct) pct.textContent = Math.round(percent) + '%';
        if (detail && percent < 100) detail.textContent = label;
    },

    hideProgress() {
        const card = document.getElementById('btProgressCard');
        if (card) card.classList.add('d-none');
        const spinner = document.getElementById('btSpinner');
        if (spinner) spinner.classList.remove('d-none');
        document.getElementById('btRunBtn').disabled = false;
        document.getElementById('btRunBtn').innerHTML = '<i class="bi bi-play-fill me-1"></i> Run Backtest';
    },

    // ========== HISTORY ==========
    async loadHistory() {
        const container = document.getElementById('btHistory');
        if (!container) return;

        try {
            if (!API.connected) {
                container.innerHTML = `
                <div class="table-responsive">
                    <table class="table table-hover mb-0">
                        <thead><tr>
                            <th>Strategy</th><th>Timerange</th><th>Profit</th><th>Trades</th><th>Date</th><th></th>
                        </tr></thead>
                        <tbody>
                            <tr class="text-secondary"><td colspan="6" class="text-center py-3">Connect to Freqtrade or run a backtest to see history</td></tr>
                        </tbody>
                    </table>
                </div>`;
                return;
            }

            const history = await API.getBacktestHistory();
            if (!history || history.length === 0) {
                container.innerHTML = '<div class="text-center text-secondary py-3">No backtest history</div>';
                return;
            }

            container.innerHTML = `
            <div class="table-responsive">
                <table class="table table-hover mb-0">
                    <thead><tr>
                        <th>Strategy</th><th>Timerange</th><th>Profit</th><th>Trades</th><th>Date</th><th></th>
                    </tr></thead>
                    <tbody>
                        ${history.map(h => `
                        <tr>
                            <td class="fw-semibold">${h.strategy || '-'}</td>
                            <td>${h.timerange || '-'}</td>
                            <td class="${(h.profit_total || 0) >= 0 ? 'text-profit' : 'text-loss'}">
                                ${Components.formatPercent(h.profit_total_pct || h.profit_total)}
                            </td>
                            <td>${h.trades || '-'}</td>
                            <td class="text-secondary small">${h.backtest_start || '-'}</td>
                            <td>
                                <button class="btn btn-outline-success btn-sm" onclick="BacktestingPage.loadHistoryResult('${h.filename}', '${h.strategy}')">
                                    <i class="bi bi-eye"></i>
                                </button>
                            </td>
                        </tr>`).join('')}
                    </tbody>
                </table>
            </div>`;
        } catch (e) {
            container.innerHTML = `<div class="text-center text-secondary py-3">Error loading history: ${e.message}</div>`;
        }
    },

    async loadHistoryResult(filename, strategy) {
        try {
            const result = await API.getBacktestResult(filename, strategy);
            this.displayResults(result);
        } catch (e) {
            App.showToast(`Error loading result: ${e.message}`, 'error');
        }
    },

    formatDateStr(dateStr) {
        if (!dateStr || dateStr.length !== 8) return dateStr;
        return `${dateStr.substring(6, 8)}/${dateStr.substring(4, 6)}/${dateStr.substring(0, 4)}`;
    },

    destroy() {
        if (this.chart) { this.chart.remove(); this.chart = null; }
        if (this.pollTimer) { clearTimeout(this.pollTimer); this.pollTimer = null; }
        this.isRunning = false;
    }
};

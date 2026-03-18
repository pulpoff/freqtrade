/**
 * BotCrypto - Backtesting Page
 * Run backtests with date selection, auto data download, and progress tracking
 * Uses Freqtrade REST API for real backtest execution
 */
const BacktestingPage = {
    chart: null,
    isRunning: false,
    pollTimer: null,
    currentResult: null,
    strategies: [],
    _downloadJobId: null,
    _autoDownloaded: false,

    render() {
        return `
        <div id="backtestingPage">
            <!-- Hidden form elements needed by runBacktest() when called from strategy builder -->
            <div class="d-none">
                <select id="btStrategy"><option value="">-- Select --</option></select>
                <select id="btFreqaiModel"><option value="">None</option></select>
                <select id="btPair"></select>
                <select id="btTimeframe"><option value="" selected>Default</option></select>
                <input type="date" id="btStartDate" value="${this._defaultStartDate()}">
                <input type="date" id="btEndDate" value="${this._defaultEndDate()}">
                <input type="number" id="btWallet" value="1000">
                <input type="text" id="btStakeAmount" value="unlimited">
                <input type="number" id="btMaxTrades" value="3">
                <input type="checkbox" id="btProtections">
                <input type="file" id="btFileInput" accept=".py" style="display:none">
                <span id="btStrategyInfo"></span>
                <button id="btRunBtn">Run Backtest</button>
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

            <!-- Results Section (botcrypto-style analytics dashboard) -->
            <div id="btResults" class="d-none">
                <!-- Results Header -->
                <div class="card mb-3" id="btResultsHeader"></div>

                <!-- Top: Chart + Key Metrics (botcrypto layout) -->
                <div class="row g-3 mb-3">
                    <!-- Left: Market Chart with buy/sell markers -->
                    <div class="col-lg-8">
                        <div class="card h-100">
                            <div class="card-body">
                                <div id="btChartToolbar"></div>
                                <div id="btChart" class="chart-container" style="height:400px"></div>
                            </div>
                        </div>
                    </div>
                    <!-- Right: Key Metrics (large typography like botcrypto) -->
                    <div class="col-lg-4">
                        <div class="card h-100">
                            <div class="card-body d-flex flex-column">
                                <h6 class="fw-semibold mb-3"><i class="bi bi-bar-chart me-2 text-success"></i>Performance</h6>
                                <div id="btKeyMetrics" class="flex-grow-1"></div>
                                <div id="btBalanceDisplay" class="d-flex align-items-center gap-2 mt-3 pt-3 border-top border-secondary">
                                    <i class="bi bi-gem text-warning"></i>
                                    <span class="fw-semibold">0 USDT</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Bottom: Equity Chart + Trade Log -->
                <div class="row g-3">
                    <div class="col-lg-4">
                        <div class="card h-100">
                            <div class="card-body">
                                <h6 class="fw-semibold mb-3"><i class="bi bi-graph-up-arrow me-2 text-success"></i>Equity Curve</h6>
                                <div id="btEquityChart" style="height:180px"></div>
                                <div id="btProfitDisplay" class="mt-2"></div>
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
        await this.loadStrategies();
        // Auto-select strategy if one was requested (e.g. from strategy store)
        if (this.pendingStrategy) {
            const select = document.getElementById('btStrategy');
            if (select) {
                for (const opt of select.options) {
                    if (opt.value === this.pendingStrategy || opt.textContent === this.pendingStrategy) {
                        select.value = opt.value;
                        break;
                    }
                }
            }
            this.pendingStrategy = null;
        }
        await this.loadPairList();
        this.loadHistory();
        this.loadCurrentConfig();
    },

    async loadCurrentConfig() {
        try {
            if (!API.connected) return;
            const config = await API.getConfig();
            if (config) {
                const walletInput = document.getElementById('btWallet');
                if (walletInput && config.dry_run_wallet) {
                    walletInput.value = config.dry_run_wallet;
                }
                const maxTradesInput = document.getElementById('btMaxTrades');
                if (maxTradesInput && config.max_open_trades) {
                    maxTradesInput.value = config.max_open_trades;
                }
            }
        } catch (e) { /* optional */ }
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

        // Add imported strategies — always show them, upload in background if needed
        const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
        const apiNames = this.strategies || [];
        for (const [name, info] of Object.entries(imported)) {
            if (!apiNames.includes(name)) {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                select.appendChild(opt);
                // Try to upload in background if connected and not yet uploaded
                if (API.connected && !info.uploaded && info.content) {
                    API.request('/strategies/upload', {
                        method: 'POST',
                        body: JSON.stringify({ strategy: info.content, name })
                    }).then(() => {
                        info.uploaded = true;
                        localStorage.setItem('bc_imported_strategies', JSON.stringify(imported));
                    }).catch(e => console.log(`Upload ${name}:`, e.message));
                }
            }
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

    // Top 20 most traded futures pairs on Bybit
    _defaultPairs: [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT',
        'DOGE/USDT:USDT', 'ADA/USDT:USDT', 'AVAX/USDT:USDT', 'LINK/USDT:USDT',
        'DOT/USDT:USDT', 'MATIC/USDT:USDT', 'SUI/USDT:USDT', 'ARB/USDT:USDT',
        'OP/USDT:USDT', 'NEAR/USDT:USDT', 'APT/USDT:USDT', 'FIL/USDT:USDT',
        'ATOM/USDT:USDT', 'LTC/USDT:USDT', 'UNI/USDT:USDT', 'PEPE/USDT:USDT',
    ],

    async loadPairList() {
        const select = document.getElementById('btPair');
        if (!select) return;

        const addedPairs = new Set();
        const addPair = (p) => {
            if (addedPairs.has(p)) return;
            addedPairs.add(p);
            const opt = document.createElement('option');
            opt.value = p; opt.textContent = p;
            select.appendChild(opt);
        };

        // Add default popular pairs first
        this._defaultPairs.forEach(addPair);

        // Then append any extra pairs from config whitelist
        try {
            if (API.connected) {
                const whitelist = await API.getWhitelist();
                (whitelist?.whitelist || []).forEach(addPair);
            }
        } catch (e) {
            // defaults already added above, this is just a fallback no-op
            ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'SOL/USDT'].forEach(p => {
                const opt = document.createElement('option');
                opt.value = p;
                opt.textContent = p;
                select.appendChild(opt);
            });
        }
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
            const match = content.match(/class\s+(\w+)\s*\(IStrategy\)/);
            const stratName = match ? match[1] : file.name.replace('.py', '');

            localStorage.setItem(`bc_py_strategy_${stratName}`, content);

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

        if (!API.connected) {
            App.showToast('Connect to Freqtrade first to run backtests', 'warning');
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
        const freqaimodel = document.getElementById('btFreqaiModel')?.value || '';

        this.showProgress('Preparing backtest...');
        this.isRunning = true;

        try {
            const strategyName = strategy.startsWith('visual:') ? strategy.replace('visual:', '') : strategy;

            const btConfig = {
                strategy: strategyName,
                timerange: timerange,
                max_open_trades: maxTrades,
                stake_amount: stakeAmount === 'unlimited' ? 'unlimited' : parseFloat(stakeAmount),
                enable_protections: protections,
                dry_run_wallet: wallet,
            };
            if (timeframe) btConfig.timeframe = timeframe;
            if (freqaimodel) btConfig.freqaimodel = freqaimodel;

            this.updateProgress(5, 'Resetting previous backtest...');
            await API.resetBacktest().catch(() => {});

            // Pre-download data for selected pair
            const selectedPair = document.getElementById('btPair')?.value || 'BTC/USDT:USDT';
            btConfig.pair_whitelist = [selectedPair];
            const dlPairs = [selectedPair];
            const dlTimeframes = [timeframe || '5m'];
            for (const tf of ['1h', '4h', '1d']) {
                if (!dlTimeframes.includes(tf)) dlTimeframes.push(tf);
            }
            this.updateProgress(8, 'Checking available data...');
            try {
                const dlResult = await API.downloadMissingData({
                    pairs: dlPairs,
                    timeframes: dlTimeframes,
                    timerange: timerange,
                });
                if (dlResult && dlResult.job_id) {
                    this.updateProgress(10, 'Downloading missing data...');
                    await this._waitForDownload(dlResult.job_id);
                } else {
                    this.updateProgress(18, 'Data already available');
                }
            } catch(dlErr) {
                console.log('Pre-download skipped:', dlErr.message);
            }

            this.updateProgress(20, 'Starting backtest...');
            await API.startBacktest(btConfig);

            this.pollBacktest();

        } catch (e) {
            this.hideProgress();
            App.showToast(`Backtest error: ${e.message}`, 'error');
            this.isRunning = false;
        }
    },

    async pollBacktest() {
        if (!this.isRunning) return;

        try {
            const status = await API.getBacktestStatus();

            if (status.running) {
                const progress = 15 + (status.progress || 0) * 80;
                const step = status.step || status.status_msg || 'Processing...';
                this.updateProgress(progress, step);

                if (status.trade_count) {
                    document.getElementById('btProgressDetail').textContent =
                        `${step} - ${status.trade_count} trades found`;
                }

                this.pollTimer = setTimeout(() => this.pollBacktest(), 1500);
            } else if (status.status === 'ended' || (status.backtest_result && !status.running)) {
                this.updateProgress(95, 'Processing results...');
                this.isRunning = false;

                setTimeout(() => {
                    this.currentResult = status.backtest_result || status;
                    this.updateProgress(100, 'Complete!');
                    setTimeout(() => {
                        this.hideProgress();
                        this.displayResults(this.currentResult);
                        this.loadHistory();
                    }, 500);
                }, 200);
            } else if (status.status === 'error') {
                const errMsg = status.status_msg || 'Unknown error';
                const isDataError = errMsg.includes('No data found') || errMsg.includes('No data')
                    || errMsg.includes('Length of values') || errMsg.includes('does not match length');
                if (isDataError && !this._autoDownloaded) {
                    this.isRunning = false;
                    this._autoDownloaded = true;
                    this.updateProgress(0, 'No data found - downloading data...');
                    this.autoDownloadData();
                    return;
                }
                this.hideProgress();
                this.isRunning = false;
                if (errMsg.includes('freqai') || errMsg.includes('FreqAI') || errMsg.includes('freqaimodel')) {
                    this._showErrorModal('FreqAI Model Required',
                        'This strategy requires a FreqAI model to run. Please select a FreqAI model from the dropdown before launching the backtest.',
                        errMsg);
                } else {
                    this._showErrorModal('Backtest Error', 'The backtest failed with an error.', errMsg);
                }
            } else {
                this.pollTimer = setTimeout(() => this.pollBacktest(), 2000);
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

    // ========== AUTO DATA DOWNLOAD ==========
    async autoDownloadData() {
        try {
            const timeframe = document.getElementById('btTimeframe').value || '5m';
            const startDate = document.getElementById('btStartDate').value.replace(/-/g, '');
            const endDate = document.getElementById('btEndDate').value.replace(/-/g, '');
            const timerange = `${startDate}-${endDate}`;

            const selectedPair = document.getElementById('btPair').value || 'BTC/USDT:USDT';
            const pairs = [selectedPair];

            const timeframes = [timeframe];
            // Include common informative timeframes that strategies often need
            for (const tf of ['1h', '4h', '1d']) {
                if (!timeframes.includes(tf)) timeframes.push(tf);
            }

            this.updateProgress(5, 'Checking available data...');
            const detail = document.getElementById('btProgressDetail');
            if (detail) detail.textContent = `${pairs.join(', ')} | ${timeframes.join(', ')}`;

            const result = await API.downloadMissingData({
                pairs: pairs,
                timeframes: timeframes,
                timerange: timerange,
            });

            if (result && result.job_id) {
                this._downloadJobId = result.job_id;
                this.updateProgress(10, 'Downloading data...');
                this.pollDownload();
            } else {
                this.hideProgress();
                App.showToast('Failed to start data download', 'error');
            }
        } catch (e) {
            this.hideProgress();
            App.showToast(`Download error: ${e.message}`, 'error');
        }
    },

    async pollDownload() {
        try {
            const job = await API.getBackgroundJob(this._downloadJobId);

            if (job.running || job.status === 'pending') {
                let totalProgress = 0;
                let totalItems = 0;
                let completedItems = 0;
                let currentTask = 'Downloading...';

                if (job.progress_tasks) {
                    const tasks = Object.values(job.progress_tasks);
                    tasks.forEach(t => {
                        totalItems += (t.total || 0);
                        completedItems += (t.progress || 0);
                        if (t.progress < t.total) {
                            currentTask = t.description || 'Downloading...';
                        }
                    });
                    totalProgress = totalItems > 0 ? (completedItems / totalItems) * 100 : 0;
                }

                const pct = 10 + totalProgress * 0.7;
                this.updateProgress(pct, currentTask);

                const detail = document.getElementById('btProgressDetail');
                if (detail && totalItems > 0) {
                    detail.textContent = `${Math.round(completedItems)} / ${totalItems} tasks completed`;
                }

                this.pollTimer = setTimeout(() => this.pollDownload(), 1000);
            } else if (job.status === 'success') {
                this.updateProgress(85, 'Download complete! Starting backtest...');
                App.showToast('Data download complete', 'success');
                setTimeout(() => this.runBacktest(), 500);
            } else {
                this.hideProgress();
                const errMsg = job.error || 'Download failed';
                App.showToast(`Data download error: ${errMsg}`, 'error');
            }
        } catch (e) {
            this.hideProgress();
            App.showToast(`Download polling error: ${e.message}`, 'error');
        }
    },

    displayResults(result) {
        if (!result) return;

        console.log('Backtest result keys:', Object.keys(result));

        let stratResult;
        if (result.strategy && typeof result.strategy === 'object') {
            // Standard backtest result format: { strategy: { StrategyName: { ... } } }
            const stratValues = Object.values(result.strategy);
            if (stratValues.length > 0 && typeof stratValues[0] === 'object') {
                stratResult = stratValues[0];
            }
        }

        // If strategy wrapper didn't work, check if result itself has the data
        if (!stratResult || (!stratResult.trades && stratResult.profit_total === undefined)) {
            if (result.strategy_name || result.trades || result.profit_total !== undefined) {
                stratResult = result;
            } else if (result.backtest_result) {
                // Nested backtest_result (from /backtest polling)
                return this.displayResults(result.backtest_result);
            } else {
                // Try to find strategy data in any nested key
                for (const key of Object.keys(result)) {
                    const val = result[key];
                    if (val && typeof val === 'object' && !Array.isArray(val) &&
                        (val.trades || val.profit_total !== undefined || val.strategy_name)) {
                        stratResult = val;
                        break;
                    }
                }
            }
        }

        // Use strategy_comparison for summary data if available and stratResult is sparse
        if (result.strategy_comparison && Array.isArray(result.strategy_comparison) && result.strategy_comparison.length > 0) {
            const comp = result.strategy_comparison[0];
            if (stratResult && !stratResult.profit_total && comp.profit_total !== undefined) {
                stratResult.profit_total = comp.profit_total;
                stratResult.profit_total_abs = comp.profit_total_abs || comp.profit_total_abs;
                stratResult.trades = stratResult.trades || [];
                if (!stratResult.wins && comp.wins !== undefined) stratResult.wins = comp.wins;
                if (!stratResult.losses && comp.losses !== undefined) stratResult.losses = comp.losses;
            }
        }

        if (!stratResult) {
            App.showToast('No results returned', 'warning');
            return;
        }

        const trades = stratResult.trades || [];
        const stratName = stratResult.strategy_name || Object.keys(result.strategy || {})[0] || 'Strategy';
        const dateRange = `${stratResult.backtest_start || stratResult.backtest_start_ts || ''} - ${stratResult.backtest_end || stratResult.backtest_end_ts || ''}`;
        const stakeCurrency = stratResult.stake_currency || 'USDT';

        // Results header
        const header = document.getElementById('btResultsHeader');
        if (header) {
            header.innerHTML = `<div class="card-body">${Components.chartHeader(
                `${stratName} backtest`, stratName, dateRange, 'COMPLETED'
            )}</div>`;
        }

        // Key metrics panel (botcrypto-style large typography)
        const metricsEl = document.getElementById('btKeyMetrics');
        if (metricsEl) {
            const totalProfit = stratResult.profit_total_abs || 0;
            const profitPct = (stratResult.profit_total || 0) * 100;
            const maxDrawdownPct = ((stratResult.max_drawdown_account || stratResult.max_drawdown || 0) * 100);
            const winTrades = stratResult.wins || 0;
            const lossTrades = stratResult.losses || 0;
            const totalTrades = trades.length;
            const winRate = totalTrades > 0 ? (winTrades / totalTrades * 100) : 0;
            const avgDuration = stratResult.holding_avg || stratResult.duration_avg || '-';

            metricsEl.innerHTML = `
                <div class="mb-3">
                    <div class="text-secondary small mb-1">Total Profit</div>
                    <div class="fs-3 fw-bold ${totalProfit >= 0 ? 'text-profit' : 'text-loss'}">
                        ${totalProfit >= 0 ? '+' : ''}${Components.formatNumber(totalProfit, 2)} ${stakeCurrency}
                    </div>
                </div>
                <div class="mb-3">
                    <div class="text-secondary small mb-1">ROI</div>
                    <div class="fs-4 fw-bold ${profitPct >= 0 ? 'text-profit' : 'text-loss'}">
                        ${profitPct >= 0 ? '+' : ''}${Components.formatPercent(profitPct)}
                    </div>
                </div>
                <div class="row g-3 mb-3">
                    <div class="col-6">
                        <div class="text-secondary small mb-1">Win Rate</div>
                        <div class="fs-5 fw-semibold ${winRate >= 50 ? 'text-profit' : 'text-loss'}">${Components.formatPercent(winRate)}</div>
                    </div>
                    <div class="col-6">
                        <div class="text-secondary small mb-1">Trades</div>
                        <div class="fs-5 fw-semibold">${totalTrades}</div>
                    </div>
                </div>
                <div class="row g-3 mb-3">
                    <div class="col-6">
                        <div class="text-secondary small mb-1">Wins / Losses</div>
                        <div class="fw-semibold"><span class="text-profit">${winTrades}W</span> / <span class="text-loss">${lossTrades}L</span></div>
                    </div>
                    <div class="col-6">
                        <div class="text-secondary small mb-1">Max Drawdown</div>
                        <div class="fw-semibold text-loss">${Components.formatPercent(maxDrawdownPct)}</div>
                    </div>
                </div>
                <div class="mb-2">
                    <div class="text-secondary small mb-1">Avg Trade Duration</div>
                    <div class="fw-semibold">${avgDuration}</div>
                </div>`;
        }

        // Balance display
        const balDisplay = document.getElementById('btBalanceDisplay');
        if (balDisplay) {
            balDisplay.innerHTML = `
                <i class="bi bi-gem text-warning"></i>
                <span class="fw-semibold">${Components.formatNumber(stratResult.final_balance || 0, 2)} ${stakeCurrency}</span>
                <small class="text-secondary ms-2">from ${Components.formatNumber(stratResult.starting_balance || 1000, 2)} ${stakeCurrency}</small>`;
        }

        // Profit display
        const totalProfit = stratResult.profit_total_abs || 0;
        const totalTrades = trades.length;
        const winTrades = stratResult.wins || 0;
        const winRate = totalTrades > 0 ? (winTrades / totalTrades * 100) : 0;
        const avgProfit = totalTrades > 0 ? totalProfit / totalTrades : 0;

        const pd = document.getElementById('btProfitDisplay');
        if (pd) {
            pd.innerHTML = Components.profitDisplay(
                0, totalProfit, winRate, avgProfit, stakeCurrency
            );
        }

        // Trades table (botcrypto-style with color-coded gains and status pills)
        const tt = document.getElementById('btTradesTable');
        if (tt) {
            if (trades.length > 0) {
                tt.innerHTML = `
                <div class="d-flex align-items-center justify-content-between mb-3">
                    <h6 class="fw-semibold mb-0"><i class="bi bi-arrow-left-right me-2"></i>Trades <span class="badge bg-secondary ms-1">${trades.length}</span></h6>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-secondary active" onclick="BacktestingPage._filterTrades('all', this)">All</button>
                        <button class="btn btn-outline-success" onclick="BacktestingPage._filterTrades('wins', this)">Wins</button>
                        <button class="btn btn-outline-danger" onclick="BacktestingPage._filterTrades('losses', this)">Losses</button>
                    </div>
                </div>
                <div class="table-responsive" style="max-height:400px;overflow:auto">
                    <table class="table table-hover table-sm mb-0" id="btTradesTableInner">
                        <thead class="sticky-top bg-dark"><tr>
                            <th>Gain</th><th>Pair</th><th>Action</th><th>Open</th><th>Close</th>
                            <th>Volume</th><th>Duration</th><th>Status</th>
                        </tr></thead>
                        <tbody>
                            ${trades.map((t, i) => {
                                const profitPctTrade = (t.profit_ratio || 0) * 100;
                                const isWin = profitPctTrade >= 0;
                                return `
                            <tr class="trade-row ${isWin ? 'trade-win' : 'trade-loss'}">
                                <td>
                                    <span class="fw-bold ${isWin ? 'text-profit' : 'text-loss'}" style="font-size:14px">
                                        ${isWin ? '+' : ''}${Components.formatPercent(profitPctTrade)}
                                    </span>
                                    <br><small class="${isWin ? 'text-profit' : 'text-loss'}">${(t.profit_abs || 0) >= 0 ? '+' : ''}${Components.formatNumber(t.profit_abs || 0, 2)} ${stakeCurrency}</small>
                                </td>
                                <td class="fw-semibold">${Components.cleanPairName ? Components.cleanPairName(t.pair || '-') : (t.pair || '-')}</td>
                                <td><span class="badge ${t.is_short ? 'bg-danger' : 'bg-success'} bg-opacity-75">${t.is_short ? 'Short' : 'Long'}</span></td>
                                <td>
                                    <small>${Components.formatNumber(t.open_rate, 6)}</small>
                                    <br><small class="text-secondary">${t.open_date ? new Date(t.open_date).toLocaleString() : '-'}</small>
                                </td>
                                <td>
                                    <small>${Components.formatNumber(t.close_rate, 6)}</small>
                                    <br><small class="text-secondary">${t.close_date ? new Date(t.close_date).toLocaleString() : '-'}</small>
                                </td>
                                <td class="small">${Components.formatNumber(t.stake_amount || 0, 2)}</td>
                                <td class="small">${t.trade_duration || '-'} min</td>
                                <td>
                                    <span class="badge ${isWin ? 'bg-success' : 'bg-danger'} bg-opacity-25 ${isWin ? 'text-success' : 'text-danger'}">
                                        ${t.exit_reason || t.sell_reason || 'Completed'}
                                    </span>
                                </td>
                            </tr>`;
                            }).join('')}
                        </tbody>
                    </table>
                </div>`;
            } else {
                tt.innerHTML = Components.emptyState('arrow-left-right', 'No trades', 'Backtest produced no trades');
            }
        }

        // Charts
        setTimeout(() => {
            this.initResultChart(trades, stratResult);
            this.initEquityChart(trades, stratResult);
        }, 100);

        document.getElementById('btResults').classList.remove('d-none');
        App.showToast(`Backtest completed! ${trades.length} trades`, 'success');
    },

    async initResultChart(trades, stratResult) {
        const container = document.getElementById('btChart');
        if (!container) return;
        container.innerHTML = '';

        const pairs = [...new Set(trades.map(t => t.pair).filter(Boolean))];
        const pair = pairs[0] || document.getElementById('btPair')?.value || 'BTC/USDT:USDT';
        const timeframe = stratResult.timeframe || document.getElementById('btTimeframe')?.value || '5m';

        const tb = document.getElementById('btChartToolbar');
        if (tb) {
            tb.innerHTML = `<div class="d-flex align-items-center gap-2 mb-2">
                <small class="text-secondary">Pair: ${pair}</small>
                <small class="text-secondary ms-3">Trades: ${trades.length}</small>
            </div>`;
        }

        this.chart = Components.createChart(container, {
            handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
            handleScale: { axisPressedMouseMove: false, mouseWheel: false, pinch: false },
        });
        if (!this.chart) return;

        // Fetch actual OHLCV candle data for the pair
        let candleData = [];
        try {
            const ohlcv = await API.getPairOhlcv(pair, timeframe, 3000);
            if (ohlcv && ohlcv.data && ohlcv.data.length > 0) {
                // Filter to backtest period
                const btStart = stratResult.backtest_start ? new Date(stratResult.backtest_start).getTime() / 1000 : 0;
                const btEnd = stratResult.backtest_end ? new Date(stratResult.backtest_end).getTime() / 1000 : Infinity;

                candleData = ohlcv.data
                    .map(d => ({ time: Math.floor(d[0] / 1000), open: d[1], high: d[2], low: d[3], close: d[4] }))
                    .filter(d => d.time >= btStart - 3600 && d.time <= btEnd + 3600)
                    .sort((a, b) => a.time - b.time);

                // Deduplicate
                const seen = new Set();
                candleData = candleData.filter(d => { if (seen.has(d.time)) return false; seen.add(d.time); return true; });
            }
        } catch (e) {
            console.log('Could not fetch OHLCV data:', e.message);
        }

        if (candleData.length > 0) {
            // Candlestick chart with price data
            const candleSeries = this.chart.addCandlestickSeries({
                upColor: '#2dd4a8',
                downColor: '#e74c5e',
                borderUpColor: '#2dd4a8',
                borderDownColor: '#e74c5e',
                wickUpColor: '#2dd4a8',
                wickDownColor: '#e74c5e',
            });
            candleSeries.setData(candleData);

            // Build buy/sell marker data from trades
            const tradeMarkers = [];
            trades.forEach(t => {
                const openTime = t.open_date ? Math.floor(new Date(t.open_date).getTime() / 1000) : 0;
                const closeTime = t.close_date ? Math.floor(new Date(t.close_date).getTime() / 1000) : 0;

                // Snap to nearest candle time
                const snapTo = (ts) => {
                    if (!ts) return 0;
                    let best = candleData[0]?.time || 0;
                    let bestDiff = Math.abs(ts - best);
                    for (const c of candleData) {
                        const diff = Math.abs(ts - c.time);
                        if (diff < bestDiff) { best = c.time; bestDiff = diff; }
                        if (c.time > ts + 3600) break;
                    }
                    return best;
                };

                if (openTime) {
                    const snapped = snapTo(openTime);
                    const candle = candleData.find(c => c.time === snapped);
                    tradeMarkers.push({ time: snapped, price: candle ? candle.low : (t.open_rate || 0), type: 'buy' });
                }
                if (closeTime) {
                    const snapped = snapTo(closeTime);
                    const candle = candleData.find(c => c.time === snapped);
                    tradeMarkers.push({ time: snapped, price: candle ? candle.high : (t.close_rate || 0), type: 'sell' });
                }
            });

            // Create HTML overlay markers (white letter in colored circle)
            this._tradeMarkerEls = [];
            const chartEl = container.querySelector('table') || container;
            tradeMarkers.forEach(m => {
                const el = document.createElement('div');
                const isBuy = m.type === 'buy';
                el.textContent = isBuy ? 'B' : 'S';
                Object.assign(el.style, {
                    position: 'absolute',
                    width: '22px',
                    height: '22px',
                    borderRadius: '50%',
                    background: isBuy ? '#2dd4a8' : '#e74c5e',
                    color: '#fff',
                    fontSize: '11px',
                    fontWeight: '700',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: '10',
                    pointerEvents: 'none',
                    lineHeight: '1',
                });
                container.style.position = 'relative';
                container.appendChild(el);
                this._tradeMarkerEls.push({ el, time: m.time, price: m.price, type: m.type });
            });

            // Position markers on chart and update on scroll/zoom
            const updateMarkerPositions = () => {
                const ts = this.chart.timeScale();
                this._tradeMarkerEls.forEach(({ el, time, price, type }) => {
                    const x = ts.timeToCoordinate(time);
                    const y = candleSeries.priceToCoordinate(price);
                    if (x === null || y === null || x < 0) {
                        el.style.display = 'none';
                        return;
                    }
                    el.style.display = 'flex';
                    const offset = type === 'buy' ? 8 : -30;
                    el.style.left = (x - 11) + 'px';
                    el.style.top = (y + offset) + 'px';
                });
            };
            updateMarkerPositions();
            this.chart.timeScale().subscribeVisibleLogicalRangeChange(updateMarkerPositions);
            candleSeries.subscribeDataChanged && candleSeries.subscribeDataChanged(updateMarkerPositions);

            this._candleSeries = candleSeries;
        } else {
            // Fallback: line chart from trade data if no OHLCV available
            const lineSeries = this.chart.addLineSeries({ color: '#2dd4a8', lineWidth: 2 });
            const pricePoints = [];
            trades.forEach(t => {
                if (t.open_date && t.open_rate) pricePoints.push({ time: Math.floor(new Date(t.open_date).getTime() / 1000), value: t.open_rate });
                if (t.close_date && t.close_rate) pricePoints.push({ time: Math.floor(new Date(t.close_date).getTime() / 1000), value: t.close_rate });
            });
            pricePoints.sort((a, b) => a.time - b.time);
            const seen = new Set();
            const unique = pricePoints.filter(d => { if (seen.has(d.time)) return false; seen.add(d.time); return true; });
            if (unique.length > 1) lineSeries.setData(unique);
            this._candleSeries = lineSeries;
        }

        this.chart.timeScale().fitContent();
    },

    initEquityChart(trades, stratResult) {
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

        let cumProfit = 0;
        const startBalance = stratResult.starting_balance || 1000;
        const data = trades.map(t => {
            cumProfit += (t.profit_abs || 0);
            const time = t.close_date ? Math.floor(new Date(t.close_date).getTime() / 1000) : 0;
            return { time, value: startBalance + cumProfit };
        }).filter(d => d.time > 0).sort((a, b) => a.time - b.time);

        const unique = [];
        const seen = new Set();
        data.forEach(d => {
            if (!seen.has(d.time)) {
                seen.add(d.time);
                unique.push(d);
            }
        });

        if (unique.length > 1) {
            areaSeries.setData(unique);
            chart.timeScale().fitContent();
        }
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
                            <th>Strategy</th><th>Pair</th><th>Timerange</th><th>Timeframe</th><th>Trades</th><th>Profit</th><th>FreqAI</th><th>Date</th><th></th>
                        </tr></thead>
                        <tbody>
                            <tr class="text-secondary"><td colspan="9" class="text-center py-3">Connect to Freqtrade to see backtest history</td></tr>
                        </tbody>
                    </table>
                </div>`;
                return;
            }

            const history = await API.getBacktestHistory();
            if (!history || !Array.isArray(history) || history.length === 0) {
                container.innerHTML = '<div class="text-center text-secondary py-3">No backtest history</div>';
                return;
            }

            const fmtTs = (ts) => {
                if (!ts) return '-';
                const d = new Date(ts * 1000);
                return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
            };
            const fmtRunDate = (ts) => {
                if (!ts) return '-';
                const d = new Date(ts * 1000);
                return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) + ' ' +
                       d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
            };

            container.innerHTML = `
            <div class="table-responsive">
                <table class="table table-hover table-sm mb-0">
                    <thead><tr>
                        <th>Strategy</th><th>Pair</th><th>Date Range</th><th>Timeframe</th><th>Trades</th><th>Profit</th><th>FreqAI</th><th>Run Date</th><th></th>
                    </tr></thead>
                    <tbody>
                        ${history.map((h, idx) => {
                            const dateRange = (h.backtest_start_ts && h.backtest_end_ts)
                                ? `${fmtTs(h.backtest_start_ts)} - ${fmtTs(h.backtest_end_ts)}`
                                : '-';
                            return `
                        <tr>
                            <td class="fw-semibold">${h.strategy || '-'}</td>
                            <td class="small" id="btHistPair_${idx}"><span class="text-secondary">...</span></td>
                            <td class="small">${dateRange}</td>
                            <td class="small">${h.timeframe || '-'}</td>
                            <td class="small" id="btHistTrades_${idx}"><span class="text-secondary">...</span></td>
                            <td class="small" id="btHistProfit_${idx}"><span class="text-secondary">...</span></td>
                            <td class="small" id="btHistFreqai_${idx}"><span class="text-secondary">...</span></td>
                            <td class="text-secondary small">${fmtRunDate(h.backtest_start_time)}</td>
                            <td class="text-end" style="white-space:nowrap">
                                <button class="btn btn-outline-success btn-sm me-1" onclick="BacktestingPage.loadHistoryResult('${h.filename || ''}', '${h.strategy || ''}')" title="View results">
                                    <i class="bi bi-eye"></i>
                                </button>
                                <button class="btn btn-outline-danger btn-sm" onclick="BacktestingPage.deleteHistoryEntry('${h.filename || ''}')" title="Delete">
                                    <i class="bi bi-trash"></i>
                                </button>
                            </td>
                        </tr>`;
                        }).join('')}
                    </tbody>
                </table>
            </div>`;

            // Fetch summary data for each history entry in the background
            history.forEach((h, idx) => {
                if (!h.filename || !h.strategy) {
                    ['Pair', 'Trades', 'Profit', 'Freqai'].forEach(col => {
                        const el = document.getElementById(`btHist${col}_${idx}`);
                        if (el) el.textContent = '-';
                    });
                    return;
                }
                API.getBacktestResult(h.filename, h.strategy).then(rawResult => {
                    // Unwrap backtest_result wrapper if present
                    const result = rawResult?.backtest_result || rawResult;
                    let sr = null;
                    if (result && result.strategy && typeof result.strategy === 'object') {
                        const vals = Object.values(result.strategy);
                        if (vals.length > 0) sr = vals[0];
                    }
                    if (!sr) sr = result;

                    // Pair
                    const pairEl = document.getElementById(`btHistPair_${idx}`);
                    if (pairEl) {
                        const trades = sr.trades || [];
                        const pairs = [...new Set(trades.map(t => t.pair))];
                        pairEl.textContent = pairs.length > 0 ? pairs.join(', ') : (sr.pairlist || '-');
                    }

                    // Trades count
                    const tradesEl = document.getElementById(`btHistTrades_${idx}`);
                    if (tradesEl) {
                        const count = (sr.trades || []).length || sr.trade_count || 0;
                        tradesEl.textContent = count;
                    }

                    // Profit
                    const profitEl = document.getElementById(`btHistProfit_${idx}`);
                    if (profitEl) {
                        const profitAbs = sr.profit_total_abs || 0;
                        const profitPct = (sr.profit_total || 0) * 100;
                        const currency = sr.stake_currency || 'USDT';
                        const color = profitAbs >= 0 ? 'text-profit' : 'text-loss';
                        profitEl.innerHTML = `<span class="${color} fw-semibold">${profitAbs >= 0 ? '+' : ''}${Components.formatNumber(profitAbs, 2)} ${currency}</span> <span class="text-secondary">(${profitPct >= 0 ? '+' : ''}${profitPct.toFixed(1)}%)</span>`;
                    }

                    // FreqAI model
                    const freqaiEl = document.getElementById(`btHistFreqai_${idx}`);
                    if (freqaiEl) {
                        const model = sr.freqai?.model || sr.freqai_model || '';
                        freqaiEl.textContent = model || '-';
                    }
                }).catch(() => {
                    ['Pair', 'Trades', 'Profit', 'Freqai'].forEach(col => {
                        const el = document.getElementById(`btHist${col}_${idx}`);
                        if (el) el.textContent = '-';
                    });
                });
            });
        } catch (e) {
            container.innerHTML = `<div class="text-center text-secondary py-3">Error loading history: ${e.message}</div>`;
        }
    },

    async deleteHistoryEntry(filename) {
        if (!filename) return;
        if (!confirm('Delete this backtest result?')) return;
        try {
            await API.deleteBacktestHistory(filename);
            App.showToast('Backtest result deleted', 'success');
            this.loadHistory();
        } catch (e) {
            App.showToast(`Delete failed: ${e.message}`, 'error');
        }
    },

    async loadHistoryResult(filename, strategy) {
        if (!filename) return;
        try {
            const result = await API.getBacktestResult(filename, strategy);
            console.log('History result raw:', result);
            this.displayResults(result);
        } catch (e) {
            App.showToast(`Error loading result: ${e.message}`, 'error');
        }
    },

    _defaultStartDate() {
        const d = new Date();
        d.setDate(d.getDate() - 7);
        return d.toISOString().slice(0, 10);
    },

    _defaultEndDate() {
        return new Date().toISOString().slice(0, 10);
    },

    /** Filter trades table by wins/losses/all */
    _filterTrades(filter, btn) {
        const table = document.getElementById('btTradesTableInner');
        if (!table) return;
        const rows = table.querySelectorAll('.trade-row');
        rows.forEach(row => {
            if (filter === 'all') row.style.display = '';
            else if (filter === 'wins') row.style.display = row.classList.contains('trade-win') ? '' : 'none';
            else if (filter === 'losses') row.style.display = row.classList.contains('trade-loss') ? '' : 'none';
        });
        // Update active button
        if (btn) {
            btn.closest('.btn-group').querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        }
    },

    async _waitForDownload(jobId) {
        const maxWait = 120;
        for (let i = 0; i < maxWait; i++) {
            await new Promise(r => setTimeout(r, 1000));
            try {
                const jobs = await API.getBackgroundJobs();
                const job = jobs?.find(j => j.id === jobId) || {};
                if (job.status === 'success') {
                    this.updateProgress(18, 'Data ready');
                    return;
                }
                if (job.status === 'failed') {
                    console.log('Download job failed:', job.error);
                    return;
                }
                const pct = 8 + Math.min(10, i * 0.5);
                const tasks = Object.values(job.progress_tasks || {});
                const desc = tasks.length > 0 ? tasks[tasks.length - 1].description : 'Downloading...';
                this.updateProgress(pct, `Downloading: ${desc}`);
            } catch(e) { return; }
        }
    },

    _showErrorModal(title, message, detail) {
        let modal = document.getElementById('btErrorModal');
        if (modal) modal.remove();
        modal = document.createElement('div');
        modal.id = 'btErrorModal';
        modal.className = 'modal fade';
        modal.tabIndex = -1;
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="background:var(--bc-card);border:1px solid var(--bc-border);color:var(--bc-text)">
                    <div class="modal-header border-secondary">
                        <h5 class="modal-title"><i class="bi bi-exclamation-triangle-fill text-danger me-2"></i>${title}</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>${message}</p>
                        <div class="bg-dark rounded p-3 mt-2" style="font-size:0.8rem;max-height:200px;overflow:auto">
                            <code class="text-danger">${detail}</code>
                        </div>
                    </div>
                    <div class="modal-footer border-secondary">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>`;
        document.body.appendChild(modal);
        new bootstrap.Modal(modal).show();
        modal.addEventListener('hidden.bs.modal', () => modal.remove());
    },

    destroy() {
        if (this.chart) { this.chart.remove(); this.chart = null; }
        if (this.pollTimer) { clearTimeout(this.pollTimer); this.pollTimer = null; }
        this.isRunning = false;
    }
};

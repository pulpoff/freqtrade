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
            <!-- Config Section -->
            <div class="card mb-3">
                <div class="card-body">
                    <h5 class="fw-semibold mb-3"><i class="bi bi-clock-history me-2 text-success"></i>Run Backtest</h5>

                    <div class="row g-2 g-md-3">
                        <!-- Strategy Selection -->
                        <div class="col-12 col-md-4">
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

                        <!-- FreqAI Model -->
                        <div class="col-6 col-md-2">
                            <label class="form-label small text-secondary">FreqAI Model</label>
                            <select class="form-select" id="btFreqaiModel">
                                <option value="">None</option>
                                <option value="LightGBMRegressor">LightGBMRegressor</option>
                                <option value="LightGBMClassifier">LightGBMClassifier</option>
                                <option value="XGBoostRegressor">XGBoostRegressor</option>
                                <option value="XGBoostClassifier">XGBoostClassifier</option>
                                <option value="XGBoostRFRegressor">XGBoostRFRegressor</option>
                                <option value="SKLearnRandomForestClassifier">SKLearnRandomForest</option>
                                <option value="PyTorchMLPRegressor">PyTorchMLPRegressor</option>
                                <option value="ReinforcementLearner">ReinforcementLearner</option>
                            </select>
                        </div>

                        <!-- Pair Filter -->
                        <div class="col-6 col-md-2">
                            <label class="form-label small text-secondary">Pair Filter</label>
                            <select class="form-select" id="btPair">
                                <option value="">All (from config)</option>
                            </select>
                        </div>

                        <!-- Timeframe -->
                        <div class="col-6 col-md-2">
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
                        <div class="col-6 col-md-2">
                            <label class="form-label small text-secondary">Start Date</label>
                            <input type="date" class="form-control" id="btStartDate" value="${this._defaultStartDate()}">
                        </div>
                        <div class="col-6 col-md-2">
                            <label class="form-label small text-secondary">End Date</label>
                            <input type="date" class="form-control" id="btEndDate" value="${this._defaultEndDate()}">
                        </div>
                    </div>

                    <div class="row g-2 g-md-3 mt-1">
                        <!-- Stake Amount -->
                        <div class="col-6 col-md-3">
                            <label class="form-label small text-secondary">Initial Wallet (Dry Run)</label>
                            <div class="input-group">
                                <input type="number" class="form-control" id="btWallet" value="1000">
                                <span class="input-group-text">USDT</span>
                            </div>
                        </div>

                        <!-- Stake per trade -->
                        <div class="col-6 col-md-3">
                            <label class="form-label small text-secondary">Stake Amount</label>
                            <input type="text" class="form-control" id="btStakeAmount" value="unlimited">
                        </div>

                        <!-- Max Open Trades -->
                        <div class="col-6 col-md-2">
                            <label class="form-label small text-secondary">Max Open Trades</label>
                            <input type="number" class="form-control" id="btMaxTrades" value="3">
                        </div>

                        <!-- Enable Protections -->
                        <div class="col-6 col-md-2">
                            <label class="form-label small text-secondary">Protections</label>
                            <div class="form-check form-switch mt-2">
                                <input type="checkbox" class="form-check-input" id="btProtections">
                                <label class="form-check-label" for="btProtections">Enable</label>
                            </div>
                        </div>

                        <!-- Run Button -->
                        <div class="col-12 col-md-2 d-flex align-items-end">
                            <button class="btn btn-success w-100 fw-semibold" id="btRunBtn" onclick="BacktestingPage._autoDownloaded = false; BacktestingPage.runBacktest()">
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

    async loadPairList() {
        const select = document.getElementById('btPair');
        if (!select) return;

        try {
            if (API.connected) {
                const whitelist = await API.getWhitelist();
                if (whitelist && whitelist.whitelist) {
                    whitelist.whitelist.forEach(p => {
                        const opt = document.createElement('option');
                        opt.value = p;
                        opt.textContent = p;
                        select.appendChild(opt);
                    });
                }
            }
        } catch (e) {
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

            this.updateProgress(10, 'Resetting previous backtest...');
            await API.resetBacktest().catch(() => {});

            this.updateProgress(15, 'Starting backtest...');
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
                    }, 500);
                }, 200);
            } else if (status.status === 'error') {
                const errMsg = status.status_msg || 'Unknown error';
                if ((errMsg.includes('No data found') || errMsg.includes('No data')) && !this._autoDownloaded) {
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

            let pairs = [];
            const selectedPair = document.getElementById('btPair').value;
            if (selectedPair) {
                pairs = [selectedPair];
            } else {
                try {
                    const whitelist = await API.getWhitelist();
                    pairs = whitelist?.whitelist || [];
                } catch (e) {}
            }
            if (pairs.length === 0) {
                try {
                    const config = await API.getConfig();
                    pairs = config?.exchange?.pair_whitelist || ['BTC/USDT'];
                } catch (e) {
                    pairs = ['BTC/USDT'];
                }
            }

            const timeframes = [timeframe];
            if (timeframe !== '1h' && timeframe !== '4h') {
                timeframes.push('1h');
            }

            this.updateProgress(5, `Downloading data for ${pairs.length} pair(s)...`);
            const detail = document.getElementById('btProgressDetail');
            if (detail) detail.textContent = `Pairs: ${pairs.join(', ')} | Timeframes: ${timeframes.join(', ')}`;

            const result = await API.downloadData({
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

    initResultChart(trades, stratResult) {
        const container = document.getElementById('btChart');
        if (!container) return;
        container.innerHTML = '';

        const tb = document.getElementById('btChartToolbar');
        if (tb) {
            const pairs = [...new Set(trades.map(t => t.pair).filter(Boolean))];
            tb.innerHTML = `<div class="d-flex align-items-center gap-2 mb-2">
                <small class="text-secondary">Pairs: ${pairs.join(', ') || 'N/A'}</small>
                <small class="text-secondary ms-3">Trades: ${trades.length}</small>
            </div>`;
        }

        this.chart = Components.createChart(container);
        if (!this.chart) return;

        const lineSeries = this.chart.addLineSeries({
            color: '#2dd4a8',
            lineWidth: 2,
        });

        let cumProfit = 0;
        const startBalance = stratResult.starting_balance || 1000;
        const equityData = trades.map(t => {
            cumProfit += (t.profit_abs || 0);
            const closeTime = t.close_date ? Math.floor(new Date(t.close_date).getTime() / 1000) : 0;
            return { time: closeTime, value: startBalance + cumProfit };
        }).filter(d => d.time > 0).sort((a, b) => a.time - b.time);

        // Remove duplicates (same timestamp)
        const uniqueEquity = [];
        const seenTimes = new Set();
        equityData.forEach(d => {
            if (!seenTimes.has(d.time)) {
                seenTimes.add(d.time);
                uniqueEquity.push(d);
            }
        });

        if (uniqueEquity.length > 1) {
            lineSeries.setData(uniqueEquity);
        }

        // Add trade markers
        const markers = trades.map(t => {
            const time = t.close_date ? Math.floor(new Date(t.close_date).getTime() / 1000) : 0;
            if (!time || !seenTimes.has(time)) return null;
            const isWin = (t.profit_abs || 0) >= 0;
            return {
                time,
                position: isWin ? 'aboveBar' : 'belowBar',
                color: isWin ? '#2dd4a8' : '#e74c5e',
                shape: 'circle',
                text: isWin ? 'W' : 'L',
            };
        }).filter(Boolean).sort((a, b) => a.time - b.time);

        const uniqueMarkers = [];
        const markerTimes = new Set();
        markers.forEach(m => {
            if (!markerTimes.has(m.time)) {
                markerTimes.add(m.time);
                uniqueMarkers.push(m);
            }
        });

        if (uniqueMarkers.length > 0) {
            lineSeries.setMarkers(uniqueMarkers);
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
                            <th>Strategy</th><th>Timerange</th><th>Profit</th><th>Trades</th><th>Date</th><th></th>
                        </tr></thead>
                        <tbody>
                            <tr class="text-secondary"><td colspan="6" class="text-center py-3">Connect to Freqtrade to see backtest history</td></tr>
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
                                ${Components.formatPercent((h.profit_total || 0) * 100)}
                            </td>
                            <td>${h.trades || '-'}</td>
                            <td class="text-secondary small">${h.backtest_start || Components.formatDate(h.run_id) || '-'}</td>
                            <td>
                                <button class="btn btn-outline-success btn-sm" onclick="BacktestingPage.loadHistoryResult('${h.filename || ''}', '${h.strategy || ''}')">
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

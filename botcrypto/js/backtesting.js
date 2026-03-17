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

    render() {
        return `
        <div id="backtestingPage">
            <!-- Config Section -->
            <div class="card mb-3">
                <div class="card-body">
                    <h5 class="fw-semibold mb-3"><i class="bi bi-flask me-2 text-success"></i>Run Backtest</h5>

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

                        <!-- Trading Pair (informational - backtest uses strategy's pair config) -->
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">Pair Filter</label>
                            <select class="form-select" id="btPair">
                                <option value="">All (from config)</option>
                            </select>
                        </div>

                        <!-- Timeframe -->
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">Timeframe</label>
                            <select class="form-select" id="btTimeframe">
                                <option value="">Strategy default</option>
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
                            <input type="date" class="form-control" id="btStartDate" value="2024-01-01">
                        </div>
                        <div class="col-md-2">
                            <label class="form-label small text-secondary">End Date</label>
                            <input type="date" class="form-control" id="btEndDate" value="2024-03-01">
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
                            <input type="text" class="form-control" id="btStakeAmount" value="unlimited">
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
                <!-- Results Header -->
                <div class="card mb-3" id="btResultsHeader"></div>

                <!-- Summary Stats -->
                <div class="row g-3 mb-3" id="btSummaryStats"></div>

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
                // Pre-fill wallet from config
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
            // Add defaults
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

        // Show progress
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

            // Only include timeframe if explicitly set
            if (timeframe) {
                btConfig.timeframe = timeframe;
            }

            this.updateProgress(10, 'Resetting previous backtest...');
            await API.resetBacktest().catch(() => {});

            this.updateProgress(15, 'Starting backtest...');
            await API.startBacktest(btConfig);

            // Poll for progress
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
                this.hideProgress();
                this.isRunning = false;
                App.showToast(`Backtest error: ${status.status_msg || 'Unknown error'}`, 'error');
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

    displayResults(result) {
        if (!result) return;

        // Freqtrade returns {strategy: {StrategyName: {...}}}
        let stratResult;
        if (result.strategy) {
            const strategies = Object.values(result.strategy);
            stratResult = strategies[0];
        } else {
            stratResult = result;
        }

        if (!stratResult) {
            App.showToast('No results returned', 'warning');
            return;
        }

        const trades = stratResult.trades || [];
        const stratName = stratResult.strategy_name || Object.keys(result.strategy || {})[0] || 'Strategy';
        const dateRange = `${stratResult.backtest_start || ''} - ${stratResult.backtest_end || ''}`;
        const stakeCurrency = stratResult.stake_currency || 'USDT';

        // Results header
        const header = document.getElementById('btResultsHeader');
        if (header) {
            header.innerHTML = `<div class="card-body">${Components.chartHeader(
                `${stratName} backtest`, stratName, dateRange, 'COMPLETED'
            )}</div>`;
        }

        // Summary stats row
        const statsEl = document.getElementById('btSummaryStats');
        if (statsEl) {
            const totalProfit = stratResult.profit_total_abs || 0;
            const profitPct = (stratResult.profit_total || 0) * 100;
            const maxDrawdown = stratResult.max_drawdown_abs || stratResult.max_drawdown || 0;
            const maxDrawdownPct = ((stratResult.max_drawdown_account || stratResult.max_drawdown || 0) * 100);
            const winTrades = stratResult.wins || 0;
            const lossTrades = stratResult.losses || 0;
            const totalTrades = trades.length;
            const winRate = totalTrades > 0 ? (winTrades / totalTrades * 100) : 0;

            statsEl.innerHTML = `
                <div class="col-md-2"><div class="card"><div class="card-body py-2 text-center">
                    <div class="stat-value">${totalTrades}</div><div class="stat-label">Total Trades</div>
                </div></div></div>
                <div class="col-md-2"><div class="card"><div class="card-body py-2 text-center">
                    <div class="stat-value ${totalProfit >= 0 ? 'text-profit' : 'text-loss'}">${totalProfit >= 0 ? '+' : ''}${Components.formatNumber(totalProfit, 2)} ${stakeCurrency}</div>
                    <div class="stat-label">Total Profit</div>
                </div></div></div>
                <div class="col-md-2"><div class="card"><div class="card-body py-2 text-center">
                    <div class="stat-value ${profitPct >= 0 ? 'text-profit' : 'text-loss'}">${profitPct >= 0 ? '+' : ''}${Components.formatPercent(profitPct)}</div>
                    <div class="stat-label">Profit %</div>
                </div></div></div>
                <div class="col-md-2"><div class="card"><div class="card-body py-2 text-center">
                    <div class="stat-value ${winRate >= 50 ? 'text-profit' : 'text-loss'}">${Components.formatPercent(winRate)}</div>
                    <div class="stat-label">Win Rate (${winTrades}W/${lossTrades}L)</div>
                </div></div></div>
                <div class="col-md-2"><div class="card"><div class="card-body py-2 text-center">
                    <div class="stat-value text-loss">${Components.formatPercent(maxDrawdownPct)}</div>
                    <div class="stat-label">Max Drawdown</div>
                </div></div></div>
                <div class="col-md-2"><div class="card"><div class="card-body py-2 text-center">
                    <div class="stat-value">${Components.formatNumber(stratResult.final_balance || 0, 2)} ${stakeCurrency}</div>
                    <div class="stat-label">Final Balance</div>
                </div></div></div>`;
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

        // Trades table
        const tt = document.getElementById('btTradesTable');
        if (tt) {
            if (trades.length > 0) {
                tt.innerHTML = `
                <h6 class="fw-semibold mb-3">Trades (${trades.length})</h6>
                <div class="table-responsive" style="max-height:400px;overflow:auto">
                    <table class="table table-hover table-sm mb-0">
                        <thead><tr>
                            <th>#</th><th>Pair</th><th>Profit</th><th>Open Rate</th><th>Close Rate</th>
                            <th>Duration</th><th>Exit Reason</th>
                        </tr></thead>
                        <tbody>
                            ${trades.map((t, i) => `
                            <tr>
                                <td>${i + 1}</td>
                                <td class="fw-semibold">${t.pair || '-'}</td>
                                <td class="${(t.profit_ratio || 0) >= 0 ? 'text-profit' : 'text-loss'} fw-semibold">
                                    ${Components.formatPercent((t.profit_ratio || 0) * 100)}
                                    <br><small>${(t.profit_abs || 0) >= 0 ? '+' : ''}${Components.formatNumber(t.profit_abs || 0)}</small>
                                </td>
                                <td>${Components.formatNumber(t.open_rate, 6)}</td>
                                <td>${Components.formatNumber(t.close_rate, 6)}</td>
                                <td class="small">${t.trade_duration || '-'} min</td>
                                <td><span class="badge bg-secondary">${t.exit_reason || t.sell_reason || '-'}</span></td>
                            </tr>`).join('')}
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

        // Create equity line from cumulative profit
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

        // Deduplicate markers by time
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

        // Deduplicate
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
            this.displayResults(result);
        } catch (e) {
            App.showToast(`Error loading result: ${e.message}`, 'error');
        }
    },

    destroy() {
        if (this.chart) { this.chart.remove(); this.chart = null; }
        if (this.pollTimer) { clearTimeout(this.pollTimer); this.pollTimer = null; }
        this.isRunning = false;
    }
};

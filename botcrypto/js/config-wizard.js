/**
 * BotCrypto - Configuration Wizard
 * Step-by-step setup for Freqtrade config, exchange API keys,
 * and the ability to load/create config files
 */
const ConfigWizardPage = {
    currentStep: 1,
    totalSteps: 5,
    config: {
        // Exchange
        exchange: 'binance',
        apiKey: '',
        apiSecret: '',
        tradingMode: 'spot',

        // Trading
        stakeCurrency: 'USDT',
        stakeAmount: 'unlimited',
        maxOpenTrades: 3,
        dryRun: true,
        dryRunWallet: 1000,

        // Pairs
        pairWhitelist: ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'SOL/USDT'],
        pairBlacklist: ['BNB/USDT'],

        // Risk
        stoploss: -0.10,
        trailingStop: false,
        trailingStopPositive: 0.01,
        minimalRoi: { '0': 0.04, '20': 0.02, '40': 0.01, '60': 0 },

        // API Server
        apiServerEnabled: true,
        apiHost: '0.0.0.0',
        apiPort: 8080,
        apiUsername: 'freqtrader',
        apiPassword: '',
        corsOrigins: ['http://localhost:3000'],
    },

    render() {
        return `
        <div id="configPage">
            <!-- Saved Configs from Database -->
            <div class="card mb-4">
                <div class="card-header d-flex align-items-center justify-content-between">
                    <h5 class="mb-0 fw-semibold"><i class="bi bi-database me-2"></i>Saved Configurations</h5>
                    <div class="d-flex gap-2">
                        <button class="btn btn-outline-success btn-sm" onclick="ConfigWizardPage.importFromFile()">
                            <i class="bi bi-file-earmark-arrow-up me-1"></i> Import JSON
                        </button>
                        <button class="btn btn-outline-secondary btn-sm" onclick="ConfigWizardPage.importPyStrategy()">
                            <i class="bi bi-file-earmark-code me-1"></i> Import .py Strategy
                        </button>
                        <input type="file" id="dbConfigImport" accept=".json" style="display:none"
                            onchange="ConfigWizardPage.onDbImport(event)">
                        <input type="file" id="dbStrategyImport" accept=".py" style="display:none"
                            onchange="ConfigWizardPage.onPyImport(event)">
                    </div>
                </div>
                <div class="card-body" id="savedConfigsList">
                    <div class="text-center text-secondary py-3">
                        <div class="spinner-border spinner-border-sm me-2"></div> Loading configs...
                    </div>
                </div>
            </div>

            <!-- Strategy Files -->
            <div class="card mb-4">
                <div class="card-header">
                    <h6 class="mb-0"><i class="bi bi-file-earmark-code me-2"></i>Loaded Strategy Files (.py)</h6>
                </div>
                <div class="card-body" id="strategyFilesList">
                    <div class="text-center text-secondary py-2 small">No strategy files loaded</div>
                </div>
            </div>

            <div class="row justify-content-center">
                <div class="col-lg-8">
                    <h4 class="fw-semibold mb-4"><i class="bi bi-gear me-2"></i>Configuration Wizard</h4>

                    <!-- Step Indicators -->
                    <div class="d-flex justify-content-center mb-4">
                        ${this._stepIndicators()}
                    </div>

                    <!-- Step Content -->
                    <div class="card">
                        <div class="card-body p-4" id="wizardContent">
                            ${this._renderStep()}
                        </div>
                    </div>

                    <!-- Navigation -->
                    <div class="d-flex justify-content-between mt-3">
                        <button class="btn btn-outline-secondary" id="wizPrevBtn"
                            onclick="ConfigWizardPage.prevStep()"
                            ${this.currentStep === 1 ? 'disabled' : ''}>
                            <i class="bi bi-chevron-left me-1"></i> Previous
                        </button>
                        <div class="d-flex gap-2">
                            <button class="btn btn-outline-secondary" onclick="ConfigWizardPage.loadConfigFile()">
                                <i class="bi bi-folder-open me-1"></i> Load Config
                            </button>
                            <input type="file" id="configFileInput" accept=".json" style="display:none"
                                onchange="ConfigWizardPage.onConfigFileSelected(event)">
                            ${this.currentStep === this.totalSteps ?
                                `<button class="btn btn-success fw-semibold" onclick="ConfigWizardPage.saveConfig()">
                                    <i class="bi bi-save me-1"></i> Save & Apply
                                </button>` :
                                `<button class="btn btn-success" onclick="ConfigWizardPage.nextStep()">
                                    Next <i class="bi bi-chevron-right ms-1"></i>
                                </button>`
                            }
                        </div>
                    </div>

                    <!-- Current Config Preview -->
                    <div class="card mt-4">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h6 class="mb-0"><i class="bi bi-code me-2"></i>Config Preview</h6>
                            <button class="btn btn-outline-success btn-sm" onclick="ConfigWizardPage.exportConfig()">
                                <i class="bi bi-download me-1"></i> Export JSON
                            </button>
                        </div>
                        <div class="card-body">
                            <pre class="bg-black p-3 rounded text-success small mb-0" style="max-height:300px;overflow:auto"><code id="configPreview">${this._escapeHtml(JSON.stringify(this._buildConfig(), null, 2))}</code></pre>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
    },

    _stepIndicators() {
        const steps = ['Exchange', 'Trading', 'Pairs', 'Risk', 'API Server'];
        return steps.map((name, i) => {
            const num = i + 1;
            const isActive = num === this.currentStep;
            const isCompleted = num < this.currentStep;
            return `
            <div class="d-flex align-items-center ${i > 0 ? 'ms-2' : ''}">
                ${i > 0 ? '<div class="border-top border-secondary" style="width:30px"></div>' : ''}
                <div class="d-flex align-items-center gap-2 px-3 py-2 rounded ${isActive ? 'bg-success bg-opacity-10' : ''}" style="cursor:pointer"
                    onclick="ConfigWizardPage.goToStep(${num})">
                    <div class="wizard-step-circle ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}">
                        ${isCompleted ? '<i class="bi bi-check"></i>' : num}
                    </div>
                    <span class="small ${isActive ? 'text-success fw-semibold' : 'text-secondary'}">${name}</span>
                </div>
            </div>`;
        }).join('');
    },

    _renderStep() {
        switch(this.currentStep) {
            case 1: return this._stepExchange();
            case 2: return this._stepTrading();
            case 3: return this._stepPairs();
            case 4: return this._stepRisk();
            case 5: return this._stepApiServer();
            default: return '';
        }
    },

    _stepExchange() {
        return `
        <h5 class="fw-semibold mb-3"><i class="bi bi-bank me-2"></i>Exchange Configuration</h5>
        <p class="text-secondary mb-4">Connect your exchange. API keys are encrypted and never have withdrawal permissions.</p>

        <div class="mb-3">
            <label class="form-label">Exchange</label>
            <select class="form-select" onchange="ConfigWizardPage.config.exchange = this.value">
                <option value="binance" ${this.config.exchange === 'binance' ? 'selected' : ''}>Binance</option>
                <option value="kraken" ${this.config.exchange === 'kraken' ? 'selected' : ''}>Kraken</option>
                <option value="kucoin" ${this.config.exchange === 'kucoin' ? 'selected' : ''}>KuCoin</option>
                <option value="gate" ${this.config.exchange === 'gate' ? 'selected' : ''}>Gate.io</option>
                <option value="bybit" ${this.config.exchange === 'bybit' ? 'selected' : ''}>Bybit</option>
                <option value="okx" ${this.config.exchange === 'okx' ? 'selected' : ''}>OKX</option>
            </select>
        </div>

        <div class="mb-3">
            <label class="form-label">Trading Mode</label>
            <div class="btn-group w-100">
                <button class="btn ${this.config.tradingMode === 'spot' ? 'btn-success' : 'btn-outline-secondary'}"
                    onclick="ConfigWizardPage.config.tradingMode = 'spot'; ConfigWizardPage.refreshStep()">Spot</button>
                <button class="btn ${this.config.tradingMode === 'futures' ? 'btn-success' : 'btn-outline-secondary'}"
                    onclick="ConfigWizardPage.config.tradingMode = 'futures'; ConfigWizardPage.refreshStep()">Futures</button>
            </div>
        </div>

        <div class="mb-3">
            <label class="form-label">API Key</label>
            <input type="text" class="form-control" placeholder="Enter your API key"
                value="${this.config.apiKey}"
                onchange="ConfigWizardPage.config.apiKey = this.value">
        </div>

        <div class="mb-3">
            <label class="form-label">API Secret</label>
            <input type="password" class="form-control" placeholder="Enter your API secret"
                value="${this.config.apiSecret}"
                onchange="ConfigWizardPage.config.apiSecret = this.value">
        </div>

        <div class="alert alert-info small">
            <i class="bi bi-shield-lock me-2"></i>
            <strong>Security:</strong> API keys are stored locally with AES-256 encryption. Never enable withdrawal permissions on your exchange API keys.
        </div>`;
    },

    _stepTrading() {
        return `
        <h5 class="fw-semibold mb-3"><i class="bi bi-currency-exchange me-2"></i>Trading Settings</h5>
        <p class="text-secondary mb-4">Configure how the bot trades.</p>

        <div class="row g-3">
            <div class="col-md-6">
                <label class="form-label">Stake Currency</label>
                <select class="form-select" onchange="ConfigWizardPage.config.stakeCurrency = this.value">
                    <option value="USDT" ${this.config.stakeCurrency === 'USDT' ? 'selected' : ''}>USDT</option>
                    <option value="BTC" ${this.config.stakeCurrency === 'BTC' ? 'selected' : ''}>BTC</option>
                    <option value="ETH" ${this.config.stakeCurrency === 'ETH' ? 'selected' : ''}>ETH</option>
                    <option value="EUR" ${this.config.stakeCurrency === 'EUR' ? 'selected' : ''}>EUR</option>
                </select>
            </div>
            <div class="col-md-6">
                <label class="form-label">Stake Amount per Trade</label>
                <input type="text" class="form-control" value="${this.config.stakeAmount}"
                    onchange="ConfigWizardPage.config.stakeAmount = this.value">
                <small class="text-secondary">Use "unlimited" for dynamic calculation</small>
            </div>
            <div class="col-md-6">
                <label class="form-label">Max Open Trades</label>
                <input type="number" class="form-control" value="${this.config.maxOpenTrades}"
                    onchange="ConfigWizardPage.config.maxOpenTrades = parseInt(this.value)">
            </div>
            <div class="col-md-6">
                <label class="form-label">Dry Run Wallet</label>
                <div class="input-group">
                    <input type="number" class="form-control" value="${this.config.dryRunWallet}"
                        onchange="ConfigWizardPage.config.dryRunWallet = parseFloat(this.value)">
                    <span class="input-group-text">${this.config.stakeCurrency}</span>
                </div>
            </div>
        </div>

        <div class="form-check form-switch mt-3">
            <input type="checkbox" class="form-check-input" id="dryRunSwitch"
                ${this.config.dryRun ? 'checked' : ''}
                onchange="ConfigWizardPage.config.dryRun = this.checked">
            <label class="form-check-label" for="dryRunSwitch">
                <strong>Dry Run Mode</strong> (paper trading - no real money)
            </label>
        </div>

        <div class="alert alert-warning small mt-3">
            <i class="bi bi-exclamation-triangle me-2"></i>
            <strong>Recommended:</strong> Start with Dry Run mode enabled to test your strategy before using real funds.
        </div>`;
    },

    _stepPairs() {
        return `
        <h5 class="fw-semibold mb-3"><i class="bi bi-tags me-2"></i>Trading Pairs</h5>
        <p class="text-secondary mb-4">Select which pairs the bot should trade.</p>

        <div class="mb-3">
            <label class="form-label">Pair Whitelist</label>
            <textarea class="form-control" rows="4" placeholder="One pair per line: BTC/USDT"
                onchange="ConfigWizardPage.config.pairWhitelist = this.value.split('\\n').map(s => s.trim()).filter(s => s)">${this.config.pairWhitelist.join('\n')}</textarea>
            <small class="text-secondary">Enter trading pairs, one per line (e.g., BTC/USDT)</small>
        </div>

        <div class="mb-3">
            <label class="form-label">Pair Blacklist</label>
            <textarea class="form-control" rows="2" placeholder="Pairs to avoid"
                onchange="ConfigWizardPage.config.pairBlacklist = this.value.split('\\n').map(s => s.trim()).filter(s => s)">${this.config.pairBlacklist.join('\n')}</textarea>
            <small class="text-secondary">Pairs to exclude from trading</small>
        </div>

        <div class="d-flex gap-2 mt-3">
            <button class="btn btn-outline-success btn-sm" onclick="ConfigWizardPage.addTopPairs()">
                <i class="bi bi-plus me-1"></i> Add Top 10 by Volume
            </button>
            <button class="btn btn-outline-secondary btn-sm" onclick="ConfigWizardPage.clearPairs()">
                <i class="bi bi-x me-1"></i> Clear All
            </button>
        </div>`;
    },

    _stepRisk() {
        return `
        <h5 class="fw-semibold mb-3"><i class="bi bi-shield me-2"></i>Risk Management</h5>
        <p class="text-secondary mb-4">Set stop loss, take profit, and ROI targets.</p>

        <div class="row g-3">
            <div class="col-md-6">
                <label class="form-label">Stop Loss (%)</label>
                <div class="input-group">
                    <input type="number" class="form-control" value="${this.config.stoploss * 100}" step="0.5"
                        onchange="ConfigWizardPage.config.stoploss = parseFloat(this.value) / 100">
                    <span class="input-group-text">%</span>
                </div>
                <small class="text-secondary">e.g., -10 for 10% stop loss</small>
            </div>
            <div class="col-md-6">
                <label class="form-label">Trailing Stop</label>
                <div class="form-check form-switch mt-2">
                    <input type="checkbox" class="form-check-input" id="trailingStopSwitch"
                        ${this.config.trailingStop ? 'checked' : ''}
                        onchange="ConfigWizardPage.config.trailingStop = this.checked; ConfigWizardPage.refreshStep()">
                    <label class="form-check-label" for="trailingStopSwitch">Enable Trailing Stop</label>
                </div>
            </div>

            ${this.config.trailingStop ? `
            <div class="col-md-6">
                <label class="form-label">Trailing Stop Positive (%)</label>
                <div class="input-group">
                    <input type="number" class="form-control" value="${this.config.trailingStopPositive * 100}" step="0.1"
                        onchange="ConfigWizardPage.config.trailingStopPositive = parseFloat(this.value) / 100">
                    <span class="input-group-text">%</span>
                </div>
            </div>` : ''}
        </div>

        <hr class="border-secondary my-4">

        <h6 class="fw-semibold mb-3">Minimal ROI</h6>
        <div class="table-responsive">
            <table class="table table-sm">
                <thead>
                    <tr><th>Minutes</th><th>ROI (%)</th><th></th></tr>
                </thead>
                <tbody id="roiTable">
                    ${Object.entries(this.config.minimalRoi).map(([mins, roi]) => `
                    <tr>
                        <td><input type="number" class="form-control form-control-sm" value="${mins}" style="width:80px"
                            data-roi-minutes="${mins}"></td>
                        <td><input type="number" class="form-control form-control-sm" value="${roi * 100}" step="0.1" style="width:80px"
                            data-roi-value="${mins}"></td>
                        <td><button class="btn btn-outline-danger btn-sm" onclick="ConfigWizardPage.removeRoi('${mins}')">
                            <i class="bi bi-x"></i></button></td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>
        <button class="btn btn-outline-success btn-sm" onclick="ConfigWizardPage.addRoi()">
            <i class="bi bi-plus me-1"></i> Add ROI Point
        </button>`;
    },

    _stepApiServer() {
        return `
        <h5 class="fw-semibold mb-3"><i class="bi bi-hdd-network me-2"></i>API Server</h5>
        <p class="text-secondary mb-4">Configure the Freqtrade API server that BotCrypto connects to.</p>

        <div class="form-check form-switch mb-3">
            <input type="checkbox" class="form-check-input" id="apiEnabledSwitch"
                ${this.config.apiServerEnabled ? 'checked' : ''}
                onchange="ConfigWizardPage.config.apiServerEnabled = this.checked">
            <label class="form-check-label" for="apiEnabledSwitch">Enable API Server</label>
        </div>

        <div class="row g-3">
            <div class="col-md-6">
                <label class="form-label">Listen Host</label>
                <input type="text" class="form-control" value="${this.config.apiHost}"
                    onchange="ConfigWizardPage.config.apiHost = this.value">
            </div>
            <div class="col-md-6">
                <label class="form-label">Listen Port</label>
                <input type="number" class="form-control" value="${this.config.apiPort}"
                    onchange="ConfigWizardPage.config.apiPort = parseInt(this.value)">
            </div>
            <div class="col-md-6">
                <label class="form-label">Username</label>
                <input type="text" class="form-control" value="${this.config.apiUsername}"
                    onchange="ConfigWizardPage.config.apiUsername = this.value">
            </div>
            <div class="col-md-6">
                <label class="form-label">Password</label>
                <input type="password" class="form-control" value="${this.config.apiPassword}"
                    placeholder="Enter API password"
                    onchange="ConfigWizardPage.config.apiPassword = this.value">
            </div>
            <div class="col-12">
                <label class="form-label">CORS Origins</label>
                <input type="text" class="form-control" value="${this.config.corsOrigins.join(', ')}"
                    onchange="ConfigWizardPage.config.corsOrigins = this.value.split(',').map(s => s.trim()).filter(s => s)">
                <small class="text-secondary">Comma-separated list of allowed origins</small>
            </div>
        </div>

        <div class="alert alert-success small mt-4">
            <i class="bi bi-check-circle me-2"></i>
            <strong>Ready!</strong> Click "Save & Apply" to generate your config.json file.
        </div>`;
    },

    // Navigation
    nextStep() {
        if (this.currentStep < this.totalSteps) {
            this.currentStep++;
            this.refreshWizard();
        }
    },

    prevStep() {
        if (this.currentStep > 1) {
            this.currentStep--;
            this.refreshWizard();
        }
    },

    goToStep(step) {
        this.currentStep = step;
        this.refreshWizard();
    },

    refreshStep() {
        const content = document.getElementById('wizardContent');
        if (content) content.innerHTML = this._renderStep();
        this.updateConfigPreview();
    },

    refreshWizard() {
        const container = document.getElementById('pageContainer');
        if (container) container.innerHTML = this.render();
    },

    updateConfigPreview() {
        const preview = document.getElementById('configPreview');
        if (preview) {
            preview.textContent = JSON.stringify(this._buildConfig(), null, 2);
        }
    },

    // Config operations
    _buildConfig() {
        return {
            max_open_trades: this.config.maxOpenTrades,
            stake_currency: this.config.stakeCurrency,
            stake_amount: this.config.stakeAmount === 'unlimited' ? 'unlimited' : parseFloat(this.config.stakeAmount),
            dry_run: this.config.dryRun,
            dry_run_wallet: this.config.dryRunWallet,
            trading_mode: this.config.tradingMode,
            margin_mode: this.config.tradingMode === 'futures' ? 'isolated' : '',
            stoploss: this.config.stoploss,
            trailing_stop: this.config.trailingStop,
            ...(this.config.trailingStop ? { trailing_stop_positive: this.config.trailingStopPositive } : {}),
            minimal_roi: this.config.minimalRoi,
            exchange: {
                name: this.config.exchange,
                key: this.config.apiKey || '',
                secret: this.config.apiSecret || '',
                pair_whitelist: this.config.pairWhitelist,
                pair_blacklist: this.config.pairBlacklist,
            },
            pairlists: [{ method: 'StaticPairList' }],
            api_server: {
                enabled: this.config.apiServerEnabled,
                listen_ip_address: this.config.apiHost,
                listen_port: this.config.apiPort,
                username: this.config.apiUsername,
                password: this.config.apiPassword,
                CORS_origins: this.config.corsOrigins,
            },
        };
    },

    async saveConfig() {
        const configJson = this._buildConfig();

        // Save to local storage
        localStorage.setItem('bc_config', JSON.stringify(configJson));

        // Try to apply via API
        if (API.connected) {
            try {
                await API.reloadConfig();
                App.showToast('Configuration saved and applied!', 'success');
            } catch (e) {
                App.showToast('Config saved locally. Restart Freqtrade to apply.', 'warning');
            }
        } else {
            App.showToast('Config saved locally. Export and place as config.json in Freqtrade directory.', 'info');
        }

        // Trigger download
        this.exportConfig();
    },

    exportConfig() {
        const config = this._buildConfig();
        const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'config.json';
        a.click();
        URL.revokeObjectURL(url);
    },

    loadConfigFile() {
        document.getElementById('configFileInput').click();
    },

    onConfigFileSelected(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const config = JSON.parse(e.target.result);
                this.applyLoadedConfig(config);
                App.showToast(`Config loaded: ${file.name}`, 'success');
                this.refreshWizard();
            } catch (err) {
                App.showToast('Invalid config file', 'error');
            }
        };
        reader.readAsText(file);
    },

    applyLoadedConfig(config) {
        if (config.exchange) {
            this.config.exchange = config.exchange.name || this.config.exchange;
            this.config.apiKey = config.exchange.key || '';
            this.config.apiSecret = config.exchange.secret || '';
            this.config.pairWhitelist = config.exchange.pair_whitelist || this.config.pairWhitelist;
            this.config.pairBlacklist = config.exchange.pair_blacklist || this.config.pairBlacklist;
        }
        if (config.trading_mode) this.config.tradingMode = config.trading_mode;
        if (config.stake_currency) this.config.stakeCurrency = config.stake_currency;
        if (config.stake_amount !== undefined) this.config.stakeAmount = String(config.stake_amount);
        if (config.max_open_trades !== undefined) this.config.maxOpenTrades = config.max_open_trades;
        if (config.dry_run !== undefined) this.config.dryRun = config.dry_run;
        if (config.dry_run_wallet !== undefined) this.config.dryRunWallet = config.dry_run_wallet;
        if (config.stoploss !== undefined) this.config.stoploss = config.stoploss;
        if (config.trailing_stop !== undefined) this.config.trailingStop = config.trailing_stop;
        if (config.minimal_roi) this.config.minimalRoi = config.minimal_roi;
        if (config.api_server) {
            this.config.apiServerEnabled = config.api_server.enabled !== false;
            this.config.apiHost = config.api_server.listen_ip_address || this.config.apiHost;
            this.config.apiPort = config.api_server.listen_port || this.config.apiPort;
            this.config.apiUsername = config.api_server.username || this.config.apiUsername;
            this.config.apiPassword = config.api_server.password || '';
            this.config.corsOrigins = config.api_server.CORS_origins || this.config.corsOrigins;
        }
    },

    addTopPairs() {
        const topPairs = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT', 'SOL/USDT',
            'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT'];
        this.config.pairWhitelist = [...new Set([...this.config.pairWhitelist, ...topPairs])];
        this.refreshStep();
    },

    clearPairs() {
        this.config.pairWhitelist = [];
        this.refreshStep();
    },

    addRoi() {
        const maxMins = Math.max(...Object.keys(this.config.minimalRoi).map(Number)) || 0;
        this.config.minimalRoi[String(maxMins + 20)] = 0;
        this.refreshStep();
    },

    removeRoi(mins) {
        delete this.config.minimalRoi[mins];
        this.refreshStep();
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    async init() {
        // Initialize ConfigDB
        try {
            await ConfigDB.init();
        } catch (e) {
            console.error('ConfigDB init error:', e);
        }

        // Load saved config if available
        const saved = localStorage.getItem('bc_config');
        if (saved) {
            try {
                this.applyLoadedConfig(JSON.parse(saved));
            } catch {}
        }

        // Load saved configs list
        this.refreshSavedConfigs();
        this.refreshStrategyFiles();
    },

    // ========== DATABASE CONFIG MANAGEMENT ==========

    async refreshSavedConfigs() {
        const container = document.getElementById('savedConfigsList');
        if (!container) return;

        try {
            const configs = await ConfigDB.getAllConfigs();
            if (configs.length === 0) {
                container.innerHTML = `
                <div class="text-center py-3">
                    <p class="text-secondary mb-2">No saved configs yet</p>
                    <button class="btn btn-outline-success btn-sm" onclick="ConfigWizardPage.saveCurrentToDb()">
                        <i class="bi bi-plus me-1"></i> Save Current Config
                    </button>
                </div>`;
                return;
            }

            container.innerHTML = `
            <div class="table-responsive">
                <table class="table table-hover mb-0">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Strategy</th>
                            <th>Exchange</th>
                            <th>Pair(s)</th>
                            <th>Mode</th>
                            <th>Updated</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${configs.map(c => `
                        <tr class="${c.isActive ? 'table-success' : ''}">
                            <td class="fw-semibold">${c.name || 'Unnamed'}</td>
                            <td><code class="text-info">${c.strategy || '-'}</code></td>
                            <td>${c.exchange || '-'}</td>
                            <td><small>${(c.pairWhitelist || []).slice(0, 3).join(', ')}${(c.pairWhitelist || []).length > 3 ? '...' : ''}</small></td>
                            <td><span class="badge ${c.dryRun ? 'bg-warning text-dark' : 'bg-danger'}">${c.dryRun ? 'Dry Run' : 'Live'}</span></td>
                            <td class="small text-secondary">${Components.formatDate(c.updatedAt)}</td>
                            <td>${c.isActive ? '<span class="badge bg-success">Active</span>' : ''}</td>
                            <td>
                                <div class="btn-group btn-group-sm">
                                    <button class="btn btn-outline-success" title="Load into wizard"
                                        onclick="ConfigWizardPage.loadFromDb(${c.id})">
                                        <i class="bi bi-pencil"></i>
                                    </button>
                                    <button class="btn btn-outline-primary" title="Apply & restart bot"
                                        onclick="ConfigWizardPage.applyAndRestart(${c.id})">
                                        <i class="bi bi-play-fill"></i>
                                    </button>
                                    <button class="btn btn-outline-secondary" title="Duplicate"
                                        onclick="ConfigWizardPage.duplicateDb(${c.id})">
                                        <i class="bi bi-copy"></i>
                                    </button>
                                    <button class="btn btn-outline-info" title="Export JSON"
                                        onclick="ConfigDB.exportConfigFile(${c.id})">
                                        <i class="bi bi-download"></i>
                                    </button>
                                    <button class="btn btn-outline-danger" title="Delete"
                                        onclick="ConfigWizardPage.deleteFromDb(${c.id})">
                                        <i class="bi bi-trash"></i>
                                    </button>
                                </div>
                            </td>
                        </tr>`).join('')}
                    </tbody>
                </table>
            </div>
            <div class="mt-2">
                <button class="btn btn-outline-success btn-sm" onclick="ConfigWizardPage.saveCurrentToDb()">
                    <i class="bi bi-plus me-1"></i> Save Current Config to Database
                </button>
            </div>`;
        } catch (e) {
            container.innerHTML = `<div class="text-center text-danger py-3">Error loading configs: ${e.message}</div>`;
        }
    },

    async refreshStrategyFiles() {
        const container = document.getElementById('strategyFilesList');
        if (!container) return;

        try {
            const files = await ConfigDB.getAllStrategyFiles();
            if (files.length === 0) {
                container.innerHTML = '<div class="text-center text-secondary py-2 small">No strategy files loaded. Import .py files to manage them here.</div>';
                return;
            }

            container.innerHTML = `
            <div class="list-group list-group-flush">
                ${files.map(f => `
                <div class="list-group-item bg-transparent d-flex align-items-center justify-content-between">
                    <div>
                        <i class="bi bi-file-earmark-code text-info me-2"></i>
                        <strong>${f.name}</strong>
                        <small class="text-secondary ms-2">${Components.formatDate(f.updatedAt)}</small>
                    </div>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-info" onclick="ConfigWizardPage.viewStrategy('${f.name}')">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-outline-danger" onclick="ConfigWizardPage.deleteStrategy(${f.id})">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>`).join('')}
            </div>`;
        } catch (e) {
            container.innerHTML = `<div class="text-center text-secondary py-2 small">Strategy files not available</div>`;
        }
    },

    async saveCurrentToDb() {
        const name = prompt('Config name:', this.config.strategy || 'My Config');
        if (!name) return;

        try {
            const configData = {
                name: name,
                ...this.config,
                strategy: this.config.strategy || name,
            };
            await ConfigDB.saveConfig(configData);
            App.showToast(`Config saved: ${name}`, 'success');
            this.refreshSavedConfigs();
        } catch (e) {
            App.showToast(`Save error: ${e.message}`, 'error');
        }
    },

    async loadFromDb(id) {
        try {
            const config = await ConfigDB.getConfig(id);
            if (!config) return;
            this.applyLoadedConfig(ConfigDB.buildFreqtradeConfig(config));
            this.config.strategy = config.strategy || config.name;
            App.showToast(`Loaded: ${config.name}`, 'success');
            this.refreshWizard();
        } catch (e) {
            App.showToast(`Load error: ${e.message}`, 'error');
        }
    },

    async applyAndRestart(id) {
        if (!confirm('This will restart the bot with the selected config. Continue?')) return;

        try {
            const result = await ConfigDB.restartWithConfig(id);
            if (result.success) {
                App.showToast(result.message, 'success');
            } else {
                App.showToast(result.message, 'warning');
            }
            this.refreshSavedConfigs();
        } catch (e) {
            App.showToast(`Restart error: ${e.message}`, 'error');
        }
    },

    async duplicateDb(id) {
        try {
            await ConfigDB.duplicateConfig(id);
            App.showToast('Config duplicated', 'success');
            this.refreshSavedConfigs();
        } catch (e) {
            App.showToast(`Duplicate error: ${e.message}`, 'error');
        }
    },

    async deleteFromDb(id) {
        if (!confirm('Delete this config?')) return;
        try {
            await ConfigDB.deleteConfig(id);
            App.showToast('Config deleted', 'info');
            this.refreshSavedConfigs();
        } catch (e) {
            App.showToast(`Delete error: ${e.message}`, 'error');
        }
    },

    importFromFile() {
        document.getElementById('dbConfigImport').click();
    },

    async onDbImport(event) {
        const file = event.target.files[0];
        if (!file) return;
        try {
            await ConfigDB.importConfigFile(file);
            App.showToast(`Config imported: ${file.name}`, 'success');
            this.refreshSavedConfigs();
        } catch (e) {
            App.showToast(`Import error: ${e.message}`, 'error');
        }
        event.target.value = '';
    },

    importPyStrategy() {
        document.getElementById('dbStrategyImport').click();
    },

    async onPyImport(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (e) => {
            const content = e.target.result;
            const match = content.match(/class\s+(\w+)\s*\(IStrategy\)/);
            const name = match ? match[1] : file.name.replace('.py', '');

            try {
                await ConfigDB.saveStrategyFile(name, content, {
                    filename: file.name,
                    size: file.size,
                });
                App.showToast(`Strategy loaded: ${name}`, 'success');
                this.refreshStrategyFiles();
            } catch (err) {
                App.showToast(`Error: ${err.message}`, 'error');
            }
        };
        reader.readAsText(file);
        event.target.value = '';
    },

    async viewStrategy(name) {
        try {
            const file = await ConfigDB.getStrategyFile(name);
            if (!file) return;

            const modal = document.createElement('div');
            modal.innerHTML = `
            <div class="modal fade" tabindex="-1">
                <div class="modal-dialog modal-lg modal-dialog-scrollable">
                    <div class="modal-content bg-dark border-secondary">
                        <div class="modal-header border-secondary">
                            <h5 class="modal-title"><i class="bi bi-file-earmark-code me-2"></i>${name}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <pre class="bg-black p-3 rounded text-success small" style="max-height:500px;overflow:auto"><code>${this._escapeHtml(file.content)}</code></pre>
                        </div>
                        <div class="modal-footer border-secondary">
                            <button class="btn btn-outline-success" onclick="navigator.clipboard.writeText(${JSON.stringify(file.content).replace(/'/g, "\\'")}); App.showToast('Copied!', 'success')">
                                <i class="bi bi-clipboard me-1"></i> Copy
                            </button>
                            <button class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        </div>
                    </div>
                </div>
            </div>`;
            document.body.appendChild(modal);
            const bsModal = new bootstrap.Modal(modal.querySelector('.modal'));
            bsModal.show();
            modal.querySelector('.modal').addEventListener('hidden.bs.modal', () => modal.remove());
        } catch (e) {
            App.showToast(`Error viewing strategy: ${e.message}`, 'error');
        }
    },

    async deleteStrategy(id) {
        if (!confirm('Delete this strategy file?')) return;
        try {
            await ConfigDB.deleteStrategyFile(id);
            App.showToast('Strategy file deleted', 'info');
            this.refreshStrategyFiles();
        } catch (e) {
            App.showToast(`Delete error: ${e.message}`, 'error');
        }
    },

    destroy() {}
};

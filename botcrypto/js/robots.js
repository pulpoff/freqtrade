/**
 * BotCrypto - My Strategies Page
 * Strategy management with tabs for My Strategies / Imported Strategies
 * Matches botcrypto.io's "My strategies" view
 */
const RobotsPage = {
    strategies: [],
    activeTab: 'my',
    searchQuery: '',
    refreshTimer: null,

    render() {
        const myStrategies = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
        const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
        const importedList = Object.entries(imported).map(([name, data]) => ({ name, ...data }));

        const list = this.activeTab === 'my' ? myStrategies : importedList;
        const filtered = this.searchQuery
            ? list.filter(s => s.name.toLowerCase().includes(this.searchQuery.toLowerCase()))
            : list;

        return `
        <div id="strategiesPage">
            <div class="d-flex align-items-start justify-content-between mb-3">
                <div>
                    <h4 class="fw-semibold mb-1"><i class="bi bi-diagram-3 me-2"></i>My strategies</h4>
                    <p class="text-secondary small mb-0">Find here the summary of your strategies</p>
                </div>
                <button class="btn btn-success fw-semibold" onclick="RobotsPage.createNewStrategy()">
                    <i class="bi bi-plus-circle me-1"></i> NEW STRATEGY
                </button>
            </div>

            <!-- Tabs: My Strategies / Imported Strategies -->
            <div class="d-flex gap-2 mb-4">
                <button class="btn strategy-tab ${this.activeTab === 'my' ? 'active' : ''}"
                    onclick="RobotsPage.switchTab('my')">
                    <i class="bi bi-diagram-3 me-2"></i>My Strategies
                </button>
                <button class="btn strategy-tab ${this.activeTab === 'imported' ? 'active' : ''}"
                    onclick="RobotsPage.switchTab('imported')">
                    <i class="bi bi-download me-2"></i>Imported Strategies
                </button>
            </div>

            <!-- Search -->
            <div class="strategy-search-bar mb-4">
                <input type="text" class="form-control" placeholder="Find your strategy..."
                    value="${this.searchQuery}"
                    oninput="RobotsPage.searchQuery = this.value; RobotsPage.refresh()">
                <i class="bi bi-search"></i>
            </div>

            <!-- Strategy Cards -->
            <div class="strategy-cards-grid" id="strategiesList">
                ${filtered.length === 0 ? `
                    <div class="text-center text-secondary py-5">
                        <i class="bi bi-diagram-3 fs-1 d-block mb-2"></i>
                        <p>${this.activeTab === 'my' ? 'No strategies created yet' : 'No imported strategies'}</p>
                        <button class="btn btn-outline-success btn-sm" onclick="RobotsPage.${this.activeTab === 'my' ? 'createNewStrategy' : 'importStrategy'}()">
                            <i class="bi bi-plus-lg me-1"></i> ${this.activeTab === 'my' ? 'Create Your First Strategy' : 'Import a Strategy'}
                        </button>
                    </div>
                ` : filtered.map((s, i) => this._renderStrategyCard(s, i)).join('')}
            </div>

            <!-- Bots Section -->
            <div class="d-flex align-items-center justify-content-between mt-4 mb-3">
                <h5 class="fw-semibold mb-0"><i class="bi bi-robot me-2"></i>My Bots</h5>
                <button class="btn btn-outline-success btn-sm" onclick="RobotsPage.addBot()">
                    <i class="bi bi-plus-lg me-1"></i> Add Bot
                </button>
            </div>
            <div id="botsContainer">
                ${this._renderBotCards()}
            </div>
        </div>`;
    },

    // Deterministic icon for a strategy name
    _strategyIcons: [
        'bi-lightning-charge', 'bi-rocket-takeoff', 'bi-bullseye', 'bi-tsunami',
        'bi-shield-check', 'bi-fire', 'bi-gem', 'bi-cpu', 'bi-graph-up-arrow',
        'bi-crosshair', 'bi-trophy', 'bi-bar-chart-line', 'bi-stars', 'bi-signpost',
        'bi-radar', 'bi-flower1', 'bi-moon-stars', 'bi-compass', 'bi-virus',
        'bi-hurricane', 'bi-eye', 'bi-lightning', 'bi-globe2', 'bi-broadcast',
        'bi-peace', 'bi-activity', 'bi-box-seam', 'bi-diamond', 'bi-infinity',
        'bi-motherboard', 'bi-layers', 'bi-snow3', 'bi-heart-pulse',
    ],

    _getStrategyIcon(name) {
        let hash = 0;
        for (let i = 0; i < name.length; i++) hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0;
        return this._strategyIcons[Math.abs(hash) % this._strategyIcons.length];
    },

    _renderStrategyCard(s, index) {
        const isImported = this.activeTab === 'imported';
        let timeUnit = s.timeUnit || s.timeframe || '';
        const nodesCount = s.nodes ? s.nodes.length : 0;
        let paramsHtml = '';
        const icon = this._getStrategyIcon(s.name);

        // Extract params from .py content for imported strategies
        if (isImported && s.content) {
            const code = s.content;
            const tf = code.match(/timeframe\s*=\s*['"]([^'"]+)['"]/);
            const sl = code.match(/stoploss\s*=\s*(-?[\d.]+)/);
            const ts = code.match(/trailing_stop\s*=\s*(True|False)/);
            const roi = code.match(/minimal_roi\s*=\s*\{[^}]*"0"\s*:\s*([\d.]+)/);
            const leverageM = code.match(/leverage\s*.*?return\s+(\d+)/s) || code.match(/leverage\s*=\s*(\d+)/);
            if (tf) timeUnit = tf[1];
            const badges = [];
            if (sl) badges.push(`<span class="badge bg-danger text-white">SL ${(parseFloat(sl[1]) * 100).toFixed(1)}%</span>`);
            if (roi) badges.push(`<span class="badge bg-success text-white">ROI ${(parseFloat(roi[1]) * 100).toFixed(1)}%</span>`);
            if (leverageM) badges.push(`<span class="badge bg-info text-white">${leverageM[1]}x</span>`);
            if (ts && ts[1] === 'True') badges.push(`<span class="badge bg-warning text-dark">Trail</span>`);
            if (badges.length) paramsHtml = `<div class="d-flex gap-1 mt-2 flex-wrap">${badges.join('')}</div>`;
        }

        return `
        <div class="strategy-card" onclick="RobotsPage.openStrategy('${s.name.replace(/'/g, "\\'")}', ${isImported})">
            <div class="d-flex align-items-start justify-content-between">
                <div class="d-flex align-items-center gap-2">
                    <i class="bi ${icon}" style="color:var(--bc-accent);opacity:0.8;font-size:1.1rem"></i>
                    <span class="fw-semibold strategy-card-name">${s.name}</span>
                </div>
                <div class="dropdown" onclick="event.stopPropagation()">
                    <button class="btn btn-sm btn-link text-secondary p-0" data-bs-toggle="dropdown">
                        <i class="bi bi-three-dots"></i>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end dropdown-menu-dark">
                        <li><a class="dropdown-item" href="#" onclick="event.preventDefault(); RobotsPage.openStrategy('${s.name.replace(/'/g, "\\'")}', ${isImported})">
                            <i class="bi bi-pencil me-2"></i>Edit</a></li>
                        <li><a class="dropdown-item" href="#" onclick="event.preventDefault(); RobotsPage.duplicateStrategy(${index})">
                            <i class="bi bi-copy me-2"></i>Duplicate</a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item text-danger" href="#" onclick="event.preventDefault(); RobotsPage.deleteStrategy(${index})">
                            <i class="bi bi-trash me-2"></i>Delete</a></li>
                    </ul>
                </div>
            </div>
            ${paramsHtml}
            <div class="d-flex align-items-center justify-content-between mt-2">
                <span class="text-secondary small">${isImported ? 'Python' : (nodesCount > 0 ? nodesCount + ' blocks' : 'No blocks')}</span>
                <div class="d-flex align-items-center gap-3">
                    ${!isImported && s.desc ? `<span class="text-success small">${s.desc.substring(0, 20)}</span>` : ''}
                    ${timeUnit ? `<span class="text-secondary small">${timeUnit}<i class="bi bi-clock ms-1"></i></span>` : ''}
                </div>
            </div>
        </div>`;
    },

    switchTab(tab) {
        this.activeTab = tab;
        this.searchQuery = '';
        this.refresh();
    },

    createNewStrategy() {
        // Navigate to strategy builder - it will create a fresh strategy with just START
        localStorage.removeItem('bc_strategy');
        StrategyBuilderPage.nodes = [];
        StrategyBuilderPage.connections = [];
        StrategyBuilderPage.nextId = 1;
        StrategyBuilderPage.strategyName = 'My Strategy';
        StrategyBuilderPage.strategyDesc = '';
        StrategyBuilderPage.createDefaultNodes();
        StrategyBuilderPage.autoSave();
        App.navigate('strategy-builder');
    },

    openStrategy(name, isImported) {
        if (isImported) {
            const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
            if (imported[name]) {
                // Parse imported strategy into flow and open builder
                StrategyBuilderPage._parseStrategyToFlow(imported[name].content, name);
                StrategyBuilderPage.autoSave();
                App.navigate('strategy-builder');
            }
        } else {
            const strategies = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
            const s = strategies.find(st => st.name === name);
            if (s) {
                StrategyBuilderPage.nodes = s.nodes || [];
                StrategyBuilderPage.connections = s.connections || [];
                StrategyBuilderPage.strategyName = s.name;
                StrategyBuilderPage.strategyDesc = s.desc || '';
                StrategyBuilderPage.nextId = s.nextId || 1;
                StrategyBuilderPage.timeUnit = s.timeUnit || '5m';
                StrategyBuilderPage.autoSave();
                App.navigate('strategy-builder');
            }
        }
    },

    duplicateStrategy(index) {
        if (this.activeTab === 'my') {
            const strategies = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
            if (strategies[index]) {
                const copy = JSON.parse(JSON.stringify(strategies[index]));
                copy.name = copy.name + ' (copy)';
                copy.savedAt = new Date().toISOString();
                strategies.push(copy);
                localStorage.setItem('bc_strategies', JSON.stringify(strategies));
                this.refresh();
                App.showToast('Strategy duplicated', 'success');
            }
        }
    },

    deleteStrategy(index) {
        if (!confirm('Delete this strategy?')) return;
        if (this.activeTab === 'my') {
            const strategies = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
            strategies.splice(index, 1);
            localStorage.setItem('bc_strategies', JSON.stringify(strategies));
        } else {
            const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
            const keys = Object.keys(imported);
            if (keys[index]) {
                delete imported[keys[index]];
                localStorage.setItem('bc_imported_strategies', JSON.stringify(imported));
            }
        }
        this.refresh();
        App.showToast('Strategy deleted', 'info');
    },

    importStrategy() {
        StrategyBuilderPage.importStrategy();
    },

    async init() {
        await this.loadActiveBotInfo();
        this.refreshTimer = setInterval(() => this.loadActiveBotInfo(), 15000);
    },

    async loadActiveBotInfo() {
        const el = document.getElementById('activeBotInfo');
        if (!el) return;

        if (!API.connected) {
            el.innerHTML = `<div class="col-12 text-center text-secondary py-3">
                <small>Connect to Freqtrade to see bot status</small>
            </div>`;
            return;
        }

        try {
            const [config, profit, openTrades, count, balance] = await Promise.all([
                API.getConfig().catch(() => null),
                API.getProfit().catch(() => null),
                API.getOpenTrades().catch(() => []),
                API.getTradeCount().catch(() => null),
                API.getBalance().catch(() => null),
            ]);

            const state = config?.state || 'unknown';
            const strategy = config?.strategy || '-';
            const exchange = config?.exchange || '-';
            const pair = config?.trading_mode || 'spot';
            const dryRun = config?.dry_run;
            const openCount = Array.isArray(openTrades) ? openTrades.length : (count?.current || 0);
            const closedCount = count?.closed || 0;
            const totalProfit = profit?.profit_all_coin || 0;
            const profitPct = profit?.profit_all_percent || ((profit?.profit_all_ratio_sum || 0) * 100);
            const stakeCurrency = profit?.stake_currency || config?.stake_currency || 'USDT';
            const totalBalance = balance?.total || 0;

            el.innerHTML = `
                <div class="col-6 col-md-2">
                    <div class="text-secondary small mb-1">Status</div>
                    <span class="badge ${state === 'running' ? 'bg-success' : state === 'stopped' ? 'bg-danger' : 'bg-warning'} fs-6">
                        <i class="bi bi-${state === 'running' ? 'play-circle' : 'stop-circle'} me-1"></i>
                        ${state.charAt(0).toUpperCase() + state.slice(1)}
                    </span>
                    ${dryRun !== undefined ? `<br><span class="badge ${dryRun ? 'bg-warning text-dark' : 'bg-danger'} mt-1">${dryRun ? 'Dry Run' : 'LIVE'}</span>` : ''}
                </div>
                <div class="col-6 col-md-2">
                    <div class="text-secondary small mb-1">Strategy</div>
                    <div class="fw-semibold">${strategy}</div>
                    <small class="text-secondary">${exchange} · ${pair}</small>
                </div>
                <div class="col-4 col-md-2">
                    <div class="text-secondary small mb-1">Open / Closed</div>
                    <div class="fw-semibold">${openCount} <span class="text-secondary">/</span> ${closedCount}</div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="text-secondary small mb-1">Total Profit</div>
                    <div class="fw-semibold ${totalProfit >= 0 ? 'text-profit' : 'text-loss'}">
                        ${totalProfit >= 0 ? '+' : ''}${Components.formatNumber(totalProfit, 2)} ${stakeCurrency}
                    </div>
                    <small class="${profitPct >= 0 ? 'text-profit' : 'text-loss'}">${profitPct >= 0 ? '+' : ''}${Components.formatNumber(profitPct, 2)}%</small>
                </div>
                <div class="col-4 col-md-2">
                    <div class="text-secondary small mb-1">Balance</div>
                    <div class="fw-semibold">${Components.formatNumber(totalBalance, 2)} ${stakeCurrency}</div>
                </div>
                <div class="col-12 col-md-2">
                    <div class="text-secondary small mb-1">Open Trades</div>
                    ${Array.isArray(openTrades) && openTrades.length > 0 ?
                        openTrades.slice(0, 3).map(t => `<div class="small"><span class="fw-semibold">${Components.cleanPairName ? Components.cleanPairName(t.pair) : t.pair}</span> <span class="${(t.profit_ratio || 0) >= 0 ? 'text-profit' : 'text-loss'}">${Components.formatNumber((t.profit_ratio || 0) * 100, 2)}%</span></div>`).join('') +
                        (openTrades.length > 3 ? `<small class="text-secondary">+${openTrades.length - 3} more</small>` : '')
                    : '<small class="text-secondary">None</small>'}
                </div>`;
        } catch (e) {
            console.log('Bot info error:', e.message);
        }
    },

    async controlBot(action) {
        if (!API.connected) {
            App.showToast('Not connected to Freqtrade', 'warning');
            return;
        }
        try {
            if (action === 'start') await API.startBot();
            else if (action === 'stop') await API.stopBot();
            else if (action === 'pause') await API.pauseBot();
            App.showToast(`Bot ${action} command sent`, 'success');
            setTimeout(() => this.loadActiveBotInfo(), 1000);
        } catch (e) {
            App.showToast(`Failed: ${e.message}`, 'error');
        }
    },

    // ========== BOT MANAGEMENT ==========
    _getSavedBots() {
        return JSON.parse(localStorage.getItem('bc_bots') || '[]');
    },

    _saveBots(bots) {
        localStorage.setItem('bc_bots', JSON.stringify(bots));
    },

    _renderBotCards() {
        const bots = this._getSavedBots();
        // Always show the active Freqtrade bot first, then saved bot configs
        let html = `
        <div class="card mb-3" id="activeBotCard">
            <div class="card-body py-2">
                <div class="d-flex align-items-center justify-content-between mb-2">
                    <h6 class="fw-semibold mb-0"><i class="bi bi-broadcast me-2 text-success"></i>Active Freqtrade Bot</h6>
                    <div class="d-flex gap-2" id="robotBotControls">
                        <button class="btn btn-success btn-sm" onclick="RobotsPage.controlBot('start')"><i class="bi bi-play-fill me-1"></i>Start</button>
                        <button class="btn btn-warning btn-sm" onclick="RobotsPage.controlBot('pause')"><i class="bi bi-pause-fill me-1"></i>Pause</button>
                        <button class="btn btn-danger btn-sm" onclick="RobotsPage.controlBot('stop')"><i class="bi bi-stop-fill me-1"></i>Stop</button>
                        <button class="btn btn-outline-info btn-sm" onclick="RobotsPage.editActiveBot()"><i class="bi bi-pencil me-1"></i>Edit</button>
                    </div>
                </div>
                <div class="row g-3" id="activeBotInfo">
                    <div class="col-12 text-center text-secondary py-2"><small>Loading...</small></div>
                </div>
            </div>
        </div>`;

        // Saved bot configs
        bots.forEach((bot, i) => {
            html += `
            <div class="card mb-2">
                <div class="card-body py-2">
                    <div class="d-flex align-items-center justify-content-between">
                        <div class="d-flex align-items-center gap-3">
                            <i class="bi bi-robot text-info"></i>
                            <div>
                                <span class="fw-semibold">${bot.name || 'Bot ' + (i + 1)}</span>
                                <div class="d-flex gap-2 mt-1 flex-wrap">
                                    <span class="badge bg-secondary bg-opacity-25 text-secondary">${bot.exchange || '-'}</span>
                                    <span class="badge bg-info bg-opacity-25 text-info">${bot.timeframe || '5m'}</span>
                                    <span class="badge bg-success bg-opacity-25 text-success">${bot.strategy || '-'}</span>
                                    <span class="badge bg-warning bg-opacity-25 text-warning">${bot.max_open_trades || 3} trades</span>
                                    ${bot.pairs ? `<span class="badge bg-primary bg-opacity-25 text-primary">${bot.pairs.split(',').length} pairs</span>` : ''}
                                </div>
                            </div>
                        </div>
                        <div class="d-flex gap-2">
                            <button class="btn btn-outline-success btn-sm" onclick="RobotsPage.deployBot(${i})" title="Deploy to Freqtrade">
                                <i class="bi bi-cloud-upload me-1"></i>Deploy
                            </button>
                            <button class="btn btn-outline-info btn-sm" onclick="RobotsPage.editBot(${i})" title="Edit">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-outline-danger btn-sm" onclick="RobotsPage.deleteBot(${i})" title="Delete">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>`;
        });

        return html;
    },

    addBot() {
        this._showBotModal({
            name: '',
            exchange: 'bybit',
            trading_mode: 'futures',
            strategy: '',
            timeframe: '5m',
            pairs: 'BTC/USDT:USDT',
            max_open_trades: 3,
            stake_amount: 'unlimited',
            dry_run_wallet: 1000,
        }, -1);
    },

    async editActiveBot() {
        if (!API.connected) { App.showToast('Connect to Freqtrade first', 'warning'); return; }
        try {
            const config = await API.getConfig();
            const whitelist = await API.getWhitelist().catch(() => ({}));
            this._showBotModal({
                name: 'Active Bot',
                exchange: config.exchange || 'bybit',
                trading_mode: config.trading_mode || 'spot',
                strategy: config.strategy || '',
                timeframe: config.timeframe || '5m',
                pairs: (whitelist.whitelist || []).join(', '),
                max_open_trades: config.max_open_trades || 3,
                stake_amount: config.stake_amount || 'unlimited',
                dry_run_wallet: config.dry_run_wallet || 1000,
            }, 'active');
        } catch (e) {
            App.showToast(`Error: ${e.message}`, 'error');
        }
    },

    editBot(index) {
        const bots = this._getSavedBots();
        if (bots[index]) this._showBotModal(bots[index], index);
    },

    deleteBot(index) {
        if (!confirm('Delete this bot configuration?')) return;
        const bots = this._getSavedBots();
        bots.splice(index, 1);
        this._saveBots(bots);
        this.refresh();
        App.showToast('Bot deleted', 'info');
    },

    async deployBot(index) {
        const bots = this._getSavedBots();
        const bot = bots[index];
        if (!bot) return;
        if (!API.connected) { App.showToast('Connect to Freqtrade first', 'warning'); return; }
        if (!confirm(`Deploy "${bot.name}" config to Freqtrade? This will reload the configuration.`)) return;
        // For now, show what would be deployed
        App.showToast(`Bot "${bot.name}" config ready. Use Configuration page to apply settings.`, 'info');
    },

    _showBotModal(bot, index) {
        let modal = document.getElementById('botEditModal');
        if (modal) modal.remove();

        const isNew = index === -1;
        const isActive = index === 'active';
        const title = isActive ? 'Edit Active Bot' : (isNew ? 'Add New Bot' : `Edit ${bot.name || 'Bot'}`);

        modal = document.createElement('div');
        modal.id = 'botEditModal';
        modal.className = 'modal fade';
        modal.tabIndex = -1;
        const inp = 'style="background:var(--bc-bg);border-color:var(--bc-border);color:var(--bc-text)"';
        modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content" style="background:var(--bc-card);border:1px solid var(--bc-border);color:var(--bc-text)">
                <div class="modal-header border-secondary">
                    <h5 class="modal-title"><i class="bi bi-robot me-2"></i>${title}</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label small text-secondary">Bot Name</label>
                        <input type="text" class="form-control form-control-sm" id="botName" value="${bot.name || ''}" placeholder="My Bot" ${inp}>
                    </div>
                    <div class="row g-2 mb-3">
                        <div class="col-6">
                            <label class="form-label small text-secondary">Exchange</label>
                            <select class="form-select form-select-sm" id="botExchange" ${inp}>
                                <option value="bybit" ${bot.exchange === 'bybit' ? 'selected' : ''}>Bybit</option>
                                <option value="binance" ${bot.exchange === 'binance' ? 'selected' : ''}>Binance</option>
                                <option value="okx" ${bot.exchange === 'okx' ? 'selected' : ''}>OKX</option>
                                <option value="kraken" ${bot.exchange === 'kraken' ? 'selected' : ''}>Kraken</option>
                                <option value="gate" ${bot.exchange === 'gate' ? 'selected' : ''}>Gate.io</option>
                            </select>
                        </div>
                        <div class="col-6">
                            <label class="form-label small text-secondary">Trading Mode</label>
                            <select class="form-select form-select-sm" id="botTradingMode" ${inp}>
                                <option value="spot" ${bot.trading_mode === 'spot' ? 'selected' : ''}>Spot</option>
                                <option value="futures" ${bot.trading_mode === 'futures' ? 'selected' : ''}>Futures</option>
                            </select>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label small text-secondary">Strategy</label>
                        <select class="form-select form-select-sm" id="botStrategy" ${inp}>
                            <option value="">-- Select --</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label small text-secondary">Coin Pairs <small class="text-secondary">(comma separated)</small></label>
                        <input type="text" class="form-control form-control-sm" id="botPairs" value="${bot.pairs || ''}" placeholder="BTC/USDT:USDT, ETH/USDT:USDT" ${inp}>
                    </div>
                    <div class="row g-2 mb-3">
                        <div class="col-4">
                            <label class="form-label small text-secondary">Timeframe</label>
                            <select class="form-select form-select-sm" id="botTimeframe" ${inp}>
                                <option value="1m" ${bot.timeframe === '1m' ? 'selected' : ''}>1m</option>
                                <option value="5m" ${bot.timeframe === '5m' ? 'selected' : ''}>5m</option>
                                <option value="15m" ${bot.timeframe === '15m' ? 'selected' : ''}>15m</option>
                                <option value="1h" ${bot.timeframe === '1h' ? 'selected' : ''}>1h</option>
                                <option value="4h" ${bot.timeframe === '4h' ? 'selected' : ''}>4h</option>
                                <option value="1d" ${bot.timeframe === '1d' ? 'selected' : ''}>1d</option>
                            </select>
                        </div>
                        <div class="col-4">
                            <label class="form-label small text-secondary">Max Trades</label>
                            <input type="number" class="form-control form-control-sm" id="botMaxTrades" value="${bot.max_open_trades || 3}" ${inp}>
                        </div>
                        <div class="col-4">
                            <label class="form-label small text-secondary">Wallet</label>
                            <input type="number" class="form-control form-control-sm" id="botWallet" value="${bot.dry_run_wallet || 1000}" ${inp}>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label small text-secondary">Stake Amount</label>
                        <input type="text" class="form-control form-control-sm" id="botStakeAmount" value="${bot.stake_amount || 'unlimited'}" ${inp}>
                    </div>
                </div>
                <div class="modal-footer border-secondary">
                    ${!isNew && !isActive ? `<button class="btn btn-outline-danger btn-sm me-auto" onclick="RobotsPage.deleteBot(${index}); bootstrap.Modal.getInstance(document.getElementById('botEditModal')).hide()">
                        <i class="bi bi-trash me-1"></i>Delete
                    </button>` : ''}
                    <button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
                    <button class="btn btn-success btn-sm" onclick="RobotsPage._saveBotFromModal('${index}')">
                        <i class="bi bi-check-lg me-1"></i>${isNew ? 'Add Bot' : 'Save'}
                    </button>
                </div>
            </div>
        </div>`;

        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        modal.addEventListener('hidden.bs.modal', () => modal.remove());

        // Load strategies into select
        this._loadStrategiesForModal(bot.strategy);
    },

    async _loadStrategiesForModal(currentStrategy) {
        const sel = document.getElementById('botStrategy');
        if (!sel) return;

        // Add imported strategies
        const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
        Object.keys(imported).forEach(name => {
            const opt = document.createElement('option');
            opt.value = name; opt.textContent = name;
            if (name === currentStrategy) opt.selected = true;
            sel.appendChild(opt);
        });

        // Add strategies from Freqtrade
        if (API.connected) {
            try {
                const strats = await API.getStrategies();
                (strats.strategies || []).forEach(name => {
                    if (!imported[name]) {
                        const opt = document.createElement('option');
                        opt.value = name; opt.textContent = name;
                        if (name === currentStrategy) opt.selected = true;
                        sel.appendChild(opt);
                    }
                });
            } catch (e) {}
        }
    },

    _saveBotFromModal(indexStr) {
        const bot = {
            name: document.getElementById('botName')?.value || 'My Bot',
            exchange: document.getElementById('botExchange')?.value || 'bybit',
            trading_mode: document.getElementById('botTradingMode')?.value || 'futures',
            strategy: document.getElementById('botStrategy')?.value || '',
            pairs: document.getElementById('botPairs')?.value || '',
            timeframe: document.getElementById('botTimeframe')?.value || '5m',
            max_open_trades: parseInt(document.getElementById('botMaxTrades')?.value) || 3,
            dry_run_wallet: parseFloat(document.getElementById('botWallet')?.value) || 1000,
            stake_amount: document.getElementById('botStakeAmount')?.value || 'unlimited',
            savedAt: new Date().toISOString(),
        };

        if (indexStr === 'active') {
            // For active bot, just show info - actual config changes need Configuration page
            App.showToast('Active bot settings saved locally', 'info');
        } else {
            const bots = this._getSavedBots();
            const index = parseInt(indexStr);
            if (index === -1) {
                bots.push(bot);
            } else {
                bots[index] = bot;
            }
            this._saveBots(bots);
        }

        bootstrap.Modal.getInstance(document.getElementById('botEditModal'))?.hide();
        this.refresh();
        App.showToast(indexStr === '-1' ? 'Bot added' : 'Bot saved', 'success');
    },

    refresh() {
        const container = document.getElementById('pageContainer');
        if (container) container.innerHTML = this.render();
        this.loadActiveBotInfo();
    },

    destroy() {
        if (this.refreshTimer) { clearInterval(this.refreshTimer); this.refreshTimer = null; }
    }
};

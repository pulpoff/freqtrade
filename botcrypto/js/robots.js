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

    async deleteStrategy(index) {
        if (!await App.confirm('Delete this strategy?', { title: 'Delete Strategy', confirmText: 'Delete' })) return;
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
            // Try engine status first (for managed strategies)
            const engineStatus = await API.getEngineStatus().catch(() => null);

            if (engineStatus && engineStatus.engine_mode) {
                // Engine mode - show managed strategies
                const strategies = engineStatus.strategies || [];
                if (strategies.length === 0) {
                    el.innerHTML = `<div class="col-12 text-center text-secondary py-3">
                        <i class="bi bi-robot fs-4 d-block mb-1"></i>
                        <small>No strategies deployed. Create a bot config and click Deploy to start trading.</small>
                    </div>`;
                } else {
                    el.innerHTML = strategies.map(s => {
                        const statusColor = s.status === 'running' ? 'success' : s.status === 'error' ? 'danger' : s.status === 'starting' ? 'warning' : 'secondary';
                        const statusIcon = s.status === 'running' ? 'play-circle' : s.status === 'error' ? 'exclamation-triangle' : s.status === 'starting' ? 'hourglass-split' : 'stop-circle';
                        return `
                        <div class="col-12 mb-2">
                            <div class="d-flex align-items-center justify-content-between p-2 rounded" style="background:var(--bc-bg);border:1px solid var(--bc-border);cursor:pointer"
                                onclick="RobotsPage.openBotDetail('${s.strategy_id}', '${(s.strategy_name || '').replace(/'/g, "\\'")}', ${JSON.stringify(s.pairs || []).replace(/"/g, '&quot;')}, '${s.exchange}', '${s.trading_mode}', ${s.dry_run})">
                                <div class="d-flex align-items-center gap-3">
                                    <span class="badge bg-${statusColor}"><i class="bi bi-${statusIcon} me-1"></i>${s.status}</span>
                                    <div>
                                        <span class="fw-semibold">${s.strategy_name}</span>
                                        <div class="d-flex gap-1 mt-1">
                                            <span class="badge bg-secondary" style="font-size:10px">${s.exchange}</span>
                                            <span class="badge bg-info" style="font-size:10px">${s.trading_mode}</span>
                                            <span class="badge ${s.dry_run ? 'bg-warning text-dark' : 'bg-danger'}" style="font-size:10px">${s.dry_run ? 'Dry' : 'LIVE'}</span>
                                            ${(s.pairs || []).slice(0, 2).map(p => `<span class="badge bg-primary" style="font-size:10px">${p.split('/')[0]}</span>`).join('')}
                                            ${(s.pairs || []).length > 2 ? `<span class="badge bg-secondary" style="font-size:10px">+${s.pairs.length - 2}</span>` : ''}
                                        </div>
                                    </div>
                                </div>
                                <div class="d-flex gap-1" onclick="event.stopPropagation()">
                                    ${s.status === 'running' || s.status === 'starting' ?
                                        `<button class="btn btn-danger btn-sm" onclick="RobotsPage.controlBot('stop', '${s.strategy_id}')"><i class="bi bi-stop-fill"></i></button>` :
                                        `<button class="btn btn-success btn-sm" onclick="RobotsPage.controlBot('start', '${s.strategy_id}')"><i class="bi bi-play-fill"></i></button>`
                                    }
                                    ${s.status === 'stopped' || s.status === 'error' ?
                                        `<button class="btn btn-outline-danger btn-sm" onclick="RobotsPage.removeManagedStrategy('${s.strategy_id}')"><i class="bi bi-trash"></i></button>` : ''}
                                </div>
                            </div>
                            ${s.error ? `<div class="text-danger small mt-1 ps-2" style="max-height:60px;overflow:auto"><pre class="mb-0 small">${s.error.substring(0, 200)}</pre></div>` : ''}
                        </div>`;
                    }).join('');
                }
                return;
            }

            // Legacy trade mode
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

    async removeManagedStrategy(strategyId) {
        if (!await App.confirm('Remove this managed strategy?', { title: 'Remove Strategy', confirmText: 'Remove' })) return;
        try {
            await API.removeManagedStrategy(strategyId);
            App.showToast('Strategy removed', 'info');
            this.loadActiveBotInfo();
        } catch (e) {
            App.showToast(`Failed: ${e.message}`, 'error');
        }
    },

    async controlBot(action, strategyId) {
        if (!API.connected) {
            App.showToast('Not connected to Freqtrade', 'warning');
            return;
        }
        try {
            if (strategyId) {
                // Engine mode: use StrategyManager API
                if (action === 'start') {
                    await API.startManagedStrategy(strategyId);
                } else if (action === 'stop') {
                    await API.stopManagedStrategy(strategyId);
                }
                App.showToast(`Strategy ${action} command sent`, 'success');
            } else {
                // Legacy trade mode: use standard RPC
                if (action === 'start') {
                    try {
                        await API.startBot();
                    } catch (e) {
                        if (e.message?.includes('not in the correct state')) {
                            App.showToast('Bot is in webserver mode. Use Deploy to start a strategy.', 'warning');
                            return;
                        }
                        throw e;
                    }
                } else if (action === 'stop') {
                    await API.stopBot();
                } else if (action === 'pause') {
                    await API.pauseBot();
                }
                App.showToast(`Bot ${action} command sent`, 'success');
            }
            setTimeout(() => this.loadActiveBotInfo(), 1500);
        } catch (e) {
            App.showToast(`Failed: ${e.message || 'Unknown error'}`, 'error');
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
                                    <span class="badge" style="background:rgba(255,255,255,0.12);color:#fff">${bot.exchange || '-'}</span>
                                    <span class="badge" style="background:rgba(74,144,217,0.3);color:#fff">${bot.timeframe || '5m'}</span>
                                    <span class="badge" style="background:rgba(45,212,168,0.3);color:#fff">${bot.strategy || '-'}</span>
                                    <span class="badge" style="background:rgba(245,166,35,0.3);color:#fff">${bot.max_open_trades || 3} trades</span>
                                    ${bot.pairs ? `<span class="badge" style="background:rgba(74,144,217,0.3);color:#fff">${bot.pairs.split(',').length} pairs</span>` : ''}
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
        if (!API.connected) { App.showToast('Reconnecting...', 'info'); await App.reconnect(); if (!API.connected) { App.showToast('Could not connect to Freqtrade', 'error'); return; } }
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

    async deleteBot(index) {
        if (!await App.confirm('Delete this bot configuration?', { title: 'Delete Bot', confirmText: 'Delete' })) return;
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
        if (!API.connected) { App.showToast('Reconnecting...', 'info'); await App.reconnect(); if (!API.connected) { App.showToast('Could not connect to Freqtrade', 'error'); return; } }
        if (!bot.strategy) { App.showToast('Select a strategy first', 'warning'); return; }
        if (!await App.confirm(`Deploy and start "<b>${bot.name}</b>" with strategy <b>${bot.strategy}</b>?`, { title: 'Deploy Bot', confirmText: 'Deploy', confirmClass: 'btn-success', icon: 'bi-rocket-takeoff text-success' })) return;

        const strategyId = `${bot.name || 'bot'}-${Date.now()}`.replace(/\s+/g, '-').toLowerCase();
        const pairs = (bot.pairs || 'BTC/USDT:USDT').split(',').map(p => p.trim()).filter(Boolean);

        try {
            // Register strategy with StrategyManager
            const config = {
                strategy_id: strategyId,
                strategy: bot.strategy,
                exchange: {
                    name: bot.exchange || 'bybit',
                    pair_whitelist: pairs,
                },
                stake_currency: 'USDT',
                stake_amount: bot.stake_amount === 'unlimited' ? 'unlimited' : parseFloat(bot.stake_amount) || 'unlimited',
                max_open_trades: bot.max_open_trades || 3,
                dry_run: true,
                dry_run_wallet: bot.dry_run_wallet || 1000,
                trading_mode: bot.trading_mode || 'futures',
                timeframe: bot.timeframe || '5m',
                extra_config: {},
            };

            if (bot.freqaimodel) {
                config.extra_config.freqai = { enabled: true, model: bot.freqaimodel };
            }

            App.showToast('Registering strategy...', 'info');
            await API.addManagedStrategy(config);

            // Start it
            App.showToast('Starting strategy...', 'info');
            await API.startManagedStrategy(strategyId);

            // Save strategy_id back to bot config
            bots[index].strategy_id = strategyId;
            bots[index].deployed = true;
            this._saveBots(bots);

            App.showToast(`"${bot.name}" deployed and starting!`, 'success');
            setTimeout(() => this.loadActiveBotInfo(), 2000);
            this.refresh();
        } catch (e) {
            App.showToast(`Deploy failed: ${e.message}`, 'error');
        }
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
                        <label class="form-label small text-secondary">FreqAI Model</label>
                        <select class="form-select form-select-sm" id="botFreqaiModel" ${inp}>
                            <option value="" ${!bot.freqaimodel ? 'selected' : ''}>None</option>
                            <option value="LightGBMRegressor" ${bot.freqaimodel === 'LightGBMRegressor' ? 'selected' : ''}>LightGBMRegressor</option>
                            <option value="LightGBMClassifier" ${bot.freqaimodel === 'LightGBMClassifier' ? 'selected' : ''}>LightGBMClassifier</option>
                            <option value="XGBoostRegressor" ${bot.freqaimodel === 'XGBoostRegressor' ? 'selected' : ''}>XGBoostRegressor</option>
                            <option value="XGBoostClassifier" ${bot.freqaimodel === 'XGBoostClassifier' ? 'selected' : ''}>XGBoostClassifier</option>
                            <option value="XGBoostRFRegressor" ${bot.freqaimodel === 'XGBoostRFRegressor' ? 'selected' : ''}>XGBoostRFRegressor</option>
                            <option value="SKLearnRandomForestClassifier" ${bot.freqaimodel === 'SKLearnRandomForestClassifier' ? 'selected' : ''}>SKLearnRandomForest</option>
                            <option value="PyTorchMLPRegressor" ${bot.freqaimodel === 'PyTorchMLPRegressor' ? 'selected' : ''}>PyTorchMLPRegressor</option>
                            <option value="ReinforcementLearner" ${bot.freqaimodel === 'ReinforcementLearner' ? 'selected' : ''}>ReinforcementLearner</option>
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
            freqaimodel: document.getElementById('botFreqaiModel')?.value || '',
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
        this._cleanupBotDetail();
    },

    // ========== BOT DETAIL MODAL ==========
    _bdChart: null,
    _bdCandleSeries: null,
    _bdVolumeSeries: null,
    _bdIndicators: {},
    _bdRefreshTimer: null,
    _bdStrategyId: null,
    _bdPairs: [],
    _bdCurrentPair: '',
    _bdCurrentTf: '5m',
    _bdStrategyName: '',

    _cleanupBotDetail() {
        if (this._bdRefreshTimer) { clearInterval(this._bdRefreshTimer); this._bdRefreshTimer = null; }
        if (this._bdChart) { try { this._bdChart.remove(); } catch(e) {} this._bdChart = null; }
        this._bdCandleSeries = null;
        this._bdVolumeSeries = null;
        this._bdIndicators = {};
    },

    async openBotDetail(strategyId, strategyName, pairs, exchange, tradingMode, dryRun) {
        this._bdStrategyId = strategyId;
        this._bdStrategyName = strategyName;
        this._bdPairs = pairs || [];
        this._bdCurrentPair = this._bdPairs[0] || 'BTC/USDT:USDT';
        this._cleanupBotDetail();

        // Build modal HTML
        const el = document.createElement('div');
        el.id = 'botDetailWrapper';
        el.innerHTML = `
        <div class="modal fade" id="botDetailModal" tabindex="-1">
            <div class="modal-dialog modal-fullscreen">
                <div class="modal-content bg-dark">
                    <div class="modal-header border-secondary py-2">
                        <div class="d-flex align-items-center gap-3">
                            <h6 class="modal-title mb-0"><i class="bi bi-robot me-2"></i>${strategyName}</h6>
                            <span class="badge bg-success"><i class="bi bi-play-circle me-1"></i>running</span>
                            <span class="badge" style="background:rgba(255,255,255,0.12);color:#fff">${exchange}</span>
                            <span class="badge" style="background:rgba(74,144,217,0.3);color:#fff">${tradingMode}</span>
                            <span class="badge" style="background:${dryRun ? 'rgba(245,166,35,0.3)' : 'rgba(231,76,94,0.3)'};color:#fff">${dryRun ? 'Dry' : 'LIVE'}</span>
                        </div>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body p-2" style="overflow-y:auto">
                        <!-- Stats Row -->
                        <div class="row g-2 mb-2" id="bdStats">
                            <div class="col-2"><div class="card"><div class="card-body py-2 text-center">
                                <div class="stat-value" id="bdProfit">-</div><div class="stat-label">Profit</div>
                            </div></div></div>
                            <div class="col-2"><div class="card"><div class="card-body py-2 text-center">
                                <div class="stat-value" id="bdProfitPct">-</div><div class="stat-label">Profit %</div>
                            </div></div></div>
                            <div class="col-2"><div class="card"><div class="card-body py-2 text-center">
                                <div class="stat-value" id="bdTradeCount">0</div><div class="stat-label">Trades</div>
                            </div></div></div>
                            <div class="col-2"><div class="card"><div class="card-body py-2 text-center">
                                <div class="stat-value" id="bdWinRate">-</div><div class="stat-label">Win Rate</div>
                            </div></div></div>
                            <div class="col-2"><div class="card"><div class="card-body py-2 text-center">
                                <div class="stat-value" id="bdOpenTrades">0</div><div class="stat-label">Open</div>
                            </div></div></div>
                            <div class="col-2"><div class="card"><div class="card-body py-2 text-center">
                                <div class="stat-value" id="bdAvgProfit">-</div><div class="stat-label">Avg Profit</div>
                            </div></div></div>
                        </div>

                        <!-- Chart -->
                        <div class="card mb-2">
                            <div class="card-body p-2">
                                <div class="d-flex align-items-center justify-content-between flex-wrap gap-2 border-bottom border-secondary pb-2 mb-2">
                                    <div class="d-flex align-items-center gap-2 flex-wrap">
                                        <select class="form-select form-select-sm" style="width:140px" id="bdPairSelect"
                                            onchange="RobotsPage._bdChangePair(this.value)">
                                            ${this._bdPairs.map(p => `<option value="${p}" ${p === this._bdCurrentPair ? 'selected' : ''}>${Components.cleanPairName ? Components.cleanPairName(p) : p}</option>`).join('')}
                                        </select>
                                        <span id="bdTfBtns">${Components.timeframeSelector(this._bdCurrentTf, 'RobotsPage._bdChangeTf')}</span>
                                        <button class="btn btn-sm btn-outline-secondary" onclick="RobotsPage._bdShowIndicators()">
                                            <i class="bi bi-activity me-1"></i> Indicators
                                        </button>
                                    </div>
                                    <div class="d-flex align-items-center gap-2">
                                        <small class="text-secondary" id="bdChartInfo"><i class="bi bi-bar-chart"></i> Loading...</small>
                                        <button class="btn btn-sm btn-link text-secondary" onclick="RobotsPage._bdLoadChart()"><i class="bi bi-arrow-clockwise"></i></button>
                                    </div>
                                </div>
                                <div id="bdChart" style="height:450px"></div>
                            </div>
                        </div>

                        <!-- Trades -->
                        <div class="card">
                            <div class="card-body p-2">
                                <h6 class="fw-semibold mb-2"><i class="bi bi-arrow-left-right me-2"></i>Open Trades</h6>
                                <div id="bdTradesTable"><div class="text-center text-secondary py-3">Loading trades...</div></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
        document.body.appendChild(el);

        const modal = new bootstrap.Modal(el.querySelector('.modal'));
        el.querySelector('.modal').addEventListener('hidden.bs.modal', () => {
            this._cleanupBotDetail();
            el.remove();
        });
        modal.show();

        // Initialize chart & load data
        setTimeout(() => {
            this._bdInitChart();
            this._bdLoadData();
            this._bdRefreshTimer = setInterval(() => this._bdLoadData(), 15000);
        }, 300);
    },

    _bdInitChart() {
        const container = document.getElementById('bdChart');
        if (!container || typeof LightweightCharts === 'undefined') return;
        container.innerHTML = '';

        this._bdChart = Components.createChart(container, {
            handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
            handleScale: { mouseWheel: true, axisPressedMouseMove: true, pinch: true },
        });
        if (!this._bdChart) return;

        this._bdCandleSeries = this._bdChart.addCandlestickSeries({
            upColor: '#2dd4a8', downColor: '#e74c5e',
            borderUpColor: '#2dd4a8', borderDownColor: '#e74c5e',
            wickUpColor: '#2dd4a8', wickDownColor: '#e74c5e',
        });

        this._bdVolumeSeries = this._bdChart.addHistogramSeries({
            color: '#4a90d9', priceFormat: { type: 'volume' }, priceScaleId: '',
        });
        this._bdChart.priceScale('').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

        this._bdLoadChart();
    },

    async _bdLoadChart() {
        if (!this._bdCandleSeries) return;
        const pair = this._bdCurrentPair;
        const tf = this._bdCurrentTf;
        const info = document.getElementById('bdChartInfo');

        if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair}, ${tf} - <span class="spinner-border spinner-border-sm"></span>`;

        try {
            let candles = null, signals = [];

            // Try pair_candles first (strategy-analyzed data with signals)
            try {
                const data = await API.getPairCandles(pair, tf, 2000);
                if (data?.columns && data?.data?.length > 0) {
                    candles = API.parseCandleData(data);
                    signals = API.parseSignals(data);
                }
            } catch(e) {}

            // Fallback to pair_history
            if (!candles || candles.length === 0) {
                try {
                    const now = new Date();
                    const daysBack = { '1m': 1, '5m': 3, '15m': 7, '1h': 30, '4h': 60, '1d': 180 };
                    const days = daysBack[tf] || 3;
                    const start = new Date(now.getTime() - days * 86400000);
                    const timerange = `${start.toISOString().slice(0,10).replace(/-/g,'')}-${now.toISOString().slice(0,10).replace(/-/g,'')}`;
                    const data = await API.getPairHistory(pair, tf, timerange, this._bdStrategyName);
                    if (data?.columns && data?.data?.length > 0) {
                        candles = API.parseCandleData(data);
                        signals = API.parseSignals(data);
                    }
                } catch(e) {}
            }

            // Fallback to raw OHLCV
            if (!candles || candles.length === 0) {
                try {
                    const data = await API.getPairOhlcv(pair, tf, 2000);
                    if (data?.columns && data?.data?.length > 0) {
                        candles = API.parseCandleData(data);
                    }
                } catch(e) {}
            }

            if (candles && candles.length > 0) {
                this._bdCandles = candles;
                this._bdCandleSeries.setData(candles);

                const volumes = candles.map(c => ({
                    time: c.time, value: c.volume || 0,
                    color: c.close >= c.open ? 'rgba(45,212,168,0.3)' : 'rgba(231,76,94,0.3)'
                }));
                if (this._bdVolumeSeries) this._bdVolumeSeries.setData(volumes);

                // Signal markers (B/S from strategy analysis)
                if (signals.length > 0) {
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
                    this._bdCandleSeries.setMarkers(markers);
                }

                this._bdChart.timeScale().fitContent();

                // Re-apply active indicators
                for (const [id, ind] of Object.entries(this._bdIndicators)) {
                    if (ind.enabled) this._bdToggleIndicator(id, true);
                }

                if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> ${pair} · ${tf} · ${candles.length} candles`;
            } else {
                if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> No data for ${pair}`;
            }
        } catch(e) {
            if (info) info.innerHTML = `<i class="bi bi-bar-chart"></i> Error loading chart`;
        }
    },

    _bdChangePair(pair) {
        this._bdCurrentPair = pair;
        this._bdCandleSeries?.setData([]);
        this._bdCandleSeries?.setMarkers([]);
        this._bdLoadChart();
    },

    _bdChangeTf(tf) {
        this._bdCurrentTf = tf;
        const btns = document.getElementById('bdTfBtns');
        if (btns) btns.innerHTML = Components.timeframeSelector(tf, 'RobotsPage._bdChangeTf');
        this._bdCandleSeries?.setData([]);
        this._bdCandleSeries?.setMarkers([]);
        this._bdLoadChart();
    },

    async _bdLoadData() {
        if (!this._bdStrategyId) return;
        try {
            const [tradesData, profitData] = await Promise.all([
                API.getManagedStrategyTrades(this._bdStrategyId).catch(() => ({ trades: [] })),
                API.getManagedStrategyProfit(this._bdStrategyId).catch(() => ({})),
            ]);

            // Update stats
            const trades = tradesData.trades || [];
            const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
            const profit = profitData.profit_all_coin || profitData.profit_closed_coin || 0;
            const profitPct = profitData.profit_all_percent || profitData.profit_closed_percent || 0;
            const tradeCount = profitData.trade_count || profitData.closed_trade_count || 0;
            const winRate = profitData.winning_trades !== undefined && tradeCount > 0
                ? ((profitData.winning_trades / tradeCount) * 100).toFixed(1) + '%' : '-';
            const avgProfit = profitData.avg_profit || 0;

            setEl('bdProfit', `${profit >= 0 ? '+' : ''}${parseFloat(profit).toFixed(2)}`);
            setEl('bdProfitPct', `${profitPct >= 0 ? '+' : ''}${parseFloat(profitPct).toFixed(2)}%`);
            setEl('bdTradeCount', tradeCount);
            setEl('bdWinRate', winRate);
            setEl('bdOpenTrades', trades.length);
            setEl('bdAvgProfit', `${avgProfit >= 0 ? '+' : ''}${parseFloat(avgProfit).toFixed(2)}%`);

            // Color profit
            const profitEl = document.getElementById('bdProfit');
            if (profitEl) profitEl.style.color = profit >= 0 ? 'var(--bc-green)' : 'var(--bc-red)';
            const pctEl = document.getElementById('bdProfitPct');
            if (pctEl) pctEl.style.color = profitPct >= 0 ? 'var(--bc-green)' : 'var(--bc-red)';

            // Trades table
            const tt = document.getElementById('bdTradesTable');
            if (tt) {
                if (trades.length === 0) {
                    tt.innerHTML = '<div class="text-center text-secondary py-3"><i class="bi bi-inbox me-2"></i>No open trades</div>';
                } else {
                    tt.innerHTML = `<div class="table-responsive"><table class="table table-sm table-hover mb-0">
                        <thead><tr><th>Pair</th><th>Side</th><th>Amount</th><th>Open Rate</th><th>Current</th><th>Profit</th><th>Opened</th></tr></thead>
                        <tbody>${trades.map(t => {
                            const pct = ((t.profit_pct || 0) * 100);
                            const isWin = pct >= 0;
                            return `<tr>
                                <td class="fw-semibold">${t.pair}</td>
                                <td><span class="badge ${t.is_short ? 'bg-danger' : 'bg-success'}">${t.is_short ? 'Short' : 'Long'}</span></td>
                                <td>${parseFloat(t.amount || 0).toFixed(4)}</td>
                                <td>${parseFloat(t.open_rate || 0).toFixed(6)}</td>
                                <td>${parseFloat(t.current_rate || 0).toFixed(6)}</td>
                                <td class="fw-bold" style="color:${isWin ? 'var(--bc-green)' : 'var(--bc-red)'}">${isWin ? '+' : ''}${pct.toFixed(2)}%</td>
                                <td class="text-secondary small">${t.open_date ? new Date(t.open_date).toLocaleString() : '-'}</td>
                            </tr>`;
                        }).join('')}</tbody></table></div>`;
                }
            }
        } catch(e) {
            console.error('Bot detail data load error:', e);
        }
    },

    // ===== Indicators for bot detail =====
    _bdShowIndicators() {
        // Reuse DashboardPage's indicator definitions
        const defs = DashboardPage._indicatorDefs || [];
        const categories = {};
        defs.forEach(d => {
            if (!categories[d.category]) categories[d.category] = [];
            categories[d.category].push(d);
        });

        const el = document.createElement('div');
        el.innerHTML = `
        <div class="modal fade" id="bdIndicatorsModal" tabindex="-1">
            <div class="modal-dialog modal-lg modal-dialog-scrollable">
                <div class="modal-content bg-dark border-secondary">
                    <div class="modal-header border-secondary">
                        <h6 class="modal-title"><i class="bi bi-activity me-2"></i>Indicators</h6>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        ${Object.entries(categories).map(([cat, items]) => `
                            <h6 class="fw-semibold text-secondary small text-uppercase mt-3 mb-2">${cat}</h6>
                            <div class="row g-2">
                                ${items.map(d => `
                                    <div class="col-6 col-md-4 col-lg-3">
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" id="bdInd_${d.id}"
                                                ${this._bdIndicators[d.id]?.enabled ? 'checked' : ''}
                                                onchange="RobotsPage._bdToggleIndicator('${d.id}', this.checked)">
                                            <label class="form-check-label small" for="bdInd_${d.id}">
                                                <span style="color:${d.color}">●</span> ${d.name}
                                            </label>
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        </div>`;
        document.body.appendChild(el);
        const modal = new bootstrap.Modal(el.querySelector('.modal'));
        el.querySelector('.modal').addEventListener('hidden.bs.modal', () => el.remove());
        modal.show();
    },

    _bdToggleIndicator(id, enabled) {
        const defs = DashboardPage._indicatorDefs || [];
        const def = defs.find(d => d.id === id);
        if (!def || !this._bdChart || !this._bdCandles) return;

        // Remove existing series
        if (this._bdIndicators[id]?.series) {
            const series = this._bdIndicators[id].series;
            (Array.isArray(series) ? series : [series]).forEach(s => {
                try { this._bdChart.removeSeries(s); } catch(e) {}
            });
        }

        if (!enabled) {
            this._bdIndicators[id] = { enabled: false, series: null };
            return;
        }

        // Use DashboardPage's calc methods - they expect candle objects with .close/.high/.low/.volume/.time
        const candles = this._bdCandles;
        const dp = DashboardPage;
        const scaleId = def.overlay ? undefined : id;
        const lineOpts = (color, extra = {}) => ({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, ...extra });
        const oscOpts = (color, extra = {}) => ({ ...lineOpts(color, extra), priceScaleId: scaleId, lastValueVisible: true });
        const setOscScale = () => {
            if (scaleId) this._bdChart.priceScale(scaleId).applyOptions({ scaleMargins: { top: 0.85, bottom: 0 }, borderVisible: false });
        };
        const addLine = (data, opts) => { const s = this._bdChart.addLineSeries(opts); s.setData(data); return s; };
        const addHist = (data, opts) => { const s = this._bdChart.addHistogramSeries(opts); s.setData(data); return s; };

        let series = null;
        try {
        // ========== MOVING AVERAGES ==========
        if (def.type === 'ema' || def.type === 'sma') {
            series = addLine(dp._calcMA(candles, def.period, def.type), lineOpts(def.color));

        } else if (def.type === 'wma') {
            series = addLine(dp._calcWMA(candles, def.period), lineOpts(def.color));

        } else if (def.type === 'dema') {
            series = addLine(dp._calcDEMA(candles, def.period), lineOpts(def.color));

        } else if (def.type === 'tema') {
            series = addLine(dp._calcTEMA(candles, def.period), lineOpts(def.color));

        } else if (def.type === 'kama') {
            series = addLine(dp._calcKAMA(candles, def.period), lineOpts(def.color));

        } else if (def.type === 'hma') {
            series = addLine(dp._calcHMA(candles, def.period), lineOpts(def.color));

        } else if (def.type === 'vwma') {
            series = addLine(dp._calcVWMA(candles, def.period), lineOpts(def.color));

        // ========== OVERLAYS ==========
        } else if (def.type === 'bb') {
            const bb = dp._calcBB(candles, def.period);
            series = [
                addLine(bb.upper, lineOpts(def.color, { lineStyle: 2 })),
                addLine(bb.lower, lineOpts(def.color, { lineStyle: 2 })),
                addLine(bb.mid,   lineOpts(def.color, { lineStyle: 1 })),
            ];

        } else if (def.type === 'kc') {
            const kc = dp._calcKC(candles, def.period);
            series = [
                addLine(kc.upper, lineOpts(def.color, { lineStyle: 2 })),
                addLine(kc.lower, lineOpts(def.color, { lineStyle: 2 })),
                addLine(kc.mid,   lineOpts(def.color, { lineStyle: 1 })),
            ];

        } else if (def.type === 'dc') {
            const dc = dp._calcDC(candles, def.period);
            series = [
                addLine(dc.upper, lineOpts(def.color, { lineStyle: 2 })),
                addLine(dc.lower, lineOpts(def.color, { lineStyle: 2 })),
                addLine(dc.mid,   lineOpts(def.color, { lineStyle: 1 })),
            ];

        } else if (def.type === 'envelope') {
            const env = dp._calcEnvelope(candles, def.period, def.pct);
            series = [
                addLine(env.upper, lineOpts(def.color, { lineStyle: 2 })),
                addLine(env.lower, lineOpts(def.color, { lineStyle: 2 })),
                addLine(env.mid,   lineOpts(def.color, { lineStyle: 1 })),
            ];

        } else if (def.type === 'psar') {
            const data = dp._calcPSAR(candles);
            const s = this._bdChart.addLineSeries({ ...lineOpts(def.color), lineType: 1, pointMarkersVisible: true, lineVisible: false });
            s.setData(data);
            series = s;

        } else if (def.type === 'ichimoku') {
            const ich = dp._calcIchimoku(candles);
            series = [
                addLine(ich.tenkan,  lineOpts('#e74c3c')),
                addLine(ich.kijun,   lineOpts('#3498db')),
                addLine(ich.senkouA, lineOpts('#2ecc71', { lineStyle: 2 })),
                addLine(ich.senkouB, lineOpts('#e74c5e', { lineStyle: 2 })),
                addLine(ich.chikou,  lineOpts('#9b59b6', { lineStyle: 1 })),
            ];

        } else if (def.type === 'supertrend') {
            const st = dp._calcSupertrend(candles, def.period, def.mult);
            const s = this._bdChart.addLineSeries({ ...lineOpts(def.color), lineWidth: 2 });
            s.setData(st);
            series = s;

        } else if (def.type === 'pivots') {
            const piv = dp._calcPivots(candles);
            series = [
                addLine(piv.pivot, lineOpts('#dfe6e9', { lineStyle: 1 })),
                addLine(piv.r1,    lineOpts('#e74c5e', { lineStyle: 2 })),
                addLine(piv.s1,    lineOpts('#2ecc71', { lineStyle: 2 })),
                addLine(piv.r2,    lineOpts('#ff7675', { lineStyle: 2 })),
                addLine(piv.s2,    lineOpts('#55efc4', { lineStyle: 2 })),
            ];

        } else if (def.type === 'vwap') {
            series = addLine(dp._calcVWAP(candles), lineOpts(def.color, { lineWidth: 2 }));

        // ========== MOMENTUM / OSCILLATORS ==========
        } else if (def.type === 'rsi') {
            series = addLine(dp._calcRSI(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'stochrsi') {
            const sr = dp._calcStochRSI(candles, def.period);
            series = [
                addLine(sr.k, oscOpts('#00cec9')),
                addLine(sr.d, oscOpts('#e74c5e', { lineStyle: 2 })),
            ];
            setOscScale();

        } else if (def.type === 'macd') {
            const macd = dp._calcMACD(candles);
            series = [
                addLine(macd.macd, { ...oscOpts('#4a90d9'), lineWidth: 1.5 }),
                addLine(macd.signal, oscOpts('#e74c5e')),
                addHist(macd.histogram, { priceScaleId: scaleId, priceLineVisible: false, lastValueVisible: false }),
            ];
            setOscScale();

        } else if (def.type === 'stoch') {
            const stoch = dp._calcStoch(candles, def.period, def.smooth);
            series = [
                addLine(stoch.k, oscOpts(def.color)),
                addLine(stoch.d, oscOpts('#e74c5e', { lineStyle: 2 })),
            ];
            setOscScale();

        } else if (def.type === 'cci') {
            series = addLine(dp._calcCCI(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'willr') {
            series = addLine(dp._calcWillR(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'mom') {
            series = addLine(dp._calcMomentum(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'roc') {
            series = addLine(dp._calcROC(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'tsi') {
            series = addLine(dp._calcTSI(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'uo') {
            series = addLine(dp._calcUO(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'awesome') {
            series = addHist(dp._calcAwesome(candles), { priceScaleId: scaleId, priceLineVisible: false, lastValueVisible: false });
            setOscScale();

        } else if (def.type === 'ppo') {
            series = addLine(dp._calcPPO(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'cmo') {
            series = addLine(dp._calcCMO(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'fisher') {
            series = addLine(dp._calcFisher(candles, def.period), oscOpts(def.color));
            setOscScale();

        // ========== VOLATILITY ==========
        } else if (def.type === 'atr') {
            series = addLine(dp._calcATR(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'natr') {
            series = addLine(dp._calcNATR(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'bbwidth') {
            series = addLine(dp._calcBBWidth(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'bbpct') {
            series = addLine(dp._calcBBPct(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'stddev') {
            series = addLine(dp._calcStdDev(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'chop') {
            series = addLine(dp._calcChop(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'kc_width') {
            series = addLine(dp._calcKCWidth(candles, def.period), oscOpts(def.color));
            setOscScale();

        // ========== VOLUME ==========
        } else if (def.type === 'obv') {
            series = addLine(dp._calcOBV(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'adosc') {
            series = addLine(dp._calcADOsc(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'cmf') {
            series = addLine(dp._calcCMF(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'mfi') {
            series = addLine(dp._calcMFI(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'eom') {
            series = addLine(dp._calcEOM(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'vpt') {
            series = addLine(dp._calcVPT(candles), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'fi') {
            series = addLine(dp._calcFI(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'nvi') {
            series = addLine(dp._calcNVI(candles), oscOpts(def.color));
            setOscScale();

        // ========== TREND ==========
        } else if (def.type === 'adx') {
            series = addLine(dp._calcADX(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'di') {
            const di = dp._calcDI(candles, def.period);
            series = [
                addLine(di.plus, oscOpts('#2ecc71')),
                addLine(di.minus, oscOpts('#e74c5e')),
            ];
            setOscScale();

        } else if (def.type === 'aroon') {
            const ar = dp._calcAroon(candles, def.period);
            series = [
                addLine(ar.up, oscOpts('#2ecc71')),
                addLine(ar.down, oscOpts('#e74c5e')),
            ];
            setOscScale();

        } else if (def.type === 'aroonosc') {
            series = addLine(dp._calcAroonOsc(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'vortex') {
            const vt = dp._calcVortex(candles, def.period);
            series = [
                addLine(vt.plus, oscOpts('#2ecc71')),
                addLine(vt.minus, oscOpts('#e74c5e')),
            ];
            setOscScale();

        } else if (def.type === 'dpo') {
            series = addLine(dp._calcDPO(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'trix') {
            series = addLine(dp._calcTRIX(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'mass') {
            series = addLine(dp._calcMass(candles, def.period), oscOpts(def.color));
            setOscScale();

        } else if (def.type === 'copp') {
            series = addLine(dp._calcCoppock(candles), oscOpts(def.color));
            setOscScale();
        }

        } catch(e) {
            console.error(`Error adding indicator ${id}:`, e);
        }

        this._bdIndicators[id] = { enabled, series };
    }
};

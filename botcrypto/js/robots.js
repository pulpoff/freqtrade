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

            <!-- Active Bot Section -->
            <div class="card mt-4" id="activeBotCard">
                <div class="card-body">
                    <div class="d-flex align-items-center justify-content-between mb-3">
                        <h6 class="fw-semibold mb-0"><i class="bi bi-broadcast me-2 text-success"></i>Active Freqtrade Bot</h6>
                        <div class="d-flex gap-2" id="robotBotControls">
                            <button class="btn btn-success btn-sm" onclick="RobotsPage.controlBot('start')">
                                <i class="bi bi-play-fill me-1"></i> Start
                            </button>
                            <button class="btn btn-warning btn-sm" onclick="RobotsPage.controlBot('pause')">
                                <i class="bi bi-pause-fill me-1"></i> Pause
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="RobotsPage.controlBot('stop')">
                                <i class="bi bi-stop-fill me-1"></i> Stop
                            </button>
                        </div>
                    </div>
                    <div class="row g-3" id="activeBotInfo">
                        <div class="col-12 text-center text-secondary py-3">
                            <small>Connect to Freqtrade to see bot status</small>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
    },

    _renderStrategyCard(s, index) {
        const isImported = this.activeTab === 'imported';
        let timeUnit = s.timeUnit || s.timeframe || '';
        const nodesCount = s.nodes ? s.nodes.length : 0;
        let paramsHtml = '';

        // Extract params from .py content for imported strategies
        if (isImported && s.content) {
            const code = s.content;
            const tf = code.match(/timeframe\s*=\s*['"]([^'"]+)['"]/);
            const sl = code.match(/stoploss\s*=\s*(-?[\d.]+)/);
            const ts = code.match(/trailing_stop\s*=\s*(True|False)/);
            const roi = code.match(/minimal_roi\s*=\s*\{[^}]*"0"\s*:\s*([\d.]+)/);
            if (tf) timeUnit = tf[1];
            const badges = [];
            if (sl) badges.push(`<span class="badge bg-danger bg-opacity-25 text-danger">SL ${(parseFloat(sl[1]) * 100).toFixed(1)}%</span>`);
            if (roi) badges.push(`<span class="badge bg-success bg-opacity-25 text-success">ROI ${(parseFloat(roi[1]) * 100).toFixed(1)}%</span>`);
            if (ts && ts[1] === 'True') badges.push(`<span class="badge bg-warning bg-opacity-25 text-warning">Trailing</span>`);
            if (badges.length) paramsHtml = `<div class="d-flex gap-1 mt-2 flex-wrap">${badges.join('')}</div>`;
        }

        return `
        <div class="strategy-card" onclick="RobotsPage.openStrategy('${s.name.replace(/'/g, "\\'")}', ${isImported})">
            <div class="d-flex align-items-start justify-content-between">
                <div class="d-flex align-items-center gap-2">
                    <i class="bi ${isImported ? 'bi-file-earmark-code text-success' : 'bi-diagram-3 text-warning'}"></i>
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

    refresh() {
        const container = document.getElementById('pageContainer');
        if (container) container.innerHTML = this.render();
        this.loadActiveBotInfo();
    },

    destroy() {
        if (this.refreshTimer) { clearInterval(this.refreshTimer); this.refreshTimer = null; }
    }
};

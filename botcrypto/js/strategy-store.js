/**
 * BotCrypto - Strategy Store Page
 * Library of pre-built strategies that users can import and customize
 * Matches botcrypto.io's strategy store with import counts, ratings, descriptions
 */
const StrategyStorePage = {
    currentView: 'grid', // grid or detail
    selectedStrategy: null,
    searchQuery: '',
    filterTimeframe: '',
    filterCategory: '',

    // Pre-built strategy templates matching botcrypto.io patterns
    templates: [
        {
            id: 1,
            name: 'Buy & Sell 1m -5% Stop-Loss',
            desc: 'This strategy runs a regular Buy&Sell 1 minute bot in loop. Plus, if you lose more than 5%, the bot sells everything and terminates.',
            timeframe: '1m',
            pair: 'BTC/USDT',
            category: 'Trend Following',
            imports: 45,
            rating: 4,
            note: 8,
            nodes: [
                { id: 1, type: 'start', x: 100, y: 280, params: {} },
                { id: 2, type: 'indicator', x: 280, y: 380, params: { type: 'EMA', timeframe: '1m', period: 9, value: 0, condition: 'Crosses Over', compareType: 'EMA', comparePeriod: 26, compareValue: 0 }},
                { id: 3, type: 'buy', x: 480, y: 280, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: true }},
                { id: 4, type: 'gain', x: 680, y: 180, params: { condition: 'Above', value: 2, trade: 'Last' }},
                { id: 5, type: 'sell', x: 880, y: 120, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: false }},
                { id: 6, type: 'gain', x: 680, y: 380, params: { condition: 'Below', value: -5, trade: 'Last' }},
                { id: 7, type: 'sell', x: 880, y: 380, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: false }},
                { id: 8, type: 'terminate', x: 1080, y: 120, params: {} },
            ],
            connections: [
                { from: 1, to: 2, type: 'normal' },
                { from: 1, to: 3, type: 'normal' },
                { from: 2, to: 3, type: 'normal' },
                { from: 3, to: 4, type: 'normal' },
                { from: 3, to: 6, type: 'normal' },
                { from: 4, to: 5, type: 'true' },
                { from: 6, to: 7, type: 'true' },
                { from: 5, to: 8, type: 'normal' },
                { from: 7, to: 5, type: 'normal' },
            ]
        },
        {
            id: 2,
            name: 'Bullish Trend Following',
            desc: 'Uses EMA crossover strategy to identify bullish trends. Enters on EMA 9/26 golden cross and exits on death cross or when RSI becomes overbought.',
            timeframe: '30m',
            pair: 'XRP/USDT',
            category: 'Trend Following',
            imports: 127,
            rating: 5,
            note: 12,
            nodes: [
                { id: 1, type: 'start', x: 100, y: 250, params: {} },
                { id: 2, type: 'indicator', x: 300, y: 350, params: { type: 'EMA', timeframe: '30m', period: 9, value: 0, condition: 'Crosses Over', compareType: 'EMA', comparePeriod: 26, compareValue: 0 }},
                { id: 3, type: 'indicator', x: 300, y: 150, params: { type: 'RSI', timeframe: '30m', period: 14, value: 30, condition: 'Below', compareType: 'Value', comparePeriod: 0, compareValue: 30 }},
                { id: 4, type: 'group', x: 500, y: 250, params: { logic: 'AND' }},
                { id: 5, type: 'buy', x: 700, y: 250, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: true }},
                { id: 6, type: 'gain', x: 900, y: 150, params: { condition: 'Above', value: 3, trade: 'Last' }},
                { id: 7, type: 'sell', x: 1100, y: 150, params: { orderType: 'Market', trade: 'All', volume: 100, volumePercent: true, price: 0, assetQuote: false }},
                { id: 8, type: 'stoploss', x: 900, y: 350, params: { value: -3, trade: 'All' }},
            ],
            connections: [
                { from: 1, to: 2, type: 'normal' },
                { from: 1, to: 3, type: 'normal' },
                { from: 2, to: 4, type: 'normal' },
                { from: 3, to: 4, type: 'normal' },
                { from: 4, to: 5, type: 'normal' },
                { from: 5, to: 6, type: 'normal' },
                { from: 5, to: 8, type: 'normal' },
                { from: 6, to: 7, type: 'true' },
            ]
        },
        {
            id: 3,
            name: 'RSI Oversold/Overbought',
            desc: 'Simple RSI strategy that buys when RSI drops below 30 (oversold) and sells when RSI goes above 70 (overbought). Good for ranging markets.',
            timeframe: '15m',
            pair: 'ETH/USDT',
            category: 'Mean Reversion',
            imports: 89,
            rating: 4,
            note: 6,
            nodes: [
                { id: 1, type: 'start', x: 100, y: 250, params: {} },
                { id: 2, type: 'indicator', x: 300, y: 250, params: { type: 'RSI', timeframe: '15m', period: 14, value: 30, condition: 'Below', compareType: 'Value', comparePeriod: 0, compareValue: 30 }},
                { id: 3, type: 'buy', x: 500, y: 250, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: true }},
                { id: 4, type: 'indicator', x: 700, y: 250, params: { type: 'RSI', timeframe: '15m', period: 14, value: 70, condition: 'Above', compareType: 'Value', comparePeriod: 0, compareValue: 70 }},
                { id: 5, type: 'sell', x: 900, y: 250, params: { orderType: 'Market', trade: 'All', volume: 100, volumePercent: true, price: 0, assetQuote: false }},
            ],
            connections: [
                { from: 1, to: 2, type: 'normal' },
                { from: 2, to: 3, type: 'normal' },
                { from: 3, to: 4, type: 'normal' },
                { from: 4, to: 5, type: 'normal' },
            ]
        },
        {
            id: 4,
            name: 'MACD + Bollinger Bands',
            desc: 'Combines MACD crossover signals with Bollinger Band squeeze for high-probability entries. Takes profit at upper band, stop loss at -4%.',
            timeframe: '1h',
            pair: 'BTC/USDT',
            category: 'Momentum',
            imports: 63,
            rating: 4,
            note: 9,
            nodes: [
                { id: 1, type: 'start', x: 100, y: 250, params: {} },
                { id: 2, type: 'indicator', x: 300, y: 150, params: { type: 'MACD', timeframe: '1h', period: 12, value: 0, condition: 'Crosses Over', compareType: 'Value', comparePeriod: 0, compareValue: 0 }},
                { id: 3, type: 'indicator', x: 300, y: 350, params: { type: 'Bollinger Bands', timeframe: '1h', period: 20, value: 0, condition: 'Below', compareType: 'Value', comparePeriod: 0, compareValue: 0 }},
                { id: 4, type: 'group', x: 500, y: 250, params: { logic: 'AND' }},
                { id: 5, type: 'buy', x: 700, y: 250, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: true }},
                { id: 6, type: 'takeprofit', x: 900, y: 150, params: { value: 5, trade: 'All' }},
                { id: 7, type: 'stoploss', x: 900, y: 350, params: { value: -4, trade: 'All' }},
            ],
            connections: [
                { from: 1, to: 2, type: 'normal' },
                { from: 1, to: 3, type: 'normal' },
                { from: 2, to: 4, type: 'normal' },
                { from: 3, to: 4, type: 'normal' },
                { from: 4, to: 5, type: 'normal' },
                { from: 5, to: 6, type: 'normal' },
                { from: 5, to: 7, type: 'normal' },
            ]
        },
        {
            id: 5,
            name: 'Trailing Stop Scalper',
            desc: 'Quick scalping strategy using EMA crossover with tight trailing stop. Designed for volatile pairs on short timeframes.',
            timeframe: '5m',
            pair: 'SOL/USDT',
            category: 'Scalping',
            imports: 34,
            rating: 3,
            note: 4,
            nodes: [
                { id: 1, type: 'start', x: 100, y: 250, params: {} },
                { id: 2, type: 'indicator', x: 300, y: 250, params: { type: 'EMA', timeframe: '5m', period: 5, value: 0, condition: 'Crosses Over', compareType: 'EMA', comparePeriod: 13, compareValue: 0 }},
                { id: 3, type: 'buy', x: 500, y: 250, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: true }},
                { id: 4, type: 'trailing', x: 700, y: 250, params: { activation: 1.5, callback: 0.5 }},
                { id: 5, type: 'sell', x: 900, y: 250, params: { orderType: 'Market', trade: 'All', volume: 100, volumePercent: true, price: 0, assetQuote: false }},
            ],
            connections: [
                { from: 1, to: 2, type: 'normal' },
                { from: 2, to: 3, type: 'normal' },
                { from: 3, to: 4, type: 'normal' },
                { from: 4, to: 5, type: 'normal' },
            ]
        },
        {
            id: 6,
            name: 'Webhook Signal Bot',
            desc: 'Receives buy/sell signals from external sources (TradingView, custom scripts) via webhook. No built-in indicators - pure signal execution.',
            timeframe: '1m',
            pair: 'Any',
            category: 'External Signals',
            imports: 78,
            rating: 4,
            note: 5,
            nodes: [
                { id: 1, type: 'start', x: 100, y: 250, params: {} },
                { id: 2, type: 'webhook', x: 300, y: 250, params: { url: '' }},
                { id: 3, type: 'buy', x: 500, y: 150, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: true }},
                { id: 4, type: 'sell', x: 500, y: 350, params: { orderType: 'Market', trade: 'All', volume: 100, volumePercent: true, price: 0, assetQuote: false }},
                { id: 5, type: 'stoploss', x: 700, y: 250, params: { value: -5, trade: 'All' }},
            ],
            connections: [
                { from: 1, to: 2, type: 'normal' },
                { from: 2, to: 3, type: 'normal' },
                { from: 2, to: 4, type: 'normal' },
                { from: 3, to: 5, type: 'normal' },
            ]
        },
    ],

    render() {
        if (this.currentView === 'detail' && this.selectedStrategy) {
            return this.renderDetail();
        }
        return this.renderGrid();
    },

    renderGrid() {
        const filtered = this.getFilteredTemplates();
        return `
        <div id="strategyStorePage">
            <!-- Header -->
            <div class="d-flex align-items-center justify-content-between mb-4">
                <h4 class="fw-semibold mb-0"><i class="bi bi-shop me-2"></i>Strategy Store</h4>
                <div class="d-flex gap-2 align-items-center">
                    <button class="btn btn-outline-success btn-sm" onclick="StrategyStorePage.importPyFile()">
                        <i class="bi bi-file-earmark-code me-1"></i> Import .py File
                    </button>
                    <button class="btn btn-outline-primary btn-sm" onclick="StrategyStorePage.newCodeStrategy()">
                        <i class="bi bi-plus-lg me-1"></i> New Strategy
                    </button>
                    <div class="input-group" style="width:280px">
                        <span class="input-group-text bg-transparent border-secondary">
                            <i class="bi bi-search text-secondary"></i>
                        </span>
                        <input type="text" class="form-control" placeholder="Search strategies..."
                            value="${this.searchQuery}"
                            oninput="StrategyStorePage.searchQuery = this.value; StrategyStorePage.refresh()">
                    </div>
                    <select class="form-select form-select-sm" style="width:140px"
                        onchange="StrategyStorePage.filterTimeframe = this.value; StrategyStorePage.refresh()">
                        <option value="">All Timeframes</option>
                        <option value="1m">1m</option>
                        <option value="5m">5m</option>
                        <option value="15m">15m</option>
                        <option value="30m">30m</option>
                        <option value="1h">1h</option>
                    </select>
                    <select class="form-select form-select-sm" style="width:160px"
                        onchange="StrategyStorePage.filterCategory = this.value; StrategyStorePage.refresh()">
                        <option value="">All Categories</option>
                        <option value="Trend Following">Trend Following</option>
                        <option value="Mean Reversion">Mean Reversion</option>
                        <option value="Momentum">Momentum</option>
                        <option value="Scalping">Scalping</option>
                        <option value="External Signals">External Signals</option>
                    </select>
                </div>
            </div>

            <!-- Strategy Grid -->
            <div class="row g-3">
                ${filtered.map(s => {
                    const icon = this._getStrategyIcon(s.name);
                    const badges = [];
                    if (s._stoploss) badges.push(`<span class="badge bg-danger bg-opacity-15 text-danger">SL ${s._stoploss}%</span>`);
                    if (s._roi) badges.push(`<span class="badge bg-success bg-opacity-15 text-success">ROI ${s._roi}%</span>`);
                    if (s._leverage) badges.push(`<span class="badge bg-info bg-opacity-15 text-info">${s._leverage}x</span>`);
                    if (s._trailing) badges.push(`<span class="badge bg-warning bg-opacity-15 text-warning">Trail</span>`);
                    if (s._canShort) badges.push(`<span class="badge bg-purple bg-opacity-15" style="color:#a78bfa">Short</span>`);
                    return `
                <div class="col-lg-4 col-md-6">
                    <div class="card strategy-card h-100">
                        <div class="card-body" onclick="StrategyStorePage.viewDetail(${s.id})" style="cursor:pointer">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <h6 class="fw-semibold mb-0">
                                    <i class="bi ${icon} me-2" style="color:var(--bc-accent);opacity:0.8"></i>${s.name}
                                </h6>
                                <span class="text-success small fw-semibold">${s.isRemote ? 'Freqtrade' : `Imported ${s.imports} times`}</span>
                            </div>
                            <p class="text-secondary small mb-2" style="line-height:1.6">${s.desc}</p>
                            ${badges.length > 0 ? `<div class="d-flex gap-1 flex-wrap mb-2">${badges.join('')}</div>` : ''}
                            <div class="d-flex justify-content-between align-items-center">
                                <div class="d-flex gap-1">
                                    <span class="badge bg-primary bg-opacity-10 text-primary">${s.timeframe}</span>
                                    <span class="badge bg-success bg-opacity-10 text-success">${s.pair}</span>
                                    <span class="badge bg-warning bg-opacity-10 text-warning">${s.category}</span>
                                </div>
                                <div class="d-flex gap-1 align-items-center">
                                    ${s.isRemote ? `<button class="btn btn-outline-primary btn-sm py-0 px-1" onclick="event.stopPropagation(); StrategyStorePage.editCode('remote', '${s.name}')" title="Edit code"><i class="bi bi-code-slash"></i></button>` : ''}
                                    <span class="text-warning small">
                                        ${Array(5).fill(0).map((_, i) => `<i class="bi bi-star${i < s.rating ? '-fill' : ''}"></i>`).join('')}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>`; }).join('')}
            </div>

            ${filtered.length === 0 ? Components.emptyState('search', 'No strategies found', 'Try adjusting your search or filters') : ''}

            <!-- User's Saved Strategies -->
            <h5 class="fw-semibold mt-4 mb-3"><i class="bi bi-bookmark me-2"></i>My Strategies</h5>
            <div class="row g-3" id="myStrategiesGrid">
                ${this.renderUserStrategies()}
            </div>
        </div>`;
    },

    renderUserStrategies() {
        const saved = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
        const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');

        const cards = [];

        // Visual flow strategies
        saved.forEach((s, i) => {
            const hasCode = imported[s.name] && imported[s.name].content;
            cards.push(`
            <div class="col-lg-4 col-md-6">
                <div class="card strategy-card h-100">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h6 class="fw-semibold mb-0">${s.name}</h6>
                            <small class="text-secondary">${Components.formatDate(s.savedAt)}</small>
                        </div>
                        <p class="text-secondary small mb-3">${s.desc || 'No description'}</p>
                        <div class="d-flex gap-2 flex-wrap">
                            <button class="btn btn-outline-success btn-sm" onclick="StrategyStorePage.loadUserStrategy(${i})"
                                title="Open in visual flow editor">
                                <i class="bi bi-diagram-3 me-1"></i> Visual
                            </button>
                            <button class="btn btn-outline-primary btn-sm" onclick="StrategyStorePage.editCode('visual', ${i})"
                                title="Open in code editor">
                                <i class="bi bi-code-slash me-1"></i> Code
                            </button>
                            <button class="btn btn-outline-secondary btn-sm" onclick="StrategyStorePage.backtestUserStrategy(${i})">
                                <i class="bi bi-clock-history me-1"></i> Backtest
                            </button>
                            <button class="btn btn-outline-danger btn-sm" onclick="StrategyStorePage.deleteUserStrategy(${i})">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>`);
        });

        // Imported .py strategies (code-only, no visual flow)
        Object.entries(imported).forEach(([name, info]) => {
            // Skip if already in visual strategies list
            if (saved.find(s => s.name === name)) return;
            cards.push(`
            <div class="col-lg-4 col-md-6">
                <div class="card strategy-card h-100">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h6 class="fw-semibold mb-0">${name}</h6>
                            <small class="text-secondary">${Components.formatDate(info.importedAt)}</small>
                        </div>
                        <p class="text-secondary small mb-3">
                            <span class="badge bg-primary bg-opacity-10 text-primary me-1">Python</span>
                            Imported .py strategy
                        </p>
                        <div class="d-flex gap-2 flex-wrap">
                            <button class="btn btn-outline-primary btn-sm" onclick="StrategyStorePage.editCode('imported', '${name}')"
                                title="Open in code editor">
                                <i class="bi bi-code-slash me-1"></i> Code
                            </button>
                            <button class="btn btn-outline-success btn-sm" onclick="StrategyStorePage.openImportedInVisual('${name}')"
                                title="Open in visual flow editor">
                                <i class="bi bi-diagram-3 me-1"></i> Visual
                            </button>
                            <button class="btn btn-outline-secondary btn-sm" onclick="StrategyStorePage.backtestImported('${name}')">
                                <i class="bi bi-clock-history me-1"></i> Backtest
                            </button>
                            <button class="btn btn-outline-danger btn-sm" onclick="StrategyStorePage.deleteImported('${name}')">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>`);
        });

        if (cards.length === 0) {
            return `<div class="col-12"><div class="text-center text-secondary py-4">
                <p>No saved strategies yet. Build one in the Strategy Builder or import a .py file!</p>
                <div class="d-flex gap-2 justify-content-center">
                    <button class="btn btn-outline-success btn-sm" onclick="App.navigate('strategy-builder')">
                        <i class="bi bi-diagram-3 me-1"></i> Visual Builder
                    </button>
                    <button class="btn btn-outline-primary btn-sm" onclick="StrategyStorePage.importPyFile()">
                        <i class="bi bi-file-earmark-code me-1"></i> Import .py
                    </button>
                </div>
            </div></div>`;
        }
        return cards.join('');
    },

    renderDetail() {
        const s = this.selectedStrategy;
        return `
        <div id="strategyDetailPage">
            <!-- Header like botcrypto -->
            <div class="d-flex align-items-center justify-content-between mb-4">
                <div class="d-flex align-items-center gap-3">
                    <button class="btn btn-link text-secondary p-0" onclick="StrategyStorePage.backToGrid()">
                        <i class="bi bi-chevron-left fs-4"></i>
                    </button>
                    <i class="bi bi-diagram-3 text-warning fs-5"></i>
                    <h4 class="fw-semibold mb-0">${s.name}</h4>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <a href="#" class="btn btn-sm btn-link text-info"><i class="bi bi-info-circle me-1"></i>Helpdesk</a>
                    <span class="badge bg-dark border border-secondary px-3 py-2">
                        <i class="bi bi-clock me-1"></i> Time unit <strong>${s.timeframe}</strong>
                    </span>
                    <button class="btn btn-warning fw-semibold" onclick="StrategyStorePage.importToBuilder(${s.id})">
                        IMPORT <i class="bi bi-download ms-1"></i>
                    </button>
                </div>
            </div>

            <div class="row g-3">
                <!-- Left: Info -->
                <div class="col-md-4">
                    <div class="card h-100">
                        <div class="card-body">
                            <div class="text-success fw-semibold mb-2">Imported ${s.imports} times</div>
                            <div class="text-warning small mb-3">
                                ${Array(5).fill(0).map((_, i) => `<i class="bi bi-star${i < s.rating ? '-fill' : ''}"></i>`).join('')}
                            </div>

                            <h6 class="fw-semibold">Description:</h6>
                            <p class="text-secondary small" style="line-height:1.6">${s.desc}</p>

                            <h6 class="fw-semibold mt-3">Botcrypto note <span class="badge bg-secondary">${s.note}</span></h6>

                            <div class="mt-3">
                                <span class="badge bg-primary bg-opacity-10 text-primary me-1">${s.timeframe}</span>
                                <span class="badge bg-success bg-opacity-10 text-success me-1">${s.pair}</span>
                                <span class="badge bg-warning bg-opacity-10 text-warning">${s.category}</span>
                            </div>

                            <hr class="border-secondary">

                            <button class="btn btn-success w-100 fw-semibold mb-2" onclick="StrategyStorePage.importToBuilder(${s.id})">
                                <i class="bi bi-download me-1"></i> Import to Builder
                            </button>
                            <button class="btn btn-outline-success w-100" onclick="StrategyStorePage.backtestTemplate(${s.id})">
                                <i class="bi bi-clock-history me-1"></i> Run Backtest
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Right: Visual Preview -->
                <div class="col-md-8">
                    <div class="card h-100">
                        <div class="card-body position-relative" style="min-height:500px;">
                            <div class="builder-canvas-wrapper w-100 h-100 rounded" id="previewCanvas" style="min-height:450px">
                                <svg class="connections-layer" id="previewConnectionsLayer"></svg>
                                <div id="previewNodesContainer" class="builder-canvas"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
    },

    // Deterministic icon for a strategy name (persistent across sessions)
    _strategyIcons: [
        'bi-lightning-charge', 'bi-rocket-takeoff', 'bi-bullseye', 'bi-tsunami',
        'bi-shield-check', 'bi-fire', 'bi-gem', 'bi-cpu', 'bi-graph-up-arrow',
        'bi-crosshair', 'bi-trophy', 'bi-bar-chart-line', 'bi-stars', 'bi-signpost',
        'bi-radar', 'bi-flower1', 'bi-moon-stars', 'bi-compass', 'bi-virus',
        'bi-hurricane', 'bi-eye', 'bi-lightning', 'bi-globe2', 'bi-broadcast',
        'bi-peace', 'bi-activity', 'bi-box-seam', 'bi-diamond', 'bi-infinity',
        'bi-motherboard', 'bi-layers', 'bi-snow3', 'bi-heart-pulse', 'bi-tsunami',
    ],

    _getStrategyIcon(name) {
        // Hash the name to get a persistent index
        let hash = 0;
        for (let i = 0; i < name.length; i++) hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0;
        return this._strategyIcons[Math.abs(hash) % this._strategyIcons.length];
    },

    init() {
        this.loadRemoteStrategies();
    },

    async loadRemoteStrategies() {
        try {
            if (API.connected) {
                const data = await API.getStrategies();
                if (data && data.strategies) {
                    data.strategies.forEach(name => {
                        if (!this.templates.find(t => t.name === name)) {
                            this.templates.push({
                                id: 100 + this.templates.length,
                                name: name,
                                desc: `Freqtrade strategy: ${name}. Load to view details and backtest.`,
                                timeframe: '5m',
                                pair: 'Various',
                                category: 'Freqtrade',
                                imports: 0,
                                rating: 0,
                                note: 0,
                                isRemote: true,
                                nodes: [],
                                connections: []
                            });
                        }
                    });
                    this.refresh();
                    // Fetch details for remote strategies in background
                    this._loadRemoteDetails(data.strategies);
                }
            }
        } catch (e) {
            console.log('Could not load remote strategies:', e.message);
        }
    },

    async _loadRemoteDetails(names) {
        for (const name of names) {
            try {
                const detail = await API.getStrategy(name);
                if (!detail || !detail.code) continue;
                const code = detail.code;
                const tpl = this.templates.find(t => t.name === name && t.isRemote);
                if (!tpl) continue;
                // Parse key info from code
                const tfM = code.match(/timeframe\s*=\s*['"]([^'"]+)['"]/);
                if (tfM) tpl.timeframe = tfM[1];
                const slM = code.match(/stoploss\s*=\s*(-?[\d.]+)/);
                if (slM) tpl._stoploss = (parseFloat(slM[1]) * 100).toFixed(1);
                const roiM = code.match(/minimal_roi\s*=\s*\{[^}]*"0"\s*:\s*([\d.]+)/);
                if (roiM) tpl._roi = (parseFloat(roiM[1]) * 100).toFixed(1);
                const leverageM = code.match(/leverage\s*.*?return\s+(\d+)/s) || code.match(/leverage\s*=\s*(\d+)/);
                if (leverageM) tpl._leverage = leverageM[1];
                const trailM = code.match(/trailing_stop\s*=\s*True/);
                if (trailM) tpl._trailing = true;
                const canShort = code.match(/can_short\s*=\s*True/);
                if (canShort) tpl._canShort = true;
            } catch(e) { /* skip */ }
        }
        this.refresh();
    },

    getFilteredTemplates() {
        let filtered = [...this.templates];
        if (this.searchQuery) {
            const q = this.searchQuery.toLowerCase();
            filtered = filtered.filter(s =>
                s.name.toLowerCase().includes(q) ||
                s.desc.toLowerCase().includes(q) ||
                s.category.toLowerCase().includes(q)
            );
        }
        if (this.filterTimeframe) {
            filtered = filtered.filter(s => s.timeframe === this.filterTimeframe);
        }
        if (this.filterCategory) {
            filtered = filtered.filter(s => s.category === this.filterCategory);
        }
        return filtered;
    },

    viewDetail(id) {
        this.selectedStrategy = this.templates.find(s => s.id === id);
        if (!this.selectedStrategy) return;
        this.currentView = 'detail';
        this.refresh();

        // Render preview nodes after DOM update
        setTimeout(() => this.renderPreviewNodes(), 100);
    },

    renderPreviewNodes() {
        const s = this.selectedStrategy;
        if (!s || !s.nodes) return;

        const container = document.getElementById('previewNodesContainer');
        const svg = document.getElementById('previewConnectionsLayer');
        if (!container || !svg) return;

        // Render nodes (simplified, non-interactive)
        container.innerHTML = s.nodes.map(node => {
            const bt = StrategyBuilderPage.blockTypes[node.type];
            if (!bt) return '';
            const letter = bt.letter || bt.text || bt.label.charAt(0);

            let paramsText = '';
            if (node.type === 'buy' || node.type === 'sell') {
                const p = node.params;
                paramsText = `${p.orderType} ${p.trade} ${p.volume}% ${p.price} ${p.assetQuote ? 'Quote' : 'Base'}`;
            } else if (node.type === 'indicator') {
                const p = node.params;
                paramsText = `${p.timeframe} | ${p.period} ${p.value} ${p.condition} ${p.compareType} ${p.comparePeriod} ${p.compareValue}`;
            } else if (node.type === 'gain') {
                paramsText = `${node.params.condition} ${node.params.value} ${node.params.trade}`;
            }

            const paramsClass = node.type === 'buy' ? 'params-green' : node.type === 'sell' ? 'params-red' : '';

            return `
            <div class="canvas-node" style="left:${node.x}px;top:${node.y}px">
                <div class="node-body">
                    <div class="node-icon ${bt.iconClass}">
                        ${bt.letter ? `<span class="fw-bold fs-4">${letter}</span>` : bt.text ? `<span class="fw-bold small">${bt.text}</span>` : `<i class="bi ${bt.icon}"></i>`}
                    </div>
                    <div class="node-label">${node.type === 'indicator' ? (node.params.type || 'EMA') : bt.label}</div>
                </div>
                ${paramsText ? `<div class="node-params ${paramsClass}">${paramsText}</div>` : ''}
            </div>`;
        }).join('');

        // Render connections
        svg.innerHTML = s.connections.map(conn => {
            const fromNode = s.nodes.find(n => n.id === conn.from);
            const toNode = s.nodes.find(n => n.id === conn.to);
            if (!fromNode || !toNode) return '';

            const x1 = fromNode.x + 45;
            let y1 = fromNode.y + 45;
            const x2 = toNode.x;
            const y2 = toNode.y + 45;

            const bt = StrategyBuilderPage.blockTypes[fromNode.type];
            if (bt && bt.hasTwoOutputs) {
                y1 = conn.type === 'true' ? fromNode.y + 30 : fromNode.y + 60;
            }

            const cx1 = x1 + 60;
            const cx2 = x2 - 60;
            const pathClass = conn.type === 'true' ? 'conn-true' : conn.type === 'false' ? 'conn-false' : 'conn-normal';
            return `<path class="${pathClass}" d="M${x1},${y1} C${cx1},${y1} ${cx2},${y2} ${x2},${y2}"/>`;
        }).join('');
    },

    backToGrid() {
        this.currentView = 'grid';
        this.selectedStrategy = null;
        this.refresh();
    },

    async importToBuilder(id) {
        const s = this.templates.find(t => t.id === id);
        if (!s) return;

        // For remote Freqtrade strategies, fetch code and parse into visual nodes
        if (s.isRemote && (!s.nodes || s.nodes.length === 0)) {
            try {
                App.showToast(`Loading strategy "${s.name}"...`, 'info');
                const detail = await API.getStrategy(s.name);
                if (detail && detail.code) {
                    // Store imported code for analysis and backtesting
                    StrategyBuilderPage._importedStrategyCode = detail.code;
                    StrategyBuilderPage._importedStrategyName = s.name;
                    // Save to imported strategies localStorage
                    const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
                    imported[s.name] = { content: detail.code, importedAt: new Date().toISOString(), uploaded: true };
                    localStorage.setItem('bc_imported_strategies', JSON.stringify(imported));
                    // Parse code into visual flow nodes
                    StrategyBuilderPage._parseStrategyToFlow(detail.code, s.name);
                    StrategyBuilderPage.autoSave();
                    App.showToast(`Strategy "${s.name}" imported as visual flow`, 'success');
                    App.navigate('strategy-builder');
                    setTimeout(() => {
                        StrategyBuilderPage.renderNodes();
                        StrategyBuilderPage.zoomFit();
                    }, 200);
                    return;
                }
            } catch(e) {
                console.log('Failed to fetch remote strategy:', e.message);
                App.showToast(`Could not load strategy code: ${e.message}`, 'warning');
            }
        }

        // For template strategies with pre-built nodes
        StrategyBuilderPage.nodes = JSON.parse(JSON.stringify(s.nodes));
        StrategyBuilderPage.connections = JSON.parse(JSON.stringify(s.connections));
        StrategyBuilderPage.strategyName = s.name;
        StrategyBuilderPage.strategyDesc = s.desc;
        StrategyBuilderPage.timeUnit = s.timeframe;
        StrategyBuilderPage.nextId = s.nodes.length > 0 ? Math.max(...s.nodes.map(n => n.id)) + 1 : 1;

        StrategyBuilderPage.autoSave();
        App.showToast(`Strategy "${s.name}" imported as visual flow`, 'success');
        App.navigate('strategy-builder');

        setTimeout(() => {
            StrategyBuilderPage.renderNodes();
            StrategyBuilderPage.zoomFit();
        }, 200);
    },

    backtestTemplate(id) {
        const s = this.templates.find(t => t.id === id);
        if (!s) return;
        this.importToBuilder(id);
        BacktestingPage.pendingStrategy = `visual:${s.name}`;
        setTimeout(() => App.navigate('backtesting'), 100);
    },

    loadUserStrategy(index) {
        const saved = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
        const s = saved[index];
        if (!s) return;

        StrategyBuilderPage.nodes = JSON.parse(JSON.stringify(s.nodes));
        StrategyBuilderPage.connections = JSON.parse(JSON.stringify(s.connections));
        StrategyBuilderPage.strategyName = s.name;
        StrategyBuilderPage.strategyDesc = s.desc || '';
        StrategyBuilderPage.nextId = s.nextId || 1;
        StrategyBuilderPage.timeUnit = s.timeUnit || '5m';
        StrategyBuilderPage.autoSave();

        App.navigate('strategy-builder');
        setTimeout(() => StrategyBuilderPage.renderNodes(), 200);
    },

    backtestUserStrategy(index) {
        const saved = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
        const s = saved[index];
        if (s) BacktestingPage.pendingStrategy = `visual:${s.name}`;
        this.loadUserStrategy(index);
        setTimeout(() => App.navigate('backtesting'), 100);
    },

    deleteUserStrategy(index) {
        if (!confirm('Delete this strategy?')) return;
        const saved = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
        saved.splice(index, 1);
        localStorage.setItem('bc_strategies', JSON.stringify(saved));
        this.refresh();
        App.showToast('Strategy deleted', 'info');
    },

    /** Import a .py file from disk */
    importPyFile() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.py';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            try {
                const content = await file.text();
                const name = file.name.replace(/\.py$/, '');

                // Upload to Freqtrade
                let uploaded = false;
                if (API.connected) {
                    try {
                        await API.request('/strategies/upload', {
                            method: 'POST',
                            body: JSON.stringify({ strategy: content, name })
                        });
                        uploaded = true;
                    } catch (err) {
                        console.log('Upload failed:', err.message);
                    }
                }

                // Save in localStorage
                const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
                imported[name] = { content, importedAt: new Date().toISOString(), uploaded };
                localStorage.setItem('bc_imported_strategies', JSON.stringify(imported));

                App.showToast(`Strategy "${name}" imported${uploaded ? ' and uploaded to Freqtrade' : ''}`, 'success');
                this.refresh();
            } catch (err) {
                App.showToast(`Import failed: ${err.message}`, 'error');
            }
        };
        input.click();
    },

    /** Create a new strategy from scratch in code editor */
    newCodeStrategy() {
        const defaultCode = `# --- Do not remove these libs ---
from freqtrade.strategy import IStrategy
from pandas import DataFrame
# --------------------------------

class NewStrategy(IStrategy):
    """
    Custom strategy
    """
    INTERFACE_VERSION = 3
    timeframe = '5m'
    stoploss = -0.10
    minimal_roi = {"0": 0.05, "30": 0.03, "60": 0.01, "120": 0}
    can_short = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Add your indicators here
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Add entry conditions
        dataframe.loc[:, 'enter_long'] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Add exit conditions
        dataframe.loc[:, 'exit_long'] = 0
        return dataframe
`;
        this._showCodeEditor('NewStrategy', defaultCode, true);
    },

    /** Open code editor for a strategy */
    async editCode(source, key) {
        let code = '';
        let name = '';

        if (source === 'imported') {
            // Imported .py strategy from localStorage
            const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
            const info = imported[key];
            if (info && info.content) {
                code = info.content;
                name = key;
            }
        } else if (source === 'visual') {
            // Visual strategy - try to get its generated code or load from Freqtrade
            const saved = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
            const s = saved[key];
            if (!s) return;
            name = s.name;

            // Check if we have imported code for it
            const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
            if (imported[name] && imported[name].content) {
                code = imported[name].content;
            } else if (API.connected) {
                // Try to load from Freqtrade API
                try {
                    const data = await API.getStrategy(name);
                    if (data && data.code) code = data.code;
                } catch (e) {
                    console.log('Could not load strategy code:', e.message);
                }
            }
            if (!code) {
                code = `# Strategy "${name}" - no Python code available yet.\n# Edit this file to create the strategy code.\n`;
            }
        } else if (source === 'remote') {
            name = key;
            if (API.connected) {
                try {
                    const data = await API.getStrategy(name);
                    if (data && data.code) code = data.code;
                } catch (e) {
                    App.showToast(`Could not load strategy: ${e.message}`, 'error');
                    return;
                }
            }
        }

        if (!code) {
            App.showToast('No code available for this strategy', 'warning');
            return;
        }
        this._showCodeEditor(name, code, false);
    },

    /** Show the code editor modal */
    _showCodeEditor(name, code, isNew) {
        // Escape HTML entities in code for textarea
        const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        const modal = document.createElement('div');
        modal.innerHTML = `
        <div class="modal fade" tabindex="-1" id="codeEditorModal">
            <div class="modal-dialog modal-xl modal-dialog-scrollable">
                <div class="modal-content bg-dark border-secondary">
                    <div class="modal-header border-secondary">
                        <div class="d-flex align-items-center gap-3">
                            <h5 class="modal-title"><i class="bi bi-code-slash me-2"></i>Strategy Code Editor</h5>
                            <input type="text" class="form-control form-control-sm" style="width:200px"
                                id="codeEditorName" value="${name}" placeholder="Strategy name">
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            <button class="btn btn-sm btn-outline-success" onclick="StrategyStorePage._saveCode()">
                                <i class="bi bi-floppy me-1"></i> Save & Upload
                            </button>
                            <button class="btn btn-sm btn-outline-primary" onclick="StrategyStorePage._downloadCode()">
                                <i class="bi bi-download me-1"></i> Download
                            </button>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                    </div>
                    <div class="modal-body p-0">
                        <textarea id="codeEditorTextarea" class="form-control bg-dark text-light border-0 font-monospace"
                            style="min-height:70vh;resize:none;font-size:13px;line-height:1.5;tab-size:4"
                            spellcheck="false">${escaped}</textarea>
                    </div>
                    <div class="modal-footer border-secondary py-1">
                        <small class="text-secondary me-auto">
                            <i class="bi bi-info-circle me-1"></i>
                            Save uploads the strategy to Freqtrade's user_data/strategies/ for backtesting
                        </small>
                        <button class="btn btn-sm btn-outline-warning" onclick="StrategyStorePage._openInVisual()">
                            <i class="bi bi-diagram-3 me-1"></i> Open in Visual Builder
                        </button>
                    </div>
                </div>
            </div>
        </div>`;
        document.body.appendChild(modal);
        this._codeModal = new bootstrap.Modal(modal.querySelector('.modal'));
        this._codeModalEl = modal;
        this._codeModal.show();
        modal.querySelector('.modal').addEventListener('hidden.bs.modal', () => modal.remove());

        // Handle tab key in textarea
        const textarea = document.getElementById('codeEditorTextarea');
        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = textarea.selectionStart;
                const end = textarea.selectionEnd;
                textarea.value = textarea.value.substring(0, start) + '    ' + textarea.value.substring(end);
                textarea.selectionStart = textarea.selectionEnd = start + 4;
            }
        });
    },

    /** Save code from editor to Freqtrade and localStorage */
    async _saveCode() {
        const name = document.getElementById('codeEditorName')?.value.trim();
        const code = document.getElementById('codeEditorTextarea')?.value;
        if (!name || !code) {
            App.showToast('Please enter a strategy name', 'warning');
            return;
        }

        // Save to localStorage
        const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
        imported[name] = { content: code, importedAt: new Date().toISOString(), uploaded: false };

        // Upload to Freqtrade
        if (API.connected) {
            try {
                await API.request('/strategies/upload', {
                    method: 'POST',
                    body: JSON.stringify({ strategy: code, name })
                });
                imported[name].uploaded = true;
                App.showToast(`Strategy "${name}" saved and uploaded to Freqtrade`, 'success');
            } catch (err) {
                App.showToast(`Saved locally but upload failed: ${err.message}`, 'warning');
            }
        } else {
            App.showToast(`Strategy "${name}" saved locally (connect to Freqtrade to upload)`, 'info');
        }

        localStorage.setItem('bc_imported_strategies', JSON.stringify(imported));
        this.refresh();
    },

    /** Download strategy code as .py file */
    _downloadCode() {
        const name = document.getElementById('codeEditorName')?.value.trim() || 'strategy';
        const code = document.getElementById('codeEditorTextarea')?.value || '';
        const blob = new Blob([code], { type: 'text/x-python' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${name}.py`;
        a.click();
        URL.revokeObjectURL(url);
    },

    /** Open current code in visual builder */
    _openInVisual() {
        const code = document.getElementById('codeEditorTextarea')?.value || '';
        const name = document.getElementById('codeEditorName')?.value.trim() || 'Strategy';
        if (this._codeModal) this._codeModal.hide();
        StrategyBuilderPage._parseStrategyToFlow(code, name);
        StrategyBuilderPage.autoSave();
        App.navigate('strategy-builder');
        setTimeout(() => StrategyBuilderPage.renderNodes(), 200);
    },

    /** Open imported strategy in visual flow builder */
    openImportedInVisual(name) {
        const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
        const info = imported[name];
        if (!info || !info.content) {
            App.showToast('No code found for this strategy', 'warning');
            return;
        }
        StrategyBuilderPage._parseStrategyToFlow(info.content, name);
        StrategyBuilderPage.autoSave();
        App.navigate('strategy-builder');
        setTimeout(() => StrategyBuilderPage.renderNodes(), 200);
    },

    /** Backtest an imported strategy */
    backtestImported(name) {
        // Navigate to backtesting with this strategy pre-selected
        BacktestingPage.pendingStrategy = name;
        App.navigate('backtesting');
    },

    /** Delete an imported strategy */
    deleteImported(name) {
        if (!confirm(`Delete imported strategy "${name}"?`)) return;
        const imported = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
        delete imported[name];
        localStorage.setItem('bc_imported_strategies', JSON.stringify(imported));
        this.refresh();
        App.showToast('Strategy deleted', 'info');
    },

    refresh() {
        const container = document.getElementById('pageContainer');
        if (container) {
            container.innerHTML = this.render();
            if (this.currentView === 'detail') {
                setTimeout(() => this.renderPreviewNodes(), 100);
            }
        }
    },

    destroy() {}
};

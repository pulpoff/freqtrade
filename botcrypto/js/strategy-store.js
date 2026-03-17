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
                ${filtered.map(s => `
                <div class="col-lg-4 col-md-6">
                    <div class="card strategy-card h-100" onclick="StrategyStorePage.viewDetail(${s.id})">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <h6 class="fw-semibold mb-0">${s.name}</h6>
                                <span class="text-success small fw-semibold">Imported ${s.imports} times</span>
                            </div>
                            <p class="text-secondary small mb-3" style="line-height:1.6">${s.desc}</p>
                            <div class="d-flex justify-content-between align-items-center">
                                <div class="d-flex gap-1">
                                    <span class="badge bg-primary bg-opacity-10 text-primary">${s.timeframe}</span>
                                    <span class="badge bg-success bg-opacity-10 text-success">${s.pair}</span>
                                    <span class="badge bg-warning bg-opacity-10 text-warning">${s.category}</span>
                                </div>
                                <div class="text-warning small">
                                    ${Array(5).fill(0).map((_, i) => `<i class="bi bi-star${i < s.rating ? '-fill' : ''}"></i>`).join('')}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>`).join('')}
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
        if (saved.length === 0) {
            return `<div class="col-12"><div class="text-center text-secondary py-4">
                <p>No saved strategies yet. Build one in the Strategy Builder!</p>
                <button class="btn btn-outline-success btn-sm" onclick="App.navigate('strategy-builder')">
                    <i class="bi bi-plus me-1"></i> Create Strategy
                </button>
            </div></div>`;
        }
        return saved.map((s, i) => `
        <div class="col-lg-4 col-md-6">
            <div class="card strategy-card h-100">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <h6 class="fw-semibold mb-0">${s.name}</h6>
                        <small class="text-secondary">${Components.formatDate(s.savedAt)}</small>
                    </div>
                    <p class="text-secondary small mb-3">${s.desc || 'No description'}</p>
                    <div class="d-flex gap-2">
                        <button class="btn btn-outline-success btn-sm" onclick="StrategyStorePage.loadUserStrategy(${i})">
                            <i class="bi bi-pencil me-1"></i> Edit
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
        </div>`).join('');
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

    init() {
        // Load any Freqtrade strategies
        this.loadRemoteStrategies();
    },

    async loadRemoteStrategies() {
        try {
            if (API.connected) {
                const data = await API.getStrategies();
                if (data && data.strategies) {
                    // Add as importable templates
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
                }
            }
        } catch (e) {
            console.log('Could not load remote strategies:', e.message);
        }
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

    importToBuilder(id) {
        const s = this.templates.find(t => t.id === id);
        if (!s) return;

        // Load into strategy builder state
        StrategyBuilderPage.nodes = JSON.parse(JSON.stringify(s.nodes));
        StrategyBuilderPage.connections = JSON.parse(JSON.stringify(s.connections));
        StrategyBuilderPage.strategyName = s.name;
        StrategyBuilderPage.strategyDesc = s.desc;
        StrategyBuilderPage.timeUnit = s.timeframe;
        StrategyBuilderPage.nextId = s.nodes.length > 0 ? Math.max(...s.nodes.map(n => n.id)) + 1 : 1;

        // Save to localStorage so init() picks it up
        StrategyBuilderPage.autoSave();

        App.showToast(`Strategy "${s.name}" imported as visual flow`, 'success');

        // Force full page re-render by navigating
        App.navigate('strategy-builder');

        // Ensure nodes render after DOM is ready (in case init timing is off)
        setTimeout(() => {
            StrategyBuilderPage.renderNodes();
            // Update strategy name input if it didn't pick up the new value
            const nameInput = document.querySelector('#dashboardPage input, .builder-layout input[type="text"]');
            if (nameInput && nameInput.value !== s.name) {
                nameInput.value = s.name;
            }
        }, 200);
    },

    backtestTemplate(id) {
        const s = this.templates.find(t => t.id === id);
        if (!s) return;
        this.importToBuilder(id);
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

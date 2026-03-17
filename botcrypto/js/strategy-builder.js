/**
 * BotCrypto - Visual Strategy Builder
 * Node-based canvas editor matching botcrypto.io's visual builder
 */
const StrategyBuilderPage = {
    nodes: [],
    connections: [],
    selectedNode: null,
    draggingNode: null,
    connectingFrom: null,
    canvasOffset: { x: 0, y: 0 },
    dragStart: null,
    nextId: 1,
    _zoom: 1,
    _panX: 0,
    _panY: 0,
    _isPanning: false,
    _panStart: null,
    strategyName: 'My Strategy',
    strategyDesc: '',
    timeUnit: '5m',

    // Block definitions matching botcrypto
    blockTypes: {
        start: { label: 'START', icon: 'bi-play-circle', iconClass: 'n-start', category: 'flow', hasOutput: true, hasInput: false },
        terminate: { label: 'TERMINATE', icon: 'bi-stop-circle', iconClass: 'n-terminate', category: 'flow', hasOutput: false, hasInput: true, text: 'FIN' },
        buy: { label: 'BUY', icon: 'bi-cart-plus', iconClass: 'n-buy', category: 'action', hasOutput: true, hasInput: true, letter: 'A',
            params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: true }},
        sell: { label: 'SELL', icon: 'bi-cart-dash', iconClass: 'n-sell', category: 'action', hasOutput: true, hasInput: true, letter: 'V',
            params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: false }},
        indicator: { label: 'EMA', icon: 'bi-graph-up', iconClass: 'n-indicator', category: 'indicator', hasOutput: true, hasInput: true, hasTwoOutputs: false,
            params: { type: 'EMA', timeframe: '1m', period: 9, value: 0, condition: 'Crosses Over', compareType: 'EMA', comparePeriod: 26, compareValue: 0 }},
        gain: { label: 'GAIN', icon: 'bi-graph-up-arrow', iconClass: 'n-gain', category: 'condition', hasOutput: false, hasInput: true, hasTwoOutputs: true,
            params: { condition: 'Above', value: 2, trade: 'Last' }},
        group: { label: 'GROUP', icon: 'bi-diagram-2', iconClass: 'n-group', category: 'logic', hasOutput: true, hasInput: true,
            params: { logic: 'AND' }},
        stoploss: { label: 'STOP LOSS', icon: 'bi-shield-x', iconClass: 'n-stoploss', category: 'risk', hasOutput: true, hasInput: true,
            params: { value: -5, trade: 'Last' }},
        takeprofit: { label: 'TAKE PROFIT', icon: 'bi-trophy', iconClass: 'n-takeprofit', category: 'risk', hasOutput: true, hasInput: true,
            params: { value: 5, trade: 'Last' }},
        trailing: { label: 'TRAILING', icon: 'bi-graph-down-arrow', iconClass: 'n-trailing', category: 'risk', hasOutput: true, hasInput: true,
            params: { activation: 2, callback: 1 }},
        wait: { label: 'WAIT', icon: 'bi-hourglass-split', iconClass: 'n-wait', category: 'flow', hasOutput: true, hasInput: true,
            params: { duration: 5, unit: 'm' }},
        webhook: { label: 'WEBHOOK', icon: 'bi-link-45deg', iconClass: 'n-webhook', category: 'external', hasOutput: true, hasInput: true,
            params: { url: '' }},
        reset: { label: 'RESET', icon: 'bi-arrow-counterclockwise', iconClass: 'n-reset', category: 'flow', hasOutput: true, hasInput: true },
    },

    // Indicator types available
    indicatorTypes: [
        'EMA', 'SMA', 'RSI', 'MACD', 'Bollinger Bands', 'Stochastic',
        'ATR', 'CCI', 'Williams %R', 'Ichimoku', 'ADX', 'OBV',
        'VWAP', 'Parabolic SAR', 'Supertrend', 'Pivot Points',
        'Fear & Greed Index', 'MFI', 'ROC', 'TRIX'
    ],

    render() {
        return `
        <div class="builder-layout d-flex flex-column">
            <!-- Top Bar -->
            <div class="d-flex align-items-center justify-content-between border-bottom border-secondary px-2 px-md-3 py-2" style="background:var(--bc-bg-dark)">
                <div class="d-flex align-items-center gap-2 gap-md-3">
                    <button class="btn btn-link text-secondary p-0" onclick="App.navigate('dashboard')">
                        <i class="bi bi-chevron-left fs-5"></i>
                    </button>
                    <i class="bi bi-diagram-3 text-warning"></i>
                    <input type="text" class="form-control form-control-sm bg-transparent border-0 text-white fw-semibold"
                        style="width:200px;max-width:30vw" value="${this.strategyName}"
                        onchange="StrategyBuilderPage.strategyName = this.value">
                </div>
                <div class="d-flex align-items-center gap-2">
                    <button class="btn btn-sm btn-outline-secondary" onclick="StrategyBuilderPage.saveStrategy()" title="Save">
                        <i class="bi bi-save"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-secondary" onclick="StrategyBuilderPage.loadStrategy()" title="Load">
                        <i class="bi bi-folder-open"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-success" onclick="StrategyBuilderPage.generateCode()" title="Generate Code">
                        <i class="bi bi-code-slash"></i>
                    </button>
                    <select class="form-select form-select-sm border-secondary" style="width:80px;background:var(--bc-card);color:var(--bc-text)"
                        id="sbTimeUnit" onchange="StrategyBuilderPage.timeUnit = this.value">
                        <option value="1m">1m</option><option value="3m">3m</option>
                        <option value="5m" selected>5m</option><option value="15m">15m</option>
                        <option value="30m">30m</option><option value="1h">1h</option>
                        <option value="4h">4h</option><option value="1d">1d</option>
                    </select>
                    <button class="btn btn-warning btn-sm fw-semibold" onclick="StrategyBuilderPage.importStrategy()">
                        IMPORT <i class="bi bi-download ms-1"></i>
                    </button>
                    <button class="btn btn-success btn-sm fw-semibold" onclick="StrategyBuilderPage.exportStrategy()">
                        <i class="bi bi-play-fill me-1"></i> BACKTEST
                    </button>
                </div>
            </div>

            <!-- Canvas (full width, no sidebar) -->
            <div class="flex-grow-1 d-flex flex-column" style="min-height:0">
                <div id="builderCanvas" class="builder-canvas-wrapper flex-grow-1"
                     onmousedown="StrategyBuilderPage.onCanvasMouseDown(event)"
                     onmousemove="StrategyBuilderPage.onCanvasMouseMove(event)"
                     onmouseup="StrategyBuilderPage.onCanvasMouseUp(event)"
                     ondrop="StrategyBuilderPage.onDrop(event)"
                     ondragover="event.preventDefault()">
                    <div id="canvasTransform" class="canvas-transform">
                        <svg class="connections-layer" id="connectionsLayer"></svg>
                        <div id="nodesContainer" class="builder-canvas"></div>
                    </div>
                </div>
                <!-- Zoom controls -->
                <div class="builder-zoom-controls">
                    <button class="btn btn-sm btn-outline-secondary" onclick="StrategyBuilderPage.zoomIn()" title="Zoom in"><i class="bi bi-plus-lg"></i></button>
                    <span class="zoom-level" id="sbZoomLevel">100%</span>
                    <button class="btn btn-sm btn-outline-secondary" onclick="StrategyBuilderPage.zoomOut()" title="Zoom out"><i class="bi bi-dash-lg"></i></button>
                    <button class="btn btn-sm btn-outline-secondary ms-1" onclick="StrategyBuilderPage.zoomReset()" title="Reset view"><i class="bi bi-fullscreen"></i></button>
                </div>

                <!-- Indicator Picker Popup (hidden by default) -->
                <div class="indicator-picker-popup" id="indicatorPickerPopup">
                    <div class="indicator-picker-header">
                        <span class="fw-semibold">Choose an Indicator</span>
                        <button class="btn btn-sm btn-link text-secondary p-0" onclick="StrategyBuilderPage.closeIndicatorPicker()">
                            <i class="bi bi-x-lg"></i>
                        </button>
                    </div>
                    <input type="text" class="indicator-picker-search" id="indicatorSearch"
                        placeholder="Search indicators..." oninput="StrategyBuilderPage.filterIndicators(this.value)">
                    <div class="indicator-picker-list" id="indicatorPickerList">
                        ${this.indicatorTypes.map(t => `
                            <div class="indicator-picker-item" draggable="true"
                                 ondragstart="StrategyBuilderPage.onIndicatorDragStart(event, '${t}')"
                                 onclick="StrategyBuilderPage.addIndicatorNode('${t}')">
                                <i class="bi bi-graph-up text-info me-2"></i>
                                <span>${t}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>

                <!-- Bottom Toolbar - Single row block palette matching botcrypto.io -->
                <div class="builder-bottom-toolbar">
                    <div class="toolbar-blocks-row">
                        <div class="toolbar-block" onclick="StrategyBuilderPage.toggleIndicatorPicker(event)">
                            <div class="tb-icon tb-indicator position-relative">
                                <i class="bi bi-graph-up"></i>
                                <i class="bi bi-chevron-up indicator-arrow-up"></i>
                            </div>
                            <span class="tb-name">Indicators</span>
                        </div>
                        ${this._toolbarBlock('group', 'bi-diagram-2', 'Group', 'tb-group')}
                        ${this._toolbarBlock('gain', 'bi-graph-up-arrow', 'Gain', 'tb-gain')}
                        ${this._toolbarBlock('trailing', 'bi-graph-down-arrow', 'Trailing stop', 'tb-trailing')}
                        ${this._toolbarBlock('wait', 'bi-hourglass-split', 'Wait', 'tb-wait')}
                        ${this._toolbarBlock('webhook', 'bi-link-45deg', 'Webhook', 'tb-webhook')}
                        ${this._toolbarBlock('buy', 'bi-cart-plus', 'Buy', 'tb-buy')}
                        ${this._toolbarBlock('sell', 'bi-cart-dash', 'Sell', 'tb-sell')}
                        ${this._toolbarBlock('takeprofit', 'bi-trophy', 'Take Profit', 'tb-takeprofit')}
                        ${this._toolbarBlock('terminate', 'bi-stop-circle', 'Terminate', 'tb-terminate')}
                        ${this._toolbarBlock('reset', 'bi-arrow-counterclockwise', 'Reset', 'tb-reset')}
                    </div>
                </div>
            </div>
        </div>`;
    },

    _switchTab(el, tabId) {
        // Toggle active tab link
        document.querySelectorAll('#sbPanelTabs .nav-link').forEach(a => a.classList.remove('active'));
        el.classList.add('active');
        // Toggle tab pane
        document.querySelectorAll('.builder-tab-pane').forEach(p => p.classList.remove('active'));
        const pane = document.getElementById('sbTab-' + tabId);
        if (pane) pane.classList.add('active');
    },

    // ========== INDICATOR PICKER ==========
    toggleIndicatorPicker(event) {
        event.stopPropagation();
        const popup = document.getElementById('indicatorPickerPopup');
        if (!popup) return;
        popup.classList.toggle('open');
        if (popup.classList.contains('open')) {
            const search = document.getElementById('indicatorSearch');
            if (search) { search.value = ''; search.focus(); }
            this.filterIndicators('');
            // Close on outside click
            setTimeout(() => {
                this._indicatorPickerCloseHandler = (e) => {
                    if (!popup.contains(e.target) && !e.target.closest('.toolbar-block')) {
                        this.closeIndicatorPicker();
                    }
                };
                document.addEventListener('click', this._indicatorPickerCloseHandler);
            }, 10);
        } else {
            this._removeIndicatorPickerHandler();
        }
    },

    closeIndicatorPicker() {
        const popup = document.getElementById('indicatorPickerPopup');
        if (popup) popup.classList.remove('open');
        this._removeIndicatorPickerHandler();
    },

    _removeIndicatorPickerHandler() {
        if (this._indicatorPickerCloseHandler) {
            document.removeEventListener('click', this._indicatorPickerCloseHandler);
            this._indicatorPickerCloseHandler = null;
        }
    },

    filterIndicators(query) {
        const list = document.getElementById('indicatorPickerList');
        if (!list) return;
        const items = list.querySelectorAll('.indicator-picker-item');
        const q = query.toLowerCase();
        items.forEach(item => {
            const name = item.textContent.toLowerCase();
            item.style.display = name.includes(q) ? '' : 'none';
        });
    },

    addIndicatorNode(type) {
        this.closeIndicatorPicker();
        const canvas = document.getElementById('builderCanvas');
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        const x = (rect.width / 2 - this._panX) / this._zoom - 40 + Math.random() * 100;
        const y = (rect.height / 2 - this._panY) / this._zoom - 40 + Math.random() * 100;

        const bt = this.blockTypes.indicator;
        const node = {
            id: this.nextId++,
            type: 'indicator',
            x: Math.max(0, x),
            y: Math.max(0, y),
            params: { ...bt.params, type }
        };
        this.nodes.push(node);
        this.renderNodes();
        this.autoSave();
        App.showToast(`Added ${type} indicator`, 'success');
    },

    onIndicatorDragStart(event, indicatorType) {
        event.dataTransfer.setData('blockType', 'indicator');
        event.dataTransfer.setData('indicatorType', indicatorType);
        this.closeIndicatorPicker();
    },

    _toolbarBlock(type, icon, name, tbClass) {
        return `
        <div class="toolbar-block" draggable="true"
             ondragstart="StrategyBuilderPage.onDragStart(event, '${type}')"
             onclick="StrategyBuilderPage.addNode('${type}')">
            <div class="tb-icon ${tbClass}"><i class="bi ${icon}"></i></div>
            <span class="tb-name">${name}</span>
        </div>`;
    },

    init() {
        // Load saved strategy or create default
        const saved = localStorage.getItem('bc_strategy');
        if (saved) {
            try {
                const data = JSON.parse(saved);
                this.nodes = data.nodes || [];
                this.connections = data.connections || [];
                this.strategyName = data.name || 'My Strategy';
                this.strategyDesc = data.desc || '';
                this.nextId = data.nextId || 1;
            } catch { this.createDefaultNodes(); }
        } else {
            this.createDefaultNodes();
        }
        setTimeout(() => {
            this.renderNodes();
            this._applyTransform();
        }, 100);

        // Wheel zoom
        this._wheelHandler = (e) => {
            const canvas = document.getElementById('builderCanvas');
            if (!canvas || !canvas.contains(e.target)) return;
            e.preventDefault();
            const rect = canvas.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;
            const delta = e.deltaY > 0 ? -0.05 : 0.05;
            const newZoom = Math.min(3, Math.max(0.2, this._zoom + delta));
            // Zoom toward cursor
            const scale = newZoom / this._zoom;
            this._panX = mx - scale * (mx - this._panX);
            this._panY = my - scale * (my - this._panY);
            this._zoom = newZoom;
            this._applyTransform();
        };
        document.addEventListener('wheel', this._wheelHandler, { passive: false });

        // Keyboard shortcuts
        this._keyHandler = (e) => {
            if (e.key === 'Delete' || e.key === 'Backspace') {
                // Don't delete if typing in an input
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
                if (this.selectedNode) {
                    this.deleteNode(this.selectedNode);
                }
            }
            if (e.key === 'Escape') {
                this.connectingFrom = null;
                this._removeTempLine();
                this.selectedNode = null;
                this.renderNodes();
            }
        };
        document.addEventListener('keydown', this._keyHandler);
    },

    createDefaultNodes() {
        this.nodes = [
            { id: 1, type: 'start', x: 100, y: 250, params: {} },
            { id: 2, type: 'indicator', x: 300, y: 350, params: { type: 'EMA', timeframe: '1m', period: 9, value: 0, condition: 'Crosses Over', compareType: 'EMA', comparePeriod: 26, compareValue: 0 } },
            { id: 3, type: 'buy', x: 500, y: 250, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: true } },
            { id: 4, type: 'gain', x: 700, y: 180, params: { condition: 'Above', value: 2, trade: 'Last' } },
            { id: 5, type: 'sell', x: 900, y: 120, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: false } },
            { id: 6, type: 'gain', x: 700, y: 350, params: { condition: 'Below', value: -5, trade: 'Last' } },
            { id: 7, type: 'sell', x: 900, y: 350, params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: false } },
            { id: 8, type: 'terminate', x: 1100, y: 120, params: {} },
        ];
        this.connections = [
            { from: 1, to: 2, type: 'normal' },
            { from: 1, to: 3, type: 'normal' },
            { from: 2, to: 3, type: 'normal' },
            { from: 3, to: 4, type: 'normal' },
            { from: 3, to: 6, type: 'normal' },
            { from: 4, to: 5, type: 'true' },
            { from: 6, to: 7, type: 'true' },
            { from: 5, to: 8, type: 'normal' },
            { from: 7, to: 5, type: 'normal' },
        ];
        this.nextId = 9;
    },

    renderNodes() {
        const container = document.getElementById('nodesContainer');
        if (!container) return;

        container.innerHTML = this.nodes.map(node => this._renderNode(node)).join('');
        this.renderConnections();
    },

    _renderNode(node) {
        const bt = this.blockTypes[node.type];
        if (!bt) return '';

        const selected = this.selectedNode === node.id ? 'selected' : '';
        const letter = bt.letter || bt.text || bt.label.charAt(0);
        const nodeIndex = this.nodes.indexOf(node);

        // Build params pill label
        let paramsText = '';
        if (node.type === 'indicator') {
            const p = node.params;
            paramsText = `${p.timeframe} | ${p.type}${p.period ? '+' : ''} ${p.period} ${p.value} ${p.condition} ${p.compareType}...`;
        } else if (node.type === 'gain') {
            const p = node.params;
            paramsText = `${p.condition} ${p.value} ${p.trade}`;
        } else if (node.type === 'stoploss') {
            paramsText = `${node.params.value}% ${node.params.trade}`;
        } else if (node.type === 'takeprofit') {
            paramsText = `${node.params.value}% ${node.params.trade}`;
        } else if (node.type === 'trailing') {
            paramsText = `Act: ${node.params.activation}% CB: ${node.params.callback}%`;
        } else if (node.type === 'wait') {
            paramsText = `${node.params.duration}${node.params.unit}`;
        }

        // Volume pill for buy/sell nodes
        const volumeText = (node.type === 'buy' || node.type === 'sell') && node.params
            ? `${node.params.volume}${node.params.volumePercent ? ' %' : ''}`
            : '';

        // Node type class for distinctive styling
        const nodeTypeClass = `node-type-${node.type}`;
        const paramsClass = node.type === 'indicator' ? 'params-indicator' : node.type === 'gain' ? '' : '';

        return `
        <div class="canvas-node ${nodeTypeClass}" id="node-${node.id}" style="left:${node.x}px;top:${node.y}px"
             onmousedown="StrategyBuilderPage.onNodeMouseDown(event, ${node.id})"
             ondblclick="StrategyBuilderPage.editNode(${node.id})"
             oncontextmenu="StrategyBuilderPage.onNodeContextMenu(event, ${node.id})">
            <div class="node-badge">${nodeIndex}</div>
            <div class="node-body ${selected}">
                ${bt.hasInput ? `<div class="node-connector input" onmousedown="StrategyBuilderPage.onConnectorMouseDown(event, ${node.id}, 'input')"></div>` : ''}
                <div class="node-icon ${bt.iconClass}">
                    ${bt.letter ? `<span class="fw-bold fs-3">${letter}</span>` : bt.text ? `<span class="fw-bold small">${bt.text}</span>` : `<i class="bi ${bt.icon}"></i>`}
                </div>
                <div class="node-label">${node.type === 'indicator' ? (node.params.type || 'EMA') : bt.label}</div>
                ${bt.hasOutput && !bt.hasTwoOutputs ? `<div class="node-connector output" onmousedown="StrategyBuilderPage.onConnectorMouseDown(event, ${node.id}, 'output')"></div>` : ''}
                ${bt.hasTwoOutputs ? `
                    <div class="node-connector output-true" onmousedown="StrategyBuilderPage.onConnectorMouseDown(event, ${node.id}, 'output-true')"></div>
                    <div class="node-connector output-false" onmousedown="StrategyBuilderPage.onConnectorMouseDown(event, ${node.id}, 'output-false')"></div>
                ` : ''}
            </div>
            ${volumeText ? `<div class="node-volume-pill">${volumeText}</div>` : ''}
            ${paramsText ? `<div class="node-params ${paramsClass}">${paramsText}</div>` : ''}
        </div>`;
    },

    renderConnections() {
        const svg = document.getElementById('connectionsLayer');
        if (!svg) return;

        // Ensure SVG covers the full canvas area
        const wrapper = svg.parentElement;
        if (wrapper) {
            const maxX = Math.max(1200, ...this.nodes.map(n => n.x + 200));
            const maxY = Math.max(600, ...this.nodes.map(n => n.y + 200));
            svg.setAttribute('width', maxX);
            svg.setAttribute('height', maxY);
            svg.style.width = maxX + 'px';
            svg.style.height = maxY + 'px';
        }

        // SVG defs for arrowhead markers (use hardcoded colors - CSS vars don't work in SVG innerHTML)
        const defs = `<defs>
            <marker id="arrowNormal" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L10,4 L0,8 L2,4 Z" fill="#f5a623"/>
            </marker>
            <marker id="arrowTrue" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L10,4 L0,8 L2,4 Z" fill="#f5a623"/>
            </marker>
            <marker id="arrowFalse" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L10,4 L0,8 L2,4 Z" fill="#e74c5e"/>
            </marker>
        </defs>`;

        const paths = this.connections.map(conn => {
            const fromNode = this.nodes.find(n => n.id === conn.from);
            const toNode = this.nodes.find(n => n.id === conn.to);
            if (!fromNode || !toNode) return '';

            const fromBt = this.blockTypes[fromNode.type];
            // Output connector is on the right side of the node (node width ~90px)
            const x1 = fromNode.x + 90;
            let y1 = fromNode.y + 45;
            // Input connector is on the left side of the target node
            const x2 = toNode.x;
            const y2 = toNode.y + 45;

            // Adjust for two-output nodes
            if (fromBt && fromBt.hasTwoOutputs) {
                if (conn.type === 'true') y1 = fromNode.y + 30;
                else if (conn.type === 'false') y1 = fromNode.y + 60;
            }

            const dx = Math.abs(x2 - x1);
            const cx1 = x1 + Math.max(40, dx * 0.4);
            const cx2 = x2 - Math.max(40, dx * 0.4);

            const strokeColor = conn.type === 'false' ? '#e74c5e' : '#f5a623';
            const dashArray = conn.type === 'false' ? ' stroke-dasharray="6,3"' : '';
            const markerRef = conn.type === 'false' ? 'arrowFalse' : conn.type === 'true' ? 'arrowTrue' : 'arrowNormal';

            return `<path d="M${x1},${y1} C${cx1},${y1} ${cx2},${y2} ${x2},${y2}" fill="none" stroke="${strokeColor}" stroke-width="2.5"${dashArray} marker-end="url(#${markerRef})"/>`;
        }).join('');

        svg.innerHTML = defs + paths;
    },

    // ========== EVENT HANDLERS ==========
    onDragStart(event, type) {
        event.dataTransfer.setData('blockType', type);
    },

    onDrop(event) {
        event.preventDefault();
        const type = event.dataTransfer.getData('blockType');
        if (!type) return;

        const canvas = document.getElementById('builderCanvas');
        const rect = canvas.getBoundingClientRect();
        const x = (event.clientX - rect.left - this._panX) / this._zoom - 40;
        const y = (event.clientY - rect.top - this._panY) / this._zoom - 40;

        // If dragging a specific indicator type from the picker
        const indicatorType = event.dataTransfer.getData('indicatorType');
        if (type === 'indicator' && indicatorType) {
            const bt = this.blockTypes.indicator;
            const node = {
                id: this.nextId++,
                type: 'indicator',
                x: Math.max(0, x),
                y: Math.max(0, y),
                params: { ...bt.params, type: indicatorType }
            };
            this.nodes.push(node);
            this.renderNodes();
            this.autoSave();
            App.showToast(`Added ${indicatorType} indicator`, 'success');
            return;
        }

        this.addNodeAt(type, x, y);
    },

    addNode(type, x, y) {
        const canvas = document.getElementById('builderCanvas');
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        // Default position: center of visible canvas in canvas coords
        if (!x) x = (rect.width / 2 - this._panX) / this._zoom - 40 + Math.random() * 100;
        if (!y) y = (rect.height / 2 - this._panY) / this._zoom - 40 + Math.random() * 100;
        this.addNodeAt(type, x, y);
    },

    addNodeAt(type, x, y) {
        const bt = this.blockTypes[type];
        if (!bt) return;

        const node = {
            id: this.nextId++,
            type,
            x: Math.max(0, x),
            y: Math.max(0, y),
            params: bt.params ? { ...bt.params } : {}
        };

        this.nodes.push(node);
        this.renderNodes();
        this.autoSave();
        App.showToast(`Added ${bt.label} block`, 'success');
    },

    onNodeMouseDown(event, nodeId) {
        if (event.target.classList.contains('node-connector')) return;
        event.stopPropagation();

        this.draggingNode = nodeId;
        this.selectedNode = nodeId;

        const node = this.nodes.find(n => n.id === nodeId);
        this.dragStart = {
            mouseX: event.clientX,
            mouseY: event.clientY,
            nodeX: node.x,
            nodeY: node.y
        };

        this.renderNodes();
    },

    onConnectorMouseDown(event, nodeId, connType) {
        event.stopPropagation();
        event.preventDefault();

        if (connType === 'input') {
            // Complete connection
            if (this.connectingFrom) {
                // Don't connect to self
                if (this.connectingFrom.nodeId === nodeId) return;
                // Don't create duplicate connections
                const exists = this.connections.find(c => c.from === this.connectingFrom.nodeId && c.to === nodeId);
                if (exists) { App.showToast('Connection already exists', 'warning'); return; }

                this.connections.push({
                    from: this.connectingFrom.nodeId,
                    to: nodeId,
                    type: this.connectingFrom.type === 'output-true' ? 'true' :
                          this.connectingFrom.type === 'output-false' ? 'false' : 'normal'
                });
                this.connectingFrom = null;
                this._removeTempLine();
                this.renderConnections();
                this.autoSave();
                App.showToast('Connection created', 'success');
            }
        } else {
            // Start connection from output
            this.connectingFrom = { nodeId, type: connType };
            // Store starting position for temp line
            const node = this.nodes.find(n => n.id === nodeId);
            const bt = this.blockTypes[node.type];
            this._connStartX = node.x + 45;
            this._connStartY = node.y + 45;
            if (bt && bt.hasTwoOutputs) {
                this._connStartY = connType === 'output-true' ? node.y + 30 : node.y + 60;
            }
        }
    },

    _removeTempLine() {
        const svg = document.getElementById('connectionsLayer');
        if (svg) {
            const temp = svg.querySelector('#tempConnection');
            if (temp) temp.remove();
        }
    },

    onCanvasMouseDown(event) {
        if (event.target.id === 'builderCanvas' || event.target.id === 'canvasTransform' ||
            event.target.tagName === 'svg' ||
            (event.target.closest('.builder-canvas-wrapper') && !event.target.closest('.canvas-node'))) {
            this.selectedNode = null;
            this.connectingFrom = null;
            this._removeTempLine();
            // Start panning
            this._isPanning = true;
            this._panStart = { x: event.clientX, y: event.clientY, panX: this._panX, panY: this._panY };
            this.renderNodes();
        }
    },

    onCanvasMouseMove(event) {
        // Pan the canvas
        if (this._isPanning && this._panStart) {
            this._panX = this._panStart.panX + (event.clientX - this._panStart.x);
            this._panY = this._panStart.panY + (event.clientY - this._panStart.y);
            this._applyTransform();
            return;
        }

        // Draw temp connection line while connecting
        if (this.connectingFrom && this._connStartX !== undefined) {
            const canvas = document.getElementById('builderCanvas');
            if (!canvas) return;
            const rect = canvas.getBoundingClientRect();
            // Convert screen coords to canvas coords (account for zoom/pan)
            const mx = (event.clientX - rect.left - this._panX) / this._zoom;
            const my = (event.clientY - rect.top - this._panY) / this._zoom;
            const x1 = this._connStartX;
            const y1 = this._connStartY;
            const cx1 = x1 + 60;
            const cx2 = mx - 60;

            const svg = document.getElementById('connectionsLayer');
            if (svg) {
                let temp = svg.querySelector('#tempConnection');
                if (!temp) {
                    temp = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    temp.id = 'tempConnection';
                    temp.setAttribute('stroke', '#2dd4a8');
                    temp.setAttribute('stroke-width', '2');
                    temp.setAttribute('stroke-dasharray', '6,4');
                    temp.setAttribute('fill', 'none');
                    svg.appendChild(temp);
                }
                temp.setAttribute('d', `M${x1},${y1} C${cx1},${y1} ${cx2},${my} ${mx},${my}`);
            }
        }

        if (this.draggingNode && this.dragStart) {
            const node = this.nodes.find(n => n.id === this.draggingNode);
            if (!node) return;

            // Account for zoom when dragging nodes
            node.x = this.dragStart.nodeX + (event.clientX - this.dragStart.mouseX) / this._zoom;
            node.y = this.dragStart.nodeY + (event.clientY - this.dragStart.mouseY) / this._zoom;

            const el = document.getElementById(`node-${node.id}`);
            if (el) {
                el.style.left = node.x + 'px';
                el.style.top = node.y + 'px';
            }
            this.renderConnections();
        }
    },

    onCanvasMouseUp() {
        this._isPanning = false;
        this._panStart = null;
        if (this.draggingNode) {
            this.draggingNode = null;
            this.dragStart = null;
            this.autoSave();
        }
    },

    /** Right-click context menu on nodes */
    onNodeContextMenu(event, nodeId) {
        event.preventDefault();
        event.stopPropagation();

        // Remove existing menu
        document.querySelectorAll('.node-context-menu').forEach(m => m.remove());

        this.selectedNode = nodeId;
        this.renderNodes();

        const menu = document.createElement('div');
        menu.className = 'node-context-menu';
        menu.style.cssText = `position:fixed;left:${event.clientX}px;top:${event.clientY}px;z-index:9999;
            background:var(--bc-card-bg,#1c2128);border:1px solid var(--bc-border,#30363d);border-radius:8px;
            padding:4px 0;min-width:160px;box-shadow:0 8px 24px rgba(0,0,0,0.5)`;

        menu.innerHTML = `
            <div class="px-3 py-2 text-light small cursor-pointer" style="cursor:pointer"
                onmouseover="this.style.background='rgba(45,212,168,0.1)'" onmouseout="this.style.background=''"
                onclick="StrategyBuilderPage.editNode(${nodeId}); this.parentElement.remove()">
                <i class="bi bi-pencil me-2"></i>Edit Properties
            </div>
            <div class="px-3 py-2 text-light small" style="cursor:pointer"
                onmouseover="this.style.background='rgba(45,212,168,0.1)'" onmouseout="this.style.background=''"
                onclick="StrategyBuilderPage.duplicateNode(${nodeId}); this.parentElement.remove()">
                <i class="bi bi-copy me-2"></i>Duplicate
            </div>
            <div class="px-3 py-2 text-light small" style="cursor:pointer"
                onmouseover="this.style.background='rgba(45,212,168,0.1)'" onmouseout="this.style.background=''"
                onclick="StrategyBuilderPage.disconnectNode(${nodeId}); this.parentElement.remove()">
                <i class="bi bi-scissors me-2"></i>Disconnect All
            </div>
            <hr class="border-secondary my-1">
            <div class="px-3 py-2 text-danger small" style="cursor:pointer"
                onmouseover="this.style.background='rgba(248,81,73,0.1)'" onmouseout="this.style.background=''"
                onclick="StrategyBuilderPage.deleteNode(${nodeId}); this.parentElement.remove()">
                <i class="bi bi-trash me-2"></i>Delete
            </div>`;

        document.body.appendChild(menu);
        // Close on outside click
        setTimeout(() => {
            const handler = (e) => {
                if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', handler); }
            };
            document.addEventListener('click', handler);
        }, 10);
    },

    duplicateNode(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;
        const newNode = {
            id: this.nextId++,
            type: node.type,
            x: node.x + 80,
            y: node.y + 80,
            params: JSON.parse(JSON.stringify(node.params))
        };
        this.nodes.push(newNode);
        this.renderNodes();
        this.autoSave();
        App.showToast('Block duplicated', 'success');
    },

    disconnectNode(nodeId) {
        this.connections = this.connections.filter(c => c.from !== nodeId && c.to !== nodeId);
        this.renderConnections();
        this.autoSave();
        App.showToast('All connections removed', 'info');
    },

    // ========== NODE EDITING ==========
    editNode(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const bt = this.blockTypes[node.type];
        const offcanvas = document.getElementById('nodeProperties');
        const title = document.getElementById('nodePropertiesTitle');
        const body = document.getElementById('nodePropertiesBody');

        title.innerHTML = `<span class="me-2">${bt.letter || ''}</span> ${bt.label}`;

        let html = `<p class="text-secondary small">${this._getBlockDescription(node.type)}</p>`;

        if (node.type === 'buy' || node.type === 'sell') {
            html += this._orderPropertiesForm(node);
        } else if (node.type === 'indicator') {
            html += this._indicatorPropertiesForm(node);
        } else if (node.type === 'gain') {
            html += this._gainPropertiesForm(node);
        } else if (node.type === 'stoploss' || node.type === 'takeprofit') {
            html += this._riskPropertiesForm(node);
        } else if (node.type === 'trailing') {
            html += this._trailingPropertiesForm(node);
        } else if (node.type === 'wait') {
            html += this._waitPropertiesForm(node);
        } else if (node.type === 'group') {
            html += this._groupPropertiesForm(node);
        }

        html += `
        <hr class="border-secondary">
        <button class="btn btn-success w-100 fw-semibold py-2" onclick="StrategyBuilderPage.validateNode(${nodeId})">
            VALIDATE <i class="bi bi-chevron-right ms-1"></i>
        </button>
        <button class="btn btn-outline-danger btn-sm w-100 mt-2" onclick="StrategyBuilderPage.deleteNode(${nodeId})">
            <i class="bi bi-trash me-1"></i> Delete Block
        </button>`;

        body.innerHTML = html;
        new bootstrap.Offcanvas(offcanvas).show();
    },

    _getBlockDescription(type) {
        const descs = {
            buy: 'Send a market or limit buy order. Allows to manage currently opened bot orders.',
            sell: 'Send a market or limit sell order. Allows to manage currently opened bot orders.',
            indicator: 'Technical analysis indicator. Compare values to generate trading signals.',
            gain: 'Check the gain/loss of a trade. Routes flow based on condition.',
            stoploss: 'Automatically sell when loss exceeds threshold.',
            takeprofit: 'Automatically sell when profit reaches target.',
            trailing: 'Dynamic stop that follows price movement.',
            wait: 'Pause execution for a specified duration.',
            group: 'Group multiple conditions with AND/OR logic.',
            start: 'Entry point of the strategy.',
            terminate: 'End point of the strategy.',
            webhook: 'Receive external signals via webhook URL.',
            reset: 'Reset the strategy flow and start over.',
        };
        return descs[type] || '';
    },

    _orderPropertiesForm(node) {
        const p = node.params;
        return `
        <h6 class="text-light mb-2">Order type</h6>
        <div class="btn-group w-100 mb-3">
            <button class="btn ${p.orderType === 'Market' ? 'btn-success' : 'btn-outline-secondary'}"
                onclick="StrategyBuilderPage.updateParam(${node.id}, 'orderType', 'Market'); StrategyBuilderPage.editNode(${node.id})">Market</button>
            <button class="btn ${p.orderType === 'Limit' ? 'btn-success' : 'btn-outline-secondary'}"
                onclick="StrategyBuilderPage.updateParam(${node.id}, 'orderType', 'Limit'); StrategyBuilderPage.editNode(${node.id})">Limit</button>
        </div>

        <h6 class="text-light mb-2">Trade</h6>
        <div class="btn-group w-100 mb-3">
            ${['First', 'Open', 'Last', 'All'].map(t => `
                <button class="btn btn-sm ${p.trade === t ? 'btn-outline-success active' : 'btn-outline-secondary'}"
                    onclick="StrategyBuilderPage.updateParam(${node.id}, 'trade', '${t}'); StrategyBuilderPage.editNode(${node.id})">${t}</button>
            `).join('')}
        </div>

        <div class="row g-2 mb-3">
            <div class="col">
                <h6 class="text-light mb-2">Volume</h6>
                <div class="input-group">
                    <input type="number" class="form-control" value="${p.volume}"
                        onchange="StrategyBuilderPage.updateParam(${node.id}, 'volume', parseFloat(this.value))">
                    <span class="input-group-text">%</span>
                    <div class="input-group-text">
                        <div class="form-check form-switch mb-0">
                            <input type="checkbox" class="form-check-input" ${p.volumePercent ? 'checked' : ''}
                                onchange="StrategyBuilderPage.updateParam(${node.id}, 'volumePercent', this.checked)">
                        </div>
                    </div>
                </div>
            </div>
            <div class="col">
                <h6 class="text-light mb-2">Price</h6>
                <input type="number" class="form-control" value="${p.price}" step="0.01"
                    onchange="StrategyBuilderPage.updateParam(${node.id}, 'price', parseFloat(this.value))"
                    ${p.orderType === 'Market' ? 'disabled' : ''}>
            </div>
        </div>

        <div class="form-check form-switch mb-3">
            <input type="checkbox" class="form-check-input" id="assetQuote-${node.id}" ${p.assetQuote ? 'checked' : ''}
                onchange="StrategyBuilderPage.updateParam(${node.id}, 'assetQuote', this.checked)">
            <label class="form-check-label text-light" for="assetQuote-${node.id}">Asset Quote</label>
        </div>`;
    },

    _indicatorPropertiesForm(node) {
        const p = node.params;
        return `
        <h6 class="text-light mb-2">Indicator Type</h6>
        <select class="form-select mb-3" onchange="StrategyBuilderPage.updateParam(${node.id}, 'type', this.value); StrategyBuilderPage.editNode(${node.id})">
            ${this.indicatorTypes.map(t => `<option value="${t}" ${p.type === t ? 'selected' : ''}>${t}</option>`).join('')}
        </select>

        <div class="row g-2 mb-3">
            <div class="col">
                <label class="form-label small text-secondary">Timeframe</label>
                <select class="form-select form-select-sm" onchange="StrategyBuilderPage.updateParam(${node.id}, 'timeframe', this.value)">
                    ${['1m','5m','15m','30m','1h','4h','1d'].map(t => `<option ${p.timeframe === t ? 'selected' : ''}>${t}</option>`).join('')}
                </select>
            </div>
            <div class="col">
                <label class="form-label small text-secondary">Period</label>
                <input type="number" class="form-control form-control-sm" value="${p.period}"
                    onchange="StrategyBuilderPage.updateParam(${node.id}, 'period', parseInt(this.value))">
            </div>
            <div class="col">
                <label class="form-label small text-secondary">Value</label>
                <input type="number" class="form-control form-control-sm" value="${p.value}" step="0.01"
                    onchange="StrategyBuilderPage.updateParam(${node.id}, 'value', parseFloat(this.value))">
            </div>
        </div>

        <h6 class="text-light mb-2">Condition</h6>
        <select class="form-select mb-3" onchange="StrategyBuilderPage.updateParam(${node.id}, 'condition', this.value)">
            ${['Crosses Over', 'Crosses Under', 'Above', 'Below', 'Equals'].map(c => `<option ${p.condition === c ? 'selected' : ''}>${c}</option>`).join('')}
        </select>

        <h6 class="text-light mb-2">Compare With</h6>
        <div class="row g-2 mb-3">
            <div class="col">
                <select class="form-select form-select-sm" onchange="StrategyBuilderPage.updateParam(${node.id}, 'compareType', this.value)">
                    ${this.indicatorTypes.map(t => `<option ${p.compareType === t ? 'selected' : ''}>${t}</option>`).join('')}
                    <option ${p.compareType === 'Value' ? 'selected' : ''}>Value</option>
                    <option ${p.compareType === 'Price' ? 'selected' : ''}>Price</option>
                </select>
            </div>
            <div class="col">
                <input type="number" class="form-control form-control-sm" value="${p.comparePeriod}"
                    onchange="StrategyBuilderPage.updateParam(${node.id}, 'comparePeriod', parseInt(this.value))">
            </div>
        </div>`;
    },

    _gainPropertiesForm(node) {
        const p = node.params;
        return `
        <h6 class="text-light mb-2">Condition</h6>
        <select class="form-select mb-3" onchange="StrategyBuilderPage.updateParam(${node.id}, 'condition', this.value)">
            ${['Above', 'Below', 'Equals'].map(c => `<option ${p.condition === c ? 'selected' : ''}>${c}</option>`).join('')}
        </select>

        <h6 class="text-light mb-2">Value (%)</h6>
        <input type="number" class="form-control mb-3" value="${p.value}" step="0.1"
            onchange="StrategyBuilderPage.updateParam(${node.id}, 'value', parseFloat(this.value))">

        <h6 class="text-light mb-2">Trade</h6>
        <div class="btn-group w-100 mb-3">
            ${['First', 'Open', 'Last', 'All'].map(t => `
                <button class="btn btn-sm ${p.trade === t ? 'btn-outline-success active' : 'btn-outline-secondary'}"
                    onclick="StrategyBuilderPage.updateParam(${node.id}, 'trade', '${t}'); StrategyBuilderPage.editNode(${node.id})">${t}</button>
            `).join('')}
        </div>`;
    },

    _riskPropertiesForm(node) {
        const p = node.params;
        const label = node.type === 'stoploss' ? 'Stop Loss' : 'Take Profit';
        return `
        <h6 class="text-light mb-2">${label} Value (%)</h6>
        <input type="number" class="form-control mb-3" value="${p.value}" step="0.1"
            onchange="StrategyBuilderPage.updateParam(${node.id}, 'value', parseFloat(this.value))">

        <h6 class="text-light mb-2">Trade</h6>
        <div class="btn-group w-100 mb-3">
            ${['First', 'Open', 'Last', 'All'].map(t => `
                <button class="btn btn-sm ${p.trade === t ? 'btn-outline-success active' : 'btn-outline-secondary'}"
                    onclick="StrategyBuilderPage.updateParam(${node.id}, 'trade', '${t}'); StrategyBuilderPage.editNode(${node.id})">${t}</button>
            `).join('')}
        </div>`;
    },

    _trailingPropertiesForm(node) {
        const p = node.params;
        return `
        <h6 class="text-light mb-2">Activation (%)</h6>
        <input type="number" class="form-control mb-3" value="${p.activation}" step="0.1"
            onchange="StrategyBuilderPage.updateParam(${node.id}, 'activation', parseFloat(this.value))">

        <h6 class="text-light mb-2">Callback (%)</h6>
        <input type="number" class="form-control mb-3" value="${p.callback}" step="0.1"
            onchange="StrategyBuilderPage.updateParam(${node.id}, 'callback', parseFloat(this.value))">`;
    },

    _waitPropertiesForm(node) {
        const p = node.params;
        return `
        <h6 class="text-light mb-2">Duration</h6>
        <div class="input-group mb-3">
            <input type="number" class="form-control" value="${p.duration}"
                onchange="StrategyBuilderPage.updateParam(${node.id}, 'duration', parseInt(this.value))">
            <select class="form-select" style="max-width:80px"
                onchange="StrategyBuilderPage.updateParam(${node.id}, 'unit', this.value)">
                <option value="m" ${p.unit === 'm' ? 'selected' : ''}>min</option>
                <option value="h" ${p.unit === 'h' ? 'selected' : ''}>hour</option>
                <option value="d" ${p.unit === 'd' ? 'selected' : ''}>day</option>
            </select>
        </div>`;
    },

    _groupPropertiesForm(node) {
        const p = node.params;
        return `
        <h6 class="text-light mb-2">Logic</h6>
        <div class="btn-group w-100 mb-3">
            <button class="btn ${p.logic === 'AND' ? 'btn-success' : 'btn-outline-secondary'}"
                onclick="StrategyBuilderPage.updateParam(${node.id}, 'logic', 'AND'); StrategyBuilderPage.editNode(${node.id})">AND</button>
            <button class="btn ${p.logic === 'OR' ? 'btn-success' : 'btn-outline-secondary'}"
                onclick="StrategyBuilderPage.updateParam(${node.id}, 'logic', 'OR'); StrategyBuilderPage.editNode(${node.id})">OR</button>
        </div>`;
    },

    // ========== NODE OPERATIONS ==========
    updateParam(nodeId, key, value) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (node) {
            node.params[key] = value;
            this.renderNodes();
            this.autoSave();
        }
    },

    validateNode(nodeId) {
        const offcanvas = bootstrap.Offcanvas.getInstance(document.getElementById('nodeProperties'));
        if (offcanvas) offcanvas.hide();
        this.renderNodes();
        this.autoSave();
        App.showToast('Block validated', 'success');
    },

    deleteNode(nodeId) {
        this.nodes = this.nodes.filter(n => n.id !== nodeId);
        this.connections = this.connections.filter(c => c.from !== nodeId && c.to !== nodeId);
        const offcanvas = bootstrap.Offcanvas.getInstance(document.getElementById('nodeProperties'));
        if (offcanvas) offcanvas.hide();
        this.selectedNode = null;
        this.renderNodes();
        this.autoSave();
        App.showToast('Block deleted', 'info');
    },

    // ========== STRATEGY CODE GENERATION ==========
    generateCode() {
        const code = this._buildFreqtradeStrategy();
        // Show in modal
        const modal = document.createElement('div');
        modal.innerHTML = `
        <div class="modal fade" tabindex="-1">
            <div class="modal-dialog modal-lg modal-dialog-scrollable">
                <div class="modal-content bg-dark border-secondary">
                    <div class="modal-header border-secondary">
                        <h5 class="modal-title"><i class="bi bi-code-slash me-2"></i>Generated Strategy Code</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <pre class="bg-black p-3 rounded text-success small" style="max-height:500px;overflow:auto"><code>${this._escapeHtml(code)}</code></pre>
                    </div>
                    <div class="modal-footer border-secondary">
                        <button class="btn btn-outline-success" onclick="navigator.clipboard.writeText(\`${code.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`); App.showToast('Copied to clipboard', 'success')">
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
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    _buildFreqtradeStrategy() {
        const name = this.strategyName.replace(/[^a-zA-Z0-9]/g, '_');
        const indicators = this.nodes.filter(n => n.type === 'indicator');
        const buyNodes = this.nodes.filter(n => n.type === 'buy');
        const sellNodes = this.nodes.filter(n => n.type === 'sell');
        const gainNodes = this.nodes.filter(n => n.type === 'gain');
        const stoplossNodes = this.nodes.filter(n => n.type === 'stoploss');
        const trailingNodes = this.nodes.filter(n => n.type === 'trailing');

        // Build indicator code
        let indicatorCode = '';
        indicators.forEach(ind => {
            const p = ind.params;
            const indType = (p.type || 'EMA').toLowerCase();
            if (indType === 'ema') {
                indicatorCode += `        dataframe['ema_${p.period}'] = ta.EMA(dataframe, timeperiod=${p.period})\n`;
                if (p.compareType && p.compareType.toLowerCase() === 'ema') {
                    indicatorCode += `        dataframe['ema_${p.comparePeriod}'] = ta.EMA(dataframe, timeperiod=${p.comparePeriod})\n`;
                }
            } else if (indType === 'sma') {
                indicatorCode += `        dataframe['sma_${p.period}'] = ta.SMA(dataframe, timeperiod=${p.period})\n`;
            } else if (indType === 'rsi') {
                indicatorCode += `        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=${p.period})\n`;
            } else if (indType === 'macd') {
                indicatorCode += `        macd = ta.MACD(dataframe)\n        dataframe['macd'] = macd['macd']\n        dataframe['macdsignal'] = macd['macdsignal']\n`;
            } else if (indType === 'bollinger bands') {
                indicatorCode += `        bollinger = ta.BBANDS(dataframe, timeperiod=${p.period})\n        dataframe['bb_upper'] = bollinger['upperband']\n        dataframe['bb_middle'] = bollinger['middleband']\n        dataframe['bb_lower'] = bollinger['lowerband']\n`;
            } else {
                indicatorCode += `        # TODO: Implement ${p.type} indicator\n        dataframe['${indType}_${p.period}'] = ta.EMA(dataframe, timeperiod=${p.period})\n`;
            }
        });

        // Build entry conditions
        let entryConditions = [];
        indicators.forEach(ind => {
            const p = ind.params;
            const indType = (p.type || 'EMA').toLowerCase();
            const col1 = `${indType}_${p.period}`;
            let col2 = '';
            if (p.compareType && p.compareType.toLowerCase() !== 'value' && p.compareType.toLowerCase() !== 'price') {
                col2 = `${p.compareType.toLowerCase()}_${p.comparePeriod}`;
            }

            if (p.condition === 'Crosses Over' && col2) {
                entryConditions.push(`(qtpylib.crossed_above(dataframe['${col1}'], dataframe['${col2}']))`);
            } else if (p.condition === 'Crosses Under' && col2) {
                entryConditions.push(`(qtpylib.crossed_below(dataframe['${col1}'], dataframe['${col2}']))`);
            } else if (p.condition === 'Above') {
                const cmp = col2 ? `dataframe['${col2}']` : p.compareValue || p.value;
                entryConditions.push(`(dataframe['${col1}'] > ${cmp})`);
            } else if (p.condition === 'Below') {
                const cmp = col2 ? `dataframe['${col2}']` : p.compareValue || p.value;
                entryConditions.push(`(dataframe['${col1}'] < ${cmp})`);
            }
        });

        // Stoploss value
        let stoplossValue = -0.05;
        if (stoplossNodes.length > 0) {
            stoplossValue = stoplossNodes[0].params.value / 100;
        }

        // ROI from gain nodes
        let roi = '{"0": 0.04}';
        if (gainNodes.length > 0) {
            const gains = gainNodes.filter(g => g.params.condition === 'Above');
            if (gains.length > 0) {
                roi = `{"0": ${gains[0].params.value / 100}}`;
            }
        }

        // Trailing stop
        let trailingCode = 'False';
        let trailingOffset = '';
        if (trailingNodes.length > 0) {
            trailingCode = 'True';
            trailingOffset = `
    trailing_stop_positive = ${trailingNodes[0].params.activation / 100}
    trailing_stop_positive_offset = ${(trailingNodes[0].params.activation + trailingNodes[0].params.callback) / 100}
    trailing_only_offset_is_reached = True`;
        }

        return `# --- Generated by BotCrypto Visual Strategy Builder ---
# Strategy: ${this.strategyName}
# ${this.strategyDesc || 'Auto-generated strategy'}

import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy, merge_informative_candle
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame


class ${name}(IStrategy):
    """
    ${this.strategyDesc || this.strategyName}
    Generated by BotCrypto Visual Strategy Builder
    """

    INTERFACE_VERSION = 3

    timeframe = '${this.timeUnit}'

    minimal_roi = ${roi}

    stoploss = ${stoplossValue}

    trailing_stop = ${trailingCode}${trailingOffset}

    # Run "populate_indicators()" only for new candle
    process_only_new_candles = True

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count = 30

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
${indicatorCode || '        # No indicators defined\n        pass'}
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []
${entryConditions.length > 0 ?
    entryConditions.map(c => `        conditions.append(${c})`).join('\n') + `
        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'enter_long'] = 1` :
    '        # No entry conditions defined - add conditions in the visual builder\n        pass'}
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit conditions from visual builder
        # ROI and stoploss handle most exits
        return dataframe
`;
    },

    // ========== SAVE / LOAD ==========
    autoSave() {
        localStorage.setItem('bc_strategy', JSON.stringify({
            name: this.strategyName,
            desc: this.strategyDesc,
            nodes: this.nodes,
            connections: this.connections,
            nextId: this.nextId,
            timeUnit: this.timeUnit
        }));
    },

    saveStrategy() {
        this.autoSave();
        // Also save to strategies list
        const strategies = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
        const existing = strategies.findIndex(s => s.name === this.strategyName);
        const data = {
            name: this.strategyName,
            desc: this.strategyDesc,
            nodes: this.nodes,
            connections: this.connections,
            nextId: this.nextId,
            timeUnit: this.timeUnit,
            savedAt: new Date().toISOString()
        };
        if (existing >= 0) strategies[existing] = data;
        else strategies.push(data);
        localStorage.setItem('bc_strategies', JSON.stringify(strategies));
        App.showToast('Strategy saved', 'success');
    },

    loadStrategy() {
        const strategies = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
        if (strategies.length === 0) {
            App.showToast('No saved strategies found', 'warning');
            return;
        }
        // Show picker
        const list = strategies.map((s, i) => `
            <button class="list-group-item list-group-item-action bg-dark text-light border-secondary"
                onclick="StrategyBuilderPage._loadStrategyByIndex(${i})">
                <div class="fw-semibold">${s.name}</div>
                <small class="text-secondary">${s.desc || 'No description'} - ${Components.formatDate(s.savedAt)}</small>
            </button>`).join('');

        const modal = document.createElement('div');
        modal.innerHTML = `
        <div class="modal fade" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content bg-dark border-secondary">
                    <div class="modal-header border-secondary">
                        <h5 class="modal-title">Load Strategy</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="list-group">${list}</div>
                    </div>
                </div>
            </div>
        </div>`;
        document.body.appendChild(modal);
        this._loadModal = new bootstrap.Modal(modal.querySelector('.modal'));
        this._loadModal.show();
        this._loadModalEl = modal;
        modal.querySelector('.modal').addEventListener('hidden.bs.modal', () => modal.remove());
    },

    _loadStrategyByIndex(index) {
        const strategies = JSON.parse(localStorage.getItem('bc_strategies') || '[]');
        const s = strategies[index];
        if (!s) return;
        this.nodes = s.nodes;
        this.connections = s.connections;
        this.strategyName = s.name;
        this.strategyDesc = s.desc;
        this.nextId = s.nextId;
        this.timeUnit = s.timeUnit || '5m';
        if (this._loadModal) this._loadModal.hide();
        this.renderNodes();
        App.showToast(`Loaded: ${s.name}`, 'success');
    },

    importStrategy() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.py';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            try {
                const content = await file.text();
                const name = file.name.replace(/\.py$/, '');

                // Upload to Freqtrade user_data/strategies/ so it's available for backtesting
                let uploaded = false;
                if (API.connected) {
                    try {
                        await API.request('/strategies/upload', {
                            method: 'POST',
                            body: JSON.stringify({ strategy: content, name })
                        });
                        uploaded = true;
                        App.showToast(`Strategy "${name}" saved to Freqtrade strategies folder`, 'success');
                    } catch (err) {
                        console.log('Upload to Freqtrade failed:', err.message);
                        App.showToast(`Could not upload to Freqtrade: ${err.message}`, 'warning');
                    }
                }

                // Also store the raw .py content in localStorage as backup
                const importedStrategies = JSON.parse(localStorage.getItem('bc_imported_strategies') || '{}');
                importedStrategies[name] = { content, importedAt: new Date().toISOString(), uploaded };
                localStorage.setItem('bc_imported_strategies', JSON.stringify(importedStrategies));

                // Parse the Python strategy into visual flow nodes
                this._parseStrategyToFlow(content, name);
                this.renderNodes();
                this.autoSave();
                if (!uploaded) {
                    App.showToast(`Strategy "${name}" imported locally (connect to Freqtrade to use for backtesting)`, 'info');
                }

            } catch (err) {
                App.showToast(`Import failed: ${err.message}`, 'error');
            }
        };
        input.click();
    },

    /** Parse a Freqtrade .py strategy file into visual flow nodes */
    _parseStrategyToFlow(code, fileName) {
        // Reset
        this.nodes = [];
        this.connections = [];
        this.nextId = 1;

        // Extract class name
        const classMatch = code.match(/class\s+(\w+)\s*\(/);
        this.strategyName = classMatch ? classMatch[1] : fileName;

        // Extract docstring as description
        const docMatch = code.match(/class\s+\w+[^:]*:\s*\n\s*"""([\s\S]*?)"""/);
        this.strategyDesc = docMatch ? docMatch[1].trim().split('\n')[0] : '';

        // Extract timeframe
        const tfMatch = code.match(/timeframe\s*=\s*['"](\w+)['"]/);
        if (tfMatch) {
            this.timeUnit = tfMatch[1];
            const sel = document.getElementById('sbTimeUnit');
            if (sel) sel.value = tfMatch[1];
        }

        // Extract stoploss
        const slMatch = code.match(/stoploss\s*=\s*(-?[\d.]+)/);
        const stoplossVal = slMatch ? parseFloat(slMatch[1]) * 100 : -5;

        // Extract trailing stop
        const trailMatch = code.match(/trailing_stop\s*=\s*True/);
        const trailPosMatch = code.match(/trailing_stop_positive\s*=\s*([\d.]+)/);
        const trailOffMatch = code.match(/trailing_stop_positive_offset\s*=\s*([\d.]+)/);

        // Extract minimal_roi
        const roiMatch = code.match(/minimal_roi\s*=\s*\{([^}]+)\}/);
        let roiVal = 4;
        if (roiMatch) {
            const roiEntries = roiMatch[1].match(/:\s*([\d.]+)/g);
            if (roiEntries && roiEntries.length > 0) {
                roiVal = parseFloat(roiEntries[0].replace(':', '').trim()) * 100;
            }
        }

        // Extract indicators from populate_indicators
        const indSection = this._extractFunction(code, 'populate_indicators');
        const indicators = this._parseIndicators(indSection);

        // Extract entry conditions from populate_entry_trend
        const entrySection = this._extractFunction(code, 'populate_entry_trend');
        const entryConditions = this._parseConditions(entrySection, 'entry');

        // Extract exit conditions from populate_exit_trend
        const exitSection = this._extractFunction(code, 'populate_exit_trend');
        const exitConditions = this._parseConditions(exitSection, 'exit');

        // Build visual flow
        const xStep = 200;
        const yCenter = 250;
        let x = 50;

        // 1. START node
        const startNode = { id: this.nextId++, type: 'start', x, y: yCenter, params: {} };
        this.nodes.push(startNode);
        x += xStep;

        // 2. Indicator nodes
        const indicatorNodes = [];
        indicators.forEach((ind, i) => {
            const node = {
                id: this.nextId++, type: 'indicator',
                x, y: yCenter - 80 + i * 160,
                params: {
                    type: ind.type, timeframe: this.timeUnit || '5m',
                    period: ind.period, value: ind.value || 0,
                    condition: ind.condition || 'Crosses Over',
                    compareType: ind.compareType || 'Value',
                    comparePeriod: ind.comparePeriod || 0,
                    compareValue: ind.compareValue || 0
                }
            };
            this.nodes.push(node);
            indicatorNodes.push(node);
            // Connect start → indicator
            this.connections.push({ from: startNode.id, to: node.id, type: 'normal' });
        });
        if (indicatorNodes.length > 0) x += xStep;

        // 3. Group node if multiple indicators
        let preEntryNode = startNode;
        if (indicatorNodes.length > 1) {
            const groupNode = { id: this.nextId++, type: 'group', x, y: yCenter, params: { logic: 'AND' } };
            this.nodes.push(groupNode);
            indicatorNodes.forEach(ind => {
                this.connections.push({ from: ind.id, to: groupNode.id, type: 'normal' });
            });
            preEntryNode = groupNode;
            x += xStep;
        } else if (indicatorNodes.length === 1) {
            preEntryNode = indicatorNodes[0];
        }

        // 4. BUY node
        const buyNode = {
            id: this.nextId++, type: 'buy', x, y: yCenter,
            params: { orderType: 'Market', trade: 'First', volume: 100, volumePercent: true, price: 0, assetQuote: true }
        };
        this.nodes.push(buyNode);
        this.connections.push({ from: preEntryNode.id, to: buyNode.id, type: 'normal' });
        x += xStep;

        // 5. Take profit (gain) node
        const gainNode = {
            id: this.nextId++, type: 'gain', x, y: yCenter - 100,
            params: { condition: 'Above', value: roiVal, trade: 'Last' }
        };
        this.nodes.push(gainNode);
        this.connections.push({ from: buyNode.id, to: gainNode.id, type: 'normal' });

        // 6. Stoploss node
        const slNode = {
            id: this.nextId++, type: 'stoploss', x, y: yCenter + 100,
            params: { value: stoplossVal, trade: 'All' }
        };
        this.nodes.push(slNode);
        this.connections.push({ from: buyNode.id, to: slNode.id, type: 'normal' });
        x += xStep;

        // 7. SELL node (from gain)
        const sellNode = {
            id: this.nextId++, type: 'sell', x, y: yCenter,
            params: { orderType: 'Market', trade: 'All', volume: 100, volumePercent: true, price: 0, assetQuote: false }
        };
        this.nodes.push(sellNode);
        this.connections.push({ from: gainNode.id, to: sellNode.id, type: 'true' });
        this.connections.push({ from: slNode.id, to: sellNode.id, type: 'normal' });

        // 8. Trailing stop if enabled
        if (trailMatch) {
            const trailNode = {
                id: this.nextId++, type: 'trailing', x: x - xStep, y: yCenter + 200,
                params: {
                    activation: trailPosMatch ? parseFloat(trailPosMatch[1]) * 100 : 1,
                    callback: trailOffMatch ? (parseFloat(trailOffMatch[1]) - (trailPosMatch ? parseFloat(trailPosMatch[1]) : 0)) * 100 : 0.5
                }
            };
            this.nodes.push(trailNode);
            this.connections.push({ from: buyNode.id, to: trailNode.id, type: 'normal' });
        }
        x += xStep;

        // 9. TERMINATE node
        const endNode = { id: this.nextId++, type: 'terminate', x, y: yCenter, params: {} };
        this.nodes.push(endNode);
        this.connections.push({ from: sellNode.id, to: endNode.id, type: 'normal' });

        // Update name input
        const nameInput = document.querySelector('input[onchange*="strategyName"]');
        if (nameInput) nameInput.value = this.strategyName;
        const descInput = document.querySelector('textarea[onchange*="strategyDesc"]');
        if (descInput) descInput.value = this.strategyDesc;
    },

    /** Extract a function body from Python code */
    _extractFunction(code, funcName) {
        const regex = new RegExp(`def\\s+${funcName}\\s*\\([^)]*\\)[^:]*:[\\s\\S]*?(?=\\n    def |\\nclass |$)`, 'g');
        const match = regex.exec(code);
        return match ? match[0] : '';
    },

    /** Parse indicator definitions from populate_indicators code */
    _parseIndicators(code) {
        const indicators = [];
        // EMA
        const emaMatches = code.matchAll(/ta\.EMA\s*\([^,]*,\s*timeperiod\s*=\s*(\d+)/g);
        const emaPeriods = new Set();
        for (const m of emaMatches) {
            const period = parseInt(m[1]);
            if (!emaPeriods.has(period)) {
                emaPeriods.add(period);
            }
        }
        // Check for crossover in entry to pair EMAs
        const emaPeriodArr = [...emaPeriods];
        if (emaPeriodArr.length >= 2) {
            indicators.push({
                type: 'EMA', period: emaPeriodArr[0],
                condition: 'Crosses Over', compareType: 'EMA',
                comparePeriod: emaPeriodArr[1], value: 0, compareValue: 0
            });
        } else if (emaPeriodArr.length === 1) {
            indicators.push({ type: 'EMA', period: emaPeriodArr[0], condition: 'Above', compareType: 'Value', value: 0 });
        }

        // SMA
        const smaMatches = code.matchAll(/ta\.SMA\s*\([^,]*,\s*timeperiod\s*=\s*(\d+)/g);
        const smaPeriods = new Set();
        for (const m of smaMatches) { smaPeriods.add(parseInt(m[1])); }
        const smaPeriodArr = [...smaPeriods];
        if (smaPeriodArr.length >= 2) {
            indicators.push({ type: 'SMA', period: smaPeriodArr[0], condition: 'Crosses Over', compareType: 'SMA', comparePeriod: smaPeriodArr[1], value: 0, compareValue: 0 });
        } else if (smaPeriodArr.length === 1) {
            indicators.push({ type: 'SMA', period: smaPeriodArr[0], condition: 'Above', compareType: 'Value', value: 0 });
        }

        // RSI
        const rsiMatch = code.match(/ta\.RSI\s*\([^,]*,\s*timeperiod\s*=\s*(\d+)/);
        if (rsiMatch) {
            indicators.push({ type: 'RSI', period: parseInt(rsiMatch[1]), condition: 'Below', compareType: 'Value', value: 30, compareValue: 30 });
        }

        // MACD
        if (code.includes('ta.MACD')) {
            indicators.push({ type: 'MACD', period: 12, condition: 'Crosses Over', compareType: 'Value', value: 0, compareValue: 0 });
        }

        // Bollinger Bands
        const bbMatch = code.match(/ta\.BBANDS\s*\([^,]*,\s*timeperiod\s*=\s*(\d+)/);
        if (bbMatch) {
            indicators.push({ type: 'Bollinger Bands', period: parseInt(bbMatch[1]), condition: 'Below', compareType: 'Value', value: 0, compareValue: 0 });
        }

        return indicators;
    },

    /** Parse entry/exit conditions */
    _parseConditions(code, type) {
        const conditions = [];
        // Look for crossed_above / crossed_below
        const crossAbove = code.matchAll(/crossed_above\s*\(\s*dataframe\['([^']+)'\]\s*,\s*dataframe\['([^']+)'\]/g);
        for (const m of crossAbove) conditions.push({ col1: m[1], col2: m[2], op: 'Crosses Over' });

        const crossBelow = code.matchAll(/crossed_below\s*\(\s*dataframe\['([^']+)'\]\s*,\s*dataframe\['([^']+)'\]/g);
        for (const m of crossBelow) conditions.push({ col1: m[1], col2: m[2], op: 'Crosses Under' });

        // Simple comparisons
        const gtMatch = code.matchAll(/dataframe\['([^']+)'\]\s*>\s*(\d+[\d.]*)/g);
        for (const m of gtMatch) conditions.push({ col1: m[1], value: parseFloat(m[2]), op: 'Above' });

        const ltMatch = code.matchAll(/dataframe\['([^']+)'\]\s*<\s*(\d+[\d.]*)/g);
        for (const m of ltMatch) conditions.push({ col1: m[1], value: parseFloat(m[2]), op: 'Below' });

        return conditions;
    },

    exportStrategy() {
        // Go to backtesting with current strategy
        this.saveStrategy();
        App.navigate('backtesting');
    },

    // ========== ZOOM & PAN ==========
    _applyTransform() {
        const el = document.getElementById('canvasTransform');
        if (el) {
            el.style.transform = `translate(${this._panX}px, ${this._panY}px) scale(${this._zoom})`;
        }
        const lbl = document.getElementById('sbZoomLevel');
        if (lbl) lbl.textContent = Math.round(this._zoom * 100) + '%';
    },

    zoomIn() {
        this._zoom = Math.min(3, this._zoom + 0.1);
        this._applyTransform();
    },

    zoomOut() {
        this._zoom = Math.max(0.2, this._zoom - 0.1);
        this._applyTransform();
    },

    zoomReset() {
        this._zoom = 1;
        this._panX = 0;
        this._panY = 0;
        this._applyTransform();
    },

    zoomFit() {
        if (this.nodes.length === 0) return;
        const canvas = document.getElementById('builderCanvas');
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        const minX = Math.min(...this.nodes.map(n => n.x));
        const maxX = Math.max(...this.nodes.map(n => n.x + 100));
        const minY = Math.min(...this.nodes.map(n => n.y));
        const maxY = Math.max(...this.nodes.map(n => n.y + 100));
        const w = maxX - minX + 100;
        const h = maxY - minY + 100;
        this._zoom = Math.min(rect.width / w, rect.height / h, 1.5);
        this._zoom = Math.max(0.2, Math.min(3, this._zoom));
        this._panX = (rect.width - w * this._zoom) / 2 - minX * this._zoom + 50 * this._zoom;
        this._panY = (rect.height - h * this._zoom) / 2 - minY * this._zoom + 50 * this._zoom;
        this._applyTransform();
    },

    destroy() {
        this.autoSave();
        if (this._keyHandler) {
            document.removeEventListener('keydown', this._keyHandler);
            this._keyHandler = null;
        }
        if (this._wheelHandler) {
            document.removeEventListener('wheel', this._wheelHandler);
            this._wheelHandler = null;
        }
        document.querySelectorAll('.node-context-menu').forEach(m => m.remove());
    }
};

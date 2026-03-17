/**
 * BotCrypto - Shared UI Components
 */
const Components = {

    /** Create a stat card */
    statCard(value, label, sublabel = '', colorClass = '') {
        return `
        <div class="card">
            <div class="card-body py-3">
                <div class="stat-value ${colorClass}">${value}</div>
                <div class="stat-label">${label}</div>
                ${sublabel ? `<div class="stat-sublabel">${sublabel}</div>` : ''}
            </div>
        </div>`;
    },

    /** Create profit display like botcrypto */
    profitDisplay(unrealized, realized, winRate, avgProfit, currency = 'USDT') {
        return `
        <div class="row g-3 py-3">
            <div class="col-6">
                <div class="stat-value">${this.formatNumber(unrealized)} <small class="fs-6 text-secondary">${currency}</small></div>
                <div class="stat-label">Unrealized profits</div>
                <div class="stat-sublabel">Open orders pending profits</div>
            </div>
            <div class="col-6">
                <div class="stat-value text-profit">+${this.formatNumber(realized)} <small class="fs-6 text-secondary">${currency}</small></div>
                <div class="stat-label">Realized profits</div>
                <div class="stat-sublabel">Closed orders profits</div>
            </div>
            <div class="col-6">
                <div class="stat-value text-profit">${this.formatNumber(winRate)} %</div>
                <div class="stat-label">Win rate</div>
                <div class="stat-sublabel">Closed trades winning ratio</div>
            </div>
            <div class="col-6">
                <div class="stat-value text-profit">+${this.formatNumber(avgProfit)} <small class="fs-6 text-secondary">${currency}</small></div>
                <div class="stat-label">Average profit</div>
                <div class="stat-sublabel">Average profit per trade</div>
            </div>
        </div>`;
    },

    /** Trade table row like botcrypto */
    tradeRow(trade) {
        const gain = trade.profit_abs || 0;
        const gainClass = gain >= 0 ? 'text-profit' : 'text-loss';
        const gainIcon = gain >= 0 ? 'bi-triangle-fill' : 'bi-triangle-fill rotate-180';
        return `
        <tr>
            <td>
                <span class="${gainClass}">
                    <i class="bi ${gainIcon} me-1" style="font-size:8px;${gain < 0 ? 'transform:rotate(180deg);display:inline-block' : ''}"></i>
                    ${gain >= 0 ? '+' : ''}${this.formatNumber(gain)} <small class="text-secondary">${trade.quote_currency || 'USDT'}</small>
                </span>
            </td>
            <td>
                <div class="action-sell">SELL</div>
                <div class="action-buy">BUY</div>
            </td>
            <td>${trade.exit_reason ? 'Market' : trade.order_type || 'Market'}</td>
            <td>
                <div>${this.formatNumber(trade.close_rate || trade.open_rate, 4)} <small class="text-secondary">${trade.quote_currency || 'USDT'}</small></div>
                <div>${this.formatNumber(trade.open_rate, 4)} <small class="text-secondary">${trade.quote_currency || 'USDT'}</small></div>
            </td>
            <td>${this.formatNumber(trade.amount, 1)} <small class="text-secondary">${trade.base_currency || ''}</small></td>
            <td><span class="badge badge-bc badge-completed">Close</span></td>
            <td class="text-secondary small">${this.formatDate(trade.close_date || trade.open_date)}</td>
        </tr>`;
    },

    /** Trades table */
    tradesTable(trades, showTabs = true) {
        const tradeCount = trades.length;
        return `
        ${showTabs ? `
        <div class="d-flex gap-3 mb-3">
            <button class="btn btn-sm btn-outline-light active" onclick="this.classList.add('active')">
                <i class="bi bi-arrow-left-right me-1"></i> Trades <span class="badge bg-success">${tradeCount}</span>
            </button>
        </div>` : ''}
        <div class="table-responsive">
            <table class="table table-hover mb-0">
                <thead>
                    <tr>
                        <th>Gain <i class="bi bi-chevron-expand"></i></th>
                        <th>Action <i class="bi bi-chevron-expand"></i></th>
                        <th>Order Type</th>
                        <th>Price</th>
                        <th>Volume</th>
                        <th>Status</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
                    ${trades.map(t => this.tradeRow(t)).join('')}
                    ${trades.length === 0 ? '<tr><td colspan="7" class="text-center text-secondary py-4">No trades yet</td></tr>' : ''}
                </tbody>
            </table>
        </div>`;
    },

    /** Chart header bar like botcrypto backtest */
    chartHeader(title, strategyName, dateRange, status = 'COMPLETED') {
        const statusClass = status === 'COMPLETED' ? 'badge-completed' :
                           status === 'RUNNING' ? 'badge-running' : 'badge-failed';
        return `
        <div class="d-flex align-items-center gap-3 flex-wrap mb-3">
            <button class="btn btn-link text-secondary p-0" onclick="history.back()">
                <i class="bi bi-chevron-left fs-5"></i>
            </button>
            <h5 class="mb-0 fw-semibold">
                <i class="bi bi-gear-wide-connected me-1"></i> ${title}
            </h5>
            <span class="badge bg-dark border border-secondary rounded-pill px-3">
                <i class="bi bi-diagram-3 me-1"></i> ${strategyName}
            </span>
            <span class="badge badge-bc ${statusClass}">
                <i class="bi bi-check-circle me-1"></i> ${status}
            </span>
            <span class="text-secondary small">${dateRange}</span>
            <div class="ms-auto">
                <button class="btn btn-bc-delete btn-sm">
                    <i class="bi bi-trash me-1"></i> DELETE
                </button>
            </div>
        </div>`;
    },

    /** Timeframe selector buttons */
    timeframeSelector(selected = '30m', onChange = null) {
        const tfs = ['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d'];
        return `
        <div class="btn-group btn-group-sm" role="group">
            ${tfs.map(tf => `
                <button type="button" class="btn ${tf === selected ? 'btn-outline-success active' : 'btn-outline-secondary'}"
                    onclick="${onChange ? onChange + "('" + tf + "')" : ''}">${tf}</button>
            `).join('')}
        </div>`;
    },

    /** Common trading pairs for dropdown */
    commonPairs: [
        'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'SOL/USDT', 'ADA/USDT',
        'DOGE/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT', 'LINK/USDT',
        'UNI/USDT', 'ATOM/USDT', 'LTC/USDT', 'OP/USDT', 'ARB/USDT',
        'GRT/USDT', 'FIL/USDT', 'NEAR/USDT', 'APT/USDT', 'INJ/USDT',
    ],

    /** Chart toolbar like botcrypto - with working pair selector and timeframe buttons */
    chartToolbar(pair = 'BTC/USDT', timeframe = '5m', onPairChange = '', onTimeframeChange = '') {
        const tfs = ['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d'];
        return `
        <div class="d-flex align-items-center justify-content-between border-bottom border-secondary pb-2 mb-2">
            <div class="d-flex align-items-center gap-2">
                <div class="position-relative" style="width:140px">
                    <input type="text" class="form-control form-control-sm fw-semibold" id="chartPairInput"
                        value="${pair}" list="pairList"
                        onchange="${onPairChange || ''}"
                        onfocus="this.select()"
                        style="background:rgba(255,255,255,0.08);border-color:var(--bc-border)">
                    <datalist id="pairList">
                        ${this.commonPairs.map(p => `<option value="${p}">`).join('')}
                    </datalist>
                </div>
                <div class="btn-group btn-group-sm" role="group">
                    ${tfs.map(tf => `
                        <button type="button" class="btn ${tf === timeframe ? 'btn-outline-success active' : 'btn-outline-secondary'}"
                            onclick="${onTimeframeChange ? onTimeframeChange + "('" + tf + "')" : ''}">${tf}</button>
                    `).join('')}
                </div>
                <button class="btn btn-sm btn-link text-secondary"><i class="bi bi-activity me-1"></i> Indicators</button>
            </div>
            <div class="d-flex align-items-center gap-2">
                <button class="btn btn-sm btn-link text-secondary" onclick="${onPairChange || ''}"><i class="bi bi-arrow-clockwise"></i></button>
                <button class="btn btn-sm btn-link text-secondary"><i class="bi bi-arrows-fullscreen"></i></button>
            </div>
        </div>`;
    },

    /** Loading spinner */
    loading(text = 'Loading...') {
        return `
        <div class="d-flex justify-content-center align-items-center py-5">
            <div class="spinner-border text-success me-3" role="status"></div>
            <span class="text-secondary">${text}</span>
        </div>`;
    },

    /** Empty state */
    emptyState(icon, title, desc) {
        return `
        <div class="text-center py-5">
            <i class="bi bi-${icon} display-1 text-secondary opacity-25 mb-3 d-block"></i>
            <h5 class="text-secondary">${title}</h5>
            <p class="text-secondary small">${desc}</p>
        </div>`;
    },

    /** Progress bar */
    progressBar(percent, label = '') {
        return `
        <div class="mb-2">
            ${label ? `<div class="d-flex justify-content-between mb-1"><small class="text-secondary">${label}</small><small class="text-secondary">${percent}%</small></div>` : ''}
            <div class="progress" style="height: 6px;">
                <div class="progress-bar bg-success" style="width: ${percent}%"></div>
            </div>
        </div>`;
    },

    // ========== UTILITIES ==========
    formatNumber(n, decimals = 4) {
        if (n === null || n === undefined) return '0';
        return Number(n).toFixed(decimals);
    },

    formatPercent(n) {
        if (n === null || n === undefined) return '0%';
        return Number(n).toFixed(2) + '%';
    },

    formatDate(dateStr) {
        if (!dateStr) return '-';
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-GB', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    },

    formatCurrency(amount, currency = 'USDT') {
        return `${this.formatNumber(amount)} ${currency}`;
    },

    /** Create a lightweight chart */
    createChart(container, options = {}) {
        if (!window.LightweightCharts) {
            container.innerHTML = '<div class="text-center py-5 text-secondary">Chart library not loaded</div>';
            return null;
        }
        const chart = LightweightCharts.createChart(container, {
            layout: {
                background: { type: 'solid', color: 'transparent' },
                textColor: '#8a8fa8',
                fontFamily: 'Inter, sans-serif',
            },
            grid: {
                vertLines: { color: 'rgba(46, 51, 72, 0.5)' },
                horzLines: { color: 'rgba(46, 51, 72, 0.5)' },
            },
            crosshair: { mode: 0 },
            rightPriceScale: { borderColor: '#2e3348' },
            timeScale: {
                borderColor: '#2e3348',
                timeVisible: true,
            },
            ...options
        });
        return chart;
    },

    /** Generate demo candle data */
    generateDemoCandles(count = 200, startPrice = 0.25) {
        const data = [];
        let price = startPrice;
        const now = Math.floor(Date.now() / 1000);
        for (let i = count; i >= 0; i--) {
            const time = now - i * 1800; // 30min candles
            const open = price;
            const change = (Math.random() - 0.48) * price * 0.02;
            const close = price + change;
            const high = Math.max(open, close) + Math.random() * price * 0.01;
            const low = Math.min(open, close) - Math.random() * price * 0.01;
            data.push({ time, open, high, low, close });
            price = close;
        }
        return data;
    },

    /** Generate demo equity curve */
    generateDemoEquity(count = 100, startBalance = 30000) {
        const data = [];
        let balance = startBalance;
        const now = Math.floor(Date.now() / 1000);
        for (let i = count; i >= 0; i--) {
            const time = now - i * 86400;
            balance += (Math.random() - 0.35) * balance * 0.01;
            data.push({ time, value: balance });
        }
        return data;
    },

    /** Generate demo trades */
    generateDemoTrades(count = 20) {
        const pairs = ['XRP/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'ADA/USDT'];
        const trades = [];
        for (let i = 0; i < count; i++) {
            const pair = pairs[Math.floor(Math.random() * pairs.length)];
            const buyPrice = 0.2 + Math.random() * 0.15;
            const sellPrice = buyPrice * (0.95 + Math.random() * 0.12);
            const amount = 50000 + Math.random() * 100000;
            trades.push({
                trade_id: i + 1,
                pair: pair,
                base_currency: pair.split('/')[0],
                quote_currency: pair.split('/')[1],
                open_rate: buyPrice,
                close_rate: sellPrice,
                amount: amount,
                profit_abs: (sellPrice - buyPrice) * amount,
                profit_ratio: (sellPrice - buyPrice) / buyPrice,
                open_date: new Date(Date.now() - (count - i) * 86400000).toISOString(),
                close_date: new Date(Date.now() - (count - i - 1) * 86400000).toISOString(),
                exit_reason: 'roi',
                order_type: 'Market',
                is_open: false
            });
        }
        return trades.sort((a, b) => (b.profit_abs || 0) - (a.profit_abs || 0));
    }
};

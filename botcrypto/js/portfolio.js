/**
 * BotCrypto - Portfolio Page
 * Asset allocation, wallet balance across exchanges, performance monitoring
 * Similar to botcrypto.io's "Portefeuilles" view
 */
const PortfolioPage = {
    refreshTimer: null,

    render() {
        return `
        <div id="portfolioPage">
            <div class="d-flex align-items-center justify-content-between mb-4">
                <h4 class="fw-semibold mb-0"><i class="bi bi-wallet2 me-2"></i>Portfolio</h4>
                <button class="btn btn-outline-secondary btn-sm" onclick="PortfolioPage.refresh()">
                    <i class="bi bi-arrow-clockwise me-1"></i> Refresh
                </button>
            </div>

            <!-- Total Balance Card -->
            <div class="card mb-3">
                <div class="card-body">
                    <div class="row align-items-center g-3">
                        <div class="col-12 col-md-4">
                            <div class="text-secondary small mb-1">Total Portfolio Value</div>
                            <div class="fs-2 fw-bold" id="portfolioTotal">-</div>
                            <div id="portfolioChange" class="small"></div>
                        </div>
                        <div class="col-6 col-md-4">
                            <div class="text-secondary small mb-1">Available Balance</div>
                            <div class="fs-4 fw-semibold" id="portfolioFree">-</div>
                        </div>
                        <div class="col-6 col-md-4">
                            <div class="text-secondary small mb-1">In Trades</div>
                            <div class="fs-4 fw-semibold" id="portfolioUsed">-</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Asset Allocation + Performance -->
            <div class="row g-3 mb-3">
                <!-- Asset Allocation Chart -->
                <div class="col-lg-5">
                    <div class="card h-100">
                        <div class="card-body">
                            <h6 class="fw-semibold mb-3"><i class="bi bi-pie-chart me-2 text-primary"></i>Asset Allocation</h6>
                            <div id="assetAllocation">
                                <div class="text-center text-secondary py-4">
                                    <small>Connect to Freqtrade to see assets</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Performance Summary -->
                <div class="col-lg-7">
                    <div class="card h-100">
                        <div class="card-body">
                            <h6 class="fw-semibold mb-3"><i class="bi bi-graph-up me-2 text-success"></i>Trading Performance</h6>
                            <div id="portfolioPerformance">
                                <div class="text-center text-secondary py-4">
                                    <small>Connect to Freqtrade to see performance</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Recent Orders -->
            <div class="card mb-3">
                <div class="card-header">
                    <h6 class="mb-0"><i class="bi bi-clock-history me-2"></i>Recent Orders</h6>
                </div>
                <div class="card-body" id="recentOrders">
                    <div class="text-center text-secondary py-3">
                        <small>Connect to Freqtrade to see recent orders</small>
                    </div>
                </div>
            </div>

            <!-- Daily/Weekly/Monthly Profit -->
            <div class="row g-3">
                <div class="col-lg-4">
                    <div class="card h-100">
                        <div class="card-header"><h6 class="mb-0">Daily Profit</h6></div>
                        <div class="card-body" id="dailyProfit">
                            <div class="text-center text-secondary py-3"><small>Loading...</small></div>
                        </div>
                    </div>
                </div>
                <div class="col-lg-4">
                    <div class="card h-100">
                        <div class="card-header"><h6 class="mb-0">Weekly Profit</h6></div>
                        <div class="card-body" id="weeklyProfit">
                            <div class="text-center text-secondary py-3"><small>Loading...</small></div>
                        </div>
                    </div>
                </div>
                <div class="col-lg-4">
                    <div class="card h-100">
                        <div class="card-header"><h6 class="mb-0">Monthly Profit</h6></div>
                        <div class="card-body" id="monthlyProfit">
                            <div class="text-center text-secondary py-3"><small>Loading...</small></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
    },

    async init() {
        await this.loadData();
        this.refreshTimer = setInterval(() => this.loadData(), 30000);
    },

    async loadData() {
        if (!API.connected) return;

        try {
            const [balance, profit, trades, daily, weekly, monthly, performance] = await Promise.all([
                API.getBalance().catch(() => null),
                API.getProfit().catch(() => null),
                API.getTrades(20).catch(() => ({ trades: [] })),
                API.getDaily(14).catch(() => null),
                API.getWeekly(8).catch(() => null),
                API.getMonthly(6).catch(() => null),
                API.getPerformance().catch(() => null),
            ]);

            this.renderBalance(balance, profit);
            this.renderAssetAllocation(balance);
            this.renderPerformance(profit, performance);
            this.renderRecentOrders(trades);
            this.renderDaily(daily);
            this.renderWeekly(weekly);
            this.renderMonthly(monthly);
        } catch (e) {
            console.log('Portfolio load error:', e.message);
        }
    },

    renderBalance(balance, profit) {
        const currency = profit?.stake_currency || balance?.stake || 'USDT';
        const total = balance?.total || 0;
        const free = balance?.free || 0;
        const used = balance?.used || 0;

        const totalEl = document.getElementById('portfolioTotal');
        const freeEl = document.getElementById('portfolioFree');
        const usedEl = document.getElementById('portfolioUsed');
        const changeEl = document.getElementById('portfolioChange');

        if (totalEl) totalEl.textContent = `${Components.formatNumber(total, 2)} ${currency}`;
        if (freeEl) freeEl.textContent = `${Components.formatNumber(free, 2)} ${currency}`;
        if (usedEl) usedEl.textContent = `${Components.formatNumber(used, 2)} ${currency}`;

        if (changeEl && profit) {
            const pnl = profit.profit_all_coin || 0;
            const pnlPct = profit.profit_all_percent || ((profit.profit_all_ratio_sum || 0) * 100);
            changeEl.innerHTML = `<span class="${pnl >= 0 ? 'text-profit' : 'text-loss'} fw-semibold">
                ${pnl >= 0 ? '+' : ''}${Components.formatNumber(pnl, 2)} ${currency}
                (${pnlPct >= 0 ? '+' : ''}${Components.formatNumber(pnlPct, 2)}%)
            </span> all-time P&L`;
        }
    },

    renderAssetAllocation(balance) {
        const el = document.getElementById('assetAllocation');
        if (!el) return;

        if (!balance || !balance.currencies) {
            // Try to show basic info
            if (balance) {
                const currency = balance.stake || balance.symbol || 'USDT';
                el.innerHTML = `
                <div class="d-flex align-items-center justify-content-between py-2">
                    <div class="d-flex align-items-center gap-2">
                        <div class="rounded-circle bg-success d-flex align-items-center justify-content-center" style="width:32px;height:32px">
                            <small class="fw-bold text-white">${currency.substring(0, 2)}</small>
                        </div>
                        <div>
                            <div class="fw-semibold">${currency}</div>
                            <small class="text-secondary">Stake Currency</small>
                        </div>
                    </div>
                    <div class="text-end">
                        <div class="fw-semibold">${Components.formatNumber(balance.total || 0, 2)}</div>
                        <small class="text-secondary">100%</small>
                    </div>
                </div>`;
            }
            return;
        }

        const colors = ['#2dd4a8', '#4a90d9', '#f0ad4e', '#e74c5e', '#9b59b6', '#1abc9c', '#e67e22', '#3498db'];
        const currencies = balance.currencies.filter(c => (c.balance || 0) > 0).sort((a, b) => (b.est_stake || 0) - (a.est_stake || 0));
        const totalStake = currencies.reduce((sum, c) => sum + (c.est_stake || 0), 0);

        if (currencies.length === 0) {
            el.innerHTML = `<div class="text-center text-secondary py-3"><small>No assets found</small></div>`;
            return;
        }

        // Simple bar chart
        el.innerHTML = `
            <div class="d-flex gap-1 mb-3 rounded overflow-hidden" style="height:24px">
                ${currencies.slice(0, 8).map((c, i) => {
                    const pct = totalStake > 0 ? (c.est_stake / totalStake * 100) : 0;
                    return pct > 1 ? `<div style="width:${pct}%;background:${colors[i % colors.length]}" title="${c.currency}: ${pct.toFixed(1)}%"></div>` : '';
                }).join('')}
            </div>
            ${currencies.slice(0, 10).map((c, i) => `
            <div class="d-flex align-items-center justify-content-between py-2 ${i > 0 ? 'border-top border-secondary' : ''}">
                <div class="d-flex align-items-center gap-2">
                    <div class="rounded-circle d-flex align-items-center justify-content-center" style="width:28px;height:28px;background:${colors[i % colors.length]}">
                        <small class="fw-bold text-white" style="font-size:10px">${(c.currency || '?').substring(0, 3)}</small>
                    </div>
                    <div>
                        <div class="fw-semibold small">${c.currency}</div>
                    </div>
                </div>
                <div class="text-end">
                    <div class="fw-semibold small">${Components.formatNumber(c.balance, 4)}</div>
                    <small class="text-secondary">${totalStake > 0 ? Components.formatNumber(c.est_stake / totalStake * 100, 1) : 0}%</small>
                </div>
            </div>`).join('')}`;
    },

    renderPerformance(profit, performance) {
        const el = document.getElementById('portfolioPerformance');
        if (!el) return;

        let html = '';

        if (profit) {
            const currency = profit.stake_currency || 'USDT';
            html += `
            <div class="row g-3 mb-3">
                <div class="col-4">
                    <div class="text-secondary small mb-1">Winning Trades</div>
                    <div class="fw-semibold text-profit">${profit.winning_trades || 0}</div>
                </div>
                <div class="col-4">
                    <div class="text-secondary small mb-1">Losing Trades</div>
                    <div class="fw-semibold text-loss">${profit.losing_trades || 0}</div>
                </div>
                <div class="col-4">
                    <div class="text-secondary small mb-1">Avg Duration</div>
                    <div class="fw-semibold">${profit.avg_duration || '-'}</div>
                </div>
            </div>
            <div class="row g-3 mb-3">
                <div class="col-4">
                    <div class="text-secondary small mb-1">Best Trade</div>
                    <div class="fw-semibold text-profit">${profit.best_pair || '-'}</div>
                </div>
                <div class="col-4">
                    <div class="text-secondary small mb-1">Worst Trade</div>
                    <div class="fw-semibold text-loss">${profit.worst_pair || '-'}</div>
                </div>
                <div class="col-4">
                    <div class="text-secondary small mb-1">Closed Profit</div>
                    <div class="fw-semibold ${(profit.profit_closed_coin || 0) >= 0 ? 'text-profit' : 'text-loss'}">
                        ${Components.formatNumber(profit.profit_closed_coin || 0, 2)} ${currency}
                    </div>
                </div>
            </div>`;
        }

        if (performance && performance.length > 0) {
            html += `<h6 class="fw-semibold mt-3 mb-2">Top Pairs</h6>`;
            html += performance.slice(0, 5).map((p, i) => `
            <div class="d-flex align-items-center justify-content-between py-1 ${i > 0 ? 'border-top border-secondary' : ''}">
                <span class="fw-semibold small">${p.pair}</span>
                <span class="${p.profit >= 0 ? 'text-profit' : 'text-loss'} fw-semibold small">
                    ${p.profit >= 0 ? '+' : ''}${Components.formatNumber(p.profit, 2)}%
                    <small class="text-secondary ms-1">(${p.count} trades)</small>
                </span>
            </div>`).join('');
        }

        el.innerHTML = html || `<div class="text-center text-secondary py-3"><small>No performance data yet</small></div>`;
    },

    renderRecentOrders(trades) {
        const el = document.getElementById('recentOrders');
        if (!el) return;

        const tradeList = trades?.trades || [];
        if (tradeList.length === 0) {
            el.innerHTML = `<div class="text-center text-secondary py-3"><small>No recent orders</small></div>`;
            return;
        }

        el.innerHTML = `
        <div class="table-responsive">
            <table class="table table-hover table-sm mb-0">
                <thead><tr>
                    <th>Pair</th><th>Action</th><th>Profit</th><th>Open</th><th>Close</th><th>Duration</th><th>Status</th>
                </tr></thead>
                <tbody>
                    ${tradeList.slice(0, 15).map(t => {
                        const pnl = (t.profit_ratio || 0) * 100;
                        const isWin = pnl >= 0;
                        return `<tr>
                            <td class="fw-semibold">${Components.cleanPairName ? Components.cleanPairName(t.pair) : t.pair}</td>
                            <td><span class="badge ${t.is_short ? 'bg-danger' : 'bg-success'} bg-opacity-75">${t.is_short ? 'Short' : 'Long'}</span></td>
                            <td class="${isWin ? 'text-profit' : 'text-loss'} fw-semibold">${isWin ? '+' : ''}${Components.formatNumber(pnl, 2)}%</td>
                            <td class="small">${t.open_date ? new Date(t.open_date).toLocaleDateString() : '-'}</td>
                            <td class="small">${t.close_date ? new Date(t.close_date).toLocaleDateString() : '-'}</td>
                            <td class="small">${t.trade_duration || '-'} min</td>
                            <td><span class="badge ${t.is_open ? 'bg-primary' : isWin ? 'bg-success' : 'bg-danger'} bg-opacity-25 ${t.is_open ? 'text-primary' : isWin ? 'text-success' : 'text-danger'}">${t.is_open ? 'Open' : 'Completed'}</span></td>
                        </tr>`;
                    }).join('')}
                </tbody>
            </table>
        </div>`;
    },

    _renderProfitTable(data, type) {
        if (!data || !data.data || data.data.length === 0) return `<div class="text-center text-secondary py-2"><small>No data</small></div>`;

        const currency = data.stake_currency || 'USDT';
        return `<div class="table-responsive" style="max-height:250px;overflow:auto">
            <table class="table table-sm mb-0">
                <thead><tr><th>Period</th><th>Profit</th><th>Trades</th></tr></thead>
                <tbody>
                    ${data.data.slice(0, 14).map(d => {
                        const profit = d.abs_profit || 0;
                        return `<tr>
                            <td class="small">${d.date || '-'}</td>
                            <td class="${profit >= 0 ? 'text-profit' : 'text-loss'} fw-semibold small">${profit >= 0 ? '+' : ''}${Components.formatNumber(profit, 2)} ${currency}</td>
                            <td class="small">${d.trade_count || 0}</td>
                        </tr>`;
                    }).join('')}
                </tbody>
            </table>
        </div>`;
    },

    renderDaily(data) {
        const el = document.getElementById('dailyProfit');
        if (el) el.innerHTML = this._renderProfitTable(data, 'daily');
    },

    renderWeekly(data) {
        const el = document.getElementById('weeklyProfit');
        if (el) el.innerHTML = this._renderProfitTable(data, 'weekly');
    },

    renderMonthly(data) {
        const el = document.getElementById('monthlyProfit');
        if (el) el.innerHTML = this._renderProfitTable(data, 'monthly');
    },

    refresh() {
        const container = document.getElementById('pageContainer');
        if (container) {
            container.innerHTML = this.render();
            this.loadData();
        }
    },

    destroy() {
        if (this.refreshTimer) { clearInterval(this.refreshTimer); this.refreshTimer = null; }
    }
};

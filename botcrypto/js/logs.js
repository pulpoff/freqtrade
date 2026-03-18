const LogsPage = {
    pollTimer: null,
    autoScroll: true,
    logLimit: 200,

    render() {
        return `
        <div class="container-fluid py-3">
            <div class="d-flex align-items-center justify-content-between mb-3">
                <h6 class="fw-semibold mb-0"><i class="bi bi-terminal me-2 text-success"></i>Live Log</h6>
                <div class="d-flex align-items-center gap-2">
                    <div class="form-check form-switch mb-0">
                        <input class="form-check-input" type="checkbox" id="logAutoScroll" checked onchange="LogsPage.autoScroll = this.checked">
                        <label class="form-check-label small text-secondary" for="logAutoScroll">Auto-scroll</label>
                    </div>
                    <select class="form-select form-select-sm" id="logLevelFilter" style="width:auto;background:var(--bc-bg);border-color:var(--bc-border);color:var(--bc-text)" onchange="LogsPage.refresh()">
                        <option value="">All Levels</option>
                        <option value="ERROR">Error</option>
                        <option value="WARNING">Warning</option>
                        <option value="INFO">Info</option>
                        <option value="DEBUG">Debug</option>
                    </select>
                    <select class="form-select form-select-sm" id="logLimitSelect" style="width:auto;background:var(--bc-bg);border-color:var(--bc-border);color:var(--bc-text)" onchange="LogsPage.logLimit = parseInt(this.value); LogsPage.refresh()">
                        <option value="100">100 lines</option>
                        <option value="200" selected>200 lines</option>
                        <option value="500">500 lines</option>
                        <option value="1000">1000 lines</option>
                    </select>
                    <button class="btn btn-outline-secondary btn-sm" onclick="LogsPage.refresh()">
                        <i class="bi bi-arrow-clockwise"></i>
                    </button>
                    <button class="btn btn-outline-secondary btn-sm" onclick="LogsPage.clearDisplay()">
                        <i class="bi bi-trash me-1"></i>Clear
                    </button>
                </div>
            </div>
            <div id="logContainer" class="rounded" style="background:#0d1117;border:1px solid var(--bc-border);height:calc(100vh - 160px);overflow-y:auto;font-family:'JetBrains Mono',Consolas,monospace;font-size:12px;padding:12px;line-height:1.6">
                <div class="text-secondary text-center py-5">Loading logs...</div>
            </div>
        </div>`;
    },

    init() {
        this.refresh();
        this.pollTimer = setInterval(() => this.refresh(), 3000);
    },

    destroy() {
        if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
    },

    async refresh() {
        if (!API.connected) {
            const c = document.getElementById('logContainer');
            if (c) c.innerHTML = '<div class="text-secondary text-center py-5">Connect to Freqtrade to view logs</div>';
            return;
        }

        try {
            const data = await API.getLogs(this.logLimit);
            const logs = data?.logs || [];
            const container = document.getElementById('logContainer');
            if (!container) return;

            const levelFilter = document.getElementById('logLevelFilter')?.value || '';

            const filtered = levelFilter
                ? logs.filter(l => (l[2] || '').toUpperCase() === levelFilter)
                : logs;

            if (filtered.length === 0) {
                container.innerHTML = '<div class="text-secondary text-center py-5">No log entries</div>';
                return;
            }

            container.innerHTML = filtered.map(l => {
                const timestamp = l[0] || '';
                const logger = l[1] || '';
                const level = (l[2] || '').toUpperCase();
                const message = l[3] || (typeof l === 'string' ? l : JSON.stringify(l));

                const levelColor = {
                    'ERROR': '#e74c5e',
                    'WARNING': '#f0ad4e',
                    'INFO': '#2dd4a8',
                    'DEBUG': '#6c757d',
                }[level] || '#adb5bd';

                const levelBadge = `<span style="color:${levelColor};font-weight:600;min-width:55px;display:inline-block">${level}</span>`;
                const ts = timestamp ? `<span style="color:#6c757d">${timestamp}</span> ` : '';
                const log = logger ? `<span style="color:#58a6ff">${logger}</span> ` : '';

                return `<div style="white-space:pre-wrap;word-break:break-all;border-bottom:1px solid #1b2130;padding:2px 0">${ts}${levelBadge} ${log}<span style="color:#c9d1d9">${this._escapeHtml(message)}</span></div>`;
            }).join('');

            if (this.autoScroll) {
                container.scrollTop = container.scrollHeight;
            }
        } catch (e) {
            console.log('Log fetch error:', e.message);
        }
    },

    clearDisplay() {
        const c = document.getElementById('logContainer');
        if (c) c.innerHTML = '<div class="text-secondary text-center py-5">Log cleared</div>';
    },

    _escapeHtml(str) {
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
};

/**
 * BotCrypto - Webhooks Management Page
 * Generate and manage incoming webhook URLs for TradingView integration
 */
const WebhooksPage = {
    webhooks: [],

    render() {
        return `
        <div id="webhooksPage">
            <div class="d-flex align-items-center justify-content-between mb-4">
                <h4 class="fw-semibold mb-0"><i class="bi bi-link-45deg me-2"></i>Webhooks</h4>
                <button class="btn btn-success" onclick="WebhooksPage.createWebhook()">
                    <i class="bi bi-plus-lg me-1"></i> New Incoming Webhook
                </button>
            </div>

            <!-- How it works -->
            <div class="card mb-4">
                <div class="card-body">
                    <h6 class="fw-semibold mb-3"><i class="bi bi-info-circle me-2 text-info"></i>How Webhooks Work</h6>
                    <div class="row g-4">
                        <div class="col-md-4">
                            <div class="d-flex gap-3">
                                <div class="rounded-circle bg-success bg-opacity-10 d-flex align-items-center justify-content-center flex-shrink-0" style="width:40px;height:40px">
                                    <span class="fw-bold text-success">1</span>
                                </div>
                                <div>
                                    <h6 class="fw-semibold mb-1">Create a Webhook</h6>
                                    <p class="text-secondary small mb-0">Generate a unique URL endpoint that listens for incoming signals.</p>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="d-flex gap-3">
                                <div class="rounded-circle bg-primary bg-opacity-10 d-flex align-items-center justify-content-center flex-shrink-0" style="width:40px;height:40px">
                                    <span class="fw-bold text-primary">2</span>
                                </div>
                                <div>
                                    <h6 class="fw-semibold mb-1">Connect to TradingView</h6>
                                    <p class="text-secondary small mb-0">Paste the URL into a TradingView alert's "Webhook URL" field.</p>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="d-flex gap-3">
                                <div class="rounded-circle bg-warning bg-opacity-10 d-flex align-items-center justify-content-center flex-shrink-0" style="width:40px;height:40px">
                                    <span class="fw-bold text-warning">3</span>
                                </div>
                                <div>
                                    <h6 class="fw-semibold mb-1">Use in Strategy</h6>
                                    <p class="text-secondary small mb-0">Add a Webhook block in the strategy builder and link it to this endpoint.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Webhooks List -->
            <div class="card">
                <div class="card-header">
                    <h6 class="mb-0"><i class="bi bi-inbox me-2"></i>Incoming Webhooks</h6>
                </div>
                <div class="card-body" id="webhooksList">
                    ${this.renderWebhooksList()}
                </div>
            </div>

            <!-- Webhook Payload Format -->
            <div class="card mt-3">
                <div class="card-header">
                    <h6 class="mb-0"><i class="bi bi-code-slash me-2"></i>Payload Format</h6>
                </div>
                <div class="card-body">
                    <p class="text-secondary small">Send a JSON payload to your webhook URL with the following structure:</p>
                    <pre class="bg-dark border border-secondary rounded p-3 text-light"><code>{
  "action": "buy",        // "buy" or "sell"
  "pair": "BTC/USDT",     // Trading pair
  "price": 84500,         // Optional: limit price
  "volume": 100,          // Optional: volume percentage (default 100%)
  "side": "long",         // Optional: "long" or "short"
  "strategy": "my_strat"  // Optional: strategy name
}</code></pre>
                    <p class="text-secondary small mt-2">
                        <strong>TradingView Alert Message Example:</strong>
                    </p>
                    <pre class="bg-dark border border-secondary rounded p-3 text-light"><code>{"action": "{{strategy.order.action}}", "pair": "{{ticker}}", "price": {{close}}}</code></pre>
                </div>
            </div>
        </div>`;
    },

    init() {
        this.loadWebhooks();
    },

    loadWebhooks() {
        this.webhooks = JSON.parse(localStorage.getItem('bc_webhooks') || '[]');
        const list = document.getElementById('webhooksList');
        if (list) list.innerHTML = this.renderWebhooksList();
    },

    renderWebhooksList() {
        const webhooks = JSON.parse(localStorage.getItem('bc_webhooks') || '[]');
        if (webhooks.length === 0) {
            return `<div class="text-center text-secondary py-4">
                <i class="bi bi-inbox fs-1 d-block mb-2"></i>
                <p>No webhooks created yet</p>
                <button class="btn btn-outline-success btn-sm" onclick="WebhooksPage.createWebhook()">
                    <i class="bi bi-plus-lg me-1"></i> Create Your First Webhook
                </button>
            </div>`;
        }
        return webhooks.map((wh, i) => `
        <div class="d-flex align-items-center justify-content-between py-3 ${i > 0 ? 'border-top border-secondary' : ''}">
            <div class="flex-grow-1">
                <div class="d-flex align-items-center gap-2 mb-1">
                    <h6 class="fw-semibold mb-0">${wh.name}</h6>
                    <span class="badge ${wh.active ? 'bg-success' : 'bg-secondary'}">${wh.active ? 'Active' : 'Inactive'}</span>
                    <small class="text-secondary">Created: ${Components.formatDate(wh.createdAt)}</small>
                </div>
                <div class="input-group input-group-sm" style="max-width:600px">
                    <span class="input-group-text bg-dark border-secondary text-secondary"><i class="bi bi-link-45deg"></i></span>
                    <input type="text" class="form-control form-control-sm font-monospace bg-dark text-light border-secondary"
                        value="${wh.url}" readonly id="webhookUrl-${i}">
                    <button class="btn btn-outline-success btn-sm" onclick="WebhooksPage.copyUrl(${i})" title="Copy URL">
                        <i class="bi bi-clipboard"></i>
                    </button>
                </div>
                ${wh.lastSignal ? `<small class="text-secondary mt-1 d-block">Last signal: ${Components.formatDate(wh.lastSignal)}</small>` : ''}
            </div>
            <div class="d-flex gap-2 ms-3">
                <button class="btn btn-outline-secondary btn-sm" onclick="WebhooksPage.toggleWebhook(${i})">
                    <i class="bi bi-${wh.active ? 'pause' : 'play'}-fill"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" onclick="WebhooksPage.deleteWebhook(${i})">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>`).join('');
    },

    createWebhook() {
        const id = crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).substr(2);
        const baseUrl = API.baseUrl || window.location.origin;
        const webhook = {
            id,
            name: `Webhook ${(JSON.parse(localStorage.getItem('bc_webhooks') || '[]')).length + 1}`,
            url: `${baseUrl}/api/v1/webhook/${id}`,
            active: true,
            createdAt: new Date().toISOString(),
            lastSignal: null,
        };

        const webhooks = JSON.parse(localStorage.getItem('bc_webhooks') || '[]');
        webhooks.push(webhook);
        localStorage.setItem('bc_webhooks', JSON.stringify(webhooks));

        this.loadWebhooks();
        App.showToast('Webhook created! Copy the URL to your TradingView alert.', 'success');
    },

    copyUrl(index) {
        const input = document.getElementById(`webhookUrl-${index}`);
        if (input) {
            navigator.clipboard.writeText(input.value).then(() => {
                App.showToast('Webhook URL copied to clipboard', 'success');
            }).catch(() => {
                input.select();
                document.execCommand('copy');
                App.showToast('Webhook URL copied', 'success');
            });
        }
    },

    toggleWebhook(index) {
        const webhooks = JSON.parse(localStorage.getItem('bc_webhooks') || '[]');
        if (webhooks[index]) {
            webhooks[index].active = !webhooks[index].active;
            localStorage.setItem('bc_webhooks', JSON.stringify(webhooks));
            this.loadWebhooks();
        }
    },

    async deleteWebhook(index) {
        if (!await App.confirm('Delete this webhook?', { title: 'Delete Webhook', confirmText: 'Delete' })) return;
        const webhooks = JSON.parse(localStorage.getItem('bc_webhooks') || '[]');
        webhooks.splice(index, 1);
        localStorage.setItem('bc_webhooks', JSON.stringify(webhooks));
        this.loadWebhooks();
        App.showToast('Webhook deleted', 'info');
    },

    destroy() {}
};

/**
 * BotCrypto - Config Database Manager
 * Uses IndexedDB to store and manage strategy configurations
 * Allows loading, modifying, and applying configs via web GUI
 */
const ConfigDB = {
    dbName: 'botcrypto_configs',
    dbVersion: 1,
    db: null,

    /** Initialize IndexedDB */
    async init() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                resolve();
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // Strategy configs store
                if (!db.objectStoreNames.contains('configs')) {
                    const configStore = db.createObjectStore('configs', { keyPath: 'id', autoIncrement: true });
                    configStore.createIndex('name', 'name', { unique: false });
                    configStore.createIndex('strategy', 'strategy', { unique: false });
                    configStore.createIndex('createdAt', 'createdAt', { unique: false });
                    configStore.createIndex('isActive', 'isActive', { unique: false });
                }

                // Strategy Python files store
                if (!db.objectStoreNames.contains('strategy_files')) {
                    const stratStore = db.createObjectStore('strategy_files', { keyPath: 'id', autoIncrement: true });
                    stratStore.createIndex('name', 'name', { unique: true });
                    stratStore.createIndex('createdAt', 'createdAt', { unique: false });
                }

                // Bot run history
                if (!db.objectStoreNames.contains('run_history')) {
                    const runStore = db.createObjectStore('run_history', { keyPath: 'id', autoIncrement: true });
                    runStore.createIndex('configId', 'configId', { unique: false });
                    runStore.createIndex('startedAt', 'startedAt', { unique: false });
                }
            };
        });
    },

    // ========== CONFIG CRUD ==========

    /** Save a new config */
    async saveConfig(config) {
        const data = {
            ...config,
            createdAt: config.createdAt || new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            isActive: config.isActive || false,
        };
        return this._put('configs', data);
    },

    /** Get all configs */
    async getAllConfigs() {
        return this._getAll('configs');
    },

    /** Get config by ID */
    async getConfig(id) {
        return this._get('configs', id);
    },

    /** Delete config */
    async deleteConfig(id) {
        return this._delete('configs', id);
    },

    /** Set a config as active (deactivate others) */
    async setActiveConfig(id) {
        const configs = await this.getAllConfigs();
        const tx = this.db.transaction('configs', 'readwrite');
        const store = tx.objectStore('configs');

        for (const config of configs) {
            config.isActive = (config.id === id);
            store.put(config);
        }

        return new Promise((resolve, reject) => {
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
    },

    /** Get the active config */
    async getActiveConfig() {
        const configs = await this.getAllConfigs();
        return configs.find(c => c.isActive) || null;
    },

    /** Duplicate a config */
    async duplicateConfig(id) {
        const original = await this.getConfig(id);
        if (!original) return null;
        const copy = { ...original };
        delete copy.id;
        copy.name = `${original.name} (Copy)`;
        copy.isActive = false;
        copy.createdAt = new Date().toISOString();
        return this.saveConfig(copy);
    },

    // ========== STRATEGY FILES ==========

    /** Save a strategy Python file */
    async saveStrategyFile(name, content, metadata = {}) {
        const data = {
            name,
            content,
            ...metadata,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
        };

        // Check if exists by name
        const existing = await this._getByIndex('strategy_files', 'name', name);
        if (existing) {
            data.id = existing.id;
            data.createdAt = existing.createdAt;
        }

        return this._put('strategy_files', data);
    },

    /** Get all strategy files */
    async getAllStrategyFiles() {
        return this._getAll('strategy_files');
    },

    /** Get strategy file by name */
    async getStrategyFile(name) {
        return this._getByIndex('strategy_files', 'name', name);
    },

    /** Delete strategy file */
    async deleteStrategyFile(id) {
        return this._delete('strategy_files', id);
    },

    // ========== RUN HISTORY ==========

    /** Log a bot run */
    async logRun(configId, data = {}) {
        return this._put('run_history', {
            configId,
            ...data,
            startedAt: new Date().toISOString(),
        });
    },

    /** Get run history for a config */
    async getRunHistory(configId) {
        const all = await this._getAll('run_history');
        return all.filter(r => r.configId === configId).sort((a, b) =>
            new Date(b.startedAt) - new Date(a.startedAt)
        );
    },

    // ========== APPLY CONFIG TO FREQTRADE ==========

    /**
     * Apply a config to Freqtrade:
     * 1. Build the config JSON
     * 2. If connected, reload via API
     * 3. Log the run
     */
    async applyConfig(configId) {
        const config = await this.getConfig(configId);
        if (!config) throw new Error('Config not found');

        // Set as active
        await this.setActiveConfig(configId);

        // Build Freqtrade config JSON
        const ftConfig = this.buildFreqtradeConfig(config);

        if (API.connected) {
            try {
                // Attempt to reload config
                await API.reloadConfig();
                await this.logRun(configId, { status: 'applied', config: ftConfig });
                return { success: true, message: 'Config applied and bot reloaded' };
            } catch (e) {
                await this.logRun(configId, { status: 'error', error: e.message });
                return { success: false, message: `Config saved but reload failed: ${e.message}` };
            }
        } else {
            await this.logRun(configId, { status: 'saved', config: ftConfig });
            return { success: false, message: 'Config saved locally. Connect to Freqtrade to apply.' };
        }
    },

    /** Restart the bot with a specific config */
    async restartWithConfig(configId) {
        const config = await this.getConfig(configId);
        if (!config) throw new Error('Config not found');

        await this.setActiveConfig(configId);

        if (!API.connected) {
            return { success: false, message: 'Not connected to Freqtrade' };
        }

        try {
            // Stop bot
            await API.stopBot().catch(() => {});

            // Wait briefly
            await new Promise(r => setTimeout(r, 1000));

            // Reload config
            await API.reloadConfig();

            // Start bot
            await API.startBot();

            await this.logRun(configId, { status: 'restarted' });
            return { success: true, message: 'Bot restarted with new config' };
        } catch (e) {
            await this.logRun(configId, { status: 'restart_error', error: e.message });
            return { success: false, message: `Restart failed: ${e.message}` };
        }
    },

    /** Build a Freqtrade-compatible config.json from stored config */
    buildFreqtradeConfig(config) {
        return {
            max_open_trades: config.maxOpenTrades || 3,
            stake_currency: config.stakeCurrency || 'USDT',
            stake_amount: config.stakeAmount === 'unlimited' ? 'unlimited' : parseFloat(config.stakeAmount) || 'unlimited',
            dry_run: config.dryRun !== false,
            dry_run_wallet: config.dryRunWallet || 1000,
            trading_mode: config.tradingMode || 'spot',
            margin_mode: config.tradingMode === 'futures' ? 'isolated' : '',
            timeframe: config.timeframe || '5m',
            stoploss: config.stoploss || -0.10,
            trailing_stop: config.trailingStop || false,
            ...(config.trailingStop ? {
                trailing_stop_positive: config.trailingStopPositive || 0.01,
                trailing_stop_positive_offset: config.trailingStopPositiveOffset || 0.02,
                trailing_only_offset_is_reached: true,
            } : {}),
            minimal_roi: config.minimalRoi || { '0': 0.04, '20': 0.02, '40': 0.01, '60': 0 },
            exchange: {
                name: config.exchange || 'binance',
                key: config.apiKey || '',
                secret: config.apiSecret || '',
                pair_whitelist: config.pairWhitelist || [],
                pair_blacklist: config.pairBlacklist || [],
            },
            pairlists: config.pairlists || [{ method: 'StaticPairList' }],
            api_server: {
                enabled: true,
                listen_ip_address: config.apiHost || '0.0.0.0',
                listen_port: config.apiPort || 8080,
                username: config.apiUsername || 'freqtrader',
                password: config.apiPassword || '',
                CORS_origins: config.corsOrigins || [],
            },
            ...(config.strategy ? { strategy: config.strategy } : {}),
        };
    },

    /** Export config as downloadable JSON file */
    async exportConfigFile(configId) {
        const config = await this.getConfig(configId);
        if (!config) return;

        const ftConfig = this.buildFreqtradeConfig(config);
        const blob = new Blob([JSON.stringify(ftConfig, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `config_${config.name.replace(/[^a-zA-Z0-9]/g, '_')}.json`;
        a.click();
        URL.revokeObjectURL(url);
    },

    /** Import config from JSON file */
    async importConfigFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = async (e) => {
                try {
                    const json = JSON.parse(e.target.result);
                    const config = this._parseFreqtradeConfig(json, file.name);
                    const id = await this.saveConfig(config);
                    resolve(id);
                } catch (err) {
                    reject(err);
                }
            };
            reader.readAsText(file);
        });
    },

    /** Parse a Freqtrade config.json into our config format */
    _parseFreqtradeConfig(json, filename = 'Imported Config') {
        return {
            name: json.strategy || filename.replace('.json', ''),
            strategy: json.strategy || '',
            exchange: json.exchange?.name || 'binance',
            apiKey: json.exchange?.key || '',
            apiSecret: json.exchange?.secret || '',
            tradingMode: json.trading_mode || 'spot',
            stakeCurrency: json.stake_currency || 'USDT',
            stakeAmount: String(json.stake_amount || 'unlimited'),
            maxOpenTrades: json.max_open_trades || 3,
            dryRun: json.dry_run !== false,
            dryRunWallet: json.dry_run_wallet || 1000,
            timeframe: json.timeframe || '5m',
            pairWhitelist: json.exchange?.pair_whitelist || [],
            pairBlacklist: json.exchange?.pair_blacklist || [],
            stoploss: json.stoploss || -0.10,
            trailingStop: json.trailing_stop || false,
            trailingStopPositive: json.trailing_stop_positive || 0.01,
            minimalRoi: json.minimal_roi || { '0': 0.04 },
            apiHost: json.api_server?.listen_ip_address || '0.0.0.0',
            apiPort: json.api_server?.listen_port || 8080,
            apiUsername: json.api_server?.username || 'freqtrader',
            apiPassword: json.api_server?.password || '',
            corsOrigins: json.api_server?.CORS_origins || [],
            pairlists: json.pairlists || [{ method: 'StaticPairList' }],
            isActive: false,
        };
    },

    // ========== LOW-LEVEL DB HELPERS ==========

    _put(storeName, data) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.put(data);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    },

    _get(storeName, key) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result || null);
            request.onerror = () => reject(request.error);
        });
    },

    _getAll(storeName) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result || []);
            request.onerror = () => reject(request.error);
        });
    },

    _getByIndex(storeName, indexName, value) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const index = store.index(indexName);
            const request = index.get(value);
            request.onsuccess = () => resolve(request.result || null);
            request.onerror = () => reject(request.error);
        });
    },

    _delete(storeName, key) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.delete(key);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    },
};

<script lang="ts">
    import { api } from '$lib/api';

    let status = $state('Idle');
    let result = $state<Record<string, unknown> | null>(null);
    let loading = $state(false);

    async function importCsv() {
        loading = true; status = 'Importing...'; result = null;
        try { const r = await api.importCsv(); result = r; status = 'Done'; }
        catch (e: unknown) { status = 'Error'; result = { error: String(e) }; }
        loading = false;
    }

    async function fitModel() {
        loading = true; status = 'Training...'; result = null;
        try { const r = await api.fitModel(); result = r; status = 'Done'; }
        catch (e: unknown) { status = 'Error'; result = { error: String(e) }; }
        loading = false;
    }

    async function fitAndEval() {
        loading = true; status = 'Training + evaluating...'; result = null;
        try { const r = await api.fitAndEval(); result = r; status = 'Done'; }
        catch (e: unknown) { status = 'Error'; result = { error: String(e) }; }
        loading = false;
    }

    async function expandData() {
        loading = true; status = 'Fetching data...'; result = null;
        try { const r = await api.expandCsv('2023,2024'); result = r; status = 'Done'; }
        catch (e: unknown) { status = 'Error'; result = { error: String(e) }; }
        loading = false;
    }

    // Render structured metric cards from result object
    const metricLabels: Record<string, string> = {
        accuracy: 'Accuracy',
        log_loss: 'Log Loss',
        brier_score: 'Brier Score',
        auc_roc: 'AUC ROC',
        calibration_error: 'Calibration Error',
        matches: 'Matches',
        total_staked: 'Total Staked',
        total_profit: 'Total Profit',
        roi: 'ROI',
        win_rate: 'Win Rate',
        sharpe_ratio: 'Sharpe Ratio',
        max_drawdown: 'Max Drawdown',
        profit_factor: 'Profit Factor',
        model_type: 'Model Type',
        train_size: 'Training Size',
        test_size: 'Test Size',
        features: 'Features',
        import_rows: 'Rows Imported',
        status: 'Status',
        file: 'File',
        error: 'Error',
    };

    const positiveMetrics = new Set(['accuracy', 'roi', 'win_rate', 'profit_factor', 'sharpe_ratio', 'total_profit']);
    const negativeMetrics = new Set(['log_loss', 'brier_score', 'calibration_error', 'max_drawdown']);

    function formatValue(key: string, val: unknown): string {
        if (val === null || val === undefined) return '-';
        if (typeof val === 'boolean') return val ? 'Yes' : 'No';
        if (typeof val === 'number') {
            if (['accuracy', 'roi', 'win_rate'].includes(key)) return (val * 100).toFixed(1) + '%';
            if (['calibration_error', 'brier_score', 'log_loss'].includes(key)) return val.toFixed(4);
            if (['total_staked', 'total_profit'].includes(key)) return '$' + val.toFixed(2);
            if (typeof val === 'number' && val > 1000) return val.toLocaleString();
            return String(val);
        }
        return String(val);
    }

    let metricKeys = $derived(result ? Object.keys(result).filter(k => k !== 'trades' && k !== 'predictions' && k !== 'details' && k !== 'error') : []);
    let hasError = $derived(result && result.error);
    let nestedKeys = $derived(result ? Object.keys(result).filter(k => typeof result[k] === 'object' && result[k] !== null && !Array.isArray(result[k])) : []);
</script>

<h1>Models</h1>
<p style="color:var(--text-dim);margin-bottom:1rem;font-size:0.85rem">Train Poisson / Dixon-Coles models on historical match data.</p>

<div class="stat-grid" style="grid-template-columns:1fr 1fr 1fr">
    <div class="card" style="display:flex;flex-direction:column;gap:0.5rem">
        <h3>1. Import Data</h3>
        <p style="font-size:0.8rem;color:var(--text-dim)">Load 60 historical matches from CSV</p>
        <button onclick={importCsv} disabled={loading}>📥 Import CSV</button>
    </div>
    <div class="card" style="display:flex;flex-direction:column;gap:0.5rem">
        <h3>2. Train Model</h3>
        <p style="font-size:0.8rem;color:var(--text-dim)">Fit Poisson + Dixon-Coles MLE models</p>
        <button onclick={fitModel} disabled={loading}>🧠 Fit Model</button>
    </div>
    <div class="card" style="display:flex;flex-direction:column;gap:0.5rem">
        <h3>3. Evaluate</h3>
        <p style="font-size:0.8rem;color:var(--text-dim)">Calibration + backtest on holdout</p>
        <button onclick={fitAndEval} disabled={loading}>📊 Fit + Eval</button>
    </div>
</div>

<div class="card mt-1">
    <h3>Data Expansion</h3>
    <p style="font-size:0.8rem;color:var(--text-dim);margin-bottom:0.5rem">Fetch real match data from football-data.org (requires API key)</p>
    <button onclick={expandData} disabled={loading} class="btn-outline">🌐 Expand to 1,000+ matches</button>
</div>

{#if loading}
    <div class="card mt-1">
        <div class="skeleton skeleton-line w40"></div>
        <div class="stat-grid" style="margin-top:1rem">
            {#each Array(4) as _}
                <div>
                    <div class="skeleton skeleton-line w60" style="height:0.7rem"></div>
                    <div class="skeleton skeleton-block" style="height:2rem;margin-top:0.25rem"></div>
                </div>
            {/each}
        </div>
    </div>
{:else if result}
    <div class="card mt-1">
        <div class="flex mb-1" style="justify-content:space-between">
            <span class="badge" class:badge-green={status === 'Done'} class:badge-red={status === 'Error'}>{status}</span>
        </div>

        {#if hasError}
            <div style="background:var(--red-bg);padding:1rem;border-radius:var(--radius);color:var(--red);font-size:0.85rem">
                {result.error}
            </div>
        {:else}
            <!-- Top-level metric cards -->
            {#if metricKeys.length > 0}
                <div class="stat-grid">
                    {#each metricKeys as key}
                        <div class="card" style="background:var(--bg)">
                            <div class="stat-label">{metricLabels[key] || key.replace(/_/g, ' ')}</div>
                            <div class="stat-value" class:positive={positiveMetrics.has(key) && Number(result[key]) > 0}
                                 class:negative={positiveMetrics.has(key) && Number(result[key]) < 0}
                                 style="font-size:1.1rem">
                                {formatValue(key, result[key])}
                            </div>
                        </div>
                    {/each}
                </div>
            {/if}

            <!-- Nested objects as sub-cards -->
            {#each nestedKeys as nKey}
                <div class="card mt-1" style="background:var(--bg)">
                    <h3 style="margin-bottom:0.75rem">{metricLabels[nKey] || nKey.replace(/_/g, ' ')}</h3>
                    <div class="stat-grid" style="grid-template-columns:repeat(auto-fit, minmax(140px, 1fr))">
                        {#each Object.entries(result[nKey] as Record<string, unknown>) as [k, v]}
                            {#if typeof v !== 'object'}
                                <div>
                                    <div class="stat-label">{metricLabels[k] || k.replace(/_/g, ' ')}</div>
                                    <div class="stat-value" style="font-size:1rem">{formatValue(k, v)}</div>
                                </div>
                            {/if}
                        {/each}
                    </div>
                </div>
            {/each}

            <!-- Fallback: show raw JSON for anything complex -->
            {#if metricKeys.length === 0 && nestedKeys.length === 0}
                <pre style="margin-top:0.5rem;font-size:0.8rem;max-height:300px;overflow-y:auto;white-space:pre-wrap">{JSON.stringify(result, null, 2)}</pre>
            {/if}
        {/if}
    </div>
{/if}

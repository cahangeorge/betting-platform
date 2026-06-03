<script lang="ts">
    import { api } from '$lib/api';

    let result = $state<Record<string, unknown> | null>(null);
    let loading = $state(false);

    async function runBacktest() {
        loading = true;
        result = null;
        try {
            const r = await api.fitAndEval();
            result = r;
        } catch (e: unknown) {
            result = { error: e instanceof Error ? e.message : 'Backtest failed' };
        }
        loading = false;
    }

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
            if (val > 1000) return val.toLocaleString();
            return String(val);
        }
        return String(val);
    }

    let metricKeys = $derived(result ? Object.keys(result).filter(k => k !== 'trades' && k !== 'predictions' && k !== 'details' && k !== 'error') : []);
    let hasError = $derived(result && result.error);
    let nestedKeys = $derived(result ? Object.keys(result).filter(k => typeof result[k] === 'object' && result[k] !== null && !Array.isArray(result[k])) : []);
</script>

<h1>Backtest</h1>
<p style="color:var(--text-dim);margin-bottom:1rem;font-size:0.85rem">Use the CLI for full backtesting: <code>uv run python3 scripts/backtest_cli.py --stake 1000 --kelly 0.25 --edge 0.05</code></p>

<div class="grid-2">
    <div class="card">
        <h3>Quick Eval</h3>
        <div style="display:flex;flex-direction:column;gap:1rem;margin-top:1rem">
            <button onclick={runBacktest} disabled={loading}>{loading ? 'Running...' : '▶ Run Fit & Evaluate'}</button>

            {#if loading}
                <div class="stat-grid" style="grid-template-columns:1fr 1fr">
                    {#each Array(4) as _}
                        <div>
                            <div class="skeleton skeleton-line w60" style="height:0.7rem"></div>
                            <div class="skeleton skeleton-block" style="height:2rem;margin-top:0.25rem"></div>
                        </div>
                    {/each}
                </div>
            {:else if result}
                <div style="font-size:0.85rem">
                    {#if hasError}
                        <div style="background:var(--red-bg);padding:1rem;border-radius:var(--radius);color:var(--red)">
                            {result.error}
                        </div>
                    {:else}
                        {#if metricKeys.length > 0}
                            <div class="stat-grid" style="grid-template-columns:1fr 1fr">
                                {#each metricKeys as key}
                                    <div class="card" style="background:var(--bg);padding:0.75rem">
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

                        {#each nestedKeys as nKey}
                            <div class="card mt-1" style="background:var(--bg);padding:0.75rem">
                                <h3 style="margin-bottom:0.5rem;font-size:0.9rem">{metricLabels[nKey] || nKey.replace(/_/g, ' ')}</h3>
                                <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem">
                                    {#each Object.entries(result[nKey] as Record<string, unknown>) as [k, v]}
                                        {#if typeof v !== 'object'}
                                            <div>
                                                <div class="stat-label" style="font-size:0.65rem">{metricLabels[k] || k.replace(/_/g, ' ')}</div>
                                                <div style="font-weight:600;font-size:0.9rem">{formatValue(k, v)}</div>
                                            </div>
                                        {/if}
                                    {/each}
                                </div>
                            </div>
                        {/each}

                        {#if metricKeys.length === 0 && nestedKeys.length === 0}
                            <pre style="white-space:pre-wrap;max-height:300px;overflow-y:auto">{JSON.stringify(result, null, 2)}</pre>
                        {/if}
                    {/if}
                </div>
            {/if}
        </div>
    </div>

    <div class="card">
        <h3>Full Backtest (CLI)</h3>
        <div style="margin-top:1rem;font-size:0.85rem;color:var(--text-dim);line-height:1.6">
            <p>Run the full backtesting engine from the terminal:</p>
            <pre style="background:var(--bg);padding:1rem;border-radius:var(--radius);margin-top:0.5rem;overflow-x:auto">cd /root/betting_platform/backend
uv run python3 scripts/backtest_cli.py \
  --stake 1000 \
  --kelly 0.25 \
  --edge 0.05</pre>
            <p style="margin-top:0.5rem">Outputs: Sharpe ratio, max drawdown, profit factor, edge distribution, odds win rates, league breakdown, full trade log.</p>
        </div>
    </div>
</div>

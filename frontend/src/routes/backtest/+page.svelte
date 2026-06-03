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
</script>

<h1>Backtest</h1>
<p style="color:var(--text-dim);margin-bottom:1rem;font-size:0.85rem">Use the CLI for full backtesting: <code>uv run python3 scripts/backtest_cli.py --stake 1000 --kelly 0.25 --edge 0.05</code></p>

<div class="grid-2">
    <div class="card">
        <h3>Quick Eval</h3>
        <div style="display:flex;flex-direction:column;gap:1rem;margin-top:1rem">
            <button onclick={runBacktest} disabled={loading}>{loading ? 'Running...' : '▶ Run Fit & Evaluate'}</button>
            {#if result}
                <div style="font-size:0.85rem;max-height:300px;overflow-y:auto">
                    <pre style="white-space:pre-wrap">{JSON.stringify(result, null, 2)}</pre>
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

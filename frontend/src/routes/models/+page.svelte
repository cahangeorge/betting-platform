<script lang="ts">
    import { api } from '$lib/api';

    let status = $state('Idle');
    let result = $state('');
    let loading = $state(false);

    async function importCsv() {
        loading = true; status = 'Importing...';
        try { const r = await api.importCsv(); result = JSON.stringify(r, null, 2); status = 'Done'; }
        catch (e: unknown) { status = 'Error'; result = String(e); }
        loading = false;
    }

    async function fitModel() {
        loading = true; status = 'Training...';
        try { const r = await api.fitModel(); result = JSON.stringify(r, null, 2); status = 'Done'; }
        catch (e: unknown) { status = 'Error'; result = String(e); }
        loading = false;
    }

    async function fitAndEval() {
        loading = true; status = 'Training + evaluating...';
        try { const r = await api.fitAndEval(); result = JSON.stringify(r, null, 2); status = 'Done'; }
        catch (e: unknown) { status = 'Error'; result = String(e); }
        loading = false;
    }

    async function expandData() {
        loading = true; status = 'Fetching data...';
        try { const r = await api.expandCsv('2023,2024'); result = JSON.stringify(r, null, 2); status = 'Done'; }
        catch (e: unknown) { status = 'Error'; result = String(e); }
        loading = false;
    }
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

{#if result}
    <div class="card mt-1">
        <div class="flex"><span class="badge" class:badge-green={status === 'Done'}>{status}</span></div>
        <pre style="margin-top:0.5rem;font-size:0.8rem;max-height:300px;overflow-y:auto;white-space:pre-wrap">{result}</pre>
    </div>
{/if}

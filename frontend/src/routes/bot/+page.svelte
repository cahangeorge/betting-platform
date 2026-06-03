<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { api } from '$lib/api';
    import { bankrolls, activeBankrollId } from '$lib/stores';

    let status = $state<Record<string, unknown>>({ running: false });
    let config = $state({ kellyFraction: 0.5, edgeThreshold: 0.15, pollInterval: 5, paper: true });
    let loading = $state(true);
    let message = $state('');
    let intervalId: ReturnType<typeof setInterval> | null = null;

    async function loadStatus() {
        const bid = $activeBankrollId;
        if (bid) {
            try { status = await api.botStatus(bid); } catch { /* ignore */ }
        }
    }

    onMount(async () => {
        const bs = await api.listBankrolls();
        bankrolls.set(bs);
        const bid = bs.length > 0 ? String(bs[0].id) : null;
        if (bid) {
            activeBankrollId.set(bid);
            await loadStatus();
        }
        loading = false;
        intervalId = setInterval(loadStatus, 5000);
    });

    onDestroy(() => {
        if (intervalId) clearInterval(intervalId);
    });

    async function startBot() {
        message = '';
        const bid = $activeBankrollId;
        if (!bid) { message = 'No bankroll found'; return; }
        try {
            const r = await api.botStart(bid, {
                kelly_fraction: config.kellyFraction,
                edge_threshold: config.edgeThreshold,
                poll_interval_seconds: config.pollInterval,
                paper: config.paper,
            });
            status = await api.botStatus(bid);
            message = `Bot ${r.status}`;
        } catch (e: unknown) { message = e instanceof Error ? e.message : 'Failed'; }
    }

    async function stopBot() {
        message = '';
        const bid = $activeBankrollId;
        if (!bid) return;
        try {
            await api.botStop(bid);
            status = await api.botStatus(bid);
            message = 'Bot stopped';
        } catch (e: unknown) { message = e instanceof Error ? e.message : 'Failed'; }
    }

    async function refresh() {
        loading = true;
        await loadStatus();
        loading = false;
    }
</script>

<div class="flex mb-2">
    <h1>Bot Control</h1>
    <button onclick={refresh} class="btn-outline" style="margin-left:auto">↻ Refresh</button>
</div>

{#if loading}
    <div class="stat-grid">
        {#each Array(4) as _}
            <div class="card">
                <div class="skeleton skeleton-line w60"></div>
                <div class="skeleton skeleton-block" style="margin-top:0.5rem"></div>
            </div>
        {/each}
    </div>
{:else}
    <div class="stat-grid">
        <div class="card">
            <div class="stat-label">Status</div>
            <div class="stat-value" class:positive={status.running as boolean}>{status.running ? '🟢 Running' : '⏹ Stopped'}</div>
        </div>
        <div class="card">
            <div class="stat-label">Cycles</div>
            <div class="stat-value">{String(status.cycles ?? 0)}</div>
        </div>
        <div class="card">
            <div class="stat-label">Signals Found</div>
            <div class="stat-value">{String(status.signals_found ?? 0)}</div>
        </div>
        <div class="card">
            <div class="stat-label">Orders Placed</div>
            <div class="stat-value">{String(status.orders_placed ?? 0)}</div>
        </div>
    </div>

    <div class="grid-2">
        <div class="card">
            <h3>Configuration</h3>
            <div style="display:flex;flex-direction:column;gap:1rem;margin-top:1rem">
                <div class="form-group">
                    <label>Kelly Fraction ({config.kellyFraction})</label>
                    <input type="range" min="0" max="1" step="0.05" bind:value={config.kellyFraction} />
                </div>
                <div class="form-group">
                    <label>Edge Threshold ({config.edgeThreshold})</label>
                    <input type="range" min="0.01" max="0.5" step="0.01" bind:value={config.edgeThreshold} />
                </div>
                <div class="form-group">
                    <label>Poll Interval (s)</label>
                    <input type="number" min="1" max="300" bind:value={config.pollInterval} />
                </div>
                <label class="flex" style="align-items:center;gap:0.5rem;cursor:pointer">
                    <input type="checkbox" bind:checked={config.paper} />
                    Paper mode (simulated fills)
                </label>
            </div>
        </div>

        <div class="card">
            <h3>Controls</h3>
            <div class="flex" style="margin-top:1rem;flex-wrap:wrap">
                <button onclick={startBot} disabled={status.running as boolean} class="btn-green">▶ Start Bot</button>
                <button onclick={stopBot} disabled={!status.running as boolean} class="btn-red">⏹ Stop Bot</button>
            </div>
            {#if message}
                <p style="margin-top:1rem;font-size:0.85rem;color:var(--text-dim)">{message}</p>
            {/if}
        </div>
    </div>
{/if}

<script lang="ts">
    import { onMount } from 'svelte';
    import { api } from '$lib/api';
    import { bankrolls, activeBankrollId } from '$lib/stores';

    let stats = $state({
        bankroll: 0, trades: 0, winRate: 0, pnl: 0,
        botRunning: false, matches: 0, signals: 0,
    });
    let loading = $state(true);

    onMount(async () => {
        try {
            const bs = await api.listBankrolls();
            bankrolls.set(bs);
            const bid = bs.length > 0 ? String(bs[0].id) : null;
            if (bid) activeBankrollId.set(bid);

            const [st, trades, matches] = await Promise.all([
                bid ? api.botStatus(bid).catch(() => ({})) : {},
                bid ? api.listTrades(bid).catch(() => []) : [],
                api.listMatches('live').catch(() => []),
            ]);

            const s = st as Record<string, unknown>;
            stats = {
                bankroll: bs.length > 0 ? Number(bs[0].balance) : 0,
                trades: trades.length,
                winRate: trades.length > 0
                    ? Math.round(trades.filter((t: Record<string, unknown>) => t.final_result === 'won').length / trades.length * 100)
                    : 0,
                pnl: trades.reduce((s: number, t: Record<string, unknown>) => s + Number(t.profit_loss || 0), 0),
                botRunning: s.running === true,
                matches: matches.length,
                signals: Number(s.signals_found || 0),
            };
        } catch { /* not authed */ }
        loading = false;
    });
</script>

<h1>Dashboard</h1>

{#if loading}
    <p>Loading...</p>
{:else}
    <div class="stat-grid">
        <div class="card">
            <div class="stat-label">Bankroll</div>
            <div class="stat-value mono">${stats.bankroll.toFixed(2)}</div>
        </div>
        <div class="card">
            <div class="stat-label">P&L</div>
            <div class="stat-value mono" class:positive={stats.pnl >= 0} class:negative={stats.pnl < 0}>
                ${stats.pnl >= 0 ? '+' : ''}{stats.pnl.toFixed(2)}
            </div>
        </div>
        <div class="card">
            <div class="stat-label">Trades</div>
            <div class="stat-value">{stats.trades}</div>
        </div>
        <div class="card">
            <div class="stat-label">Win Rate</div>
            <div class="stat-value">{stats.winRate}%</div>
        </div>
        <div class="card">
            <div class="stat-label">Bot</div>
            <div class="stat-value" class:positive={stats.botRunning}>{stats.botRunning ? 'Running' : 'Stopped'}</div>
        </div>
        <div class="card">
            <div class="stat-label">Live Matches</div>
            <div class="stat-value">{stats.matches}</div>
        </div>
    </div>
{/if}

<style>
    .stat-value { font-size: 1.25rem; }
</style>

<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { api } from '$lib/api';
    import { bankrolls, activeBankrollId } from '$lib/stores';

    let stats = $state({
        bankroll: 0, trades: 0, winRate: 0, pnl: 0,
        botRunning: false, matches: 0, signals: 0,
    });
    let equityHistory = $state<number[]>([]);
    let loading = $state(true);
    let intervalId: ReturnType<typeof setInterval> | null = null;

    async function loadData() {
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
            const currentBankroll = bs.length > 0 ? Number(bs[0].balance) : 0;
            stats = {
                bankroll: currentBankroll,
                trades: trades.length,
                winRate: trades.length > 0
                    ? Math.round(trades.filter((t: Record<string, unknown>) => t.final_result === 'won').length / trades.length * 100)
                    : 0,
                pnl: trades.reduce((s: number, t: Record<string, unknown>) => s + Number(t.profit_loss || 0), 0),
                botRunning: s.running === true,
                matches: matches.length,
                signals: Number(s.signals_found || 0),
            };

            // Build equity curve from trades (cumulative P&L)
            const sortedTrades = [...trades].sort((a: Record<string, unknown>, b: Record<string, unknown>) =>
                String(a.created_at || '').localeCompare(String(b.created_at || ''))
            );
            let cumPnl = 0;
            const initial = bs.length > 0 ? Number(bs[0].initial_balance || bs[0].balance || 1000) : 1000;
            const curve: number[] = [initial];
            for (const t of sortedTrades) {
                cumPnl += Number(t.profit_loss || 0);
                curve.push(initial + cumPnl);
            }
            equityHistory = curve;
        } catch { /* not authed */ }
        loading = false;
    }

    onMount(async () => {
        await loadData();
        intervalId = setInterval(loadData, 5000);
    });

    onDestroy(() => {
        if (intervalId) clearInterval(intervalId);
    });

    // SVG chart helpers
    let chartBars = $derived.by(() => {
        if (equityHistory.length === 0) return [];
        const min = Math.min(...equityHistory) * 0.98;
        const max = Math.max(...equityHistory) * 1.02;
        const range = max - min || 1;
        const chartH = 120;
        const chartW = 400;
        const barW = Math.max(2, Math.min(20, (chartW - (equityHistory.length - 1) * 2) / equityHistory.length));
        const gap = equityHistory.length > 1 ? (chartW - barW * equityHistory.length) / (equityHistory.length - 1) : 0;
        return equityHistory.map((val, i) => {
            const h = ((val - min) / range) * chartH;
            const x = i * (barW + (equityHistory.length > 1 ? gap : 0));
            const y = chartH - h;
            const color = i === 0 ? 'var(--accent)' : val >= (equityHistory[i - 1] ?? min) ? 'var(--green)' : 'var(--red)';
            return { x, y, h: Math.max(1, h), w: barW, color, val };
        });
    });
</script>

<h1>Dashboard</h1>

{#if loading}
    <div class="stat-grid">
        {#each Array(6) as _}
            <div class="card">
                <div class="skeleton skeleton-line w60"></div>
                <div class="skeleton skeleton-block" style="margin-top:0.5rem"></div>
            </div>
        {/each}
    </div>
    <div class="card">
        <div class="skeleton skeleton-line w40"></div>
        <div class="skeleton skeleton-chart"></div>
    </div>
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

    <!-- Equity Curve Chart -->
    {#if equityHistory.length > 0}
        <div class="card">
            <div class="stat-label" style="margin-bottom:0.75rem">Bankroll Equity Curve</div>
            <svg viewBox="0 0 400 130" style="width:100%;height:auto;overflow:visible">
                <!-- Baseline -->
                <line x1="0" y1="120" x2="400" y2="120" stroke="var(--border)" stroke-width="1" />
                <!-- Bars -->
                {#each chartBars as bar}
                    <rect x={bar.x} y={bar.y} width={bar.w} height={bar.h} fill={bar.color} rx="2" opacity="0.85">
                        <title>${bar.val.toFixed(2)}</title>
                    </rect>
                {/each}
            </svg>
            <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:var(--text-dim);margin-top:0.25rem">
                <span>Start</span>
                <span>Now</span>
            </div>
        </div>
    {:else}
        <div class="card">
            <div class="stat-label">Bankroll Equity Curve</div>
            <p style="color:var(--text-dim);font-size:0.85rem;margin-top:0.5rem">No trades yet — equity curve will appear here.</p>
        </div>
    {/if}
{/if}

<style>
    .stat-value { font-size: 1.25rem; }
</style>

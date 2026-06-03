<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { api } from '$lib/api';
    import { bankrolls, activeBankrollId } from '$lib/stores';

    let trades = $state<Array<Record<string, unknown>>>([]);
    let filter = $state('all');
    let loading = $state(true);
    let intervalId: ReturnType<typeof setInterval> | null = null;

    // Pagination
    let page = $state(1);
    const pageSize = 20;
    let paginatedTrades = $derived.by(() => {
        const start = (page - 1) * pageSize;
        return trades.slice(start, start + pageSize);
    });
    let totalPages = $derived(Math.max(1, Math.ceil(trades.length / pageSize)));

    async function loadData() {
        const bid = $activeBankrollId;
        if (bid) {
            try {
                trades = await api.listTrades(bid, filter === 'all' ? undefined : filter);
            } catch { /* ignore */ }
        }
    }

    onMount(async () => {
        const bs = await api.listBankrolls();
        bankrolls.set(bs);
        const bid = bs.length > 0 ? String(bs[0].id) : null;
        if (bid) {
            activeBankrollId.set(bid);
            await loadData();
        }
        loading = false;
        intervalId = setInterval(loadData, 5000);
    });

    onDestroy(() => {
        if (intervalId) clearInterval(intervalId);
    });

    async function refresh() {
        loading = true;
        await loadData();
        loading = false;
    }

    function onFilterChange() {
        page = 1;
        refresh();
    }

    let totalPnl = $derived(trades.reduce((s, t) => s + Number(t.profit_loss || 0), 0));
    let wins = $derived(trades.filter(t => t.final_result === 'won').length);
    let losses = $derived(trades.filter(t => t.final_result === 'lost').length);
</script>

<div class="flex mb-2">
    <h1>Trade Log</h1>
    <div class="flex gap-sm" style="margin-left:auto">
        <select bind:value={filter} onchange={onFilterChange}>
            <option value="all">All</option>
            <option value="filled">Filled</option>
            <option value="settled">Settled</option>
        </select>
        <button onclick={refresh}>↻</button>
    </div>
</div>

<div class="stat-grid">
    <div class="card"><div class="stat-label">Total Trades</div><div class="stat-value">{trades.length}</div></div>
    <div class="card"><div class="stat-label">Wins</div><div class="stat-value positive">{wins}</div></div>
    <div class="card"><div class="stat-label">Losses</div><div class="stat-value negative">{losses}</div></div>
    <div class="card"><div class="stat-label">Total P&L</div><div class="stat-value mono" class:positive={totalPnl >= 0} class:negative={totalPnl < 0}>${totalPnl.toFixed(2)}</div></div>
</div>

<div class="card" style="overflow-x:auto">
    {#if loading}
        <table>
            <thead>
                <tr><th>Match</th><th>Bet</th><th>Odds</th><th>Edge</th><th>Stake</th><th>Result</th><th>P&L</th></tr>
            </thead>
            <tbody>
                {#each Array(8) as _}
                    <tr>
                        {#each Array(7) as _}
                            <td><div class="skeleton skeleton-line w80"></div></td>
                        {/each}
                    </tr>
                {/each}
            </tbody>
        </table>
    {:else if trades.length === 0}
        <p style="color:var(--text-dim);text-align:center">No trades yet</p>
    {:else}
        <table>
            <thead>
                <tr><th>Match</th><th>Bet</th><th>Odds</th><th>Edge</th><th>Stake</th><th>Result</th><th>P&L</th></tr>
            </thead>
            <tbody>
                {#each paginatedTrades as t}
                    <tr>
                        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{t.market_id as string}</td>
                        <td><span class="tag">{t.side as string}</span></td>
                        <td class="mono">{Number(t.requested_odds).toFixed(2)}</td>
                        <td class="mono">{t.edge_at_entry ? (Number(t.edge_at_entry) * 100).toFixed(1) + '%' : '-'}</td>
                        <td class="mono">${Number(t.requested_stake).toFixed(2)}</td>
                        <td>
                            {#if t.final_result === 'won'}
                                <span class="badge badge-green">WON</span>
                            {:else if t.final_result === 'lost'}
                                <span class="badge badge-red">LOST</span>
                            {:else}
                                <span class="badge badge-blue">{t.status as string}</span>
                            {/if}
                        </td>
                        <td class="mono" class:positive={Number(t.profit_loss) >= 0} class:negative={Number(t.profit_loss) < 0}>
                            {t.profit_loss ? `$${Number(t.profit_loss).toFixed(2)}` : '-'}
                        </td>
                    </tr>
                {/each}
            </tbody>
        </table>

        {#if totalPages > 1}
            <div class="pagination">
                <button onclick={() => page = Math.max(1, page - 1)} disabled={page <= 1}>← Prev</button>
                <span class="page-info">Page {page} / {totalPages}</span>
                <button onclick={() => page = Math.min(totalPages, page + 1)} disabled={page >= totalPages}>Next →</button>
            </div>
        {/if}
    {/if}
</div>

<style>
    .positive { color: var(--green); }
    .negative { color: var(--red); }
</style>

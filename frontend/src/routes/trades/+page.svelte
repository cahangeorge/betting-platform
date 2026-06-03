<script lang="ts">
    import { onMount } from 'svelte';
    import { api } from '$lib/api';
    import { bankrolls, activeBankrollId } from '$lib/stores';

    let trades = $state<Array<Record<string, unknown>>>([]);
    let filter = $state('all');
    let loading = $state(true);

    onMount(async () => {
        const bs = await api.listBankrolls();
        bankrolls.set(bs);
        const bid = bs.length > 0 ? String(bs[0].id) : null;
        if (bid) {
            activeBankrollId.set(bid);
            trades = await api.listTrades(bid, filter === 'all' ? undefined : filter);
        }
        loading = false;
    });

    async function refresh() {
        loading = true;
        const bid = $activeBankrollId;
        if (bid) trades = await api.listTrades(bid, filter === 'all' ? undefined : filter);
        loading = false;
    }

    let totalPnl = $derived(trades.reduce((s, t) => s + Number(t.profit_loss || 0), 0));
    let wins = $derived(trades.filter(t => t.final_result === 'won').length);
    let losses = $derived(trades.filter(t => t.final_result === 'lost').length);
</script>

<div class="flex mb-2">
    <h1>Trade Log</h1>
    <div class="flex gap-sm" style="margin-left:auto">
        <select bind:value={filter} onchange={refresh}>
            <option value="all">All</option>
            <option value="filled">Open</option>
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
    {#if trades.length === 0}
        <p style="color:var(--text-dim);text-align:center">No trades yet</p>
    {:else}
        <table>
            <thead>
                <tr><th>Match</th><th>Bet</th><th>Odds</th><th>Edge</th><th>Stake</th><th>Result</th><th>P&L</th></tr>
            </thead>
            <tbody>
                {#each trades as t}
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
    {/if}
</div>

<style>
    .positive { color: var(--green); }
    .negative { color: var(--red); }
</style>

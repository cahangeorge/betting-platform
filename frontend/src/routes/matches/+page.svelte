<script lang="ts">
    import { onMount } from 'svelte';
    import { api } from '$lib/api';

    let matches = $state<Array<Record<string, unknown>>>([]);
    let loading = $state(true);
    let filter = $state('live');

    onMount(async () => {
        try {
            const all = await api.listMatches(filter === 'all' ? undefined : filter);
            matches = all;
        } catch { /* */ }
        loading = false;
    });

    async function refresh() {
        loading = true;
        try { matches = await api.listMatches(filter === 'all' ? undefined : filter); } catch { /* */ }
        loading = false;
    }
</script>

<div class="flex mb-2">
    <h1>Matches</h1>
    <div class="flex gap-sm" style="margin-left:auto">
        <select bind:value={filter} onchange={refresh}>
            <option value="live">Live</option>
            <option value="upcoming">Upcoming</option>
            <option value="finished">Finished</option>
            <option value="all">All</option>
        </select>
        <button onclick={refresh}>↻</button>
    </div>
</div>

{#if loading}
    <p>Loading...</p>
{:else if matches.length === 0}
    <div class="card"><p style="color:var(--text-dim);text-align:center">No matches found</p></div>
{:else}
    <div class="card" style="overflow-x:auto">
        <table>
            <thead>
                <tr>
                    <th>Home</th><th>Away</th><th>League</th><th>Score</th><th>Status</th><th>Odds</th><th>Action</th>
                </tr>
            </thead>
            <tbody>
                {#each matches as m}
                    <tr>
                        <td><strong>{m.home_team as string}</strong></td>
                        <td>{m.away_team as string}</td>
                        <td><span class="tag">{m.league as string}</span></td>
                        <td class="mono">{m.home_score ?? '-'} : {m.away_score ?? '-'}</td>
                        <td><span class="badge" class:badge-green={m.status === 'live'} class:badge-blue={m.status === 'upcoming'}>{m.status as string}</span></td>
                        <td class="mono">{m.betfair_market_id ? 'BF' : ''}{m.smarkets_market_id ? ' SM' : ''}</td>
                        <td><a href={`/matches/${m.id}`} class="btn btn-outline" style="padding:0.25rem 0.5rem;font-size:0.75rem">View</a></td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
{/if}

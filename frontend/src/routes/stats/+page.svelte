<script lang="ts">
    import { onMount } from 'svelte';
    import { api } from '$lib/api';

    let ingester = $state<Record<string, unknown>>({ running: false });
    let matches = $state<Array<Record<string, unknown>>>([]);
    let loading = $state(true);
    let momentumPopup = $state<Record<string, unknown> | null>(null);
    let showPopup = $state(false);

    onMount(async () => {
        try {
            ingester = await api.ingesterStatus();
            matches = await api.listMatches('live');
        } catch { /* */ }
        loading = false;
    });

    async function toggleIngester() {
        if (ingester.running) {
            await api.ingesterStop();
        } else {
            await api.ingesterStart();
        }
        ingester = await api.ingesterStatus();
    }

    async function getMomentum(matchId: string) {
        const m = await api.momentum(matchId);
        momentumPopup = m as Record<string, unknown>;
        showPopup = true;
    }
</script>

<h1>Live Stats</h1>
<p style="color:var(--text-dim);margin-bottom:1rem;font-size:0.85rem">Live match stats from football-data.org + Understat feeds.</p>

<div class="stat-grid">
    <div class="card">
        <div class="stat-label">Stats Ingester</div>
        <div class="stat-value" class:positive={ingester.running as boolean}>{ingester.running ? '🟢 Running' : '⏹ Stopped'}</div>
        <button onclick={toggleIngester} style="margin-top:0.5rem;font-size:0.8rem">
            {ingester.running ? 'Stop' : 'Start'} Ingester
        </button>
    </div>
    <div class="card">
        <div class="stat-label">Live Matches</div>
        <div class="stat-value">{matches.length}</div>
    </div>
</div>

<div class="card">
    <h3>Live Matches</h3>
    {#if matches.length === 0}
        <p style="color:var(--text-dim);font-size:0.85rem">No live matches. Set a match to status="live" in the DB or through the API.</p>
    {:else}
        <table>
            <thead><tr><th>Match</th><th>Score</th><th>Momentum</th><th>Action</th></tr></thead>
            <tbody>
                {#each matches as m}
                <tr>
                    <td>{m.home_team as string} vs {m.away_team as string}</td>
                    <td class="mono">{m.home_score ?? '-'} : {m.away_score ?? '-'}</td>
                    <td>
                        <button class="btn-outline" style="padding:0.2rem 0.4rem;font-size:0.75rem" onclick={() => getMomentum(m.id as string)}>
                            View
                        </button>
                    </td>
                    <td><a href={`/matches/${m.id}`} class="btn-outline" style="padding:0.2rem 0.4rem;font-size:0.75rem">Details</a></td>
                </tr>
                {/each}
            </tbody>
        </table>
    {/if}
</div>

{#if showPopup && momentumPopup}
<div style="position:fixed;inset:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:50" onclick={() => showPopup = false}>
    <div class="card" style="max-width:400px;width:90%;max-height:80vh;overflow-y:auto" onclick={(e) => e.stopPropagation()}>
        <h3>Momentum</h3>
        <pre style="font-size:0.8rem;margin-top:0.5rem">{JSON.stringify(momentumPopup, null, 2)}</pre>
        <button onclick={() => showPopup = false} style="margin-top:1rem">Close</button>
    </div>
</div>
{/if}

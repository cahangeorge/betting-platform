<script lang="ts">
    import { page } from '$app/stores';
    import { onMount } from 'svelte';
    import { api } from '$lib/api';

    let match = $state<Record<string, unknown> | null>(null);
    let momentum = $state<Record<string, unknown> | null>(null);
    let stats = $state<Array<Record<string, unknown>>>([]);
    let prediction = $state<Record<string, unknown> | null>(null);
    let loading = $state(true);

    onMount(async () => {
        const id = $page.params.id;
        try {
            const [m, mom, hist, pred] = await Promise.all([
                api.listMatches('all').then(ms => ms.find((x: Record<string, unknown>) => x.id === id)),
                api.momentum(id).catch(() => null),
                api.statHistory(id).catch(() => []),
                api.predict(
                    (match?.home_team as string) || 'Arsenal',
                    (match?.away_team as string) || 'Chelsea'
                ).catch(() => null),
            ]);
            match = m ?? null;
            momentum = mom as Record<string, unknown> | null;
            stats = hist as Array<Record<string, unknown>>;
            prediction = pred as Record<string, unknown> | null;
        } catch { /* */ }
        loading = false;
    });
</script>

<button onclick={() => history.back()} class="btn-outline mb-1" style="font-size:0.8rem">← Back</button>

{#if loading}
    <p>Loading...</p>
{:else if !match}
    <div class="card"><p>Match not found</p></div>
{:else}
    <h1>{match.home_team as string} vs {match.away_team as string}</h1>
    <p style="color:var(--text-dim);margin-bottom:1rem">{match.league as string} · Score: {match.home_score ?? '-'} : {match.away_score ?? '-'} · <span class="badge" class:badge-green={match.status === 'live'}>{match.status as string}</span></p>

    <div class="grid-2">
        {#if prediction}
        <div class="card">
            <h3>Model Prediction</h3>
            <div class="stat-grid" style="grid-template-columns:1fr 1fr 1fr">
                <div><div class="stat-label">Home</div><div class="stat-value" style="font-size:1rem">{(Number(prediction.home_win_prob) * 100).toFixed(1)}%</div></div>
                <div><div class="stat-label">Draw</div><div class="stat-value" style="font-size:1rem">{(Number(prediction.draw_prob) * 100).toFixed(1)}%</div></div>
                <div><div class="stat-label">Away</div><div class="stat-value" style="font-size:1rem">{(Number(prediction.away_win_prob) * 100).toFixed(1)}%</div></div>
            </div>
            <div class="flex gap-sm" style="margin-top:0.5rem;font-size:0.8rem;color:var(--text-dim)">
                <span>Model: {prediction.model_name as string}</span>
                <span>Confidence: {prediction.confidence as string}</span>
            </div>
        </div>
        {/if}

        {#if momentum}
        <div class="card">
            <h3>Momentum</h3>
            {#if momentum.momentum as Record<string, unknown>}
                <div class="stat-grid" style="grid-template-columns:1fr 1fr">
                    <div><div class="stat-label">Home Score</div><div class="stat-value" style="font-size:1rem;color:var(--green)">{(momentum.momentum as Record<string, unknown>).home_score as number}</div></div>
                    <div><div class="stat-label">Away Score</div><div class="stat-value" style="font-size:1rem;color:var(--red)">{(momentum.momentum as Record<string, unknown>).away_score as number}</div></div>
                </div>
                <p style="font-size:0.8rem;color:var(--text-dim);margin-top:0.5rem">Differential: {(momentum.momentum as Record<string, unknown>).differential as number}</p>
            {:else}
                <p style="color:var(--text-dim);font-size:0.85rem">No momentum data yet</p>
            {/if}
        </div>
        {/if}
    </div>

    {#if match.status === 'live'}
        <div class="card mt-1">
            <h3>Live Stats</h3>
            {#if stats.length > 0}
                <table>
                    <thead><tr><th>Min</th><th>xG H</th><th>xG A</th><th>SoT H</th><th>SoT A</th></tr></thead>
                    <tbody>
                        {#each stats as s}
                        <tr>
                            <td class="mono">{s.elapsed as string}'</td>
                            <td class="mono">{s.xg_home as string ?? '-'}</td>
                            <td class="mono">{s.xg_away as string ?? '-'}</td>
                            <td class="mono">{s.shots_on_target_home as string ?? '-'}</td>
                            <td class="mono">{s.shots_on_target_away as string ?? '-'}</td>
                        </tr>
                        {/each}
                    </tbody>
                </table>
            {:else}
                <p style="color:var(--text-dim);font-size:0.85rem">No stats ingested yet. Use <code>/stats/ingest/{match.id}</code> or start the stats ingester.</p>
            {/if}
        </div>
    {/if}
{/if}

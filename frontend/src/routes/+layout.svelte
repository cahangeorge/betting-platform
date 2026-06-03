<script lang="ts">
    import { page } from '$app/stores';
    import { user, token, bankrolls, activeBankrollId } from '$lib/stores';
    import { api, getToken, setToken } from '$lib/api';
    import { onMount } from 'svelte';
    import '../app.css';

    let { children } = $props();
    let authed = $state(false);

    onMount(async () => {
        if (getToken()) {
            try {
                const u = await api.me();
                user.set(u);
                token.set(getToken());
                authed = true;
                const bs = await api.listBankrolls();
                bankrolls.set(bs);
                if (bs.length > 0) activeBankrollId.set(String(bs[0].id));
            } catch {
                setToken(null);
                authed = false;
            }
        }
    });

    let u = $derived($user);
    $effect(() => { authed = !!u; });

    let nav = $derived($page.url.pathname);
    function isActive(p: string) { return nav === p ? 'active' : ''; }

    async function logout() {
        setToken(null);
        user.set(null);
        authed = false;
    }
</script>

{#if !authed}
    {@render children()}
{:else}
    <div class="layout">
        <aside class="sidebar">
            <h1>⚽ Betting Bot</h1>
            <nav>
                <a href="/dashboard" class={isActive('/dashboard')}>Dashboard</a>
                <a href="/matches" class={isActive('/matches')}>Matches</a>
                <a href="/bot" class={isActive('/bot')}>Bot Control</a>
                <a href="/trades" class={isActive('/trades')}>Trade Log</a>
                <a href="/backtest" class={isActive('/backtest')}>Backtest</a>
                <a href="/models" class={isActive('/models')}>Models</a>
                <a href="/stats" class={isActive('/stats')}>Live Stats</a>
            </nav>
            <div style="margin-top:auto;padding:1rem 1.25rem;border-top:1px solid var(--border);font-size:0.8rem;color:var(--text-dim)">
                <div>{u?.email}</div>
                <button class="btn-outline" style="margin-top:0.5rem;font-size:0.75rem;padding:0.3rem 0.6rem" onclick={logout}>Logout</button>
            </div>
        </aside>
        <main class="main">
            {@render children()}
        </main>
    </div>
{/if}

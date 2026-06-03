<script lang="ts">
    import { page } from '$app/stores';
    import { user } from '$lib/stores';
    import { getToken, setToken, api } from '$lib/api';
    import { onMount } from 'svelte';

    let email = '';
    let password = '';
    let error = '';
    let loading = false;

    onMount(() => {
        if (getToken()) {
            api.me().then(u => user.set(u)).catch(() => setToken(null));
        }
    });

    async function handleLogin() {
        loading = true;
        error = '';
        try {
            const r = await api.login(email, password);
            setToken(r.access_token);
            const u = await api.me();
            user.set(u);
        } catch (e: unknown) {
            error = e instanceof Error ? e.message : 'Login failed';
        }
        loading = false;
    }

    async function handleRegister() {
        loading = true;
        error = '';
        try {
            await api.register(email, password);
            await handleLogin();
        } catch (e: unknown) {
            error = e instanceof Error ? e.message : 'Registration failed';
        }
        loading = false;
    }
</script>

<div class="login-page">
    <div class="login-card">
        <h1>Betting Bot</h1>
        <p class="subtitle">Live Football Trading Platform</p>

        <form onsubmit={(e) => { e.preventDefault(); handleLogin(); }}>
            <div class="form-group">
                <label for="email">Email</label>
                <input id="email" type="email" bind:value={email} placeholder="you@example.com" required />
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input id="password" type="password" bind:value={password} placeholder="••••••••" required />
            </div>

            {#if error}
                <div class="error-msg">{error}</div>
            {/if}

            <div class="flex gap-sm">
                <button type="submit" disabled={loading}>{loading ? 'Loading...' : 'Sign In'}</button>
                <button type="button" class="btn-outline" onclick={handleRegister} disabled={loading}>Register</button>
            </div>
        </form>
    </div>
</div>

<style>
    .login-page {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 100vh;
        background: var(--bg);
    }
    .login-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 2.5rem;
        width: 380px;
    }
    .login-card h1 { text-align: center; margin-bottom: 0.25rem; }
    .subtitle { text-align: center; color: var(--text-dim); font-size: 0.875rem; margin-bottom: 2rem; }
    .login-card form { display: flex; flex-direction: column; gap: 1rem; }
    .error-msg { background: var(--red-bg); color: var(--red); padding: 0.5rem; border-radius: var(--radius); font-size: 0.8rem; text-align: center; }
</style>

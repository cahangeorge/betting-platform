<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { authApi } from '$lib/api/auth';
	import { Menu, Activity, Search, Wifi, WifiOff } from 'lucide-svelte';
	import { onMount } from 'svelte';
	import Button from './ui/Button.svelte';
	import { ThemeToggle } from './ui/theme-toggle';
	import {
		DropdownMenuRoot,
		DropdownMenuTrigger,
		DropdownMenuContent,
		DropdownMenuItem,
		DropdownMenuSeparator,
		DropdownMenuLabel
	} from './ui/dropdown-menu';
	import { liveSocket } from '$lib/stores/liveSocket';
	import type { User as AuthenticatedUser } from '$lib/types';

	let {
		user,
		onToggleSidebar,
		onOpenCommandPalette,
		showWorkspaceMenu = true
	}: {
		user: AuthenticatedUser | null;
		onToggleSidebar: () => void;
		onOpenCommandPalette: () => void;
		showWorkspaceMenu?: boolean;
	} = $props();

	let now = $state(new Date());
	let wsStatus = $state('disconnected');

	async function handleLogout() {
		try {
			await authApi.logout();
				goto('/login');
		} catch {
				goto('/login');
		}
	}

	onMount(() => {
		const interval = setInterval(() => {
			now = new Date();
		}, 60_000);
		const unsub = liveSocket.subscribe((s) => {
			wsStatus = s.status;
		});

		return () => {
			clearInterval(interval);
			unsub();
		};
	});

	let timeStr = $derived(
		now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
	);
	const homeHref = $derived(user ? '/' : '/about');
	const authHref = $derived($page.url.pathname.startsWith('/login') ? '/signup' : '/login');
	const authLabel = $derived($page.url.pathname.startsWith('/login') ? 'Creează cont' : 'Autentificare');
	const displayName = $derived(user?.name?.trim() || user?.email || 'Utilizator');
</script>

<nav
	class="fixed top-0 left-0 right-0 z-50 h-16 border-b border-border bg-background/80 backdrop-blur-xl"
	aria-label="Bara principală de navigare"
>
	<div class="flex items-center justify-between h-full px-4 lg:px-6">
		<div class="flex items-center gap-2 sm:gap-4">
			{#if showWorkspaceMenu}
				<Button
					variant="ghost"
					size="sm"
					class="lg:hidden p-2"
					onclick={onToggleSidebar}
					aria-label="Deschide meniul lateral"
				>
					<Menu class="w-5 h-5 text-muted-foreground" />
				</Button>
			{/if}
			<a href={homeHref} class="flex min-h-11 items-center gap-2" aria-label="Betfront — pagina principală">
				<span class="flex size-8 items-center justify-center border border-football-green/60 bg-football-green/10 font-sport text-sm font-extrabold text-football-green" aria-hidden="true">BF</span>
				<span class="hidden text-sm font-semibold tracking-tight text-foreground sm:inline">
					Betfront <span class="text-muted-foreground">/ Spațiu de decizie</span>
				</span>
			</a>
		</div>

		<div class="flex items-center space-x-4">
			<Button
				variant="ghost"
				size="sm"
				class="hidden md:flex items-center gap-2 px-3"
				onclick={onOpenCommandPalette}
				aria-label="Deschide paleta de navigare"
			>
				<Search class="w-4 h-4 text-muted-foreground" />
				<span class="text-sm text-muted-foreground">Navigare</span>
				<span class="text-[10px] font-mono text-muted-foreground">Alt K</span>
			</Button>

			<ThemeToggle />

			<div class="hidden md:flex items-center space-x-3">
				{#if wsStatus === 'connected'}
					<Wifi class="w-3 h-3 text-football-green" />
					<span class="text-xs font-mono text-football-green">Conectat</span>
				{:else if wsStatus === 'connecting' || wsStatus === 'reconnecting'}
					<Activity class="w-3 h-3 text-amber-500 animate-pulse" />
					<span class="text-xs font-mono text-amber-500">Se conectează...</span>
				{:else}
					<WifiOff class="w-3 h-3 text-destructive" />
					<span class="text-xs font-mono text-destructive">Deconectat</span>
				{/if}
				<span class="text-xs font-mono text-muted-foreground">{timeStr}</span>
			</div>

			{#if user}
				<DropdownMenuRoot>
					<DropdownMenuTrigger class="touch-target flex items-center space-x-2 border border-border p-1.5 transition-colors hover:bg-muted">
						<div class="w-7 h-7 flex items-center justify-center text-xs font-bold  bg-muted text-football-green">
							{displayName.charAt(0).toUpperCase()}
						</div>
						<span class="text-sm hidden md:block text-foreground">{displayName}</span>
					</DropdownMenuTrigger>
					<DropdownMenuContent class="w-56" align="end">
						<DropdownMenuLabel>
							<p class="text-sm font-medium text-foreground">{displayName}</p>
							<p class="text-xs text-muted-foreground">{user.email}</p>
						</DropdownMenuLabel>
						<DropdownMenuSeparator />
						<DropdownMenuItem>
							<a href="/account" class="block w-full text-sm text-muted-foreground hover:text-foreground transition-colors">
								Setările contului
							</a>
						</DropdownMenuItem>
						<DropdownMenuItem>
							<button
								class="w-full text-left text-sm text-destructive hover:text-destructive/80 transition-colors"
								onclick={handleLogout}
							>
								Deconectare
							</button>
						</DropdownMenuItem>
					</DropdownMenuContent>
				</DropdownMenuRoot>
			{:else}
				<a href={authHref} class="inline-flex min-h-11 items-center justify-center bg-primary px-4 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90">
					{authLabel}
				</a>
			{/if}
		</div>
	</div>
</nav>

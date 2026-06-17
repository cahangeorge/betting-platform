<script lang="ts">
	import { page } from '$app/stores';
	import {
		Home,
		BarChart3,
		Ticket,
		Download,
		Database,
		LayoutGrid,
		User,
		Info,
		Zap,
		Radio
	} from 'lucide-svelte';
	import { cn } from '$lib/utils';
	import Button from './ui/Button.svelte';
	import { ThemeToggle } from './ui/theme-toggle';
	import {
		SheetRoot,
		SheetContent,
		SheetHeader,
		SheetTitle,
		SheetClose
	} from './ui/sheet';

	let {
		open = $bindable(false),
		user
	}: {
		open: boolean;
		user: { name: string; email: string } | null;
	} = $props();

	const primaryNavItems = [
		{ href: '/', label: 'Dashboard', icon: Home },
		{ href: '/scrape', label: 'Scrape', icon: Download },
		{ href: '/predict', label: 'Predict', icon: BarChart3 },
		{ href: '/tickets', label: 'Tickets', icon: Ticket },
		{ href: '/account', label: 'Account', icon: User }
	];

	const secondaryNavItems = [
		{ href: '/data', label: 'Data', icon: Database },
		{ href: '/board', label: 'Board', icon: LayoutGrid },
		{ href: '/value-bets', label: 'Value Bets', icon: Zap },
		{ href: '/live', label: 'Live', icon: Radio },
		{ href: '/about', label: 'About', icon: Info }
	];

	function isActive(href: string): boolean {
		if (href === '/') return $page.url.pathname === '/';
		return $page.url.pathname.startsWith(href);
	}

	let connected = $state(true);
</script>

<!-- Mobile: Sheet from left -->
{#if open}
	<SheetRoot bind:open={open}>
		<SheetContent side="left" class="w-[220px] p-0 bg-card border-border">
			<div class="flex flex-col h-full">
				<nav class="p-3 space-y-0.5 flex-1">
					<p class="px-3 pb-2 pt-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
						Core Workflow
					</p>
					{#each primaryNavItems as item (item.href)}
						<a
							href={item.href}
							class={cn(
								'flex items-center space-x-3 px-3 py-2.5 text-sm font-medium transition-all duration-200 ease-out border-l-2',
								isActive(item.href)
									? 'bg-football-green/5 text-football-green border-football-green'
									: 'text-muted-foreground border-transparent hover:bg-muted hover:text-foreground'
							)}
							aria-current={isActive(item.href) ? 'page' : undefined}
							onclick={() => (open = false)}
						>
							<item.icon class="w-5 h-5 flex-shrink-0" />
							<span>{item.label}</span>
						</a>
					{/each}

					<p class="px-3 pb-2 pt-5 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
						Explore
					</p>
					{#each secondaryNavItems as item (item.href)}
						<a
							href={item.href}
							class={cn(
								'flex items-center space-x-3 px-3 py-2.5 text-sm font-medium transition-all duration-200 ease-out border-l-2',
								isActive(item.href)
									? 'bg-football-green/5 text-football-green border-football-green'
									: 'text-muted-foreground border-transparent hover:bg-muted hover:text-foreground'
							)}
							aria-current={isActive(item.href) ? 'page' : undefined}
							onclick={() => (open = false)}
						>
							<item.icon class="w-5 h-5 flex-shrink-0" />
							<span>{item.label}</span>
						</a>
					{/each}
				</nav>

			<div class="border-t border-border p-3 bg-card">
				<div class="flex items-center justify-between">
					<div class="flex items-center space-x-2">
						<div class="w-2 h-2  animate-pulse {connected ? 'bg-football-green' : 'bg-destructive'}"></div>
						<span class="text-xs text-muted-foreground">
							{connected ? 'Connected' : 'Disconnected'}
						</span>
					</div>
					<div class="flex items-center space-x-2">
						<ThemeToggle />
						<span class="text-xs font-mono text-muted-foreground">Betfront v1.0.0</span>
					</div>
				</div>
				<div class="mt-2 flex items-center space-x-2 text-muted-foreground">
					<Info class="w-3 h-3" />
					<span class="text-xs text-muted-foreground">
						{user?.name ?? 'Offline'}
					</span>
				</div>
			</div>
			</div>
		</SheetContent>
	</SheetRoot>
{/if}

<!-- Desktop: fixed sidebar -->
<aside
	class="hidden lg:block fixed top-16 left-0 z-30 w-[220px] h-[calc(100vh-64px)] border-r border-border bg-card/80 backdrop-blur-xl overflow-y-auto scroll-thin"
>
	<nav class="p-3 space-y-0.5">
		<p class="px-3 pb-2 pt-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
			Core Workflow
		</p>
		{#each primaryNavItems as item (item.href)}
			<a
				href={item.href}
				class={cn(
					'flex items-center space-x-3 px-3 py-2.5 text-sm font-medium transition-all duration-200 ease-out border-l-2',
					isActive(item.href)
						? 'bg-football-green/5 text-football-green border-football-green'
						: 'text-muted-foreground border-transparent hover:bg-muted hover:text-foreground'
				)}
				aria-current={isActive(item.href) ? 'page' : undefined}
			>
				<item.icon class="w-5 h-5 flex-shrink-0" />
				<span>{item.label}</span>
			</a>
		{/each}

		<p class="px-3 pb-2 pt-5 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
			Explore
		</p>
		{#each secondaryNavItems as item (item.href)}
			<a
				href={item.href}
				class={cn(
					'flex items-center space-x-3 px-3 py-2.5 text-sm font-medium transition-all duration-200 ease-out border-l-2',
					isActive(item.href)
						? 'bg-football-green/5 text-football-green border-football-green'
						: 'text-muted-foreground border-transparent hover:bg-muted hover:text-foreground'
				)}
				aria-current={isActive(item.href) ? 'page' : undefined}
			>
				<item.icon class="w-5 h-5 flex-shrink-0" />
				<span>{item.label}</span>
			</a>
		{/each}
	</nav>

	<div class="absolute bottom-0 left-0 right-0 border-t border-border p-3 bg-card">
		<div class="flex items-center justify-between">
			<div class="flex items-center space-x-2">
				<div class="w-2 h-2  animate-pulse {connected ? 'bg-football-green' : 'bg-destructive'}"></div>
				<span class="text-xs text-muted-foreground">
					{connected ? 'Connected' : 'Disconnected'}
				</span>
			</div>
			<div class="flex items-center space-x-2">
				<ThemeToggle />
				<span class="text-xs font-mono text-muted-foreground">Betfront v1.0.0</span>
			</div>
		</div>
		<div class="mt-2 flex items-center space-x-2 text-muted-foreground">
			<Info class="w-3 h-3" />
			<span class="text-xs text-muted-foreground">
				{user?.name ?? 'Offline'}
			</span>
		</div>
	</div>
</aside>

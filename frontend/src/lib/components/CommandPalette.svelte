<script lang="ts">
	import {
		Home,
		Brain,
		Ticket,
		Database,
		Download,
		LayoutDashboard,
		User,
		Search,
		Zap,
		Plus,
		Eye
	} from 'lucide-svelte';
	import { goto } from '$app/navigation';
	import { cn } from '$lib/utils';

	interface CommandItem {
		id: string;
		label: string;
		icon: typeof Home;
		shortcut?: string;
		group: 'primary' | 'secondary' | 'match' | 'action';
		action: () => void;
	}

	const pages: CommandItem[] = [
		{
			id: 'dashboard',
			label: 'Dashboard',
			icon: Home,
			shortcut: 'H',
			group: 'primary',
			action: () => goto('/')
		},
		{
			id: 'scrape',
			label: 'Scrape',
			icon: Download,
			shortcut: 'S',
			group: 'primary',
			action: () => goto('/scrape')
		},
		{
			id: 'predict',
			label: 'Predict',
			icon: Brain,
			shortcut: 'P',
			group: 'primary',
			action: () => goto('/predict')
		},
		{
			id: 'tickets',
			label: 'Tickets',
			icon: Ticket,
			shortcut: 'T',
			group: 'primary',
			action: () => goto('/tickets')
		},
		{
			id: 'account',
			label: 'Account',
			icon: User,
			shortcut: 'A',
			group: 'primary',
			action: () => goto('/account')
		},
		{
			id: 'data',
			label: 'Data',
			icon: Database,
			shortcut: 'D',
			group: 'secondary',
			action: () => goto('/data')
		},
		{
			id: 'board',
			label: 'Board',
			icon: LayoutDashboard,
			shortcut: 'B',
			group: 'secondary',
			action: () => goto('/board')
		},
		{
			id: 'live',
			label: 'Live',
			icon: Eye,
			shortcut: 'L',
			group: 'secondary',
			action: () => goto('/live')
		},
		{
			id: 'value-bets',
			label: 'Value Bets',
			icon: Zap,
			group: 'secondary',
			action: () => goto('/value-bets')
		}
	];

	const actions: CommandItem[] = [
		{
			id: 'run-prediction',
			label: 'Run Prediction',
			icon: Zap,
			group: 'action',
			action: () => goto('/predict')
		},
		{
			id: 'place-bet',
			label: 'Place Bet',
			icon: Plus,
			group: 'action',
			action: () => goto('/tickets')
		},
		{
			id: 'view-live',
			label: 'Check Live Markets',
			icon: Eye,
			group: 'action',
			action: () => goto('/live')
		}
	];

	let {
		matches = [],
		open = $bindable(false)
	}: {
		matches?: { id: number; home_team: string; away_team: string }[];
		open?: boolean;
	} = $props();

	let query = $state('');
	let selectedIndex = $state(0);
	let inputRef = $state<HTMLInputElement | null>(null);

	const allItems = $derived.by(() => {
		const matchItems: CommandItem[] = matches.map((m) => ({
			id: `match-${m.id}`,
			label: `${m.home_team} vs ${m.away_team}`,
			icon: Search,
			group: 'match',
			action: () => goto(`/matches/${m.id}`)
		}));
		return [...pages, ...matchItems, ...actions];
	});

	const filtered = $derived(
		query.trim() === ''
			? allItems
			: allItems.filter(
				(item) =>
					item.label.toLowerCase().includes(query.toLowerCase()) ||
					item.group.toLowerCase().includes(query.toLowerCase())
			)
	);

	const sectionMeta: Record<CommandItem['group'], string> = {
		primary: 'Core Workflow',
		action: 'Actions',
		secondary: 'Explore',
		match: 'Matches'
	};

	const sectionOrder: CommandItem['group'][] = ['primary', 'action', 'secondary', 'match'];

	const filteredSections = $derived.by(() =>
		sectionOrder
			.map((group) => ({
				group,
				label: sectionMeta[group],
				items: filtered
					.map((item, index) => ({ item, index }))
					.filter((entry) => entry.item.group === group)
			}))
			.filter((section) => section.items.length > 0)
	);

	$effect(() => {
		selectedIndex = 0;
	});

	function handleKeydown(e: KeyboardEvent) {
		if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
			e.preventDefault();
			open = !open;
			return;
		}
		if (!open) return;

		if (e.key === 'Escape') {
			e.preventDefault();
			open = false;
			return;
		}

		if (e.key === 'ArrowDown') {
			e.preventDefault();
			selectedIndex = (selectedIndex + 1) % filtered.length;
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			selectedIndex = (selectedIndex - 1 + filtered.length) % filtered.length;
		} else if (e.key === 'Enter') {
			e.preventDefault();
			const item = filtered[selectedIndex];
			if (item) {
				item.action();
				open = false;
			}
		}
	}

	function executeItem(item: CommandItem) {
		item.action();
		open = false;
	}

	$effect(() => {
		if (open) {
			const t = setTimeout(() => inputRef?.focus(), 50);
			return () => clearTimeout(t);
		}
	});
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
	<div
		role="button"
		aria-label="Close command palette"
		tabindex="-1"
		onkeydown={(e) => {
			if (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				open = false;
			}
		}}
		class="fixed inset-0 z-[60] flex items-start justify-center pt-[15vh] bg-background/95 backdrop-blur-sm"
		onclick={(e) => {
			if (e.target === e.currentTarget) open = false;
		}}
	>
		<div class="w-full max-w-xl overflow-hidden  border border-border bg-card shadow-2xl">
			<!-- Search input -->
			<div class="flex items-center gap-3 px-4 py-3 border-b border-border">
				<Search class="w-5 h-5 text-muted-foreground" />
				<input
					bind:this={inputRef}
					type="text"
					placeholder="Search pages, matches, actions..."
					class="flex-1 bg-transparent text-sm outline-none text-foreground placeholder:text-muted-foreground"
					bind:value={query}
				/>
				<span class="text-[10px] font-mono px-1.5 py-0.5 border border-border text-muted-foreground">
					ESC
				</span>
			</div>

			<!-- Results -->
			<div class="max-h-[50vh] overflow-y-auto">
				{#if filtered.length === 0}
					<div class="flex flex-col items-center justify-center py-12 gap-2">
						<Search class="w-8 h-8 text-muted-foreground opacity-40" />
						<p class="text-sm text-muted-foreground">No results found</p>
						<p class="text-xs text-muted-foreground opacity-60">
							Try a different search term
						</p>
					</div>
				{:else}
					{#each filteredSections as section (section.group)}
						<div class="border-b border-border/60 last:border-b-0">
							<div class="px-4 py-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
								{section.label}
							</div>
							{#each section.items as entry (entry.item.id)}
								{@const item = entry.item}
								{@const isSelected = entry.index === selectedIndex}
								{@const Icon = item.icon}
								<button
									class={cn(
										'flex items-center justify-between w-full px-4 py-3 text-left transition-colors duration-200',
										isSelected
											? 'bg-football-green/8 text-football-green'
											: 'text-foreground hover:bg-muted'
									)}
									onmouseenter={() => (selectedIndex = entry.index)}
									onclick={() => executeItem(item)}
								>
									<div class="flex items-center gap-3">
										<Icon
											class={cn(
												'w-4 h-4',
												isSelected ? 'text-football-green' : 'text-muted-foreground'
											)}
										/>
										<span class="text-sm">{item.label}</span>
										<span class="text-[10px] font-mono px-1 py-0.5 border border-border text-muted-foreground uppercase">
											{item.group}
										</span>
									</div>
									{#if item.shortcut}
										<span class="text-[10px] font-mono px-1.5 py-0.5 border border-border text-muted-foreground">
											{item.shortcut}
										</span>
									{/if}
								</button>
							{/each}
						</div>
					{/each}
				{/if}
			</div>

			<!-- Footer hint -->
			<div class="flex items-center gap-4 px-4 py-2 text-[10px] border-t border-border text-muted-foreground opacity-60 font-mono">
				<span>&#8593;&#8595; navigate</span>
				<span>&#8629; select</span>
				<span>esc close</span>
			</div>
		</div>
	</div>
{/if}

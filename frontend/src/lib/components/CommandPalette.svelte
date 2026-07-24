<script lang="ts">
	import {
		Home,
		Brain,
		Ticket,
		Database,
		Download,
		User,
		Search,
		Zap,
		Plus,
		Eye,
		Settings,
		Globe2
	} from 'lucide-svelte';
	import { goto } from '$app/navigation';
	import { cn } from '$lib/utils';
	import { onMount } from 'svelte';

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
			label: 'Home',
			icon: Home,
			shortcut: 'H',
			group: 'primary',
			action: () => goto('/')
		},
		{
			id: 'scrape',
			label: 'Prepare data',
			icon: Download,
			shortcut: 'S',
			group: 'primary',
			action: () => goto('/prepare')
		},
		{
			id: 'predict',
			label: 'Analyze',
			icon: Brain,
			shortcut: 'P',
			group: 'primary',
			action: () => goto('/analyze')
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
			label: 'Account settings',
			icon: User,
			shortcut: 'A',
			group: 'primary',
			action: () => goto('/settings/account')
		},
		{
			id: 'data',
			label: 'Data explorer',
			icon: Database,
			shortcut: 'D',
			group: 'secondary',
			action: () => goto('/prepare/data')
		},
		{
			id: 'configuratii',
			label: 'Strategies',
			icon: Settings,
			shortcut: 'C',
			group: 'secondary',
			action: () => goto('/settings/strategies')
		},
		{
			id: 'countries-leagues',
			label: 'Listare țări/ligi',
			icon: Globe2,
			group: 'secondary',
			action: () => goto('/settings/countries-leagues')
		},
		{
			id: 'live',
			label: 'Live opportunities',
			icon: Eye,
			shortcut: 'L',
			group: 'secondary',
			action: () => goto('/opportunities?view=live')
		},
		{
			id: 'value-bets',
			label: 'Value opportunities',
			icon: Zap,
			group: 'secondary',
			action: () => goto('/opportunities?view=value')
		}
	];

	const actions: CommandItem[] = [
		{
			id: 'run-prediction',
			label: 'Run analysis',
			icon: Zap,
			group: 'action',
			action: () => goto('/analyze')
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
			label: 'Check live opportunities',
			icon: Eye,
			group: 'action',
			action: () => goto('/opportunities?view=live')
		}
	];

	let {
		matches = [],
		onClose
	}: {
		matches?: { id: number; home_team: string; away_team: string }[];
		onClose: () => void;
	} = $props();

	let query = $state('');
	let selectedIndex = $state(0);
	let inputRef = $state<HTMLInputElement | null>(null);
	let dialogRef = $state<HTMLDivElement | null>(null);

	const allItems = $derived.by(() => {
		const matchItems: CommandItem[] = matches.map((m) => ({
			id: `match-${m.id}`,
			label: `${m.home_team} vs ${m.away_team}`,
			icon: Search,
			group: 'match',
			action: () => goto(`/matches/${m.id}`)
		}));
		return [
			...pages.filter((item) => item.group === 'primary'),
			...actions,
			...pages.filter((item) => item.group === 'secondary'),
			...matchItems
		];
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
		primary: 'Workspace',
		action: 'Actions',
		secondary: 'Tools',
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

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Tab') {
			const focusable = Array.from(
				dialogRef?.querySelectorAll<HTMLElement>(
					'input, button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
				) ?? []
			);
			if (focusable.length === 0) return;
			const first = focusable[0];
			const last = focusable.at(-1);
			if (e.shiftKey && document.activeElement === first) {
				e.preventDefault();
				last?.focus();
			} else if (!e.shiftKey && document.activeElement === last) {
				e.preventDefault();
				first.focus();
			}
			return;
		}

		if (e.key === 'Escape') {
			e.preventDefault();
			onClose();
			return;
		}

		if (e.key === 'ArrowDown') {
			e.preventDefault();
			selectedIndex = (selectedIndex + 1) % filtered.length;
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			selectedIndex = (selectedIndex - 1 + filtered.length) % filtered.length;
		} else if (e.key === 'Enter') {
			if (document.activeElement instanceof HTMLButtonElement && dialogRef?.contains(document.activeElement)) {
				return;
			}
			e.preventDefault();
			const item = filtered[selectedIndex];
			if (item) {
				item.action();
				onClose();
			}
		}
	}

	function executeItem(item: CommandItem) {
		item.action();
		onClose();
	}

	onMount(() => {
		const previouslyFocused =
			document.activeElement instanceof HTMLElement ? document.activeElement : null;
		const focusTimer = setTimeout(() => inputRef?.focus(), 50);
		return () => {
			clearTimeout(focusTimer);
			previouslyFocused?.focus();
		};
	});
</script>

<svelte:window onkeydown={handleKeydown} />

	<div class="fixed inset-0 z-[60] flex items-start justify-center pt-[15vh]">
		<button
			type="button"
			class="absolute inset-0 bg-background/95 backdrop-blur-sm"
			onclick={onClose}
			aria-label="Close command palette"
		></button>
		<div
			bind:this={dialogRef}
			role="dialog"
			aria-modal="true"
			aria-label="Navigare rapidă"
			class="relative w-full max-w-xl overflow-hidden border border-border bg-card shadow-2xl"
		>
			<!-- Search input -->
			<div class="flex items-center gap-3 px-4 py-3 border-b border-border">
				<Search class="w-5 h-5 text-muted-foreground" />
				<input
					bind:this={inputRef}
					type="text"
					aria-label="Caută pagini, meciuri și acțiuni"
					placeholder="Search pages, matches, actions..."
					class="flex-1 bg-transparent text-sm outline-none text-foreground placeholder:text-muted-foreground"
					value={query}
					oninput={(event) => {
						query = event.currentTarget.value;
						selectedIndex = 0;
					}}
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
									onfocus={() => (selectedIndex = entry.index)}
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

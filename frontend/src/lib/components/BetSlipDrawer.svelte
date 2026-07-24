<script lang="ts">
	import { goto } from '$app/navigation';
	import { ShoppingCart, X } from 'lucide-svelte';
	import { onMount } from 'svelte';
	import { betslip, betslipCombinedOdds, betslipPotentialReturn } from '$lib/stores/betslip';
	import Badge from './ui/Badge.svelte';
	import Button from './ui/Button.svelte';

	let {
		closeBetslip
	}: {
		closeBetslip: () => void;
	} = $props();

	let dialog = $state<HTMLDivElement | null>(null);
	let closeButton = $state<HTMLButtonElement | null>(null);

	const quickStakes = [5, 10, 25, 50, 100];

	async function reviewTicket() {
		closeBetslip();
		await goto('/tickets');
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.preventDefault();
			closeBetslip();
			return;
		}

		if (event.key !== 'Tab') return;
		const focusable = Array.from(
			dialog?.querySelectorAll<HTMLElement>(
				'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
			) ?? []
		);
		if (focusable.length === 0) return;
		const first = focusable[0];
		const last = focusable.at(-1);
		if (event.shiftKey && document.activeElement === first) {
			event.preventDefault();
			last?.focus();
		} else if (!event.shiftKey && document.activeElement === last) {
			event.preventDefault();
			first.focus();
		}
	}

	onMount(() => {
		const previousOverflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		closeButton?.focus();
		return () => {
			document.body.style.overflow = previousOverflow;
		};
	});
</script>

<svelte:window onkeydown={handleKeydown} />

<div
	bind:this={dialog}
	role="dialog"
	aria-modal="true"
	aria-labelledby="betslip-dialog-title"
	class="flex flex-col bg-card"
>
	<div class="flex items-center justify-between px-4 py-3 border-b border-border">
		<div class="flex items-center gap-2">
			<ShoppingCart class="w-4 h-4 text-football-green" />
			<span id="betslip-dialog-title" class="text-xs font-bold tracking-widest font-sport text-foreground">SLIP DE PARIURI</span>
			{#if $betslip.legs.length > 0}
				<Badge variant="success">{$betslip.legs.length}</Badge>
			{/if}
		</div>
			<button bind:this={closeButton} type="button" class="touch-target inline-flex min-h-11 min-w-11 items-center justify-center p-1 text-muted-foreground hover:bg-muted hover:text-foreground" onclick={closeBetslip} aria-label="Închide slipul de pariuri">
				<X class="w-5 h-5 text-muted-foreground" />
			</button>
	</div>

	<div class="flex-1 overflow-y-auto scroll-thin">
		{#if $betslip.legs.length === 0}
			<div class="flex flex-col items-center justify-center py-16 gap-3">
				<ShoppingCart class="w-10 h-10 text-muted-foreground opacity-30" />
				<p class="text-sm text-muted-foreground">Selectează cote pentru a adăuga pariuri</p>
				<p class="text-xs text-muted-foreground">Folosește Dashboard, Predicții, Live sau Value Bets</p>
			</div>
		{:else}
			<div class="p-3 space-y-2">
				{#each $betslip.legs as leg (leg.id)}
					<div class="border border-border bg-background p-3">
						<div class="mb-2 flex items-start justify-between gap-2">
							<div class="min-w-0 flex-1">
								<p class="truncate text-xs font-medium text-foreground">{leg.matchName}</p>
								<div class="mt-1 flex flex-wrap items-center gap-2">
									<Badge variant="neutral" class="text-[10px] px-1.5 py-0.5 font-mono">{leg.market}</Badge>
									<Badge variant="success" class="text-[10px] px-1.5 py-0.5 font-mono">{leg.selection}</Badge>
									<span class="text-sm font-mono font-semibold text-football-blue">{leg.odds.toFixed(2)}</span>
								</div>
							</div>
							<Button variant="ghost" size="sm" class="min-h-11 min-w-11 p-1" onclick={() => betslip.removeLeg(leg.id)} aria-label="Elimină selecția">
								<X class="w-4 h-4 text-muted-foreground" />
							</Button>
						</div>
						<div class="flex items-center justify-between text-[11px] text-muted-foreground">
							<span>{leg.league ?? 'Selecție'}</span>
							<span>{leg.kickoff ? new Date(leg.kickoff).toLocaleString('ro-RO') : 'Start necunoscut'}</span>
						</div>
					</div>
				{/each}
			</div>

			<div class="px-3 pb-2">
				<div class="flex items-center gap-1.5">
					{#each quickStakes as amount (amount)}
						<button
							class="min-h-11 flex-1 border border-border py-2 text-xs font-mono text-foreground transition-colors duration-200 hover:border-football-green"
							onclick={() => betslip.setStake(amount)}
						>
							£{amount}
						</button>
					{/each}
				</div>
			</div>

			<div class="px-3 py-2">
				<div class="flex items-center justify-between border border-border bg-background p-2">
					<span class="text-xs text-muted-foreground">Multiplu</span>
					<button
						class="relative h-7 w-12 transition-colors duration-200"
						style="background: {$betslip.ticketType === 'accumulator' ? 'hsl(var(--football-green))' : 'hsl(var(--border))'};"
						onclick={() => betslip.setTicketType($betslip.ticketType === 'accumulator' ? 'single' : 'accumulator')}
						aria-label="Comută bilet multiplu"
					>
						<div
							class="absolute top-1 h-5 w-5 bg-card transition-all duration-200"
							style="left: {$betslip.ticketType === 'accumulator' ? '26px' : '2px'};"
						></div>
					</button>
				</div>
			</div>

			<div class="px-3 pb-2">
				<label for="betslip-stake" class="mb-2 block text-xs text-muted-foreground">Miză</label>
				<input
					id="betslip-stake"
					type="number"
					min="0"
					step="0.01"
					value={$betslip.stake || ''}
					placeholder="0.00"
					class="w-full border border-border bg-transparent px-3 py-2 font-mono text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
					oninput={(e) => betslip.setStake(parseFloat(e.currentTarget.value) || 0)}
				/>
			</div>

			<div class="mx-3 space-y-2 border border-border bg-background p-3">
				<div class="flex items-center justify-between">
					<span class="text-xs text-muted-foreground">Miză</span>
					<span class="text-sm font-mono font-semibold text-foreground">£{$betslip.stake.toFixed(2)}</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-xs text-muted-foreground">Cotă totală</span>
					<span class="text-sm font-mono font-semibold text-foreground">x{$betslipCombinedOdds.toFixed(2)}</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-xs text-muted-foreground">Retur potențial</span>
					<span class="text-sm font-mono font-bold text-football-green">£{$betslipPotentialReturn.toFixed(2)}</span>
				</div>
			</div>
		{/if}
	</div>

	{#if $betslip.legs.length > 0}
		<div class="border-t border-border p-3">
			<Button
				class="w-full bg-football-green py-3 text-sm font-bold tracking-wider text-primary-foreground hover:bg-football-green/90"
				onclick={reviewTicket}
				aria-label="Revizuiește biletul"
			>
				REVIZUIEȘTE BILETUL
			</Button>
		</div>
	{/if}
</div>

<style>
	input[type='number']::-webkit-inner-spin-button,
	input[type='number']::-webkit-outer-spin-button {
		-webkit-appearance: none;
		margin: 0;
	}
	input::placeholder {
		color: hsl(var(--muted-foreground));
		opacity: 0.4;
	}
</style>

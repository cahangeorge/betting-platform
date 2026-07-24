<script lang="ts">
	import { ShoppingCart } from 'lucide-svelte';
	import { cn } from '$lib/utils';
	import { betslipCount } from '$lib/stores/betslip';

	let {
		onclick
	}: {
		onclick?: (event: MouseEvent) => void;
	} = $props();
</script>

<button
	class={cn(
		'bottom-[calc(var(--mobile-nav-height)+var(--mobile-floating-gap)+5.5rem)] touch-target fixed right-4 z-40 flex h-14 w-14 items-center justify-center shadow-lg lg:bottom-6 lg:right-6 lg:h-12 lg:w-auto lg:gap-2 lg:px-4',
		'bg-football-green text-primary-foreground',
		'active:scale-95 transition-transform duration-150',
		'backdrop-blur-xl border border-football-green/30'
	)}
	onclick={onclick}
	aria-label="Revizuiește biletul"
>
	<ShoppingCart class="w-6 h-6" />
		<span class="hidden text-sm font-semibold lg:inline">Revizuiește biletul</span>
	{#if $betslipCount > 0}
		<span
			class="absolute -top-1 -right-1 flex items-center justify-center w-5 h-5 text-[10px] font-bold bg-destructive text-destructive-foreground"
		>
			{$betslipCount > 99 ? '99+' : $betslipCount}
		</span>
	{/if}
</button>

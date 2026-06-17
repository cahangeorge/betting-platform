<script lang="ts">
	import { ShoppingCart } from 'lucide-svelte';
	import { cn } from '$lib/utils';
	import { betslipCount } from '$lib/stores/betslip';

	let {
		onclick
	}: {
		onclick?: () => void;
	} = $props();
</script>

<button
	class={cn(
		'fixed z-40 lg:hidden flex items-center justify-center',
		'w-14 h-14 shadow-lg',
		'bg-football-green text-primary-foreground',
		'active:scale-95 transition-transform duration-150',
		'backdrop-blur-xl border border-football-green/30'
	)}
	style="bottom: calc(80px + env(safe-area-inset-bottom, 0px)); right: 16px;"
	onclick={onclick}
	aria-label="Open bet slip"
>
	<ShoppingCart class="w-6 h-6" />
	{#if $betslipCount > 0}
		<span
			class="absolute -top-1 -right-1 flex items-center justify-center w-5 h-5 text-[10px] font-bold bg-destructive text-destructive-foreground"
		>
			{$betslipCount > 99 ? '99+' : $betslipCount}
		</span>
	{/if}
</button>

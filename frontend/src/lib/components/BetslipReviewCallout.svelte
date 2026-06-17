<script lang="ts">
	import { goto } from '$app/navigation';
	import { betslipCount, betslipCombinedOdds, betslipPotentialReturn } from '$lib/stores/betslip';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	let {
		label = 'Selections ready'
	}: {
		label?: string;
	} = $props();

	async function reviewSlip() {
		await goto('/tickets');
	}
</script>

{#if $betslipCount > 0}
	<div class="border border-football-green/30 bg-football-green/8 px-4 py-3">
		<div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
			<div class="flex items-start gap-3">
				<Badge variant="success">{$betslipCount} in slip</Badge>
				<div class="space-y-1">
					<p class="text-sm font-semibold text-foreground">{label}</p>
					<p class="text-xs text-muted-foreground">
						Combined odds x{$betslipCombinedOdds.toFixed(2)} · Potential return
						£{$betslipPotentialReturn.toFixed(2)}
					</p>
				</div>
			</div>
			<Button variant="primary" onclick={reviewSlip}>Review Ticket</Button>
		</div>
	</div>
{/if}

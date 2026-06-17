<script lang="ts">
	import type { Snippet } from 'svelte';
	import ShadcnSelect from './select/select.svelte';

	let {
		value = $bindable(),
		label,
		options,
		placeholder = 'Select...',
		disabled = false,
		name,
		onchange
	}: {
		value: string;
		label?: string;
		options: { value: string; label: string }[];
		placeholder?: string;
		disabled?: boolean;
		name?: string;
		onchange?: (e: Event) => void;
	} = $props();
</script>

<div class="space-y-1.5">
	{#if label}
		<label for={name} class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
			{label}
		</label>
	{/if}
	<ShadcnSelect {name} {disabled} bind:value onchange={onchange}>
		<option value="" disabled>{placeholder}</option>
		{#each options as opt (opt.value)}
			<option value={opt.value}>{opt.label}</option>
		{/each}
	</ShadcnSelect>
</div>

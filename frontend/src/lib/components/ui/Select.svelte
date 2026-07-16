<script lang="ts">
	import type { HTMLSelectAttributes } from 'svelte/elements';
	import ShadcnSelect from './select/select.svelte';

	const generatedId = $props.id();

	let {
		value = $bindable(),
		label,
		id,
		options,
		placeholder = 'Select...',
		disabled = false,
		name,
		onchange,
		...rest
	}: {
		value: string;
		label?: string;
		id?: string;
		options: { value: string; label: string }[];
		placeholder?: string;
		disabled?: boolean;
		name?: string;
		onchange?: (e: Event) => void;
	} & Omit<HTMLSelectAttributes, 'id' | 'value' | 'disabled' | 'name' | 'onchange'> = $props();

	let selectId = $derived(id ?? name ?? `${generatedId}-select`);
</script>

<div class="space-y-1.5">
	{#if label}
		<label for={selectId} class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
			{label}
		</label>
	{/if}
	<ShadcnSelect id={selectId} {name} {disabled} bind:value onchange={onchange} {...rest}>
		<option value="" disabled>{placeholder}</option>
		{#each options as opt (opt.value)}
			<option value={opt.value}>{opt.label}</option>
		{/each}
	</ShadcnSelect>
</div>

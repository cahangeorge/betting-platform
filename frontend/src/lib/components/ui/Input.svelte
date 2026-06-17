<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';
	import ShadcnInput from './input/input.svelte';

	let {
		value = $bindable(),
		label,
		type = 'text',
		placeholder = '',
		error,
		disabled = false,
		name,
		class: className,
		...rest
	}: {
		value: string;
		label?: string;
		type?: string;
		placeholder?: string;
		error?: string;
		disabled?: boolean;
		name?: string;
		class?: string;
	} & Omit<HTMLInputAttributes, 'type' | 'value' | 'placeholder' | 'disabled' | 'name' | 'class'> = $props();

	let inputClasses = $derived(
		cn(error ? 'border-destructive focus-visible:ring-destructive' : '', className)
	);
</script>

<div class="space-y-1.5">
	{#if label}
		<label for={name} class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
			{label}
		</label>
	{/if}
	<ShadcnInput
		{type}
		{name}
		{placeholder}
		{disabled}
		bind:value
		class={inputClasses}
		{...rest}
	/>
	{#if error}
		<p class="text-sm font-medium text-destructive">{error}</p>
	{/if}
</div>

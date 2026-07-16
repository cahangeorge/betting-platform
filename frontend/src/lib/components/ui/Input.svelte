<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';
	import ShadcnInput from './input/input.svelte';

	const generatedId = $props.id();

	let {
		value = $bindable(),
		label,
		id,
		type = 'text',
		placeholder = '',
		error,
		disabled = false,
		name,
		class: className,
		'aria-describedby': ariaDescribedBy,
		'aria-invalid': ariaInvalid,
		...rest
	}: {
		value: string;
		label?: string;
		id?: string;
		type?: string;
		placeholder?: string;
		error?: string;
		disabled?: boolean;
		name?: string;
		class?: string;
	} & Omit<HTMLInputAttributes, 'type' | 'value' | 'placeholder' | 'disabled' | 'name' | 'class'> = $props();

	let inputClasses = $derived(
		cn(
			error
				? 'border-[hsl(var(--status-danger-border))] focus-visible:ring-[hsl(var(--status-danger-border))]'
				: '',
			className
		)
	);

	let inputId = $derived(id ?? name ?? `${generatedId}-input`);
	let errorId = $derived(`${inputId}-error`);
	let describedBy = $derived(
		[ariaDescribedBy, error ? errorId : undefined].filter(Boolean).join(' ') || undefined
	);
</script>

<div class="space-y-1.5">
	{#if label}
		<label for={inputId} class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
			{label}
		</label>
	{/if}
	<ShadcnInput
		id={inputId}
		{type}
		{name}
		{placeholder}
		{disabled}
		bind:value
		class={inputClasses}
		{...rest}
		aria-invalid={ariaInvalid ?? (error ? true : undefined)}
		aria-describedby={describedBy}
	/>
	{#if error}
		<p id={errorId} class="text-sm font-medium text-[hsl(var(--status-danger-text))]">{error}</p>
	{/if}
</div>

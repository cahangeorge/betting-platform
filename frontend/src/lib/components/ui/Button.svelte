<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import ShadcnButton from './button/button.svelte';

	let {
		children,
		variant = 'primary',
		size = 'md',
		disabled = false,
		type = 'button',
		fullWidth = false,
		onclick,
		class: className,
		...rest
	}: {
		children: Snippet;
		variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'glow';
		size?: 'sm' | 'md' | 'lg';
		disabled?: boolean;
		type?: 'button' | 'submit' | 'reset';
		fullWidth?: boolean;
		onclick?: (e: MouseEvent) => void;
		class?: string;
	} & Omit<HTMLButtonAttributes, 'type' | 'disabled' | 'onclick'> = $props();

	const variantMap: Record<string, 'default' | 'destructive' | 'secondary' | 'ghost' | 'link'> = {
		primary: 'default',
		secondary: 'secondary',
		danger: 'destructive',
		ghost: 'ghost',
		glow: 'default'
	};

	const sizeMap: Record<string, 'default' | 'sm' | 'lg'> = {
		sm: 'sm',
		md: 'default',
		lg: 'lg'
	};

	let mappedVariant = $derived(variantMap[variant] ?? 'default');
	let mappedSize = $derived(sizeMap[size] ?? 'default');

	let classes = $derived(
		[fullWidth ? 'w-full' : '', className].filter(Boolean).join(' ') || undefined
	);

	let extraClass = $derived(variant === 'glow' ? 'shadow-[0_0_20px_rgba(74,222,128,0.3)] hover:shadow-[0_0_30px_rgba(74,222,128,0.5)]' : undefined);

	let combinedClass = $derived(
		[classes, extraClass].filter(Boolean).join(' ') || undefined
	);
</script>

<ShadcnButton
	variant={mappedVariant}
	size={mappedSize}
	{disabled}
	{type}
	class={combinedClass}
	{onclick}
	{...rest}
>
	{@render children()}
</ShadcnButton>

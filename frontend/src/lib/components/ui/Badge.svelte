<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';

	let {
		children,
		variant = 'default',
		class: className,
		...rest
	}: {
		children: Snippet;
		variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'live' | 'premium' | 'profit' | 'loss' | 'neutral';
		class?: string;
	} & Omit<HTMLAttributes<HTMLDivElement>, 'class'> = $props();

	const variantClasses: Record<string, string> = {
		default: 'bg-primary text-primary-foreground',
		success: 'border-[hsl(var(--status-success-border))] bg-[hsl(var(--status-success-bg))] text-[hsl(var(--status-success-text))]',
		warning: 'border-[hsl(var(--status-warning-border))] bg-[hsl(var(--status-warning-bg))] text-[hsl(var(--status-warning-text))]',
		danger: 'border-[hsl(var(--status-danger-border))] bg-[hsl(var(--status-danger-bg))] text-[hsl(var(--status-danger-text))]',
		info: 'border-[hsl(var(--status-info-border))] bg-[hsl(var(--status-info-bg))] text-[hsl(var(--status-info-text))]',
		live: 'border-[hsl(var(--status-danger-border))] bg-[hsl(var(--status-danger-bg))] text-[hsl(var(--status-danger-text))]',
		premium: 'border-[hsl(var(--status-premium-border))] bg-[hsl(var(--status-premium-bg))] text-[hsl(var(--status-premium-text))]',
		profit: 'border-[hsl(var(--status-success-border))] bg-[hsl(var(--status-success-bg))] text-[hsl(var(--status-success-text))]',
		loss: 'border-[hsl(var(--status-danger-border))] bg-[hsl(var(--status-danger-bg))] text-[hsl(var(--status-danger-text))]',
		neutral: 'bg-secondary text-secondary-foreground'
	};

	let classes = $derived(
		cn(
			'inline-flex items-center  border px-2.5 py-0.5 text-xs font-semibold transition-colors',
			variantClasses[variant],
			className
		)
	);
</script>

<div class={classes} {...rest}>
	{@render children()}
</div>

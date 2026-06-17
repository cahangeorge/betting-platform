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
		success: 'bg-green-500/15 text-green-400 border-green-500/30',
		warning: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
		danger: 'bg-destructive text-destructive-foreground',
		info: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
		live: 'bg-red-500/15 text-red-400 border-red-500/30 animate-pulse',
		premium: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
		profit: 'bg-green-500/15 text-green-400 border-green-500/30',
		loss: 'bg-red-500/15 text-red-400 border-red-500/30',
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

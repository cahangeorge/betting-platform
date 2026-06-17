<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';
	import CardRoot from './card/card.svelte';
	import CardHeader from './card/card-header.svelte';
	import CardTitle from './card/card-title.svelte';
	import CardContent from './card/card-content.svelte';

	let {
		children,
		title,
		padded = true,
		variant = 'default',
		interactive = false,
		class: className,
		style: styleAttr,
		...rest
	}: {
		children: Snippet;
		title?: string;
		padded?: boolean;
		variant?: 'default' | 'active' | 'data' | 'prediction';
		interactive?: boolean;
		class?: string;
		style?: string;
	} & Omit<HTMLAttributes<HTMLDivElement>, 'class' | 'style'> = $props();

	const variantClasses: Record<string, string> = {
		active: 'border-t-2 border-t-football-green shadow-[0_0_40px_rgba(74,222,128,0.06)]',
		data: 'border-t-2 border-t-football-blue',
		prediction: 'border-t-2 border-t-football-gold'
	};

let interactiveClass = $derived(
	interactive
		? 'cursor-pointer transition-all duration-200 hover:shadow-lg hover:scale-[1.01] motion-safe:hover:scale-[1.01] motion-reduce:hover:scale-100'
		: ''
);

	let classes = $derived(
		cn(variantClasses[variant], interactiveClass, className)
	);
</script>

<CardRoot class={classes} style={styleAttr} {...rest}>
	{#if title}
		<CardHeader>
			<CardTitle class="text-lg">{title}</CardTitle>
		</CardHeader>
	{/if}
	<CardContent class={padded ? '' : 'p-0'}>
		{@render children()}
	</CardContent>
</CardRoot>

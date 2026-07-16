<script lang="ts">
	import { Sun, Moon } from 'lucide-svelte';
	import { onMount } from 'svelte';

	let theme = $state<'light' | 'dark'>('dark');

	onMount(() => {
		const stored = localStorage.getItem('theme');
		if (stored === 'light' || stored === 'dark') {
			theme = stored;
		} else {
			theme = 'dark';
		}
		document.documentElement.classList.toggle('dark', theme === 'dark');
		document.documentElement.classList.toggle('light', theme === 'light');
	});

	function toggle() {
		theme = theme === 'dark' ? 'light' : 'dark';
		localStorage.setItem('theme', theme);
		document.documentElement.classList.toggle('dark', theme === 'dark');
		document.documentElement.classList.toggle('light', theme === 'light');
	}
</script>

<button
	onclick={toggle}
	class="touch-target inline-flex h-9 w-9 cursor-pointer items-center justify-center border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
	aria-label={theme === 'dark' ? 'Activează tema luminoasă' : 'Activează tema întunecată'}
	title={theme === 'dark' ? 'Temă luminoasă' : 'Temă întunecată'}
>
	{#if theme === 'dark'}
		<Sun class="h-5 w-5" />
	{:else}
		<Moon class="h-5 w-5" />
	{/if}
</button>

<script lang="ts">
	import Card from '$lib/components/ui/Card.svelte';

	const techStack = [
		{ name: 'SvelteKit 2', description: 'Full-stack framework' },
		{ name: 'Svelte 5', description: 'UI framework with runes' },
		{ name: 'Tailwind CSS v4', description: 'Utility-first styling' },
		{ name: 'FastAPI', description: 'Python API layer' },
		{ name: 'SQLAlchemy', description: 'Async ORM and query layer' },
		{ name: 'PostgreSQL', description: 'Primary application database' }
	];
</script>

<div class="max-w-3xl mx-auto space-y-8">
	<div class="text-center py-8">
		<div class="w-20 h-20 flex items-center justify-center mx-auto mb-4 bg-muted border border-football-green">
			<span class="text-3xl font-extrabold text-football-green font-sport">SI</span>
		</div>
		<h1 class="text-3xl font-extrabold font-sport text-foreground">Betfront</h1>
		<p class="mt-2 text-muted-foreground">Sports Betting Analytics Platform</p>
	</div>

	<Card title="About">
		<div class="space-y-4 text-sm text-muted-foreground">
			<p>
				Betfront is a comprehensive sports betting intelligence platform that combines real-time odds data,
				AI-powered prediction models, and portfolio tracking tools for data-driven sports bettors.
			</p>
			<p>
				Built with modern web technologies and a Python FastAPI backend, the platform provides
				live odds comparison across multiple bookmakers, statistical prediction models
				(Poisson, Bivariate Poisson, Elo, XGBoost), and full portfolio management with
				bankrolls and betting history.
			</p>
		</div>
	</Card>

	<Card title="Tech Stack">
		<div class="grid grid-cols-2 md:grid-cols-3 gap-4">
			{#each techStack as tech (tech.name)}
				<div class="p-3 bg-background border border-border">
					<h4 class="font-medium text-foreground">{tech.name}</h4>
					<p class="text-xs mt-1 text-muted-foreground/60">{tech.description}</p>
				</div>
			{/each}
		</div>
	</Card>

	<Card title="Version">
		<div class="space-y-2 text-sm">
			<div class="flex justify-between">
				<span class="text-muted-foreground/60">Platform</span>
				<span class="font-mono text-foreground">0.1.0</span>
			</div>
			<div class="flex justify-between">
				<span class="text-muted-foreground/60">API</span>
				<span class="font-mono text-foreground">0.1.0</span>
			</div>
			<div class="flex justify-between">
				<span class="text-muted-foreground/60">Frontend</span>
				<span class="font-mono text-foreground">SvelteKit 2 + Svelte 5</span>
			</div>
			<div class="flex justify-between">
				<span class="text-muted-foreground/60">Backend</span>
				<span class="font-mono text-foreground">FastAPI + PostgreSQL via /api proxy</span>
			</div>
		</div>
	</Card>

	<div class="text-center pb-8">
		<a
			href="https://github.com/gion/bet"
			target="_blank"
			rel="noopener noreferrer"
			class="inline-flex items-center space-x-2 text-sm transition-colors duration-200 text-muted-foreground hover:text-muted-foreground"
		>
			<svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
				<path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
			</svg>
			<span>View on GitHub</span>
		</a>
	</div>
</div>

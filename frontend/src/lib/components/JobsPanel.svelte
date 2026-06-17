<script lang="ts">
	import { jobsApi } from '$lib/api/jobs';
	import { ApiClientError } from '$lib/api/client';
	import type { ScheduledJob } from '$lib/types';
	import { onMount } from 'svelte';
	import Button from './ui/Button.svelte';
	import Card from './ui/Card.svelte';
	import Badge from './ui/Badge.svelte';
	import Loading from './Loading.svelte';

	let jobs = $state<ScheduledJob[]>([]);
	let loading = $state(true);
	let error = $state('');

	async function loadJobs() {
		loading = true;
		error = '';
		try {
			jobs = await jobsApi.getScheduledJobs();
		} catch (err) {
			error = err instanceof ApiClientError ? err.message : 'Failed to load scheduled jobs';
		} finally {
			loading = false;
		}
	}

	async function toggleJob(id: number) {
		try {
			const updated = await jobsApi.toggleJob(id);
			jobs = jobs.map((j) => (j.id === id ? updated : j));
		} catch (err) {
			error = err instanceof ApiClientError ? err.message : 'Failed to toggle job';
		}
	}

	async function deleteJob(id: number) {
		error = 'Scheduled job deletion is not supported by the backend yet';
	}

	onMount(() => {
		void loadJobs();
	});
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h2 class="text-xl font-semibold text-foreground">Scheduled Jobs</h2>
		<Button onclick={loadJobs} variant="ghost" size="sm">
			Refresh
		</Button>
	</div>

	{#if loading}
		<Loading message="Loading scheduled jobs..." />
	{:else if error}
		<div class="p-4  text-sm bg-destructive/10 border border-destructive/30 text-destructive">{error}</div>
		<Button onclick={loadJobs}>Retry</Button>
	{:else if jobs.length === 0}
		<div class="text-center py-12 text-muted-foreground">
			<p class="text-lg mb-2">No scheduled jobs</p>
			<p class="text-sm">Scheduled jobs will appear here once configured</p>
		</div>
	{:else}
		<div class="space-y-3">
			{#each jobs as job (job.id)}
				<Card>
					<div class="flex items-center justify-between">
						<div class="flex-1">
							<div class="flex items-center space-x-3">
								<h4 class="font-medium text-foreground">{job.name}</h4>
								<Badge variant={job.enabled ? 'success' : 'default'}>
									{job.enabled ? 'Enabled' : 'Disabled'}
								</Badge>
							</div>
							<div class="mt-1 flex items-center space-x-4 text-xs text-muted-foreground">
								<span>Task: {job.task_type}</span>
								<span>Cron: <code class="font-mono text-football-green">{job.cron_expression}</code></span>
							</div>
							<div class="mt-1 flex items-center space-x-4 text-xs text-muted-foreground opacity-70">
								<span>Last run: {job.last_run ? new Date(job.last_run).toLocaleString() : 'Never'}</span>
								<span>Next run: {job.next_run ? new Date(job.next_run).toLocaleString() : 'N/A'}</span>
							</div>
						</div>
						<div class="flex items-center space-x-2">
							<Button
								size="sm"
								variant={job.enabled ? 'danger' : 'primary'}
								onclick={() => toggleJob(job.id)}
							>
								{job.enabled ? 'Disable' : 'Enable'}
							</Button>
							<Button size="sm" variant="danger" onclick={() => deleteJob(job.id)}>
								Delete unavailable
							</Button>
						</div>
					</div>
				</Card>
			{/each}
		</div>
	{/if}
</div>

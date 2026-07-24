<script lang="ts">
	import { onMount } from 'svelte';
	import { Activity, BadgeCheck, DatabaseZap, RefreshCw, ShieldAlert } from 'lucide-svelte';
	import {
		modelGovernanceApi,
		type GovernanceCertification,
		type GovernanceEvaluation,
		type GovernanceEvidence,
		type GovernanceMonitoring
	} from '$lib/api/model-governance';
	import { createRequestGeneration } from '$lib/async-request';
	import Badge from './ui/Badge.svelte';
	import Button from './ui/Button.svelte';
	import Card from './ui/Card.svelte';
	import Select from './ui/Select.svelte';

	let evaluations = $state<GovernanceEvaluation[]>([]);
	let certifications = $state<GovernanceCertification[]>([]);
	let monitoring = $state<GovernanceMonitoring[]>([]);
	let evidence = $state<GovernanceEvidence | null>(null);
	let selectedModelVersionId = $state('');
	let loading = $state(true);
	let error = $state('');
	let evidenceLoading = $state(false);
	let evidenceError = $state('');
	const evidenceRequests = createRequestGeneration();

	const modelOptions = $derived.by(() => {
		const ids = [...evaluations, ...certifications, ...monitoring].map((item) => item.model_version_id);
		return ids
			.filter((id, index) => ids.indexOf(id) === index)
			.sort((a, b) => b - a)
			.map((id) => ({ value: String(id), label: `Model version #${id}` }));
	});

	function metric(metrics: Record<string, unknown> | null | undefined, key: string): string {
		const value = metrics?.[key];
		return typeof value === 'number' ? value.toFixed(4) : '—';
	}

	function statusVariant(status: string): 'success' | 'warning' | 'danger' | 'default' {
		if (['passed', 'certified', 'healthy', 'walk_forward_passed'].includes(status)) return 'success';
		if (['failed', 'critical', 'suspended', 'expired'].includes(status)) return 'danger';
		if (['warning', 'paper_collecting', 'insufficient_evidence'].includes(status)) return 'warning';
		return 'default';
	}

	async function loadEvidence(): Promise<void> {
		const requestId = evidenceRequests.next();
		const id = Number(selectedModelVersionId);
		if (!Number.isInteger(id) || id <= 0) {
			evidence = null;
			evidenceLoading = false;
			evidenceError = '';
			return;
		}
		evidence = null;
		evidenceLoading = true;
		evidenceError = '';
		try {
			const loadedEvidence = await modelGovernanceApi.getEvidence(id);
			if (!evidenceRequests.isCurrent(requestId)) return;
			evidence = loadedEvidence;
		} catch (caught) {
			if (!evidenceRequests.isCurrent(requestId)) return;
			evidenceError = caught instanceof Error
				? caught.message
				: 'Dovezile pentru versiunea selectată nu au putut fi încărcate.';
		} finally {
			if (evidenceRequests.isCurrent(requestId)) evidenceLoading = false;
		}
	}

	async function load(): Promise<void> {
		evidenceRequests.invalidate();
		evidenceLoading = false;
		evidenceError = '';
		loading = true;
		error = '';
		try {
			const [evaluationPage, certificationPage, monitoringPage] = await Promise.all([
				modelGovernanceApi.getEvaluations(),
				modelGovernanceApi.getCertifications(),
				modelGovernanceApi.getMonitoring()
			]);
			evaluations = evaluationPage.items;
			certifications = certificationPage.items;
			monitoring = monitoringPage.items;
			if (!selectedModelVersionId && modelOptions[0]) selectedModelVersionId = modelOptions[0].value;
			await loadEvidence();
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Dovezile de guvernanță nu au putut fi încărcate.';
		} finally {
			loading = false;
		}
	}

	onMount(() => void load());
</script>

<section class="space-y-6" aria-labelledby="model-governance-title">
	<div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
		<div>
				<h1 id="model-governance-title" class="text-2xl font-semibold text-foreground">Model governance</h1>
			<p class="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
				Walk-forward, certificare paper și drift sunt tratate separat. ROI-ul singur nu certifică un model.
			</p>
		</div>
		<Button variant="secondary" onclick={load} disabled={loading}>
			<RefreshCw class={`mr-2 size-4 ${loading ? 'animate-spin' : ''}`} /> Reîncarcă
		</Button>
	</div>

	{#if error}
		<div class="border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{error}</div>
	{/if}

	{#if loading}
		<div class="border border-border bg-muted/30 p-6 text-sm text-muted-foreground">Se încarcă dovezile persistate…</div>
	{:else if modelOptions.length === 0}
		<div class="border border-border bg-muted/30 p-6">
			<p class="font-medium text-foreground">Nu există încă evaluări versionate.</p>
			<p class="mt-2 text-sm text-muted-foreground">Rulările legacy rămân disponibile în Analyze, dar nu pot genera certificări.</p>
		</div>
	{:else}
			<Select
				label="Versiune model"
				bind:value={selectedModelVersionId}
				options={modelOptions}
				disabled={loading || evidenceLoading}
				onchange={() => void loadEvidence()}
			/>

			{#if evidenceLoading}
				<div class="border border-border bg-muted/30 p-4 text-sm text-muted-foreground" role="status" aria-live="polite">
					Se încarcă dovezile pentru modelul selectat…
				</div>
			{:else if evidenceError}
				<div class="border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive" role="alert">
					{evidenceError}
				</div>
			{:else if evidence}
			<div class="grid gap-4 lg:grid-cols-3">
				<Card>
					<div class="space-y-3">
						<div class="flex items-center gap-2"><DatabaseZap class="size-5 text-primary" /><h3 class="font-semibold">Versiune</h3></div>
						<p class="font-mono text-sm">{evidence.model_version.model_key} · {evidence.model_version.version}</p>
						<p class="break-all text-xs text-muted-foreground">Config: {evidence.model_version.strategy_config_hash}</p>
						<p class="break-all text-xs text-muted-foreground">Training: {evidence.model_version.training_data_fingerprint}</p>
					</div>
				</Card>
				<Card>
					<div class="space-y-3">
						<div class="flex items-center gap-2"><BadgeCheck class="size-5 text-primary" /><h3 class="font-semibold">Gate paper</h3></div>
						<Badge variant={evidence.gate.manual_paper_allowed ? 'success' : 'warning'}>Manual: {evidence.gate.manual_paper_allowed ? 'permis' : 'blocat'}</Badge>
						<Badge variant={evidence.gate.scheduled_paper_allowed ? 'success' : 'warning'}>Programat: {evidence.gate.scheduled_paper_allowed ? 'permis' : 'blocat'}</Badge>
						<p class="text-sm text-muted-foreground">{evidence.gate.reason}</p>
					</div>
				</Card>
				<Card>
					<div class="space-y-3">
						<div class="flex items-center gap-2"><Activity class="size-5 text-primary" /><h3 class="font-semibold">Drift</h3></div>
						{#if evidence.latest_monitoring}
							<Badge variant={statusVariant(evidence.latest_monitoring.severity)}>{evidence.latest_monitoring.severity}</Badge>
							<p class="text-sm text-muted-foreground">{evidence.latest_monitoring.sample_size} rezultate în fereastra curentă</p>
						{:else}<p class="text-sm text-muted-foreground">Fără snapshot de monitorizare.</p>{/if}
					</div>
				</Card>
			</div>

			{#if evidence.latest_evaluation}
				<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
					{#each [
						['Brier', metric(evidence.latest_evaluation.metrics, 'brier_score')],
						['Log loss', metric(evidence.latest_evaluation.metrics, 'log_loss')],
						['ECE', metric(evidence.latest_evaluation.metrics, 'expected_calibration_error')],
						['Coverage', evidence.latest_evaluation.coverage === null ? '—' : `${(evidence.latest_evaluation.coverage * 100).toFixed(1)}%`],
						['Fold-uri', String(evidence.latest_evaluation.valid_folds)]
					] as item (item[0])}
						<div class="border border-border bg-card p-4"><p class="text-xs uppercase text-muted-foreground">{item[0]}</p><p class="mt-2 font-mono text-lg">{item[1]}</p></div>
					{/each}
				</div>
			{/if}
		{/if}

		<div class="grid gap-4 xl:grid-cols-3">
			<Card><div class="space-y-3"><div class="flex items-center gap-2"><DatabaseZap class="size-5 text-primary" /><h3 class="font-semibold">Evaluări</h3></div>{#each evaluations.slice(0, 8) as row (row.id)}<div class="flex items-start justify-between gap-3 border-t border-border pt-3"><p class="text-sm text-foreground">{row.evaluation_kind} · {row.scope_key}</p><Badge variant={statusVariant(row.status)}>{row.status}</Badge></div>{:else}<p class="text-sm text-muted-foreground">Fără înregistrări.</p>{/each}</div></Card>
			<Card><div class="space-y-3"><div class="flex items-center gap-2"><BadgeCheck class="size-5 text-primary" /><h3 class="font-semibold">Certificări</h3></div>{#each certifications.slice(0, 8) as row (row.id)}<div class="flex items-start justify-between gap-3 border-t border-border pt-3"><p class="text-sm text-foreground">{row.certification_type} · {row.scope_key}</p><Badge variant={statusVariant(row.status)}>{row.status}</Badge></div>{:else}<p class="text-sm text-muted-foreground">Fără înregistrări.</p>{/each}</div></Card>
			<Card><div class="space-y-3"><div class="flex items-center gap-2"><ShieldAlert class="size-5 text-primary" /><h3 class="font-semibold">Monitorizare</h3></div>{#each monitoring.slice(0, 8) as row (row.id)}<div class="flex items-start justify-between gap-3 border-t border-border pt-3"><p class="text-sm text-foreground">{row.scope_key} · n={row.sample_size}</p><Badge variant={statusVariant(row.severity)}>{row.severity}</Badge></div>{:else}<p class="text-sm text-muted-foreground">Fără înregistrări.</p>{/each}</div></Card>
		</div>
	{/if}
</section>

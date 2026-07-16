<script lang="ts">
	import { onMount } from 'svelte';
	import {
		AlertTriangle,
		Clock3,
		Gauge,
		LoaderCircle,
		PauseCircle,
		RefreshCw,
		Save,
		ShieldCheck
	} from 'lucide-svelte';
	import {
		riskApi,
		type RiskPolicy,
		type RiskPolicyInput,
		type RiskPolicyOverview,
		type RiskStakingMode,
		type RiskUsage
	} from '$lib/api/risk';
	import Button from './ui/button/button.svelte';

	type ExplicitBoolean = '' | 'true' | 'false';
	type FormState = {
		stakingMode: '' | RiskStakingMode;
		flatStakePercent: string;
		kellyFraction: string;
		maxTicketPercent: string;
		maxOpenExposurePercent: string;
		maxMatchPercent: string;
		maxTeamPercent: string;
		maxLeagueWindowPercent: string;
		leagueWindowHours: string;
		maxDailyStakePercent: string;
		maxWeeklyStakePercent: string;
		maxDailyTicketCount: string;
		maxWeeklyTicketCount: string;
		accumulatorsEnabled: ExplicitBoolean;
		automationEnabled: ExplicitBoolean;
	};

	type Props = {
		bankrollId: number;
		onSaved?: (overview: RiskPolicyOverview) => void;
	};

	let { bankrollId, onSaved }: Props = $props();
	const headingId = $props.id();

	const emptyForm = (): FormState => ({
		stakingMode: '',
		flatStakePercent: '',
		kellyFraction: '',
		maxTicketPercent: '',
		maxOpenExposurePercent: '',
		maxMatchPercent: '',
		maxTeamPercent: '',
		maxLeagueWindowPercent: '',
		leagueWindowHours: '',
		maxDailyStakePercent: '',
		maxWeeklyStakePercent: '',
		maxDailyTicketCount: '',
		maxWeeklyTicketCount: '',
		accumulatorsEnabled: '',
		automationEnabled: ''
	});

	let overview = $state<RiskPolicyOverview | null>(null);
	let form: FormState = $state(emptyForm());
	let loading = $state(true);
	let saving = $state(false);
	let pausing = $state(false);
	let error = $state('');
	let success = $state('');
	let pauseUntil = $state('');
	let pauseReason = $state('');

	const activePolicy = $derived(overview?.policy ?? null);
	const pendingPolicy = $derived(overview?.pending_policy ?? null);
	const pauseState = $derived(overview?.state ?? null);
	const riskUsage = $derived(overview?.usage ?? null);
	const pauseActive = $derived(
		Boolean(pauseState?.paused_until && new Date(pauseState.paused_until).getTime() > Date.now())
	);

	function percentFromFraction(value: number | null): string {
		return value === null ? '' : String(Number((value * 100).toFixed(4)));
	}

	function explicitBoolean(value: boolean): ExplicitBoolean {
		return value ? 'true' : 'false';
	}

	function populateForm(policy: RiskPolicy | null): void {
		if (!policy) {
			form = emptyForm();
			return;
		}
		form = {
			stakingMode: policy.staking_mode,
			flatStakePercent: percentFromFraction(policy.flat_stake_pct),
			kellyFraction: policy.kelly_fraction === null ? '' : String(policy.kelly_fraction),
			maxTicketPercent: percentFromFraction(policy.max_ticket_pct),
			maxOpenExposurePercent: percentFromFraction(policy.max_open_exposure_pct),
			maxMatchPercent: percentFromFraction(policy.max_match_pct),
			maxTeamPercent: percentFromFraction(policy.max_team_pct),
			maxLeagueWindowPercent: percentFromFraction(policy.max_league_window_pct),
			leagueWindowHours: String(policy.league_window_hours),
			maxDailyStakePercent: percentFromFraction(policy.max_daily_stake_pct),
			maxWeeklyStakePercent: percentFromFraction(policy.max_weekly_stake_pct),
			maxDailyTicketCount:
				policy.max_daily_ticket_count === null ? '' : String(policy.max_daily_ticket_count),
			maxWeeklyTicketCount:
				policy.max_weekly_ticket_count === null ? '' : String(policy.max_weekly_ticket_count),
			accumulatorsEnabled: explicitBoolean(policy.accumulators_enabled),
			automationEnabled: explicitBoolean(policy.automation_enabled)
		};
	}

	async function loadPolicy(): Promise<void> {
		loading = true;
		error = '';
		try {
			overview = await riskApi.getRiskPolicy(bankrollId);
			populateForm(overview?.policy ?? null);
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Politica de risc nu a putut fi încărcată.';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		void loadPolicy();
	});

	function requiredNumber(value: string, label: string): number {
		if (value.trim() === '') throw new Error(`${label} trebuie configurat explicit.`);
		const parsed = Number(value);
		if (!Number.isFinite(parsed) || parsed <= 0) {
			throw new Error(`${label} trebuie să fie un număr mai mare decât zero.`);
		}
		return parsed;
	}

	function requiredInteger(value: string, label: string): number {
		const parsed = requiredNumber(value, label);
		if (!Number.isInteger(parsed)) throw new Error(`${label} trebuie să fie un număr întreg.`);
		return parsed;
	}

	function percentFraction(value: string, label: string, ceiling: number): number {
		const parsed = requiredNumber(value, label);
		if (parsed > ceiling) throw new Error(`${label} nu poate depăși ${ceiling}%.`);
		return parsed / 100;
	}

	function parseExplicitBoolean(value: ExplicitBoolean, label: string): boolean {
		if (value === '') throw new Error(`${label} trebuie ales explicit.`);
		return value === 'true';
	}

	function buildPayload(): RiskPolicyInput {
		if (form.stakingMode === '') throw new Error('Metoda de staking trebuie aleasă explicit.');
		const flatStakePercent =
			form.stakingMode === 'flat_percent'
				? percentFraction(form.flatStakePercent, 'Miza flat', 5)
				: null;
		const kellyFraction =
			form.stakingMode === 'fractional_kelly'
				? requiredNumber(form.kellyFraction, 'Fracția Kelly')
				: null;
		if (kellyFraction !== null && kellyFraction > 0.5) {
			throw new Error('Fracția Kelly nu poate depăși 0,5.');
		}

		const dailyStakeFraction = percentFraction(
			form.maxDailyStakePercent,
			'Miza maximă în 24h',
			100
		);
		const weeklyStakeFraction = percentFraction(
			form.maxWeeklyStakePercent,
			'Miza maximă în 7 zile',
			100
		);
		const dailyCount = requiredInteger(form.maxDailyTicketCount, 'Numărul maxim de bilete în 24h');
		const weeklyCount = requiredInteger(form.maxWeeklyTicketCount, 'Numărul maxim de bilete în 7 zile');
		if (dailyStakeFraction > weeklyStakeFraction) {
			throw new Error('Limita de miză pe 24h nu poate depăși limita pe 7 zile.');
		}
		if (dailyCount > weeklyCount) {
			throw new Error('Numărul de bilete pe 24h nu poate depăși numărul pe 7 zile.');
		}

		return {
			staking_mode: form.stakingMode,
			flat_stake_pct: flatStakePercent,
			kelly_fraction: kellyFraction,
			max_ticket_pct: percentFraction(form.maxTicketPercent, 'Expunerea per ticket', 5),
			max_open_exposure_pct: percentFraction(
				form.maxOpenExposurePercent,
				'Expunerea totală deschisă',
				20
			),
			max_match_pct: percentFraction(form.maxMatchPercent, 'Expunerea per meci', 20),
			max_team_pct: percentFraction(form.maxTeamPercent, 'Expunerea per echipă', 20),
			max_league_window_pct: percentFraction(
				form.maxLeagueWindowPercent,
				'Expunerea per ligă și fereastră',
				20
			),
			league_window_hours: requiredInteger(form.leagueWindowHours, 'Fereastra ligii'),
			max_daily_stake_pct: dailyStakeFraction,
			max_weekly_stake_pct: weeklyStakeFraction,
			max_daily_ticket_count: dailyCount,
			max_weekly_ticket_count: weeklyCount,
			accumulators_enabled: parseExplicitBoolean(
				form.accumulatorsEnabled,
				'Permisiunea pentru acumulatoare'
			),
			automation_enabled: parseExplicitBoolean(
				form.automationEnabled,
				'Permisiunea pentru automatizare'
			)
		};
	}

	async function savePolicy(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		saving = true;
		error = '';
		success = '';
		try {
			const saved = await riskApi.saveRiskPolicy(bankrollId, buildPayload());
			overview = saved;
			populateForm(saved.policy ?? null);
			success = saved.pending_policy
				? 'Politica a fost salvată și relaxările vor intra în vigoare la data indicată.'
				: 'Politica de risc a fost salvată.';
			onSaved?.(saved);
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Politica de risc nu a putut fi salvată.';
		} finally {
			saving = false;
		}
	}

	async function activatePause(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		pausing = true;
		error = '';
		success = '';
		try {
			if (!pauseUntil) throw new Error('Data până la care se aplică pauza este obligatorie.');
			if (!pauseReason.trim()) throw new Error('Motivul pauzei este obligatoriu.');
			const until = new Date(pauseUntil);
			if (!Number.isFinite(until.getTime()) || until.getTime() <= Date.now()) {
				throw new Error('Pauza trebuie să se încheie în viitor.');
			}
			const paused = await riskApi.pauseBankroll(bankrollId, {
				paused_until: until.toISOString(),
				pause_reason: pauseReason.trim()
			});
			overview = paused;
			pauseUntil = '';
			pauseReason = '';
			success = 'Pauza a fost activată. Generarea de bilete rămâne blocată până la expirare.';
			onSaved?.(paused);
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Pauza nu a putut fi activată.';
		} finally {
			pausing = false;
		}
	}

	function money(value: number | null | undefined): string {
		return typeof value === 'number' && Number.isFinite(value)
			? new Intl.NumberFormat('ro-RO', { style: 'currency', currency: 'RON' }).format(value)
			: '—';
	}

	function percentage(value: number | null | undefined): string {
		return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—';
	}

	function dateTime(value: string | null | undefined): string {
		if (!value) return '—';
		const date = new Date(value);
		return Number.isFinite(date.getTime())
			? new Intl.DateTimeFormat('ro-RO', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
			: '—';
	}

	function usageRows(usage: RiskUsage | null): Array<{ label: string; value: string }> {
		if (!usage) return [];
		return [
			{ label: 'Sold disponibil', value: money(usage.available_balance ?? usage.bankroll_balance) },
			{
				label: 'Expunere deschisă',
				value: `${money(usage.open_exposure_amount)} · ${percentage(usage.open_exposure_pct)}`
			},
			{ label: 'Mize în ultimele 24h', value: money(usage.staked_last_24h) },
			{ label: 'Mize în ultimele 7 zile', value: money(usage.staked_last_7d) },
			{ label: 'Bilete în ultimele 24h', value: String(usage.ticket_count_last_24h ?? '—') },
			{ label: 'Bilete în ultimele 7 zile', value: String(usage.ticket_count_last_7d ?? '—') }
		];
	}
</script>

<section class="border border-border bg-card p-4 sm:p-5" aria-labelledby={`${headingId}-title`}>
	<div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
		<div class="flex min-w-0 items-start gap-3">
			<ShieldCheck class="mt-0.5 size-6 shrink-0 text-football-green" aria-hidden="true" />
			<div>
				<p class="text-xs font-semibold uppercase tracking-wide text-football-green">Paper betting · fail-closed</p>
				<h2 id={`${headingId}-title`} class="mt-1 text-xl font-semibold text-foreground">Politica de risc</h2>
				<p class="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
					Platforma nu generează bilete până când alegi explicit staking-ul și toate limitele.
				</p>
			</div>
		</div>
		<Button variant="outline" disabled={loading || saving || pausing} onclick={() => void loadPolicy()}>
			<RefreshCw class={`mr-2 size-4 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />
			Reîncarcă
		</Button>
	</div>

	<div class="mt-4 grid gap-3 sm:grid-cols-2">
		<div class="border border-football-red/40 bg-football-red/10 p-3">
			<p class="text-xs font-semibold uppercase tracking-wide text-football-red">Plafon de platformă</p>
			<p class="mt-1 text-lg font-mono font-semibold text-foreground">5% / ticket</p>
			<p class="mt-1 text-xs leading-5 text-muted-foreground">Nicio politică nu poate ridica acest plafon.</p>
		</div>
		<div class="border border-football-red/40 bg-football-red/10 p-3">
			<p class="text-xs font-semibold uppercase tracking-wide text-football-red">Plafon de platformă</p>
			<p class="mt-1 text-lg font-mono font-semibold text-foreground">20% expunere deschisă</p>
			<p class="mt-1 text-xs leading-5 text-muted-foreground">Este calculată pe toate biletele paper active.</p>
		</div>
	</div>

	{#if error}
		<div class="mt-4 flex gap-2 border border-[hsl(var(--status-danger-border))] bg-[hsl(var(--status-danger-bg))] p-3 text-sm text-[hsl(var(--status-danger-text))]" role="alert">
			<AlertTriangle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
			<p>{error}</p>
		</div>
	{/if}
	{#if success}
		<p class="mt-4 border border-[hsl(var(--status-success-border))] bg-[hsl(var(--status-success-bg))] p-3 text-sm text-[hsl(var(--status-success-text))]" role="status">{success}</p>
	{/if}

	{#if loading}
		<div class="mt-5 flex min-h-40 items-center justify-center gap-2 border border-border bg-background text-sm text-muted-foreground" role="status">
			<LoaderCircle class="size-5 animate-spin" aria-hidden="true" /> Se încarcă politica de risc...
		</div>
	{:else}
		<div class="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(18rem,0.8fr)]">
			<form class="space-y-5 border border-border bg-background p-4" onsubmit={savePolicy}>
				<div>
					<h3 class="font-semibold text-foreground">Configurare explicită</h3>
					<p class="mt-1 text-xs leading-5 text-muted-foreground">
						{activePolicy ? `Editezi politica activă v${activePolicy.version}.` : 'Nu există o politică activă. Niciun câmp nu este completat automat.'}
					</p>
				</div>

				<fieldset class="space-y-3">
					<legend class="text-sm font-semibold text-foreground">Staking</legend>
					<label class="block space-y-1.5 text-sm font-medium text-foreground">
						<span>Metodă</span>
						<select class="min-h-11 w-full border border-input bg-card px-3 text-sm" bind:value={form.stakingMode} required>
							<option value="" disabled>Alege explicit</option>
							<option value="flat_percent">Procent fix din bankroll</option>
							<option value="fractional_kelly">Kelly fracționat</option>
						</select>
					</label>
					{#if form.stakingMode === 'flat_percent'}
						<label class="block space-y-1.5 text-sm font-medium text-foreground">
							<span>Miză fixă din bankroll (%)</span>
							<input class="min-h-11 w-full border border-input bg-card px-3" type="number" min="0.01" max="5" step="0.01" bind:value={form.flatStakePercent} required />
						</label>
					{:else if form.stakingMode === 'fractional_kelly'}
						<label class="block space-y-1.5 text-sm font-medium text-foreground">
							<span>Fracție Kelly (max. 0,5)</span>
							<input class="min-h-11 w-full border border-input bg-card px-3" type="number" min="0.01" max="0.5" step="0.01" bind:value={form.kellyFraction} required />
						</label>
					{/if}
				</fieldset>

				<fieldset class="space-y-3">
					<legend class="text-sm font-semibold text-foreground">Expunere maximă</legend>
					<div class="grid gap-3 sm:grid-cols-2">
						{#each [
							{ key: 'maxTicketPercent', label: 'Per ticket (%)', max: 5 },
							{ key: 'maxOpenExposurePercent', label: 'Total deschis (%)', max: 20 },
							{ key: 'maxMatchPercent', label: 'Per meci (%)', max: 20 },
							{ key: 'maxTeamPercent', label: 'Per echipă (%)', max: 20 },
							{ key: 'maxLeagueWindowPercent', label: 'Per ligă/fereastră (%)', max: 20 }
						] as field (field.key)}
							<label class="block space-y-1.5 text-sm font-medium text-foreground">
								<span>{field.label}</span>
								<input class="min-h-11 w-full border border-input bg-card px-3" type="number" min="0.01" max={field.max} step="0.01" bind:value={form[field.key as keyof FormState]} required />
							</label>
						{/each}
						<label class="block space-y-1.5 text-sm font-medium text-foreground">
							<span>Fereastră ligă (ore)</span>
							<input class="min-h-11 w-full border border-input bg-card px-3" type="number" min="1" step="1" bind:value={form.leagueWindowHours} required />
						</label>
					</div>
				</fieldset>

				<fieldset class="space-y-3">
					<legend class="text-sm font-semibold text-foreground">Limite rolling</legend>
					<div class="grid gap-3 sm:grid-cols-2">
						<label class="block space-y-1.5 text-sm font-medium text-foreground"><span>Miză maximă în 24h (% bankroll)</span><input class="min-h-11 w-full border border-input bg-card px-3" type="number" min="0.01" max="100" step="0.01" bind:value={form.maxDailyStakePercent} required /></label>
						<label class="block space-y-1.5 text-sm font-medium text-foreground"><span>Miză maximă în 7 zile (% bankroll)</span><input class="min-h-11 w-full border border-input bg-card px-3" type="number" min="0.01" max="100" step="0.01" bind:value={form.maxWeeklyStakePercent} required /></label>
						<label class="block space-y-1.5 text-sm font-medium text-foreground"><span>Bilete maxime în 24h</span><input class="min-h-11 w-full border border-input bg-card px-3" type="number" min="1" step="1" bind:value={form.maxDailyTicketCount} required /></label>
						<label class="block space-y-1.5 text-sm font-medium text-foreground"><span>Bilete maxime în 7 zile</span><input class="min-h-11 w-full border border-input bg-card px-3" type="number" min="1" step="1" bind:value={form.maxWeeklyTicketCount} required /></label>
					</div>
				</fieldset>

				<fieldset class="space-y-3">
					<legend class="text-sm font-semibold text-foreground">Funcții cu risc suplimentar</legend>
					<div class="grid gap-3 sm:grid-cols-2">
						<label class="block space-y-1.5 text-sm font-medium text-foreground"><span>Acumulatoare experimentale</span><select class="min-h-11 w-full border border-input bg-card px-3" bind:value={form.accumulatorsEnabled} required><option value="" disabled>Alege explicit</option><option value="false">Dezactivate</option><option value="true">Activate</option></select></label>
						<label class="block space-y-1.5 text-sm font-medium text-foreground"><span>Generare automată de drafturi</span><select class="min-h-11 w-full border border-input bg-card px-3" bind:value={form.automationEnabled} required><option value="" disabled>Alege explicit</option><option value="false">Dezactivată</option><option value="true">Activată</option></select></label>
					</div>
				</fieldset>

				<Button type="submit" disabled={saving || pausing}>
					{#if saving}<LoaderCircle class="mr-2 size-4 animate-spin" aria-hidden="true" />{:else}<Save class="mr-2 size-4" aria-hidden="true" />{/if}
					Salvează politica
				</Button>
			</form>

			<aside class="space-y-4">
				<div class="border border-border bg-background p-4">
					<div class="flex items-start gap-2"><Gauge class="mt-0.5 size-5 text-football-blue" aria-hidden="true" /><div><h3 class="font-semibold text-foreground">Utilizare curentă</h3><p class="mt-1 text-xs text-muted-foreground">Expunere și rulaj paper raportate de backend.</p></div></div>
					{#if usageRows(riskUsage).length === 0}
						<p class="mt-4 border border-dashed border-border p-3 text-sm text-muted-foreground">Datele de utilizare nu sunt încă disponibile.</p>
					{:else}
						<dl class="mt-4 space-y-2">
							{#each usageRows(riskUsage) as row (row.label)}
								<div class="flex items-start justify-between gap-3 border-b border-border pb-2 text-sm"><dt class="text-muted-foreground">{row.label}</dt><dd class="text-right font-mono text-foreground">{row.value}</dd></div>
							{/each}
						</dl>
					{/if}
				</div>

				{#if pendingPolicy}
					<div class="border border-football-gold/40 bg-football-gold/10 p-4">
						<div class="flex gap-2"><Clock3 class="mt-0.5 size-5 shrink-0 text-football-gold" aria-hidden="true" /><div><h3 class="font-semibold text-foreground">Relaxare în așteptare</h3><p class="mt-1 text-sm leading-5 text-muted-foreground">Politica v{pendingPolicy.version} intră în vigoare la {dateTime(pendingPolicy.effective_from)}. Limitele curente rămân active până atunci.</p></div></div>
					</div>
				{/if}

				<form class="border border-border bg-background p-4" onsubmit={activatePause}>
					<div class="flex items-start gap-2"><PauseCircle class="mt-0.5 size-5 shrink-0 text-football-gold" aria-hidden="true" /><div><h3 class="font-semibold text-foreground">Pauză voluntară</h3><p class="mt-1 text-xs leading-5 text-muted-foreground">Pauza blochează generarea. Nu este scurtată din acest panou.</p></div></div>
					{#if pauseActive}
						<p class="mt-3 border border-football-gold/40 bg-football-gold/10 p-3 text-sm text-foreground">Activă până la {dateTime(pauseState?.paused_until)}{pauseState?.pause_reason ? ` · ${pauseState.pause_reason}` : ''}</p>
					{/if}
					<label class="mt-4 block space-y-1.5 text-sm font-medium text-foreground"><span>Pauză până la</span><input class="min-h-11 w-full border border-input bg-card px-3" type="datetime-local" bind:value={pauseUntil} required /></label>
					<label class="mt-3 block space-y-1.5 text-sm font-medium text-foreground"><span>Motiv</span><textarea class="min-h-24 w-full border border-input bg-card p-3 text-sm" maxlength="255" bind:value={pauseReason} required></textarea></label>
					<Button class="mt-4" type="submit" variant="outline" disabled={pausing || saving}>
						{#if pausing}<LoaderCircle class="mr-2 size-4 animate-spin" aria-hidden="true" />{:else}<PauseCircle class="mr-2 size-4" aria-hidden="true" />{/if}
						Activează pauza
					</Button>
				</form>
			</aside>
		</div>
	{/if}
</section>

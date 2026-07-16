<script lang="ts">
	import { AlertTriangle, CheckCircle2, Database, ShieldCheck } from 'lucide-svelte';
	import type { Ticket } from '$lib/types';
	import Badge from './ui/Badge.svelte';
	import {
		ticketStructuralSignals,
		ticketLegSnapshotCompleteness
	} from './tickets-panel.helpers';

	let { tickets }: { tickets: Ticket[] } = $props();

	const ticketsWithStructuralSignals = $derived(
		tickets.filter((ticket) => ticketStructuralSignals(ticket).length > 0).length
	);
	const snapshotTotals = $derived.by(() =>
		tickets.reduce(
			(total, ticket) => {
				const current = ticketLegSnapshotCompleteness(ticket);
				return { complete: total.complete + current.complete, total: total.total + current.total };
			},
			{ complete: 0, total: 0 }
		)
	);

	function percent(value: number | null | undefined, fraction = false): string {
		if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
		return `${(fraction ? value * 100 : value).toFixed(1)}%`;
	}

	function probabilityBasis(value: string | null | undefined): string {
		if (value === 'consensus_de_vig') return 'consens fără marjă';
		if (value === 'inverse_selected_odds') return '1 / cota selectată';
		return value || 'bază indisponibilă';
	}
</script>

<section class="border border-border bg-background p-3 sm:p-4" aria-labelledby="decision-evidence-heading">
	<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
		<div>
			<p class="text-xs font-semibold uppercase tracking-wide text-football-blue">Dovada deciziei</p>
			<h3 id="decision-evidence-heading" class="mt-1 text-base font-semibold text-foreground">Snapshot și dependențe pe bilet</h3>
			<p class="mt-1 max-w-3xl text-sm leading-5 text-muted-foreground">Valorile de mai jos sunt cele salvate la generare. Nu se rescriu când modelul sau cotele se schimbă ulterior.</p>
		</div>
		<Badge variant={ticketsWithStructuralSignals > 0 ? 'warning' : 'success'}>
			{ticketsWithStructuralSignals > 0 ? `${ticketsWithStructuralSignals} cu semnale structurale` : 'Fără concentrare structurală'}
		</Badge>
	</div>

	<div class="mt-4 grid gap-px border border-border bg-border sm:grid-cols-3">
		<div class="min-w-0 bg-card p-3">
			<p class="text-xs text-muted-foreground">Bilete revizuite</p>
			<p class="mt-1 font-mono text-lg text-foreground">{tickets.length}</p>
		</div>
		<div class="min-w-0 bg-card p-3">
			<p class="text-xs text-muted-foreground">Snapshot complet</p>
			<p class="mt-1 font-mono text-lg {snapshotTotals.complete === snapshotTotals.total ? 'text-football-green' : 'text-football-gold'}">{snapshotTotals.complete}/{snapshotTotals.total}</p>
		</div>
		<div class="min-w-0 bg-card p-3">
			<p class="text-xs text-muted-foreground">Semnale structurale</p>
			<p class="mt-1 font-mono text-lg {ticketsWithStructuralSignals > 0 ? 'text-football-gold' : 'text-football-green'}">{ticketsWithStructuralSignals}</p>
		</div>
	</div>

	<div class="mt-4 space-y-2">
		{#each tickets as ticket (ticket.id)}
			{@const warnings = ticketStructuralSignals(ticket)}
			{@const completeness = ticketLegSnapshotCompleteness(ticket)}
			<details class="group border border-border bg-card" data-testid="ticket-decision-evidence">
				<summary class="flex min-h-12 cursor-pointer list-none flex-wrap items-center justify-between gap-2 px-3 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:px-4">
					<span class="min-w-0">
						<span class="block truncate font-mono text-sm font-semibold text-foreground">Bilet #{ticket.reference ?? ticket.id}</span>
						<span class="mt-1 block text-xs text-muted-foreground">{ticket.legs.length} selecții · snapshot {completeness.complete}/{completeness.total}</span>
					</span>
					<span class="inline-flex items-center gap-1 text-xs {warnings.length > 0 ? 'text-football-gold' : 'text-football-green'}">
						{#if warnings.length > 0}<AlertTriangle class="size-4" aria-hidden="true" />{warnings.length} semnal{:else}<CheckCircle2 class="size-4" aria-hidden="true" />fără concentrare observabilă{/if}
					</span>
				</summary>

				<div class="space-y-3 border-t border-border p-3 sm:p-4">
					{#each warnings as warning (`${ticket.id}-${warning.kind}-${warning.matchIds.join('-')}-${warning.legIds.join('-')}`)}
						<div class="flex gap-2 border border-football-gold/40 bg-football-gold/10 p-3 text-sm text-foreground" role="note">
							<AlertTriangle class="mt-0.5 size-4 shrink-0 text-football-gold" aria-hidden="true" />
							<div class="min-w-0"><p class="font-medium">{warning.label}</p><p class="mt-1 break-words text-xs leading-5 text-muted-foreground">{warning.message} Piețe: {warning.markets.join(', ')}.</p></div>
						</div>
					{/each}

					<div class="space-y-2">
						{#each ticket.legs as leg (leg.id)}
							<article class="min-w-0 border border-border bg-background p-3">
								<div class="flex flex-wrap items-start justify-between gap-2">
									<div class="min-w-0"><p class="break-words text-sm font-medium text-foreground">{leg.match?.home_team ?? 'Meci'} vs {leg.match?.away_team ?? `#${leg.match_id}`}</p><p class="mt-1 break-words font-mono text-xs text-muted-foreground">{leg.market} · {leg.selection} · @{leg.odds.toFixed(2)}</p></div>
									<Badge variant={typeof leg.prediction_run_id_snapshot === 'number' ? 'info' : 'warning'}>{typeof leg.prediction_run_id_snapshot === 'number' ? `run #${leg.prediction_run_id_snapshot}` : 'snapshot vechi'}</Badge>
								</div>
								<div class="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
									<div class="min-w-0 border-l-2 border-football-blue pl-2"><p class="text-muted-foreground">Prob. model</p><p class="mt-1 font-mono text-foreground">{percent(leg.model_probability_snapshot, true)}</p></div>
									<div class="min-w-0 border-l-2 border-football-gold pl-2"><p class="text-muted-foreground">Prob. piață</p><p class="mt-1 font-mono text-foreground">{percent(leg.market_probability_snapshot, true)}</p><p class="mt-1 break-words text-[11px] text-muted-foreground">{probabilityBasis(leg.market_probability_basis_snapshot)}</p></div>
									<div class="min-w-0 border-l-2 border-football-green pl-2"><p class="text-muted-foreground">EV / edge</p><p class="mt-1 font-mono text-foreground">{percent(leg.expected_value_snapshot, true)} / {percent(leg.edge_pct_snapshot)}</p></div>
									<div class="min-w-0 border-l-2 border-border pl-2"><p class="text-muted-foreground">Fiabilitate</p><p class="mt-1 break-words text-foreground">{leg.reliability_label_snapshot ?? '—'}</p><p class="mt-1 font-mono text-[11px] text-muted-foreground">{percent(leg.reliability_score_snapshot)}</p></div>
								</div>
							</article>
						{/each}
					</div>
					<p class="flex gap-2 text-xs leading-5 text-muted-foreground"><Database class="mt-0.5 size-4 shrink-0" aria-hidden="true" />Snapshot-ul permite auditarea deciziei istorice; probabilitatea de piață indică explicit baza de calcul.</p>
					<p class="flex gap-2 text-xs leading-5 text-muted-foreground"><ShieldCheck class="mt-0.5 size-4 shrink-0" aria-hidden="true" />Acestea sunt semnale conservative de dependență sau concentrare din structura biletului. Corelația statistică nu este disponibilă fără un model comun al rezultatelor.</p>
				</div>
			</details>
		{/each}
	</div>
</section>

import type { ValueBetFeed, ValueBetItem, ValueBetTrustMetadata } from '$lib/types';

type ValueBetReliabilityObject = {
	label?: string | null;
	score?: number | null;
	is_ticket_eligible?: boolean | null;
	block_reasons?: string[] | null;
};

export type RawValueBetItem = Omit<
	ValueBetItem,
	'reliability' | 'trust' | 'is_ticket_eligible'
> & {
	reliability?: string | ValueBetReliabilityObject | null;
	trust?: ValueBetTrustMetadata | null;
	is_ticket_eligible?: boolean | null;
	is_betslip_eligible?: boolean | null;
};

export type RawValueBetFeed = Omit<ValueBetFeed, 'items'> & {
	items: RawValueBetItem[];
};

function isReliabilityObject(value: unknown): value is ValueBetReliabilityObject {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function uniqueStrings(values: unknown[]): string[] {
	return Array.from(
		new Set(
			values.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
		)
	);
}

export function normalizeValueBetItem(item: RawValueBetItem): ValueBetItem {
	const { is_betslip_eligible: isBetslipEligible, ...canonicalItem } = item;
	const reliabilityObject = isReliabilityObject(item.reliability) ? item.reliability : null;
	const trust = item.trust ?? null;
	const qualityReasons = uniqueStrings(item.quality_reasons ?? []);
	const blockReasons = uniqueStrings([
		...(item.block_reasons ?? []),
		...(trust?.block_reasons ?? []),
		...(reliabilityObject?.block_reasons ?? []),
		...qualityReasons
	]);
	const reliability =
		typeof item.reliability === 'string'
			? item.reliability
			: reliabilityObject?.label ?? trust?.reliability_label ?? null;
	const isTicketEligible =
		isBetslipEligible ??
		item.is_ticket_eligible ??
		trust?.is_ticket_eligible ??
		reliabilityObject?.is_ticket_eligible ??
		null;
	const reliabilityScore =
		item.reliability_score ?? trust?.reliability_score ?? reliabilityObject?.score ?? null;

	return {
		...canonicalItem,
		reliability,
		reliability_score: reliabilityScore,
		quality_reasons: qualityReasons,
		is_ticket_eligible: isTicketEligible,
		block_reasons: blockReasons,
		source_ok: item.source_ok ?? trust?.source_ok ?? null,
		data_age_seconds: item.data_age_seconds ?? trust?.data_age_seconds ?? null,
		odds_freshness_seconds: item.odds_freshness_seconds ?? trust?.odds_freshness_seconds ?? null,
		selection_age_seconds: item.selection_age_seconds ?? trust?.selection_age_seconds ?? null,
		model_drift_flag: item.model_drift_flag ?? trust?.model_drift_flag ?? null,
		trust: trust
			? {
					...trust,
					is_ticket_eligible: isTicketEligible,
					block_reasons: blockReasons,
					reliability_label: trust.reliability_label ?? reliability,
					reliability_score: reliabilityScore
				}
			: null
	};
}

export function normalizeValueBetFeed(response: RawValueBetFeed | RawValueBetItem[]): ValueBetFeed {
	if (Array.isArray(response)) {
		return {
			items: response.map(normalizeValueBetItem),
			source: 'prediction',
			is_demo: false,
			generated_at: new Date().toISOString()
		};
	}

	return {
		...response,
		items: (response.items ?? []).map(normalizeValueBetItem)
	};
}

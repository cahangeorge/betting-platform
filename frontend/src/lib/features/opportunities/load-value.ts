import { predictionsApi } from '$lib/api/predictions';

export async function loadValueOpportunities({ fetch }: { fetch: typeof globalThis.fetch }) {
	try {
		const response = await predictionsApi.getValueBets(fetch);
		return {
			valueBets: response.items ?? [],
			generatedAt: response.generated_at,
			loading: false,
			source: response.source,
			isDemo: response.is_demo,
			error: (response.items ?? []).length === 0 ? 'No value bets are currently available.' : null
		};
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Failed to load value bets.';
		return {
			valueBets: [],
			generatedAt: new Date().toISOString(),
			loading: false,
			source: 'prediction',
			isDemo: false,
			error:
				message.includes('404')
					? 'Fluxul Value Bets nu este disponibil momentan.'
					: message
		};
	}
}

export type ValueOpportunitiesData = Awaited<ReturnType<typeof loadValueOpportunities>>;

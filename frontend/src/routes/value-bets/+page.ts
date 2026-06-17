import type { PageLoad } from './$types';
import { predictionsApi } from '$lib/api/predictions';

export const load: PageLoad = async ({ fetch }) => {
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
					? 'Value bet feed is unavailable because the backend endpoint is not implemented yet.'
					: message
		};
	}
};

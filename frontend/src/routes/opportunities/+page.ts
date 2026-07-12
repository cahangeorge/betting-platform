import type { PageLoad } from './$types';
import { loadLiveOpportunities } from '$lib/features/opportunities/load-live';
import { loadValueOpportunities } from '$lib/features/opportunities/load-value';

export const load: PageLoad = async (event) => {
	const view = event.url.searchParams.get('view') === 'live' ? 'live' : 'value';
	const payload = view === 'live' ? await loadLiveOpportunities(event) : await loadValueOpportunities(event);
	return { view, payload };
};

import type { PageLoad } from './$types';
import { load as loadLive } from '../live/+page';
import { load as loadValue } from '../value-bets/+page';

const loadLiveForCanonical = loadLive as unknown as (
	event: Parameters<PageLoad>[0]
) => ReturnType<typeof loadLive>;
const loadValueForCanonical = loadValue as unknown as (
	event: Parameters<PageLoad>[0]
) => ReturnType<typeof loadValue>;

export const load: PageLoad = async (event) => {
	const view = event.url.searchParams.get('view') === 'live' ? 'live' : 'value';
	const payload = view === 'live' ? await loadLiveForCanonical(event) : await loadValueForCanonical(event);
	return { view, payload };
};
